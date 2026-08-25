"""
The buys the guard said no to.

`GomesGatekeeper.evaluate_buy_guard` returns `(False, reason)` and every caller
in the app throws the reason away. That is a real hole in the discipline: the
engine keeps a record of every position it opened and none of the ones it
refused to open, so "the rules protected the capital" can never be checked. It
is exactly the sample you need — a rule that only ever shows its successes is
indistinguishable from one that costs money.

What a row is
-------------
One refusal, with the state it was computed from. Reading it back a year later
answers a question nothing else in the app can: of the buys the guard blocked,
how many would have made money? If the answer is "most of them", the gate that
blocked them is mis-set and the owner should know.

The gate is stored as a CODE, not parsed back out of a sentence
---------------------------------------------------------------
`failed_gate` comes from `GomesGatekeeper.BuyGate`, so grouping refusals by
cause is a GROUP BY rather than a regex over prose. `reason` keeps the sentence
alongside it, because the code says which gate and the sentence says with what
numbers.

One row per ticker per day per gate
-----------------------------------
The daily action engine re-evaluates the same watchlist every run. Without the
uniqueness constraint a single unchanged refusal would write 365 rows a year
and drown the signal. A refusal that changes gate — market alert lifts and the
answer becomes "not cheap enough" — is new information and gets its own row.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)

from .base import Base


class RefusedBuy(Base):
    """One buy the Gomes Buy Guard refused, with the gate that refused it."""

    __tablename__ = "refused_buys"

    id = Column(Integer, primary_key=True)

    ticker = Column(String(20), nullable=False, index=True)

    #: Date part of `refused_at`, carried separately because the uniqueness
    #: rule is per calendar day and comparing a timestamptz to a day is not.
    refused_on = Column(Date, nullable=False, default=date.today)
    refused_at = Column(
        DateTime(timezone=True), nullable=False, default=func.now(), index=True
    )

    #: A `GomesGatekeeper.BuyGate` value. Never free text, never parsed back
    #: out of `reason`.
    failed_gate = Column(String(40), nullable=False)
    reason = Column(Text, nullable=True, doc="The sentence the guard produced, with its numbers")

    # ------------------------------------------------------------------
    # The state the refusal was computed from, so it can be re-checked rather
    # than trusted. NULL means the app did not know that value at the time —
    # which for `cylinders` is usually the very reason the buy was refused.
    # ------------------------------------------------------------------
    source_key = Column(String(30), nullable=True, doc="GOMES / BREAKOUT_INVESTORS / OTHER")
    price = Column(Numeric(12, 4), nullable=True)
    green_line = Column(Numeric(12, 4), nullable=True)
    red_line = Column(Numeric(12, 4), nullable=True)
    line_currency = Column(String(3), nullable=True)
    rr_score = Column(Numeric(6, 3), nullable=True)
    deserved_score = Column(Numeric(6, 3), nullable=True)
    cylinders = Column(Integer, nullable=True)
    lifecycle_phase = Column(String(20), nullable=True)
    market_alert = Column(String(10), nullable=True)

    __table_args__ = (
        UniqueConstraint("ticker", "refused_on", "failed_gate", name="uq_refused_buy_day"),
        Index("idx_refused_buys_ticker", "ticker", "refused_at"),
        Index("idx_refused_buys_gate", "failed_gate", "refused_at"),
    )

    def __repr__(self) -> str:
        return f"<RefusedBuy {self.ticker} {self.failed_gate} @ {self.refused_on}>"
