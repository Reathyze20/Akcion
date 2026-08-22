"""
Breakout Investors watchlist parsing, change detection and poll throttling.

No network here — the pure functions carry the rules that matter. Fixtures use
the real payload shape captured from /api/stocks on 2026-08-22.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.breakout_watchlist import (
    WatchlistEntry,
    WatchlistUnavailable,
    diff_watchlist,
    parse_watchlist,
    should_poll,
)

# Real shape, real numbers, from /api/stocks.
RAW = [
    {
        "id": "173e290f",
        "symbol": "CXDO",
        "companyName": "Crexendo, Inc.",
        "endorsements": 3,
        "upside": 0.6209150326797386,
        "created_at": "2026-03-20T13:53:09.385925+00:00",
    },
    {
        "id": "5b309c5e",
        "symbol": "AEHR",
        "companyName": "Aehr Test Systems, Inc.",
        "endorsements": 5,
        "upside": 0.06403940886699508,
        "created_at": "2025-12-28T17:19:32.427643+00:00",
    },
]


def entry(symbol: str, endorsements: int, upside: float | None) -> WatchlistEntry:
    return WatchlistEntry(
        symbol=symbol,
        company_name=symbol,
        endorsements=endorsements,
        upside_ratio=upside,
        added_at=None,
    )


# ==============================================================================
# Parsing
# ==============================================================================

def test_parses_the_real_payload_shape():
    entries = parse_watchlist(RAW)
    assert [e.symbol for e in entries] == ["CXDO", "AEHR"]
    cxdo = entries[0]
    assert cxdo.company_name == "Crexendo, Inc."
    assert cxdo.endorsements == 3
    assert cxdo.upside_ratio == pytest.approx(0.6209, rel=1e-3)
    assert cxdo.added_at == datetime(2026, 3, 20, 13, 53, 9, 385925, tzinfo=timezone.utc)


def test_upside_is_a_ratio_exposed_as_a_percentage():
    """0.62 means +62%. Getting this backwards would misprice every decision."""
    entries = parse_watchlist(RAW)
    assert entries[0].upside_pct == pytest.approx(62.09, rel=1e-3)
    assert entries[1].upside_pct == pytest.approx(6.40, rel=1e-3)


def test_rows_without_a_symbol_are_dropped_not_guessed():
    entries = parse_watchlist([{"companyName": "Mystery Co", "endorsements": 4}])
    assert entries == []


def test_unparseable_numbers_do_not_become_zero():
    """A missing upside is unknown, and unknown must not read as 'no upside'."""
    entries = parse_watchlist([{"symbol": "XYZ", "upside": "not a number"}])
    assert entries[0].upside_ratio is None
    assert entries[0].upside_pct is None


def test_wrong_shape_raises_rather_than_returning_empty():
    """An unreachable source and an empty watchlist must stay distinguishable."""
    with pytest.raises(WatchlistUnavailable):
        parse_watchlist({"data": []})


def test_company_name_is_length_capped():
    entries = parse_watchlist([{"symbol": "AAA", "companyName": "x" * 5000}])
    assert len(entries[0].company_name) <= 200


# ==============================================================================
# Change detection — the reason to poll
# ==============================================================================

def test_new_name_on_the_watchlist_is_reported():
    changes = diff_watchlist([], [entry("IDN", 3, 1.15)])
    assert len(changes) == 1
    assert changes[0].kind == "ADDED"
    assert "IDN" in changes[0].detail
    assert "+115" in changes[0].detail


def test_removed_name_is_reported():
    changes = diff_watchlist([entry("IDN", 3, 1.15)], [])
    assert changes[0].kind == "REMOVED"


def test_rising_conviction_is_reported_with_direction():
    changes = diff_watchlist([entry("CXDO", 3, 0.62)], [entry("CXDO", 5, 0.62)])
    endorsement = next(c for c in changes if c.kind == "ENDORSEMENTS")
    assert endorsement.before == 3 and endorsement.after == 5
    assert "vzrostla" in endorsement.detail


def test_falling_conviction_is_reported_too():
    """Losing backers is at least as important as gaining them."""
    changes = diff_watchlist([entry("CXDO", 5, 0.62)], [entry("CXDO", 2, 0.62)])
    endorsement = next(c for c in changes if c.kind == "ENDORSEMENTS")
    assert "klesla" in endorsement.detail


def test_daily_price_noise_does_not_raise_an_alert():
    """
    `upside` moves with the price every single day. Firing on every wiggle
    trains the owner to ignore the alerts, which is worse than no alerts.
    """
    changes = diff_watchlist([entry("CXDO", 3, 0.6209)], [entry("CXDO", 3, 0.6255)])
    assert changes == []


def test_meaningful_upside_move_is_reported():
    changes = diff_watchlist([entry("CXDO", 3, 0.62)], [entry("CXDO", 3, 0.95)])
    upside = next(c for c in changes if c.kind == "UPSIDE")
    assert "+62" in upside.detail and "+95" in upside.detail


def test_unchanged_watchlist_produces_nothing():
    same = [entry("CXDO", 3, 0.62), entry("AEHR", 5, 0.064)]
    assert diff_watchlist(same, same) == []


def test_unknown_upside_never_fabricates_a_change():
    changes = diff_watchlist([entry("XYZ", 1, None)], [entry("XYZ", 1, 0.5)])
    assert not any(c.kind == "UPSIDE" for c in changes)


# ==============================================================================
# Poll throttling — enforced, not just documented
# ==============================================================================

NOW = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)


def test_first_ever_poll_is_allowed():
    assert should_poll(None, now=NOW) is True


def test_polling_again_too_soon_is_refused():
    """A tight loop against someone else's endpoint is how it gets closed."""
    assert should_poll(NOW - timedelta(hours=2), now=NOW) is False


def test_polling_after_a_day_is_allowed():
    assert should_poll(NOW - timedelta(hours=25), now=NOW) is True


def test_naive_timestamp_is_treated_as_utc_not_rejected():
    assert should_poll(datetime(2026, 8, 20, 12, 0), now=NOW) is True
