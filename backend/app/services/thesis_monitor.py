"""
Thesis Monitor Service
======================

Monitors thesis drift by comparing score changes and generating alerts.

Event Logic:
- delta < -3 → THESIS_BROKEN → CRITICAL_ALERT → Recommend SELL
- delta -1 to -2 → THESIS_DRIFT → WARNING_ALERT → Create review task
- delta > +2 → IMPROVEMENT → OPPORTUNITY_ALERT → If undervalued, suggest ADD

Author: GitHub Copilot with Claude Opus 4.5
Date: 2026-02-01
"""

from typing import Optional, List
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
from sqlalchemy.orm import Session
from loguru import logger

from app.models.stock import Stock
from app.models.gomes import GomesAlert, GomesScoreHistory


class ThesisDriftLevel(str, Enum):
    """Classification of thesis drift severity"""
    THESIS_BROKEN = "THESIS_BROKEN"      # delta <= -3
    THESIS_DRIFT = "THESIS_DRIFT"        # delta -1 to -2
    STABLE = "STABLE"                    # delta 0
    IMPROVEMENT = "IMPROVEMENT"          # delta +1 to +2
    MAJOR_IMPROVEMENT = "MAJOR_IMPROVEMENT"  # delta >= +3


class AlertSeverity(str, Enum):
    """Alert severity levels"""
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"
    OPPORTUNITY = "OPPORTUNITY"


@dataclass
class ThesisDriftResult:
    """Result of thesis drift analysis"""
    ticker: str
    previous_score: Optional[int]
    current_score: int
    delta: int
    drift_level: ThesisDriftLevel
    alert_severity: AlertSeverity
    recommendation: str
    message: str
    created_alert: bool


