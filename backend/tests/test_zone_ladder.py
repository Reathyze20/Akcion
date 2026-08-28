"""
The band, and the two prices at which it changes.

Why a ladder rather than a verdict
----------------------------------
A verdict tells the owner what is true today, which is only useful on a day he
opens the app. Two prices let him place an order once and stop looking — and
looking is precisely what he cannot reliably do. That is the whole point of
computing the boundaries: they come from the LINES, not from today's quote, so
a stale price cannot corrupt them.

Two axes, kept apart
--------------------
The BAND compares today's score with `10 − cylinders` (canon §4b): is this
cheap for its quality? The TRIGGERS compare today's score with the score at
ENTRY (canon §5): has it moved three points since it was bought? An earlier
draft of this plan used `deserved ± 3` as the band edges, which welded the two
rules into one and would have reported "sell" for a stock that is merely dearer
than it deserves.

Fixtures are the real picks from canon §8a, so a failure here is a drift from
the methodology and not just from last week's code.
"""

import pytest

from app.trading.gomes_logic import (
    THREE_POINTS,
    Band,
    RiskRewardCalculator,
    Trigger,
    ZoneLadder,
)

# Canon §8a, verified against the live tracker on 2026-07-25.
CXDO = dict(low=3.25, high=15.50)      # price 6.62 -> score 5.45
VTSI = dict(low=5.00, high=22.50)      # price 3.18 -> below the Green Line
AEHR = dict(low=8.00, high=60.00)      # price 76.32 -> above the Red Line


# ==============================================================================
# The inverse: from a score back to a price
# ==============================================================================

def test_the_boundary_price_round_trips_through_the_score():
    """
    `price_at_score` is `calculate_rr_score` run backwards. If the two ever
    disagree, the limit price the owner places at the broker is not the price
    the band actually changes at — and he would find out by being filled.
    """
    for target in (0.0, 2.5, 5.0, 7.5, 10.0):
        price = ZoneLadder.price_at_score(target, **CXDO)
        back = RiskRewardCalculator.calculate_rr_score(price, **CXDO)
        assert back == pytest.approx(target, abs=1e-6)


def test_the_ends_of_the_scale_are_the_lines_themselves():
    assert ZoneLadder.price_at_score(10, **CXDO) == pytest.approx(CXDO["low"])
    assert ZoneLadder.price_at_score(0, **CXDO) == pytest.approx(CXDO["high"])


def test_a_degenerate_band_yields_no_price():
    """Inverted or equal lines are bad data, not a price of zero."""
    assert ZoneLadder.price_at_score(5, low=15.5, high=3.25) is None
    assert ZoneLadder.price_at_score(5, low=3.25, high=3.25) is None
    assert ZoneLadder.price_at_score(5, low=0, high=15.5) is None


# ==============================================================================
# The band answers "cheap for its quality?"
# ==============================================================================

def test_the_same_price_lands_in_different_bands_at_different_quality():
    """
    The core of canon §4b, and the reason cylinders had to be unblocked first.
    CXDO at 6.62 scores 5.45 either way. On four cylinders it deserves 6.0 and
    is therefore dear; on seven it deserves 3.0 and is cheap. The price did not
    move — what it is worth did.
    """
    dear = ZoneLadder.read(6.62, cylinders=4, **CXDO)
    cheap = ZoneLadder.read(6.62, cylinders=7, **CXDO)

    assert dear.band is Band.PREPLACENO
    assert cheap.band is Band.NAKUP
    assert dear.rr_score == cheap.rr_score == pytest.approx(5.45, abs=0.01)


def test_a_better_company_deserves_a_higher_buy_limit():
    """
    Quality moves the whole ladder, not just the verdict. Seven cylinders may
    be bought up to 8.97 where four may only be bought up to 5.61.
    """
    dear = ZoneLadder.read(6.62, cylinders=4, **CXDO)
    cheap = ZoneLadder.read(6.62, cylinders=7, **CXDO)

    assert dear.buy_below == pytest.approx(5.61, abs=0.01)
    assert cheap.buy_below == pytest.approx(8.97, abs=0.01)
    assert cheap.buy_below > dear.buy_below


