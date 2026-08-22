"""
riskrewardcharts.com tracker parsing, scoring and change detection.

Fixtures are the real payload shape and real numbers captured from
/api/tickers on 2026-08-22. The scoring assertions double as a regression
test on the canon formula: the tracker publishes its own formula on the page,
so the app and the source must agree to the decimal.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.gomes_tracker import (
    NOT_OFFICIAL,
    OFFICIAL,
    TrackerPick,
    TrackerUnavailable,
    diff_tracker,
    parse_tracker,
    should_poll,
)

RAW = {
    "items": [
        {
            "ticker": "CXDO", "low": 3.25, "high": 15.5, "pickType": "OFFICIAL",
            "price": 6.39,
            "chartUrl": "https://riskreward.z13.web.core.windows.net/charts/CXDO.PNG",
        },
        {
            "ticker": "AEHR", "low": 8, "high": 60, "pickType": "NOT OFFICIAL",
            "price": 101.73, "chartUrl": None,
        },
    ],
    "cached": True,
}


def pick(ticker: str, low, high, pick_type, price=None) -> TrackerPick:
    return TrackerPick(
        ticker=ticker, low=low, high=high, pick_type=pick_type, price=price
    )


# ==============================================================================
# Parsing
# ==============================================================================

def test_parses_the_real_payload():
    picks = parse_tracker(RAW)
    assert [p.ticker for p in picks] == ["CXDO", "AEHR"]
    cxdo = picks[0]
    assert (cxdo.low, cxdo.high, cxdo.price) == (3.25, 15.5, 6.39)
    assert cxdo.is_official is True
    assert picks[1].is_official is False


def test_official_flag_is_the_portfolio_watchlist_split():
    """Canon §8a: OFFICIAL maps to the portfolio, NOT OFFICIAL to the watchlist."""
    picks = parse_tracker(RAW)
    assert picks[0].pick_type == OFFICIAL
    assert picks[1].pick_type == NOT_OFFICIAL


def test_unknown_pick_type_becomes_none_not_watchlist():
    """
    Defaulting an unrecognised classification to 'watchlist' would hide a
    real portfolio position — the one direction that costs money.
    """
    picks = parse_tracker({"items": [{"ticker": "X", "pickType": "SOMETHING_NEW"}]})
    assert picks[0].pick_type is None
    assert picks[0].is_official is False


def test_zero_price_is_missing_data_not_a_price():
    picks = parse_tracker({"items": [{"ticker": "X", "low": 1, "high": 2, "price": 0}]})
    assert picks[0].price is None


def test_wrong_shape_raises():
    with pytest.raises(TrackerUnavailable):
        parse_tracker([{"ticker": "CXDO"}])


def test_rows_without_a_ticker_are_skipped():
    assert parse_tracker({"items": [{"low": 1, "high": 2}]}) == []


# ==============================================================================
# Scoring — must match the formula the tracker itself publishes
# ==============================================================================

def test_score_matches_the_canon_worked_example():
    """
    Canon §4a cites CXDO 3.25/15.50 @ 6.62 -> 5.45. Same formula, same numbers.
        score = 10 * log(high/price) / log(high/low)
    """
    assert pick("CXDO", 3.25, 15.5, OFFICIAL, 6.62).rr_score == pytest.approx(5.45, abs=0.01)


def test_price_at_the_green_line_scores_ten():
    assert pick("X", 3.25, 15.5, OFFICIAL, 3.25).rr_score == pytest.approx(10.0)


def test_price_at_the_red_line_scores_zero():
    assert pick("X", 3.25, 15.5, OFFICIAL, 15.5).rr_score == pytest.approx(0.0)


def test_price_far_above_the_red_line_is_clamped_to_zero():
    """AEHR at 101.73 against a 60 ceiling — deep in sell territory, never negative."""
    assert pick("AEHR", 8, 60, NOT_OFFICIAL, 101.73).rr_score == pytest.approx(0.0)


def test_missing_price_yields_no_score_rather_than_a_guess():
    assert pick("X", 3.25, 15.5, OFFICIAL, None).rr_score is None


def test_missing_lines_yield_no_score():
    assert pick("X", None, None, OFFICIAL, 5.0).rr_score is None


# ==============================================================================
# Change detection
# ==============================================================================

def test_promotion_to_official_is_reported_as_money_moving():
    changes = diff_tracker(
        [pick("IDN", 2, 25, NOT_OFFICIAL)], [pick("IDN", 2, 25, OFFICIAL)]
    )
    change = next(c for c in changes if c.kind == "PICK_TYPE")
    assert "povýšen na OFFICIAL" in change.detail


def test_demotion_from_official_is_reported():
    changes = diff_tracker(
        [pick("IDN", 2, 25, OFFICIAL)], [pick("IDN", 2, 25, NOT_OFFICIAL)]
    )
    change = next(c for c in changes if c.kind == "PICK_TYPE")
    assert "sesazen z OFFICIAL" in change.detail


def test_moved_band_is_reported_because_every_prior_score_used_the_old_one():
    changes = diff_tracker(
        [pick("CXDO", 3.25, 15.5, OFFICIAL)], [pick("CXDO", 4.0, 18.0, OFFICIAL)]
    )
    change = next(c for c in changes if c.kind == "LINE_MOVED")
    assert "přeceněno" in change.detail
    assert change.before == "3.25–15.5" and change.after == "4.0–18.0"


def test_new_pick_is_reported():
    changes = diff_tracker([], [pick("VTSI", 5, 22.5, OFFICIAL)])
    assert changes[0].kind == "NEW_PICK"


def test_removed_pick_is_reported():
    changes = diff_tracker([pick("VTSI", 5, 22.5, OFFICIAL)], [])
    assert changes[0].kind == "REMOVED"


def test_price_movement_alone_raises_nothing():
    """
    Price moves every day and is read live elsewhere. Alerting on it would
    bury the changes that actually mean the analyst changed his mind.
    """
    changes = diff_tracker(
        [pick("CXDO", 3.25, 15.5, OFFICIAL, 6.39)],
        [pick("CXDO", 3.25, 15.5, OFFICIAL, 7.80)],
    )
    assert changes == []


def test_identical_reads_produce_nothing():
    same = [pick("CXDO", 3.25, 15.5, OFFICIAL, 6.39), pick("AEHR", 8, 60, NOT_OFFICIAL)]
    assert diff_tracker(same, same) == []


# ==============================================================================
# Poll throttling
# ==============================================================================

NOW = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)


def test_first_poll_allowed():
    assert should_poll(None, now=NOW) is True


def test_too_soon_refused():
    assert should_poll(NOW - timedelta(hours=3), now=NOW) is False


def test_after_twelve_hours_allowed():
    assert should_poll(NOW - timedelta(hours=13), now=NOW) is True
