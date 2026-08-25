"""
State and history of reading riskrewardcharts.com.

The tracker is where the Green and Red Lines actually live — the two numbers
the whole decision engine is built on (GOMES_METHODOLOGY_CANON.md §4a). Until
now `tracker_sync.sync_tracker()` existed, was tested, and had no caller at
all, so those lines never reached the database and every band downstream was
computed against nothing.

Two tables, for two different reasons.

`TrackerPollState` — when we last looked
----------------------------------------
The canon says these lines are not real-time and change on the order of weeks.
Twice a day is already generous for such a source, and the limit is enforced
here rather than by the scheduler, so running the job by hand cannot hammer
somebody else's server. Written on every attempt, successful or not: a source
that is down must not be retried faster than one that is up.

`TrackerLineChange` — what moved, and whether it was reported
--------------------------------------------------------------
A moved line is the single most consequential event this app can observe. It
means the analyst revalued the company, and every score, every deserved
comparison, every 3-point trigger and every outstanding instruction was
computed against the old band until this moment. That deserves a record and one
message, which is what `notified_at` is for — it separates "we saw it" from
"the owner was told".

A pick flipping OFFICIAL <-> NOT OFFICIAL is bigger still: it means Gomes moved
real money in or out.
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    TIMESTAMP,
    func,
)

from .base import Base

#: The kinds `gomes_tracker.diff_tracker` can emit. Kept here so a change kind
#: that no reader understands cannot be written in the first place.
TRACKER_CHANGE_KINDS = ("NEW_PICK", "REMOVED", "LINE_MOVED", "PICK_TYPE")


class TrackerPollState(Base):
    """A single row (id = 1) recording when the tracker was last read."""

    __tablename__ = "tracker_poll_state"

    id = Column(Integer, primary_key=True)
    last_attempt_at = Column(TIMESTAMP(timezone=True), nullable=True)
    last_success_at = Column(TIMESTAMP(timezone=True), nullable=True)
    last_error = Column(String(300), nullable=True)
    picks_last_read = Column(Integer, nullable=True)

    def __repr__(self) -> str:
        return f"<TrackerPollState success={self.last_success_at}>"


class TrackerLineChange(Base):
    """One thing that moved on the tracker between two reads."""

    __tablename__ = "tracker_line_changes"

    id = Column(Integer, primary_key=True)
    ticker = Column(String(20), nullable=False, index=True)

    #: NEW_PICK | REMOVED | LINE_MOVED | PICK_TYPE
    kind = Column(String(20), nullable=False)

    #: The band or pick type on each side, as text. Text rather than numbers
    #: because a PICK_TYPE change moves between words and a LINE_MOVED between
    #: pairs — one column that holds both is more honest than four that are
    #: half empty.
    before_value = Column(String(60), nullable=True)
    after_value = Column(String(60), nullable=True)

    #: Ready-to-show Czech sentence, written once in `diff_tracker` so the
    #: mail and the screen say the same thing instead of two paraphrases.
    detail_cs = Column(Text, nullable=False)

    detected_at = Column(
        TIMESTAMP(timezone=True), nullable=False, default=func.now(), index=True
    )
    #: NULL until the owner was actually told. A failed send leaves it NULL so
    #: the next run picks it up again rather than losing the news silently.
    notified_at = Column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_tracker_changes_unnotified", "notified_at", "detected_at"),
    )

    def __repr__(self) -> str:
        return f"<TrackerLineChange {self.ticker} {self.kind}>"
