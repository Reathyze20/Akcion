"""
Válce — operational health 0-10, proposed from facts, confirmed by the owner.

What this unblocks
------------------
`deserved_score = 10 − cylinders` (GOMES_METHODOLOGY_CANON.md §4b) is one half
of every buy decision, and `GomesGatekeeper` refuses a purchase outright when
cylinders are unknown. They have been unknown for every company since the app
was written: the only writer was `StockLifecycleClassifier.classify()`, which
hardcodes `cylinders_count=None`. The engine could therefore never emit a BUY,
and the whole buy branch of the Daily Action engine was unreachable code.

Not a model's guess
-------------------
An LLM asked "how healthy is this company, 0-10" would answer, fluently, every
time — including for companies it knows nothing about. That is the defect this
codebase keeps finding: an absence rendered as a confident number. So the
proposal here is arithmetic over named, dated facts, and every point carries
the sentence and the source that produced it.

Three consequences follow, and they are the design:

1. **A proposal can be refused.** Below a minimum of hard readings the answer
   is `cylinders=None` plus a list of what could not be seen. That is a worse
   answer to look at and a better one to act on.
2. **The layer is always named.** SEC XBRL is audited and quarterly. Yahoo's
   trailing-twelve-month aggregates cover the Canadian and OTC names EDGAR
   cannot see, but nobody audited them and they cannot express a year-on-year
   quarter — so a Yahoo-layer proposal is clamped to the middle of the scale
   and can never claim high confidence.
3. **Narrative is capped.** What Gomes said moves the number by at most a
   point, and never past what the numbers support. The canon is a fundamental
   method; the filings outrank the commentary.

About the thresholds
--------------------
The cut-points below (±5 % and ±15 % on revenue, ±3 p.b. on margin, 6/12/24
months of runway, 10 % dilution) are judgement, not measurement. They are set
where a microcap's quarterly noise stops and a trend starts, and they are
written here rather than buried so they can be argued with. The safety net is
not their precision: it is that the owner confirms every number before it can
authorise a purchase.

What this module cannot see yet
-------------------------------
The severity-ranked red flags from the filing TEXT — going concern, controls
declared not effective, restatements — exist only inside the Czech markdown in
`sec_filings.analysis`. They are not stored in a form anything can query, and
re-reading the filings to structure them would spend API credit on work the
subscription already covers. So they are declared as a named gap rather than
silently skipped, and `runway` carries the numeric half of the same warning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Final

from app.services.sec_fundamentals import (
    BURN_PERIOD_TOLERANCE_DAYS,
    Fundamentals,
    _monthly_burn,
    _split_between,
)

# ==============================================================================
# Where a proposal can come from
# ==============================================================================

LAYER_SEC: Final[str] = "SEC_XBRL"      # audited, quarterly, year-on-year
LAYER_RELEASE: Final[str] = "RELEASE"   # the company's own quarterly release
LAYER_YAHOO: Final[str] = "YAHOO_TTM"   # aggregated, unaudited, trailing year
LAYER_NONE: Final[str] = "NONE"

CONFIDENCE_HIGH: Final[str] = "VYSOKA"
CONFIDENCE_MEDIUM: Final[str] = "STREDNI"

#: "Unremarkable operations": the company reports, it neither grows nor
#: shrinks, it funds itself. Not a default that means "we do not know" — that
#: case returns no proposal at all.
BASE: Final[int] = 5

#: Below this many hard readings there is no proposal. Two is deliberately low:
#: the owner confirms every number anyway, and refusing to speak about a
#: company he holds helps nobody. What it rules out is a number built from
#: nothing but somebody's opinion.
MIN_HARD_READINGS: Final[int] = 2

#: Enough separate audited readings to claim the top confidence band.
HIGH_CONFIDENCE_READINGS: Final[int] = 4

#: Yahoo's trailing aggregates cannot express a year-on-year quarter and nobody
#: audited them. They are enough to tell a solvent company from a struggling
#: one, not enough to justify the ends of the scale.
YAHOO_FLOOR: Final[int] = 3
YAHOO_CEILING: Final[int] = 7

#: The company's own release is narrower than a filing and wider than a
#: trailing aggregate, and the band says exactly how.
#:
#: The ceiling is the lower of the two ends because of what a release leaves
#: out rather than what it says: no operating cash flow and no share count in
#: any of the four read so far, which are the two facts that kill a microcap.
#: A source that cannot see dilution or burn is not allowed to call a company
#: excellent. Eight is "clearly working", and that is as far as it goes.
#:
#: The floor sits below Yahoo's because a release *can* see a collapse — a
#: quarter's revenue against the same quarter last year, stated by the company
#: — where a trailing twelve-month aggregate smears it. A source that would be
#: believed about good news has to be allowed to deliver bad.
RELEASE_FLOOR: Final[int] = 2
RELEASE_CEILING: Final[int] = 8

#: Total influence of everything that is somebody's opinion rather than a
#: reported number. The canon is a fundamental method (§1).
SOFT_CAP: Final[int] = 2

# --- thresholds, all judgement, all argued with in the module docstring ------
REVENUE_STRONG_PCT: Final[float] = 15.0
REVENUE_WEAK_PCT: Final[float] = 5.0
MARGIN_MOVE_PP: Final[float] = 3.0
RUNWAY_CRITICAL_MONTHS: Final[float] = 6.0
RUNWAY_TIGHT_MONTHS: Final[float] = 12.0
RUNWAY_COMFORTABLE_MONTHS: Final[float] = 24.0
DILUTION_PCT: Final[float] = 10.0

#: A net margin below this is not "slightly unprofitable" — it is a company
#: spending several times what it earns, which on the trailing layer is the
#: only severity signal available. KUYA's trailing margin is −124 %; treating
#: that the same as −1 % would be the rubric refusing to see a difference the
#: owner would see instantly.
MARGIN_SEVERE_LOSS_PCT: Final[float] = -50.0

SOURCE_XBRL: Final[str] = "SEC_XBRL"
SOURCE_YAHOO: Final[str] = "YAHOO_TTM"
SOURCE_FORM4: Final[str] = "FORM4"
SOURCE_ANALYST: Final[str] = "GOMES"
SOURCE_FILING: Final[str] = "SEC_TEXT"
SOURCE_RELEASE: Final[str] = "RELEASE"

#: Balance-sheet states a release may assert. A comparison, never an amount —
#: which is what keeps it usable when the company never says which dollar.
BALANCE_CASH_EXCEEDS_DEBT: Final[str] = "CASH_EXCEEDS_DEBT"
BALANCE_DEBT_EXCEEDS_CASH: Final[str] = "DEBT_EXCEEDS_CASH"


# ==============================================================================
# Czech number and date formatting
# ==============================================================================
# These sentences are written here rather than on the front end, the same way
# the Daily Action warnings are: they have to read identically in the app, in
# an e-mail and in a log. That makes Czech convention this module's job —
# a decimal comma, and a date as "30. 6. 2026" with the month unpadded.

def _n(value: float, places: int = 1) -> str:
    """A number in Czech: decimal comma, no thousands separator."""
    return f"{value:.{places}f}".replace(".", ",")


def _d(value: date) -> str:
    """A date in Czech: day, month, year, each without a leading zero."""
    return f"{value.day}. {value.month}. {value.year}"


@dataclass(frozen=True)
class Evidence:
    """One fact, what it did to the number, and where it came from."""

    delta: int
    fact_cs: str
    source: str
    as_of: date | None = None

    @property
    def is_hard(self) -> bool:
        """Reported by the company or filed with a regulator, not said by anyone."""
        return self.source in (
            SOURCE_XBRL,
            SOURCE_YAHOO,
            SOURCE_FORM4,
            SOURCE_FILING,
            SOURCE_RELEASE,
        )


@dataclass
class CylinderProposal:
    """
    What the app thinks, why, and what it could not see.

    `cylinders is None` is a real answer and the common one at first: it says
    no purchase can be authorised for this company and names the reason.
    """

    ticker: str
    cylinders: int | None = None
    layer: str = LAYER_NONE
    confidence: str | None = None
    evidence: list[Evidence] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    #: Months of cash at the reported rate of spending. Computed here anyway
    #: for the cylinder count; exposed as a number because survival is a fact
    #: worth reading on its own — and it is the only rule that still works for
    #: a company the method cannot value at all.
    runway_months: float | None = None
    runway_as_of: date | None = None

    @property
    def deserved_score(self) -> float | None:
        """The canon's other half: 10 − cylinders (§4b)."""
        return None if self.cylinders is None else 10.0 - self.cylinders

    def summary_cs(self) -> str:
        if self.cylinders is None:
            return (
                f"{self.ticker}: kvalitu firmy neposoudím — "
                f"{'; '.join(self.unknowns) if self.unknowns else 'chybí data'}"
            )
        moves = [e for e in self.evidence if e.delta]
        return (
            f"{self.ticker}: {self.cylinders}/10 válců "
            f"({len(moves)} z {len(self.evidence)} faktů posunulo číslo, "
            f"vrstva {self.layer}, jistota {self.confidence})"
        )


