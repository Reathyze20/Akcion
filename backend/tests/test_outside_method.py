"""
Rules for the positions the method cannot value.

Eight of the twelve holdings have no Green and no Red Line, and until now the
band engine correctly said MIMO_METODIKU and the app then said nothing at all
about most of the money. Silence is not neutral: the position nobody is
watching is the one that turns into a loss slowly enough to go unnoticed.

What is tested is the boundary. None of these rules may produce a BUY — buying
needs a valuation and there isn't one — and none of them may pretend to know
what a company is worth. They answer questions a band was never needed for.
"""

import pytest

from app.services.outside_method import (
    DRAWDOWN_REVIEW_PCT,
    RUNWAY_CRITICAL_MONTHS,
    SEVERITY_EXIT,
    SEVERITY_NOTE,
    SEVERITY_REVIEW,
    UNVALUED_WEIGHT_PCT,
    Finding,
    UnvaluedPosition,
    assess,
)


def position(**kw) -> UnvaluedPosition:
    base = dict(ticker="DAIO", weight_pct=4.0, sec_covered=True)
    base.update(kw)
    return UnvaluedPosition(**base)


# ==============================================================================
# Survival, which needs no valuation
# ==============================================================================

def test_a_few_months_of_cash_is_an_exit(assertion_note=None):
    """
    Under six months the question stops being about price. SMSI's balance was
    four months of spending in August 2026 while its going concern warning sat
    in a markdown blob nothing could query — this is the numeric half of the
    same warning, and it is the half the app can actually read.
    """
    [finding] = assess(position(ticker="SMSI", runway_months=4.0))
    assert finding.severity == SEVERITY_EXIT
    assert finding.is_exit
    assert "4 měsíc" in finding.message_cs


def test_under_a_year_is_worth_reading_not_acting_on():
    [finding] = assess(position(ticker="ECOR", runway_months=8.0))
    assert finding.severity == SEVERITY_REVIEW
    assert "peníze odjinud" in finding.message_cs


def test_comfortable_cash_says_nothing():
    assert assess(position(runway_months=31.0)) == []


def test_an_unknown_runway_outside_sec_is_named_as_a_hole():
    """
    "Nothing found" means nothing when nobody looked. Four of the five largest
    positions file where EDGAR cannot see, and reporting their silence as
    reassurance is the defect this codebase keeps finding.
    """
    [finding] = assess(position(ticker="KUYA.V", sec_covered=False))
    assert finding.severity == SEVERITY_NOTE
    assert "prázdné místo" in finding.message_cs


def test_an_unknown_runway_inside_sec_is_not_alarming():
    """A company EDGAR covers whose runway simply is not computable this quarter."""
    assert assess(position(sec_covered=True)) == []


# ==============================================================================
# What it has done to the owner
# ==============================================================================

def test_a_deep_fall_from_its_own_high_asks_for_a_re_read():
    [finding] = assess(position(high_water=10.0, current_price=5.0))
    assert finding.severity == SEVERITY_REVIEW
    assert "50 % pod svým maximem" in finding.message_cs


def test_a_fall_is_never_turned_into_a_sale():
    """
    The one thing this module must not do. The canon buys falling prices near
    the Green Line on purpose, so a stop here would sell exactly what the
    method means to buy — and without a band there is no way to tell an
    opportunity from a broken thesis.
    """
    findings = assess(position(high_water=10.0, current_price=3.0))
    assert all(not f.is_exit for f in findings)
    assert any("přečti si ji znovu" in f.message_cs for f in findings)


def test_a_shallow_fall_is_not_news():
    assert assess(position(high_water=10.0, current_price=8.0)) == []


def test_a_position_at_its_high_is_not_news():
    assert assess(position(high_water=10.0, current_price=10.0)) == []


def test_a_missing_high_water_mark_produces_nothing():
    """No history is not a fall of zero percent."""
    assert assess(position(high_water=None, current_price=5.0)) == []


# ==============================================================================
# How much of the money rests on something unjudgeable
# ==============================================================================

def test_a_large_unvalued_holding_is_flagged():
    [finding] = assess(position(ticker="INFU", weight_pct=12.0))
    assert finding.severity == SEVERITY_REVIEW
    assert "neumí říct vůbec nic" in finding.message_cs


def test_the_weight_rule_is_about_the_app_not_the_company():
    """
    Deliberately looser than the speculative tier cap of 2 %. This is not a
    verdict about the business — it is a limit on how much should rest on
    something nobody can judge.
    """
    assert UNVALUED_WEIGHT_PCT > 2.0
    assert assess(position(weight_pct=UNVALUED_WEIGHT_PCT)) == []


# ==============================================================================
# The shape of the answer
# ==============================================================================

def test_the_worst_finding_comes_first():
    findings = assess(position(
        ticker="SMSI", runway_months=4.0, weight_pct=12.0,
        high_water=10.0, current_price=4.0,
    ))
    assert [f.severity for f in findings] == [
        SEVERITY_EXIT, SEVERITY_REVIEW, SEVERITY_REVIEW
    ]


def test_nothing_wrong_that_this_module_can_see_is_an_empty_list():
    """
    Which is not the same as nothing being wrong, and the caller has to say so.
    A company with no band is unjudged, not judged and cleared.
    """
    assert assess(position(runway_months=30.0, high_water=10.0, current_price=9.5)) == []


def test_no_rule_here_can_ever_produce_a_purchase():
    """
    The boundary of the whole module. Buying needs a valuation and there is
    none; everything here is a reason to look or a reason to take money off the
    table.
    """
    findings = assess(position(
        runway_months=1.0, weight_pct=20.0, high_water=100.0, current_price=1.0,
    ))
    assert findings
    assert all(f.severity in (SEVERITY_EXIT, SEVERITY_REVIEW, SEVERITY_NOTE)
               for f in findings)
