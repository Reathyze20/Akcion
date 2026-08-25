"""
Which of the canon's three stages a holding is in, proposed from dated facts.

The hole this fills
-------------------
On 2026-08-24 all twelve holdings carry `phase = UNKNOWN`, and the consequences
are not cosmetic:

  * `determine_tier` ends in "everything else = TERTIARY", so every position is
    held at the strictest 2 % cap regardless of its numbers, and
  * the de-risking branch refuses to sell anything at all, because an unknown
    phase is not proof that a position is speculative — it is proof of nothing.

That refusal is correct and was written on purpose: conviction is not a tier,
and the app once tried to sell its highest-conviction holding because nobody had
recorded a phase. But it means a yellow market currently produces no defensive
action whatever. Safe, and blind.

The canon's three stages (§3)
-----------------------------
  1. **Great Find** — nobody has heard of it, but it is starting to do great
     things. Being early is profitable. Risky; permitted in a green market.
  2. **Wait Time** — the hype died and the story has not gained traction. It
     retraces much of the Great Find move and takes longer than you expect.
     The canon's instruction is blunt: **do not be invested**.
  3. **Gold Mine** — momentum has started, the company is profitable or has
     strong orders. Safe to hold.

What a rubric can and cannot see
--------------------------------
Two of the three are largely arithmetic. "Profitable, revenue accelerating, not
deeply retraced" is Gold Mine; "revenue flat or falling, deeply retraced from
its own high" is Wait Time. Those are facts with dates.

**Great Find is different and the difference is honest.** Half its definition —
*nobody has heard of it* — is a statement about the market's attention, and this
app measures no such thing. So a Great Find proposal is offered only as the
residual (early positive signs, not yet profitable, no deep retrace) and always
carries a named caveat saying the obscurity half was not checked. It never
arrives at high confidence.

The same two rules as the cylinder rubric
-----------------------------------------
Not enough hard readings → **no proposal**, and the gap is named. A proposal
authorises nothing until the owner confirms it, because a phase decides whether
a position gets sold in a yellow market and that is not a decision to take from
a number nobody looked at.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Final

from app.core.czech import d as cz_date
from app.core.czech import n as cz
from app.core.czech import months as cz_months
from app.core.czech import plural as cz_plural

#: The canon's three stages, plus the honest fourth state.
GREAT_FIND: Final[str] = "GREAT_FIND"
WAIT_TIME: Final[str] = "WAIT_TIME"
GOLD_MINE: Final[str] = "GOLD_MINE"
UNKNOWN: Final[str] = "UNKNOWN"

#: Fewer hard readings than this and no proposal is made at all. A phase drives
#: selling; one number is not enough to sell a position on.
MIN_HARD_READINGS: Final[int] = 2

# ==============================================================================
# The ratchet: Gold Mine is an absorbing state
# ==============================================================================
#
# `GOMES_VIDEO_ADDENDUM.md` §V1. The one thing Gomes tells the viewer to write
# down is that a Gold Mine company having a bad run has NOT gone back to Wait
# Time:
#
#   "The fact that you go through a rough patch -- less orders, the business
#    slows down -- does NOT mean you have shifted out of Gold Mine. You've
#    already proven your product sells in the marketplace, so you're not going
#    to go back to Wait Time. Gold Mine is a long-term measure that denotes a
#    company that has graduated from being promising to being proven."
#
# So the stage is a RATCHET over the canon's sequence, not a fresh judgement
# each time the numbers are re-read. Everything below `propose_phase` is a
# reading of today; this is what turns a reading into a stage.
#
# Why this is not a loosening of safety
# -------------------------------------
# Without the ratchet, a proven holding that misses one quarter is relabelled
# WAIT_TIME, and `GomesGatekeeper` then refuses to buy it -- at the exact moment
# it is cheapest, which is the setup the whole method exists to catch. The
# caution does not disappear with the relabelling; it MOVES, to where the canon
# already put it:
#
#   * cylinders fall, so `deserved_score = 10 - cylinders` rises and the buy is
#     refused as NOT_CHEAP_ENOUGH if it is not actually cheap enough, and
#   * the rough patch is recorded as its own flag, which the guard reads.
#
# A rough patch is a temporary fact about trading, kept apart from the stage on
# purpose. Conflating the two is what this section prevents.

#: The canon's sequence (§3). Higher = further along; the stage never moves down
#: on its own. UNKNOWN is deliberately absent: it is the absence of a reading,
#: not a rung, and must never overwrite a stage that was reached.
PHASE_RANK: Final[dict[str, int]] = {
    GREAT_FIND: 1,
    WAIT_TIME: 2,
    GOLD_MINE: 3,
}


@dataclass(frozen=True)
class RatchetResult:
    """
    The stage that stands after the ratchet, and what the blocked reading meant.

    `rough_patch` is the whole point of returning a structure instead of a
    string. A Wait Time reading on a proven company is not noise to discard --
    it is a real observation that the business has slowed. It stops being a
    stage and becomes a flag, so nothing is silently swallowed.
    """

    phase: str
    #: True when today's reading argued for Wait Time on a proven Gold Mine.
    rough_patch: bool = False
    #: Why the proposal did not take effect, in Czech, for the screen.
    held_back_cs: str = ""

    @property
    def changed(self) -> bool:
        """Whether the ratchet overrode what the numbers proposed."""
        return bool(self.held_back_cs)


def apply_ratchet(proposed: str | None, reached: str | None) -> RatchetResult:
    """
    Reconcile today's reading with the furthest stage this company ever reached.

    Args:
        proposed: What the numbers argue for today, or None when they do not
            argue enough. None is not a demotion -- it is silence, and silence
            leaves the stage where it was.
        reached: The high-water stage on record (`stock_lifecycle.phase_reached`).

    The rule is monotonic over `PHASE_RANK`, which is conservative in both of
    the ordinary directions -- a Great Find whose story stalls is allowed to
    become Wait Time, and a Wait Time company does not get promoted back to
    Great Find on a good quarter. The one direction it deliberately blocks is
    GOLD_MINE -> WAIT_TIME, which is the case Gomes names.
    """
    prior = PHASE_RANK.get((reached or "").upper())
    now = PHASE_RANK.get((proposed or "").upper())

    if now is None:
        # No reading today. The stage on record stands, unchanged and unflagged.
        return RatchetResult(phase=(reached or UNKNOWN).upper())

    if prior is None or now >= prior:
        return RatchetResult(phase=proposed.upper())

    # A reading that would move the stage backwards.
    kept = (reached or "").upper()
    if kept == GOLD_MINE and proposed.upper() == WAIT_TIME:
        return RatchetResult(
            phase=GOLD_MINE,
            rough_patch=True,
            held_back_cs=(
                "Čísla dnes ukazují na čekání, ale firma už jednou prokázala, "
                "že její produkt na trhu prodává — zůstává zlatý důl a je "
                "vedená jako v přechodném útlumu. Kvalita se propíše do válců, "
                "ne do fáze."
            ),
        )

    return RatchetResult(
        phase=kept,
        held_back_cs=(
            f"Čísla dnes ukazují na {PHASE_NAMES_CS.get(proposed.upper(), proposed)}, "
            f"ale firma už dosáhla fáze "
            f"{PHASE_NAMES_CS.get(kept, kept)} — fáze cyklu se sama nevrací zpět."
        ),
    )


#: Revenue growing at least this much year on year counts as traction.
REVENUE_TRACTION_PCT: Final[float] = 10.0
#: Revenue falling by this much is the story failing to catch, not noise.
REVENUE_DECLINE_PCT: Final[float] = -5.0

#: "Retraces a large part of the Great Find move" (§3), as a fall from the
#: position's own high-water mark. Deliberately the same threshold the unvalued
#: rules use to ask for a re-read: it is the same observation.
DEEP_RETRACE_PCT: Final[float] = 40.0

#: Under this many months of cash, a company is not a Gold Mine whatever its
#: revenue line says. Momentum that runs out of money is not momentum.
RUNWAY_TIGHT_MONTHS: Final[float] = 12.0

#: Confidence never rises above this when the numbers came from annual
#: aggregates rather than quarterly filings — Yahoo does not publish a series.
LAYER_XBRL: Final[str] = "SEC_XBRL"
#: A vendor's year-on-year computation over filings the app never read.
#: Above Yahoo — a real comparison rather than a rolling total — and below
#: XBRL, where the app reads the tagged numbers and sees each period.
LAYER_FINNHUB: Final[str] = "FINNHUB"
LAYER_YAHOO: Final[str] = "YAHOO_TTM"
LAYER_NONE: Final[str] = "NONE"

CONFIDENCE_HIGH: Final[str] = "VYSOKA"
CONFIDENCE_MEDIUM: Final[str] = "STREDNI"
CONFIDENCE_LOW: Final[str] = "NIZKA"

SOURCE_XBRL: Final[str] = "SEC_XBRL"
SOURCE_FINNHUB: Final[str] = "FINNHUB"
SOURCE_YAHOO: Final[str] = "YAHOO_TTM"
SOURCE_PRICE: Final[str] = "CENA"
SOURCE_ANALYST: Final[str] = "ANALYTIK"

#: Sources reported by the company or observed directly, as opposed to said by
#: somebody. Only these count towards MIN_HARD_READINGS.
_HARD_SOURCES = frozenset({SOURCE_XBRL, SOURCE_FINNHUB, SOURCE_YAHOO, SOURCE_PRICE})


@dataclass(frozen=True)
class Signal:
    """One fact, which stage it argues for, and where it came from."""

    towards: str
    weight: int
    fact_cs: str
    source: str
    as_of: date | None = None

    @property
    def is_hard(self) -> bool:
        return self.source in _HARD_SOURCES


@dataclass(frozen=True)
class LifecycleInputs:
    """What is known about a holding, as this rubric needs to see it."""

    ticker: str
    #: Year-on-year revenue change in percent, same quarter where the filings
    #: allow it. None when nobody can compute it.
    revenue_yoy_pct: float | None = None
    #: Positive means the business generates cash. None means unknown, which is
    #: not the same as zero.
    operating_cash_flow: float | None = None
    #: Net or operating margin in percent.
    margin_pct: float | None = None
    #: Change in margin in percentage points against a year ago.
    margin_move_pp: float | None = None
    #: Months of cash at the reported burn. None when the company generates it.
    runway_months: float | None = None
    #: The peak of the stated window, in the POSITION's currency, and today's
    #: price. Reconciled by the intake — a euro price against a dollar peak
    #: reports a drawdown that is really an exchange rate.
    high_water: float | None = None
    current_price: float | None = None
    #: When that peak happened, in Czech. Printed with the drawdown, because
    #: „57 % pod maximem" and „57 % pod maximem z listopadu 2024" are
    #: different claims and only the second can be judged.
    high_water_on_cs: str | None = None
    #: Where the numbers came from.
    layer: str = LAYER_NONE
    as_of: date | None = None
    #: What a named analyst said about the stage, if anything. Never decides on
    #: its own — it is one voice beside the filings, exactly as in the cylinder
    #: rubric.
    analyst_says: str | None = None
    analyst_name: str | None = None
    analyst_on: date | None = None


@dataclass
class LifecycleProposal:
    """What the app thinks the stage is, why, and what it could not see."""

    ticker: str
    phase: str | None = None
    confidence: str | None = None
    layer: str = LAYER_NONE
    signals: list[Signal] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)

    #: Set by the ratchet (§V1), not by the signal count. `phase` is what the
    #: numbers argued for BEFORE the ratchet; `ratcheted_to` is what would
    #: actually be written. They differ only when a reading tried to move the
    #: stage backwards, and then `ratchet_note_cs` says so on the screen.
    ratcheted_to: str | None = None
    rough_patch: bool = False
    ratchet_note_cs: str = ""

    @property
    def effective_phase(self) -> str | None:
        """The stage that would be written — the ratchet's answer, not the vote."""
        return self.ratcheted_to or self.phase

    @property
    def hard_readings(self) -> int:
        return sum(1 for s in self.signals if s.is_hard)

    def score_for(self, phase: str) -> int:
        return sum(s.weight for s in self.signals if s.towards == phase)

    def summary_cs(self) -> str:
        if self.phase is None:
            return (
                f"{self.ticker}: fázi cyklu neposoudím — "
                f"{'; '.join(self.unknowns) if self.unknowns else 'chybí data'}"
            )
        line = (
            f"{self.ticker}: {PHASE_NAMES_CS[self.phase]} "
            f"({self.hard_readings} tvrdých údajů, vrstva {self.layer}, "
            f"jistota {self.confidence})"
        )
        if self.ratchet_note_cs:
            line += (
                f" → zapíše se {PHASE_NAMES_CS.get(self.effective_phase, '?')}"
                f"{' + přechodný útlum' if self.rough_patch else ''}"
            )
        return line


