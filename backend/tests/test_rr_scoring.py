"""
Risk/Reward scoring tests — Group A + B from EFFICIENT_INVESTING_PLAYBOOK.md.

Locks the LOGARITHMIC Gomes R/R score (canon §4a, verified against the live
riskrewardcharts.com tracker) and the cylinders-based buy/sell decision (§4b).
Fixtures use real tracker numbers (snapshot 2026-07-25), so these tests double
as a regression guard against silently reverting to the old (wrong) linear bands.
"""

from __future__ import annotations

import math

import pytest

from app.trading.gomes_logic import RiskRewardCalculator as R


# ---------------------------------------------------------------------------
# Group A — logarithmic score math (must be exact)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "label, price, low, high, top, expected",
    [
        ("A1 CXDO", 6.62, 3.25, 15.50, 0, 5.45),
        ("A2 GKPRF", 1.17, 0.30, 3.75, 0, 4.61),
        ("A3 VTSI below-green cap", 3.18, 5.00, 22.50, 0, 10.0),
        ("A4 AEHR above-red cap", 76.32, 8.00, 60.00, 0, 0.0),
        ("A5 [10,1] at high", 60.0, 8.0, 60.0, 1, 1.0),
    ],
)
def test_rr_score_values(label, price, low, high, top, expected):
    assert R.calculate_rr_score(price, low, high, top) == pytest.approx(expected, abs=0.01)


@pytest.mark.parametrize(
    "label, price, low, high",
    [
        ("A8 low==high degenerate", 5.0, 5.0, 5.0),
        ("high<low inverted", 5.0, 10.0, 3.0),
        ("negative price", -1.0, 3.0, 10.0),
        ("zero low", 5.0, 0.0, 10.0),
        ("missing price", None, 3.0, 10.0),
        ("missing high", 5.0, 3.0, None),
    ],
)
def test_rr_score_invalid_returns_none(label, price, low, high):
    """Fail safe: invalid inputs return None, never a fabricated number."""
    assert R.calculate_rr_score(price, low, high) is None


def test_rr_score_is_logarithmic_not_linear():
    """
    Regression guard: at CXDO's numbers the price sits at ~27.5% of the LINEAR
    range (old code -> BUY) but at log score 5.45 = ~mid (correct -> not BUY).
    """
    linear_pct = (6.62 - 3.25) / (15.50 - 3.25) * 100
    assert linear_pct < 30  # old linear code would have called this "near green"
    score = R.calculate_rr_score(6.62, 3.25, 15.50)
    assert 5.0 < score < 6.0  # log scale correctly places it mid-range


# ---------------------------------------------------------------------------
# Group B — buy/hold/sell decision vs deserved score (10 - cylinders)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "label, score, cylinders, expected_zone",
    [
        ("B1 cheap for quality", 8, 3, "BUY"),    # deserved 7, 8 > 7 -> BUY
        ("B2 pricey but strong co", 4, 8, "BUY"), # deserved 2, 4 > 2 -> BUY
        ("B3 expensive for quality", 3, 3, "SELL"),  # deserved 7, 3 < 7 -> SELL
        ("B4 at fair value", 7, 3, "HOLD"),       # deserved 7, within deadband
    ],
)
def test_decide_from_score(label, score, cylinders, expected_zone):
    assert R.decide_from_score(score, cylinders)[0] == expected_zone


def test_decide_unknown_cylinders_never_buys():
    """B5: without operational quality, refuse BUY (avoid Wait-Time value traps)."""
    zone, reason = R.decide_from_score(6.0, None)
    assert zone == "WATCH"
    assert "kvalita" in reason.lower()


def test_decide_none_score_is_unknown():
    assert R.decide_from_score(None, 5)[0] == "UNKNOWN"


def test_decide_from_prices_integration():
    """decide() ties price->score->cylinders together."""
    # CXDO score 5.45, weak company (2 cylinders -> deserves 8): too expensive -> SELL
    assert R.decide(6.62, 3.25, 15.50, cylinders=2)[0] == "SELL"
    # GKPRF score 4.61, strong company (9 cylinders -> deserves 1): cheap -> BUY
    assert R.decide(1.17, 0.30, 3.75, cylinders=9)[0] == "BUY"


# ---------------------------------------------------------------------------
# get_action_zone — price-only zone (neutral midpoint 5), corrected to log
# ---------------------------------------------------------------------------

def test_action_zone_extremes():
    assert R.get_action_zone(3.18, 5.00, 22.50)[0] == "BUY"   # below green, score 10
    assert R.get_action_zone(76.32, 8.00, 60.00)[0] == "SELL"  # above red, score 0


def test_action_zone_midrange_is_hold_not_buy():
    """CXDO (score 5.45) is fair-value HOLD; old linear code wrongly said BUY."""
    assert R.get_action_zone(6.62, 3.25, 15.50)[0] == "HOLD"


def test_action_zone_unknown_price():
    assert R.get_action_zone(None, 3.0, 10.0)[0] == "UNKNOWN"


# ---------------------------------------------------------------------------
# 3-point take-profit / add triggers (canon §5)
# ---------------------------------------------------------------------------

def test_three_point_up_drops_score_by_three():
    price, low, high = 1.17, 0.30, 3.75
    base = R.calculate_rr_score(price, low, high)
    up_price = R.three_point_up(price, low, high)
    at_up = R.calculate_rr_score(up_price, low, high)
    assert base - at_up == pytest.approx(3.0, abs=0.01)


def test_three_point_down_raises_score_by_three():
    price, low, high = 1.17, 0.30, 3.75
    base = R.calculate_rr_score(price, low, high)
    down_price = R.three_point_down(price, low, high)
    at_down = R.calculate_rr_score(down_price, low, high)
    assert at_down - base == pytest.approx(3.0, abs=0.01)


def test_three_point_invalid_returns_none():
    assert R.three_point_up(1.0, 5.0, 3.0) is None  # inverted lines
