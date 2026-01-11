"""
SQLAlchemy Stock Model
CRITICAL: This schema must remain identical to preserve data integrity.
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Stock(Base):
    """
    Stock analysis record following the Gomes Investment Methodology.
    
    Fields aligned with Mark Gomes' investment framework:
    - Information Arbitrage (edge)
    - Catalysts (upcoming events)
    - Risk Assessment (risks)
    - Scoring System (gomes_score: 1-10)
    """
    __tablename__ = 'stocks'
    
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, server_default=func.now())
    
    # Stock Identification
    ticker = Column(String(20), nullable=False, index=True)
    company_name = Column(String(200))
    
    # Source Attribution
    source_type = Column(String(50))  # YouTube, Google Docs, WhatsApp, etc.
    speaker = Column(String(100))     # Mark Gomes, etc.
    
    # Analysis Metadata
    sentiment = Column(String(50))           # Bullish, Bearish, Neutral
    gomes_score = Column(Integer)            # 1-10 scoring (10 = highest conviction)
    conviction_score = Column(Integer)       # Alternative/backup conviction metric
    
    # Price & Timing
    price_target = Column(Text)              # Can be complex: "Buy at $5, sell at $10"
    time_horizon = Column(String(100))       # Short-term, Long-term, etc.
    
    # The Gomes Rules (Core Analysis)
    edge = Column(Text)                      # Information Arbitrage - What others don't know
    catalysts = Column(Text)                 # Specific upcoming events/dates
    risks = Column(Text)                     # Honest risk assessment
    
    # Additional Notes
    raw_notes = Column(Text)                 # Freeform notes, status (New Idea, Update, Sold)
    
    # ========== NEW: TRADING ACTION FIELDS ==========
    action_verdict = Column(String(50))      # BUY_NOW, ACCUMULATE, WATCH_LIST, TRIM, SELL, AVOID
    entry_zone = Column(String(200))         # "Under $15" or "Pullback to EMA20"
    price_target_short = Column(String(50))  # Short-term target
    price_target_long = Column(String(50))   # Long-term target  
    stop_loss_risk = Column(Text)            # "Close below $10" or "High Volatility"
    moat_rating = Column(Integer)            # 1-5, competitive advantage strength
    trade_rationale = Column(Text)           # Why NOW vs later
    chart_setup = Column(Text)               # Technical setup description
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
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
            "risks": self.risks,
            "raw_notes": self.raw_notes,
            "action_verdict": self.action_verdict,
            "entry_zone": self.entry_zone,
            "price_target_short": self.price_target_short,
            "price_target_long": self.price_target_long,
            "stop_loss_risk": self.stop_loss_risk,
            "moat_rating": self.moat_rating,
            "trade_rationale": self.trade_rationale,
            "chart_setup": self.chart_setup
        }