@dataclass(frozen=True)
class QualityInputs:
    """
    Everything the rubric reads, gathered by the caller.

    Kept as a plain value so the rules can be tested against fixed numbers
    without a network or a database — the same reason `generate_daily_actions`
    takes a snapshot rather than a Session.
    """

    ticker: str
    as_of: date
    fundamentals: Fundamentals | None = None
    #: Material warnings the filings made about themselves, worst first.
    #: `(severity, fact_cs)` — a going concern, controls declared not
    #: effective, a restatement. Empty means either nothing material or nothing
    #: read; `filings_read` tells those apart.
    filing_findings: tuple[tuple[str, str], ...] = ()
    #: Whether any filing of this company has been analysed at all. Without it
    #: "no findings" would read as a clean bill of health for a company nobody
    #: has opened.
    filings_read: bool = False
    #: The company's own latest quarterly release, read by hand with a verbatim
    #: quote behind every number — `release_fundamentals.Release`. Used where
    #: EDGAR cannot see but the company still publishes a year-on-year
    #: comparison, which is the four Canadian holdings.
    release: Any | None = None
    #: Yahoo's cached aggregates: revenue_ttm, net_income_ttm, operating_margin,
    #: profit_margin, total_cash, total_debt. Used only where EDGAR cannot see.
    yahoo: dict[str, Any] | None = None
    #: Open-market trades only — `InsiderTransaction.signal`, which is already
    #: restricted to codes P and S. A gift or a tax withholding is not a
    #: decision and must never read as one.
    insider_buys: int = 0
    insider_sells: int = 0
    insider_data_available: bool = False
    #: What Gomes actually said, reduced to a direction. None = he has not.
    analyst_stance: str | None = None


