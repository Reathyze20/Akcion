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
# Transcript timestamps
# ==============================================================================

#: Shape of a real Gomes video transcript: the tool drops "(H:MM:SS)" markers
#: wherever it feels like, including the middle of a sentence.
TRANSCRIPT = """if you look at a company like gatekeeper gatekeeper is operating on ten
cylinders right now (1:12:04) I don't think anybody can deny that. KRMD chart,
there you go. I like KRMD, okay? Very much at the low end of the range.
(1:35:22) Stock's still coming lower, very cheap.
"""


def test_quote_across_a_timestamp_is_accepted():
    """
    The regression this exists for. Eight true claims from a real two-hour
    transcript were rejected — among them the only cylinder count in the whole
    video, which is the one input the Buy Guard cannot run without. Every one
    of them had been said; each merely spanned an injected timestamp that the
    model left out when quoting.
    """
    ok, bad = verify_claims(
        [claim("I like KRMD, okay? Very much at the low end of the range. "
               "Stock's still coming lower", ticker="KRMD")],
        TRANSCRIPT,
    )
    assert len(ok) == 1 and not bad


def test_a_quote_may_also_keep_the_timestamp():
    """Both directions: the model may quote the marker or drop it."""
    ok, _ = verify_claims(
        [claim("operating on ten cylinders right now (1:12:04) I don't think",
               ticker="GKPRF")],
        TRANSCRIPT,
    )
    assert len(ok) == 1


def test_bracketed_timestamps_are_handled_too():
    ok, _ = verify_claims(
        [claim("hello world")], "hello [00:12] world"
    )
    assert len(ok) == 1


def test_stripping_timestamps_does_not_forgive_a_fabrication():
    """
    The relaxation is narrow on purpose: it removes a transcript artifact, not
    a word. An invented sentence is still rejected, and so is a real sentence
    with an altered number.
    """
    ok, bad = verify_claims(
        [claim("gatekeeper is operating on four cylinders right now",
               ticker="GKPRF"),
         claim("I like KRMD at the very top of the range", ticker="KRMD")],
        TRANSCRIPT,
    )
    assert not ok and len(bad) == 2


def test_a_price_in_parentheses_is_not_mistaken_for_a_timestamp():
    """Money must survive normalisation — "(3:1)" splits, "$4.50" prices."""
    ok, bad = verify_claims(
        [claim("announced a 1-for-10 reverse split at $4.50"),
         claim("nothing like this was ever said")],
        "The board announced a 1-for-10 reverse split at $4.50 per share.",
    )
    assert len(ok) == 1 and len(bad) == 1


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
