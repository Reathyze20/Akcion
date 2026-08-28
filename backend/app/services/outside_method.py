"""
Rules for the positions the method cannot value.

Eight of twelve holdings have no Green and no Red Line. The tracker carries
Gomes' picks; the portfolio also holds companies he has never drawn a chart
for. For those the band engine correctly says `MIMO_METODIKU` and stops — and
until now that meant the app had nothing at all to say about most of the money.

Silence is not neutral here. A position nobody is watching is exactly the one
that turns into a loss slowly enough that nobody notices.

What can be said without a valuation band
-----------------------------------------
Not "is this cheap" — that question needs the lines and there is no honest way
around it. But several of the canon's rules never needed a band in the first
place, and the filings answer questions of their own:

  * **Doubling** (§5). Twice what you paid is twice what you paid, whatever the
    company is worth. Already implemented; it simply must not be switched off
    by a missing band.
  * **Runway.** Under six months of cash is a fact about survival, not about
    price. It is the numeric half of "going concern".
  * **Drawdown from the position's own high.** No band required: this is about
    what the holding has done to the owner, not about what the business is
    worth.
  * **Weight.** A company nobody can value should not be a large share of the
    portfolio, however well it has done.

None of these produce a BUY. They cannot: buying needs a valuation and there
isn't one. They produce a reason to look, or a reason to take money off the
table — which is the asymmetry this whole app is built on.
"""

from __future__ import annotations

from app.core.czech import d as cz_date, months as cz_months, n as cz

from dataclasses import dataclass
from datetime import date
from typing import Final

#: Under this, the company is spending its way out of existence and the
#: question stops being about valuation. Same threshold the cylinder rubric
#: uses, and the same one `core/gomes_compliance.py` refuses purchases on.
RUNWAY_CRITICAL_MONTHS: Final[float] = 6.0

#: Between here and the critical line, a company is fundable but not
#: comfortable — worth reading, not worth acting on by itself.
RUNWAY_TIGHT_MONTHS: Final[float] = 12.0

#: A fall this far from the position's own high-water mark is worth re-reading
#: the thesis for. Not a stop: the canon buys falling prices near the Green
#: Line on purpose, and a stop would sell exactly what it means to buy. This is
#: a prompt to look, and it says so.
DRAWDOWN_REVIEW_PCT: Final[float] = 40.0

#: A company the method cannot value has no business being a large part of the
#: portfolio. Deliberately looser than the speculative tier cap of 2 %: this is
#: not a verdict about the company, only about how much of the portfolio should
#: rest on something the app cannot judge.
UNVALUED_WEIGHT_PCT: Final[float] = 8.0

SEVERITY_EXIT = "EXIT"        # take the money off the table
SEVERITY_REVIEW = "REVIEW"    # read the thesis again
SEVERITY_NOTE = "NOTE"        # worth knowing, not worth acting on


@dataclass(frozen=True)
class Finding:
    """One thing that can be said about a position without valuing it."""

    ticker: str
    severity: str
    message_cs: str

    @property
    def is_exit(self) -> bool:
        return self.severity == SEVERITY_EXIT


@dataclass(frozen=True)
class UnvaluedPosition:
    """What is known about a holding with no band."""

    ticker: str
    weight_pct: float | None = None
    runway_months: float | None = None
    runway_as_of: date | None = None
    #: Highest price the app has ever seen for this position, and today's.
    high_water: float | None = None
    current_price: float | None = None
    #: Whether SEC covers the company at all. "Nothing found" means nothing
    #: when nobody looked.
    sec_covered: bool = False


def assess(position: UnvaluedPosition) -> list[Finding]:
    """
    Everything that can honestly be said about one unvalued holding.

    Ordered by severity, worst first. An empty list means nothing is wrong that
    this module can see — which is different from nothing being wrong, and the
    caller says so.
    """
    findings: list[Finding] = []

    findings.extend(_runway(position))
    findings.extend(_drawdown(position))
    findings.extend(_weight(position))

    order = {SEVERITY_EXIT: 0, SEVERITY_REVIEW: 1, SEVERITY_NOTE: 2}
    return sorted(findings, key=lambda f: order.get(f.severity, 9))


def _runway(p: UnvaluedPosition) -> list[Finding]:
    if p.runway_months is None:
        if not p.sec_covered:
            return [
                Finding(
                    p.ticker, SEVERITY_NOTE,
                    "runway neznám — firma nepodává tam, kam vidím, takže o její "
                    "hotovosti nevím nic; není to dobrá zpráva, je to prázdné místo",
                )
            ]
        return []

    # Datum česky: 30. 6. 2026, ne 30.06.2026. Stejná věta, stejná obrazovka.
    when = f" (k {cz_date(p.runway_as_of)})" if p.runway_as_of else ""
    if p.runway_months < RUNWAY_CRITICAL_MONTHS:
        return [
            Finding(
                p.ticker, SEVERITY_EXIT,
                f"hotovost vydrží {cz_months(p.runway_months)}{when} — pod "
                f"{cz(RUNWAY_CRITICAL_MONTHS, 0)} měsíci už nejde o cenu, ale o to, "
                f"jestli firma další rok přežije bez ředění",
            )
        ]
    if p.runway_months < RUNWAY_TIGHT_MONTHS:
        return [
            Finding(
                p.ticker, SEVERITY_REVIEW,
                f"hotovost vydrží {cz_months(p.runway_months)}{when} — do roka "
                f"bude firma potřebovat peníze odjinud",
            )
        ]
    return []


def _drawdown(p: UnvaluedPosition) -> list[Finding]:
    """
    How far the holding is off its own high.

    Not a stop. The canon buys falling prices near the Green Line on purpose,
    so a stop here would sell precisely what the method means to buy. Without a
    band there is no way to tell those apart, and the honest output is a prompt
    to look rather than an instruction.
    """
    if not p.high_water or not p.current_price or p.high_water <= 0:
        return []

    fall = (p.high_water - p.current_price) / p.high_water * 100.0
    if fall < DRAWDOWN_REVIEW_PCT:
        return []

    return [
        Finding(
            p.ticker, SEVERITY_REVIEW,
            f"je {cz(fall, 0)} % pod svým maximem ({p.high_water:g} → "
            f"{p.current_price:g}) — bez pásma nepoznám, jestli je to "
            f"příležitost nebo rozbitá teze; přečti si ji znovu",
        )
    ]


def _weight(p: UnvaluedPosition) -> list[Finding]:
    if p.weight_pct is None or p.weight_pct <= UNVALUED_WEIGHT_PCT:
        return []
    return [
        Finding(
            p.ticker, SEVERITY_REVIEW,
            f"drží {cz(p.weight_pct, 1)} % portfolia a nemá ocenění — o téhle "
            f"části peněz aplikace neumí říct vůbec nic",
        )
    ]
