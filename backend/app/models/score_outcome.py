"""
Score Outcome Model

What a journaled conviction score turned out to be worth, one row per horizon.

Written by `app/services/score_outcomes.py`. See
`migrations/add_score_outcomes.sql` for the two CHECK constraints that stop an
'evaluated' row existing without the prices it claims to be computed from.
"""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base


# ==============================================================================
# Statuses
# ==============================================================================

#: Both prices are real and the return below is measured.
STATUS_EVALUATED = "evaluated"

#: The horizon has not elapsed yet. The overwhelming majority of rows for the
#: first year, and not a failure — the journal only opened on 2026-08-23.
STATUS_PENDING = "pending"

#: The horizon passed but the measurement cannot be made. `unable_reason`
#: always says which gap: no baseline, no forward bar, a zero baseline price.
STATUS_UNABLE = "unable"


class ScoreOutcome(Base):
    """One conviction score, measured at one horizon."""

    __tablename__ = "score_outcomes"

    id = Column(Integer, primary_key=True)
    history_id = Column(
        Integer,
        ForeignKey("conviction_score_history.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    horizon_days = Column(Integer, nullable=False)

    eval_status = Column(String(20), nullable=False)
    unable_reason = Column(String(50), nullable=True)

    baseline_price = Column(Numeric(12, 4), nullable=True)
    baseline_source = Column(
        String(30),
        nullable=True,
        doc="'journal' or 'close_on_record_date'",
    )

    end_price = Column(Numeric(12, 4), nullable=True)
    end_date = Column(Date, nullable=True)

    return_pct = Column(Numeric(10, 4), nullable=True)
    benchmark_return_pct = Column(
        Numeric(10, 4),
        nullable=True,
        doc="^GSPC over the same window; NULL when the index could not be read",
    )
    excess_return_pct = Column(
        Numeric(10, 4),
        nullable=True,
        doc="return_pct - benchmark_return_pct; the headline metric",
    )

    evaluated_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    history = relationship("ConvictionScoreHistory", foreign_keys=[history_id])

    __table_args__ = (
        UniqueConstraint("history_id", "horizon_days", name="uq_score_outcome_horizon"),
        CheckConstraint(
            "eval_status IN ('evaluated', 'pending', 'unable')",
            name="check_outcome_status",
        ),
        CheckConstraint(
            "eval_status <> 'evaluated' OR (baseline_price IS NOT NULL "
            "AND end_price IS NOT NULL AND return_pct IS NOT NULL)",
            name="evaluated_has_its_numbers",
        ),
        CheckConstraint(
            "eval_status <> 'unable' OR unable_reason IS NOT NULL",
            name="unable_names_its_reason",
        ),
        Index("idx_score_outcomes_horizon", "horizon_days", "eval_status"),
    )

    def __repr__(self) -> str:
        return (
            f"<ScoreOutcome history={self.history_id} "
            f"{self.horizon_days}d {self.eval_status}>"
        )
