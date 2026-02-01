"""
Gomes Intelligence Service
============================

Business logic layer for Gomes Investment Gatekeeper.
Combines database operations, ML predictions, and Gomes rules.

Author: GitHub Copilot with Claude Opus 4.5
Date: 2026-01-17
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.gomes import (
    GomesRulesLogModel,
    ImageAnalysisLogModel,
    InvestmentVerdictModel,
    MarketAlertModel,
    PriceLinesModel,
    PositionTierModel,
    StockLifecycleModel,
)
from app.models.stock import Stock
from app.models.trading import ActiveWatchlist, MLPrediction
from app.trading.gomes_logic import (
    GomesGatekeeper,
    GomesVerdict,
    LifecyclePhase,
    MarketAlert,
    MarketAlertSystem,
    MarketAllocation,
    PositionSizingEngine,
    PositionTier,
    PriceLines,
    RiskRewardCalculator,
    StockLifecycleClassifier,
)


logger = logging.getLogger(__name__)


# ============================================================================
# IMAGE PRICE LINE DATA (Hardcoded from screenshots)
# ============================================================================

# Import from dedicated data file
from app.trading.price_lines_data import get_price_lines_dict, EXTRACTED_LINES

# Get lines from data file
IMAGE_PRICE_LINES: dict[str, dict[str, Any]] = get_price_lines_dict()


class GomesIntelligenceService:
    """
    Main service for Gomes Intelligence Module.
    
    Provides:
    - Market alert management
    - Lifecycle phase tracking
    - Price line management
    - Verdict generation
    - ML integration
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.logger = logging.getLogger(__name__)
    
    # ========================================================================
    # MARKET ALERT METHODS
    # ========================================================================
    
    def get_current_market_alert(self) -> MarketAlert:
        """Get current market alert level"""
        alert = (
            self.db.query(MarketAlertModel)
            .filter(MarketAlertModel.effective_until.is_(None))
            .order_by(desc(MarketAlertModel.effective_from))
            .first()
        )
        
        if alert:
            return MarketAlert(alert.alert_level)
        
        # Default to GREEN if no alert set
        return MarketAlert.GREEN
    
    def get_market_allocation(self) -> MarketAllocation:
        """Get current portfolio allocation based on market alert"""
        alert_level = self.get_current_market_alert()
        return MarketAlertSystem.get_allocation(alert_level)
    
    def set_market_alert(
        self,
        alert_level: str,
        reason: str,
        source: str = "manual",
        created_by: str = "user"
    ) -> MarketAlertModel:
        """
        Set new market alert level.
        
        Deactivates previous alert and creates new one.
        """
        # Deactivate current alert
        current = (
            self.db.query(MarketAlertModel)
            .filter(MarketAlertModel.effective_until.is_(None))
            .first()
        )
        
        if current:
            current.effective_until = datetime.utcnow()
        
        # Get allocation for new level
        allocation = MarketAlertSystem.get_allocation(alert_level)
        
        # Create new alert
        new_alert = MarketAlertModel(
            alert_level=alert_level.upper(),
            stocks_pct=Decimal(str(allocation.stocks_pct)),
            cash_pct=Decimal(str(allocation.cash_pct)),
            hedge_pct=Decimal(str(allocation.hedge_pct)),
            reason=reason,
            source=source,
            created_by=created_by
        )
        
        self.db.add(new_alert)
        self.db.commit()
        self.db.refresh(new_alert)
        
        self.logger.info(f"Market alert changed to {alert_level}: {reason}")
        
        return new_alert
    
    # ========================================================================
    # LIFECYCLE METHODS
    # ========================================================================
    
    def get_stock_lifecycle(self, ticker: str) -> StockLifecycleModel | None:
        """Get current lifecycle phase for ticker"""
        return (
            self.db.query(StockLifecycleModel)
            .filter(StockLifecycleModel.ticker == ticker.upper())
            .filter(StockLifecycleModel.valid_until.is_(None))
            .first()
        )
    
    def classify_stock_lifecycle(
        self,
        ticker: str,
        transcript_text: str | None = None,
        source: str = "auto"
    ) -> StockLifecycleModel:
        """
        Classify stock lifecycle and save to DB.
        
        Args:
            ticker: Stock ticker
            transcript_text: Optional transcript for classification
            source: Data source
            
        Returns:
            StockLifecycleModel with phase
        """
        ticker = ticker.upper()
        
        # Get classification
        assessment = StockLifecycleClassifier.classify(ticker, transcript_text)
        
        # Deactivate previous lifecycle
        current = self.get_stock_lifecycle(ticker)
        if current:
            current.valid_until = datetime.utcnow()
        
        # Get stock_id if exists
        stock = (
            self.db.query(Stock)
            .filter(Stock.ticker == ticker)
            .filter(Stock.is_latest == True)
            .first()
        )
        
        # Create new lifecycle record
        lifecycle = StockLifecycleModel(
            ticker=ticker,
            stock_id=stock.id if stock else None,
            phase=assessment.phase.value,
            is_investable=assessment.is_investable,
            firing_on_all_cylinders=assessment.firing_on_all_cylinders,
            cylinders_count=assessment.cylinders_count,
            phase_signals=assessment.signals,
            phase_reasoning=assessment.reasoning,
            confidence=assessment.confidence,
            source=source
        )
        
        self.db.add(lifecycle)
        self.db.commit()
        self.db.refresh(lifecycle)
        
        self.logger.info(f"{ticker} classified as {assessment.phase.value}")
        
        return lifecycle
    
    def is_investable(self, ticker: str) -> tuple[bool, str]:
        """
        Quick check if ticker is investable based on lifecycle.
        
        Returns:
            (is_investable, reason)
        """
        lifecycle = self.get_stock_lifecycle(ticker)
        
        if not lifecycle:
            return True, "No lifecycle data - assuming investable"
        
        if not lifecycle.is_investable:
            return False, f"BLOCKED: {lifecycle.phase} phase - {lifecycle.phase_reasoning}"
        
        return True, f"Investable: {lifecycle.phase} phase"
    
    # ========================================================================
    # PRICE LINES METHODS
    # ========================================================================
    
    def get_price_lines(self, ticker: str) -> PriceLinesModel | None:
        """Get current price lines for ticker"""
        return (
            self.db.query(PriceLinesModel)
            .filter(PriceLinesModel.ticker == ticker.upper())
            .filter(PriceLinesModel.valid_until.is_(None))
            .first()
        )
    
    def set_price_lines(
        self,
        ticker: str,
        green_line: float | None = None,
        red_line: float | None = None,
        grey_line: float | None = None,
        current_price: float | None = None,
        source: str = "manual",
        source_reference: str | None = None,
        image_path: str | None = None
    ) -> PriceLinesModel:
        """
        Set price lines for ticker.
        
        Args:
            ticker: Stock ticker
            green_line: Buy zone price
            red_line: Sell zone price
            grey_line: Neutral zone (optional)
            current_price: Current market price
            source: Data source
            source_reference: Reference (quote, etc.)
            image_path: Path to screenshot
            
        Returns:
            PriceLinesModel
        """
        ticker = ticker.upper()
        
        # Deactivate previous
        current = self.get_price_lines(ticker)
        if current:
            current.valid_until = datetime.utcnow()
        
        # Get stock_id
        stock = (
            self.db.query(Stock)
            .filter(Stock.ticker == ticker)
            .filter(Stock.is_latest == True)
            .first()
        )
        
        # Calculate valuation
        is_undervalued = None
        is_overvalued = None
        if current_price and green_line:
            is_undervalued = current_price < green_line
        if current_price and red_line:
            is_overvalued = current_price > red_line
        
        # Create new record
        lines = PriceLinesModel(
            ticker=ticker,
            stock_id=stock.id if stock else None,
            green_line=Decimal(str(green_line)) if green_line else None,
            red_line=Decimal(str(red_line)) if red_line else None,
            grey_line=Decimal(str(grey_line)) if grey_line else None,
            current_price=Decimal(str(current_price)) if current_price else None,
            is_undervalued=is_undervalued,
            is_overvalued=is_overvalued,
            source=source,
            source_reference=source_reference,
            image_path=image_path
        )
        
        self.db.add(lines)
        self.db.commit()
        self.db.refresh(lines)
        
        self.logger.info(f"{ticker} price lines set: G=${green_line} R=${red_line}")
        
        return lines
    
    def load_price_lines_from_images(self) -> list[PriceLinesModel]:
        """
        Load price lines from IMAGE_PRICE_LINES dictionary.
        
        This populates the database with lines extracted from screenshots.
        """
        results = []
        
        for ticker, data in IMAGE_PRICE_LINES.items():
            lines = self.set_price_lines(
                ticker=ticker,
                green_line=data.get("green_line"),
                red_line=data.get("red_line"),
                grey_line=data.get("grey_line"),
                source="image",
                image_path=data.get("source")
            )
            results.append(lines)
            
            # Also log to image_analysis_log
            log = ImageAnalysisLogModel(
                ticker=ticker,
                image_path=data.get("source", ""),
                extracted_green_line=Decimal(str(data.get("green_line"))) if data.get("green_line") else None,
                extracted_red_line=Decimal(str(data.get("red_line"))) if data.get("red_line") else None,
                extracted_grey_line=Decimal(str(data.get("grey_line"))) if data.get("grey_line") else None,
                analysis_method="manual",
                status="verified"
            )
            self.db.add(log)
        
        self.db.commit()
        self.logger.info(f"Loaded {len(results)} price lines from images")
        
        return results
    
    # ========================================================================
    # VERDICT GENERATION
    # ========================================================================
    
    def generate_verdict(
        self,
        ticker: str,
        conviction_score: int | None = None,
        current_price: float | None = None,
        earnings_date: datetime | None = None,
        transcript_text: str | None = None,
        force_ml_refresh: bool = False
    ) -> GomesVerdict:
        """
        Generate complete investment verdict for ticker.
        
        This is THE MAIN FUNCTION - synthesizes all Gomes rules.
        
        Args:
            ticker: Stock ticker
            conviction_score: Base Conviction Score (or fetch from DB)
            current_price: Current price (or fetch from market data)
            earnings_date: Next earnings date
            transcript_text: Optional transcript for lifecycle detection
            force_ml_refresh: Force new ML prediction
            
        Returns:
            GomesVerdict with complete analysis
        """
        ticker = ticker.upper()
        
        # =====================================================================
        # 1. GET MARKET ALERT
        # =====================================================================
        market_alert = self.get_current_market_alert()
        
        # =====================================================================
        # 2. GET/CLASSIFY LIFECYCLE
        # =====================================================================
        lifecycle = self.get_stock_lifecycle(ticker)
        lifecycle_phase = None
        
        if lifecycle:
            lifecycle_phase = LifecyclePhase(lifecycle.phase)
        elif transcript_text:
            lifecycle_model = self.classify_stock_lifecycle(ticker, transcript_text)
            lifecycle_phase = LifecyclePhase(lifecycle_model.phase)
        
        # =====================================================================
        # 3. GET PRICE LINES
        # =====================================================================
        price_lines = self.get_price_lines(ticker)
        green_line = float(price_lines.green_line) if price_lines and price_lines.green_line else None
        red_line = float(price_lines.red_line) if price_lines and price_lines.red_line else None
        
        # =====================================================================
        # 4. GET Conviction Score FROM DB IF NOT PROVIDED
        # =====================================================================
        if conviction_score is None:
            stock = (
                self.db.query(Stock)
                .filter(Stock.ticker == ticker)
                .filter(Stock.is_latest == True)
                .first()
            )
            conviction_score = stock.conviction_score if stock else 5
        
        # =====================================================================
        # 5. GET ML PREDICTION
        # =====================================================================
        ml_prediction = None
        ml_record = (
            self.db.query(MLPrediction)
            .filter(MLPrediction.ticker == ticker)
            .order_by(desc(MLPrediction.created_at))
            .first()
        )
        
        if ml_record:
            ml_prediction = {
                "direction": ml_record.prediction_type,
                "confidence": float(ml_record.confidence) if ml_record.confidence else None,
                "predicted_price": float(ml_record.predicted_price) if ml_record.predicted_price else None
            }
        
        # =====================================================================
        # 6. GET CATALYST INFO FROM STOCK
        # =====================================================================
        catalyst_info = None
        stock = (
            self.db.query(Stock)
            .filter(Stock.ticker == ticker)
            .filter(Stock.is_latest == True)
            .first()
        )
        
        if stock and stock.catalysts:
            catalyst_info = {
                "has_catalyst": True,
                "type": "from_transcript",
                "description": stock.catalysts[:200] if stock.catalysts else None
            }
        
        # =====================================================================
        # 7. RUN GATEKEEPER
        # =====================================================================
        gatekeeper = GomesGatekeeper(market_alert=market_alert)
        
        verdict = gatekeeper.evaluate(
            ticker=ticker,
            conviction_score=conviction_score,
            lifecycle_phase=lifecycle_phase,
            current_price=current_price,
            green_line=green_line,
            red_line=red_line,
            earnings_date=earnings_date,
            ml_prediction=ml_prediction,
            transcript_text=transcript_text,
            catalyst_info=catalyst_info
        )
        
        # =====================================================================
        # 8. SAVE VERDICT TO DB
        # =====================================================================
        self._save_verdict(verdict, stock)
        
        return verdict
    
    def _save_verdict(self, verdict: GomesVerdict, stock: Stock | None) -> InvestmentVerdictModel:
        """Save verdict to database"""
        # Deactivate previous verdict
        current = (
            self.db.query(InvestmentVerdictModel)
            .filter(InvestmentVerdictModel.ticker == verdict.ticker)
            .filter(InvestmentVerdictModel.valid_until.is_(None))
            .first()
        )
        
        if current:
            current.valid_until = datetime.utcnow()
        
        # Create new verdict
        model = InvestmentVerdictModel(
            ticker=verdict.ticker,
            stock_id=stock.id if stock else None,
            verdict=verdict.verdict.value,
            passed_gomes_filter=verdict.passed_gomes_filter,
            blocked_reason=verdict.blocked_reason,
            conviction_score=verdict.conviction_score,
            ml_prediction_score=Decimal(str(verdict.ml_prediction_score)) if verdict.ml_prediction_score else None,
            ml_prediction_direction=verdict.ml_direction,
            lifecycle_phase=verdict.lifecycle_phase.value if verdict.lifecycle_phase else None,
            lifecycle_investable=verdict.passed_gomes_filter,
            market_alert_level=verdict.market_alert.value if verdict.market_alert else None,
            position_tier=verdict.position_tier.value if verdict.position_tier else None,
            max_position_size=Decimal(str(verdict.max_position_pct)) if verdict.max_position_pct else None,
            current_price=Decimal(str(verdict.current_price)) if verdict.current_price else None,
            green_line=Decimal(str(verdict.green_line)) if verdict.green_line else None,
            red_line=Decimal(str(verdict.red_line)) if verdict.red_line else None,
            risk_factors=verdict.risk_factors,
            has_catalyst=verdict.has_catalyst,
            catalyst_type=verdict.catalyst_type,
            catalyst_description=verdict.catalyst_description,
            days_to_earnings=verdict.days_to_earnings,
            bull_case=verdict.bull_case,
            bear_case=verdict.bear_case,
            confidence=verdict.confidence
        )
        
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        
        return model
    
    # ========================================================================
    # BULK OPERATIONS
    # ========================================================================
    
    def scan_watchlist(
        self,
        min_score: int = 5,
        limit: int = 20
    ) -> list[GomesVerdict]:
        """
        Scan entire watchlist and generate verdicts.
        
        Returns:
            List of GomesVerdict sorted by score (highest first)
        """
        # Get active watchlist
        watchlist = (
            self.db.query(ActiveWatchlist)
            .filter(ActiveWatchlist.is_active == True)
            .all()
        )
        
        verdicts = []
        
        for item in watchlist:
            try:
                verdict = self.generate_verdict(
                    ticker=item.ticker,
                    conviction_score=int(item.conviction_score) if item.conviction_score else 5
                )
                
                if verdict.conviction_score >= min_score:
                    verdicts.append(verdict)
                    
            except Exception as e:
                self.logger.error(f"Error analyzing {item.ticker}: {e}")
        
        # Sort by score (highest first)
        verdicts.sort(key=lambda v: v.conviction_score, reverse=True)
        
        return verdicts[:limit]
    
    def get_blocked_stocks(self) -> list[dict[str, Any]]:
        """Get list of stocks blocked by Gomes filter"""
        blocked = (
            self.db.query(InvestmentVerdictModel)
            .filter(InvestmentVerdictModel.passed_gomes_filter == False)
            .filter(InvestmentVerdictModel.valid_until.is_(None))
            .all()
        )
        
        return [
            {
                "ticker": v.ticker,
                "verdict": v.verdict,
                "blocked_reason": v.blocked_reason,
                "lifecycle_phase": v.lifecycle_phase,
                "conviction_score": v.conviction_score
            }
            for v in blocked
        ]
    
    def get_top_opportunities(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get top investment opportunities (passed filter, highest score)"""
        opportunities = (
            self.db.query(InvestmentVerdictModel)
            .filter(InvestmentVerdictModel.passed_gomes_filter == True)
            .filter(InvestmentVerdictModel.valid_until.is_(None))
            .filter(InvestmentVerdictModel.verdict.in_(["STRONG_BUY", "BUY", "ACCUMULATE"]))
            .order_by(desc(InvestmentVerdictModel.conviction_score))
            .limit(limit)
            .all()
        )
        
        return [
            {
                "ticker": v.ticker,
                "verdict": v.verdict,
                "conviction_score": v.conviction_score,
                "lifecycle_phase": v.lifecycle_phase,
                "position_tier": v.position_tier,
                "max_position_size": float(v.max_position_size) if v.max_position_size else None,
                "green_line": float(v.green_line) if v.green_line else None,
                "red_line": float(v.red_line) if v.red_line else None,
                "has_catalyst": v.has_catalyst,
                "confidence": v.confidence
            }
            for v in opportunities
        ]

    def get_gomes_stocks_with_lines(self) -> list[dict[str, Any]]:
        """
        Get all stocks from Gomes videos with price lines.
        
        Returns stocks from ActiveWatchlist joined with PriceLines for ML page.
        """
        from app.models.trading import MLPrediction
        from sqlalchemy import func
        
        # Get all active watchlist items
        watchlist = (
            self.db.query(ActiveWatchlist)
            .filter(ActiveWatchlist.is_active == True)
            .all()
        )
        
        result = []
        
        for item in watchlist:
            ticker = item.ticker
            
            # Get price lines
            lines = self.get_price_lines(ticker)
            
            # Get lifecycle
            lifecycle = self.get_stock_lifecycle(ticker)
            
            # Get stock info
            stock = item.stock
            
            # Get latest ML prediction
            ml_pred = (
                self.db.query(MLPrediction)
                .filter(MLPrediction.ticker == ticker)
                .order_by(desc(MLPrediction.created_at))
                .first()
            )
            
            # Calculate price zone
            current_price = float(lines.current_price) if lines and lines.current_price else None
            green_line = float(lines.green_line) if lines and lines.green_line else None
            red_line = float(lines.red_line) if lines and lines.red_line else None
            
            price_zone = None
            price_position_pct = None
            
            if current_price and (green_line or red_line):
                price_zone, price_position_pct = RiskRewardCalculator.get_action_zone(
                    current_price, green_line, red_line
                )
            
            result.append({
                "ticker": ticker,
                "company_name": stock.company_name if stock else None,
                "conviction_score": int(item.conviction_score) if item.conviction_score else None,
                "sentiment": stock.sentiment if stock else None,
                "action_verdict": item.action_verdict,
                "lifecycle_phase": lifecycle.phase if lifecycle else None,
                "green_line": green_line,
                "red_line": red_line,
                "current_price": current_price,
                "price_zone": price_zone,
                "price_position_pct": price_position_pct,
                "has_ml_prediction": ml_pred is not None,
                "ml_direction": ml_pred.prediction_type if ml_pred else None,
                "ml_confidence": float(ml_pred.confidence) if ml_pred and ml_pred.confidence else None,
                "video_date": stock.created_at.isoformat() if stock and stock.created_at else None,
                "notes": item.notes,
            })
        
        # Sort by conviction_score descending
        result.sort(key=lambda x: (x.get("conviction_score") or 0), reverse=True)
        
        return result