# ==============================================================================
# The rubric
# ==============================================================================

def propose_cylinders(inputs: QualityInputs) -> CylinderProposal:
    """
    Turn what is known about a company into a cylinder count, or into a refusal.

    Pure: same inputs, same answer, no clock and no I/O.
    """
    proposal = CylinderProposal(ticker=inputs.ticker.upper())

    hard: list[Evidence] = []
    soft: list[Evidence] = []

    # Best source first, but a source only claims the layer if it actually said
    # something. A company that files with EDGAR and tags none of the concepts
    # this rubric reads used to stop here with an empty SEC layer, while its own
    # quarterly release sat unread one line below — the better source blocking
    # the usable one. Intermap is exactly that shape.
    financial: list[Evidence] = []
    available: list[str] = []

    if inputs.fundamentals is not None:
        available.append("SEC")
        financial = _from_xbrl(inputs.fundamentals, inputs.as_of, proposal.unknowns)
        if financial:
            proposal.layer = LAYER_SEC

    if not financial and getattr(inputs.release, "has_anything", False):
        # Above Yahoo, below a filing. Layers are never mixed: a count built
        # half from a release and half from a trailing aggregate would have no
        # honest confidence to report.
        available.append("tiskovka")
        financial = _from_release(inputs.release, proposal.unknowns)
        if financial:
            proposal.layer = LAYER_RELEASE

    if not financial and inputs.yahoo:
        available.append("Yahoo")
        financial = _from_yahoo(inputs.yahoo, inputs.as_of)
        if financial:
            proposal.layer = LAYER_YAHOO
            proposal.unknowns.append(
                "SEC na tuhle firmu nedosáhne — čísla jsou roční souhrny z Yahoo, "
                "neauditované; meziroční srovnání čtvrtletí ani ředění z nich nevyčtu"
            )

    if not financial:
        proposal.unknowns.append(
            "žádná finanční data — firma nepodává u SEC a ani Yahoo o ní nic nemá"
            if not available
            else f"žádná finanční data — {', '.join(available)} o ní nic použitelného nemá"
        )

    hard.extend(financial)

    hard.extend(_from_findings(inputs, proposal.unknowns))
    hard.extend(_from_insiders(inputs, proposal.unknowns))
    soft.extend(_from_analyst(inputs))

    # The narrative never outweighs the numbers.
    soft_total = _clamp(sum(e.delta for e in soft), -SOFT_CAP, SOFT_CAP)

    proposal.evidence = hard + soft
    if inputs.fundamentals is not None:
        measured = runway_months(inputs.fundamentals)
        if measured is not None:
            proposal.runway_months, proposal.runway_as_of = measured

    readings = [e for e in hard if e.is_hard]
    if len(readings) < MIN_HARD_READINGS:
        proposal.unknowns.insert(
            0,
            f"jen {len(readings)} tvrdých údajů, potřebuji aspoň {MIN_HARD_READINGS}",
        )
        return proposal

    raw = BASE + sum(e.delta for e in hard) + soft_total

    if proposal.layer == LAYER_YAHOO:
        proposal.cylinders = _clamp(raw, YAHOO_FLOOR, YAHOO_CEILING)
        proposal.confidence = CONFIDENCE_MEDIUM
    elif proposal.layer == LAYER_RELEASE:
        proposal.cylinders = _clamp(raw, RELEASE_FLOOR, RELEASE_CEILING)
        # Never HIGH, however many readings the release carries. It is the
        # company's own selection of its own numbers, and it omits cash flow.
        proposal.confidence = CONFIDENCE_MEDIUM
    else:
        proposal.cylinders = _clamp(raw, 0, 10)
        proposal.confidence = (
            CONFIDENCE_HIGH
            if len(readings) >= HIGH_CONFIDENCE_READINGS
            else CONFIDENCE_MEDIUM
        )

    return proposal


