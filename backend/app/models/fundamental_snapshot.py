"""
Keeping the trailing figures instead of overwriting them.

The problem
-----------
`yahoo_finance_cache` holds one row per ticker and rewrites it on every
refresh. That is right for a cache and wrong for everything that wants to know
whether a company is getting better or worse: each read destroys the previous
one, so the app has never been able to see a trend in any company EDGAR cannot
reach — which is four of the five largest positions.

SEC gives quarterly series with real period boundaries and is the better source
by a wide margin. It simply does not cover the Canadian and OTC names. For
those, this table is the only way a year-on-year comparison will ever exist.

Why it is urgent rather than merely useful
------------------------------------------
The data is already being fetched. Nothing extra is downloaded, nothing costs
anything, and the only difference between having a series in 2027 and not
having one is whether these rows were being written from today. The same
"now or never" as the decision journal: history that was never recorded cannot
be reconstructed later.

What it is not
--------------
Not audited, not period-boundaried, and not comparable with a filing. These are
trailing-twelve-month aggregates a data provider assembled, and everything
built on them is labelled `YAHOO_TTM` and capped away from the ends of the
cylinder scale for exactly that reason.
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    func,
)

from .base import Base


class FundamentalSnapshot(Base):
    """One reading of a company's trailing figures, kept rather than replaced."""

    __tablename__ = "fundamental_snapshots"

    id = Column(Integer, primary_key=True)
    #: The symbol the provider answered under, not the canonical one: two
    #: listings can report different currencies and different share counts, and
    #: silently merging them would produce a trend out of a units change.
    ticker = Column(String(20), nullable=False, index=True)
    captured_at = Column(
        DateTime(timezone=True), nullable=False, default=func.now(), index=True
    )

    revenue_ttm = Column(Float, nullable=True)
    net_income_ttm = Column(Float, nullable=True)
    operating_margin = Column(Float, nullable=True)
    profit_margin = Column(Float, nullable=True)
    total_cash = Column(Float, nullable=True)
    total_debt = Column(Float, nullable=True)
    shares_outstanding = Column(Float, nullable=True)
    market_cap = Column(Float, nullable=True)
    currency = Column(String(8), nullable=True)

    # --- Balance sheet, for the downside floor ---------------------------
    # Everything above says how the business is doing; these say what would be
    # left if it stopped. Goodwill and intangibles are stored rather than
    # pre-subtracted so a reader can see how much was taken off — they are
    # deducted from the floor because they are the first entries written down
    # when a thesis breaks, and a floor that counts them is not a floor.
    stockholders_equity = Column(Float, nullable=True)
    goodwill = Column(Float, nullable=True)
    intangibles = Column(Float, nullable=True)

    #: Deduplication is by VALUE, not by day, and it happens in
    #: `record_snapshot`. The provider moves these numbers on the order of
    #: quarters, so a nightly job would otherwise write the same figures ninety
    #: times — and a series padded with repeats reads as stability that was
    #: never observed. A row here means something actually changed.
    __table_args__ = (Index("idx_snapshot_ticker_time", "ticker", "captured_at"),)

    def __repr__(self) -> str:
        return f"<FundamentalSnapshot {self.ticker} @ {self.captured_at}>"
