"""
Portfolio and Position Models

Domain models for portfolio management and position tracking.

Clean Code Principles Applied:
- Explicit column documentation with doc parameter
- Type hints for all properties and methods
- Grouped related fields logically
- Constants via Enum classes
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum as SQLEnum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship, Mapped

from .base import Base

if TYPE_CHECKING:
    from typing import List


class BrokerType(str, Enum):
    """
    Supported broker platforms.
    
    Each broker has different CSV export formats handled by the importer.
    """
    T212 = "T212"
    DEGIRO = "DEGIRO"
    XTB = "XTB"


class Portfolio(Base):
    """
    Portfolio representing a user's investment account.
    
    Tracks:
    - Account metadata (name, owner, broker)
    - Cash balance available for investments
    - Associated positions (holdings)
    """
    
    __tablename__ = "portfolios"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
        doc="Unique identifier"
    )
    name = Column(
        String,
        nullable=False,
        doc="Portfolio display name (e.g., 'My Growth Portfolio')"
    )
    owner = Column(
        String(100),
        nullable=False,
        default="Default User",
        index=True,
        doc="Owner identifier (e.g., 'Já', 'Přítelkyně')"
    )
    broker = Column(
        SQLEnum(BrokerType),
        nullable=False,
        doc="Broker platform"
    )
    cash_balance = Column(
        Float,
        nullable=False,
        default=0.0,
        doc="Available cash for investments"
    )
    monthly_contribution = Column(
        Float,
        nullable=False,
        # Nula, ne dvacet tisíc. Výchozí hodnota sloupce se jinak tváří jako
        # vklad, který nikdo nezadal — a rozpočet, ze kterého aplikace
        # doporučuje nákupy, se s každým novým portfoliem tiše zvedl.
        default=0.0,
        doc="Monthly contribution in CZK. Zero until a human sets one."
    )
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        doc="Creation timestamp"
    )
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        doc="Last update timestamp"
    )

    # Relationships
    positions: Mapped[list["Position"]] = relationship(
        "Position",
        back_populates="portfolio",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Portfolio(id={self.id}, name={self.name}, owner={self.owner})>"


class Position(Base):
    """
    Position representing a stock holding in a portfolio.
    
    Tracks:
    - Stock identification (ticker, company name)
    - Quantity and cost basis
    - Current market price for P&L calculation
    """
    
    __tablename__ = "positions"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
        doc="Unique identifier"
    )
    portfolio_id = Column(
        Integer,
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
        doc="Parent portfolio ID"
    )
    ticker = Column(
        String,
        nullable=False,
        index=True,
        doc="Stock ticker symbol"
    )
    company_name = Column(
        String(255),
        nullable=True,
        doc="Full company name"
    )
    shares_count = Column(
        Float,
        nullable=False,
        doc="Number of shares held"
    )
    avg_cost = Column(
        Float,
        nullable=True,
        doc=(
            "Average purchase price per share. NULL = unknown (Degiro CSV "
            "exports carry no buy price) — the user must fill it in before "
            "P/L and the doubling rule apply. Never fabricated from a quote."
        )
    )
    currency = Column(
        String(3),
        nullable=False,
        default="USD",
        doc="Currency code (USD, EUR, HKD, etc.)"
    )
    currency_confirmed = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        doc=(
            "The owner has confirmed this currency against his broker. "
            "A ticker's suffix names an exchange and an exchange has one "
            "currency, so `currency_mismatch` warns when the two disagree — "
            "but IMP.V and KUYA.V are held on a European line while the "
            "ticker is the Canadian one the Gomes tracker uses, and there the "
            "currency is right and the suffix is a nickname. Only the owner "
            "knows which side is wrong, so this records his answer instead of "
            "the app guessing."
        ),
    )
    current_price = Column(
        Float,
        nullable=True,
        doc="Latest market price (updated by background job)"
    )
    last_price_update = Column(
        DateTime,
        nullable=True,
        doc="Timestamp of last price update"
    )
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        doc="Creation timestamp"
    )
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        doc="Last update timestamp"
    )

    # Relationships
    portfolio: Mapped["Portfolio"] = relationship(
        "Portfolio",
        back_populates="positions"
    )

    @property
    def cost_basis(self) -> float | None:
        """Total amount invested (shares * avg_cost); None when cost unknown."""
        if self.avg_cost is None:
            return None
        return self.shares_count * self.avg_cost

    @property
    def market_value(self) -> float:
        """Current market value (shares * current_price)."""
        if self.current_price is None:
            return 0.0
        return self.shares_count * self.current_price

    @property
    def unrealized_pl(self) -> float | None:
        """Unrealized profit/loss in currency; None when cost unknown."""
        if self.avg_cost is None:
            return None
        if self.current_price is None:
            return 0.0
        return (self.current_price - self.avg_cost) * self.shares_count

    @property
    def unrealized_pl_percent(self) -> float | None:
        """Unrealized profit/loss as percentage; None when cost unknown."""
        if self.avg_cost is None:
            return None
        if self.avg_cost == 0 or self.current_price is None:
            return 0.0
        return ((self.current_price - self.avg_cost) / self.avg_cost) * 100

    def __repr__(self) -> str:
        return f"<Position(ticker={self.ticker}, shares={self.shares_count})>"


class MarketStatusEnum(str, Enum):
    """
    Market condition indicator - Mark Gomes 4-state system.
    
    Determines overall portfolio stance and risk appetite.
    """
    GREEN = "GREEN"    # Offense - Aggressively deploying capital
    YELLOW = "YELLOW"  # Selective - Be cautious, pick best setups only
    ORANGE = "ORANGE"  # Defense - Reducing exposure, protecting gains
    RED = "RED"        # Cash is King - Maximum defensive, preserve capital


class MarketStatus(Base):
    """
    Global market status indicator (Traffic Light).
    
    Single row table tracking current market conditions
    according to Mark Gomes methodology.
    """
    
    __tablename__ = "market_status"

    id = Column(
        Integer,
        primary_key=True,
        doc="Unique identifier"
    )
    status = Column(
        SQLEnum(MarketStatusEnum),
        nullable=False,
        default=MarketStatusEnum.GREEN,
        doc="Current market status (GREEN/YELLOW/ORANGE/RED)"
    )
    last_updated = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        doc="Last status update timestamp"
    )
    note = Column(
        String,
        nullable=True,
        doc="Optional explanation or quote from analyst"
    )

    # ------------------------------------------------------------------
    # The identified cause behind an ORANGE or RED.
    #
    # GOMES_VIDEO_ADDENDUM.md §V3: the grades are not four levels of expensive.
    # YELLOW is "too expensive, cause unknown"; ORANGE is a named cause of
    # unknown size (COVID); RED is a named cause known to be severe (twice in
    # thirty years). A valuation measure can only ever report the first, so the
    # other two need somebody to write down what is happening.
    #
    # It is also the only handle this app has on DE-escalation. Nothing here
    # ever lowers the semafor — `market_watch` tightens and never loosens, by
    # design — so an ORANGE set during a scare and forgotten would keep the Buy
    # Guard refusing every purchase indefinitely, silently, because a refusal
    # looks exactly like caution working. A dated cause can be shown as stale
    # and questioned.
    # ------------------------------------------------------------------
    catalyst_description = Column(
        Text,
        nullable=True,
        doc="What is happening. Required for ORANGE/RED to be supported.",
    )
    catalyst_identified_at = Column(
        DateTime,
        nullable=True,
        doc="When it was recorded. Age is what makes a forgotten alert visible.",
    )
    catalyst_severity_known = Column(
        Boolean,
        nullable=False,
        default=False,
        doc="False = ORANGE ('I didn't know how bad'). True = RED ('I know how severe').",
    )

    def __repr__(self) -> str:
        return f"<MarketStatus(status={self.status.value})>"


class InvestmentLogType(str, Enum):
    """
    Types of investment activities tracked for gamification.
    """
    DEPOSIT = "DEPOSIT"       # Monthly contribution
    BUY = "BUY"               # Stock purchase
    SELL = "SELL"             # Stock sale
    DIVIDEND = "DIVIDEND"     # Dividend received
    MILESTONE = "MILESTONE"   # Portfolio milestone reached
    BADGE = "BADGE"           # Merit badge earned


class InvestmentLog(Base):
    """
    Investment activity log for gamification and journaling.
    
    Tracks all significant portfolio actions with emotional context
    for AI-powered monthly summaries and motivation.
    """
    
    __tablename__ = "investment_logs"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
        doc="Unique identifier"
    )
    portfolio_id = Column(
        Integer,
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=True,
        doc="Associated portfolio (nullable for global events)"
    )
    log_type = Column(
        SQLEnum(InvestmentLogType),
        nullable=False,
        doc="Type of activity"
    )
    ticker = Column(
        String(20),
        nullable=True,
        doc="Stock ticker (for BUY/SELL)"
    )
    trade_date = Column(
        Date,
        nullable=True,
        doc=(
            "When the trade actually happened at the broker. NULL for rows "
            "written before this column existed — and NULL means unknown, so "
            "readers fall back to created_at rather than to today. "
            "`created_at` is when the row was TYPED IN, and the two differ "
            "whenever an old sale is recorded late: three leftover rows closed "
            "on 2026-08-23 read as three trades that week and set off the "
            "over-trading brake."
        ),
    )
    amount = Column(
        Float,
        nullable=True,
        doc="Amount in CZK"
    )
    shares = Column(
        Float,
        nullable=True,
        doc="Number of shares (for BUY/SELL)"
    )
    price = Column(
        Float,
        nullable=True,
        doc="Price per share at time of action"
    )
    cost_basis = Column(
        Float,
        nullable=True,
        doc="Position avg_cost at the moment of the trade (NULL = purchase price unknown)"
    )
    realized_pl = Column(
        Float,
        nullable=True,
        doc="P/L locked in on a SELL. NULL when cost_basis is unknown — never 0 as a stand-in."
    )
    currency = Column(
        String(3),
        nullable=True,
        doc="ISO code for price/amount/cost_basis/realized_pl on this row"
    )
    # ------------------------------------------------------------------
    # The valuation this trade was made at.
    #
    # `price` and `cost_basis` say what was paid; these say what it was WORTH
    # at the time, on the canon's own 0-10 scale. The distinction is what makes
    # the 3-point rule (GOMES_METHODOLOGY_CANON.md §5) computable: that rule
    # fires on a 3-point move FROM ENTRY, and price alone cannot express it
    # because the analyst moves the lines underneath the price.
    #
    # NULL throughout means the lines were not known when the trade was
    # recorded. The rule then stays silent for that position — it does not fall
    # back to a score derived from today's band, which would date a move to a
    # starting point that never existed.
    # ------------------------------------------------------------------
    rr_score_at_entry = Column(
        Numeric(6, 3),
        nullable=True,
        doc="Logarithmic R/R score when the trade happened. NULL = lines unknown; the 3-point rule then stays silent."
    )
    green_line_at_entry = Column(
        Numeric(12, 4),
        nullable=True,
        doc="Green Line behind rr_score_at_entry, kept so the score survives a later re-banding"
    )
    red_line_at_entry = Column(
        Numeric(12, 4),
        nullable=True,
        doc="Red Line behind rr_score_at_entry"
    )
    cylinders_at_entry = Column(
        Integer,
        nullable=True,
        doc="Operational health 0-10 at the time — what the position was judged to deserve when opened"
    )
    line_currency = Column(
        String(3),
        nullable=True,
        doc="Currency of the entry lines, which need not be the currency of `price`"
    )
    emotion_tag = Column(
        String(100),
        nullable=True,
        doc="Emotional context (e.g., 'Bál jsem se, ale koupil jsem dip')"
    )
    note = Column(
        String(500),
        nullable=True,
        doc="User note or AI-generated insight"
    )
    badge_id = Column(
        String(50),
        nullable=True,
        doc="Badge ID if log_type is BADGE"
    )
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
        doc="When the action occurred"
    )

    # Relationship
    portfolio: Mapped["Portfolio"] = relationship(
        "Portfolio",
        foreign_keys=[portfolio_id]
    )

    def __repr__(self) -> str:
        return f"<InvestmentLog({self.log_type.value}, {self.ticker or 'N/A'}, {self.amount})>"