# ==============================================================================
# Audited numbers
# ==============================================================================

def _from_xbrl(
    data: Fundamentals, as_of: date, unknowns: list[str]
) -> list[Evidence]:
    """Everything the company filed, read only in comparable periods."""
    out: list[Evidence] = []

    revenue = data.get("revenue")
    out.extend(_revenue_evidence(revenue, unknowns))
    out.extend(_margin_evidence(revenue, data.get("gross_profit")))
    out.extend(_cash_flow_evidence(data.get("operating_cash_flow")))
    out.extend(_runway_evidence(data, as_of, unknowns))
    out.extend(_dilution_evidence(data.get("shares_outstanding")))
    return out


def _revenue_evidence(revenue, unknowns: list[str]) -> list[Evidence]:
    if revenue is None or revenue.latest_quarter is None:
        unknowns.append("tržby: firma je ve výkazech netaguje")
        return []

    latest = revenue.latest_quarter
    prior = revenue.year_ago_quarter()
    if prior is None or not prior.value:
        # The comparability trap this module refuses to fall into: comparing a
        # quarter with a nine-month span turns growth into collapse.
        unknowns.append(
            f"tržby: srovnatelné čtvrtletí o rok dřív ve výkazech chybí "
            f"(nejnovější končí {_d(latest.end)}) — meziroční změnu nepočítám"
        )
        return []

    change = (latest.value - prior.value) / abs(prior.value) * 100.0
    if change >= REVENUE_STRONG_PCT:
        delta, word = 2, "silný růst"
    elif change >= REVENUE_WEAK_PCT:
        delta, word = 1, "růst"
    elif change <= -REVENUE_STRONG_PCT:
        delta, word = -2, "silný pokles"
    elif change <= -REVENUE_WEAK_PCT:
        delta, word = -1, "pokles"
    else:
        delta, word = 0, "beze změny"

    return [
        Evidence(
            delta=delta,
            fact_cs=(
                f"Tržby meziročně {word} o {_n(abs(change))} % "
                f"(čtvrtletí do {_d(latest.end)} proti {_d(prior.end)})"
            ),
            source=SOURCE_XBRL,
            as_of=latest.end,
        )
    ]


