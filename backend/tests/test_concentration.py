"""
The question no per-stock rule can answer.

The band engine judges one holding at a time and is right to. But "am I fine"
is a question about the portfolio, and two facts only exist at that level: how
much of the money sits in companies with a material warning, and how much sits
in companies nobody can read.

The second is what surprised. On 2026-08-23, 3.6 % of this portfolio was in a
company with a known problem and 60.5 % was in companies EDGAR cannot see —
four Canadian listings and an OTC name. Reporting the 3.6 % alone would be true
and misleading, so the answer is a range and the gap between its ends is itself
the finding.
"""

import pytest

from app.services.concentration import (
    MATERIAL_BLOCK_PCT,
    MATERIAL_WARN_PCT,
    UNASSESSED_WARN_PCT,
    Holding,
    assess,
)


def held(ticker, value, **kw):
    return Holding(ticker=ticker, value_czk=value, **kw)


# ==============================================================================
# Three buckets, and the one that is not a verdict
# ==============================================================================

def test_a_read_company_with_nothing_material_is_clean():
    reading = assess([held("INFU", 1000.0, assessed=True, runway_months=30.0)])
    assert reading.material_pct == 0.0
    assert reading.unassessed_pct == 0.0


def test_a_company_nobody_can_read_is_unassessed_not_clean():
    """
    The defect this exists to prevent. "Nothing found" for a company EDGAR
    cannot serve is an empty result, not a reassuring one.
    """
    reading = assess([held("KUYA.V", 1000.0, assessed=False)])
    assert reading.unassessed_pct == 100.0
    assert reading.material_pct == 0.0
    assert reading.unassessed_tickers == ["KUYA.V"]


def test_short_cash_is_material_even_with_no_filing_text():
    """
    The balance sheet said it in numbers, which needs no narrative — and the
    narrative half is still trapped in markdown for eight filings.
    """
    reading = assess([held("SMSI", 1000.0, assessed=False, runway_months=4.0)])
    assert reading.material_pct == 100.0
    assert reading.material_tickers == ["SMSI"]


def test_a_filing_finding_is_material_whatever_the_cash_says():
    reading = assess([
        held("ECOR", 1000.0, assessed=True, has_material_finding=True, runway_months=30.0)
    ])
    assert reading.material_pct == 100.0


# ==============================================================================
# A range, never a number
# ==============================================================================

def test_the_answer_spans_from_the_known_to_the_possible():
    """
    Today's real shape: one small company known to be in trouble, most of the
    money unreadable. The floor alone would read as the answer.
    """
    reading = assess([
        held("SMSI", 36.0, assessed=True, runway_months=4.0),
        held("VTSI", 74.0, assessed=True, runway_months=31.0),
        held("KUYA.V", 605.0, assessed=False),
        held("IRIX", 285.0, assessed=True, runway_months=24.0),
    ])

    assert reading.material_pct == pytest.approx(3.6, abs=0.1)
    assert reading.unassessed_pct == pytest.approx(60.5, abs=0.1)
    assert reading.upper_bound_pct == pytest.approx(64.1, abs=0.1)


def test_the_range_is_stated_in_words():
    reading = assess([
        held("SMSI", 100.0, assessed=True, runway_months=4.0),
        held("KUYA.V", 900.0, assessed=False),
    ])
    [_material, unassessed] = reading.warnings_cs()

    assert "NEPOSOUZENO" in unassessed
    assert "mezi 10,0 %" in unassessed.replace(".", ",")
    assert "nenalezení tam nic neznamená" in unassessed


def test_a_portfolio_nobody_can_read_says_so_loudly():
    reading = assess([held("KUYA.V", 1000.0, assessed=False)])
    assert reading.unassessed_pct > UNASSESSED_WARN_PCT
    assert any("NEPOSOUZENO" in w for w in reading.warnings_cs())


def test_a_readable_portfolio_says_nothing_about_blind_spots():
    reading = assess([held("VTSI", 1000.0, assessed=True, runway_months=31.0)])
    assert reading.warnings_cs() == []


# ==============================================================================
# What it stops, and what it does not
# ==============================================================================

def test_a_pile_of_broken_companies_stops_new_speculation():
    """
    Adding another gamble on top of a portfolio already carrying broken
    companies is the sequence that turns a bad quarter into a bad year.
    """
    reading = assess([
        held("SMSI", 300.0, assessed=True, runway_months=4.0),
        held("VTSI", 700.0, assessed=True, runway_months=31.0),
    ])
    assert reading.material_pct == 30.0
    assert reading.blocks_speculation


def test_a_small_known_problem_stops_nothing():
    reading = assess([
        held("SMSI", 36.0, assessed=True, runway_months=4.0),
        held("VTSI", 964.0, assessed=True, runway_months=31.0),
    ])
    assert not reading.blocks_speculation
    assert any("S NÁLEZEM" in w for w in reading.warnings_cs())


def test_a_blind_spot_never_blocks_anything():
    """
    An unreadable company is not a bad one. Blocking on ignorance would refuse
    every purchase for want of filings nobody publishes.
    """
    reading = assess([held("KUYA.V", 1000.0, assessed=False)])
    assert not reading.blocks_speculation


def test_past_the_upper_threshold_the_wording_changes():
    """Above forty percent it is not one bad position, it is the portfolio."""
    reading = assess([
        held("SMSI", 500.0, assessed=True, runway_months=4.0),
        held("VTSI", 500.0, assessed=True, runway_months=31.0),
    ])
    assert reading.material_pct > MATERIAL_WARN_PCT
    assert any("skladba portfolia" in w for w in reading.warnings_cs())


def test_the_block_threshold_sits_below_the_warning_one():
    assert MATERIAL_BLOCK_PCT < MATERIAL_WARN_PCT


def test_an_empty_portfolio_says_nothing():
    assert assess([]).warnings_cs() == []
    assert assess([held("X", 0.0)]).total_czk == 0.0