#: Czech names. The screen never shows GOLD_MINE.
PHASE_NAMES_CS: Final[dict[str, str]] = {
    GREAT_FIND: "objev",
    WAIT_TIME: "čekání",
    GOLD_MINE: "zlatý důl",
    UNKNOWN: "neznámá fáze",
}

#: One sentence each, for somebody who has not read the canon.
PHASE_MEANING_CS: Final[dict[str, str]] = {
    GREAT_FIND: (
        "začíná dělat dobré věci, ale ještě nevydělává — být brzo se vyplácí, "
        "a je to riskantní"
    ),
    WAIT_TIME: (
        "nadšení opadlo a příběh se zatím nechytil — kánon říká v téhle fázi "
        "nebýt investovaný"
    ),
    GOLD_MINE: "rozjelo se to, firma vydělává nebo má objednávky — dá se držet",
}


def propose_phase(inputs: LifecycleInputs) -> LifecycleProposal:
    """
    Which stage the numbers argue for, or None when they do not argue enough.

    None is a real answer and the safe one: it leaves the position unjudged
    rather than selling it on a guess.
    """
    proposal = LifecycleProposal(ticker=inputs.ticker, layer=inputs.layer)
    signals: list[Signal] = []
    unknowns: list[str] = []

    signals.extend(_revenue_signals(inputs, unknowns))
    signals.extend(_profitability_signals(inputs, unknowns))
    signals.extend(_retrace_signals(inputs, unknowns))
    signals.extend(_survival_signals(inputs))
    signals.extend(_analyst_signals(inputs))

    proposal.signals = signals
    proposal.unknowns = unknowns

    if proposal.hard_readings < MIN_HARD_READINGS:
        unknowns.insert(
            0,
            f"mám jen {proposal.hard_readings} "
            f"{cz_plural(proposal.hard_readings, 'tvrdý údaj', 'tvrdé údaje', 'tvrdých údajů')}"
            f" — na zařazení do fáze cyklu je potřeba aspoň {MIN_HARD_READINGS}",
        )
        return proposal

    scores = {
        GOLD_MINE: proposal.score_for(GOLD_MINE),
        WAIT_TIME: proposal.score_for(WAIT_TIME),
        GREAT_FIND: proposal.score_for(GREAT_FIND),
    }
    best = max(scores, key=lambda p: scores[p])
    if scores[best] <= 0:
        unknowns.insert(0, "žádný z údajů neukazuje na konkrétní fázi")
        return proposal

    # A tie is not a verdict. Two stages arguing equally means the numbers do
    # not distinguish them, and picking one would be a coin toss that sells a
    # position.
    if list(scores.values()).count(scores[best]) > 1:
        tied = [PHASE_NAMES_CS[p] for p, v in scores.items() if v == scores[best]]
        unknowns.insert(0, f"čísla se neshodnou — sedí stejně na {' i '.join(tied)}")
        return proposal

    contradiction = _contradicts_the_definition(best, inputs)
    if contradiction:
        unknowns.insert(0, contradiction)
        return proposal

    proposal.phase = best
    proposal.confidence = _confidence(proposal, best, inputs)
    return proposal


