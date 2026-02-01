"""
Gomes Intelligence Database Models
====================================

SQLAlchemy models for Gomes Investment Gatekeeper system.
These models store lifecycle phases, price lines, market alerts, and verdicts.

Author: GitHub Copilot with Claude Opus 4.5
Date: 2026-01-17
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import relationship

from .base import Base

if TYPE_CHECKING:
    from .stock import Stock
    from .analysis import AnalystTranscript


# ============================================================================
# 1. MARKET ALERT (Traffic Light System)
# ============================================================================

class MarketAlertModel(Base):
    """
    Market Alert Level (Semafor)
    
    Tracks overall market state: GREEN/YELLOW/ORANGE/RED
    Affects portfolio allocation and position sizing.
    """
    __tablename__ = "market_alerts"
    
    id = Column(Integer, primary_key=True)
    alert_level = Column(
        String(10),
        nullable=False,
        doc="Alert level: GREEN, YELLOW, ORANGE, RED"
    )
    
    # Allocation percentages
    stocks_pct = Column(Numeric(5, 2), nullable=False, default=100.00)
    cash_pct = Column(Numeric(5, 2), nullable=False, default=0.00)
    hedge_pct = Column(Numeric(5, 2), nullable=False, default=0.00)
    
    # Metadata
    reason = Column(Text, doc="Reason for alert level change")
    source = Column(String(100), doc="transcript, manual, system")
    transcript_id = Column(Integer, ForeignKey('analyst_transcripts.id', ondelete='SET NULL'))
    
    # Timestamps
    effective_from = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    effective_until = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    created_by = Column(String(100), default='system')
    
    # Relationships
    transcript = relationship("AnalystTranscript", foreign_keys=[transcript_id])
    
    __table_args__ = (
        CheckConstraint("alert_level IN ('GREEN', 'YELLOW', 'ORANGE', 'RED')", name='check_alert_level'),
        CheckConstraint('stocks_pct >= 0 AND stocks_pct <= 100', name='check_stocks_pct'),
        CheckConstraint('cash_pct >= 0 AND cash_pct <= 100', name='check_cash_pct'),
        CheckConstraint('hedge_pct >= 0 AND hedge_pct <= 100', name='check_hedge_pct'),
        CheckConstraint('stocks_pct + cash_pct + hedge_pct = 100.00', name='check_allocation_sum'),
        Index('idx_market_alerts_active', 'effective_from', postgresql_where="effective_until IS NULL"),
        Index('idx_market_alerts_level', 'alert_level', 'effective_from'),
    )
    
    def __repr__(self):
        return f"<MarketAlert {self.alert_level} @ {self.effective_from}>"


# ============================================================================
# 2. STOCK LIFECYCLE (Great Find / Wait Time / Gold Mine)
# ============================================================================

class StockLifecycleModel(Base):
    """
    Stock Lifecycle Phase
    
    GREAT_FIND: Dream phase - early opportunity
    WAIT_TIME: Dead money - DO NOT INVEST
    GOLD_MINE: Proven execution - safe buy
    """
    __tablename__ = "stock_lifecycle"
    
    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), nullable=False, index=True)
    stock_id = Column(Integer, ForeignKey('stocks.id', ondelete='CASCADE'))
    
    # Phase
    phase = Column(
        String(20),
        nullable=False,
        doc="GREAT_FIND, WAIT_TIME, GOLD_MINE, UNKNOWN"
    )
    
    # Investability
    is_investable = Column(Boolean, nullable=False, default=True)
    firing_on_all_cylinders = Column(Boolean, nullable=True)
    cylinders_count = Column(Integer, nullable=True)
    
    # Detection
    phase_signals = Column(JSONB, default={})
    phase_reasoning = Column(Text)
    confidence = Column(String(10))
    
    # Source
    source = Column(String(100))
    transcript_id = Column(Integer, ForeignKey('analyst_transcripts.id', ondelete='SET NULL'))
    
    # Timestamps
    detected_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    valid_until = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    
    # Relationships
    stock = relationship("Stock", foreign_keys=[stock_id])
    transcript = relationship("AnalystTranscript", foreign_keys=[transcript_id])
    
    __table_args__ = (
        CheckConstraint("phase IN ('GREAT_FIND', 'WAIT_TIME', 'GOLD_MINE', 'UNKNOWN')", name='check_lifecycle_phase'),
        CheckConstraint('cylinders_count >= 0 AND cylinders_count <= 10', name='check_cylinders'),
        CheckConstraint("confidence IN ('HIGH', 'MEDIUM', 'LOW')", name='check_lifecycle_confidence'),
        Index('idx_lifecycle_ticker', 'ticker', 'detected_at'),
        Index('idx_lifecycle_phase', 'phase', 'is_investable'),
        Index('idx_lifecycle_active', 'ticker', postgresql_where="valid_until IS NULL"),
    )
    
    def __repr__(self):
        return f"<Lifecycle {self.ticker}: {self.phase} (investable={self.is_investable})>"


# ============================================================================
# 3. PRICE LINES (Green / Red / Grey)
# ============================================================================

class PriceLinesModel(Base):
    """
    Price Target Lines
    
    Green Line: Buy zone (undervalued)
    Red Line: Sell zone (overvalued)
    Grey Line: Neutral zone
    """
    __tablename__ = "price_lines"
    
    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), nullable=False, index=True)
    stock_id = Column(Integer, ForeignKey('stocks.id', ondelete='CASCADE'))
    
    # Price targets
    green_line = Column(Numeric(12, 4), nullable=True)
    red_line = Column(Numeric(12, 4), nullable=True)
    grey_line = Column(Numeric(12, 4), nullable=True)
    
    # Current context
    current_price = Column(Numeric(12, 4), nullable=True)
    is_undervalued = Column(Boolean, nullable=True)
    is_overvalued = Column(Boolean, nullable=True)
    
    # Score at lines
    conviction_score_at_green = Column(Integer, nullable=True)
    conviction_score_at_red = Column(Integer, nullable=True)
    
    # Source
    source = Column(String(100))
    source_reference = Column(Text)
    transcript_id = Column(Integer, ForeignKey('analyst_transcripts.id', ondelete='SET NULL'))
    image_path = Column(Text)
    
    # Timestamps
    effective_from = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    valid_until = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=True)
    
    # Relationships
    stock = relationship("Stock", foreign_keys=[stock_id])
    transcript = relationship("AnalystTranscript", foreign_keys=[transcript_id])
    
    __table_args__ = (
        CheckConstraint('conviction_score_at_green >= 0 AND conviction_score_at_green <= 10', name='check_score_green'),
        CheckConstraint('conviction_score_at_red >= 0 AND conviction_score_at_red <= 10', name='check_score_red'),
        Index('idx_price_lines_ticker', 'ticker', 'effective_from'),
        Index('idx_price_lines_active', 'ticker', postgresql_where="valid_until IS NULL"),
        Index('idx_price_lines_undervalued', 'is_undervalued', 'ticker', postgresql_where="valid_until IS NULL"),
    )
    
    def __repr__(self):
        return f"<PriceLines {self.ticker}: G=${self.green_line} R=${self.red_line}>"


# ============================================================================
# 4. POSITION TIERS
# ============================================================================

class PositionTierModel(Base):
    """
    Position Sizing Tier
    
    PRIMARY: 10% max - Core positions
    SECONDARY: 5% max - Great Find, dating
    TERTIARY: 2% max - Speculative
    """
    __tablename__ = "position_tiers"
    
    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), nullable=False, index=True)
    stock_id = Column(Integer, ForeignKey('stocks.id', ondelete='CASCADE'))
    
    # Tier
    tier = Column(String(20), nullable=False)
    
    # Size limits
    max_portfolio_pct = Column(Numeric(5, 2), nullable=False)
    recommended_pct = Column(Numeric(5, 2), nullable=True)
    
    # Constraints
    allowed_in_yellow_alert = Column(Boolean, nullable=False, default=True)
    allowed_in_orange_alert = Column(Boolean, nullable=False, default=False)
    allowed_in_red_alert = Column(Boolean, nullable=False, default=False)
    
    # Metadata
    tier_reasoning = Column(Text)
    source = Column(String(100))
    transcript_id = Column(Integer, ForeignKey('analyst_transcripts.id', ondelete='SET NULL'))
    
    # Timestamps
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=True)
    
    # Relationships
    stock = relationship("Stock", foreign_keys=[stock_id])
    transcript = relationship("AnalystTranscript", foreign_keys=[transcript_id])
    
    __table_args__ = (
        CheckConstraint("tier IN ('PRIMARY', 'SECONDARY', 'TERTIARY')", name='check_tier'),
        CheckConstraint('max_portfolio_pct > 0 AND max_portfolio_pct <= 20', name='check_max_pct'),
        Index('idx_position_tiers_ticker', 'ticker'),
        Index('idx_position_tiers_tier', 'tier', 'max_portfolio_pct'),
    )
    
    def __repr__(self):
        return f"<PositionTier {self.ticker}: {self.tier} (max {self.max_portfolio_pct}%)>"


# ============================================================================
# 5. INVESTMENT VERDICTS
# ============================================================================

class InvestmentVerdictModel(Base):
    """
    Final Investment Verdict
    
    The Gatekeeper's final decision combining all Gomes rules.
    """
    __tablename__ = "investment_verdicts"
    
    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), nullable=False, index=True)
    stock_id = Column(Integer, ForeignKey('stocks.id', ondelete='CASCADE'))
    
    # Verdict
    verdict = Column(String(20), nullable=False)
    passed_gomes_filter = Column(Boolean, nullable=False)
    blocked_reason = Column(Text, nullable=True)
    
    # Scores
    conviction_score = Column(Integer, nullable=True)
    ml_prediction_score = Column(Numeric(5, 2), nullable=True)
    ml_prediction_direction = Column(String(10), nullable=True)
    
    # Context
    lifecycle_phase = Column(String(20), nullable=True)
    lifecycle_investable = Column(Boolean, nullable=True)
    market_alert_level = Column(String(10), nullable=True)
    position_tier = Column(String(20), nullable=True)
    max_position_size = Column(Numeric(5, 2), nullable=True)
    
    # Price context
    current_price = Column(Numeric(12, 4), nullable=True)
    green_line = Column(Numeric(12, 4), nullable=True)
    red_line = Column(Numeric(12, 4), nullable=True)
    price_vs_green_pct = Column(Numeric(8, 2), nullable=True)
    
    # Risk
    risk_factors = Column(JSONB, default=[])
    
    # Cases
    bull_case = Column(Text, nullable=True)
    bear_case = Column(Text, nullable=True)
    
    # Catalyst
    has_catalyst = Column(Boolean, nullable=True)
    catalyst_type = Column(String(50), nullable=True)
    catalyst_description = Column(Text, nullable=True)
    
    # Earnings
    days_to_earnings = Column(Integer, nullable=True)
    earnings_blocked = Column(Boolean, default=False)
    
    # Sources
    data_sources = Column(JSONB, default={})
    
    # Confidence
    confidence = Column(String(10), nullable=True)
    
    # Timestamps
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    valid_until = Column(TIMESTAMP(timezone=True), nullable=True)
    
    # Relationships
    stock = relationship("Stock", foreign_keys=[stock_id])
    rules_log = relationship("GomesRulesLogModel", back_populates="verdict", cascade="all, delete-orphan")
    
    __table_args__ = (
        CheckConstraint(
            "verdict IN ('STRONG_BUY', 'BUY', 'ACCUMULATE', 'HOLD', 'TRIM', 'SELL', 'AVOID', 'BLOCKED')",
            name='check_verdict'
        ),
        CheckConstraint('conviction_score >= 0 AND conviction_score <= 10', name='check_conviction_score'),
        CheckConstraint("confidence IN ('HIGH', 'MEDIUM', 'LOW')", name='check_verdict_confidence'),
        Index('idx_verdicts_ticker', 'ticker', 'created_at'),
        Index('idx_verdicts_active', 'ticker', postgresql_where="valid_until IS NULL"),
        Index('idx_verdicts_verdict', 'verdict', 'created_at'),
        Index('idx_verdicts_blocked', 'passed_gomes_filter', 'verdict', postgresql_where="valid_until IS NULL"),
    )
    
    def __repr__(self):
        return f"<Verdict {self.ticker}: {self.verdict} (score={self.conviction_score})>"


# ============================================================================
# 6. IMAGE ANALYSIS LOG
# ============================================================================

class ImageAnalysisLogModel(Base):
    """Log of image analysis for line extraction"""
    __tablename__ = "image_analysis_log"
    
    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), nullable=False, index=True)
    image_path = Column(Text, nullable=False)
    
    # Extracted data
    extracted_green_line = Column(Numeric(12, 4), nullable=True)
    extracted_red_line = Column(Numeric(12, 4), nullable=True)
    extracted_grey_line = Column(Numeric(12, 4), nullable=True)
    extracted_current_price = Column(Numeric(12, 4), nullable=True)
    
    # Metadata
    analysis_method = Column(String(50))
    confidence_score = Column(Numeric(3, 2), nullable=True)
    raw_extraction_data = Column(JSONB, nullable=True)
    
    # Status
    status = Column(String(20), default='pending')
    verified_by = Column(String(100), nullable=True)
    verified_at = Column(TIMESTAMP(timezone=True), nullable=True)
    
    # Timestamps
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=True)
    
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'completed', 'failed', 'verified')", name='check_image_status'),
        Index('idx_image_analysis_ticker', 'ticker'),
        Index('idx_image_analysis_status', 'status'),
    )
    
    def __repr__(self):
        return f"<ImageAnalysis {self.ticker}: {self.status}>"


# ============================================================================
# 7. GOMES RULES LOG (Audit Trail)
# ============================================================================

class GomesRulesLogModel(Base):
    """Audit trail for Gomes rule applications"""
    __tablename__ = "investment_rules_log"
    
    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), nullable=False, index=True)
    verdict_id = Column(Integer, ForeignKey('investment_verdicts.id', ondelete='CASCADE'))
    
    # Rule application
    rule_name = Column(String(100), nullable=False)
    rule_result = Column(String(20), nullable=False)
    rule_impact = Column(Text, nullable=True)
    
    # Context
    rule_input = Column(JSONB, nullable=True)
    
    # Timestamp
    applied_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    
    # Relationships
    verdict = relationship("InvestmentVerdictModel", back_populates="rules_log")
    
    __table_args__ = (
        CheckConstraint("rule_result IN ('PASSED', 'BLOCKED', 'WARNING', 'ADJUSTED')", name='check_rule_result'),
        Index('idx_rules_log_ticker', 'ticker', 'applied_at'),
        Index('idx_rules_log_verdict', 'verdict_id'),
        Index('idx_rules_log_rule', 'rule_name', 'rule_result'),
    )
    
    def __repr__(self):
        return f"<RulesLog {self.ticker}: {self.rule_name}={self.rule_result}>"


# ============================================================================
# 8. GOMES ALERTS (Thesis Drift Notifications)
# ============================================================================

class GomesAlert(Base):
    """
    Thesis Drift and Investment Alerts
    
    Generated by ThesisMonitor when score changes are detected.
    THESIS_BROKEN: Critical - immediate sell recommended
    THESIS_DRIFT: Warning - review position
    IMPROVEMENT: Opportunity - consider adding
    """
    __tablename__ = "gomes_alerts"
    
    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), nullable=False, index=True)
    
    # Alert type and severity
    alert_type = Column(
        String(30),
        nullable=False,
        doc="THESIS_BROKEN, THESIS_DRIFT, IMPROVEMENT, MAJOR_IMPROVEMENT, STABLE"
    )
    severity = Column(
        String(15),
        nullable=False,
        doc="CRITICAL, WARNING, INFO, OPPORTUNITY"
    )
    
    # Content
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    recommendation = Column(Text, nullable=True)
    
    # Score tracking
    previous_score = Column(Integer, nullable=True)
    current_score = Column(Integer, nullable=False)
    score_delta = Column(Integer, nullable=False, default=0)
    
    # Source
    source = Column(String(100), doc="analysis_update, deep_dd, earnings, news")
    
    # Read status
    is_read = Column(Boolean, nullable=False, default=False)
    read_at = Column(TIMESTAMP(timezone=True), nullable=True)
    
    # Action taken
    action_taken = Column(String(50), nullable=True, doc="acknowledged, dismissed, acted_upon")
    action_notes = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    expires_at = Column(TIMESTAMP(timezone=True), nullable=True)
    
    __table_args__ = (
        CheckConstraint(
            "alert_type IN ('THESIS_BROKEN', 'THESIS_DRIFT', 'STABLE', 'IMPROVEMENT', 'MAJOR_IMPROVEMENT')",
            name='check_alert_type'
        ),
        CheckConstraint(
            "severity IN ('CRITICAL', 'WARNING', 'INFO', 'OPPORTUNITY')",
            name='check_severity'
        ),
        CheckConstraint('current_score >= 0 AND current_score <= 10', name='check_current_score'),
        Index('idx_alerts_ticker', 'ticker', 'created_at'),
        Index('idx_alerts_unread', 'is_read', 'severity', postgresql_where="is_read = false"),
        Index('idx_alerts_severity', 'severity', 'created_at'),
    )
    
    def __repr__(self):
        return f"<GomesAlert {self.ticker}: {self.alert_type} ({self.severity})>"


# ============================================================================
# 9. GOMES SCORE HISTORY (Conviction Score Tracking)
# ============================================================================

class GomesScoreHistory(Base):
    """
    Historical tracking of conviction score changes.
    
    Used for thesis drift analysis and trend detection.
    """
    __tablename__ = "gomes_score_history"
    
    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), nullable=False, index=True)
    stock_id = Column(Integer, ForeignKey('stocks.id', ondelete='CASCADE'), nullable=True)
    
    # Score
    conviction_score = Column(Integer, nullable=False)
    previous_score = Column(Integer, nullable=True)
    score_delta = Column(Integer, nullable=True)
    
    # Components (optional - for detailed tracking)
    thesis_score = Column(Integer, nullable=True)
    valuation_score = Column(Integer, nullable=True)
    technical_score = Column(Integer, nullable=True)
    
    # Context
    source = Column(String(100), doc="Source of score update")
    reason = Column(Text, doc="Why score changed")
    
    # Timestamps
    recorded_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    
    # Relationships
    stock = relationship("Stock", foreign_keys=[stock_id])
    
    __table_args__ = (
        CheckConstraint('conviction_score >= 0 AND conviction_score <= 10', name='check_hist_score'),
        Index('idx_score_history_ticker', 'ticker', 'recorded_at'),
        Index('idx_score_history_score', 'conviction_score', 'recorded_at'),
    )
    
    def __repr__(self):
        return f"<ScoreHistory {self.ticker}: {self.conviction_score} @ {self.recorded_at}>"
