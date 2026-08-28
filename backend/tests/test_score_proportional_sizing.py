"""
Position size is a function of the R/R score. The tier is only the ceiling.

GOMES_VIDEO_ADDENDUM.md §V2, and Gomes states both ends of it with numbers:

    "Why would you put the same amount of money in a stock that's here as a
     stock that is way up here? When a stock is up here, I'm liable to own zero
     or 1% of it in my portfolio. When it's here, a 10 on the scale, I'm more
     liable to own 10% of that stock."

And he rejects the alternative outright: "a lot of people say, well, I'm just
going to put 10,000 in this stock, 10,000 in that stock -- that defeats the
purpose."

Until this existed, `TIER_LIMITS` handed out a flat `recommended_pct` per tier,
so a PRIMARY at a score of 5 was sized exactly like a PRIMARY at 10 and every
position in the portfolio was the wrong size.
"""

import pytest

from app.trading.gomes_logic import MarketAlert, PositionSizingEngine

TEN_PCT = 10.0  # a PRIMARY ceiling, which is where Gomes' own numbers land


# ==============================================================================
# His two stated numbers
# ==============================================================================

def test_a_ten_is_worth_the_whole_ceiling():
    assert PositionSizingEngine.target_pct(TEN_PCT, 10.0) == pytest.approx(10.0)


def test_a_one_is_worth_one_percent():
    assert PositionSizingEngine.target_pct(TEN_PCT, 1.0) == pytest.approx(1.0)


def test_the_dial_is_linear_between_them():
    assert PositionSizingEngine.target_pct(TEN_PCT, 5.0) == pytest.approx(5.0)
    assert PositionSizingEngine.target_pct(TEN_PCT, 7.5) == pytest.approx(7.5)


# ==============================================================================
# The ceiling is respected, and it scales the dial with it
# ==============================================================================

def test_a_tertiary_ceiling_scales_the_whole_range():
    """A speculative name at a perfect score still cannot exceed 2 %."""
    assert PositionSizingEngine.target_pct(2.0, 10.0) == pytest.approx(2.0)
    assert PositionSizingEngine.target_pct(2.0, 5.0) == pytest.approx(1.0)


def test_the_result_never_exceeds_the_ceiling():
    for score in (10.0, 11.0, 99.0):
        assert PositionSizingEngine.target_pct(7.0, score) <= 7.0


def test_a_zero_ceiling_stays_zero():
    """Every cap upstream — tier, asset class, dual source — still binds."""
    assert PositionSizingEngine.target_pct(0.0, 10.0) == 0.0


# ==============================================================================
# Missing and edge inputs
# ==============================================================================

def test_an_unknown_score_sizes_nothing():
    """
    Consistent with the Buy Guard: a missing input is a refusal, never a
    default. An unknown dial is not a full one.
    """
    assert PositionSizingEngine.target_pct(TEN_PCT, None) == 0.0


def test_a_score_below_zero_is_clamped_not_negative():
    assert PositionSizingEngine.target_pct(TEN_PCT, -3.0) == 0.0


# ==============================================================================
# The yellow clause, which is a different rule from the dial
# ==============================================================================

def test_a_fully_valued_name_outside_green_goes_to_zero_not_to_one_percent():
    """
    "Especially in a yellow alert -- zero. Why should I own a stock that's fully
     valued in a market that's likely to go down? There's no upside in that.
     High risk, low reward."
    """
    for alert in (MarketAlert.YELLOW, MarketAlert.ORANGE, MarketAlert.RED):
        assert PositionSizingEngine.target_pct(TEN_PCT, 1.0, market_alert=alert) == 0.0


def test_the_same_name_in_a_green_market_keeps_its_token_slice():
    assert PositionSizingEngine.target_pct(
        TEN_PCT, 1.0, market_alert=MarketAlert.GREEN
    ) == pytest.approx(1.0)


def test_a_cheap_name_is_untouched_by_the_yellow_clause():
    """The clause is about full valuation, not about caution in general."""
    assert PositionSizingEngine.target_pct(
        TEN_PCT, 9.0, market_alert=MarketAlert.YELLOW
    ) == pytest.approx(9.0)


def test_the_alert_may_be_a_plain_string():
    assert PositionSizingEngine.target_pct(TEN_PCT, 1.0, market_alert="yellow") == 0.0
