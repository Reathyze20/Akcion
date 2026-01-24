"""
Stock Analysis Model

Core domain model for stock analysis following Mark Gomes methodology.
This schema is critical for data integrity - changes require migration.

Clean Code Principles Applied:
- Explicit column documentation
- Type hints for all methods
- Grouped related fields
- Constants for magic strings
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, func

from .base import Base


# ==============================================================================
# Constants for Magic Strings
# ==============================================================================

class SourceType:
    """Valid source types for stock analysis."""
    YOUTUBE: str = "YouTube"
    GOOGLE_DOCS: str = "Google Docs"
    WHATSAPP: str = "WhatsApp"
    MANUAL: str = "Manual"


class SentimentType:
    """Valid sentiment classifications."""
    BULLISH: str = "Bullish"
    BEARISH: str = "Bearish"
    NEUTRAL: str = "Neutral"


# ==============================================================================
# Stock Model
# ==============================================================================

class Stock(Base):
    """
    Stock analysis record following the Gomes Investment Methodology.
    
    This model captures:
    - Information Arbitrage (edge): What the market doesn't know
    - Catalysts: Upcoming events that will move the price
    - Risk Assessment: Honest evaluation of risks
    - Gomes Score: 1-10 conviction rating
    
    Versioning:
    - Each analysis creates a new version
    - is_latest=True marks the current version
    - Historical versions are preserved for audit
    """
    
    __tablename__ = "stocks"
    
    # Primary Key & Timestamps
    id = Column(Integer, primary_key=True, doc="Unique identifier")
    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        doc="Record creation timestamp"
    )
    updated_at = Column(
        DateTime,
        onupdate=func.now(),
        nullable=True,
        doc="Last update timestamp"
    )
    
    # Stock Identification
    ticker = Column(
        String(20),
        nullable=False,
        index=True,
        doc="Stock ticker symbol (e.g., AAPL)"
    )
    company_name = Column(
        String(200),
        nullable=True,
        doc="Full company name"
    )
    
    # Source Attribution
    source_type = Column(
        String(50),
        nullable=True,
        doc="Origin of analysis (YouTube, Google Docs, etc.)"
    )
    speaker = Column(
        String(100),
        nullable=True,
        doc="Analyst name (e.g., Mark Gomes)"
    )
    
    # Analysis Metadata
    sentiment = Column(
        String(50),
        nullable=True,
        doc="Market sentiment: Bullish, Bearish, Neutral"
    )
    gomes_score = Column(
        Integer,
        nullable=True,
        doc="Gomes conviction score 1-10 (10 = highest)"
    )
    conviction_score = Column(
        Integer,
        nullable=True,
        doc="Alternative conviction metric (backup)"
    )
    
    # Price & Timing
    price_target = Column(
        Text,
        nullable=True,
        doc="Price target (can be complex: 'Buy at $5, sell at $10')"
    )
    time_horizon = Column(
        String(100),
        nullable=True,
        doc="Investment timeframe: Short-term, Long-term, etc."
    )
    
    # The Gomes Rules (Core Analysis)
    edge = Column(
        Text,
        nullable=True,
        doc="Information Arbitrage - What others don't know"
    )
    catalysts = Column(
        Text,
        nullable=True,
        doc="Specific upcoming events/dates that will move price"
    )
    next_catalyst = Column(
        String(100),
        nullable=True,
        doc="Next upcoming catalyst event: 'Q1 EARNINGS / MAY 26'"
    )
    risks = Column(
        Text,
        nullable=True,
        doc="Honest risk assessment"
    )
    raw_notes = Column(
        Text,
        nullable=True,
        doc="Freeform notes, status (New Idea, Update, Sold)"
    )
    
    # Trading Action Fields
    action_verdict = Column(
        String(50),
        nullable=True,
        doc="Trading signal: BUY_NOW, ACCUMULATE, WATCH_LIST, TRIM, SELL, AVOID"
    )
    entry_zone = Column(
        String(200),
        nullable=True,
        doc="Entry point: 'Under $15' or 'Pullback to EMA20'"
    )
    price_target_short = Column(
        String(50),
        nullable=True,
        doc="3-6 month price target"
    )
    price_target_long = Column(
        String(50),
        nullable=True,
        doc="12-24 month price target"
    )
    stop_loss_risk = Column(
        Text,
        nullable=True,
        doc="Stop loss level or risk description"
    )
    moat_rating = Column(
        Integer,
        nullable=True,
        doc="Competitive advantage rating 1-5 (5 = unassailable)"
    )
    trade_rationale = Column(
        Text,
        nullable=True,
        doc="Why this stock, why now?"
    )
    chart_setup = Column(
        Text,
        nullable=True,
        doc="Technical chart setup description"
    )
    
    # Version Tracking
    is_latest = Column(
        Boolean,
        default=True,
        index=True,
        doc="True if this is the current version"
    )
    version = Column(
        Integer,
        default=1,
        doc="Version number for history tracking"
    )
    
    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary for API responses.
        
        Returns:
            Dictionary with all stock fields serialized
        """
        return {
            "id": self.id,
            "created_at": self._serialize_datetime(self.created_at),
            "updated_at": self._serialize_datetime(self.updated_at),
            "ticker": self.ticker,
            "company_name": self.company_name,
            "source_type": self.source_type,
            "speaker": self.speaker,
            "sentiment": self.sentiment,
            "gomes_score": self.gomes_score,
            "conviction_score": self.conviction_score,
            "price_target": self.price_target,
            "time_horizon": self.time_horizon,
            "edge": self.edge,
            "catalysts": self.catalysts,
            "next_catalyst": self.next_catalyst,
            "risks": self.risks,
            "raw_notes": self.raw_notes,
            "action_verdict": self.action_verdict,
            "entry_zone": self.entry_zone,
            "price_target_short": self.price_target_short,
            "price_target_long": self.price_target_long,
            "stop_loss_risk": self.stop_loss_risk,
            "moat_rating": self.moat_rating,
            "trade_rationale": self.trade_rationale,
            "chart_setup": self.chart_setup,
            "is_latest": self.is_latest,
            "version": self.version,
        }
    
    @staticmethod
    def _serialize_datetime(dt: datetime | None) -> str | None:
        """Serialize datetime to ISO format string."""
        return dt.isoformat() if dt else None
    
    def __repr__(self) -> str:
        """Generate readable string representation."""
        return f"<Stock(id={self.id}, ticker={self.ticker}, score={self.gomes_score})>"
