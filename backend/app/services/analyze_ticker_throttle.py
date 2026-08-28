"""
Cooldown predicate for POST /api/intelligence/analyze-ticker.

Mirrors `gomes_tracker.should_poll`: a pure, injectable-clock function kept
separate from the route so the interval logic is testable without a live LLM
call or a database session.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

#: Ten minutes between calls is what produced 143 calls/24h on one ticker
#: (IMPLEMENTATION_PLAN.md §29 point 4). Six hours sits comfortably above any
#: legitimate re-analysis cadence (a new video, a new filing) while still
#: being measured in hours, not minutes.
MIN_ANALYZE_INTERVAL = timedelta(hours=6)


def should_analyze(last_attempt_at: datetime | None, *, now: datetime | None = None) -> bool:
    """Whether enough time has passed to analyze this ticker again."""
    if last_attempt_at is None:
        return True
    current = now or datetime.now(timezone.utc)
    if last_attempt_at.tzinfo is None:
        last_attempt_at = last_attempt_at.replace(tzinfo=timezone.utc)
    return (current - last_attempt_at) >= MIN_ANALYZE_INTERVAL
