"""
Whose word counts, and for which source.

The problem
-----------
`normalize_source` decides `Stock.source_key`, and `source_key` is what
`evaluate_dual_source_buy` reads to decide whether two sources agree — which
sets the position cap at 15 %, 7 % or 5 %. It decided by keyword:

    if "gomes" in name:      GOMES
    if "breakout" in name:   BREAKOUT_INVESTORS
    otherwise:               OTHER

So an analyst writing under his own name landed in OTHER, and OTHER does not
enter the agreement matrix at all. Their analyses were stored and silently not
used.

The other half of the same problem sat in `claim_extraction.resolve_source_key`,
which mapped EVERY speaker in the WhatsApp group to BREAKOUT_INVESTORS. A group
of around a hundred and thirty people, and any one of them saying "TPCS to $14"
carried the same authority as the analysts who write the research.

Both are now answered here, in one place, by name.

Why an explicit list and not a rule
-----------------------------------
Same reasoning as `app/core/tickers.py` for dual listings: matching people by
resemblance is the kind of quiet mistake that costs money, and the cost of a
wrong match here is a position sized against somebody else's opinion. The list
is short, every row carries why the person is on it, and it can be checked by
eye.

Nobody is on it by default. A speaker who is not listed is stored with their
name intact and counts toward nothing — which is the right treatment for a
hundred and thirty strangers and is not a judgement about any of them.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    func,
)

from .base import Base


class RosterEntry(Base):
    """One person whose claims are attributed to a source rather than discarded."""

    __tablename__ = "analyst_roster"

    id = Column(Integer, primary_key=True)

    #: Lower-cased and stripped. Matching is exact on this: a display name is
    #: what WhatsApp gives us and what the owner recognises, and fuzzy matching
    #: a person is how one analyst's conviction ends up sized against another's.
    name_key = Column(String(120), nullable=False, unique=True, index=True)
    #: As written, for the screen.
    display_name = Column(String(120), nullable=False)

    #: GOMES | BREAKOUT_INVESTORS. Never OTHER — a roster row exists precisely
    #: to say this person is not "other".
    source_key = Column(String(30), nullable=False)

    #: Why they are on the list, in one sentence. A roster without reasons is
    #: one nobody can audit a year later.
    note = Column(Text, nullable=True)

    active = Column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        doc="Deactivated rather than deleted, so old claims keep their attribution.",
    )
    added_at = Column(
        DateTime(timezone=True), nullable=False,
        default=func.now(), server_default=func.now(),
    )

    __table_args__ = (Index("idx_roster_source", "source_key", "active"),)

    def __repr__(self) -> str:
        return f"<RosterEntry {self.display_name} -> {self.source_key}>"
