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

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, func, Float, Date

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
    - Conviction Score: 1-10 conviction rating
    
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
    conviction_score = Column(
        Integer,
        nullable=True,
        doc="Investment conviction score 1-10 (10 = highest)"
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
        String(100),
        nullable=True,
        doc="Trading signal: BUY_NOW, ACCUMULATE, WATCH_LIST, TRIM, SELL, AVOID"
    )
    entry_zone = Column(
        String(200),
        nullable=True,
        doc="Entry point: 'Under $15' or 'Pullback to EMA20'"
    )
    price_target_short = Column(
        String(200),
        nullable=True,
        doc="3-6 month price target"
    )
    price_target_long = Column(
        String(200),
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
    
    # =========================================================================
    # GOMES GUARDIAN MASTER TABLE (2026-01-25)
    # =========================================================================
    
    # Identity & Classification
    asset_class = Column(
        String(100),
        nullable=True,
        doc="Gomes Asset Class: ANCHOR, HIGH_BETA_ROCKET, BIOTECH_BINARY, TURNAROUND, VALUE_TRAP"
    )
    
    # Finance (Hard Data) - Survival Metrics
    cash_runway_months = Column(
        Integer,
        nullable=True,
        doc="Months of cash at current burn rate (Cash / Monthly Burn)"
    )
    insider_ownership_pct = Column(
        Float,
        nullable=True,
        doc="Percentage of shares held by insiders (skin in the game)"
    )
    fully_diluted_market_cap = Column(
        Float,
        nullable=True,
        doc="True market cap including warrants and options"
    )
    enterprise_value = Column(
        Float,
        nullable=True,
        doc="Market Cap + Debt - Cash (real valuation)"
    )
    quarterly_burn_rate = Column(
        Float,
        nullable=True,
        doc="Average quarterly cash burn (for runway calculation)"
    )
    total_cash = Column(
        Float,
        nullable=True,
        doc="Cash & equivalents on balance sheet"
    )
    
    # Thesis (Soft Data) - The Narrative
    inflection_status = Column(
        String(50),
        nullable=True,
        doc="Business stage: WAIT_TIME (red), UPCOMING (yellow), ACTIVE_GOLD_MINE (green)"
    )
    primary_catalyst = Column(
        Text,
        nullable=True,
        doc="Next major event (e.g., Amtrak Contract Decision)"
    )
    catalyst_date = Column(
        Date,
        nullable=True,
        doc="Estimated date of catalyst event"
    )
    thesis_narrative = Column(
        Text,
        nullable=True,
        doc="One-sentence investment thesis (The Setup)"
    )
    
    # Valuation - Price Targets
    price_floor = Column(
        Float,
        nullable=True,
        doc="Liquidation value (Cash/Share) - absolute downside"
    )
    price_target_24m = Column(
        Float,
        nullable=True,
        doc="Target price in 24 months based on operational model"
    )
    current_valuation_stage = Column(
        String(50),
        nullable=True,
        doc="Valuation assessment: UNDERVALUED, FAIR, OVERVALUED, BUBBLE"
    )
    price_base = Column(
        Float,
        nullable=True,
        doc="Base case realistic target"
    )
    price_moon = Column(
        Float,
        nullable=True,
        doc="Bull case moon shot target"
    )
    forward_pe_2027 = Column(
        Float,
        nullable=True,
        doc="Forward P/E ratio (2027 earnings estimate)"
    )
    
    # Risk Control - Position Discipline
    max_allocation_cap = Column(
        Float,
        nullable=True,
        doc="Maximum portfolio allocation % (dynamically calculated by Gomes Logic)"
    )
    stop_loss_price = Column(
        Float,
        nullable=True,
        doc="Hard exit price (technical support or -20% from entry)"
    )
    insider_activity = Column(
        String(50),
        nullable=True,
        doc="Recent insider trading: BUYING, HOLDING, SELLING"
    )
    
    # Price Lines & Trend Analysis (Gomes Intelligence)
    current_price = Column(
        Float,
        nullable=True,
        doc="Current market price (live or last close)"
    )
    green_line = Column(
        Float,
        nullable=True,
        doc="Buy zone / Support level (Gomes undervalued price)"
    )
    red_line = Column(
        Float,
        nullable=True,
        doc="Sell zone / Resistance level (Gomes fair/overvalued price)"
    )
    grey_line = Column(
        Float,
        nullable=True,
        doc="Neutral zone price level (if mentioned)"
    )
    price_position_pct = Column(
        Float,
        nullable=True,
        doc="Where price sits between green/red lines (0-100%)"
    )
    price_zone = Column(
        String(50),
        nullable=True,
        doc="Price classification: DEEP_VALUE, BUY_ZONE, ACCUMULATE, FAIR_VALUE, SELL_ZONE, OVERVALUED"
    )
    market_cap = Column(
        Float,
        nullable=True,
        doc="Total market capitalization"
    )
    
    # Trading Zones (Calculated from Price Lines)
    max_buy_price = Column(
        Float,
        nullable=True,
        doc="Maximum buy price = green_line + 5% (Above this: HOLD only)"
    )
    start_sell_price = Column(
        Float,
        nullable=True,
        doc="Start selling price = red_line - 5% (Sell into strength)"
    )
    risk_to_floor_pct = Column(
        Float,
        nullable=True,
        doc="Risk percentage to green line: (current - green) / current * 100"
    )
    upside_to_ceiling_pct = Column(
        Float,
        nullable=True,
        doc="Upside percentage to red line: (red - current) / current * 100"
    )
    trading_zone_signal = Column(
        String(50),
        nullable=True,
        doc="Trading recommendation: AGGRESSIVE_BUY, BUY, HOLD, SELL, STRONG_SELL"
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
            "conviction_score": self.conviction_score,
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
            # Gomes Guardian fields
            "asset_class": self.asset_class,
            "cash_runway_months": self.cash_runway_months,
            "insider_ownership_pct": self.insider_ownership_pct,
            "fully_diluted_market_cap": self.fully_diluted_market_cap,
            "enterprise_value": self.enterprise_value,
            "quarterly_burn_rate": self.quarterly_burn_rate,
            "total_cash": self.total_cash,
            "inflection_status": self.inflection_status,
            "primary_catalyst": self.primary_catalyst,
            "catalyst_date": self._serialize_date(self.catalyst_date),
            "thesis_narrative": self.thesis_narrative,
            "price_floor": self.price_floor,
            "price_target_24m": self.price_target_24m,
            "current_valuation_stage": self.current_valuation_stage,
            "price_base": self.price_base,
            "price_moon": self.price_moon,
            "forward_pe_2027": self.forward_pe_2027,
            "max_allocation_cap": self.max_allocation_cap,
            "stop_loss_price": self.stop_loss_price,
            "insider_activity": self.insider_activity,
            # Price Lines & Trend Analysis
            "current_price": self.current_price,
            "green_line": self.green_line,
            "red_line": self.red_line,
            "grey_line": self.grey_line,
            "price_position_pct": self.price_position_pct,
            "price_zone": self.price_zone,
            "market_cap": self.market_cap,
            # Trading Zones
            "max_buy_price": self.max_buy_price,
            "start_sell_price": self.start_sell_price,
            "risk_to_floor_pct": self.risk_to_floor_pct,
            "upside_to_ceiling_pct": self.upside_to_ceiling_pct,
            "trading_zone_signal": self.trading_zone_signal,
        }
    
    @staticmethod
    def _serialize_datetime(dt: datetime | None) -> str | None:
        """Serialize datetime to ISO format string."""
        return dt.isoformat() if dt else None
    
    @staticmethod
    def _serialize_date(d) -> str | None:
        """Serialize date to ISO format string."""
        return d.isoformat() if d else None
    
    def __repr__(self) -> str:
        """Generate readable string representation."""
        return f"<Stock(id={self.id}, ticker={self.ticker}, score={self.conviction_score})>"
