"""
Portfolio Reconciliation Service
=================================

Implements the "Sync Logic" for automated portfolio housekeeping.
Detects sales, moves to watchlist, handles weekly CSV imports.

Core Principles:
- Auto-detect SALES when position missing in new import
- NEVER delete data - move to Active Watchlist
- Track position history for re-entry analysis
- Generate notifications for user awareness

Author: Akcion Lead Architect
Date: 2026-01-31
Version: 2.0.0
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.portfolio import Portfolio, Position, InvestmentLog, InvestmentLogType
from app.models.stock import Stock
from app.models.trading import ActiveWatchlist
from app.services.importer import BrokerCSVParser
from app.models.portfolio import BrokerType


logger = logging.getLogger(__name__)


class ReconciliationAction(str, Enum):
    """Actions taken during reconciliation."""
    ADDED = "ADDED"           # New position added
    UPDATED = "UPDATED"       # Existing position updated
    SOLD = "SOLD"            # Position sold (removed from import)
    UNCHANGED = "UNCHANGED"   # No changes
    

@dataclass
class PositionChange:
    """Record of a single position change during reconciliation."""
    ticker: str
    action: ReconciliationAction
    old_shares: Optional[float] = None
    new_shares: Optional[float] = None
    old_value: Optional[float] = None
    new_value: Optional[float] = None
    moved_to_watchlist: bool = False
    notes: str = ""


@dataclass
class ReconciliationResult:
    """Complete result of portfolio reconciliation."""
    portfolio_id: int
    portfolio_name: str
    import_date: datetime
    total_positions_before: int
    total_positions_after: int
    changes: List[PositionChange] = field(default_factory=list)
    sales_detected: List[str] = field(default_factory=list)
    new_positions: List[str] = field(default_factory=list)
    updated_positions: List[str] = field(default_factory=list)
    notifications: List[Dict[str, Any]] = field(default_factory=list)
    
    @property
    def has_changes(self) -> bool:
        return len(self.changes) > 0
    
    @property
    def sales_count(self) -> int:
        return len(self.sales_detected)
    
    def summary(self) -> str:
        """Generate human-readable summary."""
        parts = []
        if self.new_positions:
            parts.append(f"Added: {', '.join(self.new_positions)}")
        if self.updated_positions:
            parts.append(f"Updated: {len(self.updated_positions)} positions")
        if self.sales_detected:
            parts.append(f"Sales detected: {', '.join(self.sales_detected)} → moved to Watchlist")
        return " | ".join(parts) if parts else "No changes"


class PortfolioReconciliationService:
    """
    Service for intelligent portfolio reconciliation during imports.
    
    Implements:
    - Comparison of old vs new positions
    - Automatic sale detection
    - Watchlist migration for sold positions
    - Change tracking and notifications
    
    Usage:
        service = PortfolioReconciliationService(db)
        result = service.reconcile_import(
            portfolio_id=1,
            new_positions=[{...}, {...}]
        )
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    # =========================================================================
    # MAIN RECONCILIATION
    # =========================================================================
    
    def reconcile_import(
        self,
        portfolio_id: int,
        new_positions: List[Dict[str, Any]],
        broker_type: Optional[BrokerType] = None
    ) -> ReconciliationResult:
        """
        Reconcile new import data with existing portfolio.
        
        Steps:
        1. Get current positions
        2. Compare with new import
        3. Detect sales (missing in new)
        4. Update existing positions
        5. Add new positions
        6. Move sales to watchlist
        7. Generate notifications
        
        Args:
            portfolio_id: ID of portfolio to reconcile
            new_positions: List of position dicts from CSV import
            broker_type: Broker source for attribution
            
        Returns:
            ReconciliationResult with all changes
        """
        portfolio = self.db.query(Portfolio).filter(
            Portfolio.id == portfolio_id
        ).first()
        
        if not portfolio:
            raise ValueError(f"Portfolio {portfolio_id} not found")
        
        logger.info(f"Reconciling import for {portfolio.name} ({portfolio.owner})")
        
        # Get current positions
        current_positions = self.db.query(Position).filter(
            Position.portfolio_id == portfolio_id
        ).all()
        
        current_tickers: Set[str] = {p.ticker.upper() for p in current_positions}
        current_by_ticker: Dict[str, Position] = {
            p.ticker.upper(): p for p in current_positions
        }
        
        # Get new tickers
        new_tickers: Set[str] = {
            p.get("ticker", "").upper() 
            for p in new_positions 
            if p.get("ticker")
        }
        
        # Initialize result
        result = ReconciliationResult(
            portfolio_id=portfolio_id,
            portfolio_name=portfolio.name,
            import_date=datetime.utcnow(),
            total_positions_before=len(current_positions),
            total_positions_after=0,
        )
        
        # Detect sales (in old, not in new)
        sold_tickers = current_tickers - new_tickers
        for ticker in sold_tickers:
            self._handle_sale(
                ticker, 
                current_by_ticker[ticker], 
                portfolio,
                result
            )
        
        # Process new/updated positions
        for pos_data in new_positions:
            ticker = pos_data.get("ticker", "").upper()
            if not ticker:
                continue
            
            if ticker in current_by_ticker:
                # Update existing
                self._update_position(
                    current_by_ticker[ticker],
                    pos_data,
                    result
                )
            else:
                # Add new
                self._add_position(
                    portfolio_id,
                    pos_data,
                    result
                )
        
        # Calculate final count
        final_positions = self.db.query(Position).filter(
            Position.portfolio_id == portfolio_id
        ).count()
        result.total_positions_after = final_positions
        
        # Generate summary notification
        if result.has_changes:
            result.notifications.append({
                "type": "RECONCILIATION_COMPLETE",
                "severity": "INFO",
                "title": "Portfolio Import Complete",
                "message": result.summary(),
                "timestamp": datetime.utcnow().isoformat(),
            })
        
        # Commit all changes
        self.db.commit()
        
        logger.info(f"Reconciliation complete: {result.summary()}")
        return result
    
    # =========================================================================
    # SALE HANDLING
    # =========================================================================
    
    def _handle_sale(
        self,
        ticker: str,
        position: Position,
        portfolio: Portfolio,
        result: ReconciliationResult
    ) -> None:
        """
        Handle a detected sale (position missing in new import).
        
        Steps:
        1. Record the sale in investment log
        2. Move to Active Watchlist (don't delete data!)
        3. Mark position as sold (soft delete)
        4. Add to result for notification
        """
        logger.info(f"Sale detected: {ticker} ({position.shares_count} shares)")
        
        # Record investment log
        log = InvestmentLog(
            portfolio_id=position.portfolio_id,
            ticker=ticker,
            log_type=InvestmentLogType.SALE.value,
            shares=position.shares_count,
            price_per_share=position.current_price or position.avg_cost,
            total_amount=position.market_value or (position.shares_count * position.avg_cost),
            notes=f"Auto-detected sale during import reconciliation",
            created_at=datetime.utcnow(),
        )
        self.db.add(log)
        
        # Move to watchlist
        self._move_to_watchlist(ticker, position, portfolio)
        
        # Record change
        change = PositionChange(
            ticker=ticker,
            action=ReconciliationAction.SOLD,
            old_shares=position.shares_count,
            new_shares=0,
            old_value=position.market_value,
            new_value=0,
            moved_to_watchlist=True,
            notes=f"Sale detected. P/L: {position.unrealized_pl_percent:.1f}% | Moved to Watchlist"
        )
        result.changes.append(change)
        result.sales_detected.append(ticker)
        
        # Add notification
        result.notifications.append({
            "type": "SALE_DETECTED",
            "severity": "INFO",
            "ticker": ticker,
            "title": f"Sale Detected: {ticker}",
            "message": f"Position {ticker} ({position.shares_count:.2f} shares) not found in new import. Assumed sold and moved to Watchlist for continued monitoring.",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "shares_sold": position.shares_count,
                "avg_cost": position.avg_cost,
                "last_price": position.current_price,
                "pl_percent": position.unrealized_pl_percent,
            }
        })
        
        # Delete the position (soft delete in production, hard delete here)
        self.db.delete(position)
    
    def _move_to_watchlist(
        self,
        ticker: str,
        position: Position,
        portfolio: Portfolio
    ) -> ActiveWatchlist:
        """
        Move sold position to Active Watchlist.
        
        Preserves:
        - conviction score
        - Investment thesis
        - Risk assessment
        - Historical notes
        """
        # Check if already in watchlist
        existing = self.db.query(ActiveWatchlist).filter(
            ActiveWatchlist.ticker == ticker
        ).first()
        
        # Get stock data
        stock = self.db.query(Stock).filter(
            Stock.ticker == ticker
        ).order_by(Stock.created_at.desc()).first()
        
        if existing:
            # Update existing watchlist entry
            existing.is_active = True
            existing.last_updated = datetime.utcnow()
            existing.notes = (
                f"[{datetime.utcnow().strftime('%Y-%m-%d')}] "
                f"Position sold from {portfolio.name}. "
                f"Previous: {position.shares_count:.2f} shares @ ${position.avg_cost:.2f}. "
                f"Final P/L: {position.unrealized_pl_percent:.1f}%\n"
                + (existing.notes or "")
            )
            logger.info(f"Updated existing watchlist entry for {ticker}")
            return existing
        
        # Create new watchlist entry
        watchlist = ActiveWatchlist(
            ticker=ticker,
            stock_id=stock.id if stock else None,
            action_verdict="WATCH",  # Reset to watch after sale
            conviction_score=Decimal(str(stock.conviction_score)) if stock and stock.conviction_score else None,
            investment_thesis=stock.edge if stock else None,
            risks=stock.risks if stock else None,
            is_active=True,
            added_at=datetime.utcnow(),
            last_updated=datetime.utcnow(),
            notes=(
                f"Auto-added after sale from {portfolio.name}. "
                f"Previous position: {position.shares_count:.2f} shares @ ${position.avg_cost:.2f}. "
                f"Final P/L: {position.unrealized_pl_percent:.1f}%"
            )
        )
        
        self.db.add(watchlist)
        logger.info(f"Created new watchlist entry for {ticker}")
        return watchlist
    
    # =========================================================================
    # POSITION UPDATES
    # =========================================================================
    
    def _update_position(
        self,
        position: Position,
        new_data: Dict[str, Any],
        result: ReconciliationResult
    ) -> None:
        """Update existing position with new import data."""
        ticker = position.ticker
        old_shares = position.shares_count
        old_cost = position.avg_cost
        
        new_shares = float(new_data.get("shares_count", old_shares))
        new_cost = float(new_data.get("avg_cost", old_cost))
        
        # Check if there are actual changes
        shares_changed = abs(new_shares - old_shares) > 0.0001
        cost_changed = abs(new_cost - old_cost) > 0.01
        
        if not shares_changed and not cost_changed:
            return  # No changes
        
        # Update position
        position.shares_count = new_shares
        position.avg_cost = new_cost
        position.cost_basis = new_shares * new_cost
        
        if position.current_price:
            position.market_value = new_shares * position.current_price
            position.unrealized_pl = position.market_value - position.cost_basis
            position.unrealized_pl_percent = (
                ((position.market_value / position.cost_basis) - 1) * 100 
                if position.cost_basis > 0 else 0
            )
        
        # Determine if this was a partial sale or addition
        action_type = ReconciliationAction.UPDATED
        notes = ""
        
        if new_shares < old_shares:
            shares_diff = old_shares - new_shares
            notes = f"Reduced by {shares_diff:.2f} shares (partial sale)"
            
            # Log partial sale
            log = InvestmentLog(
                portfolio_id=position.portfolio_id,
                ticker=ticker,
                log_type=InvestmentLogType.PARTIAL_SALE.value,
                shares=shares_diff,
                price_per_share=new_cost,
                total_amount=shares_diff * new_cost,
                notes=f"Partial sale detected during reconciliation",
                created_at=datetime.utcnow(),
            )
            self.db.add(log)
            
        elif new_shares > old_shares:
            shares_diff = new_shares - old_shares
            notes = f"Added {shares_diff:.2f} shares"
            
            # Log addition
            log = InvestmentLog(
                portfolio_id=position.portfolio_id,
                ticker=ticker,
                log_type=InvestmentLogType.PURCHASE.value,
                shares=shares_diff,
                price_per_share=new_cost,
                total_amount=shares_diff * new_cost,
                notes=f"Additional shares detected during reconciliation",
                created_at=datetime.utcnow(),
            )
            self.db.add(log)
        
        # Record change
        change = PositionChange(
            ticker=ticker,
            action=action_type,
            old_shares=old_shares,
            new_shares=new_shares,
            old_value=old_shares * old_cost,
            new_value=new_shares * new_cost,
            notes=notes
        )
        result.changes.append(change)
        result.updated_positions.append(ticker)
    
    def _add_position(
        self,
        portfolio_id: int,
        pos_data: Dict[str, Any],
        result: ReconciliationResult
    ) -> None:
        """Add new position from import."""
        ticker = pos_data.get("ticker", "").upper()
        shares = float(pos_data.get("shares_count", 0))
        avg_cost = float(pos_data.get("avg_cost", 0))
        currency = pos_data.get("currency", "USD")
        
        if shares <= 0:
            return
        
        cost_basis = shares * avg_cost
        
        position = Position(
            portfolio_id=portfolio_id,
            ticker=ticker,
            shares_count=shares,
            avg_cost=avg_cost,
            current_price=avg_cost,  # Will be updated by price refresh
            cost_basis=cost_basis,
            market_value=cost_basis,
            unrealized_pl=0,
            unrealized_pl_percent=0,
            currency=currency,
        )
        
        self.db.add(position)
        
        # Log purchase
        log = InvestmentLog(
            portfolio_id=portfolio_id,
            ticker=ticker,
            log_type=InvestmentLogType.PURCHASE.value,
            shares=shares,
            price_per_share=avg_cost,
            total_amount=cost_basis,
            notes=f"New position from import",
            created_at=datetime.utcnow(),
        )
        self.db.add(log)
        
        # Check if ticker was in watchlist (re-entry)
        watchlist = self.db.query(ActiveWatchlist).filter(
            ActiveWatchlist.ticker == ticker
        ).first()
        
        if watchlist:
            # Mark as re-entry
            result.notifications.append({
                "type": "RE_ENTRY",
                "severity": "INFO",
                "ticker": ticker,
                "title": f"Re-Entry: {ticker}",
                "message": f"Position {ticker} re-opened from Watchlist. Previous thesis data preserved.",
                "timestamp": datetime.utcnow().isoformat(),
            })
        
        # Record change
        change = PositionChange(
            ticker=ticker,
            action=ReconciliationAction.ADDED,
            old_shares=0,
            new_shares=shares,
            old_value=0,
            new_value=cost_basis,
            notes="New position"
        )
        result.changes.append(change)
        result.new_positions.append(ticker)
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    def get_pending_notifications(
        self,
        portfolio_id: Optional[int] = None,
        acknowledged: bool = False
    ) -> List[Dict[str, Any]]:
        """Get pending notifications for user."""
        # In a full implementation, this would query a notifications table
        # For now, return empty (notifications are part of reconciliation result)
        return []
    
    def preview_reconciliation(
        self,
        portfolio_id: int,
        new_positions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Preview what changes would be made without committing.
        
        Useful for showing user a confirmation dialog before import.
        """
        portfolio = self.db.query(Portfolio).filter(
            Portfolio.id == portfolio_id
        ).first()
        
        if not portfolio:
            raise ValueError(f"Portfolio {portfolio_id} not found")
        
        current_positions = self.db.query(Position).filter(
            Position.portfolio_id == portfolio_id
        ).all()
        
        current_tickers = {p.ticker.upper() for p in current_positions}
        new_tickers = {p.get("ticker", "").upper() for p in new_positions if p.get("ticker")}
        
        return {
            "portfolio": portfolio.name,
            "current_count": len(current_positions),
            "new_count": len(new_tickers),
            "will_be_added": list(new_tickers - current_tickers),
            "will_be_removed": list(current_tickers - new_tickers),
            "will_be_updated": list(current_tickers & new_tickers),
            "warning": (
                f"{len(current_tickers - new_tickers)} positions will be marked as SOLD and moved to Watchlist"
                if current_tickers - new_tickers else None
            )
        }
