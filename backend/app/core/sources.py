"""
Investment source attribution + cross-source agreement.

The app is fed by pasting content from TWO independent sources:
  - Mark Gomes (a structured single analyst), and
  - Breakout Investors (a crowd-sourced Discord community).

They must coexist per ticker (never overwrite each other) and be comparable
side by side. This module holds the pure, dependency-free logic for that:
normalizing a free-text speaker into a canonical source key, and summarizing
whether the sources agree or disagree on a ticker.

Keeping this pure (no DB, no SQLAlchemy) makes it unit-testable in isolation.
See docs/GOMES_METHODOLOGY_CANON.md (dual-source context).
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum


class InvestmentSource(str, Enum):
    """Canonical source keys stored in Stock.source_key."""
    GOMES = "GOMES"
    BREAKOUT_INVESTORS = "BREAKOUT_INVESTORS"
    OTHER = "OTHER"


def normalize_source(
    speaker: str | None,
    roster: Mapping[str, str] | None = None,
) -> str:
    """
    Map a free-text speaker to the source whose authority their claim carries.

    `roster` maps a lower-cased name to a source key and is consulted FIRST.
    Load it with `app/services/analyst_roster.py`; this module stays free of
    the database so the rules can be exercised without one.

    Why the roster had to exist: this key becomes `Stock.source_key`, and
    `evaluate_dual_source_buy` reads it to decide whether two sources agree —
    which sets the position cap at 15 %, 7 % or 5 %. Deciding it by substring
    meant an analyst writing under his own name fell to OTHER, and OTHER does
    not enter the matrix at all. Their work was stored and silently unused.

    The keyword fallback stays for Gomes' own spellings and for content pasted
    with a source label rather than a person's name. Anything unrecognised is
    OTHER, which is the correct treatment for a stranger in a group of a
    hundred and thirty and is not a judgement about them.
    """
    if not speaker:
        return InvestmentSource.OTHER.value

    s = speaker.strip().lower()

    if roster:
        listed = roster.get(s)
        if listed:
            return listed

    if "gomes" in s or "money mark" in s:
        return InvestmentSource.GOMES.value
    if "breakout" in s:
        return InvestmentSource.BREAKOUT_INVESTORS.value
    return InvestmentSource.OTHER.value


# Verdict -> directional stance. Used to decide if two sources agree.
_BULLISH = {"BUY_NOW", "BUY", "STRONG_BUY", "ACCUMULATE", "ADD"}
_BEARISH = {"TRIM", "SELL", "AVOID", "EXIT", "HARD_EXIT"}
# Everything else (WATCH_LIST, HOLD, None, unknown) is treated as NEUTRAL.


def verdict_stance(action_verdict: str | None) -> str:
    """Reduce an action verdict to BULLISH / BEARISH / NEUTRAL."""
    if not action_verdict:
        return "NEUTRAL"
    v = action_verdict.strip().upper()
    if v in _BULLISH:
        return "BULLISH"
    if v in _BEARISH:
        return "BEARISH"
    return "NEUTRAL"


def summarize_source_agreement(takes: list[dict]) -> dict:
    """
    Summarize whether sources agree on a ticker.

    Args:
        takes: list of dicts, each with at least "source_key" and
               "action_verdict" (optionally "conviction_score").

    Returns a dict:
        {
          "status": "NONE" | "SINGLE" | "AGREE" | "MIXED" | "CONFLICT",
          "stances": {source_key: stance, ...},
          "detail": human-readable one-liner
        }

    - NONE     : no takes
    - SINGLE   : only one source has a take
    - AGREE    : all sources share the same stance
    - CONFLICT : at least one BULLISH and one BEARISH (direct disagreement)
    - MIXED    : differ but not opposed (e.g. BULLISH + NEUTRAL)
    """
    if not takes:
        return {"status": "NONE", "stances": {}, "detail": "Žádná analýza"}

    stances = {t.get("source_key") or "OTHER": verdict_stance(t.get("action_verdict")) for t in takes}

    if len(stances) == 1:
        (src, stance), = stances.items()
        return {
            "status": "SINGLE",
            "stances": stances,
            "detail": f"Jen {src}: {stance}",
        }

    distinct = set(stances.values())
    if len(distinct) == 1:
        stance = next(iter(distinct))
        return {
            "status": "AGREE",
            "stances": stances,
            "detail": f"Zdroje souhlasí: {stance}",
        }

    if "BULLISH" in distinct and "BEARISH" in distinct:
        return {
            "status": "CONFLICT",
            "stances": stances,
            "detail": "Zdroje si PROTIŘEČÍ (jeden BUY, druhý SELL) — rozhodni sám",
        }

    return {
        "status": "MIXED",
        "stances": stances,
        "detail": "Zdroje se liší (ne přímo opačně)",
    }


# ---------------------------------------------------------------------------
# Which reading about a company outranks which
# ---------------------------------------------------------------------------

#: A reading the analyst himself put on record — his own words, dated.
RANK_ANALYST: int = 2
#: A number this app worked out from filings and prices. Useful, and an
#: estimate.
RANK_RUBRIC: int = 1
#: Provenance nobody recorded. Ranks below the rubric on purpose: a row that
#: cannot say where it came from is the weakest thing in the table.
RANK_UNKNOWN: int = 0

_ANALYST_PREFIXES = ("gomes", "breakout", "transcript", "video")
_ANALYST_MARKERS = ("official",)
_RUBRIC_MARKERS = ("rubric", "heuristic", "estimate", "computed")


def lifecycle_source_rank(source: str | None) -> int:
    """
    How much authority a `stock_lifecycle` row's `source` carries.

    Rows about the same company arrive from two very different places. One is
    Mark Gomes saying a number out loud on a dated video; the other is this
    app's rubric inferring one from filings. Both are worth storing. They are
    not worth the same, and until 2026-08-24 the table did not know that: the
    writer superseded whatever was live, so the newest row won by being newest.

    What that cost, concretely. On 2026-08-21 Gomes said of Gatekeeper
    „they are operating on all ten cylinders". Two days later a rubric
    confirmation of 5 closed that row out. Because `zasloužené = 10 − válce`,
    the bar the price is judged against moved from 0 to 5, the R/R score of
    4,26 turned from cheap into overpriced, and the app ordered half a 13,9 %
    position sold — on the strength of its own guess, over his statement.

    So sources are ranked and the writers consult the rank. The owner may still
    overrule anything; what he may not do any more is overrule it by accident.
    """
    if not source:
        return RANK_UNKNOWN

    text = source.strip().lower()
    if text.startswith(_ANALYST_PREFIXES) or any(m in text for m in _ANALYST_MARKERS):
        return RANK_ANALYST
    if any(m in text for m in _RUBRIC_MARKERS):
        return RANK_RUBRIC
    return RANK_UNKNOWN