def test_the_boundaries_are_two_orders_he_can_actually_place():
    """
    The deliverable in one assertion: buy at or below one number, reduce at or
    above the other, and the band between them is where nothing happens.
    """
    r = ZoneLadder.read(6.62, cylinders=4, **CXDO)

    assert r.buy_below < r.sell_above          # a real corridor, not a point
    assert ZoneLadder.read(r.buy_below - 0.01, cylinders=4, **CXDO).band is Band.NAKUP
    assert ZoneLadder.read(r.sell_above + 0.01, cylinders=4, **CXDO).band is Band.PREPLACENO


def test_the_boundaries_do_not_move_when_the_quote_does():
    """
    Why the whole design rests on limit prices. The band edges come from the
    lines; a price three days stale still produces the right order.
    """
    fresh = ZoneLadder.read(6.62, cylinders=5, **CXDO)
    stale = ZoneLadder.read(4.10, cylinders=5, **CXDO)

    assert fresh.buy_below == pytest.approx(stale.buy_below)
    assert fresh.sell_above == pytest.approx(stale.sell_above)
    assert fresh.band is not stale.band        # only the verdict moved


def test_a_price_at_fair_value_holds():
    r = ZoneLadder.read(ZoneLadder.price_at_score(5.0, **CXDO), cylinders=5, **CXDO)
    assert r.band is Band.DRZET


# ==============================================================================
# The two ends are their own states
# ==============================================================================

def test_below_the_green_line_is_named_as_such():
    """
    VTSI at 3.18 against a 5.00 Green Line. "Cheaper than it deserves" is true
    but understates it: the analyst says undervalued outright.
    """
    r = ZoneLadder.read(3.18, cylinders=5, **VTSI)
    assert r.band is Band.POD_ZELENOU
    assert r.rr_score == 10.0
    assert "zelené čáře" in r.reason_cs


def test_above_the_red_line_is_named_as_such():
    """AEHR at 76.32 against a 60.00 Red Line — full valuation and past it."""
    r = ZoneLadder.read(76.32, cylinders=5, **AEHR)
    assert r.band is Band.NAD_CERVENOU
    assert r.rr_score == 0.0


def test_ten_cylinders_still_do_not_make_the_red_line_a_buy():
    """
    A company firing on all ten deserves the Red Line — it does not deserve
    more than it. Canon §4b: at 10 cylinders the deserved score is 0, which is
    the Red Line exactly, and above it there is nothing left to earn.
    """
    r = ZoneLadder.read(76.32, cylinders=10, **AEHR)
    assert r.band is Band.NAD_CERVENOU


# ==============================================================================
# Two absences, told apart
# ==============================================================================

def test_a_company_with_no_band_is_outside_the_method():
    r = ZoneLadder.read(6.62, None, None, 5)
    assert r.band is Band.MIMO_METODIKU
    assert r.is_tradeable is False
    assert r.buy_below is None                 # no price to act at


def test_a_band_without_cylinders_says_so_differently():
    """
    Not the same absence. The valuation is known and the quality is not, so the
    score is reported and the verdict withheld — buying on price alone is how
    the canon says you land in a Wait-Time value trap.
    """
    r = ZoneLadder.read(6.62, cylinders=None, **CXDO)
    assert r.band is Band.NEZNAME
    assert r.rr_score == pytest.approx(5.45, abs=0.01)
    assert r.deserved is None
    assert r.buy_below is None
    assert r.is_tradeable is False


def test_without_a_quote_the_band_is_unknown_but_the_limits_are_not():
    """
    A pleasing consequence of deriving the boundaries from the lines: with no
    usable quote the app cannot say where the stock sits today, and can still
    say what to pay for it. That is the order the owner places and forgets, and
    it survives the price feed being down.
    """
    r = ZoneLadder.read(None, cylinders=5, **CXDO)

    assert r.band is Band.NEZNAME
    assert r.rr_score is None
    assert "použitelná cena" in r.reason_cs
    assert r.buy_below is not None and r.sell_above is not None


# ==============================================================================
# The second axis: how far it has moved since entry
# ==============================================================================

