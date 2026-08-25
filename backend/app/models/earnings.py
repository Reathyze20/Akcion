"""
When each company next reports.

Why this table exists
---------------------
The canon's 14-day rule — do not be holding into a print you cannot predict —
has been fully implemented since the app was written and has never once fired.
`GomesGatekeeper.EARNINGS_DANGER_DAYS` is honoured by every code path that
receives an earnings date, and nothing ever supplied one:
`gomes_analyzer._get_earnings_date` returns `None` under a TODO, so
`investment_verdicts.days_to_earnings` is NULL on every row ever written.

A date the company confirmed and a date somebody guessed
--------------------------------------------------------
Yahoo answers with either a single day or a two-day window. A window means the
date is inferred from past cadence rather than announced, and the difference
matters enough to store: `confirmed` decides whether the app is blocking a
purchase on a fact or on an estimate, and the owner is told which.

The SEC fallback is weaker still and says so. A company that filed its last
quarter on a given date will file the next one about ninety days later, which
is true enough to be worth knowing and far too vague to present as a date.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    func,
)

from .base import Base

#: Where a date came from, in descending order of trust.
SOURCE_YAHOO = "YAHOO"          # announced or inferred by the data provider
SOURCE_SEC_CADENCE = "SEC_CADENCE"  # our own arithmetic on past filing dates


class EarningsDate(Base):
    """The next reporting date for one company, and how well it is known."""

    __tablename__ = "earnings_dates"

    id = Column(Integer, primary_key=True)
    #: Canonical symbol — one row per COMPANY, so a position held as KUYA.V
    #: finds the date filed under KUYAF.
    ticker = Column(String(20), nullable=False, unique=True, index=True)

    next_date = Column(Date, nullable=True, doc="The day, or the start of the window")
    #: Set only when the provider gave a range. A window is an inference from
    #: past cadence, not an announcement.
    window_end = Column(Date, nullable=True)
    confirmed = Column(
        Boolean,
        nullable=False,
        default=False,
        doc="True only for a single announced day. False = somebody's estimate.",
    )
    source = Column(String(20), nullable=False, default=SOURCE_YAHOO)

    fetched_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    #: Why there is no date, when there is none — an absence that names itself
    #: is one the owner can act on.
    note = Column(Text, nullable=True)

    __table_args__ = (Index("idx_earnings_next", "next_date"),)

    @property
    def is_estimate(self) -> bool:
        return not self.confirmed

    def days_until(self, today: date | None = None) -> int | None:
        if self.next_date is None:
            return None
        return (self.next_date - (today or datetime.utcnow().date())).days

    def __repr__(self) -> str:
        kind = "confirmed" if self.confirmed else "estimate"
        return f"<EarningsDate {self.ticker} {self.next_date} ({kind})>"
