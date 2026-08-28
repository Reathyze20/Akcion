"""
Throttle state for POST /api/intelligence/analyze-ticker.

The route re-runs a full LLM pass on every call and had no cooldown of its
own. IMPLEMENTATION_PLAN.md §29 point 4: on 2026-08-24 something outside this
app called it 143 times in 24 hours on KUYA.V — about once every ten minutes,
each time getting back "no new intelligence, keeping existing thesis" from the
LLM. One row per ticker here means a second call inside the cooldown is
refused before it ever reaches the LLM, regardless of what is calling it.
"""

from __future__ import annotations

from sqlalchemy import Column, String, TIMESTAMP

from .base import Base


class AnalyzeTickerState(Base):
    """Per-ticker cooldown state. Written on every attempt, successful or not."""

    __tablename__ = "analyze_ticker_state"

    ticker = Column(String(20), primary_key=True)
    last_attempt_at = Column(TIMESTAMP(timezone=True), nullable=True)
    last_success_at = Column(TIMESTAMP(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<AnalyzeTickerState {self.ticker} attempt={self.last_attempt_at}>"
