"""
The owner's own instruction for one holding, independent of what the phase
or the Buy Guard would otherwise allow.

ECOR sits at GREAT_FIND (IMPLEMENTATION_PLAN.md §31) — the phase gate would
let a buy through — but it is queued for exit, waiting for enough market
interest to sell into, not for the thesis to fail. SMSI sits at WAIT_TIME,
already blocked by phase, but for the wrong reason: it is held only for a
tax-loss harvest, not because the business might recover, and that block
would silently lift the moment a future reading moves it off WAIT_TIME.

Neither reason belongs on `stock_lifecycle`: that table is versioned by each
new automated detection (`lifecycle_intake.confirm`), and an intent recorded
there risks being carried forward, overwritten, or misread as evidence the
rubric itself produced. This is its own small table for the same reason
`tracker_poll_state` is — one fact, set by a human, read by the gate.
"""

from __future__ import annotations

from sqlalchemy import Column, String, TIMESTAMP

from .base import Base


class OwnerIntentModel(Base):
    """One ticker's standing instruction. Absence means no override."""

    __tablename__ = "stock_owner_intent"

    ticker = Column(String(20), primary_key=True)
    #: EXIT_PENDING | TAX_LOSS_HOLD today; free text, not an app-level enum —
    #: both values mean the same thing to the gate (no new buy suggestions)
    #: and only the note explains why.
    intent = Column(String(30), nullable=False)
    note = Column(String(300), nullable=True)
    set_by = Column(String(100), nullable=False)
    set_at = Column(TIMESTAMP(timezone=True), nullable=False)

    def __repr__(self) -> str:
        return f"<OwnerIntentModel {self.ticker}={self.intent}>"
