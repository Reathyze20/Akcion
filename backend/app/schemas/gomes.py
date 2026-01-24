"""
Gomes Intelligence Pydantic Schemas
=====================================

API request/response schemas for Gomes Intelligence endpoints.

Author: GitHub Copilot with Claude Opus 4.5
Date: 2026-01-17
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ============================================================================
# MARKET ALERT SCHEMAS
# ============================================================================

class MarketAlertResponse(BaseModel):
    """Current market alert status"""
    alert_level: str = Field(..., description="GREEN, YELLOW, ORANGE, RED")
    mode_name: str = Field(default="", description="OFFENSE, SELECTIVE, DEFENSE, CASH IS KING")
    mode_description: str = Field(default="", description="Human-readable description")
    stocks_pct: float = Field(..., description="Target stock allocation %")
    cash_pct: float = Field(..., description="Target cash allocation %")
    hedge_pct: float = Field(..., description="Target hedge allocation %")
    hedge_ticker: str = Field(default="RWM", description="Hedge ETF ticker")
    reason: Optional[str] = Field(None, description="Reason for current level")
    effective_from: datetime = Field(..., description="When this level became effective")
    
    class Config:
        from_attributes = True


class SetMarketAlertRequest(BaseModel):
    """Request to change market alert level"""
    alert_level: str = Field(..., pattern="^(GREEN|YELLOW|ORANGE|RED)$")
    reason: str = Field(..., min_length=5, description="Reason for change")
    source: str = Field(default="manual", description="Source: manual, transcript, system")


# ============================================================================
# LIFECYCLE SCHEMAS
# ============================================================================

class LifecyclePhaseResponse(BaseModel):
    """Stock lifecycle phase"""
    ticker: str
    phase: str = Field(..., description="GREAT_FIND, WAIT_TIME, GOLD_MINE, UNKNOWN")
    is_investable: bool
    firing_on_all_cylinders: Optional[bool] = None
    cylinders_count: Optional[int] = None
    reasoning: Optional[str] = None
    confidence: str = Field(default="MEDIUM")
    detected_at: datetime
    
    class Config:
        from_attributes = True


class ClassifyLifecycleRequest(BaseModel):
    """Request to classify stock lifecycle"""
    ticker: str = Field(..., min_length=1, max_length=10)
    transcript_text: Optional[str] = Field(None, description="Transcript for classification")


# ============================================================================
# PRICE LINES SCHEMAS
# ============================================================================

class PriceLinesResponse(BaseModel):
    """Price target lines"""
    ticker: str
    green_line: Optional[float] = Field(None, description="Buy zone price")
    red_line: Optional[float] = Field(None, description="Sell zone price")
    grey_line: Optional[float] = Field(None, description="Neutral zone")
    current_price: Optional[float] = None
    is_undervalued: Optional[bool] = None
    is_overvalued: Optional[bool] = None
    price_zone: Optional[str] = Field(None, description="BUY, HOLD, SELL")
    source: Optional[str] = None
    image_path: Optional[str] = None
    
    class Config:
        from_attributes = True


class SetPriceLinesRequest(BaseModel):
    """Request to set price lines"""
    ticker: str = Field(..., min_length=1, max_length=10)
    green_line: Optional[float] = Field(None, gt=0)
    red_line: Optional[float] = Field(None, gt=0)
    grey_line: Optional[float] = Field(None, gt=0)
    current_price: Optional[float] = Field(None, gt=0)
    source: str = Field(default="manual")
    source_reference: Optional[str] = None


# ============================================================================
# VERDICT SCHEMAS
# ============================================================================

class GomesVerdictResponse(BaseModel):
    """Complete investment verdict"""
    ticker: str
    verdict: str = Field(..., description="STRONG_BUY, BUY, ACCUMULATE, HOLD, TRIM, SELL, AVOID, BLOCKED")
    passed_gomes_filter: bool
    blocked_reason: Optional[str] = None
    
    # Scores
    gomes_score: int = Field(..., ge=0, le=10)
    ml_prediction_score: Optional[float] = Field(None, description="ML confidence 0-100%")
    ml_direction: Optional[str] = Field(None, description="UP, DOWN, NEUTRAL")
    
    # Context
    lifecycle_phase: Optional[str] = None
    market_alert: str = Field(default="GREEN")
    position_tier: Optional[str] = None
    max_position_pct: float = Field(default=0.0)
    
    # Price context
    current_price: Optional[float] = None
    green_line: Optional[float] = None
    red_line: Optional[float] = None
    price_zone: Optional[str] = Field(None, description="BUY, HOLD, SELL based on lines")
    
    # Risk
    risk_factors: list[str] = Field(default_factory=list)
    days_to_earnings: Optional[int] = None
    
    # Catalyst
    has_catalyst: bool = False
    catalyst_type: Optional[str] = None
    catalyst_description: Optional[str] = None
    
    # Cases
    bull_case: Optional[str] = None
    bear_case: Optional[str] = None
    
    # Confidence
    confidence: str = Field(default="MEDIUM")
    reasoning: str = Field(default="")
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now)
    
    class Config:
        from_attributes = True


class GenerateVerdictRequest(BaseModel):
    """Request to generate investment verdict"""
    ticker: str = Field(..., min_length=1, max_length=10)
    gomes_score: Optional[int] = Field(None, ge=0, le=10, description="Override base score")
    current_price: Optional[float] = Field(None, gt=0)
    earnings_date: Optional[datetime] = None
    transcript_text: Optional[str] = None
    force_ml_refresh: bool = False


# ============================================================================
# WATCHLIST SCAN SCHEMAS
# ============================================================================

class WatchlistScanResponse(BaseModel):
    """Watchlist scan results"""
    total_scanned: int
    passed_filter: int
    blocked: int
    top_opportunities: list[GomesVerdictResponse]
    blocked_stocks: list[dict[str, Any]]
    market_alert: str
    scan_timestamp: datetime = Field(default_factory=datetime.now)


class ScanWatchlistRequest(BaseModel):
    """Request to scan watchlist"""
    min_score: int = Field(default=5, ge=0, le=10)
    limit: int = Field(default=20, ge=1, le=100)


# ============================================================================
# DASHBOARD SCHEMAS
# ============================================================================

class GomesDashboardResponse(BaseModel):
    """Complete Gomes Intelligence dashboard"""
    # Market state
    market_alert: MarketAlertResponse
    
    # Portfolio allocation
    recommended_allocation: dict[str, float] = Field(
        default_factory=lambda: {"stocks": 100, "cash": 0, "hedge": 0}
    )
    
    # Top opportunities
    top_opportunities: list[GomesVerdictResponse]
    
    # Blocked stocks
    blocked_count: int
    blocked_stocks: list[dict[str, Any]]
    
    # Statistics
    total_watchlist: int
    investable_count: int
    avg_gomes_score: float
    
    # Timestamps
    last_updated: datetime = Field(default_factory=datetime.now)


class ImageLinesImportResponse(BaseModel):
    """Response from importing lines from images"""
    imported_count: int
    tickers: list[str]
    message: str


# ============================================================================
# POSITION SIZING SCHEMAS
# ============================================================================

class PositionSizeResponse(BaseModel):
    """Position sizing recommendation"""
    ticker: str
    tier: str = Field(..., description="PRIMARY, SECONDARY, TERTIARY")
    max_portfolio_pct: float
    recommended_pct: float
    allowed_at_current_alert: bool
    current_alert: str
    reasoning: str


class CalculatePositionRequest(BaseModel):
    """Request to calculate position size"""
    ticker: str
    portfolio_value: float = Field(..., gt=0)
    current_price: Optional[float] = Field(None, gt=0)


# ============================================================================
# ML STOCKS LIST SCHEMAS
# ============================================================================

class GomesStockItem(BaseModel):
    """Single stock with Gomes data and ML prediction info"""
    ticker: str
    company_name: Optional[str] = None
    gomes_score: Optional[int] = None
    sentiment: Optional[str] = None
    action_verdict: Optional[str] = None
    lifecycle_phase: Optional[str] = None
    
    # Price lines from Gomes
    green_line: Optional[float] = Field(None, description="Buy zone price")
    red_line: Optional[float] = Field(None, description="Sell zone price")
    current_price: Optional[float] = None
    price_zone: Optional[str] = Field(None, description="BUY, HOLD, SELL")
    price_position_pct: Optional[float] = Field(None, description="Position between lines as %")
    
    # ML prediction (summary)
    has_ml_prediction: bool = False
    ml_direction: Optional[str] = Field(None, description="UP, DOWN, NEUTRAL")
    ml_confidence: Optional[float] = Field(None, description="0-1 confidence")
    
    # Video context
    video_date: Optional[str] = None
    notes: Optional[str] = None
    
    class Config:
        from_attributes = True


class GomesStocksListResponse(BaseModel):
    """Response with all Gomes stocks for ML page"""
    stocks: list[GomesStockItem]
    total_count: int
    stocks_with_lines: int
    stocks_with_ml: int
    market_alert: str = "GREEN"


# ============================================================================
# DEEP DUE DILIGENCE SCHEMAS (v2.0 - The Treasure Hunter)
# ============================================================================

class PriceTargetsSchema(BaseModel):
    """Price target scenarios"""
    pessimistic: Optional[float] = Field(None, description="Bear case price")
    realistic: Optional[float] = Field(None, description="Base case price")
    optimistic: Optional[float] = Field(None, description="Bull case price")


class DeepDueDiligenceResult(BaseModel):
    """
    Result from Gomes Deep Due Diligence Analysis.
    
    This is the structured output from AI analysis of transcripts/news.
    Used to update stock data and trigger alerts.
    """
    ticker: str
    company_name: Optional[str] = None
    gomes_score: int = Field(..., ge=0, le=10)
    
    # Thesis tracking
    thesis_status: str = Field(
        ..., 
        pattern="^(IMPROVED|STABLE|DETERIORATED|BROKEN)$",
        description="IMPROVED, STABLE, DETERIORATED, BROKEN"
    )
    inflection_point_status: str = Field(
        ..., 
        pattern="^(UPCOMING|ACTIVE|COMPLETED|FAILED)$",
        description="UPCOMING, ACTIVE, COMPLETED, FAILED"
    )
    
    # Risk/Reward
    upside_potential: str = Field(..., description="e.g. '150%' or '2x-3x'")
    risk_level: str = Field(
        ..., 
        pattern="^(LOW|MEDIUM|HIGH|EXTREME)$"
    )
    
    # Financial health
    cash_runway_months: Optional[int] = Field(None, ge=0, description="Months of runway")
    
    # Action
    action_signal: str = Field(
        ..., 
        pattern="^(BUY|ACCUMULATE|HOLD|TRIM|SELL)$"
    )
    kelly_criterion_hint: float = Field(
        ..., 
        ge=0, 
        le=15, 
        description="Max position size % (Kelly capped at 15%)"
    )
    
    # Price targets
    price_targets: PriceTargetsSchema
    green_line: Optional[float] = Field(None, description="Buy zone price")
    red_line: Optional[float] = Field(None, description="Sell zone price")
    
    # Qualitative
    key_milestones: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    edge: Optional[str] = Field(None, description="Information arbitrage")
    catalysts: Optional[str] = Field(None, description="Upcoming events")
    risks: Optional[str] = Field(None, description="Main risks")
    
    class Config:
        from_attributes = True


class DeepDueDiligenceRequest(BaseModel):
    """Request for deep due diligence analysis"""
    transcript: str = Field(..., min_length=100, description="Raw transcript/text to analyze")
    ticker: Optional[str] = Field(None, description="Force specific ticker analysis")
    include_existing_data: bool = Field(
        default=True, 
        description="Include existing stock data for thesis drift comparison"
    )


class DeepDueDiligenceResponse(BaseModel):
    """Response from deep due diligence analysis"""
    # Human-readable analysis (Czech)
    analysis_text: str = Field(..., description="Gomes deep dive in Czech")
    
    # Structured data
    data: DeepDueDiligenceResult
    
    # Thesis drift (if comparing with existing data)
    thesis_drift: Optional[str] = Field(None, description="IMPROVED, STABLE, DETERIORATED, BROKEN")
    score_change: Optional[int] = Field(None, description="Change from previous score")
    
    # Metadata
    analyzed_at: datetime = Field(default_factory=datetime.now)
    source_length: int = Field(..., description="Length of input transcript")
    
    class Config:
        from_attributes = True


class ThesisDriftResult(BaseModel):
    """Result from thesis drift comparison"""
    ticker: str
    thesis_drift: str = Field(
        ..., 
        pattern="^(IMPROVED|STABLE|DETERIORATED|BROKEN)$"
    )
    score_change: int = Field(..., ge=-10, le=10)
    new_gomes_score: int = Field(..., ge=0, le=10)
    reasoning: str
    key_changes: list[str]
    action_update: str = Field(
        ..., 
        pattern="^(BUY|ACCUMULATE|HOLD|TRIM|SELL)$"
    )
    alert_level: str = Field(
        ..., 
        pattern="^(INFO|WARNING|CRITICAL)$"
    )
