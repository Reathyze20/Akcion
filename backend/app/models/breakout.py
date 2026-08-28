"""
Breakout Investors watchlist — what the second source publishes, stored.

Three tables, and the split matters:

  breakout_watchlist          the current snapshot, one row per symbol
  breakout_watchlist_changes  what moved between two reads, append-only
  breakout_poll_state         when the source was last reached, and whether

The changes table exists because the owner does not need a daily list of
twenty-eight names. He needs to know when one of them changed — a ticker
appeared, conviction moved, the target jumped. That is the only thing worth a
notification, and it cannot be reconstructed from a snapshot that overwrites
itself.

`breakout_poll_state` is separate from both so that a FAILED read is still a
record. Deriving "last polled" from the newest snapshot row would make an
unreachable source look identical to an unchanged one, and the app would
retry in a loop against someone else's server.

Nothing here is an instruction to the app. The user's decision (2026-08-23)
was that this source is shown, not obeyed: no column in these tables feeds
`evaluate_dual_source_buy`, and the position caps stay where the Gomes side
puts them. See `app/services/breakout_sync.py`.
"""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.sql import func

from .base import Base


#: Kinds of movement recorded in `breakout_watchlist_changes`. Mirrors
#: `WatchlistChange.kind` in app/services/breakout_watchlist.py.
CHANGE_KINDS = ("ADDED", "REMOVED", "ENDORSEMENTS", "UPSIDE")


class BreakoutWatchEntry(Base):
    """One name on the Breakout Investors watchlist, as last read."""

    __tablename__ = "breakout_watchlist"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), nullable=False, unique=True, index=True)
    company_name = Column(String(200), nullable=True)

    endorsements = Column(
        Integer,
        nullable=False,
        default=0,
        doc="How many members back the name — the group's conviction count",
    )
    upside_ratio = Column(
        Numeric(12, 6),
        nullable=True,
        doc="Expected gain as a ratio: 0.62 means +62 %. Stored as published.",
    )

    price_at_read = Column(
        Numeric(12, 4),
        nullable=True,
        doc="Their quote at the moment upside was read. The target's other half.",
    )
    implied_target = Column(
        Numeric(12, 4),
        nullable=True,
        doc=(
            "price_at_read * (1 + upside_ratio) — the group's target price, "
            "reconstructed. NULL whenever either input is missing; never guessed."
        ),
    )

    # The first reading, written once and never again. `price_at_read` and
    # `implied_target` above are the LATEST poll and are overwritten every
    # time; without these two the starting line the clock runs from is lost on
    # the second poll, and their one falsifiable prediction becomes unscorable.
    price_at_first_seen = Column(
        Numeric(12, 4),
        nullable=True,
        doc="Price at the first read. Written on insert only — the starting line.",
    )
    target_at_first_seen = Column(
        Numeric(12, 4),
        nullable=True,
        doc="Their reconstructed target at the first read. Never overwritten.",
    )

    added_at = Column(
        TIMESTAMP(timezone=True),
        nullable=True,
        doc="created_at as the source states it — when THEY added the name",
    )
    first_seen_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        doc="When WE first saw it. Differs from added_at for everything "
        "already on the list at the first poll.",
    )
    last_seen_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "implied_target IS NULL "
            "OR (price_at_read IS NOT NULL AND upside_ratio IS NOT NULL)",
            name="target_has_its_inputs",
        ),
        CheckConstraint(
            "target_at_first_seen IS NULL OR price_at_first_seen IS NOT NULL",
            name="first_target_has_its_price",
        ),
        CheckConstraint(
            "price_at_first_seen IS NULL OR price_at_first_seen > 0",
            name="first_price_is_a_price",
        ),
        CheckConstraint(
            "price_at_read IS NULL OR price_at_read > 0",
            name="price_at_read_is_a_price",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<BreakoutWatchEntry {self.symbol} "
            f"{self.endorsements} endorsements>"
        )


class BreakoutWatchChange(Base):
    """Something that moved between two reads. Append-only."""

    __tablename__ = "breakout_watchlist_changes"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), nullable=False, index=True)
    kind = Column(String(20), nullable=False)

    #: Numeric so an endorsement count and an upside ratio share a column.
    #: NULL on ADDED (`before`) and REMOVED (`after`) — the absence is the fact.
    before_value = Column(Numeric(12, 6), nullable=True)
    after_value = Column(Numeric(12, 6), nullable=True)

    detail_cs = Column(Text, nullable=False, doc="Ready-to-show Czech sentence")

    detected_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    notified_at = Column(
        TIMESTAMP(timezone=True),
        nullable=True,
        doc="When this change went out in a message. NULL = not sent yet.",
    )

    __table_args__ = (
        CheckConstraint(
            "kind IN ('ADDED', 'REMOVED', 'ENDORSEMENTS', 'UPSIDE')",
            name="check_breakout_change_kind",
        ),
        Index("idx_breakout_changes_unsent", "notified_at", "detected_at"),
    )

    def __repr__(self) -> str:
        return f"<BreakoutWatchChange {self.symbol} {self.kind}>"


class BreakoutPollState(Base):
    """
    A single row (id = 1) recording when the source was last reached.

    Written on every attempt, successful or not. `should_poll` in
    app/services/breakout_watchlist.py reads `last_attempt_at`, not
    `last_success_at`: a source that is down must not be retried faster than
    one that is up.
    """

    __tablename__ = "breakout_poll_state"

    id = Column(Integer, primary_key=True)
    last_attempt_at = Column(TIMESTAMP(timezone=True), nullable=True)
    last_success_at = Column(TIMESTAMP(timezone=True), nullable=True)
    last_error = Column(String(300), nullable=True)
    entries_last_read = Column(Integer, nullable=True)

    def __repr__(self) -> str:
        return f"<BreakoutPollState success={self.last_success_at}>"
