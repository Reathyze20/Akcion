"""
Away-mode state.

One row. It holds whether away mode is on, the window it covers, and what was
last pushed — the last two columns are what make "at most one message a day"
survive a restart. A scheduler that forgets what it sent sends it again.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, func

from .base import Base


class AwayModeState(Base):
    """The single row describing whether nobody is reading the app."""

    __tablename__ = "away_mode_state"

    id = Column(Integer, primary_key=True, index=True)

    is_away = Column(Boolean, nullable=False, default=False)
    since = Column(
        DateTime(timezone=True),
        nullable=True,
        doc="When away mode started. NULL = on, but we do not know since when.",
    )
    until = Column(
        DateTime(timezone=True),
        nullable=True,
        doc=(
            "End of the window. NULL = open-ended. A window in the past turns "
            "away mode off by itself, so one set before a hospital stay cannot "
            "silence the app for a year."
        ),
    )
    reason = Column(String(255), nullable=True, doc="Why, for the UI")

    last_push_at = Column(
        DateTime(timezone=True),
        nullable=True,
        doc=(
            "When the last away-mode message went out. NULL = none yet, which "
            "is why the quiet period has to survive a restart: a scheduler "
            "that forgets what it sent sends it again."
        ),
    )
    last_push_urgency = Column(
        Integer,
        nullable=False,
        default=0,
        doc="Urgency of the last message — a new one must beat it to interrupt.",
    )
    last_push_subject = Column(String(255), nullable=True)
    last_digest_reason = Column(
        Text,
        nullable=True,
        doc="Why the last cycle did or did not send. Shown in the app.",
    )

    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