def _contradicts_the_definition(phase: str, i: LifecycleInputs) -> str | None:
    """
    Whether the winning stage is contradicted by the canon's own wording.

    Adding up weights finds which stage the evidence leans towards. It does not
    check that the stage's *definition* still holds, and two live cases showed
    why that matters:

      * **ECOR** scored Wait Time on a 41 % retrace and eight months of cash
        while its revenue grew 28 % year on year. Wait Time means "the story
        has not caught traction" (§3) — a revenue line like that falsifies the
        definition outright. A company whose business is working and whose
        price has fallen is a cheap something, not a Wait Time.
      * **INFU** scored Gold Mine on being profitable with revenue up 2,6 %.
        The canon's Gold Mine is "momentum nastartoval, firma profituje" — both
        halves. Profitable and flat is a steady business, not momentum.

    Returning a sentence means no proposal is made. That is the right outcome:
    the numbers point somewhere the definition does not allow, and the honest
    answer is to say so rather than to pick the runner-up.
    """
    if phase == WAIT_TIME:
        if i.revenue_yoy_pct is not None and i.revenue_yoy_pct >= REVENUE_TRACTION_PCT:
            return (
                f"na „čekání\" to sedí cenou, ale tržby rostou o "
                f"{cz(i.revenue_yoy_pct)} % — příběh se chytá, takže definice "
                f"čekání neplatí; posuď to sám"
            )

    if phase == GOLD_MINE:
        has_momentum = (
            i.revenue_yoy_pct is not None and i.revenue_yoy_pct >= REVENUE_TRACTION_PCT
        ) or (i.margin_move_pp is not None and i.margin_move_pp >= 3.0)
        if not has_momentum:
            moved = (
                f"tržby meziročně {cz(i.revenue_yoy_pct)} %"
                if i.revenue_yoy_pct is not None
                else "růst tržeb neznám"
            )
            return (
                f"firma vydělává, ale „zlatý důl\" je podle kánonu vydělávání "
                f"A rozjeté momentum — {moved}, takže druhá půlka definice "
                f"chybí; posuď to sám"
            )
    return None


