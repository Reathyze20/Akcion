"""
Daily Actions API — Path 1: "Co mám dnes udělat?"

One endpoint that answers the daily question in ≤2 minutes: at most 3 ranked
executable actions with exact CZK amounts, or the rest state "Nic. Drž."
All rule logic lives in app.services.daily_actions (pure, unit-tested);
this module only loads the DB snapshot and delegates.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.gomes import StockLifecycleModel
from app.models.portfolio import MarketStatus, Portfolio, Position
from app.models.stock import Stock
from app.schemas.daily_actions import DailyActionResponse
from app.services.currency import CurrencyService
from app.services.daily_actions import (
    AnalysisInput,
    PositionInput,
    generate_daily_actions,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/trading", tags=["Daily Actions"])

# Stock.inflection_status -> canonical lifecycle phase
_INFLECTION_TO_PHASE = {
    "WAIT_TIME": "WAIT_TIME",
    "ACTIVE_GOLD_MINE": "GOLD_MINE",
    "UPCOMING": "GREAT_FIND",
}


def load_daily_action_inputs(
    db: Session,
) -> tuple[str | None, list[PositionInput], list[AnalysisInput], float | None]:
    """
    Snapshot everything the engine needs. Kept separate so tests can patch it.

    Returns (market_alert, positions, analyses, cash_czk). market_alert is
    None when the semafor was never set — the engine warns instead of
    defaulting to GREEN.
    """
    status_row = db.query(MarketStatus).first()
    market_alert = status_row.status.value if status_row else None

    portfolios = db.query(Portfolio).all()
    # cash_balance is CZK by app convention (see portfolio summary endpoint).
    cash_czk = sum(p.cash_balance or 0.0 for p in portfolios) if portfolios else None

    positions = [
        PositionInput(
            ticker=pos.ticker,
            shares=pos.shares_count or 0.0,
            avg_cost=pos.avg_cost or 0.0,
            currency=pos.currency or "USD",
            current_price=pos.current_price,
            last_price_update=pos.last_price_update,
        )
        for pos in db.query(Position).all()
    ]

    # Latest analysis per (ticker, source) — Postgres DISTINCT ON.
    stock_rows = (
        db.query(Stock)
        .order_by(Stock.ticker, Stock.source_key, desc(Stock.created_at))
        .distinct(Stock.ticker, Stock.source_key)
        .all()
    )

    # Latest active lifecycle assessment per ticker (cylinders live here).
    lifecycle_by_ticker: dict[str, StockLifecycleModel] = {}
    lifecycle_rows = (
        db.query(StockLifecycleModel)
        .filter(StockLifecycleModel.valid_until.is_(None))
        .order_by(StockLifecycleModel.ticker, desc(StockLifecycleModel.detected_at))
        .all()
    )
    for row in lifecycle_rows:
        lifecycle_by_ticker.setdefault(row.ticker.upper(), row)

    analyses: list[AnalysisInput] = []
    for stock in stock_rows:
        ticker = (stock.ticker or "").upper()
        if not ticker:
            continue
        lifecycle = lifecycle_by_ticker.get(ticker)
        phase = (
            lifecycle.phase
            if lifecycle is not None
            else _INFLECTION_TO_PHASE.get(stock.inflection_status or "")
        )
        analyses.append(
            AnalysisInput(
                ticker=ticker,
                source_key=stock.source_key or "OTHER",
                green_line=stock.green_line,
                red_line=stock.red_line,
                cylinders=lifecycle.cylinders_count if lifecycle is not None else None,
                lifecycle_phase=phase,
                conviction_score=stock.conviction_score,
                action_verdict=stock.action_verdict,
                current_price=stock.current_price,
            )
        )

    return market_alert, positions, analyses, cash_czk


@router.get("/daily-actions", response_model=DailyActionResponse)
def get_daily_actions(db: Session = Depends(get_db)) -> DailyActionResponse:
    """
    "Co mám dnes udělat?" — max 3 ranked actions or "Nic. Drž."

    - De-risk first: Yellow/Orange/Red sells Wait-Time + blocked tiers.
    - Doubling rule and R/R-vs-cylinders trims on held positions.
    - BUYs only through the hard Buy Guard (GREEN + cylinders + score >
      deserved), sized by dual-source agreement and available cash.
    - Missing data becomes a warning ("⚠️ CHYBÍ ÚDAJE"), never a number.
    """
    try:
        market_alert, positions, analyses, cash_czk = load_daily_action_inputs(db)
        return generate_daily_actions(
            market_alert=market_alert,
            positions=positions,
            analyses=analyses,
            cash_czk=cash_czk,
            fx_rate_to_czk=CurrencyService.get_rate_to_czk,
        )
    except Exception as e:
        logger.exception("Daily actions failed")
        # Honest failure: an error response, never a fake empty "Nic. Drž."
        raise HTTPException(status_code=500, detail=f"Daily actions failed: {e}")
