"""
How big a position may get, by what kind of bet it is.

The axis the tiers do not have
------------------------------
The canon's tiers — primary, secondary, tertiary — measure **how sure the
thesis is**. That is not the same question as **what kind of bet this is**. A
biotech whose next readout either doubles it or halves it is not an anchor,
however certain the thesis feels, and a stable compounder is not a lottery
ticket just because nobody has written it up yet.

`core/gomes_logic.GomesLogicEngine` is being removed — its rule 5 was
unreachable and rule 4 always fired first — but this one table inside it is
real and has no equivalent anywhere else in the app, so it is kept here rather
than deleted with the rest.

Ceilings, and they only ever tighten
------------------------------------
These are caps, not targets. Whatever the tier and the source-agreement matrix
allow, this may lower and never raise: two limits on the same position resolve
to the smaller one, always.

The unknown is not a middle value
---------------------------------
`GomesLogicEngine` defaulted a missing asset class to `HIGH_BETA_ROCKET` and
`routes/gomes.py` still does — an unrecorded field silently becoming an 8 %
ceiling on a specific kind of risk. This module refuses that: an unclassified
company gets no cap from here at all and is named instead. As of 2026-08-23
**all twelve holdings are unclassified**, so today this table changes nothing
and says so — which is the honest state, not a bug.
"""

from __future__ import annotations

from typing import Final

#: Per-class ceilings, as a percentage of the account the position sits in.
#: `VALUE_TRAP` is zero on purpose: the class means "do not own this", and a
#: cap of zero is how that is said in the same units as everything else.
BASE_CAPS: Final[dict[str, float]] = {
    "ANCHOR": 12.0,            # stable compounders
    "HIGH_BETA_ROCKET": 8.0,   # miners, leveraged plays
    "BIOTECH_BINARY": 3.0,     # one readout decides it
    "TURNAROUND": 2.0,         # recovery, and it may not
    "VALUE_TRAP": 0.0,         # never
}

#: Czech names, so no raw enum reaches a sentence somebody reads.
CLASS_NAMES_CS: Final[dict[str, str]] = {
    "ANCHOR": "kotva",
    "HIGH_BETA_ROCKET": "vysoce volatilní sázka",
    "BIOTECH_BINARY": "biotech s binárním výsledkem",
    "TURNAROUND": "ozdravení firmy",
    "VALUE_TRAP": "hodnotová past",
}


def cap_for(asset_class: str | None) -> float | None:
    """
    The ceiling this class imposes, or None when there is nothing to impose.

    None means "this axis has no opinion" — an unrecorded class, or one nobody
    recognises. It must never be read as "no limit"; the caller keeps whatever
    limits it already had.
    """
    if not asset_class:
        return None
    return BASE_CAPS.get(asset_class.strip().upper())


def apply_cap(current_cap_pct: float, asset_class: str | None) -> float:
    """
    Tighten an existing ceiling to whichever of the two is smaller.

    Only downward, so the order the limits are applied in cannot change the
    answer, and so a generous asset class can never unlock a position the tier
    or the source matrix had already limited.
    """
    cap = cap_for(asset_class)
    if cap is None:
        return current_cap_pct
    return min(current_cap_pct, cap)


def warning_cs(ticker: str, asset_class: str | None) -> str | None:
    """
    What to say when the class is missing, or when it forbids the position.

    An unclassified company is not a safe one and not a risky one — it is
    unrecorded, and the difference has to reach the screen, because the silent
    version of this defaulted every unknown to an 8 % ceiling on a risk profile
    nobody had assessed.
    """
    if not asset_class:
        return (
            f"{ticker}: druh sázky nikdo nezaznamenal — nevím, jestli je to "
            f"kotva nebo biotech s binárním výsledkem, takže strop na velikost "
            f"pozice z téhle osy nedávám žádný"
        )

    key = asset_class.strip().upper()
    if key not in BASE_CAPS:
        return f"{ticker}: druh sázky „{asset_class}“ neznám — strop z něj nedávám"

    if BASE_CAPS[key] == 0.0:
        return (
            f"{ticker}: vedeno jako {CLASS_NAMES_CS[key]} — tahle třída se "
            f"nekupuje vůbec"
        )
    return None
