"""
How much of the money rests on companies with a problem — or on none anyone can see.

What no per-stock rule can answer
---------------------------------
The band engine judges one holding at a time and is right to. But "am I fine"
is a question about the portfolio, and two facts only exist at that level:

  * how much of it sits in companies whose own filings raise a material
    warning, and
  * how much of it sits in companies nobody can read at all.

The second is the one that surprised. On 2026-08-23, 3.6 % of this portfolio
was in a company with a known problem and **60.5 % was in companies EDGAR
cannot see** — four Canadian listings and an OTC name. For that 60 % the app
has no filings, no going concern, no controls opinion and no runway. "Nothing
found" there is an empty result, not a clean one.

A range, never a number
-----------------------
Reporting 3.6 % would be true and misleading: it is the floor of what could be
wrong, computed over the third of the portfolio anyone can assess. So the
answer is a range — what is known to be bad, and what it could be if the
unreadable two thirds are as bad as the readable third. Both ends are stated,
and the gap between them is itself the finding.

What it does
------------
Above a threshold of KNOWN material exposure, new speculative positions stop:
adding another gamble on top of a portfolio already carrying broken companies
is the sequence that turns a bad quarter into a bad year. Unassessed exposure
never blocks anything — it is not evidence of a problem, only of a blind spot —
but it is said every day it is true, because a blind spot nobody mentions is
one you stop seeing.
"""

from __future__ import annotations

from app.core.czech import n as cz

from dataclasses import dataclass, field
from typing import Final

#: Above this share in companies with a KNOWN material warning, no new
#: speculative position. Not a sell trigger: the holdings themselves are
#: judged by their own rules, and this only stops the pile growing.
MATERIAL_BLOCK_PCT: Final[float] = 25.0

#: Above this, say it every day until it is not true any more.
MATERIAL_WARN_PCT: Final[float] = 40.0

#: Above this share that nobody can assess, say so. It blocks nothing — an
#: unreadable company is not a bad one — but two thirds of a portfolio in the
#: dark is the single most important thing to know about it.
UNASSESSED_WARN_PCT: Final[float] = 50.0

#: How a holding is classified.
MATERIAL = "MATERIAL"      # a filing raised something material, or cash is short
CLEAN = "CLEAN"            # read, and nothing material found
UNASSESSED = "UNASSESSED"  # nobody can tell


@dataclass(frozen=True)
class Holding:
    """One position, as this check needs to see it."""

    ticker: str
    value_czk: float
    #: A CRITICAL or HIGH finding from the company's own filing.
    has_material_finding: bool = False
    #: Months of cash. Under six is material whatever the text says — it is the
    #: numeric half of a going concern and the half the app can read today.
    runway_months: float | None = None
    #: Whether the filings can be read at all.
    assessed: bool = False


@dataclass
class Reading:
    """The portfolio's exposure to trouble, and to not knowing."""

    total_czk: float = 0.0
    material_czk: float = 0.0
    clean_czk: float = 0.0
    unassessed_czk: float = 0.0
    material_tickers: list[str] = field(default_factory=list)
    unassessed_tickers: list[str] = field(default_factory=list)

    def _pct(self, part: float) -> float:
        return (part / self.total_czk * 100.0) if self.total_czk else 0.0

    @property
    def material_pct(self) -> float:
        return self._pct(self.material_czk)

    @property
    def unassessed_pct(self) -> float:
        return self._pct(self.unassessed_czk)

    @property
    def upper_bound_pct(self) -> float:
        """
        The worst it could be: everything known bad, plus everything unknown.

        Stated alongside the floor because a floor alone reads as the answer,
        and the distance between them is what the owner actually needs to see.
        """
        return self._pct(self.material_czk + self.unassessed_czk)

    @property
    def blocks_speculation(self) -> bool:
        return self.material_pct > MATERIAL_BLOCK_PCT

    def warnings_cs(self) -> list[str]:
        """Everything worth saying about this reading, worst first."""
        out: list[str] = []
        if not self.total_czk:
            return out

        if self.material_pct > MATERIAL_WARN_PCT:
            out.append(
                f"⚠️ RIZIKO V PORTFOLIU: {cz(self.material_pct, 1)} % peněz je ve "
                f"firmách s materiálním nálezem ({', '.join(self.material_tickers)}) "
                f"— nad {cz(MATERIAL_WARN_PCT, 0)} % to není jedna špatná pozice, "
                f"ale skladba portfolia"
            )
        elif self.blocks_speculation:
            out.append(
                f"⚠️ RIZIKO V PORTFOLIU: {cz(self.material_pct, 1)} % peněz je ve "
                f"firmách s materiálním nálezem ({', '.join(self.material_tickers)}) "
                f"— dokud to neklesne, nové spekulativní pozice nepřidávám"
            )
        elif self.material_tickers:
            out.append(
                f"ℹ️ S NÁLEZEM: {cz(self.material_pct, 1)} % portfolia "
                f"({', '.join(self.material_tickers)})"
            )

        if self.unassessed_pct > UNASSESSED_WARN_PCT:
            out.append(
                f"⚠️ NEPOSOUZENO: {cz(self.unassessed_pct, 1)} % peněz je ve firmách, "
                f"jejichž výkazy nevidím ({', '.join(self.unassessed_tickers)}). "
                f"Podíl s problémem je tedy někde mezi {cz(self.material_pct, 1)} % "
                f"a {cz(self.upper_bound_pct, 1)} % — a nenalezení tam nic neznamená"
            )
        return out


def assess(holdings: list[Holding]) -> Reading:
    """
    Sort the portfolio into what is known bad, known fine, and unknown.

    Order matters: a company with short cash counts as material even if its
    filings were never read, because the balance sheet said it in numbers and
    that needs no narrative.
    """
    reading = Reading()

    for holding in holdings:
        if not holding.value_czk:
            continue
        reading.total_czk += holding.value_czk

        short_of_cash = (
            holding.runway_months is not None and holding.runway_months < 6.0
        )
        if holding.has_material_finding or short_of_cash:
            reading.material_czk += holding.value_czk
            reading.material_tickers.append(holding.ticker)
        elif holding.assessed:
            reading.clean_czk += holding.value_czk
        else:
            reading.unassessed_czk += holding.value_czk
            reading.unassessed_tickers.append(holding.ticker)

    reading.material_tickers.sort()
    reading.unassessed_tickers.sort()
    return reading