def _source_for(layer: str) -> str:
    """Which source a number carries, so the evidence never hides its layer."""
    if layer == LAYER_XBRL:
        return SOURCE_XBRL
    if layer == LAYER_FINNHUB:
        return SOURCE_FINNHUB
    return SOURCE_YAHOO


def _revenue_signals(i: LifecycleInputs, unknowns: list[str]) -> list[Signal]:
    """
    Traction, or the lack of it. The clearest single discriminator the canon
    gives: a Gold Mine has momentum, a Wait Time story "has not caught".
    """
    if i.revenue_yoy_pct is None:
        unknowns.append("meziroční růst tržeb neznám")
        return []

    source = _source_for(i.layer)
    if i.revenue_yoy_pct >= REVENUE_TRACTION_PCT:
        return [
            Signal(
                GOLD_MINE, 2,
                f"tržby meziročně {cz(i.revenue_yoy_pct)} % — příběh se chytil",
                source, i.as_of,
            )
        ]
    if i.revenue_yoy_pct <= REVENUE_DECLINE_PCT:
        return [
            Signal(
                WAIT_TIME, 2,
                f"tržby meziročně {cz(i.revenue_yoy_pct)} % — trakce zatím není",
                source, i.as_of,
            )
        ]
    return [
        Signal(
            GREAT_FIND, 1,
            f"tržby meziročně {cz(i.revenue_yoy_pct)} % — pohyb sem tam, "
            f"ještě to nikam nevystřelilo",
            source, i.as_of,
        )
    ]


