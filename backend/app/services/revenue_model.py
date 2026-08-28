"""
Analytikovy modely tržeb vs. realita.

Účel: uložit cizí bottom-up model (Mark Gomes občas publikuje modely typu
"28 produktových řádků × kusy × cena, po letech") a jakmile dorazí skutečné
číslo z výkazů, ukázat vedle sebe, co model předpověděl a co firma nahlásila.
Cíl není postavit vlastní model — je zjistit, na čem takový model staví a
jestli se jeho odhady typicky trefují.

Žádná síť, žádný LLM. `period_totals()` je čistý součet toho, co je v DB.
`compare_to_actual()` dostane už načtenou `Fundamentals` (viz sec_fundamentals)
zvenčí — sám si nic nestahuje, aby šel testovat bez SEC.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from .sec_fundamentals import Fundamentals, Series

#: Rozpozná období jako čistý rok ("2025", "FY2026" -> 2026).
_YEAR_RE = re.compile(r"^(?:FY)?\s*(\d{4})$", re.IGNORECASE)

#: Rozpozná období jako datum konce čtvrtletí ve tvaru m/d/yy nebo m/d/yyyy.
_QUARTER_DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})$")


@dataclass(frozen=True)
class PeriodTotal:
    period_label: str
    total: float
    currency: str
    #: Kolik řádků má confidence=None — appka to sama nepřečetla z originálu.
    unrated_lines: int
    line_count: int


@dataclass(frozen=True)
class PeriodComparison:
    period_label: str
    model_total: float
    currency: str
    actual: float | None
    variance_pct: float | None
    #: Proč actual chybí, když chybí — pojmenovaná mezera, ne tiché nic.
    gap_cs: str | None


def _parse_period(period_label: str) -> tuple[str, int | date]:
    """Vrátí ('year', 2025) nebo ('date', date(...)); jinak vyhodí ValueError."""
    m = _YEAR_RE.match(period_label.strip())
    if m:
        return ("year", int(m.group(1)))
    m = _QUARTER_DATE_RE.match(period_label.strip())
    if m:
        month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if year < 100:
            year += 2000
        return ("date", date(year, month, day))
    raise ValueError(f"Období '{period_label}' nejde rozpoznat jako rok ani datum.")


def period_totals(model) -> list[PeriodTotal]:
    """
    Součet řádků modelu po období, v pořadí jak se objevují poprvé.

    Sčítá jen měny, které se shodují s tou první viděnou u daného období —
    smíchat dolary a koruny do jednoho součtu by bylo tiché falšování čísla.
    """
    order: list[str] = []
    by_period: dict[str, list] = {}
    for line in model.lines:
        if line.period_label not in by_period:
            order.append(line.period_label)
            by_period[line.period_label] = []
        by_period[line.period_label].append(line)

    out: list[PeriodTotal] = []
    for label in order:
        lines = by_period[label]
        currency = lines[0].currency
        total = 0.0
        unrated = 0
        for line in lines:
            if line.currency != currency:
                raise ValueError(
                    f"Období '{label}' míchá měny ({currency} a {line.currency}) "
                    f"— součet by byl nesmyslný."
                )
            resolved = line.resolved_amount()
            if resolved is not None:
                total += resolved
            if line.confidence is None:
                unrated += 1
        out.append(
            PeriodTotal(
                period_label=label,
                total=total,
                currency=currency,
                unrated_lines=unrated,
                line_count=len(lines),
            )
        )
    return out


def compare_to_actual(
    model,
    fundamentals: Fundamentals | None,
) -> list[PeriodComparison]:
    """
    Postaví model_total vedle skutečné tržby za totéž období, když ji máme.

    `fundamentals` je None, když jsme se na SEC ještě nedívali (typicky
    zahraniční firma bez XBRL, nebo jsme ji ještě nesynchronizovali) — pak
    každé období dostane gap_cs vysvětlující proč, ne nulu.
    """
    revenue: Series | None = fundamentals.get("revenue") if fundamentals else None
    results: list[PeriodComparison] = []

    for pt in period_totals(model):
        actual: float | None = None
        gap: str | None = None

        if revenue is None:
            gap = (
                "Firma ještě nemá načtené výkazy z SEC (buď nejsme "
                "synchronizovaní, nebo tam nepatří) — nelze porovnat."
            )
        else:
            try:
                kind, key = _parse_period(pt.period_label)
            except ValueError as exc:
                gap = str(exc)
            else:
                if kind == "year":
                    match = next(
                        (p for p in revenue.annual if p.fiscal_year == key or p.end.year == key),
                        None,
                    )
                    if match is None:
                        gap = f"Roční výkaz za {key} zatím nedorazil."
                    else:
                        actual = match.value
                else:  # kind == "date"
                    match = next((p for p in revenue.quarterly if p.end == key), None)
                    if match is None:
                        gap = f"Čtvrtletí končící {key.isoformat()} zatím nedorazilo."
                    else:
                        actual = match.value

        variance = None
        if actual is not None and actual != 0:
            variance = (pt.total - actual) / abs(actual) * 100

        results.append(
            PeriodComparison(
                period_label=pt.period_label,
                model_total=pt.total,
                currency=pt.currency,
                actual=actual,
                variance_pct=variance,
                gap_cs=gap,
            )
        )
    return results
