"""
Which of the canon's three stages a holding is in, proposed from dated facts.

Why this had to exist
---------------------
On 2026-08-24 all twelve holdings carried `phase = UNKNOWN`, which capped every
one of them at the strictest tier and left the de-risking branch unable to sell
anything at all in a yellow market. Safe, and blind.

What is tested hardest is the refusal. A phase decides whether a position gets
SOLD, so the failure that costs money is a confident stage read off numbers
nobody checked — and the fix is the same one the cylinder rubric uses: too few
hard readings means no proposal, a tie means no proposal, and nothing the rubric
produces authorises anything until a person agrees to it.
"""

from datetime import date

import pytest

from app.services.lifecycle_rubric import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    DEEP_RETRACE_PCT,
    GOLD_MINE,
    GREAT_FIND,
    LAYER_NONE,
    LAYER_XBRL,
    LAYER_YAHOO,
    MIN_HARD_READINGS,
    PHASE_MEANING_CS,
    PHASE_NAMES_CS,
    WAIT_TIME,
    LifecycleInputs,
    propose_phase,
)

AS_OF = date(2026, 6, 30)


def given(**kw):
    base = dict(ticker="X", layer=LAYER_XBRL, as_of=AS_OF)
    base.update(kw)
    return propose_phase(LifecycleInputs(**base))


# ==============================================================================
# The three stages, as the canon describes them
# ==============================================================================

def test_profitable_and_growing_and_not_retraced_is_a_gold_mine():
    """§3: "momentum nastartoval, firma profituje"."""
    p = given(
        revenue_yoy_pct=28.0, operating_cash_flow=1_000_000.0,
        margin_move_pp=4.0, high_water=10.0, current_price=9.0,
    )
    assert p.phase == GOLD_MINE
    assert p.confidence == CONFIDENCE_HIGH


def test_falling_revenue_and_a_deep_retrace_is_wait_time():
    """§3: "hype umřel, story ještě nechytla trakci"."""
    p = given(
        revenue_yoy_pct=-12.0, operating_cash_flow=-500_000.0,
        high_water=10.0, current_price=4.0,
    )
    assert p.phase == WAIT_TIME


def test_early_signs_without_profit_is_a_great_find():
    """Revenue moving but the business does not yet make money."""
    p = given(
        revenue_yoy_pct=6.0, operating_cash_flow=-200_000.0,
        high_water=10.0, current_price=9.5,
    )
    assert p.phase == GREAT_FIND


def test_a_great_find_never_reaches_high_confidence():
    """
    Half the definition is that nobody has heard of the company. This app
    measures no such thing, so it says so instead of pretending otherwise.
    """
    p = given(
        revenue_yoy_pct=6.0, operating_cash_flow=-200_000.0,
        high_water=10.0, current_price=9.5,
    )
    assert p.confidence == CONFIDENCE_LOW
    assert any("pozornost trhu" in u for u in p.unknowns)


# ==============================================================================
# What it refuses to do
# ==============================================================================

def test_too_few_hard_readings_produces_no_proposal():
    """
    The rule the cylinder rubric established. A phase drives selling; one
    number is not enough to sell a position on.
    """
    p = given(layer=LAYER_NONE)
    assert p.phase is None
    assert p.hard_readings < MIN_HARD_READINGS
    assert any("tvrd" in u for u in p.unknowns)


def test_a_tie_between_two_stages_produces_no_proposal():
    """
    Two stages arguing equally means the numbers do not tell them apart, and
    picking one would be a coin toss that sells a position.
    """
    p = given(revenue_yoy_pct=28.0, high_water=10.0, current_price=4.0)
    assert p.phase is None
    assert any("neshodnou" in u for u in p.unknowns)


def test_an_analyst_alone_never_produces_a_proposal():
    """
    Somebody saying a thing is not the company reporting it. An analyst's view
    is one voice beside the filings and carries no weight towards the minimum.
    """
    p = given(
        layer=LAYER_NONE, analyst_says=GOLD_MINE,
        analyst_name="Robert Mock", analyst_on=date(2026, 8, 24),
    )
    assert p.phase is None
    assert p.hard_readings == 0


