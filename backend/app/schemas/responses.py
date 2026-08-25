"""
API Response Schemas

Pydantic models for serializing responses from FastAPI endpoints.

Clean Code Principles Applied:
- Clear, self-documenting field names
- from_attributes for SQLAlchemy model conversion
- Examples for API documentation
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, computed_field

from app.core.tickers import canonical_ticker as to_canonical


class EarningsInfo(BaseModel):
    """
    When this company reports next, and how well that is known.

    Sent on both the holdings table and the watchlist so the countdown reads
    identically in each. `confirmed` is the field that must never be dropped:
    an announced date and a pattern this app worked out are both actionable and
    are not the same claim, and `label_cs` already carries the difference in
    words ("za 78 dní" against "asi za 98 dní") so a cell cannot lose it.
    """

    next_date: date
    window_end: date | None = None
    days: int
    confirmed: bool
    source: str
    label_cs: str
    detail_cs: str
    #: Inside the fourteen days the Buy Guard refuses purchases in.
    blackout: bool


class StockAnalysisResult(BaseModel):
    """Individual stock analysis result from AI - Trading focused."""
    
    ticker: str
    company_name: str | None = None
    sentiment: str = "Neutral"
    conviction_score: int = Field(ge=1, le=10)
    price_target: str | None = None
    edge: str | None = None
    catalysts: str | None = None
    risks: str | None = None
    status: str | None = None
    time_horizon: str | None = "Long-term"
    conviction_score: int | None = Field(default=None, ge=1, le=10)
    
    # Trading action fields
    action_verdict: str | None = "WATCH_LIST"
    entry_zone: str | None = None
    price_target_short: str | None = None
    price_target_long: str | None = None
    stop_loss_risk: str | None = None
    moat_rating: int | None = Field(default=3, ge=1, le=5)
    trade_rationale: str | None = None
    chart_setup: str | None = None


class StockResponse(BaseModel):
    """Response model for individual stock data."""
    
    id: int
    created_at: datetime
    ticker: str
    company_name: str | None = None
    source_type: str | None = None
    speaker: str | None = None
    #: GOMES / BREAKOUT_INVESTORS / OTHER. Sent because a ticker can hold one
    #: row per source, and the frontend has to know which take it is looking
    #: at before it picks one to show.
    source_key: str | None = None
    sentiment: str | None = None
    conviction_score: int | None = None
    price_target: str | None = None
    time_horizon: str | None = None
    edge: str | None = None
    #: Next earnings and the countdown to it. None means no date from any
    #: tier — which the table shows as a dash, not as "no earnings coming".
    earnings: EarningsInfo | None = None
    catalysts: str | None = None
    risks: str | None = None
    raw_notes: str | None = None
    
    # Trading action fields
    action_verdict: str | None = None
    entry_zone: str | None = None
    price_target_short: str | None = None
    price_target_long: str | None = None
    stop_loss_risk: str | None = None
    moat_rating: int | None = None
    trade_rationale: str | None = None
    chart_setup: str | None = None
    
    # Price Lines data (from Gomes Intelligence)
    current_price: float | None = None
    green_line: float | None = None
    red_line: float | None = None
    grey_line: float | None = None
    
    # Computed price position (0-100%, where 0=at green, 100=at red)
    price_position_pct: float | None = None
    price_zone: str | None = None  # "UNDERVALUED", "FAIR", "OVERVALUED"
    
    # Gomes Master Table (2026-01-25)
    asset_class: str | None = None
    cash_runway_months: int | None = None
    insider_ownership_pct: float | None = None
    fully_diluted_market_cap: float | None = None
    enterprise_value: float | None = None
    quarterly_burn_rate: float | None = None
    total_cash: float | None = None
    inflection_status: str | None = None  # WAIT_TIME, UPCOMING, ACTIVE_GOLD_MINE
    primary_catalyst: str | None = None
    #: `date`, not `str`. The column is DATE, and typing it as a string here
    #: meant the schema validated only while every row happened to be NULL.
    #: The first real date turned GET /api/stocks into a 500, the frontend read
    #: an empty stock list, and the app reported "12 pozic bez konvikčního
    #: skóre" — a confident claim that no analysis existed, made out of a type
    #: annotation. See tests/test_stock_schema_types.py.
    catalyst_date: date | None = None
    thesis_narrative: str | None = None
    price_floor: float | None = None
    price_target_24m: float | None = None
    current_valuation_stage: str | None = None  # UNDERVALUED, FAIR, OVERVALUED, BUBBLE
    price_base: float | None = None
    price_moon: float | None = None
    forward_pe_2027: float | None = None
    max_allocation_cap: float | None = None
    stop_loss_price: float | None = None
    insider_activity: str | None = None  # BUYING, HOLDING, SELLING
    market_cap: float | None = None
    
    # Trading Zones (Calculated from Price Lines)
    max_buy_price: float | None = None
    start_sell_price: float | None = None
    risk_to_floor_pct: float | None = None
    upside_to_ceiling_pct: float | None = None
    trading_zone_signal: str | None = None  # AGGRESSIVE_BUY, BUY, HOLD, SELL, STRONG_SELL
    
    @computed_field  # type: ignore[prop-decorator]
    @property
    def canonical_ticker(self) -> str:
        """
        The symbol to match a position on. See `app/core/tickers.py`.

        `KUYA.V` and `KUYAF` are one company holding two rows in this table.
        Without a shared key the frontend listed the second one under
        "Sledované" while the owner held the first.
        """
        return to_canonical(self.ticker)

    model_config = {"from_attributes": True}


class AnalysisResponse(BaseModel):
    """Response model for analysis operations."""
    
    success: bool
    message: str
    stocks_found: int
    stocks: list[StockAnalysisResult]
    source_id: str
    source_type: str
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "success": True,
                "message": "Successfully analyzed transcript and found 3 stock mentions",
                "stocks_found": 3,
                "stocks": [],
                "source_id": "video_123",
                "source_type": "YouTube",
            }
        }
    }


class StockPortfolioResponse(BaseModel):
    """Response model for stock portfolio/watchlist data."""
    
    total_stocks: int
    stocks: list[StockResponse]
    filters_applied: dict | None = None
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "total_stocks": 10,
                "stocks": [],
                "filters_applied": {"sentiment": "BULLISH", "min_conviction_score": 7},
            }
        }
    }


class StocksListResponse(BaseModel):
    """Response model for list of stocks."""
    
    stocks: list[StockResponse]
    total_stocks: int
    filters_applied: dict | None = None


class HealthCheckResponse(BaseModel):
    """Response model for health check endpoint."""
    
    status: str
    message: str
    timestamp: datetime


class ErrorResponse(BaseModel):
    """Response model for error messages."""
    
    success: bool = False
    error: str
    detail: str | None = None