def _margin_evidence(revenue, gross) -> list[Evidence]:
    if revenue is None or gross is None:
        return []
    rev_q, gp_q = revenue.latest_quarter, gross.latest_quarter
    if rev_q is None or gp_q is None or rev_q.end != gp_q.end or not rev_q.value:
        return []

    margin = gp_q.value / rev_q.value * 100.0
    rev_prior, gp_prior = revenue.year_ago_quarter(), gross.year_ago_quarter()
    if (
        rev_prior is None
        or gp_prior is None
        or rev_prior.end != gp_prior.end
        or not rev_prior.value
    ):
        return []

    delta_pp = margin - (gp_prior.value / rev_prior.value * 100.0)
    if delta_pp >= MARGIN_MOVE_PP:
        delta = 1
    elif delta_pp <= -MARGIN_MOVE_PP:
        delta = -1
    else:
        delta = 0

    return [
        Evidence(
            delta=delta,
            fact_cs=(
                f"Hrubá marže {_n(margin)} % za čtvrtletí do {_d(rev_q.end)}, "
                f"meziročně {'+' if delta_pp >= 0 else ''}{_n(delta_pp)} p.b."
            ),
            source=SOURCE_XBRL,
            as_of=rev_q.end,
        )
    ]


def _cash_flow_evidence(ocf) -> list[Evidence]:
    """
    Whether the business funds itself. The single most load-bearing fact about
    a microcap: a company that generates cash chooses its own timing, one that
    does not is on somebody else's.
    """
    if ocf is None or ocf.latest_quarter is None:
        return []
    point = ocf.latest_quarter
    positive = point.value > 0
    return [
        Evidence(
            delta=1 if positive else -1,
            fact_cs=(
                f"Provozní cash flow za čtvrtletí do {_d(point.end)} "
                f"{'kladné' if positive else 'záporné'}"
            ),
            source=SOURCE_XBRL,
            as_of=point.end,
        )
    ]


def runway_months(data: Fundamentals) -> tuple[float, date] | None:
    """
    Months of cash at the reported rate of spending, with the balance date.

    None when the company generates cash (the runway does not apply) or when no
    reported spending period lines up with the balance — two different answers
    the caller has to tell apart, which is why the evidence path checks the
    cash-flow sign separately.
    """
    cash = data.get("cash")
    ocf = data.get("operating_cash_flow")
    if cash is None or not cash.instant:
        return None

    balance = cash.instant[0]
    burn = _monthly_burn(ocf, balance.end)
    if burn is None:
        return None

    monthly, _period = burn
    return balance.value / monthly, balance.end


def _runway_evidence(
    data: Fundamentals, as_of: date, unknowns: list[str]
) -> list[Evidence]:
    """
    How long the cash lasts at the reported rate of spending.

    This is also the numeric half of "going concern": the filings say it in
    prose, the balance sheet says it in months, and only the second is stored
    in a form anything can read today.
    """
    cash = data.get("cash")
    ocf = data.get("operating_cash_flow")
    if cash is None or not cash.instant:
        unknowns.append("hotovost: ve výkazech není — runway nespočítám")
        return []

    balance = cash.instant[0]
    burn = _monthly_burn(ocf, balance.end)

    if burn is None:
        # `_monthly_burn` returns None for two different reasons and they are
        # opposite news: the company generated cash, or no reported period
        # lines up with the balance date. Collapsing them would file a
        # self-funding company under "we could not tell".
        latest_ocf = ocf.latest_quarter if ocf is not None else None
        if latest_ocf is not None and latest_ocf.value >= 0:
            return [
                Evidence(
                    # Zero, not plus one: the cash generation itself is already
                    # counted by `_cash_flow_evidence`, and paying twice for one
                    # fact is how a rubric drifts upward without new evidence.
                    delta=0,
                    fact_cs=(
                        f"Firma v období do {_d(latest_ocf.end)} hotovost "
                        f"nespotřebovávala — runway se neuplatní"
                    ),
                    source=SOURCE_XBRL,
                    as_of=balance.end,
                )
            ]
        unknowns.append(
            f"runway: k hotovosti k {_d(balance.end)} nesedí žádné vykázané "
            f"období spotřeby (tolerance {BURN_PERIOD_TOLERANCE_DAYS} dní) — nepočítám"
        )
        return []

    # Already a positive magnitude of monthly outflow — the sign was resolved
    # upstream, and re-deriving it here is how the two ends get out of step.
    monthly, _period = burn
    months = balance.value / monthly
    if months < RUNWAY_CRITICAL_MONTHS:
        delta = -2
    elif months < RUNWAY_TIGHT_MONTHS:
        delta = -1
    elif months >= RUNWAY_COMFORTABLE_MONTHS:
        delta = 1
    else:
        delta = 0

    return [
        Evidence(
            delta=delta,
            fact_cs=(
                f"Hotovost vydrží {months:.0f} měsíců při tempu spotřeby "
                f"vykázaném k {_d(balance.end)}"
            ),
            source=SOURCE_XBRL,
            as_of=balance.end,
        )
    ]