class ThesisMonitor:
    """
    Monitors thesis drift and generates alerts.
    
    Usage:
        monitor = ThesisMonitor(db)
        result = monitor.analyze_drift("GKPRF", previous_score=8, new_score=4)
        # result.drift_level == ThesisDriftLevel.THESIS_BROKEN
        # result.recommendation == "SELL IMMEDIATELY"
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    def analyze_drift(
        self,
        ticker: str,
        previous_score: Optional[int],
        new_score: int,
        source: str = "analysis_update",
    ) -> ThesisDriftResult:
        """
        Analyze thesis drift and create appropriate alerts.
        
        Args:
            ticker: Stock ticker
            previous_score: Previous conviction score (None if first analysis)
            new_score: New conviction score
            source: Source of the update (e.g., "earnings", "news", "transcript")
        
        Returns:
            ThesisDriftResult with drift classification and alert info
        """
        # Calculate delta
        if previous_score is None:
            delta = 0  # First analysis, no drift
        else:
            delta = new_score - previous_score
        
        # Classify drift level
        drift_level = self._classify_drift(delta)
        
        # Determine alert severity and recommendation
        alert_severity, recommendation = self._get_alert_config(drift_level, new_score, ticker)
        
        # Generate message
        message = self._generate_message(ticker, previous_score, new_score, delta, drift_level)
        
        # Create alert in database
        created_alert = self._create_alert(
            ticker=ticker,
            drift_level=drift_level,
            alert_severity=alert_severity,
            message=message,
            recommendation=recommendation,
            previous_score=previous_score,
            new_score=new_score,
            source=source,
        )
        
        # Update stock status if thesis is broken
        if drift_level == ThesisDriftLevel.THESIS_BROKEN:
            self._mark_stock_for_review(ticker)
        
        return ThesisDriftResult(
            ticker=ticker,
            previous_score=previous_score,
            current_score=new_score,
            delta=delta,
            drift_level=drift_level,
            alert_severity=alert_severity,
            recommendation=recommendation,
            message=message,
            created_alert=created_alert,
        )
    
    def _classify_drift(self, delta: int) -> ThesisDriftLevel:
        """Classify drift level based on delta"""
        if delta <= -3:
            return ThesisDriftLevel.THESIS_BROKEN
        elif delta < 0:
            return ThesisDriftLevel.THESIS_DRIFT
        elif delta == 0:
            return ThesisDriftLevel.STABLE
        elif delta <= 2:
            return ThesisDriftLevel.IMPROVEMENT
        else:
            return ThesisDriftLevel.MAJOR_IMPROVEMENT
    
    def _get_alert_config(
        self,
        drift_level: ThesisDriftLevel,
        new_score: int,
        ticker: str,
    ) -> tuple[AlertSeverity, str]:
        """Get alert severity and recommendation based on drift level"""
        
        if drift_level == ThesisDriftLevel.THESIS_BROKEN:
            return (
                AlertSeverity.CRITICAL,
                "SELL IMMEDIATELY. Thesis fundamentally broken."
            )
        
        elif drift_level == ThesisDriftLevel.THESIS_DRIFT:
            if new_score < 5:
                return (
                    AlertSeverity.WARNING,
                    "REVIEW POSITION. Score dropped below threshold. Consider selling."
                )
            else:
                return (
                    AlertSeverity.WARNING,
                    "RE-VALIDATE THESIS. Monitor closely for further deterioration."
                )
        
        elif drift_level == ThesisDriftLevel.IMPROVEMENT:
            # Check if stock is in buy zone
            stock = self.db.query(Stock).filter(Stock.ticker.ilike(ticker)).first()
            if stock and stock.current_price and stock.green_line:
                if stock.current_price <= stock.green_line:
                    return (
                        AlertSeverity.OPPORTUNITY,
                        f"CONSIDER ADDING. Score improved to {new_score}/10 and price in buy zone."
                    )
            return (
                AlertSeverity.INFO,
                f"THESIS STRENGTHENING. Score improved to {new_score}/10. Hold or monitor for entry."
            )
        
        elif drift_level == ThesisDriftLevel.MAJOR_IMPROVEMENT:
            return (
                AlertSeverity.OPPORTUNITY,
                f"MAJOR UPGRADE! Score jumped to {new_score}/10. Strong buy candidate."
            )
        
        else:  # STABLE
            return (
                AlertSeverity.INFO,
                f"THESIS STABLE. Score unchanged at {new_score}/10."
            )
    
    def _generate_message(
        self,
        ticker: str,
        previous_score: Optional[int],
        new_score: int,
        delta: int,
        drift_level: ThesisDriftLevel,
    ) -> str:
        """Generate human-readable message"""
        if previous_score is None:
            return f"{ticker}: Initial analysis complete. Score: {new_score}/10."
        
        direction = "↓" if delta < 0 else "↑" if delta > 0 else "→"
        
        if drift_level == ThesisDriftLevel.THESIS_BROKEN:
            return (
                f"🚨 {ticker}: THESIS BROKEN! "
                f"Score crashed {previous_score} → {new_score} ({delta} points). "
                f"IMMEDIATE ACTION REQUIRED."
            )
        
        elif drift_level == ThesisDriftLevel.THESIS_DRIFT:
            return (
                f"⚠️ {ticker}: Thesis drift detected. "
                f"Score: {previous_score} → {new_score} ({direction}{abs(delta)}). "
                f"Review position."
            )
        
        elif drift_level in (ThesisDriftLevel.IMPROVEMENT, ThesisDriftLevel.MAJOR_IMPROVEMENT):
            return (
                f"✅ {ticker}: Thesis improving! "
                f"Score: {previous_score} → {new_score} ({direction}{abs(delta)}). "
            )
        
        else:
            return f"{ticker}: Score stable at {new_score}/10."
    
    def _create_alert(
        self,
        ticker: str,
        drift_level: ThesisDriftLevel,
        alert_severity: AlertSeverity,
        message: str,
        recommendation: str,
        previous_score: Optional[int],
        new_score: int,
        source: str,
    ) -> bool:
        """Create alert in database"""
        try:
            # Only create alerts for non-stable situations
            if drift_level == ThesisDriftLevel.STABLE:
                return False
            
            alert = GomesAlert(
                ticker=ticker,
                alert_type=drift_level.value,
                severity=alert_severity.value,
                title=f"{ticker}: {drift_level.value.replace('_', ' ')}",
                message=message,
                recommendation=recommendation,
                previous_score=previous_score,
                current_score=new_score,
                score_delta=new_score - (previous_score or new_score),
                source=source,
                is_read=False,
                created_at=datetime.utcnow(),
            )
            
            self.db.add(alert)
            self.db.commit()
            
            logger.info(f"Created {alert_severity.value} alert for {ticker}: {drift_level.value}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create alert for {ticker}: {e}")
            self.db.rollback()
            return False
    
    def _mark_stock_for_review(self, ticker: str) -> None:
        """Mark stock as needing review in database"""
        try:
            stock = self.db.query(Stock).filter(Stock.ticker.ilike(ticker)).first()
            if stock:
                stock.needs_review = True
                stock.review_reason = "THESIS_BROKEN"
                stock.last_review_requested = datetime.utcnow()
                self.db.commit()
                logger.warning(f"Marked {ticker} for URGENT REVIEW: THESIS_BROKEN")
        except Exception as e:
            logger.error(f"Failed to mark {ticker} for review: {e}")
            self.db.rollback()
    
    def get_pending_alerts(
        self,
        unread_only: bool = True,
        severity: Optional[AlertSeverity] = None,
        limit: int = 50,
    ) -> List[GomesAlert]:
        """Get pending alerts from database"""
        query = self.db.query(GomesAlert)
        
        if unread_only:
            query = query.filter(GomesAlert.is_read == False)
        
        if severity:
            query = query.filter(GomesAlert.severity == severity.value)
        
        # Order by severity (CRITICAL first) and then by date
        query = query.order_by(
            GomesAlert.severity.desc(),
            GomesAlert.created_at.desc()
        )
        
        return query.limit(limit).all()
    
    def get_stocks_needing_review(self) -> List[Stock]:
        """Get all stocks marked for review"""
        return self.db.query(Stock).filter(
            Stock.needs_review == True
        ).order_by(Stock.last_review_requested.desc()).all()


# ============================================================================
# INTEGRATION FUNCTION - Call after every analysis update
# ============================================================================

def check_thesis_drift(
    db: Session,
    ticker: str,
    previous_score: Optional[int],
    new_score: int,
    source: str = "analysis_update",
) -> ThesisDriftResult:
    """
    Convenience function to check thesis drift after an analysis update.
    
    This should be called after every score change in the system.
    
    Example usage in gomes_deep_dd.py:
        # After updating stock
        from app.services.thesis_monitor import check_thesis_drift
        
        result = check_thesis_drift(
            db=db,
            ticker=ticker,
            previous_score=old_score,
            new_score=new_score,
            source="deep_dd"
        )
        
        if result.drift_level == ThesisDriftLevel.THESIS_BROKEN:
            logger.critical(f"🚨 {ticker}: THESIS BROKEN!")
    """
    monitor = ThesisMonitor(db)
    return monitor.analyze_drift(
        ticker=ticker,
        previous_score=previous_score,
        new_score=new_score,
        source=source,
    )
