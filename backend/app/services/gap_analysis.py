"""
Gap Analysis Service

Matches stock analysis with user positions to identify:
- OPPORTUNITY: BUY signal, don't own
- ACCUMULATE: BUY signal, already own
- DANGER_EXIT: SELL signal, currently own
- WAIT_MARKET_BAD: BUY signal but market is RED
- HOLD: Own but no strong signal
- NO_ACTION: Don't own, no strong signal

Clean Code Principles Applied:
- Single Responsibility: Gap analysis only
- Enum for type-safe signal values
- Type hints throughout
- Clear separation of concerns
"""

from __future__ import annotations

from enum import Enum
from typing import Final

from sqlalchemy.orm import Session

from ..models.portfolio import MarketStatus, MarketStatusEnum, Position
from ..models.stock import Stock


# ==============================================================================
# Constants & Enums
# ==============================================================================

class MatchSignal(str, Enum):
    """Match signals for gap analysis between stock signals and user positions."""
    
    OPPORTUNITY = "OPPORTUNITY"      # BUY signal but don't own
    ACCUMULATE = "ACCUMULATE"        # BUY signal and already own
    DANGER_EXIT = "DANGER_EXIT"      # SELL signal and own
    WAIT_MARKET_BAD = "WAIT_MARKET_BAD"  # BUY signal but market is RED
    HOLD = "HOLD"                    # Own but no strong signal
    NO_ACTION = "NO_ACTION"          # Don't own and no strong signal


# Trading signal categories
BUY_SIGNALS: Final[tuple[str, ...]] = ("BUY_NOW", "ACCUMULATE")
SELL_SIGNALS: Final[tuple[str, ...]] = ("SELL", "TRIM", "AVOID")


