"""
Results and outlook, read from the filings themselves.

This is the signal that matters: what the company actually earned, and what it
says comes next. Insider trades are recorded elsewhere in `sec_edgar.py` and
are deliberately secondary — the canon is a fundamental method, and §4a builds
the risk/reward chart out of revenue growth and margin expectations, not out of
who bought stock last week.

The two halves are separated on purpose, because their trustworthiness differs
by an order of magnitude:

**Results are read from XBRL, not from prose.** SEC serves every reported line
item as structured, audited data. No model parses a number here, so no number
can be hallucinated — a revenue figure in this module is the one the company
filed under penalty of perjury.

**Outlook is read from the filing text**, because guidance is narrative and
lives nowhere else. That half goes through the model, and its output is
labelled as an interpretation of a document rather than as data.

The comparability trap
----------------------
XBRL returns one concept as a mixture of period lengths. TechPrecision's
`Revenues`, fetched 2026-08-22, contains in adjacent rows:

    2026-04-01 → 2026-06-30    9,096,000    one quarter
    2025-04-01 → 2026-03-31   31,644,000    a full year
    2025-04-01 → 2025-12-31   23,559,000    nine months

Sorting those by date and reading them as a trend produces "revenue fell 71 %"
out of a company that grew. Every series here is therefore split by period
length first, and a quarter is only ever compared with a quarter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Final

from loguru import logger

from app.services.sec_edgar import SecEdgarClient, SecError

COMPANY_FACTS_URL: Final[str] = (
    "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
)

#: A duration within this many days of a quarter/year counts as one. Fiscal
#: quarters are not exactly 91 days — TechPrecision's run 89 to 93 — so an
#: exact match would silently drop most of the data.
QUARTER_DAYS: Final[tuple[int, int]] = (80, 100)
ANNUAL_DAYS: Final[tuple[int, int]] = (350, 380)

#: Past this, a runway figure stops being information. A company with a small
#: quarterly outflow against a large balance computes to a hundred years of
#: runway, which says nothing anyone can act on.
RUNWAY_MEANINGLESS_MONTHS: Final[int] = 60

#: A yearly fall in share count this large is not a buyback. No company of this
#: size retires a third of its equity in a year; it is a reverse split, and
#: calling it a reduction would read as very good news about the opposite.
REVERSE_SPLIT_DROP_PCT: Final[float] = 30.0


# ==============================================================================
# The line items worth reading
# ==============================================================================

@dataclass(frozen=True)
class Concept:
    """One XBRL concept, with the alternates companies actually use."""

    key: str
    label_cs: str
    #: Tried in order. Companies tag revenue under several different names and
    #: a missing concept is not the same as a zero.
    tags: tuple[str, ...]
    #: Balance-sheet items are instants, not durations.
    is_instant: bool = False


CONCEPTS: Final[tuple[Concept, ...]] = (
    Concept("revenue", "Tržby", (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
    )),
    Concept("gross_profit", "Hrubý zisk", ("GrossProfit",)),
    Concept("operating_income", "Provozní zisk", ("OperatingIncomeLoss",)),
    Concept("net_income", "Čistý zisk", ("NetIncomeLoss",)),
    Concept("operating_cash_flow", "Provozní cash flow", (
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    )),
    Concept("cash", "Hotovost", (
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ), is_instant=True),
    Concept("shares_outstanding", "Počet akcií", (
        "CommonStockSharesOutstanding",
        "EntityCommonStockSharesOutstanding",
    ), is_instant=True),
)


# ==============================================================================
# Data
# ==============================================================================

@dataclass(frozen=True)
class Point:
    """One reported value for one period."""

    end: date
    value: float
    form: str
    start: date | None = None
    fiscal_year: int | None = None
    fiscal_period: str | None = None

    @property
    def days(self) -> int | None:
        return (self.end - self.start).days if self.start else None


@dataclass
class Series:
    """One concept, split so that only comparable periods sit together."""

    key: str
    label_cs: str
    unit: str
    tag: str
    quarterly: list[Point] = field(default_factory=list)
    annual: list[Point] = field(default_factory=list)
    instant: list[Point] = field(default_factory=list)

    @property
    def latest_quarter(self) -> Point | None:
        return self.quarterly[0] if self.quarterly else None

    def year_ago_quarter(self) -> Point | None:
        """
        The same quarter one year earlier, for a like-for-like comparison.

        Quarter-on-quarter is seasonal noise for most of these companies;
        year-on-year is the comparison the filings themselves use.
        """
        latest = self.latest_quarter
        if latest is None:
            return None
        for point in self.quarterly[1:]:
            gap = (latest.end - point.end).days
            if 350 <= gap <= 380:
                return point
        return None


@dataclass
class Fundamentals:
    """Everything the filings say in numbers, plus what it adds up to."""

    ticker: str
    cik: str
    company_name: str | None = None
    series: dict[str, Series] = field(default_factory=dict)
    #: Czech sentences, each stating one fact and its source period.
    findings: list[str] = field(default_factory=list)
    #: Gaps — a concept the company does not tag, a period we cannot compare.
    gaps: list[str] = field(default_factory=list)

    def get(self, key: str) -> Series | None:
        return self.series.get(key)


# ==============================================================================
# Fetching
# ==============================================================================

def _parse_date(value: str | None) -> date | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date() if value else None
    except (ValueError, TypeError):
        return None


def _within(days: int | None, bounds: tuple[int, int]) -> bool:
    return days is not None and bounds[0] <= days <= bounds[1]


def _build_series(concept: Concept, facts: dict[str, Any]) -> Series | None:
    """
    Assemble one concept's series, splitting durations so they stay comparable.

    Returns None when the company tags none of the concept's alternates — which
    is a gap to report, not a zero to chart.
    """
    for tag in concept.tags:
        node = facts.get(tag)
        if not node:
            continue

        units = node.get("units", {})
        unit = next((u for u in units if u in ("USD", "shares")), None)
        if unit is None:
            unit = next(iter(units), None)
        if unit is None:
            continue

        series = Series(
            key=concept.key,
            label_cs=concept.label_cs,
            unit=unit,
            tag=tag,
        )

        for row in units[unit]:
            form = (row.get("form") or "").upper()
            if form not in ("10-K", "10-Q"):
                continue  # amendments and 8-Ks restate; keep the primary record
            end = _parse_date(row.get("end"))
            if end is None:
                continue

            point = Point(
                end=end,
                start=_parse_date(row.get("start")),
                value=float(row["val"]),
                form=form,
                fiscal_year=row.get("fy"),
                fiscal_period=row.get("fp"),
            )

            if point.start is None:
                series.instant.append(point)
            elif _within(point.days, QUARTER_DAYS):
                series.quarterly.append(point)
            elif _within(point.days, ANNUAL_DAYS):
                series.annual.append(point)
            # Anything else — nine-month and six-month year-to-date figures —
            # is deliberately dropped. It is real data, but it is not
            # comparable with either bucket, and mixing it in is exactly how
            # a growing company reads as a collapsing one.

        for bucket in (series.quarterly, series.annual, series.instant):
            bucket.sort(key=lambda p: p.end, reverse=True)
            # One period can be reported by several filings (a 10-K restating
            # a quarter). Keep the first, which is the most recent filing.
            seen: set[date] = set()
            bucket[:] = [p for p in bucket if not (p.end in seen or seen.add(p.end))]

        if series.quarterly or series.annual or series.instant:
            return series

    return None


def fetch_fundamentals(
    ticker: str,
    cik: str,
    *,
    client: SecEdgarClient | None = None,
) -> Fundamentals:
    """
    Read one company's reported results from XBRL.

    Raises:
        SecError: if EDGAR cannot be read. Never returns an empty
            `Fundamentals` to mean "the company reported nothing".
    """
    client = client or SecEdgarClient()
    payload = client._get(COMPANY_FACTS_URL.format(cik=cik)).json()

    facts = payload.get("facts", {}).get("us-gaap", {})
    dei = payload.get("facts", {}).get("dei", {})
    combined = {**dei, **facts}

    result = Fundamentals(
        ticker=ticker.upper(),
        cik=cik,
        company_name=payload.get("entityName"),
    )

    for concept in CONCEPTS:
        series = _build_series(concept, combined)
        if series is None:
            result.gaps.append(
                f"{concept.label_cs}: firma tuto položku ve svých výkazech "
                f"netaguje — nelze číst"
            )
            continue
        result.series[concept.key] = series

    result.findings = derive_findings(result)
    return result


# ==============================================================================
# What the numbers say
# ==============================================================================

def _fmt_money(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:,.1f} M"
    if abs(value) >= 1_000:
        return f"{value / 1_000:,.0f} tis."
    return f"{value:,.0f}"


def _pct_change(new: float, old: float) -> float | None:
    """
    Percentage change, or None when the base makes it meaningless.

    A swing from a loss to a profit has no sensible percentage — "improved by
    -340 %" is noise dressed as precision. Those are described in words.
    """
    if old == 0 or (old < 0) != (new < 0):
        return None
    return (new - old) / abs(old) * 100


def derive_findings(data: Fundamentals) -> list[str]:
    """
    Turn the series into Czech sentences, each naming the period it covers.

    Every claim carries its dates. A finding you cannot date is one you cannot
    check, and this app's job is to produce advice its owner can judge.
    """
    out: list[str] = []

    # --- Revenue, year on year -------------------------------------------
    revenue = data.get("revenue")
    if revenue and revenue.latest_quarter:
        latest = revenue.latest_quarter
        prior = revenue.year_ago_quarter()
        head = (
            f"Tržby za čtvrtletí do {latest.end:%d.%m.%Y}: "
            f"{_fmt_money(latest.value)} {revenue.unit}"
        )
        if prior is None:
            out.append(
                f"{head} — srovnatelné čtvrtletí loni ve výkazech chybí, "
                f"meziroční změnu nepočítám"
            )
        else:
            change = _pct_change(latest.value, prior.value)
            direction = "růst" if latest.value > prior.value else "pokles"
            out.append(
                f"{head}, meziročně {direction} o {abs(change):.1f} % "
                f"(z {_fmt_money(prior.value)} za čtvrtletí do "
                f"{prior.end:%d.%m.%Y})"
                if change is not None else
                f"{head} vs {_fmt_money(prior.value)} loni"
            )

    # --- Margin ----------------------------------------------------------
    gross = data.get("gross_profit")
    if revenue and gross and revenue.latest_quarter and gross.latest_quarter:
        rev_q, gp_q = revenue.latest_quarter, gross.latest_quarter
        if rev_q.end == gp_q.end and rev_q.value:
            margin = gp_q.value / rev_q.value * 100
            note = f"Hrubá marže {margin:.1f} % za čtvrtletí do {rev_q.end:%d.%m.%Y}"
            rev_prior, gp_prior = revenue.year_ago_quarter(), gross.year_ago_quarter()
            if rev_prior and gp_prior and rev_prior.end == gp_prior.end and rev_prior.value:
                prior_margin = gp_prior.value / rev_prior.value * 100
                delta = margin - prior_margin
                note += (
                    f" — meziročně {'+' if delta >= 0 else ''}{delta:.1f} p.b. "
                    f"(loni {prior_margin:.1f} %)"
                )
            out.append(note)

    # --- Profitability ---------------------------------------------------
    net = data.get("net_income")
    if net and net.latest_quarter:
        point = net.latest_quarter
        word = "zisk" if point.value >= 0 else "ztrátu"
        out.append(
            f"Za čtvrtletí do {point.end:%d.%m.%Y} firma vykázala {word} "
            f"{_fmt_money(abs(point.value))} {net.unit}"
        )

    # --- Cash and runway -------------------------------------------------
    cash = data.get("cash")
    ocf = data.get("operating_cash_flow")
    if cash and cash.instant:
        latest_cash = cash.instant[0]
        line = (
            f"Hotovost k {latest_cash.end:%d.%m.%Y}: "
            f"{_fmt_money(latest_cash.value)} {cash.unit}"
        )

        # The cash figure can be older than the results — not every filing
        # tags every concept. A stale balance says nothing about today, so it
        # gets to say how old it is.
        newest_result = revenue.latest_quarter if revenue else None
        if newest_result and (newest_result.end - latest_cash.end).days > 100:
            line += (
                f" (o {(newest_result.end - latest_cash.end).days // 30} měsíců "
                f"starší než výsledky výše — novější firma netaguje)"
            )

        if ocf and ocf.quarterly:
            burn = ocf.quarterly[0]
            if burn.value < 0:
                monthly_burn = abs(burn.value) / 3
                months = latest_cash.value / monthly_burn if monthly_burn else None
                if months is None:
                    pass
                elif months > RUNWAY_MEANINGLESS_MONTHS:
                    # Past a few years the number is arithmetic, not insight:
                    # AEHR's tiny quarterly outflow against a large balance
                    # produced "~1238 months", which is a century of false
                    # precision about a company that may not exist by then.
                    line += "; provozní odliv je proti hotovosti zanedbatelný"
                else:
                    # Canon: runway under six months is a critical downgrade.
                    urgency = " ⚠️ pod 6 měsíců" if months < 6 else ""
                    line += (
                        f"; při provozním odlivu {_fmt_money(monthly_burn)} "
                        f"měsíčně to vystačí na ~{months:.0f} měsíců{urgency}"
                    )
            else:
                line += "; provozní cash flow je kladné"
        else:
            line += " — provozní cash flow ve výkazech nenacházím, runway nepočítám"
        out.append(line)

    # --- Dilution --------------------------------------------------------
    shares = data.get("shares_outstanding")
    if shares and len(shares.instant) >= 2:
        now_pt = shares.instant[0]
        year_ago = next(
            (p for p in shares.instant[1:] if 300 <= (now_pt.end - p.end).days <= 430),
            None,
        )
        if year_ago and year_ago.value:
            change = _pct_change(now_pt.value, year_ago.value)
            if change is not None and abs(change) >= 1.0:
                if change <= -REVERSE_SPLIT_DROP_PCT:
                    # Smith Micro's count fell 71 % in a year. Described as a
                    # reduction that reads as an enormous buyback, which would
                    # be strongly bullish. It is a reverse split — the same
                    # company divided into fewer, larger shares.
                    out.append(
                        f"Počet akcií klesl o {abs(change):.1f} % "
                        f"({year_ago.value:,.0f} → {now_pt.value:,.0f} k "
                        f"{now_pt.end:%d.%m.%Y}) — takový pokles je téměř jistě "
                        f"reverzní split, ne odkup akcií. Ověř, než to budeš "
                        f"číst jako dobrou zprávu."
                    )
                else:
                    word = "zvýšil" if change > 0 else "snížil"
                    suffix = " (ředění)" if change > 0 else " (odkup)"
                    out.append(
                        f"Počet akcií se za rok {word} o {abs(change):.1f} %"
                        f"{suffix} "
                        f"({year_ago.value:,.0f} → {now_pt.value:,.0f} k "
                        f"{now_pt.end:%d.%m.%Y})"
                    )

    return out


# ==============================================================================
# Outlook
# ==============================================================================

#: What to ask the model about a filing. Kept narrow on purpose: the numbers
#: are already read exactly from XBRL, so the model is asked only for what
#: prose alone can carry — guidance, and the operational facts behind the
#: canon's cylinder count (§4b: delays, lawsuits, an executive leaving).
OUTLOOK_PROMPT: Final[str] = """\
Jsi analytik. Níže je výňatek z výroční nebo čtvrtletní zprávy firmy {ticker}
podané u SEC ({form}, období do {period}).

