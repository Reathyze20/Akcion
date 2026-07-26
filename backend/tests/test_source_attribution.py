"""
Dual-source attribution tests (Gomes vs Breakout Investors).

Covers the pure logic that decides how the two sources are labelled and whether
they agree — the foundation for storing both takes per ticker without overwrite.
Pure functions, no DB, so these run anywhere.
"""

from __future__ import annotations

import pytest

from app.core.sources import (
    InvestmentSource,
    normalize_source,
    verdict_stance,
    summarize_source_agreement,
)


# ---------------------------------------------------------------------------
# normalize_source — free-text speaker -> canonical source key
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "speaker, expected",
    [
        ("Mark Gomes", InvestmentSource.GOMES.value),
        ("mark gomes", InvestmentSource.GOMES.value),
        ("Money Mark", InvestmentSource.GOMES.value),
        ("  GOMES  ", InvestmentSource.GOMES.value),
        ("Breakout Investors", InvestmentSource.BREAKOUT_INVESTORS.value),
        ("breakout", InvestmentSource.BREAKOUT_INVESTORS.value),
        ("Some Random Analyst", InvestmentSource.OTHER.value),
        ("", InvestmentSource.OTHER.value),
        (None, InvestmentSource.OTHER.value),
    ],
)
def test_normalize_source(speaker, expected):
    assert normalize_source(speaker) == expected


# ---------------------------------------------------------------------------
# verdict_stance — verdict -> direction
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "verdict, expected",
    [
        ("BUY_NOW", "BULLISH"),
        ("ACCUMULATE", "BULLISH"),
        ("SELL", "BEARISH"),
        ("AVOID", "BEARISH"),
        ("TRIM", "BEARISH"),
        ("WATCH_LIST", "NEUTRAL"),
        ("HOLD", "NEUTRAL"),
        (None, "NEUTRAL"),
        ("something_weird", "NEUTRAL"),
    ],
)
def test_verdict_stance(verdict, expected):
    assert verdict_stance(verdict) == expected


# ---------------------------------------------------------------------------
# summarize_source_agreement — the side-by-side comparison
# ---------------------------------------------------------------------------

def test_agreement_none():
    assert summarize_source_agreement([])["status"] == "NONE"


def test_agreement_single_source():
    takes = [{"source_key": "GOMES", "action_verdict": "BUY_NOW"}]
    assert summarize_source_agreement(takes)["status"] == "SINGLE"


def test_agreement_agree():
    takes = [
        {"source_key": "GOMES", "action_verdict": "BUY_NOW"},
        {"source_key": "BREAKOUT_INVESTORS", "action_verdict": "ACCUMULATE"},
    ]
    result = summarize_source_agreement(takes)
    assert result["status"] == "AGREE"  # both bullish


def test_agreement_conflict():
    """The case that matters: one says buy, the other says sell."""
    takes = [
        {"source_key": "GOMES", "action_verdict": "BUY_NOW"},
        {"source_key": "BREAKOUT_INVESTORS", "action_verdict": "SELL"},
    ]
    result = summarize_source_agreement(takes)
    assert result["status"] == "CONFLICT"
    assert result["stances"]["GOMES"] == "BULLISH"
    assert result["stances"]["BREAKOUT_INVESTORS"] == "BEARISH"


def test_agreement_mixed():
    takes = [
        {"source_key": "GOMES", "action_verdict": "BUY_NOW"},
        {"source_key": "BREAKOUT_INVESTORS", "action_verdict": "WATCH_LIST"},
    ]
    result = summarize_source_agreement(takes)
    assert result["status"] == "MIXED"  # bullish + neutral, not opposed