def _dilution_evidence(shares) -> list[Evidence]:
    """
    A rising share count is the owner's stake shrinking.

    Guarded by `_split_between`: Smith Micro's count fell 71 % in a year and
    that was a 1-for-5 reverse split to escape a delisting, not a buyback.
    Read the wrong way it would have been the single most positive fact in the
    whole rubric about one of the weakest companies in the portfolio.
    """
    if shares is None or len(shares.instant) < 2:
        return []

    newer = shares.instant[0]
    older = next(
        (p for p in shares.instant[1:] if 300 <= (newer.end - p.end).days <= 430),
        None,
    )
    if older is None or not older.value:
        return []

    if _split_between(shares, newer, older):
        return [
            Evidence(
                delta=0,
                fact_cs=(
                    f"Počet akcií se mezi {_d(older.end)} a "
                    f"{_d(newer.end)} skokově změnil — vypadá to na split, "
                    f"ne na ředění ani na odkup; do hodnocení nepočítám"
                ),
                source=SOURCE_XBRL,
                as_of=newer.end,
            )
        ]

    change = (newer.value - older.value) / older.value * 100.0
    delta = -1 if change >= DILUTION_PCT else 0
    if change < DILUTION_PCT and change > -DILUTION_PCT:
        return []

    word = "vzrostl" if change > 0 else "klesl"
    return [
        Evidence(
            delta=delta,
            fact_cs=(
                f"Počet akcií meziročně {word} o {_n(abs(change))} % "
                f"(k {_d(newer.end)})"
            ),
            source=SOURCE_XBRL,
            as_of=newer.end,
        )
    ]


# ==============================================================================
# The weaker layer — where EDGAR cannot see
# ==============================================================================

def _from_yahoo(yahoo: dict[str, Any], as_of: date) -> list[Evidence]:
    """
    Solvency and profitability from trailing aggregates.

    Enough to separate a company that earns money and holds more cash than debt
    from one that does neither. Not enough to see a trend, which is why the
    result is clamped away from both ends of the scale.
    """
    out: list[Evidence] = []

    margin = yahoo.get("profit_margin")
    if margin is not None:
        pct = float(margin) * 100.0
        if pct > 0:
            delta = 1
        elif pct <= MARGIN_SEVERE_LOSS_PCT:
            delta = -2
        else:
            delta = -1
        out.append(
            Evidence(
                delta=delta,
                fact_cs=(
                    f"Čistá marže za posledních 12 měsíců {_n(pct)} % "
                    f"(souhrn z Yahoo, neauditováno)"
                ),
                source=SOURCE_YAHOO,
                as_of=as_of,
            )
        )

    cash = yahoo.get("total_cash")
    debt = yahoo.get("total_debt")
    if cash is not None and debt is not None:
        cash_f, debt_f = float(cash), float(debt)
        if cash_f > debt_f:
            delta, word = 1, "víc hotovosti než dluhu"
        elif debt_f > 0 and cash_f < debt_f / 2:
            delta, word = -1, "dluh výrazně převyšuje hotovost"
        else:
            delta, word = 0, "hotovost a dluh zhruba vyrovnané"
        out.append(
            Evidence(
                delta=delta,
                fact_cs=f"Rozvaha: {word} (souhrn z Yahoo, neauditováno)",
                source=SOURCE_YAHOO,
                as_of=as_of,
            )
        )

    return out