def test_an_analyst_is_recorded_when_the_filings_already_speak():
    p = given(
        revenue_yoy_pct=28.0, operating_cash_flow=1_000_000.0,
        high_water=10.0, current_price=9.0,
        analyst_says=GOLD_MINE, analyst_name="Robert Mock",
        analyst_on=date(2026, 8, 24),
    )
    assert any("Robert Mock" in s.fact_cs for s in p.signals)


def test_nothing_pointing_anywhere_produces_no_proposal():
    p = given(revenue_yoy_pct=None, operating_cash_flow=None,
              high_water=None, current_price=None)
    assert p.phase is None


# ==============================================================================
# Momentum that runs out of money is not momentum
# ==============================================================================

def test_a_tight_runway_argues_against_a_gold_mine():
    strong = given(
        revenue_yoy_pct=28.0, operating_cash_flow=1_000_000.0,
        high_water=10.0, current_price=9.0,
    )
    starved = given(
        revenue_yoy_pct=28.0, operating_cash_flow=1_000_000.0,
        high_water=10.0, current_price=9.0, runway_months=5.0,
    )
    assert starved.score_for(WAIT_TIME) > strong.score_for(WAIT_TIME)


def test_comfortable_cash_says_nothing_either_way():
    p = given(revenue_yoy_pct=28.0, operating_cash_flow=1_000_000.0,
              high_water=10.0, current_price=9.0, runway_months=30.0)
    assert not any("hotovost" in s.fact_cs for s in p.signals)


# ==============================================================================
# The retrace, which is the observable half of Wait Time
# ==============================================================================

def test_a_deep_retrace_is_measured_against_the_positions_own_high():
    p = given(revenue_yoy_pct=0.0, operating_cash_flow=-1.0,
              high_water=10.0, current_price=10.0 * (1 - DEEP_RETRACE_PCT / 100) - 0.01)
    assert any(s.towards == WAIT_TIME and "pod maximem" in s.fact_cs
               for s in p.signals)


def test_no_high_water_mark_is_a_named_gap_not_a_fall_of_zero():
    p = given(revenue_yoy_pct=28.0, operating_cash_flow=1_000_000.0)
    assert any("maximum pozice neznám" in u for u in p.unknowns)


# ==============================================================================
# Where the numbers came from is always said
# ==============================================================================

def test_annual_aggregates_cap_the_confidence():
    """Same reason the cylinder rubric caps them: not a series, not audited."""
    p = given(
        layer=LAYER_YAHOO, revenue_yoy_pct=28.0,
        operating_cash_flow=1_000_000.0, high_water=10.0, current_price=9.0,
    )
    assert p.confidence == CONFIDENCE_MEDIUM
    assert any("ročních souhrnů" in u for u in p.unknowns)


def test_every_signal_carries_a_source():
    p = given(revenue_yoy_pct=28.0, operating_cash_flow=1_000_000.0,
              high_water=10.0, current_price=9.0)
    assert all(s.source for s in p.signals)


def test_every_signal_is_a_czech_sentence():
    p = given(revenue_yoy_pct=28.0, operating_cash_flow=1_000_000.0,
              high_water=10.0, current_price=9.0)
    for s in p.signals:
        assert s.fact_cs
        assert "_" not in s.fact_cs  # no raw enum reaches a sentence


# ==============================================================================
# Czech that reads as written
# ==============================================================================

def test_the_stages_have_czech_names():
    assert PHASE_NAMES_CS[GOLD_MINE] == "zlatý důl"
    assert set(PHASE_NAMES_CS) >= {GREAT_FIND, WAIT_TIME, GOLD_MINE}


def test_each_stage_explains_itself_without_the_canon():
    for phase in (GREAT_FIND, WAIT_TIME, GOLD_MINE):
        assert len(PHASE_MEANING_CS[phase]) > 30


def test_the_wait_time_meaning_carries_the_canons_instruction():
    """§3 is blunt about this one, and the screen must be too."""
    assert "nebýt investovaný" in PHASE_MEANING_CS[WAIT_TIME]


def test_a_summary_without_a_proposal_says_what_is_missing():
    p = given(layer=LAYER_NONE)
    assert "neposoudím" in p.summary_cs()


def test_counts_in_the_gap_message_are_declined():
    assert "0 tvrdých údajů" in given(layer=LAYER_NONE).unknowns[0]
    one = given(layer=LAYER_YAHOO, revenue_yoy_pct=6.0)
    assert "1 tvrdý údaj" in one.unknowns[0]


