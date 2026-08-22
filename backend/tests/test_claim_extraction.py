"""
Claim extraction guards.

The model call itself is not exercised here — these cover the deterministic
parts that decide whether a model's output is allowed anywhere near the
database. The verbatim guard is the single most important rule in the intake:
it is what stops a fluent, well-formatted, entirely invented claim about a
company from being stored as evidence.
"""

import pytest

from app.services.claim_extraction import (
    ClaimType,
    ExtractedClaim,
    SourceType,
    ThesisImpact,
    build_prompt,
    resolve_source_key,
    verify_claims,
)

SOURCE = """\
Money Mark Gomes
That shouldn't have happened. I publicly closed it out at $6.61

Brad Steveson
WOLF blah. They need to establish or re-establish that materials moat!
Still holding over $1B in cash and operating cash flow improved to -55m
this quarter.
"""


def claim(quote: str, ticker: str = "IDN", **kw) -> ExtractedClaim:
    return ExtractedClaim(
        ticker=ticker,
        speaker=kw.pop("speaker", "Money Mark Gomes"),
        claim_type=kw.pop("claim_type", ClaimType.FACT),
        stance=kw.pop("stance", "NEUTRAL"),
        thesis_impact=kw.pop("thesis_impact", ThesisImpact.NEUTRAL),
        summary=kw.pop("summary", "shrnutí"),
        verbatim_quote=quote,
        confidence=kw.pop("confidence", 0.9),
        **kw,
    )


# ==============================================================================
# The verbatim guard
# ==============================================================================

def test_claim_quoting_the_source_is_kept():
    ok, bad = verify_claims([claim("I publicly closed it out at $6.61")], SOURCE)
    assert len(ok) == 1 and not bad


def test_invented_claim_is_rejected():
    """
    The failure this exists for: fluent, plausible, formatted correctly — and
    never said. It must not reach the database.
    """
    fabricated = claim("The company announced a $50M share buyback program.")
    ok, bad = verify_claims([fabricated], SOURCE)
    assert not ok
    assert len(bad) == 1


def test_quote_spanning_a_line_break_is_accepted():
    """Line wrapping is a rendering difference, not a different quote."""
    ok, _ = verify_claims(
        [claim("operating cash flow improved to -55m this quarter", ticker="WOLF")],
        SOURCE,
    )
    assert len(ok) == 1


def test_paraphrase_is_rejected_even_when_true():
    """
    "over $1B in cash" is true here, but this wording is not in the source.
    The guard requires the words, not the gist — a paraphrase is where a
    number quietly changes.
    """
    ok, bad = verify_claims(
        [claim("They hold more than one billion dollars in cash", ticker="WOLF")],
        SOURCE,
    )
    assert not ok and len(bad) == 1


def test_empty_quote_is_rejected():
    ok, bad = verify_claims([claim("")], SOURCE)
    assert not ok and len(bad) == 1


def test_mixed_batch_splits_cleanly():
    ok, bad = verify_claims(
        [
            claim("I publicly closed it out at $6.61"),
            claim("Revenue tripled year over year."),
            claim("Still holding over $1B in cash", ticker="WOLF"),
        ],
        SOURCE,
    )
    assert len(ok) == 2 and len(bad) == 1


def test_case_difference_does_not_reject():
    ok, _ = verify_claims([claim("i PUBLICLY closed it out at $6.61")], SOURCE)
    assert len(ok) == 1


# ==============================================================================
# Authority mapping
# ==============================================================================

def test_earnings_call_is_a_primary_company_source():
    """Whoever is at the microphone, the company stating its own numbers is fact."""
    assert resolve_source_key("Jane Doe, CFO", SourceType.EARNINGS_CALL) == "COMPANY"


def test_gomes_is_recognised_inside_the_group_chat():
    """One paste yields both sources — that is what makes agreement computable."""
    assert resolve_source_key("Money Mark Gomes", SourceType.WHATSAPP_GROUP) == "GOMES"


def test_other_group_members_are_breakout_investors():
    assert (
        resolve_source_key("Brad Steveson", SourceType.WHATSAPP_GROUP)
        == "BREAKOUT_INVESTORS"
    )


def test_gomes_video_is_gomes_regardless_of_speaker_label():
    assert resolve_source_key(None, SourceType.GOMES_VIDEO) == "GOMES"


def test_news_is_media():
    assert resolve_source_key("Reuters", SourceType.NEWS) == "MEDIA"


@pytest.mark.parametrize("name", ["mark gomes", "MONEY MARK", "Money Mark Gomes"])
def test_gomes_name_variants(name):
    assert resolve_source_key(name, SourceType.WHATSAPP_GROUP) == "GOMES"


# ==============================================================================
# Prompt assembly
# ==============================================================================

def test_prompt_carries_the_source_specific_guidance():
    earnings = build_prompt(SourceType.EARNINGS_CALL, "2026-08-22")
    whatsapp = build_prompt(SourceType.WHATSAPP_GROUP, "2026-08-22")
    assert "PRIMÁRNÍ ZDROJ" in earnings
    assert "cash runway" in earnings.lower()
    assert "TRADE_DISCLOSURE" in whatsapp
    assert earnings != whatsapp


def test_every_prompt_states_the_verbatim_and_no_verdict_rules():
    for st in SourceType:
        p = build_prompt(st, "2026-08-22")
        assert "DOSLOVNÝ CITÁT" in p
        assert "NEDĚLEJ VERDIKTY" in p
        assert "2026-08-22" in p