def _from_release(release: Any, unknowns: list[str]) -> list[Evidence]:
    """
    The company's own quarterly release, for the filers EDGAR cannot see.

    Every reading here is a ratio, a move in points or a sign, never an amount.
    Three of the four releases read so far write `$` without saying which
    dollar, and a percentage does not care — see `release_fundamentals` for why
    that is a correctness rule and not a courtesy.

    What the release cannot say is recorded rather than skipped. `absent` is the
    company's own silence about operating cash flow and share count, and it goes
    straight into `unknowns` so the reason a runway is missing is on the screen
    next to the number.
    """
    out: list[Evidence] = []
    period = release.period_end
    label = release.fiscal_label or _d(period)

    revenue = release.readings.get("revenue_yoy_pct")
    if revenue is not None:
        change = float(revenue.value)
        if change >= REVENUE_STRONG_PCT:
            delta, word = 2, "silný růst"
        elif change >= REVENUE_WEAK_PCT:
            delta, word = 1, "růst"
        elif change <= -REVENUE_STRONG_PCT:
            delta, word = -2, "silný pokles"
        elif change <= -REVENUE_WEAK_PCT:
            delta, word = -1, "pokles"
        else:
            delta, word = 0, "beze změny"
        out.append(
            Evidence(
                delta=delta,
                fact_cs=(
                    f"Tržby meziročně {word} o {_n(abs(change))} % "
                    f"({label}, {revenue.basis_months} měs., údaj firmy)"
                ),
                source=SOURCE_RELEASE,
                as_of=period,
            )
        )
    else:
        unknowns.append(
            "meziroční změna tržeb: firma ji v tiskovce neuvedla a ze dvou "
            "absolutních čísel ji nepočítám"
        )

    # Gross margin if the company published one, operating margin if it did
    # not. Never both: they measure different things and adding them would
    # count one company's margin move twice. RADCOM reports only the operating
    # line, the Canadians only the gross one.
    margin = release.readings.get("gross_margin_pct")
    margin_word = "Hrubá marže"
    if margin is None or margin.prior is None:
        margin = release.readings.get("operating_margin_pct")
        margin_word = "Provozní marže"

    if margin is not None and margin.prior is not None:
        now, before = float(margin.value), float(margin.prior)
        delta_pp = now - before
        if delta_pp >= MARGIN_MOVE_PP:
            delta = 1
        elif delta_pp <= -MARGIN_MOVE_PP:
            delta = -1
        else:
            delta = 0
        out.append(
            Evidence(
                delta=delta,
                fact_cs=(
                    f"{margin_word} {_n(now)} %, meziročně "
                    f"{'+' if delta_pp >= 0 else ''}{_n(delta_pp)} p.b. "
                    f"({label}, {margin.basis_months} měs., údaj firmy)"
                ),
                source=SOURCE_RELEASE,
                as_of=period,
            )
        )

    bottom = release.readings.get("bottom_line")
    if bottom is not None:
        profit = str(bottom.value).upper() == "PROFIT"
        out.append(
            Evidence(
                # Half the weight of the cash-flow reading it stands in for.
                # An accounting result is not cash: D-BOX's record net profit
                # this quarter is mostly a deferred tax asset, and a mine in
                # ramp-up can widen its loss while funding itself.
                delta=1 if profit else -1,
                fact_cs=(
                    f"Účetní výsledek {'kladný' if profit else 'ztráta'} "
                    f"({label}, {bottom.basis_months} měs., údaj firmy — "
                    f"není to cash flow)"
                ),
                source=SOURCE_RELEASE,
                as_of=period,
            )
        )

    # Cash against debt, when the release states both. Currency-neutral like
    # everything else here, because it is a comparison of two amounts in the
    # same currency rather than an amount. The same reading the Yahoo layer
    # already makes, and the reason it matters: a bad quarter at a company
    # holding no debt and years of cash is a different fact from the same
    # quarter at one financed by a lender.
    balance = release.readings.get("balance")
    if balance is not None:
        state = str(balance.value).upper()
        if state == BALANCE_CASH_EXCEEDS_DEBT:
            delta, word = 1, "víc hotovosti než dluhu"
        elif state == BALANCE_DEBT_EXCEEDS_CASH:
            delta, word = -1, "dluh výrazně převyšuje hotovost"
        else:
            delta, word = 0, "hotovost a dluh zhruba vyrovnané"
        out.append(
            Evidence(
                delta=delta,
                fact_cs=f"Rozvaha: {word} ({label}, údaj firmy)",
                source=SOURCE_RELEASE,
                as_of=period,
            )
        )

    for missing in release.absent:
        unknowns.append(f"{missing}: v tiskovce firmy není")

    if not release.currency:
        unknowns.append(
            "měna: tiskovka ji neuvádí, takže se skórují jen údaje nezávislé "
            "na měně (procenta, procentní body, znaménko)"
        )

    unknowns.append(
        f"vrstva tiskovky: čísla jsou firemní výběr, neauditovaný "
        f"({release.source_url})"
    )
    return out


# ==============================================================================
# Filed with a regulator, but not a financial statement
# ==============================================================================

