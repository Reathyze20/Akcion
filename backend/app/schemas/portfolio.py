"""
Portfolio Schemas

Pydantic models for portfolio and position management.

Clean Code Principles Applied:
- Clear field descriptions
- Proper validation constraints
- from_attributes for SQLAlchemy conversion
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, computed_field

from app.core.tickers import canonical_ticker as to_canonical
from app.services.currency import currency_mismatch

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
    monthly_contribution: float = Field(default=0.0, description="Monthly contribution in CZK; zero until set")


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
    avg_cost: float | None = Field(
        None,
        description="Average cost per share; None = unknown, user must fill in",
    )
    currency: str = Field(default="USD", description="Currency code (USD, EUR, HKD, etc.)")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def canonical_ticker(self) -> str:
        """
        The symbol to match analysis on. See `app/core/tickers.py`.

        Sent alongside `ticker`, never instead of it: four positions are held
        on a Canadian exchange while every analysis names the US OTC listing,
        and the app used to treat those as two companies. The broker's symbol
        stays the one on screen.
        """
        return to_canonical(self.ticker)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def currency_conflict(self) -> str | None:
        """
        Měna, kterou napovídá přípona tickeru, když nesedí s uloženou.

        `None` znamená buď že sedí, nebo že se to říct nedá — a ty dva stavy
        se schválně nerozlišují, protože „nevíme" se nesmí hlásit jako
        „v pořádku". Počítá to backend, aby tabulka burz a měn nežila na dvou
        místech a nerozešla se.
        """
        conflict = currency_mismatch(self.ticker, self.currency)
        return None if conflict is None else conflict[0]


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
    currency_confirmed: bool | None = Field(
        default=None,
        description=(
            "Majitel potvrdil, že měna sedí s tím, co má u brokera. "
            "Umlčí kontrolu podle přípony tickeru, která u IMP.V a KUYA.V "
            "hlásí konflikt, přestože EUR je správně."
        ),
    )


class TradeRequest(BaseModel):
    """
    A trade the owner actually executed at his broker, being recorded here.

    The app is decision-support: it never places orders. This records what
    already happened so the ledger stays the source of truth for realized P/L
    and for the guardrails that read it (cooldown after a loss, revenge-trade
    detection).
    """

    side: Literal["BUY", "SELL"]
    shares: float = Field(..., gt=0, description="Shares traded (must be > 0)")
    price: float = Field(..., gt=0, description="Price per share actually paid/received")
    emotion_tag: str | None = Field(
        default=None,
        max_length=100,
        description="Why, in the owner's words — 'bál jsem se, ale koupil jsem dip'",
    )
    note: str | None = Field(default=None, max_length=500)
    trade_date: date | None = Field(
        default=None,
        description=(
            "Den, kdy obchod proběhl u brokera. Vynech jen když ho opravdu "
            "neznáš — bez něj se zpětný zápis starého prodeje počítá jako "
            "dnešní obchod a spustí brzdu proti přeobchodování."
        ),
    )


class TradeResponse(BaseModel):
    """Result of recording a trade: what was written and where the position landed."""

    success: bool
    log_id: int
    ticker: str
    side: str
    shares: float
    price: float
    currency: str | None
    gross_amount: float
    # None (not 0) when the position's purchase price was never known.
    realized_pl: float | None
    cost_basis: float | None
    new_shares_count: float
    new_avg_cost: float | None
    avg_cost_known: bool
    position_closed: bool
    message: str


class PositionResponse(PositionBase):
    """Schema for position response with computed fields."""
    
    id: int
    portfolio_id: int
    currency_confirmed: bool = False
    current_price: float | None = None
    last_price_update: datetime | None = None
    cost_basis: float | None = None
    market_value: float
    unrealized_pl: float | None = None
    unrealized_pl_percent: float | None = None
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
    # Tickers imported WITHOUT a purchase price (e.g. Degiro exports carry
    # none) — the user must fill avg_cost in before P/L rules apply to them.
    missing_avg_cost: list[str] = []


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

    # §V3: ORANGE and RED are claims about a CAUSE, not about how dear the
    # market is. Setting one without naming what is happening is refused —
    # not to be strict, but because a cause is the only thing that can later
    # be reviewed, and nothing else in this app ever lowers the semafor.
    catalyst_description: str | None = Field(
        None,
        description="What is happening. Required to set ORANGE or RED.",
    )
    catalyst_severity_known: bool = Field(
        False,
        description="False = ORANGE (size unknown). True = RED (known severe).",
    )


class MarketStatusResponse(BaseModel):
    """Schema for market status response."""
    
    id: int
    status: MarketStatusEnum
    last_updated: datetime
    note: str | None = None

    catalyst_description: str | None = None
    catalyst_identified_at: datetime | None = None
    catalyst_severity_known: bool = False
    #: Whether the grade on the field is backed by what is on record, and what
    #: to say about it. Computed, not stored — see `market_catalyst.check`.
    catalyst_supported: bool = True
    catalyst_stale: bool = False
    catalyst_message_cs: str | None = None

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
    conviction_score: int | None
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
