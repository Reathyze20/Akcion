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

    Two layers, and the difference matters
    --------------------------------------
    `conviction_score` is what a MODEL said about a company. The block below it
    is what the ENGINE decided: the logarithmic R/R score, the level the company
    deserved for its operational health, the band the price sat in, and the
    market alert that gated it.

    The second layer exists because the first cannot answer the question the
    app is for. Calibration (`app/services/score_outcomes.py`) measures each
    journaled row against what the price actually did; without the decision
    fields it can only ever report whether the nines beat the fives, never
    whether the band engine was right. And none of it can be added later —
    history here starts on 2026-08-23 because nothing before that was recorded,
    and re-deriving a past decision from today's lines would invent it.
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

    # ------------------------------------------------------------------
    # The decision, not just the score.
    # Every one of these is nullable, and NULL means "the app did not know",
    # which is itself the measurement: a row with cylinders NULL is a row where
    # no buy could have been authorised.
    # ------------------------------------------------------------------
    rr_score = Column(
        Numeric(6, 3),
        nullable=True,
        doc="Logarithmic R/R score 0-10 (canon §4a). NULL = lines missing, never 0.",
    )
    deserved_score = Column(
        Numeric(6, 3),
        nullable=True,
        doc="10 − cylinders (canon §4b): what the company deserved for its quality.",
    )
    cylinders = Column(
        Integer,
        nullable=True,
        doc="Operational health 0-10 behind deserved_score. NULL = unknown.",
    )
    green_line = Column(Numeric(12, 4), nullable=True, doc="Buy-zone line used for rr_score")
    red_line = Column(Numeric(12, 4), nullable=True, doc="Sell-zone line used for rr_score")
    line_currency = Column(
        String(3),
        nullable=True,
        doc=(
            "Currency the lines are quoted in — the tracker quotes the US OTC "
            "listing, so a CAD-priced position is converted before scoring."
        ),
    )
    band = Column(
        String(20),
        nullable=True,
        doc="POD_ZELENOU / NAKUP / DRZET / PREPLACENO / NAD_CERVENOU / MIMO_METODIKU / NEZNAME",
    )
    market_alert = Column(
        String(10),
        nullable=True,
        doc="Market alert in force. It gates every buy, so an outcome without it is unreadable.",
    )
    source_key = Column(
        String(30),
        nullable=True,
        doc="GOMES / BREAKOUT_INVESTORS / OTHER — which source this decision came from.",
    )

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
        Index("idx_score_history_band", "band", "recorded_at"),
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
