"""
Lifecycle classification from spoken text.

This classifier had no tests, and a real Gomes stream showed why that mattered:
it searched the whole document for a phrase and attributed the hit to whatever
ticker the caller passed in. A two-hour video covering forty companies made
every one of them a GOLD_MINE firing on ten cylinders.

Ten cylinders means a deserved R/R score of zero, which lets almost any
beaten-down price clear the Buy Guard. These tests pin the two rules that stop
that: evidence must be about the company being judged, and a cylinder count is
never inferred from text here at all.
"""

import pytest

from app.trading.gomes_logic import (
    LifecyclePhase,
    RiskRewardCalculator,
    StockLifecycleClassifier,
)

#: Condensed from the 2026-08-21 stream. Every sentence here was actually
#: said; what matters is which company each one is about.
TRANSCRIPT = (
    "This green line is representative of a company operating on basically "
    "one cylinder out of 10. The red line represents a company that is "
    "operating on 10 cylinders. Now if you look at a company like gatekeeper, "
    "gatekeeper is operating on ten cylinders right now. "
    "I think Watt is executing on more than one cylinder for sure. "
    "Intermap has proven themselves to not be able to execute cleanly. "
    "There are problems everywhere in this market."
)


# ==============================================================================
# The regression: evidence about someone else is not evidence
# ==============================================================================

def test_a_phrase_said_about_another_company_does_not_classify_this_one():
    """
    "10 cylinders" appears twice above — about the chart's definition and
    about GateKeeper. Neither is a statement about Intermap. Before this was
    fixed, classify("ITMSF", ...) returned ten cylinders and GOLD_MINE.
    """
    got = StockLifecycleClassifier.classify("ITMSF", TRANSCRIPT, aliases=("intermap",))
    assert got.cylinders_count is None
    assert got.firing_on_all_cylinders is None
    assert got.phase is not LifecyclePhase.GOLD_MINE


def test_the_same_holds_for_the_company_the_phrase_was_about():
    """
    GateKeeper really is on ten cylinders in this transcript. It still must
    not come from here — a count is a judgement about a business, and it
    reaches the database only through claim extraction, with a verified quote
    behind it.
    """
    got = StockLifecycleClassifier.classify("GKPRF", TRANSCRIPT, aliases=("gatekeeper",))
    assert got.cylinders_count is None


def test_hedged_speech_is_why_a_count_is_never_lifted_from_a_sentence():
    """
    "Watt is executing on MORE THAN one cylinder" names the company and
    contains a number, so scoping alone would not have saved it. One is the
    wrong answer, and wrong here spends money.
    """
    got = StockLifecycleClassifier.classify("WATT", TRANSCRIPT, aliases=("watt",))
    assert got.cylinders_count is None


def test_unknown_cylinders_make_the_buy_guard_refuse():
    """The point of returning None: the chain fails closed, not open."""
    assert RiskRewardCalculator.deserved_score(None) is None
    zone, reason = RiskRewardCalculator.decide_from_score(9.5, None)
    assert zone != "BUY"
    assert "válc" in reason


# ==============================================================================
# Scoping
# ==============================================================================

SCOPED = (
    "ACME had record revenue this quarter and is now profitable. "
    "Meanwhile another company is stuck and going nowhere with delays."
)


def test_signals_in_sentences_naming_the_ticker_still_count():
    got = StockLifecycleClassifier.classify("ACME", SCOPED)
    assert got.phase is LifecyclePhase.GOLD_MINE
    assert got.is_investable is True


def test_signals_about_the_other_company_do_not_leak_across():
    """The Wait Time signals here belong to "another company", not ACME."""
    got = StockLifecycleClassifier.classify("ACME", SCOPED)
    assert got.phase is not LifecyclePhase.WAIT_TIME
    assert not any(k.startswith("wait_time:") for k in got.signals)


def test_wait_time_still_wins_when_it_is_this_company():
    text = "ZZZ is dead money, going nowhere, stuck after repeated delays."
    got = StockLifecycleClassifier.classify("ZZZ", text)
    assert got.phase is LifecyclePhase.WAIT_TIME
    assert got.is_investable is False


def test_aliases_are_how_a_spoken_name_reaches_the_ticker():
    """Gomes says "gatekeeper", never "GKPRF"."""
    text = "Gatekeeper had record revenue and raised guidance."
    assert StockLifecycleClassifier.classify("GKPRF", text).phase is LifecyclePhase.UNKNOWN
    assert (
        StockLifecycleClassifier.classify("GKPRF", text, aliases=("gatekeeper",)).phase
        is LifecyclePhase.GOLD_MINE
    )


def test_a_ticker_never_mentioned_says_so_rather_than_guessing():
    got = StockLifecycleClassifier.classify("NOPE", SCOPED)
    assert got.phase is LifecyclePhase.UNKNOWN
    assert "NOPE" in got.reasoning


def test_no_text_is_distinct_from_text_without_signals():
    assert "No text" in StockLifecycleClassifier.classify("ACME").reasoning
    assert "Insufficient" in StockLifecycleClassifier.classify(
        "ACME", "ACME exists."
    ).reasoning


def test_a_ticker_inside_a_longer_word_is_not_a_mention():
    """Substring matching is what caused this bug; word boundaries matter."""
    got = StockLifecycleClassifier.classify("CAT", "The catalogue had record revenue.")
    assert got.phase is LifecyclePhase.UNKNOWN


@pytest.mark.parametrize("ticker", ["ITMSF", "GKPRF", "WATT", "KRMD", "ACME", "ZZZ"])
def test_no_input_produces_a_cylinder_count_from_this_path(ticker):
    for text in (TRANSCRIPT, SCOPED, None, "firing on all cylinders"):
        assert StockLifecycleClassifier.classify(ticker, text).cylinders_count is None
