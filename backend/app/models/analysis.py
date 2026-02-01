"""
Analysis Intelligence Models

SQLAlchemy models for storing analyst transcripts and SWOT analysis data.

Clean Code Principles Applied:
- Explicit column documentation
- Type hints for properties
- Proper relationship definitions
- Constants for magic strings
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TIMESTAMP
from sqlalchemy.orm import relationship, Mapped

from .base import Base


class AnalystTranscript(Base):
    """Raw and processed analyst video transcripts (e.g., Mark Gomes, Breakout Investors)"""
    __tablename__ = "analyst_transcripts"
    
    id = Column(Integer, primary_key=True)
    source_name = Column(String(100), nullable=False)  # e.g., 'Breakout Investors', 'Mark Gomes'
    raw_text = Column(Text, nullable=False)
    processed_summary = Column(Text)
    detected_tickers = Column(ARRAY(String(10)), nullable=False, default=[])  # PostgreSQL array
    date = Column(Date, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    
    # Additional metadata
    video_url = Column(String(500))
    transcript_quality = Column(String(20))  # high, medium, low
    is_processed = Column(Boolean, nullable=False, default=False)
    processing_notes = Column(Text)
    
    # Relationships
    swot_analyses = relationship("SWOTAnalysis", back_populates="transcript", cascade="all, delete-orphan")
    
    __table_args__ = (
        CheckConstraint("transcript_quality IN ('high', 'medium', 'low')", name='check_transcript_quality'),
        CheckConstraint('date <= CURRENT_DATE', name='check_date_not_future'),
        Index('idx_transcripts_source', 'source_name', 'date'),
        Index('idx_transcripts_date', 'date'),
        Index('idx_transcripts_processed', 'is_processed', 'created_at'),
        Index('idx_transcripts_tickers', 'detected_tickers', postgresql_using='gin'),
        # Full-text search index requires special SQL, applied in migration
    )
    
    @property
    def ticker_count(self):
        """Count of detected tickers"""
        return len(self.detected_tickers) if self.detected_tickers else 0
    
    @property
    def summary_preview(self):
        """First 200 characters of summary"""
        if not self.processed_summary:
            return None
        return self.processed_summary[:200] + ('...' if len(self.processed_summary) > 200 else '')
    
    def __repr__(self):
        return f"<AnalystTranscript {self.source_name} @ {self.date}: {self.ticker_count} tickers>"
    
    # Relationship to ticker mentions
    ticker_mentions = relationship("TickerMention", back_populates="transcript", cascade="all, delete-orphan")


class TickerMention(Base):
    """
    Jednotlivá zmínka tickeru v transcriptu.
    
    Umožňuje trackovat historii toho, co Mark Gomes říkal o každé akcii
    v průběhu času. Novější zmínky mají vyšší váhu v analýze.
    """
    __tablename__ = "ticker_mentions"
    
    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), nullable=False, index=True)
    transcript_id = Column(Integer, ForeignKey('analyst_transcripts.id', ondelete='CASCADE'), nullable=False)
    stock_id = Column(Integer, ForeignKey('stocks.id', ondelete='SET NULL'))
    
    # Datum zmínky (z transcriptu)
    mention_date = Column(Date, nullable=False, index=True)
    
    # Kontext zmínky
    sentiment = Column(String(20), nullable=False, default='NEUTRAL')  # BULLISH, BEARISH, NEUTRAL
    action_mentioned = Column(String(30))  # BUY, SELL, HOLD, ACCUMULATE, TRIM, WATCH
    
    # Extrahovaný kontext ze zmínky
    context_snippet = Column(Text)  # Relevantní část transcriptu pro tento ticker
    key_points = Column(JSONB)  # Seznam klíčových bodů: ["catalyst", "risk", "price_target", ...]
    
    # Číselné hodnoty (pokud zmíněny)
    price_target = Column(Numeric(12, 2))  # Zmíněný cenový cíl
    conviction_level = Column(String(20))  # HIGH, MEDIUM, LOW
    
    # Metadata
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    ai_extracted = Column(Boolean, default=True)  # Extrahováno AI vs manuálně
    is_current = Column(Boolean, default=True, index=True)  # Nejaktuálnější zmínka pro ticker
    
    # Relationships
    transcript = relationship("AnalystTranscript", back_populates="ticker_mentions")
    stock = relationship("Stock")
    
    __table_args__ = (
        CheckConstraint(
            "sentiment IN ('BULLISH', 'BEARISH', 'NEUTRAL', 'VERY_BULLISH', 'VERY_BEARISH')",
            name='check_mention_sentiment'
        ),
        CheckConstraint(
            "action_mentioned IS NULL OR action_mentioned IN ('BUY', 'SELL', 'HOLD', 'ACCUMULATE', 'TRIM', 'WATCH', 'AVOID', 'BUY_NOW')",
            name='check_mention_action'
        ),
        CheckConstraint(
            "conviction_level IS NULL OR conviction_level IN ('HIGH', 'MEDIUM', 'LOW')",
            name='check_mention_conviction'
        ),
        Index('idx_mentions_ticker_date', 'ticker', 'mention_date'),
        Index('idx_mentions_current', 'ticker', 'is_current', postgresql_where="is_current = TRUE"),
        Index('idx_mentions_sentiment', 'ticker', 'sentiment', 'mention_date'),
    )
    
    @property
    def age_days(self):
        """Počet dní od zmínky"""
        from datetime import date
        return (date.today() - self.mention_date).days if self.mention_date else None
    
    @property
    def weight(self):
        """
        Váha zmínky pro analýzu.
        Novější zmínky mají vyšší váhu (exponenciální decay).
        """
        age = self.age_days
        if age is None:
            return 0.5
        # Decay: 100% pro dnes, ~50% po 30 dnech, ~25% po 60 dnech
        import math
        return math.exp(-0.023 * age)  # ~30 day half-life
    
    def __repr__(self):
        return f"<TickerMention {self.ticker} @ {self.mention_date}: {self.sentiment} - {self.action_mentioned}>"


class SWOTAnalysis(Base):
    """AI-generated SWOT analysis per ticker"""
    __tablename__ = "swot_analysis"
    
    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), nullable=False, index=True)
    stock_id = Column(Integer, ForeignKey('stocks.id', ondelete='CASCADE'))
    watchlist_id = Column(Integer, ForeignKey('active_watchlist.id', ondelete='CASCADE'))
    transcript_id = Column(Integer, ForeignKey('analyst_transcripts.id', ondelete='SET NULL'))
    
    # SWOT data stored as JSONB for flexibility and fast querying
    # Structure: {"strengths": [...], "weaknesses": [...], "opportunities": [...], "threats": [...]}
    swot_data = Column(JSONB, nullable=False)
    
    # Metadata
    ai_model_version = Column(String(50), nullable=False)  # e.g., 'gemini-1.5-pro', 'gpt-4'
    confidence_score = Column(Numeric(5, 4))
    generated_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow, index=True)
    expires_at = Column(TIMESTAMP(timezone=True))  # Optional expiry for outdated analysis
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    notes = Column(Text)
    
    # Relationships
    stock = relationship("Stock")
    watchlist = relationship("ActiveWatchlist", back_populates="swot_analyses")
    transcript = relationship("AnalystTranscript", back_populates="swot_analyses")
    
    __table_args__ = (
        CheckConstraint('confidence_score >= 0 AND confidence_score <= 1', name='check_swot_confidence'),
        CheckConstraint(
            "swot_data ? 'strengths' AND swot_data ? 'weaknesses' AND swot_data ? 'opportunities' AND swot_data ? 'threats'",
            name='check_swot_structure'
        ),
        Index('idx_swot_ticker', 'ticker', 'generated_at'),
        Index('idx_swot_active', 'ticker', 'is_active', postgresql_where="is_active = TRUE"),
        Index('idx_swot_watchlist', 'watchlist_id', 'generated_at'),
        Index('idx_swot_data_gin', 'swot_data', postgresql_using='gin'),
        # Unique constraint: one active SWOT per ticker at a time
        Index('idx_swot_ticker_active_unique', 'ticker', unique=True, postgresql_where="is_active = TRUE"),
    )
    
    @property
    def strengths(self):
        """Extract strengths from JSONB"""
        return self.swot_data.get('strengths', []) if self.swot_data else []
    
    @property
    def weaknesses(self):
        """Extract weaknesses from JSONB"""
        return self.swot_data.get('weaknesses', []) if self.swot_data else []
    
    @property
    def opportunities(self):
        """Extract opportunities from JSONB"""
        return self.swot_data.get('opportunities', []) if self.swot_data else []
    
    @property
    def threats(self):
        """Extract threats from JSONB"""
        return self.swot_data.get('threats', []) if self.swot_data else []
    
    @property
    def total_points(self):
        """Count total SWOT points"""
        return sum([
            len(self.strengths),
            len(self.weaknesses),
            len(self.opportunities),
            len(self.threats)
        ])
    
    def is_expired(self):
        """Check if SWOT analysis has expired"""
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at
    
    def __repr__(self):
        return f"<SWOT {self.ticker}: {self.total_points} points @ {self.confidence_score:.2f}>"


# NOTE: Active Watchlist enhancements are added via ALTER TABLE in migration
# The following attributes are added to the existing ActiveWatchlist model:
# - conviction_score: Numeric(4, 2) - Conviction score (0-10)
# - investment_thesis: Text - Detailed investment thesis
# - risks: Text - Identified risks and concerns

# Add this to backend/app/models/trading.py in the ActiveWatchlist class:
"""
# Enhanced analysis fields (added via migration)
conviction_score = Column(Numeric(4, 2))
investment_thesis = Column(Text)
risks = Column(Text)

# Relationship to SWOT analyses
swot_analyses = relationship("SWOTAnalysis", back_populates="watchlist", cascade="all, delete-orphan")
"""
