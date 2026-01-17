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
    Column,
    DateTime,
    Enum as SQLEnum,
    Float,
    ForeignKey,
    Integer,
    String,
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
        nullable=False,
        doc="Average purchase price per share"
    )
    currency = Column(
        String(3),
        nullable=False,
        default="USD",
        doc="Currency code (USD, EUR, HKD, etc.)"
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
    def cost_basis(self) -> float:
        """Total amount invested (shares * avg_cost)."""
        return self.shares_count * self.avg_cost

    @property
    def market_value(self) -> float:
        """Current market value (shares * current_price)."""
        if self.current_price is None:
            return 0.0
        return self.shares_count * self.current_price

    @property
    def unrealized_pl(self) -> float:
        """Unrealized profit/loss in currency."""
        if self.current_price is None:
            return 0.0
        return (self.current_price - self.avg_cost) * self.shares_count

    @property
    def unrealized_pl_percent(self) -> float:
        """Unrealized profit/loss as percentage."""
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

    def __repr__(self) -> str:
        return f"<MarketStatus(status={self.status.value})>"