def test_a_three_point_fall_since_entry_takes_profit():
    trigger, reason = ZoneLadder.trigger(current_score=4.5, entry_score=7.5)
    assert trigger is Trigger.VYBRAT_ZISK
    assert "3,0 bodu" in reason


def test_a_three_point_rise_since_entry_adds():
    trigger, _ = ZoneLadder.trigger(current_score=7.5, entry_score=4.5)
    assert trigger is Trigger.DOKOUPIT


def test_less_than_three_points_is_not_a_trigger():
    trigger, reason = ZoneLadder.trigger(current_score=6.9, entry_score=4.5)
    assert trigger is Trigger.ZADNY
    assert "nestačí" in reason


def test_an_unknown_entry_score_keeps_the_rule_silent():
    """
    Every position opened before the entry score started being recorded. Taking
    today's band as the starting point would date the move from a moment that
    never happened.
    """
    trigger, reason = ZoneLadder.trigger(current_score=7.5, entry_score=None)
    assert trigger is Trigger.ZADNY
    assert "vstupu neznám" in reason


def test_the_trigger_is_independent_of_the_band():
    """
    The mistake this separation prevents. A stock can sit firmly in NAKUP —
    cheap for its quality — and still have moved three points against the
    position since it was bought. Both facts are true and both matter.
    """
    reading = ZoneLadder.read(6.62, cylinders=8, entry_score=9.0, **CXDO)
    assert reading.band is Band.NAKUP

    trigger, _ = ZoneLadder.trigger(reading.rr_score, entry_score=9.0)
    assert trigger is Trigger.VYBRAT_ZISK


def test_the_trigger_prices_are_three_points_from_entry():
    """
    The canon's §5 arithmetic, expressed as prices rather than as a score
    difference the owner would have to compute himself.
    """
    entry = 7.0
    r = ZoneLadder.read(6.62, cylinders=5, entry_score=entry, **CXDO)

    at_take_profit = RiskRewardCalculator.calculate_rr_score(r.take_profit_above, **CXDO)
    at_add = RiskRewardCalculator.calculate_rr_score(r.add_below, **CXDO)

    assert at_take_profit == pytest.approx(entry - THREE_POINTS, abs=1e-6)
    assert at_add == pytest.approx(entry + THREE_POINTS, abs=1e-6)
    # Taking profit happens at a HIGHER price than adding does.
    assert r.take_profit_above > r.add_below


# ==============================================================================
# Three live defects, closed
# ==============================================================================

class TestNumbersThatWereNotNumbers:
    """
    Small fixes, each of the same family: a field that carried something other
    than what its name promised.
    """

    def test_the_price_position_is_a_percentage_not_a_sentence(self):
        """
        `/api/intelligence/ml-stocks` unpacked `get_action_zone`, which returns
        (zone, REASON), into `price_zone, price_position_pct`. The front end
        types that field as `number | null` and feeds it into `left: {x}%`. It
        never crashed only because nothing calls that endpoint yet — and Fáze 5
        proposes calling exactly it.
        """
        from app.services.gomes_intelligence import GomesIntelligenceService  # noqa: F401

        reading = ZoneLadder.read(6.62, 3.25, 15.50, None)
        position_pct = round((10.0 - reading.rr_score) * 10.0, 1)

        assert isinstance(position_pct, float)
        assert 0.0 <= position_pct <= 100.0
        # CXDO at 6.62 scores 5.45, so it sits a little under halfway up.
        assert position_pct == pytest.approx(45.5, abs=0.1)

    def test_the_ends_of_the_position_scale_are_the_lines(self):
        for price, expected in ((3.25, 0.0), (15.50, 100.0)):
            reading = ZoneLadder.read(price, 3.25, 15.50, None)
            assert round((10.0 - reading.rr_score) * 10.0, 1) == expected

    def test_a_missing_conviction_score_is_not_a_five(self):
        """
        `gomes_deep_dd` defaulted a missing score to 5 — a middling conviction
        nobody expressed, which then drove the target weight and the position
        tier. Silence is now silence.
        """
        from app.services.gomes_deep_dd import _optional_score

        assert _optional_score(None) is None
        assert _optional_score("") is None
        assert _optional_score(11) is None
        assert _optional_score(7) == 7
        assert _optional_score(0) == 0        # a real zero survives