Zajímá mě VÝHLED, ne čísla za minulost — ta už mám přesně z XBRL.

Vrať JSON objekt s těmito klíči:

  "guidance": string nebo null — co firma říká o budoucích tržbách/zisku.
      Cituj vlastními slovy. Když ve výňatku žádný výhled není, vrať null.
      NIKDY si výhled nedomýšlej z minulých čísel.
  "guidance_direction": "RAISED" | "LOWERED" | "MAINTAINED" | "NONE"
  "orders_backlog": string nebo null — objednávky, backlog, pipeline.
  "cylinders_evidence": pole stringů — konkrétní provozní fakta, která podle
      Gomesova pravidla 10 válců zvyšují nebo snižují zdraví firmy: zpoždění,
      soudní spory, odchod vedení, ztráta zákazníka, nová smlouva, certifikace.
      Každý záznam musí být fakt uvedený v textu, ne tvůj odhad. Prázdné pole,
      když text žádné neuvádí.
  "risks_new": pole stringů — rizika, která zpráva zmiňuje jako nová nebo
      zhoršená. Ne standardní boilerplate rizika.
  "summary_cs": string — dvě až tři věty česky, co z toho plyne pro držitele
      akcie. Když text nedává podklad pro závěr, napiš to.

Pravidlo, které platí nad všemi ostatními: když informace ve výňatku není,
patří tam null nebo prázdné pole. Vymyšlený výhled je horší než žádný.

=== VÝŇATEK ===
{text}
"""


def analyze_outlook(
    text: str,
    *,
    ticker: str,
    form: str,
    period: str,
) -> dict[str, Any]:
    """
    Read guidance and operational facts out of a filing's narrative.

    Raises:
        LLMError: on any failure. Never returns a partial or empty outlook that
            a caller could mistake for "the filing said nothing".
    """
    from app.services.llm import complete_json

    return complete_json(
        OUTLOOK_PROMPT.format(
            ticker=ticker, form=form, period=period, text=text
        ),
        max_tokens=8000,
    )