def _profitability_signals(i: LifecycleInputs, unknowns: list[str]) -> list[Signal]:
    """
    "Firma profituje" is half the canon's Gold Mine definition, and its absence
    is half of what keeps a company a Great Find rather than a Gold Mine.
    """
    out: list[Signal] = []
    source = _source_for(i.layer)

    if i.operating_cash_flow is None:
        unknowns.append("provozní cash flow neznám")
    elif i.operating_cash_flow > 0:
        out.append(
            Signal(GOLD_MINE, 2, "provoz vydělává peníze", source, i.as_of)
        )
    else:
        # Not a Wait Time signal by itself: an early company burning cash while
        # revenue accelerates is the canon's Great Find, not its Wait Time.
        out.append(
            Signal(GREAT_FIND, 1, "provoz peníze zatím spotřebovává", source, i.as_of)
        )

    if i.margin_move_pp is not None and abs(i.margin_move_pp) >= 3.0:
        if i.margin_move_pp > 0:
            out.append(
                Signal(
                    GOLD_MINE, 1,
                    f"marže meziročně o {cz(i.margin_move_pp)} p. b. výš",
                    source, i.as_of,
                )
            )
        else:
            out.append(
                Signal(
                    WAIT_TIME, 1,
                    f"marže meziročně o {cz(abs(i.margin_move_pp))} p. b. níž",
                    source, i.as_of,
                )
            )
    return out


