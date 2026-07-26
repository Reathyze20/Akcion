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
    avg_cost: float
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
    positions: list[PositionInput],
    analyses: list[AnalysisInput],
    cash_czk: float | None,
    fx_rate_to_czk: Callable[[str], float],
    now: datetime | None = None,
) -> DailyActionResponse:
    """
    Build the daily action list. Pure function — inject FX and clock for tests.

    `analyses` should hold the latest take per (ticker, source_key); tickers
    not in `positions` are treated as watchlist BUY candidates.
    """
    now = now or datetime.utcnow()
    warnings: list[str] = []

    alert = _normalize_alert(market_alert, warnings)

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
            warnings.append(
                f"⚠️ CHYBÍ ÚDAJE: {ticker} nemá aktuální cenu — pravidla "
                f"nelze vyhodnotit, ověř ručně"
            )
            continue

        if pos.last_price_update is None:
            warnings.append(
                f"⚠️ STÁŘÍ CENY NEZNÁMÉ: {ticker} — cena bez časového razítka, "
                f"ověř před obchodem"
            )
        elif now - pos.last_price_update > STALE_PRICE_AFTER:
            warnings.append(
                f"⚠️ STARÁ CENA: {ticker} naposledy aktualizována "
                f"{pos.last_price_update:%Y-%m-%d} — ověř před obchodem"
            )

        rate = fx_rate_to_czk(pos.currency)
        position_value_czk = pos.shares * pos.current_price * rate
        portfolio_value_czk += position_value_czk

        best = _derisk_action(alert, pos, ticker, phase, analysis, rate)

        if best is None:
            best = _doubling_action(pos, ticker, rate)

        if best is None and analysis is not None:
            best = _rr_trim_action(pos, ticker, analysis, rate)

        if best is not None:
            candidates.append(best)

    # ------------------------------------------------------------------
    # Watchlist: BUY candidates through the hard Buy Guard
    # ------------------------------------------------------------------
    for ticker, analysis in sorted(gomes_by_ticker.items()):
        if ticker in held_tickers:
            continue
        buy = _buy_action(
            alert, ticker, analysis, breakout_by_ticker.get(ticker),
            cash_czk, portfolio_value_czk, fx_rate_to_czk,
        )
        if buy is not None:
            candidates.append(buy)

    # ------------------------------------------------------------------
    # Rank, cap at 3, decide the day's status
    # ------------------------------------------------------------------
    candidates.sort(key=lambda a: (-a.urgency_score, a.ticker))
    actions = candidates[:MAX_ACTIONS]

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

    conviction = analysis.conviction_score if analysis and analysis.conviction_score is not None else 0
    tier = PositionSizingEngine.determine_tier(phase, conviction)
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
    rate = fx_rate_to_czk("USD")
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
