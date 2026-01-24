"""
Portfolio Schemas

Pydantic models for portfolio and position management.

Clean Code Principles Applied:
- Clear field descriptions
- Proper validation constraints
- from_attributes for SQLAlchemy conversion
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from ..models.portfolio import BrokerType, MarketStatusEnum


# ==============================================================================
# Portfolio Schemas
# ==============================================================================

class PortfolioBase(BaseModel):
    """Base portfolio schema with common fields."""
    
    name: str = Field(..., description="Portfolio name")
    owner: str = Field(..., description="Portfolio owner (e.g., 'Já', 'Přítelkyně')")
    broker: BrokerType = Field(..., description="Broker type")
    cash_balance: float = Field(default=0.0, description="Available cash for investments")
    monthly_contribution: float = Field(default=20000.0, description="Monthly contribution amount in CZK")


class PortfolioCreate(PortfolioBase):
    """Schema for creating a new portfolio."""
    pass


class PortfolioResponse(PortfolioBase):
    """Schema for portfolio response with computed fields."""
    
    id: int
    owner: str
    created_at: datetime
    updated_at: datetime
    position_count: int | None = 0
    total_value: float | None = 0.0

    model_config = {"from_attributes": True}


# ==============================================================================
# Position Schemas
# ==============================================================================

class PositionBase(BaseModel):
    """Base position schema with common fields."""
    
    ticker: str = Field(..., description="Stock ticker symbol")
    company_name: str | None = Field(None, description="Company name")
    shares_count: float = Field(..., description="Number of shares")
    avg_cost: float = Field(..., description="Average cost per share")
    currency: str = Field(default="USD", description="Currency code (USD, EUR, HKD, etc.)")


class PositionCreate(PositionBase):
    """Schema for creating a new position."""
    portfolio_id: int


class PositionUpdate(BaseModel):
    """Schema for updating an existing position."""
    
    shares_count: float | None = None
    avg_cost: float | None = None
    current_price: float | None = None
    currency: str | None = None
    company_name: str | None = None
    ticker: str | None = None


class PositionResponse(PositionBase):
    """Schema for position response with computed fields."""
    
    id: int
    portfolio_id: int
    current_price: float | None = None
    last_price_update: datetime | None = None
    cost_basis: float
    market_value: float
    unrealized_pl: float
    unrealized_pl_percent: float
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True,
        "json_encoders": {
            float: lambda v: 0.0 if (v != v or v == float("inf") or v == float("-inf")) else v,
        },
    }


# ==============================================================================
# CSV Upload Schemas
# ==============================================================================

class CSVUploadRequest(BaseModel):
    """Schema for CSV upload request."""
    
    portfolio_id: int = Field(..., description="Target portfolio ID")
    broker: BrokerType = Field(..., description="Broker type for parsing")
    csv_content: str = Field(..., description="Raw CSV file content")


class CSVUploadResponse(BaseModel):
    """Schema for CSV upload response."""
    
    success: bool
    message: str
    positions_created: int
    positions_updated: int
    errors: list[str] = []


# ==============================================================================
# Market Data Schemas
# ==============================================================================

class PriceRefreshRequest(BaseModel):
    """Schema for price refresh request."""
    portfolio_id: int | None = None


class PriceRefreshResponse(BaseModel):
    """Schema for price refresh response."""
    
    success: bool
    message: str | None = None
    updated_count: int
    failed_count: int
    cached_count: int = 0
    tickers: list[str]
    prices: dict = {}


# ==============================================================================
# Market Status Schemas
# ==============================================================================

class MarketStatusUpdate(BaseModel):
    """Schema for updating market status."""
    status: MarketStatusEnum = Field(..., description="Market condition")
    note: str | None = Field(None, description="Optional explanation")


class MarketStatusResponse(BaseModel):
    """Schema for market status response."""
    
    id: int
    status: MarketStatusEnum
    last_updated: datetime
    note: str | None = None

    model_config = {"from_attributes": True}


# ==============================================================================
# Gap Analysis Schemas
# ==============================================================================

class EnrichedStockResponse(BaseModel):
    """Stock enriched with position data and match signal."""
    
    # Stock analysis data
    id: int
    ticker: str
    company_name: str | None
    action_verdict: str | None
    entry_zone: str | None
    price_target_short: str | None
    price_target_long: str | None
    stop_loss_risk: str | None
    moat_rating: int | None
    gomes_score: int | None
    sentiment: str | None
    edge: str | None
    risks: str | None
    catalysts: str | None
    trade_rationale: str | None
    chart_setup: str | None
    created_at: datetime | None
    updated_at: datetime | None
    
    # Position data
    user_holding: bool
    holding_quantity: float | None = None
    holding_avg_cost: float | None = None
    holding_current_price: float | None = None
    holding_unrealized_pl: float | None = None
    holding_unrealized_pl_percent: float | None = None
    
    # Gap analysis
    match_signal: str
    market_status: str


class MatchAnalysisRequest(BaseModel):
    """Schema for match analysis request."""
    portfolio_id: int | None = None


class MatchAnalysisResponse(BaseModel):
    """Schema for match analysis response with summary stats."""
    
    total_stocks: int
    opportunities: int
    accumulate: int
    danger_exits: int
    wait_market_bad: int
    market_status: str
    stocks: list[EnrichedStockResponse]


# ==============================================================================
# Portfolio Summary Schemas
# ==============================================================================

class PortfolioSummaryResponse(BaseModel):
    """Schema for portfolio summary with all positions and totals."""
    
    portfolio: PortfolioResponse
    positions: list[PositionResponse]
    total_cost_basis: float
    total_market_value: float
    total_unrealized_pl: float
    total_unrealized_pl_percent: float
    cash_balance: float = 0.0
    last_price_update: datetime | None