def _retrace_signals(i: LifecycleInputs, unknowns: list[str]) -> list[Signal]:
    """
    "Retraces a large part of the Great Find move" (§3) — the one part of the
    Wait Time definition that is directly observable, and the reason the same
    threshold is used here as in the unvalued rules.
    """
    if not i.high_water or not i.current_price or i.high_water <= 0:
        unknowns.append("maximum pozice neznám, takže propad neumím změřit")
        return []

    fall = (i.high_water - i.current_price) / i.high_water * 100.0
    when = f" z {i.high_water_on_cs}" if i.high_water_on_cs else ""
    if fall >= DEEP_RETRACE_PCT:
        return [
            Signal(
                WAIT_TIME, 2,
                f"je {cz(fall, 0)} % pod maximem{when} "
                f"({cz(i.high_water, 2)} → {cz(i.current_price, 2)}) — nadšení opadlo",
                SOURCE_PRICE, i.as_of,
            )
        ]
    return [
        Signal(
            GOLD_MINE, 1,
            f"drží se {cz(fall, 0)} % pod maximem{when} — velký propad tam není",
            SOURCE_PRICE, i.as_of,
        )
    ]


def _survival_signals(i: LifecycleInputs) -> list[Signal]:
    """
    Momentum that runs out of money is not momentum. A tight runway cannot make
    a company a Gold Mine however good the revenue line looks.
    """
    if i.runway_months is None or i.runway_months >= RUNWAY_TIGHT_MONTHS:
        return []
    return [
        Signal(
            WAIT_TIME, 1,
            f"hotovost vydrží zhruba {cz_months(i.runway_months)} — na "
            f"„rozjelo se to\" je to málo",
            SOURCE_XBRL, i.as_of,
        )
    ]


def _analyst_signals(i: LifecycleInputs) -> list[Signal]:
    """
    What a named analyst said. One voice beside the filings, never a verdict on
    its own — it carries no weight towards MIN_HARD_READINGS because somebody
    saying a thing is not the company reporting it.
    """
    said = (i.analyst_says or "").strip().upper()
    if said not in (GREAT_FIND, WAIT_TIME, GOLD_MINE):
        return []
    who = i.analyst_name or "analytik"
    when = f" ({cz_date(i.analyst_on)})" if i.analyst_on else ""
    return [
        Signal(
            said, 1,
            f"{who} to řadí jako {PHASE_NAMES_CS[said]}{when}",
            SOURCE_ANALYST, i.analyst_on,
        )
    ]


def _confidence(
    proposal: LifecycleProposal, phase: str, inputs: LifecycleInputs
) -> str:
    """
    How much to trust the proposal.

    Great Find never reaches high confidence and says why: half its definition
    is that nobody has heard of the company, and this app measures no such
    thing. Yahoo-derived numbers are capped for the reason the cylinder rubric
    caps them — annual aggregates are not a series and nobody audited them.
    """
    if phase == GREAT_FIND:
        proposal.unknowns.append(
            "„objev\" znamená i to, že o firmě nikdo neví — a pozornost trhu "
            "aplikace neměří, takže tuhle půlku definice nikdo neověřil"
        )
        return CONFIDENCE_LOW

    if inputs.layer == LAYER_FINNHUB:
        proposal.unknowns.append(
            "meziroční čísla spočítal dodavatel dat, aplikace ta podání sama "
            "nečetla — jistota nejvýš střední"
        )
        return CONFIDENCE_MEDIUM
    if inputs.layer != LAYER_XBRL:
        proposal.unknowns.append(
            "čísla jsou z ročních souhrnů, ne z výkazů po čtvrtletích — jistota "
            "nejvýš střední"
        )
        return CONFIDENCE_MEDIUM

    margin = proposal.score_for(phase) - max(
        proposal.score_for(p) for p in (GOLD_MINE, WAIT_TIME, GREAT_FIND) if p != phase
    )
    return CONFIDENCE_HIGH if margin >= 2 else CONFIDENCE_MEDIUM
