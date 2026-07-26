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

from enum import Enum


class InvestmentSource(str, Enum):
    """Canonical source keys stored in Stock.source_key."""
    GOMES = "GOMES"
    BREAKOUT_INVESTORS = "BREAKOUT_INVESTORS"
    OTHER = "OTHER"


def normalize_source(speaker: str | None) -> str:
    """
    Map a free-text speaker/analyst name to a canonical source key.

    Robust to casing and common variants ("Mark Gomes", "money mark",
    "Breakout Investors", "breakout"). Anything unrecognized -> OTHER.
    """
    if not speaker:
        return InvestmentSource.OTHER.value

    s = speaker.strip().lower()
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