class GapAnalysisService:
    """
    Service for analyzing gaps between stock signals and portfolio positions.
    
    Provides methods to:
    - Get market status (Traffic Light system)
    - Match stocks with user positions
    - Identify opportunities and danger exits
    """
    
    # ==========================================================================
    # Market Status
    # ==========================================================================

    @staticmethod
    def get_market_status(db: Session) -> MarketStatusEnum:
        """
        Get current market status (Traffic Light).
        
        Creates default GREEN status if not exists.
        
        Args:
            db: Database session
            
        Returns:
            Current market status enum
        """
        status = db.query(MarketStatus).first()
        
        if status is None:
            status = MarketStatus(status=MarketStatusEnum.GREEN)
            db.add(status)
            db.commit()
            
        return status.status

    # ==========================================================================
    # Position Queries
    # ==========================================================================

    @staticmethod
    def get_user_positions(
        db: Session, 
        portfolio_id: int | None = None
    ) -> dict[str, Position]:
        """
        Get user positions as a dictionary keyed by ticker.
        
        Args:
            db: Database session
            portfolio_id: Optional portfolio ID to filter
            
        Returns:
            Dict mapping ticker to Position object
        """
        query = db.query(Position)
        
        if portfolio_id:
            query = query.filter(Position.portfolio_id == portfolio_id)
        
        positions = query.all()
        return {pos.ticker: pos for pos in positions}

    # ==========================================================================
    # Signal Calculation
    # ==========================================================================

    @staticmethod
    def calculate_match_signal(
        stock: Stock,
        user_position: Position | None,
        market_status: MarketStatusEnum,
    ) -> MatchSignal:
        """
        Calculate the match signal based on stock analysis and user position.
        
        Logic:
        - BUY + No Position = OPPORTUNITY
        - BUY + Has Position = ACCUMULATE
        - SELL + Has Position = DANGER_EXIT
        - RED Market + BUY = WAIT_MARKET_BAD
        - Has Position + No Strong Signal = HOLD
        - No Position + No Strong Signal = NO_ACTION
        
        Args:
            stock: Stock with analysis
            user_position: User's position in this stock (None if not owned)
            market_status: Current market condition
            
        Returns:
            MatchSignal enum value
        """
        has_position = user_position is not None
        action_verdict = stock.action_verdict
        
        is_buy_signal = action_verdict in BUY_SIGNALS
        is_sell_signal = action_verdict in SELL_SIGNALS
        
        # RED market overrides BUY signals
        if market_status == MarketStatusEnum.RED and is_buy_signal:
            return MatchSignal.WAIT_MARKET_BAD
        
        # BUY signal logic
        if is_buy_signal:
            return MatchSignal.ACCUMULATE if has_position else MatchSignal.OPPORTUNITY
        
        # SELL signal logic
        if is_sell_signal:
            return MatchSignal.DANGER_EXIT if has_position else MatchSignal.NO_ACTION
        
        # WATCH_LIST logic
        if action_verdict == "WATCH_LIST":
            return MatchSignal.HOLD if has_position else MatchSignal.NO_ACTION
        
        # Default
        return MatchSignal.HOLD if has_position else MatchSignal.NO_ACTION

    # ==========================================================================
    # Enrichment & Analysis
    # ==========================================================================

    @staticmethod
    def enrich_stocks_with_positions(
        db: Session,
        stocks: list[Stock],
        portfolio_id: int | None = None,
    ) -> list[dict]:
        """
        Enrich stock objects with user position data and match signals.
        
        Args:
            db: Database session
            stocks: List of Stock objects
            portfolio_id: Optional portfolio ID to filter positions
            
        Returns:
            List of enriched stock dicts with position and signal data
        """
        market_status = GapAnalysisService.get_market_status(db)
        positions = GapAnalysisService.get_user_positions(db, portfolio_id)
        
        enriched_stocks = []
        
        for stock in stocks:
            position = positions.get(stock.ticker)
            match_signal = GapAnalysisService.calculate_match_signal(
                stock, position, market_status
            )
            
            stock_dict = {
                # Stock analysis data
                "id": stock.id,
                "ticker": stock.ticker,
                "company_name": stock.company_name,
                "action_verdict": stock.action_verdict,
                "entry_zone": stock.entry_zone,
                "price_target_short": stock.price_target_short,
                "price_target_long": stock.price_target_long,
                "stop_loss_risk": stock.stop_loss_risk,
                "moat_rating": stock.moat_rating,
                "gomes_score": stock.gomes_score,
                "sentiment": stock.sentiment,
                "edge": stock.edge,
                "risks": stock.risks,
                "catalysts": stock.catalysts,
                "trade_rationale": stock.trade_rationale,
                "chart_setup": stock.chart_setup,
                "created_at": stock.created_at,
                "updated_at": stock.updated_at,
                # Position data (if owned)
                "user_holding": position is not None,
                "holding_quantity": position.shares_count if position else None,
                "holding_avg_cost": position.avg_cost if position else None,
                "holding_current_price": position.current_price if position else None,
                "holding_unrealized_pl": position.unrealized_pl if position else None,
                "holding_unrealized_pl_percent": position.unrealized_pl_percent if position else None,
                # Gap analysis
                "match_signal": match_signal.value,
                "market_status": market_status.value,
            }
            
            enriched_stocks.append(stock_dict)
        
        return enriched_stocks

    # ==========================================================================
    # Convenience Queries
    # ==========================================================================

    @staticmethod
    def get_opportunities(
        db: Session,
        portfolio_id: int | None = None,
    ) -> list[dict]:
        """
        Get stocks with OPPORTUNITY signal (BUY but don't own).
        
        Args:
            db: Database session
            portfolio_id: Optional portfolio ID
            
        Returns:
            List of opportunity stocks
        """
        stocks = db.query(Stock).filter(Stock.action_verdict.in_(BUY_SIGNALS)).all()
        enriched = GapAnalysisService.enrich_stocks_with_positions(db, stocks, portfolio_id)
        return [s for s in enriched if s["match_signal"] == MatchSignal.OPPORTUNITY.value]

    @staticmethod
    def get_danger_exits(
        db: Session,
        portfolio_id: int | None = None,
    ) -> list[dict]:
        """
        Get positions with DANGER_EXIT signal (SELL and own).
        
        Args:
            db: Database session
            portfolio_id: Optional portfolio ID
            
        Returns:
            List of danger exit stocks
        """
        stocks = db.query(Stock).filter(Stock.action_verdict.in_(SELL_SIGNALS)).all()
        enriched = GapAnalysisService.enrich_stocks_with_positions(db, stocks, portfolio_id)
        return [s for s in enriched if s["match_signal"] == MatchSignal.DANGER_EXIT.value]
