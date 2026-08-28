"""
POST /api/intelligence/analyze-ticker had no cooldown and was called 143
times in 24 hours on one ticker (IMPLEMENTATION_PLAN.md §29 point 4). These
tests cover the pure predicate that now gates it — mirrors
test_gomes_tracker.py's should_poll tests.
"""

from datetime import datetime, timedelta, timezone

from app.services.analyze_ticker_throttle import MIN_ANALYZE_INTERVAL, should_analyze

NOW = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)


def test_first_analysis_allowed():
    assert should_analyze(None, now=NOW) is True


def test_too_soon_refused():
    assert should_analyze(NOW - timedelta(minutes=10), now=NOW) is False


def test_after_six_hours_allowed():
    assert should_analyze(NOW - MIN_ANALYZE_INTERVAL - timedelta(minutes=1), now=NOW) is True


def test_naive_timestamp_treated_as_utc():
    naive_recent = (NOW - timedelta(minutes=5)).replace(tzinfo=None)
    assert should_analyze(naive_recent, now=NOW) is False