def _from_insiders(inputs: QualityInputs, unknowns: list[str]) -> list[Evidence]:
    """
    Open-market insider trades only.

    `InsiderTransaction.signal` is already restricted to codes P and S, which
    are the only two that involve a decision to transact at a market price. A
    gift, a tax withholding, an option exercise and a grant are all disposals
    or acquisitions that mean nothing about the business.
    """
    if not inputs.insider_data_available:
        unknowns.append("insider obchody: u téhle firmy je nemám")
        return []

    if inputs.insider_buys > 0:
        return [
            Evidence(
                delta=1,
                fact_cs=(
                    f"Insideři za posledního půl roku {inputs.insider_buys}× "
                    f"nakupovali na trhu"
                ),
                source=SOURCE_FORM4,
                as_of=inputs.as_of,
            )
        ]
    if inputs.insider_sells > 0:
        return [
            Evidence(
                delta=-1,
                fact_cs=(
                    f"Insideři za posledního půl roku {inputs.insider_sells}× "
                    f"prodávali na trhu a ani jednou nekupovali"
                ),
                source=SOURCE_FORM4,
                as_of=inputs.as_of,
            )
        ]
    return [
        Evidence(
            delta=0,
            fact_cs="Insideři za posledního půl roku na trhu neobchodovali",
            source=SOURCE_FORM4,
            as_of=inputs.as_of,
        )
    ]


# ==============================================================================
# What somebody said
# ==============================================================================

def _from_analyst(inputs: QualityInputs) -> list[Evidence]:
    """Gomes' own read, worth a point and never more."""
    stance = (inputs.analyst_stance or "").upper()
    if stance == "BULLISH":
        return [Evidence(1, "Gomes se k firmě vyjádřil kladně", SOURCE_ANALYST, inputs.as_of)]
    if stance == "BEARISH":
        return [Evidence(-1, "Gomes se k firmě vyjádřil záporně", SOURCE_ANALYST, inputs.as_of)]
    return []


def _clamp(value: float, low: float, high: float) -> int:
    return int(max(low, min(high, value)))


# ==============================================================================
# What the filings said about themselves
# ==============================================================================

#: A filing questioning whether the company continues is worth two cylinders on
#: its own. Nothing else in this rubric moves the number that far, and nothing
#: else should: it is the company's own auditors saying the rest of the
#: arithmetic may be beside the point.
FINDING_CRITICAL_DELTA: Final[int] = -2
FINDING_HIGH_DELTA: Final[int] = -1

#: However many material warnings a filing carries, this is as far as they move
#: the number. Past it the company is unbuyable on any of the other gates
#: anyway, and a rubric that can reach zero on findings alone stops
#: distinguishing between bad and catastrophic.
FINDINGS_FLOOR: Final[int] = -3


def _from_findings(inputs: QualityInputs, unknowns: list[str]) -> list[Evidence]:
    """
    Going concern, controls not effective, restatements — read as data at last.

    `analyze_outlook` has always extracted these with a severity and a verbatim
    quote, and always rendered them into a markdown blob nothing could query.
    SMSI and ECOR both carry going-concern warnings and both were assessed
    without either one.
    """
    if not inputs.filings_read:
        unknowns.append(
            "nálezy z textu podání: nemám je ve strukturované podobě — going "
            "concern ani neúčinné kontroly do čísla nevstupují. Doplní se, až "
            "se firma znovu přečte"
        )
        return []

    if not inputs.filing_findings:
        return [
            Evidence(
                delta=0,
                fact_cs="Ve čteném podání nebyl žádný materiální nález",
                source=SOURCE_FILING,
                as_of=inputs.as_of,
            )
        ]

    out: list[Evidence] = []
    spent = 0
    for severity, fact in inputs.filing_findings:
        level = (severity or "").strip().upper()
        if level == "CRITICAL":
            delta = FINDING_CRITICAL_DELTA
        elif level == "HIGH":
            delta = FINDING_HIGH_DELTA
        else:
            delta = 0

        # Capped in total, so a filing with six warnings does not drive the
        # count below what any single one of them justifies.
        if delta and spent + delta < FINDINGS_FLOOR:
            delta = min(0, FINDINGS_FLOOR - spent)
        spent += delta

        out.append(
            Evidence(
                delta=delta,
                fact_cs=fact,
                source=SOURCE_FILING,
                as_of=inputs.as_of,
            )
        )
    return out