# ==============================================================================
# The definition still has to hold, not just the arithmetic
# ==============================================================================

def test_growing_revenue_forbids_a_wait_time_verdict():
    """
    ECOR, live: a 41 % retrace and eight months of cash scored Wait Time while
    revenue grew 28 % year on year. Wait Time means "the story has not caught
    traction" (§3), and a revenue line like that falsifies the definition. A
    working business at a fallen price is a cheap something, not a Wait Time.
    """
    p = given(
        revenue_yoy_pct=28.0, operating_cash_flow=-500_000.0,
        high_water=10.49, current_price=6.19, runway_months=8.0,
    )
    assert p.phase is None
    assert any("příběh se chytá" in u for u in p.unknowns)


def test_profitable_but_flat_is_not_a_gold_mine():
    """
    INFU, live: profitable with revenue up 2,6 %. The canon's Gold Mine is
    "momentum nastartoval, firma profituje" — both halves. Profitable and flat
    is a steady business, not momentum.
    """
    p = given(revenue_yoy_pct=2.6, operating_cash_flow=1_000_000.0)
    assert p.phase is None
    assert any("druhá půlka definice chybí" in u for u in p.unknowns)


def test_profitable_with_improving_margins_is_still_a_gold_mine():
    """Momentum need not be revenue: a margin turning up is momentum too."""
    p = given(
        revenue_yoy_pct=2.6, operating_cash_flow=1_000_000.0,
        margin_move_pp=6.0, high_water=10.0, current_price=9.0,
    )
    assert p.phase == GOLD_MINE


def test_a_contradicted_verdict_is_no_proposal_not_the_runner_up():
    """
    Picking second place would be inventing a verdict from evidence that
    already pointed somewhere the definition forbids.
    """
    p = given(revenue_yoy_pct=28.0, operating_cash_flow=-1.0,
              high_water=10.0, current_price=5.0)
    assert p.phase is None


def test_falling_revenue_still_reaches_wait_time():
    """The guard must not disarm the verdict it was written beside."""
    p = given(revenue_yoy_pct=-17.4, operating_cash_flow=-1.0,
              margin_move_pp=-9.7, high_water=7.47, current_price=3.17)
    assert p.phase == WAIT_TIME
    assert p.confidence == CONFIDENCE_HIGH


# ==============================================================================
# Stale is the same defect as missing, wearing a different coat
# ==============================================================================

def test_a_drawdown_needs_a_price_and_a_high_from_the_same_moment():
    """
    ECOR, live and expensive: the quote cache held 6,19 from 26 July while the
    position carried 10,52 from 21 August. Reading the month-old figure gave a
    41 % drawdown that was really 4 %, and those two points turned ECOR into a
    Wait Time — "sell it" — when the fresh price makes it a Gold Mine.

    Nothing was confirmed, so nothing was lost. The rule the app already keeps
    for missing inputs has to cover stale ones too.
    """
    stale = given(revenue_yoy_pct=28.0, operating_cash_flow=-1.0,
                  runway_months=8.0, high_water=10.49, current_price=6.19)
    fresh = given(revenue_yoy_pct=28.0, operating_cash_flow=-1.0,
                  runway_months=8.0, high_water=None, current_price=10.52)

    assert stale.phase is None       # the retrace contradicts growing revenue
    assert fresh.phase == GOLD_MINE  # with no bogus retrace, the numbers agree


def test_no_comparable_high_is_a_named_gap_not_a_drawdown_of_zero():
    p = given(revenue_yoy_pct=28.0, operating_cash_flow=1.0,
              margin_move_pp=5.0, current_price=10.52, high_water=None)
    assert any("maximum pozice neznám" in u for u in p.unknowns)
    assert not any("pod maximem" in s.fact_cs for s in p.signals)


def test_the_peaks_date_is_printed_with_the_drawdown():
    """
    „57 % pod maximem" and „57 % pod maximem z 13. 11. 2024" are different
    claims: only the second lets a person judge whether that peak was the Great
    Find move the canon means, or something older inside the same window.
    """
    p = given(revenue_yoy_pct=-17.4, operating_cash_flow=-1.0,
              high_water=8.17, current_price=3.13,
              high_water_on_cs="13. 11. 2024")
    [retrace] = [s for s in p.signals if "pod maximem" in s.fact_cs]
    assert "z 13. 11. 2024" in retrace.fact_cs
