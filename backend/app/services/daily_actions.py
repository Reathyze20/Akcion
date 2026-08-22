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
from datetime import datetime, timedelta
from typing import Callable

from app.core.sources import verdict_stance
from app.services.currency import CurrencyError, currency_mismatch
from app.schemas.daily_actions import ActionItem, DailyActionResponse
from app.trading.gomes_logic import (
    GomesGatekeeper,
    LifecyclePhase,
    MarketAlert,
    MarketAlertSystem,
    PositionSizingEngine,
    RiskRewardCalculator,
    evaluate_dual_source_buy,
)

logger = logging.getLogger(__name__)

MAX_ACTIONS = 3
STALE_PRICE_AFTER = timedelta(days=3)
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
URGENCY_BUY_BASE = 40  # + up to 20 by score margin


@dataclass
class PositionInput:
    """A held position, as read from the positions table."""
    ticker: str
    shares: float
    # None = purchase price unknown (Degiro imports carry none) — the
    # doubling rule is disarmed and a warning nags until the user fills it.
    avg_cost: float | None
    currency: str = "USD"
    current_price: float | None = None
    last_price_update: datetime | None = None


@dataclass
class AnalysisInput:
    """Latest analysis for (ticker, source), merged with lifecycle data."""
    ticker: str
    source_key: str  # GOMES | BREAKOUT_INVESTORS | OTHER
    green_line: float | None = None
    red_line: float | None = None
    cylinders: int | None = None
    lifecycle_phase: str | None = None  # GREAT_FIND | WAIT_TIME | GOLD_MINE | UNKNOWN
    conviction_score: int | None = None
    action_verdict: str | None = None
    current_price: float | None = None


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
    """
    now = now or datetime.utcnow()
    warnings: list[str] = []

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

    gomes_by_ticker = {
        a.ticker.upper(): a for a in analyses if a.source_key == "GOMES"
    }
    breakout_by_ticker = {
        a.ticker.upper(): a for a in analyses if a.source_key == "BREAKOUT_INVESTORS"
    }
    held_tickers = {p.ticker.upper() for p in positions if p.shares > 0}

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

    # ------------------------------------------------------------------
    # Held positions: de-risk, doubling rule, R/R trims
    # ------------------------------------------------------------------
    for pos in positions:
        if pos.shares <= 0:
            continue
        ticker = pos.ticker.upper()
        analysis = gomes_by_ticker.get(ticker)
        phase = _resolve_phase(analysis)

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
        # currency. When they disagree the CZK value is wrong by the ratio
        # between the two — and nothing else in the app would notice.
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

        best = _derisk_action(alert, pos, ticker, phase, analysis, rate, unjudgeable)

        if best is None:
            best = _doubling_action(pos, ticker, rate)

        if best is None and analysis is not None:
            best = _rr_trim_action(pos, ticker, analysis, rate)

        if best is not None:
            candidates.append(best)

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
        "⚠️ NEZNÁMÁ KVALITA: {t} nemá fázi ani konvikční skóre — v {alert} "
        "Alert nedokážu posoudit, jestli ji držet; rozhodni sám",
        "⚠️ NEZNÁMÁ KVALITA u {n} pozic ({tickers}) — chybí fáze i konvikční "
        "skóre, v {alert} Alert je neposoudím; rozhodni sám",
        alert=alert.value if alert else "?",
    )
    _grouped(
        warnings, currency_conflict,
        "⚠️ MĚNA NESEDÍ S BURZOU: {t} — hodnota v CZK je o tenhle poměr vedle; "
        "oprav měnu v detailu pozice",
        "⚠️ MĚNA NESEDÍ S BURZOU u {n} pozic ({tickers}) — jejich hodnota v CZK "
        "je o poměr těch měn vedle; oprav je v detailu pozic",
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
    # Watchlist: BUY candidates through the hard Buy Guard
    # ------------------------------------------------------------------
    for ticker, analysis in sorted(gomes_by_ticker.items()):
        if ticker in held_tickers:
            continue
        buy = _buy_action(
            buy_alert, ticker, analysis, breakout_by_ticker.get(ticker),
            cash_czk, portfolio_value_czk, fx_rate_to_czk,
        )
        if buy is not None:
            candidates.append(buy)

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
        warnings=warnings,
        generated_at=now,
    )


# ==============================================================================
# Rule helpers
# ==============================================================================

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


def _resolve_phase(analysis: AnalysisInput | None) -> LifecyclePhase:
    if analysis is None or not analysis.lifecycle_phase:
        return LifecyclePhase.UNKNOWN
    try:
        return LifecyclePhase(analysis.lifecycle_phase.upper())
    except ValueError:
        return LifecyclePhase.UNKNOWN


def _derisk_action(
    alert: MarketAlert | None,
    pos: PositionInput,
    ticker: str,
    phase: LifecyclePhase,
    analysis: AnalysisInput | None,
    rate: float,
    unjudgeable: list[str],
) -> ActionItem | None:
    """Yellow/Orange/Red: exit Wait-Time and alert-blocked tiers."""
    if alert is None or alert == MarketAlert.GREEN:
        return None

    if alert == MarketAlert.RED:
        return _make_action(
            "LIQUIDATE_HEAVY", ticker, pos, pos.shares, rate,
            f"🔴 RED Alert — prodej téměř vše, hotovost je král "
            f"({pos.shares:g} ks {ticker})",
            URGENCY_LIQUIDATE,
        )

    if phase == LifecyclePhase.WAIT_TIME:
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
    conviction = analysis.conviction_score if analysis else None
    if phase == LifecyclePhase.UNKNOWN and conviction is None:
        unjudgeable.append(ticker)
        return None

    tier = PositionSizingEngine.determine_tier(phase, conviction or 0)
    if tier in MarketAlertSystem.get_blocked_tiers(alert):
        return _make_action(
            "SELL", ticker, pos, pos.shares, rate,
            f"{alert.value} Alert blokuje {tier.value} pozice — "
            f"spekulace se v tomto trhu nedrží",
            URGENCY_SELL_BLOCKED_TIER,
        )
    return None


def _doubling_action(pos: PositionInput, ticker: str, rate: float) -> ActionItem | None:
    """Doubled -> sell half, play with house money."""
    if pos.avg_cost is None:
        return None  # unknown cost -> rule disarmed (warned in main loop)
    if pos.avg_cost <= 0 or pos.current_price < 2 * pos.avg_cost:
        return None
    gain_pct = (pos.current_price - pos.avg_cost) / pos.avg_cost * 100
    half = pos.shares / 2
    return _make_action(
        "TRIM", ticker, pos, half, rate,
        f"Doubling rule: +{gain_pct:.0f}% od nákupu — prodej polovinu, "
        f"zbytek jede za peníze domu",
        URGENCY_TRIM_DOUBLED,
    )


def _rr_trim_action(
    pos: PositionInput, ticker: str, analysis: AnalysisInput, rate: float
) -> ActionItem | None:
    """R/R score below deserved (10 − cylinders) -> expensive for quality, trim."""
    score = RiskRewardCalculator.calculate_rr_score(
        pos.current_price, analysis.green_line, analysis.red_line
    )
    zone, zone_reason = RiskRewardCalculator.decide_from_score(score, analysis.cylinders)
    if zone != "SELL":
        return None
    half = pos.shares / 2
    return _make_action(
        "TRIM", ticker, pos, half, rate,
        f"R/R: {zone_reason} — vezmi zisk z poloviny pozice",
        URGENCY_TRIM_RR,
        target_price=analysis.red_line,
    )


def _buy_action(
    alert: MarketAlert | None,
    ticker: str,
    analysis: AnalysisInput,
    breakout: AnalysisInput | None,
    cash_czk: float,
    portfolio_value_czk: float,
    fx_rate_to_czk: Callable[[str], float],
) -> ActionItem | None:
    """Watchlist candidate must pass the hard Buy Guard + dual-source sizing."""
    price = analysis.current_price
    if price is None or price <= 0:
        return None  # no price -> no invented BUY

    score = RiskRewardCalculator.calculate_rr_score(
        price, analysis.green_line, analysis.red_line
    )
    deserved = RiskRewardCalculator.deserved_score(analysis.cylinders)
    phase = _resolve_phase(analysis)

    allowed, guard_reason = GomesGatekeeper.evaluate_buy_guard(
        market_alert=alert.value if alert else "UNKNOWN",
        rr_score=score,
        deserved_score=deserved,
        cylinders=analysis.cylinders,
        lifecycle_stage=phase,
    )
    if not allowed:
        return None

    conviction = analysis.conviction_score if analysis.conviction_score is not None else 0
    tier = PositionSizingEngine.determine_tier(phase, conviction)
    tier_max = PositionSizingEngine.get_position_limit(tier, ticker).max_portfolio_pct

    stance = verdict_stance(breakout.action_verdict) if breakout else None
    decision = evaluate_dual_source_buy(True, guard_reason, stance, tier_max)
    if decision.decision != "ALLOW" or decision.max_position_pct <= 0:
        return None

    budget_czk = min(
        portfolio_value_czk * decision.max_position_pct / 100.0, cash_czk
    )
    try:
        rate = fx_rate_to_czk("USD")
    except CurrencyError:
        return None  # cannot size a purchase without a rate; propose nothing
    price_czk = price * rate
    quantity = math.floor(budget_czk / price_czk) if price_czk > 0 else 0
    if quantity < 1:
        return None  # not enough cash for a single share — no action

    margin = (score - deserved) if score is not None and deserved is not None else 0.0
    urgency = URGENCY_BUY_BASE + min(20, max(0, round(margin * 4)))
    source_key = "COMBINED" if stance in ("BULLISH", "BEARISH") else "GOMES"
    reason = (
        f"R/R {score:.1f} > zasloužené {deserved:.1f} "
        f"({analysis.cylinders} válců) · {decision.agreement}: {decision.reason} "
        f"· max {decision.max_position_pct:g} % portfolia"
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
    )


def _make_action(
    action_type: str,
    ticker: str,
    pos: PositionInput,
    quantity: float,
    rate: float,
    reason: str,
    urgency: int,
    target_price: float | None = None,
) -> ActionItem:
    return ActionItem(
        id=f"{action_type}-{ticker}",
        ticker=ticker,
        source_key="GOMES",
        action_type=action_type,
        current_price=pos.current_price,
        currency=pos.currency,
        target_price=target_price,
        quantity=round(quantity, 4),
        estimated_czk_value=round(quantity * pos.current_price * rate, 2),
        reason=reason,
        urgency_score=urgency,
    )
