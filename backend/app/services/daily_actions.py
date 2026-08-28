"""
Daily Action engine — Path 1: "Co mám dnes udělat?"

Pure aggregation logic (no DB, no HTTP): takes a snapshot of the market alert,
held positions, and per-source analyses, and produces at most 3 ranked
executable actions or the "Nic. Drž." rest state.

Rules applied (GOMES_METHODOLOGY_CANON.md):
  - Yellow/Orange/Red: sell Wait-Time and alert-blocked tiers (de-risk first).
  - Doubling rule: position at +100% -> sell half (house money).
  - R/R vs cylinders: score below deserved -> trim.
  - BUY only through the hard Buy Guard (GREEN + known cylinders + score >
    deserved), sized by the dual-source agreement matrix and available cash.

Honesty rules: a position with a missing/stale price never gets an invented
number — it becomes a Czech warning the UI must show instead.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Final, Iterable

from app.core.constants import MIN_TRADE_CZK

#: Prefix on every warning that belongs to ONE company rather than to the
#: portfolio. The board reads it to move those lines onto the company's own
#: card: fifteen per-ticker lines stacked above twelve cards is the wall that
#: makes a screen unreadable, and each duplicates what its own card already
#: says. Matching a marker the engine writes on purpose is a different thing
#: from parsing meaning back out of prose, which this codebase refuses to do.
UNVALUED_MARKER = "BEZ OCENĚNÍ:"
from app.core.czech import n as cz
from app.core.sources import verdict_stance
from app.core.tickers import canonical_ticker
from app.services.asset_class_caps import apply_cap as apply_asset_cap
from app.services.currency import CurrencyError, currency_mismatch
from app.schemas.daily_actions import ActionItem, ConcentrationOut, DailyActionResponse
from app.trading.gomes_logic import (
    GomesGatekeeper,
    Trigger,
    ZoneLadder,
    LifecyclePhase,
    MarketAlert,
    MarketAlertSystem,
    PositionSizingEngine,
    PositionTier,
    RiskRewardCalculator,
    evaluate_dual_source_buy,
)

logger = logging.getLogger(__name__)

MAX_ACTIONS = 3
STALE_PRICE_AFTER = timedelta(days=3)

#: Not an instruction — the two engines disagreeing, handed over as a question.
#:
#: The band asks what a price is worth against the company's quality; the
#: lifecycle stage asks what the business is doing. They are allowed to
#: disagree, and until 2026-08-24 whichever ran first won in silence: the card
#: printed PRODAT over its own line saying the stock was the cheapest thing the
#: method can name. Three of twelve holdings read that way on one morning.
#:
#: So a contradiction now has its own type. It carries no verb, no limit price
#: and nothing to press, because an order here would be the app picking a side
#: it has not earned.
CONFLICT_ACTION = "ROZPOR"
# The semafor gates every buy and the whole allocation. Gomes restates it
# roughly weekly; two weeks without an update means we do not know the
# market state, whatever the last row happens to say.
STALE_ALERT_AFTER = timedelta(days=14)
# More same-type warnings than this collapse into one grouped line.
GROUP_WARNINGS_ABOVE = 3

# Urgency bands: de-risking always outranks profit-taking outranks buying.
URGENCY_LIQUIDATE = 100
URGENCY_SELL_WAIT_TIME = 95
URGENCY_SELL_BLOCKED_TIER = 90
URGENCY_TRIM_DOUBLED = 80
URGENCY_TRIM_RR = 75
# Below de-risking a known speculative position and above taking profit: a
# company running out of cash is urgent, and the app knowing nothing else
# about it is a reason to look sooner rather than later.
URGENCY_SELL_UNVALUED = 88
URGENCY_BUY_BASE = 40  # + up to 20 by score margin
# Adding to something already held sits just below opening a new position: the
# thesis is already owned, so the decision is about size rather than about
# whether to be in it at all.
URGENCY_ADD_BASE = 35
# Canon §5 — three points cheaper than at entry is a second, independent
# reason for the same purchase, so it moves ahead of a plain top-up.
URGENCY_ADD_THREE_POINT_BONUS = 15

# The gap to target is entered in thirds. A staged entry is what makes a wrong
# entry price survivable, and the canon's objection to buying everything at
# once applies within one name as much as across a portfolio.
ADD_TRANCHES = 3
# Never more than this share of free cash in a single day. Cash is what lets
# you buy the correction — "you can't buy cheap stocks if you have no cash".
MAX_CASH_SHARE_PER_DAY = 1 / 3


@dataclass
class PositionInput:
    """A held position, as read from the positions table."""
    ticker: str
    shares: float
    # None = purchase price unknown (Degiro imports carry none) — the
    # doubling rule is disarmed and a warning nags until the user fills it.
    avg_cost: float | None
    currency: str = "USD"
    #: The owner has checked this currency against his broker statement.
    #: Silences the suffix-based mismatch check, which cannot tell which of
    #: the two sides is wrong and must not guess.
    currency_confirmed: bool = False
    current_price: float | None = None
    last_price_update: datetime | None = None


@dataclass
class AnalysisInput:
    """Latest analysis for (ticker, source), merged with lifecycle data."""
    ticker: str
    source_key: str  # GOMES | BREAKOUT_INVESTORS | OTHER
    green_line: float | None = None
    red_line: float | None = None
    #: Currency the lines are quoted in. The tracker quotes the US OTC listing,
    #: so a CAD-priced position is converted before it is scored. None =
    #: unknown, and unknown is never assumed to match the position.
    line_currency: str | None = None
    cylinders: int | None = None
    lifecycle_phase: str | None = None  # GREAT_FIND | WAIT_TIME | GOLD_MINE | UNKNOWN
    conviction_score: int | None = None
    action_verdict: str | None = None
    current_price: float | None = None
    #: When the owner agreed to `cylinders`. None = a proposal, or a number
    #: from before the rubric existed — either way it authorises no purchase.
    cylinders_confirmed_at: datetime | None = None
    #: When that agreement lapses. Past it, the buy side stops reading the
    #: number and the sell side keeps reading it.
    cylinders_valid_until: datetime | None = None
    #: A proven Gold Mine trading through a slowdown (§V1). Kept apart from the
    #: phase on purpose: the stage stays GOLD_MINE, and the caution moves here,
    #: where the Buy Guard can check the slowdown against the date the quality
    #: was agreed instead of refusing the company outright.
    rough_patch: bool = False
    rough_patch_since: datetime | None = None
    #: What kind of bet this is — ANCHOR, HIGH_BETA_ROCKET, BIOTECH_BINARY,
    #: TURNAROUND, VALUE_TRAP. A separate axis from the tier: the tier measures
    #: how sure the thesis is, this measures what happens if it is wrong. None
    #: means unrecorded, which imposes no ceiling and is said out loud.
    asset_class: str | None = None
    #: R/R score recorded when the position was opened. None for everything
    #: bought before that column existed, and the three-point rule then stays
    #: silent rather than dating a move from a moment nobody observed.
    entry_score: float | None = None
    #: Days until the company reports. The canon does not buy into a print it
    #: cannot predict, and this is the number that rule has been waiting for
    #: since the app was written.
    days_to_earnings: int | None = None
    #: False when the date is a provider window or our own cadence arithmetic.
    #: An estimate blocks like a fact — a delayed purchase is cheaper than a
    #: surprise — but it must never be SHOWN as one.
    earnings_confirmed: bool = True


def convert_price(
    price: float | None,
    from_currency: str | None,
    to_currency: str | None,
    fx_rate_to_czk: Callable[[str], float],
) -> float | None:
    """
    One price restated in another currency, through the rate this engine
    already uses for everything else.

    Both legs go through CZK deliberately: a second FX source would eventually
    disagree with the first, and the disagreement would show up as a limit
    price that is a few percent off — small enough to look plausible and large
    enough to matter on a fill.

    Returns None when the conversion cannot be made. An unconvertible price is
    not a price; it must never be quietly passed through in the wrong money.
    """
    if price is None or price <= 0:
        return None
    if not from_currency or not to_currency:
        return price if from_currency == to_currency else None
    if from_currency.upper() == to_currency.upper():
        return price
    try:
        return price * fx_rate_to_czk(from_currency) / fx_rate_to_czk(to_currency)
    except CurrencyError:
        return None


def price_in_band_currency(
    price: float | None,
    price_currency: str | None,
    line_currency: str | None,
    fx_rate_to_czk: Callable[[str], float],
) -> float | None:
    """
    The price restated in the currency the Green and Red Lines are quoted in.

    Every Gomes band is quoted on the US OTC listing, and four of the five
    largest positions trade in Canadian dollars. `app/core/tickers.py` matches
    those positions to their US analysis correctly — and the score was then
    computed from a CAD price against a USD band, wrong by the whole exchange
    rate. The first live run produced "TRIM GSI.V" on an R/R of 2.97 where the
    converted figure is about 4.25.

    Both legs go through the same CZK rate the rest of this engine uses, so no
    second FX source can disagree with the first.

    Returns None when the conversion cannot be made — an unconvertible price
    produces no score at all, rather than a score computed in the wrong money.
    """
    # An unknown band currency is not evidence that it matches; `convert_price`
    # refuses that case, which is exactly the behaviour this function needs.
    return convert_price(price, price_currency, line_currency, fx_rate_to_czk)


def _naive_utc(value: datetime | None) -> datetime | None:
    """
    Strip the timezone so a database value can be compared with the engine clock.

    This module works in naive UTC throughout, and most of the columns it reads
    are naive. The cylinder-confirmation columns are `TIMESTAMP WITH TIME ZONE`,
    so the first confirmation ever written turned every comparison here into a
    TypeError — the daily list would have gone down the moment the feature
    started working. Naive input passes through unchanged; aware input is
    converted rather than assumed.
    """
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _buyable_cylinders(analysis: "AnalysisInput", now: datetime) -> int | None:
    """
    The cylinder count a PURCHASE may be built on, or None.

    Stricter than the one the selling rules use, and deliberately asymmetric.
    A quality reading that nobody confirmed, or that has aged past the report
    which could contradict it, must not unlock new money — but it stays good
    enough to justify trimming, because the alternative is an app that goes
    quiet on a position exactly when its information got old.

    That asymmetry is the standing rule here: stale data may make this app more
    cautious, never less.
    """
    if analysis.cylinders is None:
        return None
    if analysis.cylinders_confirmed_at is None:
        return None
    expires = _naive_utc(analysis.cylinders_valid_until)
    if expires is not None and expires < _naive_utc(now):
        return None
    return analysis.cylinders


@dataclass(frozen=True)
class Refusal:
    """
    One buy the Buy Guard turned down, and the state it turned it down on.

    Emitted rather than persisted here, because this module is a pure function
    and must stay one. `app/services/refused_buys.py` is what writes it.

    It exists because the engine has always kept a record of what it did and
    none of what it declined. Both halves are needed: a rule that only shows
    its successes cannot be told apart from one that quietly costs money.
    """

    ticker: str
    failed_gate: str          # GomesGatekeeper.BuyGate value — a code, not prose
    reason: str
    source_key: str | None = None
    price: float | None = None
    green_line: float | None = None
    red_line: float | None = None
    line_currency: str | None = None
    rr_score: float | None = None
    deserved_score: float | None = None
    cylinders: int | None = None
    lifecycle_phase: str | None = None
    market_alert: str | None = None


def _by_company(analyses: Iterable[AnalysisInput]) -> dict[str, AnalysisInput]:
    """
    One analysis per company, keyed by `canonical_ticker`.

    A company can hold two rows from the same source — one per listing — and a
    plain dict comprehension would keep whichever came last. The row with a
    Conviction Score wins instead, because the score is what every rule
    downstream needs; without this, KRKN (score 2) and KRKNF (no score) would
    resolve by insertion order.
    """
    picked: dict[str, AnalysisInput] = {}
    for analysis in analyses:
        key = canonical_ticker(analysis.ticker)
        if not key:
            continue
        current = picked.get(key)
        if current is None or (
            current.conviction_score is None and analysis.conviction_score is not None
        ):
            picked[key] = analysis
    return picked


def _concentration_out(concentration) -> ConcentrationOut | None:
    """
    The same reading `Reading.warnings_cs()` already renders as prose, kept as
    numbers so a screen can show it every day, not just past a threshold.

    None when there is nothing to show: no reading was computed, or no
    position had a knowable CZK value. Zero would claim a portfolio with zero
    exposure; the honest answer here is that there is nothing to report.
    """
    if concentration is None or not concentration.total_czk:
        return None
    return ConcentrationOut(
        total_czk=round(concentration.total_czk, 2),
        material_pct=round(concentration.material_pct, 1),
        unassessed_pct=round(concentration.unassessed_pct, 1),
        upper_bound_pct=round(concentration.upper_bound_pct, 1),
        material_tickers=list(concentration.material_tickers),
        unassessed_tickers=list(concentration.unassessed_tickers),
    )


def generate_daily_actions(
    market_alert: str | None,
    market_alert_updated_at: datetime | None,
    positions: list[PositionInput],
    analyses: list[AnalysisInput],
    cash_czk: float | None,
    fx_rate_to_czk: Callable[[str], float],
    now: datetime | None = None,
    behaviour_brakes: Callable[[float], list[str]] | None = None,
    reentry_note: Callable[[str], str | None] | None = None,
    refusal_sink: Callable[[Refusal], None] | None = None,
    source_notes: list[str] | None = None,
    alert_note: str | None = None,
    pacing: Callable[[str, bool], str | None] | None = None,
    unvalued: dict[str, list] | None = None,
    concentration=None,
    owner_intent: Callable[[str], str | None] | None = None,
) -> DailyActionResponse:
    """
    Build the daily action list. Pure function — inject FX and clock for tests.

    `analyses` should hold the latest take per (ticker, source_key); tickers
    not in `positions` are treated as watchlist BUY candidates.

    `behaviour_brakes` is called with the computed portfolio value and returns
    observations about recent trading — a loss just taken, a burst of activity.
    They are appended to `warnings`, never to `actions`: they inform the
    decision, they do not make it.

    `reentry_note` is called with each proposed BUY ticker and returns a note
    if that ticker was sold at a loss recently. Same contract: it annotates the
    buy, it never removes it.

    `refusal_sink` receives a `Refusal` for every buy the guard turns down.
    Without it the engine behaves exactly as before — it just forgets what it
    blocked, which is the state that made the discipline unmeasurable.

    `pacing` is asked, for each purchase the rules already approved, whether it
    is too soon — a new position this week, or a second tranche into the same
    company this fortnight. It BLOCKS, unlike the behavioural brakes, because
    the canon's objection is to the timing of the batch rather than to any one
    trade in it (§7 rule 2). A held-back purchase is always said out loud.

    `unvalued` carries findings for holdings the method cannot value at all —
    eight of twelve of them. Without it those positions produce nothing, and a
    position nobody is watching is the one that turns into a loss slowly enough
    to go unnoticed. None of these findings can ever be a purchase; buying
    needs a valuation and there is none. See `app/services/outside_method.py`.

    `concentration` is the portfolio-level reading from
    `app/services/concentration.py`: how much of the money sits in companies
    with a material warning, and how much in companies nobody can read. No
    per-stock rule can see either. Above a threshold it stops new speculative
    positions; the unassessed share never blocks anything and is said anyway,
    because a blind spot nobody mentions is one you stop seeing.

    `source_notes` are things that moved at the sources themselves — a Green or
    Red Line the analyst shifted, a pick entering or leaving his real portfolio.
    They lead the warnings rather than trailing them, because a moved band
    means every number below it was computed against a valuation that no longer
    exists, and reading the actions first would be reading them on stale terms.

    `alert_note` is `app/services/market_catalyst.py` asking about the semafor
    itself: an ORANGE or RED with no cause written down, or one written down so
    long ago that nobody can say whether it still holds. It leads for the same
    reason the source notes do, and it is the only prompt in this app that can
    lead to the semafor coming DOWN. Nothing here lowers it — `market_watch`
    tightens and never loosens by design — so without somebody being asked, an
    escalation set during a scare goes on refusing every purchase forever, and
    silently, because a refusal looks exactly like caution working.

    `owner_intent` is asked, for a ticker about to receive a BUY or add-to
    suggestion, whether the owner has already decided something about it that
    no phase reading captures — ECOR is queued for exit despite a passing
    phase, SMSI is held only for a tax-loss harvest despite already failing
    the phase gate for an unrelated reason. A non-None answer produces no
    action at all for that ticker; it never becomes a warning, because a
    position the owner has already decided about does not need daily notice.
    """
    now = now or datetime.utcnow()
    warnings: list[str] = []

    # First, and deliberately: these change how everything under them is read.
    if source_notes:
        warnings.extend(source_notes)
    if alert_note:
        warnings.append(alert_note)

    alert = _normalize_alert(market_alert, warnings)
    # Stale data may make us more cautious, never less. A stale ORANGE still
    # de-risks; a stale GREEN stops authorising purchases.
    buy_alert = alert
    if alert is not None and _alert_is_stale(market_alert_updated_at, now):
        buy_alert = None
        age = (
            f"{(now - market_alert_updated_at).days} dní"
            if market_alert_updated_at is not None
            else "neznámo jak dlouho"
        )
        warnings.append(
            f"⚠️ STARÝ SEMAFOR: Market Alert {alert.value} nebyl {age} "
            f"aktualizován — nákupy blokovány, ochrany běží dál"
        )

    # Keyed by `canonical_ticker`, not the raw symbol. Four of these positions
    # are held on a Canadian exchange while every Gomes note names the US OTC
    # listing, and exact matching broke that in both directions: KUYA.V could
    # not see its own analysis (score 10, filed under KUYAF), and the buy loop
    # below did not recognise KUYAF as already held — so the app could propose
    # opening a position in a company it already owns, sized as if from zero.
    gomes_by_ticker = _by_company(a for a in analyses if a.source_key == "GOMES")
    breakout_by_ticker = _by_company(
        a for a in analyses if a.source_key == "BREAKOUT_INVESTORS"
    )
    held_tickers = {
        canonical_ticker(p.ticker) for p in positions if p.shares > 0
    }

    # One phase per company, from whichever row carries it. A company covered
    # only by Breakout, or by nobody, still has a lifecycle stage the owner
    # confirmed — and that stage decides whether a yellow market sells it.
    phase_by_company: dict[str, str] = {}
    for a in analyses:
        key = canonical_ticker(a.ticker)
        if key and a.lifecycle_phase and not phase_by_company.get(key):
            phase_by_company[key] = a.lifecycle_phase

    if cash_czk is None:
        warnings.append("⚠️ CHYBÍ ÚDAJE: hotovost portfolia není známa")
        cash_czk = 0.0

    candidates: list[ActionItem] = []
    portfolio_value_czk = cash_czk

    # Per-category ticker collectors — emitted after the loop, grouped when
    # many positions share the same problem (one line, not a wall of 14).
    no_price: list[str] = []
    no_cost: list[str] = []
    undated_price: list[str] = []
    stale_price: list[tuple[str, datetime]] = []
    unjudgeable: list[str] = []
    unconvertible: list[str] = []
    currency_conflict: list[str] = []
    stale_quality: list[tuple[str, datetime]] = []
    unbanded_currency: list[str] = []
    addable: list[tuple[str, PositionInput, AnalysisInput, float, float]] = []
    paced_out: list[str] = []
    capped_by_unknown_tier: list[str] = []
    unbanded_tier: list[str] = []
    unvalued_notes: list[tuple[str, str, str]] = []

    # ------------------------------------------------------------------
    # Held positions: de-risk, doubling rule, R/R trims
    # ------------------------------------------------------------------
    for pos in positions:
        if pos.shares <= 0:
            continue
        ticker = pos.ticker.upper()
        analysis = gomes_by_ticker.get(canonical_ticker(ticker))
        # The BAND comes from Gomes; the PHASE is a fact about the company and
        # is read across every row for it. IRIX is confirmed Wait Time with
        # high confidence and Gomes has no lines for it, so reading the phase
        # off the Gomes row alone left a position the canon says not to hold
        # reporting "no reason to do anything".
        phase = _resolve_phase(phase_by_company.get(canonical_ticker(ticker)))

        if pos.current_price is None or pos.current_price <= 0:
            no_price.append(ticker)
            continue

        if pos.avg_cost is None:
            no_cost.append(ticker)

        if pos.last_price_update is None:
            undated_price.append(ticker)
        elif now - pos.last_price_update > STALE_PRICE_AFTER:
            stale_price.append((ticker, pos.last_price_update))

        # A ticker's suffix names its exchange, and an exchange has one trading
        # currency. When they disagree, ONE of the two is wrong — and which
        # one, the app cannot tell. IMP.V and KUYA.V are held on a European
        # line while the ticker is the Canadian symbol the Gomes tracker uses:
        # there the currency is right and the suffix is a nickname. Saying
        # "the CZK value is wrong" would be a claim, not a finding, so the
        # warning asks and `currency_confirmed` records the answer.
        if not pos.currency_confirmed:
            conflict = currency_mismatch(pos.ticker, pos.currency)
            if conflict is not None:
                expected, actual = conflict
                currency_conflict.append(f"{ticker} ({actual}→{expected}?)")

        try:
            rate = fx_rate_to_czk(pos.currency)
        except CurrencyError:
            # No rate means no CZK value, and no CZK value means every rule
            # below — de-risk sizing, doubling, R/R trims — would be computed
            # against a number we invented. Skip it and say so.
            unconvertible.append(ticker)
            continue
        position_value_czk = pos.shares * pos.current_price * rate
        portfolio_value_czk += position_value_czk

        # An expired quality reading still trims, but the owner has to know the
        # number it is trimming on is older than the last report.
        expires = _naive_utc(analysis.cylinders_valid_until) if analysis else None
        if analysis is not None and analysis.cylinders is not None and expires is not None:
            if expires < _naive_utc(now):
                stale_quality.append((ticker, expires))

        # A band whose currency nobody recorded cannot be scored against a
        # price — and must not be scored anyway. Silence here would read as
        # "nothing to do" on a position that simply could not be measured.
        if (
            analysis is not None
            and analysis.green_line is not None
            and price_in_band_currency(
                pos.current_price, pos.currency, analysis.line_currency, fx_rate_to_czk
            ) is None
        ):
            unbanded_currency.append(ticker)

        best = _derisk_action(
            alert, pos, ticker, phase, analysis, rate, unjudgeable,
            fx_rate_to_czk=fx_rate_to_czk,
            unbanded_tier=unbanded_tier,
        )

        if best is None:
            best = _doubling_action(pos, ticker, rate, now)

        if best is None and analysis is not None:
            best = _rr_trim_action(pos, ticker, analysis, rate, fx_rate_to_czk, now)

        # A holding with no band at all. The valuation rules said nothing and
        # were right to; these say what can be said without one.
        if best is None and unvalued:
            for finding in unvalued.get(ticker, ()):  # worst first
                if finding.severity == "EXIT":
                    best = _make_action(
                        "SELL", ticker, pos, pos.shares, rate,
                        f"Bez ocenění, ale {finding.message_cs}",
                        URGENCY_SELL_UNVALUED,
                        valid_until=_valid_until(now),
                    )
                    break
                unvalued_notes.append((finding.severity, ticker, finding.message_cs))

        if best is not None:
            candidates.append(best)
        elif analysis is not None:
            # Nothing to de-risk or trim. Whether to ADD depends on this
            # position's share of the portfolio, and that total is not final
            # until the loop ends — so it is decided in a second pass.
            addable.append((ticker, pos, analysis, rate, position_value_czk))

    # ------------------------------------------------------------------
    # Data-honesty warnings — grouped per category so 14 positions with the
    # same gap read as one line, not a wall
    # ------------------------------------------------------------------
    _grouped(
        warnings, no_price,
        "⚠️ CHYBÍ ÚDAJE: {t} nemá aktuální cenu — pravidla nelze vyhodnotit, ověř ručně",
        "⚠️ CHYBÍ ÚDAJE: {n} pozic bez aktuální ceny ({tickers}) — pravidla nelze vyhodnotit",
    )
    _grouped(
        warnings, no_cost,
        "⚠️ CHYBÍ NÁKUPNÍ CENA: {t} — doplň ji v detailu pozice; P/L a pravidlo zdvojnásobení do té doby nehlídám",
        "⚠️ CHYBÍ NÁKUPNÍ CENA u {n} pozic ({tickers}) — doplň je v detailu pozic; P/L a pravidlo zdvojnásobení do té doby nehlídám",
    )
    _grouped(
        warnings, unjudgeable,
        "⚠️ NEZAŘAZENÁ POZICE: {t} nemá určenou fázi cyklu — při stupni "
        "{alert} nedokážu říct, jestli je spekulativní; prodávat ji jen proto, "
        "že o ní nic nevím, nebudu. Rozhodni sám",
        "⚠️ NEZAŘAZENÝCH POZIC {n} ({tickers}) — bez fáze cyklu nevím, které "
        "z nich jsou spekulativní, a při stupni {alert} je proto neprodávám. "
        "Rozhodni sám",
        alert=_alert_cs(alert),
    )
    _grouped(
        warnings, unbanded_tier,
        "⚠️ BEZ ČÁRY, NEPRODÁVÁM: {t} spadá do stupně rizika, který {alert} "
        "blokuje, ale nemá zelenou ani červenou čáru — bez ocenění je „je to "
        "spekulace“ dohad, ne zjištění. Rozhodni sám",
        "⚠️ BEZ ČÁRY, NEPRODÁVÁM: {n} pozic ({tickers}) spadá do stupně rizika, "
        "který {alert} blokuje, ale nemá zelenou ani červenou čáru — bez "
        "ocenění je „je to spekulace“ dohad, ne zjištění. Rozhodni sám",
        alert=_alert_cs(alert),
    )
    if len(stale_quality) <= GROUP_WARNINGS_ABOVE:
        for ticker, expired in stale_quality:
            warnings.append(
                f"⚠️ VYPRŠELÁ KVALITA: {ticker} — válce potvrzené do "
                f"{expired:%Y-%m-%d}; nakupovat nebudu, prodejní pravidla jedou "
                f"dál na starém čísle"
            )
    elif stale_quality:
        oldest = min(e for _, e in stale_quality)
        warnings.append(
            f"⚠️ VYPRŠELÁ KVALITA u {len(stale_quality)} pozic "
            f"({', '.join(t for t, _ in stale_quality)}) — nejstarší platnost do "
            f"{oldest:%Y-%m-%d}; nakupovat nebudu, prodejní pravidla jedou dál"
        )

    _grouped(
        warnings, unbanded_currency,
        "⚠️ MĚNA PÁSMA NEZNÁMÁ: {t} — cenu a pásmo nemám v čem porovnat, "
        "takže R/R skóre nepočítám; doplň měnu, ve které jsou linky vedené",
        "⚠️ MĚNA PÁSMA NEZNÁMÁ u {n} pozic ({tickers}) — cenu a pásmo nemám "
        "v čem porovnat, R/R skóre u nich nepočítám",
    )
    _grouped(
        warnings, currency_conflict,
        "⚠️ MĚNA VS. TICKER: {t} — přípona tickeru ukazuje na jinou burzu, než "
        "v jaké měně je pozice vedená. Jestli měna sedí s výpisem od brokera, "
        "potvrď ji v detailu pozice; jestli ne, hodnota v CZK je o poměr těch "
        "měn vedle",
        "⚠️ MĚNA VS. TICKER u {n} pozic ({tickers}) — přípona tickeru ukazuje "
        "na jinou burzu, než v jaké měně jsou vedené. Potvrď měnu v detailu "
        "pozic, nebo ji oprav",
    )
    _grouped(
        warnings, unconvertible,
        "⚠️ NEZNÁMÁ MĚNA: {t} — kurz do CZK nemám, pozici jsem do součtu ani "
        "do pravidel nezapočítal; doplň měnu v detailu pozice",
        "⚠️ NEZNÁMÁ MĚNA u {n} pozic ({tickers}) — kurz do CZK nemám, do součtu "
        "ani do pravidel je nezapočítávám",
    )
    _grouped(
        warnings, undated_price,
        "⚠️ STÁŘÍ CENY NEZNÁMÉ: {t} — cena bez časového razítka, ověř před obchodem",
        "⚠️ STÁŘÍ CENY NEZNÁMÉ u {n} pozic ({tickers}) — ověř před obchodem",
    )
    if len(stale_price) <= GROUP_WARNINGS_ABOVE:
        for ticker, updated in stale_price:
            warnings.append(
                f"⚠️ STARÁ CENA: {ticker} naposledy aktualizována "
                f"{updated:%Y-%m-%d} — ověř před obchodem"
            )
    else:
        oldest = min(u for _, u in stale_price)
        warnings.append(
            f"⚠️ STARÁ CENA u {len(stale_price)} pozic "
            f"({', '.join(t for t, _ in stale_price)}) — nejstarší {oldest:%Y-%m-%d}, "
            f"ověř před obchodem"
        )

    # ------------------------------------------------------------------
    # Behavioural observations — what the trade ledger says about how the last
    # few days went. Warnings, never actions: the app names the pattern, the
    # decision stays with the owner.
    # ------------------------------------------------------------------
    if behaviour_brakes is not None:
        try:
            warnings.extend(behaviour_brakes(portfolio_value_czk))
        except Exception:
            # A brake that cannot be computed must not take the day's actions
            # down with it — those still hold without it.
            logger.exception("Emoční brzdy se nepodařilo spočítat")

    # ------------------------------------------------------------------
    # Held positions: top up what is still cheap for its quality
    # ------------------------------------------------------------------
    for ticker, pos, analysis, rate, value_czk in addable:
        add = _add_action(
            pos, ticker, analysis, breakout_by_ticker.get(canonical_ticker(ticker)),
            buy_alert, value_czk, portfolio_value_czk, cash_czk, rate,
            fx_rate_to_czk, now, refusal_sink=refusal_sink,
            blocked_notes=capped_by_unknown_tier,
            owner_intent=owner_intent,
        )
        if add is None:
            continue
        if pacing is not None:
            held_back = pacing(ticker, False)
            if held_back:
                paced_out.append(f"{ticker}: {held_back}")
                continue
        candidates.append(add)

    # ------------------------------------------------------------------
    # Watchlist: BUY candidates through the hard Buy Guard
    # ------------------------------------------------------------------
    for company, analysis in sorted(gomes_by_ticker.items()):
        if company in held_tickers:
            continue
        # The analysis' own symbol is what gets shown — `company` is only the
        # matching key, and a suggestion reading "GEODF" for a note written
        # about GEO.TO would send the owner looking for the wrong line.
        ticker = analysis.ticker.upper()
        buy = _buy_action(
            buy_alert, ticker, analysis, breakout_by_ticker.get(company),
            cash_czk, portfolio_value_czk, fx_rate_to_czk, now,
            refusal_sink=refusal_sink,
            owner_intent=owner_intent,
        )
        if buy is None:
            continue
        if (
            concentration is not None
            and concentration.blocks_speculation
            and PositionSizingEngine.determine_tier(
                _resolve_phase(analysis.lifecycle_phase if analysis else None),
                analysis.conviction_score if analysis.conviction_score is not None else 0,
            ) is PositionTier.TERTIARY
        ):
            # Adding another gamble on top of a portfolio already carrying
            # broken companies is the sequence that turns a bad quarter into a
            # bad year. Held positions are judged by their own rules; this only
            # stops the pile growing.
            paced_out.append(
                f"{ticker}: spekulativní pozice, ale "
                f"{concentration.material_pct:.1f} % portfolia už drží firmy "
                f"s materiálním nálezem"
            )
            continue
        if pacing is not None:
            held_back = pacing(ticker, True)
            if held_back:
                paced_out.append(f"{ticker}: {held_back}")
                continue
        candidates.append(buy)

    _grouped(
        warnings, capped_by_unknown_tier,
        "⚠️ STROP Z NEVĚDOMOSTI: {t}",
        "⚠️ STROP Z NEVĚDOMOSTI u {n} pozic — jsou v nákupním pásmu, ale bez "
        "fáze cyklu platí nejpřísnější strop a ten je naplněný ({tickers})",
    )

    if concentration is not None:
        # First among the position-level notes: it changes how all of them read.
        warnings.extend(concentration.warnings_cs())

    for severity, ticker, message in unvalued_notes:
        mark = "⚠️" if severity == "REVIEW" else "ℹ️"
        warnings.append(f"{mark} {UNVALUED_MARKER} {ticker} — {message}")

    for note in paced_out:
        warnings.append(
            f"⏸️ TEMPO: {note} — nákup je jinak v pořádku, jen se nemá kupovat všechno naráz"
        )

    # ------------------------------------------------------------------
    # Rank, cap at 3, decide the day's status
    # ------------------------------------------------------------------
    candidates.sort(key=lambda a: (-a.urgency_score, a.ticker))
    actions = candidates[:MAX_ACTIONS]

    # A buy-back into something sold at a loss is worth a second look at the
    # moment it is proposed, not buried in a list further down. The buy still
    # stands — this only puts the question next to it.
    if reentry_note is not None:
        for action in actions:
            if not action.action_type.startswith("BUY"):
                continue
            try:
                note = reentry_note(action.ticker)
            except Exception:
                logger.exception("Kontrola zpětného nákupu %s selhala", action.ticker)
                continue
            if note:
                warnings.append(note)

    return DailyActionResponse(
        market_alert=alert.value if alert else "UNKNOWN",
        available_cash_czk=round(cash_czk, 2),
        status="ACTION_REQUIRED" if actions else "HOLD_HOLD_HOLD",
        actions=actions,
        # Uncapped and in the same order. The board states a stance for every
        # company and must not report an action the cap merely hid.
        all_actions=candidates,
        warnings=warnings,
        concentration=_concentration_out(concentration),
        generated_at=now,
    )


# ==============================================================================
# Rule helpers
# ==============================================================================

_ALERT_CS: Final[dict[str, str]] = {
    "GREEN": "zelená",
    "YELLOW": "žlutá",
    "ORANGE": "oranžová",
    "RED": "červená",
}


def _alert_cs(alert) -> str:
    """Stupeň semaforu česky. Hodnota z databáze nepatří do věty pro čtenáře."""
    if alert is None:
        return "neznámý"
    return _ALERT_CS.get(alert.value.upper(), alert.value)


def _grouped(
    warnings: list[str],
    tickers: list[str],
    single_fmt: str,
    group_fmt: str,
    **extra: object,
) -> None:
    """Emit one warning per ticker, or a single grouped line when many."""
    if not tickers:
        return
    if len(tickers) <= GROUP_WARNINGS_ABOVE:
        for t in tickers:
            warnings.append(single_fmt.format(t=t, **extra))
    else:
        warnings.append(
            group_fmt.format(n=len(tickers), tickers=", ".join(tickers), **extra)
        )


def _alert_is_stale(updated_at: datetime | None, now: datetime) -> bool:
    """
    An undated semafor counts as stale.

    The live database held one row, GREEN, last touched seven months earlier,
    and nothing said so. A green light is indistinguishable from a working
    system, which is what makes silent staleness expensive here.
    """
    if updated_at is None:
        return True
    return now - updated_at > STALE_ALERT_AFTER


def _normalize_alert(market_alert: str | None, warnings: list[str]) -> MarketAlert | None:
    """Unknown alert is a loud warning, never a silent GREEN."""
    if not market_alert:
        warnings.append(
            "⚠️ CHYBÍ ÚDAJE: Market Alert není nastaven — nákupy blokovány, "
            "nastav semafor ručně"
        )
        return None
    try:
        return MarketAlert(market_alert.upper())
    except ValueError:
        warnings.append(
            f"⚠️ CHYBÍ ÚDAJE: neznámý Market Alert '{market_alert}' — "
            f"nákupy blokovány"
        )
        return None


def _resolve_phase(phase: str | None) -> LifecyclePhase:
    """
    The canon's stage for a company, or UNKNOWN.

    Takes the value rather than an analysis row: the stage belongs to the
    business and every source row for that business carries the same one, so
    reading it off one particular row made it depend on who happened to publish
    a band.
    """
    if not phase:
        return LifecyclePhase.UNKNOWN
    try:
        return LifecyclePhase(phase.upper())
    except ValueError:
        return LifecyclePhase.UNKNOWN


def _record_conflict(
    refusal_sink,
    ticker: str,
    analysis: "AnalysisInput",
    decision,
    score: float | None,
    deserved: float | None,
    cylinders: int | None,
    phase,
    alert,
    price: float | None,
) -> None:
    """Record a purchase the second source refused, with the same vocabulary."""
    if refusal_sink is None:
        return
    refusal_sink(
        Refusal(
            ticker=ticker,
            failed_gate=GomesGatekeeper.BuyGate.SOURCE_CONFLICT.value,
            reason=decision.reason,
            source_key=analysis.source_key,
            price=price,
            green_line=analysis.green_line,
            red_line=analysis.red_line,
            line_currency=analysis.line_currency,
            rr_score=score,
            deserved_score=deserved,
            cylinders=cylinders,
            lifecycle_phase=phase.value if hasattr(phase, "value") else phase,
            market_alert=alert.value if alert else None,
        )
    )


def _limit_from_band(
    boundary: float | None,
    analysis: AnalysisInput,
    pos_currency: str | None,
    fx_rate_to_czk: Callable[[str], float],
) -> float | None:
    """
    A band edge, in the currency the order will actually be placed in.

    The ladder works in the band's money — the US OTC listing for every Gomes
    pick — and the broker takes the order in the currency the position trades
    in. Handing over the unconverted number would put a Canadian order in at a
    dollar price, roughly a third out.
    """
    return convert_price(boundary, analysis.line_currency, pos_currency, fx_rate_to_czk)


def _valuation_dissent(
    pos: PositionInput,
    analysis: AnalysisInput | None,
    fx_rate_to_czk: Callable[[str], float],
) -> str | None:
    """
    The band's objection to selling this position, or None when it has none.

    Read this as the second half of a sentence: „...ale ocenění říká {dissent}".
    Only a positive objection is returned. A band that says the price is fair,
    or that says nothing because there is no band, is not an argument for
    holding and must not be dressed up as one.
    """
    if analysis is None or analysis.green_line is None:
        return None

    price = price_in_band_currency(
        pos.current_price, pos.currency, analysis.line_currency, fx_rate_to_czk
    )
    if price is None:
        return None

    # At or under the Green Line the method has no cheaper word — and it needs
    # no cylinder count to say so, which matters here: the holdings this fires
    # on are largely the ones whose quality reading is missing. VTSI sat at
    # 3,13 against a Green Line of 5,00 while the stage rule ordered it sold at
    # a 58 % loss.
    if price <= analysis.green_line:
        return (
            f"cena {cz(price, 2)} je na zelené čáře {cz(analysis.green_line, 2)} "
            f"nebo pod ní — nejlevnější stav, jaký metodika zná"
        )

    score = RiskRewardCalculator.calculate_rr_score(
        price, analysis.green_line, analysis.red_line
    )
    zone, zone_reason = RiskRewardCalculator.decide_from_score(score, analysis.cylinders)
    return zone_reason if zone == "BUY" else None


def _conflict_action(
    pos: PositionInput,
    ticker: str,
    rate: float,
    *,
    sell_side: str,
    hold_side: str,
    urgency: int,
) -> ActionItem:
    """
    Two engines disagreeing about one company, as a question.

    Keeps the urgency of the order it replaces: a live contradiction is exactly
    as worth reading as the sell was. It simply is not a sell. No limit price,
    because there is no side to place an order on until somebody decides.
    """
    return _make_action(
        CONFLICT_ACTION, ticker, pos, pos.shares, rate,
        f"Fáze cyklu říká PRODAT ({sell_side}), ale ocenění říká OPAK "
        f"({hold_side}). Aplikace ten spor nerozhodne za tebe — "
        f"dokud se nerozhodneš, nedělá se nic.",
        urgency,
        review_required=True,
    )


def _derisk_action(
    alert: MarketAlert | None,
    pos: PositionInput,
    ticker: str,
    phase: LifecyclePhase,
    analysis: AnalysisInput | None,
    rate: float,
    unjudgeable: list[str],
    *,
    fx_rate_to_czk: Callable[[str], float],
    unbanded_tier: list[str],
) -> ActionItem | None:
    """Yellow/Orange/Red: exit Wait-Time and alert-blocked tiers."""
    if alert is None or alert == MarketAlert.GREEN:
        return None

    if alert == MarketAlert.RED:
        # Red is a statement about the market, not about this company. A cheap
        # price is not a counter-argument to „hotovost je král" and the band
        # has no standing to raise one.
        return _make_action(
            "LIQUIDATE_HEAVY", ticker, pos, pos.shares, rate,
            f"🔴 RED Alert — prodej téměř vše, hotovost je král "
            f"({pos.shares:g} ks {ticker})",
            URGENCY_LIQUIDATE,
        )

    if phase == LifecyclePhase.WAIT_TIME:
        dissent = _valuation_dissent(pos, analysis, fx_rate_to_czk)
        if dissent is not None:
            return _conflict_action(
                pos, ticker, rate,
                sell_side=f"{ticker} je ve Wait Time, mrtvé peníze",
                hold_side=dissent,
                urgency=URGENCY_SELL_WAIT_TIME,
            )
        return _make_action(
            "SELL_WAIT_TIME", ticker, pos, pos.shares, rate,
            f"{alert.value} Alert + {ticker} je ve Wait Time (mrtvé peníze) "
            f"— podle kánonu nedržet",
            URGENCY_SELL_WAIT_TIME,
        )

    # determine_tier ends in "everything else = TERTIARY", so a position we
    # know nothing about lands in the tier YELLOW blocks — and the app would
    # order it sold for the sole reason that it has no data on it. Not knowing
    # whether a holding is speculative is not the same as knowing it is. His
    # portfolio is fourteen positions with almost no phases recorded; this
    # rule alone would have told him to liquidate it.
    #
    # The first version of this guard also accepted a Conviction Score as
    # evidence that the tier was known, and that was wrong. The tier says what
    # KIND of position this is — proven Gold Mine, Great Find, speculation —
    # and that is a property of the lifecycle stage. Conviction measures
    # something else: how much of the thesis is believed. Reading one as the
    # other inverted the meaning of the number. On 2026-08-23, with the market
    # at yellow, the engine's first live run ordered KUYA.V sold in full — the
    # single highest-conviction holding in the app, score 10 — because nobody
    # had ever recorded its lifecycle stage.
    conviction = analysis.conviction_score if analysis else None
    if phase == LifecyclePhase.UNKNOWN:
        unjudgeable.append(ticker)
        return None

    tier = PositionSizingEngine.determine_tier(phase, conviction or 0)
    if tier not in MarketAlertSystem.get_blocked_tiers(alert):
        return None

    # `determine_tier` ends in „everything else = TERTIARY", and TERTIARY is
    # what yellow blocks. So a company nobody has valued lands in the tier that
    # gets sold, and the stated reason — „spekulace se v tomto trhu nedrží" —
    # is a claim the app has no evidence for. On 2026-08-24 that ordered
    # DBO.TO out at 16,8 % of the portfolio and RDCM at 8,7 %, both recorded
    # Gold Mines, on the strength of a missing Conviction Score.
    #
    # Not knowing whether a holding is speculative is not the same as knowing
    # it is — the same rule the UNKNOWN phase above already earned. Without a
    # Green Line there is no second opinion to check the tier against, so the
    # honest output is the question, not the order.
    if analysis is None or analysis.green_line is None:
        unbanded_tier.append(ticker)
        return None

    dissent = _valuation_dissent(pos, analysis, fx_rate_to_czk)
    if dissent is not None:
        return _conflict_action(
            pos, ticker, rate,
            sell_side=f"{alert.value} Alert blokuje {tier.value} pozice",
            hold_side=dissent,
            urgency=URGENCY_SELL_BLOCKED_TIER,
        )

    return _make_action(
        "SELL", ticker, pos, pos.shares, rate,
        f"{alert.value} Alert blokuje {tier.value} pozice — "
        f"spekulace se v tomto trhu nedrží",
        URGENCY_SELL_BLOCKED_TIER,
    )


def _doubling_action(
    pos: PositionInput, ticker: str, rate: float, now: datetime
) -> ActionItem | None:
    """Doubled -> sell half, play with house money."""
    if pos.avg_cost is None:
        return None  # unknown cost -> rule disarmed (warned in main loop)
    if pos.avg_cost <= 0 or pos.current_price < 2 * pos.avg_cost:
        return None
    gain_pct = (pos.current_price - pos.avg_cost) / pos.avg_cost * 100
    half = pos.shares / 2
    # Twice what it cost is the trigger and therefore also the price to place
    # the order at — the rule is "if you doubled your money, sell half", and
    # below that price it has not doubled.
    return _make_action(
        "TRIM", ticker, pos, half, rate,
        f"Doubling rule: +{gain_pct:.0f}% od nákupu — prodej polovinu, "
        f"zbytek jede za peníze domu",
        URGENCY_TRIM_DOUBLED,
        limit_price=2 * pos.avg_cost,
        limit_currency=pos.currency,
        valid_until=_valid_until(now),
    )


def _rr_trim_action(
    pos: PositionInput,
    ticker: str,
    analysis: AnalysisInput,
    rate: float,
    fx_rate_to_czk: Callable[[str], float],
    now: datetime,
) -> ActionItem | None:
    """R/R score below deserved (10 − cylinders) -> expensive for quality, trim."""
    price = price_in_band_currency(
        pos.current_price, pos.currency, analysis.line_currency, fx_rate_to_czk
    )
    score = RiskRewardCalculator.calculate_rr_score(
        price, analysis.green_line, analysis.red_line
    )
    zone, zone_reason = RiskRewardCalculator.decide_from_score(score, analysis.cylinders)
    if zone != "SELL":
        return None
    half = pos.shares / 2
    reading = ZoneLadder.read(price, analysis.green_line, analysis.red_line, analysis.cylinders)
    limit = _limit_from_band(reading.sell_above, analysis, pos.currency, fx_rate_to_czk)
    return _make_action(
        "TRIM", ticker, pos, half, rate,
        # Bez předpony: `zone_reason` už začíná „R/R skóre…", takže
        # „R/R: R/R skóre" koktalo na kartě hned v prvním řádku pokynu.
        f"{zone_reason} — vezmi zisk z poloviny pozice",
        URGENCY_TRIM_RR,
        target_price=analysis.red_line,
        limit_price=limit,
        limit_currency=pos.currency,
        valid_until=_valid_until(now),
    )


def _add_action(
    pos: PositionInput,
    ticker: str,
    analysis: AnalysisInput,
    breakout: AnalysisInput | None,
    alert: MarketAlert | None,
    position_value_czk: float,
    portfolio_value_czk: float,
    cash_czk: float,
    rate: float,
    fx_rate_to_czk: Callable[[str], float],
    now: datetime,
    refusal_sink: Callable[[Refusal], None] | None = None,
    blocked_notes: list[str] | None = None,
    owner_intent: Callable[[str], str | None] | None = None,
) -> ActionItem | None:
    """
    Add to a position already held, when it is still cheap for its quality.

    Until now a held position could only ever shrink. The buy loop skips
    anything already owned, so the most ordinary act in this whole method —
    putting the month's contribution into the name that is cheapest right now —
    had no instruction behind it at all.

    A deliberate departure from the written plan
    --------------------------------------------
    The plan required a three-point improvement since entry before adding.
    That is the canon's §5 add TRIGGER, and it is real — but making it a
    precondition would have left this path as dead as the buy path was, because
    no position on record has an entry score yet, and because the canon never
    says a cheap holding may only be topped up after it got cheaper still.
    Sizing is by the gap to target, exactly as §6 describes; the three-point
    move raises the urgency when it is known, rather than gating the action.

    Every guard the buy path uses applies unchanged: the market must be green,
    cylinders confirmed, the score above what the quality deserves, and the
    resulting weight inside the tier cap and the dual-source matrix.

    `owner_intent` is checked first and independently of all of that: a phase
    reading answers whether the business still argues for buying, but ECOR is
    GREAT_FIND today and queued for exit anyway (waiting for buyer interest,
    not for the thesis to fail), and SMSI stays blocked for the wrong reason
    once its WAIT_TIME phase eventually lifts — it is held only for a
    tax-loss harvest. Neither reason lives in a phase and neither should ever
    silently stop applying because a rubric re-read the numbers.
    """
    if owner_intent is not None and owner_intent(ticker) is not None:
        return None

    price = price_in_band_currency(
        pos.current_price, pos.currency, analysis.line_currency, fx_rate_to_czk
    )
    if price is None or price <= 0 or portfolio_value_czk <= 0:
        return None

    score = RiskRewardCalculator.calculate_rr_score(
        price, analysis.green_line, analysis.red_line
    )
    cylinders = _buyable_cylinders(analysis, now)
    deserved = RiskRewardCalculator.deserved_score(cylinders)
    phase = _resolve_phase(analysis.lifecycle_phase if analysis else None)

    allowed, gate, guard_reason = GomesGatekeeper.check_buy_guard(
        market_alert=alert.value if alert else "UNKNOWN",
        rr_score=score,
        deserved_score=deserved,
        cylinders=cylinders,
        lifecycle_stage=phase,
        days_to_earnings=analysis.days_to_earnings,
        earnings_confirmed=analysis.earnings_confirmed,
        rough_patch=analysis.rough_patch,
        rough_patch_since=analysis.rough_patch_since,
        cylinders_confirmed_at=analysis.cylinders_confirmed_at,
    )
    if not allowed:
        if refusal_sink is not None:
            refusal_sink(
                Refusal(
                    ticker=ticker,
                    failed_gate=gate.value,
                    reason=guard_reason,
                    source_key=analysis.source_key,
                    price=price,
                    green_line=analysis.green_line,
                    red_line=analysis.red_line,
                    line_currency=analysis.line_currency,
                    rr_score=score,
                    deserved_score=deserved,
                    cylinders=cylinders,
                    lifecycle_phase=phase.value if hasattr(phase, "value") else phase,
                    market_alert=alert.value if alert else None,
                )
            )
        return None

    conviction = analysis.conviction_score if analysis.conviction_score is not None else 0
    tier = PositionSizingEngine.determine_tier(phase, conviction)
    tier_max = PositionSizingEngine.get_position_limit(tier, ticker).max_portfolio_pct
    # The tier says how sure the thesis is; the asset class says what kind of
    # bet it is. Two different questions, so the smaller ceiling wins and an
    # unrecorded class imposes nothing rather than defaulting to a middle one.
    tier_max = apply_asset_cap(tier_max, analysis.asset_class)

    stance = verdict_stance(breakout.action_verdict) if breakout else None
    decision = evaluate_dual_source_buy(True, guard_reason, stance, tier_max)
    if decision.decision != "ALLOW" or decision.max_position_pct <= 0:
        # The guard passed and the other source refused. That is a decision as
        # much as any gate inside the guard, and it belongs in the same record
        # — otherwise a year from now the refusals will look like the Buy Guard
        # did all the work.
        _record_conflict(refusal_sink, ticker, analysis, decision, score,
                         deserved, cylinders, phase, alert, price)
        return None

    # §V2. The caps above say how much this name may EVER occupy; the R/R
    # score says how much it is worth today. Topping every passing name up to
    # its ceiling is the flat sizing Gomes rejects outright — "why would you
    # put the same amount of money in a stock that's here as a stock that is
    # way up here?" — and it spends the most cash on the names with the least
    # left to gain.
    target_pct = PositionSizingEngine.target_pct(
        decision.max_position_pct, score, market_alert=alert
    )
    current_pct = position_value_czk / portfolio_value_czk * 100.0
    gap_pct = target_pct - current_pct
    if gap_pct <= 0:
        # At or over the cap is a trim question, not an add one — except when
        # the cap itself is an artefact of not knowing anything. `determine_tier`
        # ends in "everything else = TERTIARY", which caps at 2 %, so a company
        # whose lifecycle stage was never recorded is held to the most
        # speculative limit in the book however good its numbers are. Every
        # position in the real portfolio is in exactly that state, and the
        # difference between "you already hold enough" and "we never classified
        # it" is the difference between a decision and a gap.
        if blocked_notes is not None and phase == LifecyclePhase.UNKNOWN:
            blocked_notes.append(
                f"{ticker}: je v nákupním pásmu, ale bez fáze cyklu platí "
                f"nejpřísnější strop {decision.max_position_pct:g} % — při "
                f"skóre {score:.1f} z něj vychází cíl {target_pct:.1f} % a ten "
                f"už máš naplněný ({current_pct:.1f} %). Doplň fázi a strop se změní"
            )
        return None

    # Split into thirds. The canon's objection to buying everything at once
    # applies within one name as much as across the portfolio: a staged entry
    # is what makes a wrong entry price survivable.
    tranche_czk = portfolio_value_czk * gap_pct / 100.0 / ADD_TRANCHES
    budget_czk = min(tranche_czk, cash_czk * MAX_CASH_SHARE_PER_DAY, cash_czk)

    price_czk = price * rate
    quantity = math.floor(budget_czk / price_czk) if price_czk > 0 else 0
    if quantity < 1 or quantity * price_czk < MIN_TRADE_CZK:
        return None

    reading = ZoneLadder.read(price, analysis.green_line, analysis.red_line, cylinders)
    limit = _limit_from_band(reading.buy_below, analysis, pos.currency, fx_rate_to_czk)

    trigger, trigger_reason = ZoneLadder.trigger(score, analysis.entry_score)
    urgency = URGENCY_ADD_BASE
    if trigger is Trigger.DOKOUPIT:
        # Canon §5: three points cheaper than it was at entry. The same
        # purchase, with a second independent reason behind it.
        urgency += URGENCY_ADD_THREE_POINT_BONUS

    reason = (
        f"R/R {score:.1f} > zasloužené {deserved:.1f} ({cylinders} válců) · "
        f"drž {current_pct:.1f} % z cíle {decision.max_position_pct:g} % — "
        f"dávka {ADD_TRANCHES}. dílu mezery"
    )
    if trigger is Trigger.DOKOUPIT:
        reason += f" · {trigger_reason}"
    if decision.review_required:
        reason += " · ⚠️ REVIEW_REQUIRED"

    return _make_action(
        "ADD", ticker, pos, quantity, rate, reason, urgency,
        target_price=analysis.green_line,
        review_required=decision.review_required,
        source_key="COMBINED" if stance in ("BULLISH", "BEARISH") else "GOMES",
        limit_price=limit,
        limit_currency=pos.currency,
        valid_until=_valid_until(now),
    )


def _buy_action(
    alert: MarketAlert | None,
    ticker: str,
    analysis: AnalysisInput,
    breakout: AnalysisInput | None,
    cash_czk: float,
    portfolio_value_czk: float,
    fx_rate_to_czk: Callable[[str], float],
    now: datetime,
    refusal_sink: Callable[[Refusal], None] | None = None,
    owner_intent: Callable[[str], str | None] | None = None,
) -> ActionItem | None:
    """
    Watchlist candidate must pass the hard Buy Guard + dual-source sizing.

    Checked before any of that, same as `_add_action`: `owner_intent`.
    """
    if owner_intent is not None and owner_intent(ticker) is not None:
        return None

    price = analysis.current_price
    if price is None or price <= 0:
        return None  # no price -> no invented BUY

    # A watchlist row carries the tracker's own price, which is already quoted
    # against its own band — but say so explicitly rather than by coincidence.
    banded = price_in_band_currency(
        price, analysis.line_currency, analysis.line_currency, fx_rate_to_czk
    )
    score = RiskRewardCalculator.calculate_rr_score(
        banded, analysis.green_line, analysis.red_line
    )
    # Only a confirmed, unexpired reading may fund a purchase.
    cylinders = _buyable_cylinders(analysis, now)
    deserved = RiskRewardCalculator.deserved_score(cylinders)
    phase = _resolve_phase(analysis.lifecycle_phase if analysis else None)

    allowed, gate, guard_reason = GomesGatekeeper.check_buy_guard(
        market_alert=alert.value if alert else "UNKNOWN",
        rr_score=score,
        deserved_score=deserved,
        cylinders=cylinders,
        lifecycle_stage=phase,
        days_to_earnings=analysis.days_to_earnings,
        earnings_confirmed=analysis.earnings_confirmed,
        rough_patch=analysis.rough_patch,
        rough_patch_since=analysis.rough_patch_since,
        cylinders_confirmed_at=analysis.cylinders_confirmed_at,
    )
    if not allowed:
        # A refusal is a decision and gets recorded like one. Reported even
        # when the sink is absent costs nothing; the sink is what decides
        # whether it reaches the database.
        if refusal_sink is not None:
            refusal_sink(
                Refusal(
                    ticker=ticker,
                    failed_gate=gate.value,
                    reason=guard_reason,
                    source_key=analysis.source_key,
                    price=price,
                    green_line=analysis.green_line,
                    red_line=analysis.red_line,
                    rr_score=score,
                    deserved_score=deserved,
                    cylinders=cylinders,
                    lifecycle_phase=phase.value if hasattr(phase, "value") else phase,
                    market_alert=alert.value if alert else None,
                )
            )
        return None

    conviction = analysis.conviction_score if analysis.conviction_score is not None else 0
    tier = PositionSizingEngine.determine_tier(phase, conviction)
    tier_max = PositionSizingEngine.get_position_limit(tier, ticker).max_portfolio_pct
    # The tier says how sure the thesis is; the asset class says what kind of
    # bet it is. Two different questions, so the smaller ceiling wins and an
    # unrecorded class imposes nothing rather than defaulting to a middle one.
    tier_max = apply_asset_cap(tier_max, analysis.asset_class)

    stance = verdict_stance(breakout.action_verdict) if breakout else None
    decision = evaluate_dual_source_buy(True, guard_reason, stance, tier_max)
    if decision.decision != "ALLOW" or decision.max_position_pct <= 0:
        # The guard passed and the other source refused. That is a decision as
        # much as any gate inside the guard, and it belongs in the same record
        # — otherwise a year from now the refusals will look like the Buy Guard
        # did all the work.
        _record_conflict(refusal_sink, ticker, analysis, decision, score,
                         deserved, cylinders, phase, alert, price)
        return None

    # §V2, same rule on the way in: the cap is the ceiling, the score is the
    # dial. A name that clears the guard at a score of 5 opens at half the
    # weight of one that clears it at 10.
    target_pct = PositionSizingEngine.target_pct(
        decision.max_position_pct, score, market_alert=alert
    )
    if target_pct <= 0:
        return None
    budget_czk = min(portfolio_value_czk * target_pct / 100.0, cash_czk)
    try:
        rate = fx_rate_to_czk("USD")
    except CurrencyError:
        return None  # cannot size a purchase without a rate; propose nothing
    price_czk = price * rate
    quantity = math.floor(budget_czk / price_czk) if price_czk > 0 else 0
    if quantity < 1:
        return None  # not enough cash for a single share — no action
    if quantity * price_czk < MIN_TRADE_CZK:
        # A purchase the fee would eat. The allocator has always refused these;
        # this path did not, so a small account could be handed a hundred-crown
        # order that costs a tenth of itself to place.
        return None

    margin = (score - deserved) if score is not None and deserved is not None else 0.0
    urgency = URGENCY_BUY_BASE + min(20, max(0, round(margin * 4)))
    source_key = "COMBINED" if stance in ("BULLISH", "BEARISH") else "GOMES"
    reading = ZoneLadder.read(banded, analysis.green_line, analysis.red_line, cylinders)
    limit = _limit_from_band(reading.buy_below, analysis, "USD", fx_rate_to_czk)

    reason = (
        f"R/R {score:.1f} > zasloužené {deserved:.1f} "
        f"({cylinders} válců) · {decision.agreement}: {decision.reason} "
        f"· cíl {target_pct:.1f} % ze stropu {decision.max_position_pct:g} %"
    )
    if decision.review_required:
        reason += " · ⚠️ REVIEW_REQUIRED"

    return ActionItem(
        id=f"BUY-{ticker}",
        ticker=ticker,
        source_key=source_key,
        action_type="BUY",
        current_price=price,
        currency="USD",
        target_price=analysis.red_line,
        quantity=float(quantity),
        estimated_czk_value=round(quantity * price_czk, 2),
        reason=reason,
        urgency_score=urgency,
        review_required=decision.review_required,
        limit_price=round(limit, 4) if limit is not None else None,
        limit_currency="USD",
        valid_until=_valid_until(now),
        invalidated_if=_invalidation_note("BUY"),
    )


#: How long an instruction stands before the app has to look again. Two weeks
#: is long enough to survive a fortnight away and short enough that nothing is
#: acted on that has not been re-checked since the market moved.
INSTRUCTION_VALID_FOR = timedelta(days=14)


def _valid_until(now: datetime) -> date:
    return (now + INSTRUCTION_VALID_FOR).date()


def _invalidation_note(action_type: str) -> str:
    """
    What would make this instruction wrong before it expires.

    Said in the instruction itself rather than left to be remembered. Someone
    coming back to a two-week-old order needs to know what to re-check, and the
    honest answer differs by direction: a purchase stops being valid when the
    market stops being green, a reduction does not.
    """
    if action_type in ("BUY", "ADD"):
        return (
            "Neplatí, když cena vystoupá nad limit, když Gomes pohne čárou "
            "nebo když semafor přestane být zelený"
        )
    if action_type == CONFLICT_ACTION:
        # Not an order, so nothing to invalidate — what ends it is one of the
        # two sides changing, or you deciding.
        return (
            "Rozpor zmizí, až Gomes pohne čárou nebo se změní fáze cyklu "
            "— nebo až rozhodneš ty"
        )
    return "Neplatí, když Gomes pohne čárou"


def _make_action(
    action_type: str,
    ticker: str,
    pos: PositionInput,
    quantity: float,
    rate: float,
    reason: str,
    urgency: int,
    target_price: float | None = None,
    review_required: bool = False,
    source_key: str = "GOMES",
    limit_price: float | None = None,
    limit_currency: str | None = None,
    valid_until: date | None = None,
) -> ActionItem:
    return ActionItem(
        id=f"{action_type}-{ticker}",
        ticker=ticker,
        source_key=source_key,
        action_type=action_type,
        current_price=pos.current_price,
        currency=pos.currency,
        target_price=target_price,
        quantity=round(quantity, 4),
        estimated_czk_value=round(quantity * pos.current_price * rate, 2),
        reason=reason,
        urgency_score=urgency,
        review_required=review_required,
        limit_price=round(limit_price, 4) if limit_price is not None else None,
        limit_currency=limit_currency,
        valid_until=valid_until,
        invalidated_if=_invalidation_note(action_type),
    )
