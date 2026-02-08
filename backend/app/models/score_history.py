"""
Conviction Score History Model

Tracks historical evolution of Conviction Scores for thesis drift detection.
Enables visualization of score trends over time.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Index,
    func,
)
from sqlalchemy.orm import relationship

from .base import Base


class ConvictionScoreHistory(Base):
    """
    Historical record of Conviction Score for a ticker.
    
    Used for:
    - Thesis Drift visualization (score trend vs price trend)
    - Alert generation when fundamentals diverge from price
    - Long-term performance analysis
    """
    __tablename__ = "conviction_score_history"
    
    id = Column(Integer, primary_key=True)
    ticker = Column(String(20), nullable=False, index=True)
    stock_id = Column(Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=True)
    
    # Score data
    conviction_score = Column(Integer, nullable=False)
    thesis_status = Column(String(20), nullable=True)  # IMPROVED, STABLE, DETERIORATED, BROKEN
    action_signal = Column(String(20), nullable=True)  # BUY, ACCUMULATE, HOLD, TRIM, SELL
    
    # Context
    price_at_analysis = Column(Numeric(12, 4), nullable=True)
    analysis_source = Column(String(100), nullable=True)  # deep_dd, transcript, manual
    
    # Timestamps
    recorded_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        index=True
    )
    
    # Relationships
    stock = relationship("Stock", foreign_keys=[stock_id])
    
    __table_args__ = (
        Index("idx_score_history_ticker_time", "ticker", "recorded_at"),
    )
    
    def __repr__(self) -> str:
        return f"<ScoreHistory {self.ticker}: {self.conviction_score}/10 @ {self.recorded_at}>"


class ThesisDriftAlert(Base):
    """
    Alert generated when thesis drift is detected.
    
    Triggers:
    - Price rising but score falling (HYPE_AHEAD_OF_FUNDAMENTALS)
    - Score dropping 3+ points (THESIS_BREAKING)
    - Score rising with accumulation signal (ACCUMULATE_SIGNAL)
    """
    __tablename__ = "thesis_drift_alerts"
    
    id = Column(Integer, primary_key=True)
    ticker = Column(String(20), nullable=False, index=True)
    
    # Alert data
    alert_type = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False)  # INFO, WARNING, CRITICAL
    
    # Context
    old_score = Column(Integer, nullable=True)
    new_score = Column(Integer, nullable=True)
    price_change_pct = Column(Numeric(8, 2), nullable=True)
    message = Column(Text, nullable=False)
    
    # Status
    is_acknowledged = Column(Boolean, default=False)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now()
    )
    
    def __repr__(self) -> str:
        return f"<ThesisDriftAlert {self.ticker}: {self.alert_type} ({self.severity})>"


# Alert type constants
class AlertType:
    HYPE_AHEAD_OF_FUNDAMENTALS = "HYPE_AHEAD_OF_FUNDAMENTALS"
    THESIS_BREAKING = "THESIS_BREAKING"
    THESIS_DETERIORATING = "THESIS_DETERIORATING"
    ACCUMULATE_SIGNAL = "ACCUMULATE_SIGNAL"
    THESIS_IMPROVING = "THESIS_IMPROVING"
