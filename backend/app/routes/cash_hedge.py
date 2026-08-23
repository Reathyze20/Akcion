"""
Cash and hedge API — the semafor turned into instruments and amounts.

The response leads with what cannot be executed. Both instruments the canon
names are US funds and this portfolio is held through EU retail brokers, so for
any defensive alert the honest headline is the blocker and the canon's own
fallback, not a target in shares.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.portfolio import MarketStatus, Portfolio, Position
from app.services.cash_hedge import (
    UCITS_INVERSE_EXAMPLE,
    HedgeError,
    build_plan,
)
from app.services.currency import CurrencyError, CurrencyService

router = APIRouter(prefix="/api/cash-hedge", tags=["cash-hedge"])


class LegOut(BaseModel):
    ticker: str
    name: str
    role: str
    currency: str
    exchange: str
    availability: str
    note_cs: str
    target_czk: float
    price: float | None = None
    shares: float | None = Field(
        default=None,
        description="None when the price or the rate could not be read.",
    )
    blocker_cs: str | None = None


class PlanOut(BaseModel):
    alert: str
    portfolio_czk: float
    stocks_pct: float
    cash_pct: float
    hedge_pct: float
    canon_text: str
    interpreted: bool = Field(
        description=(
            "True when the percentages are the app's reading, not the canon's. "
            "The canon gives a number for GREEN and YELLOW only."
        )
    )
    legs: list[LegOut]
    fallback_cs: str | None = None
    ucits_example: LegOut | None = Field(
        default=None,
        description=(
            "Named because it exists, not as a substitute — different index, "
            "daily reset. Only returned when the canon's instruments are blocked."
        ),
    )
    gaps: list[str] = Field(default_factory=list)


def _leg_out(leg) -> LegOut:
    instrument = leg.instrument
    return LegOut(
        ticker=instrument.ticker,
        name=instrument.name,
        role=instrument.role.value,
        currency=instrument.currency,
        exchange=instrument.exchange,
        availability=instrument.availability.value,
        note_cs=instrument.note_cs,
        target_czk=round(leg.target_czk, 2),
        price=leg.price,
        shares=round(leg.shares, 2) if leg.shares is not None else None,
        blocker_cs=leg.blocker_cs,
    )


@router.get("", response_model=PlanOut)
def get_plan(
    alert: str | None = Query(
        None, description="Přebít semafor. Bez toho se bere ten nastavený."
    ),
    db: Session = Depends(get_db),
) -> PlanOut:
    """
    How much cash and hedge the semafor implies, in real instruments.

    Returns 400 rather than a plan when the semafor is unset — planning for
    GREEN because nobody touched the field is how a portfolio ends up unhedged
    by accident.
    """
    if alert is None:
        status_row = db.query(MarketStatus).first()
        alert = status_row.status.value if status_row else None

    portfolio_czk, gaps = _portfolio_value(db)

    try:
        plan = build_plan(
            alert, portfolio_czk, fx_rate_to_czk=CurrencyService.get_rate_to_czk,
        )
    except HedgeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    blocked = any(leg.blocker_cs for leg in plan.legs if leg.target_czk > 0)
    example = None
    if blocked:
        from app.services.cash_hedge import Leg

        example = _leg_out(Leg(
            instrument=UCITS_INVERSE_EXAMPLE,
            target_czk=0.0,
            price=None,
            shares=None,
        ))

    return PlanOut(
        alert=plan.alert,
        portfolio_czk=round(plan.portfolio_czk, 2),
        stocks_pct=plan.stocks_pct,
        cash_pct=plan.cash_pct,
        hedge_pct=plan.hedge_pct,
        canon_text=plan.canon_text,
        interpreted=plan.interpreted,
        legs=[_leg_out(leg) for leg in plan.legs],
        fallback_cs=plan.fallback_cs,
        ucits_example=example,
        gaps=(plan.gaps or []) + gaps,
    )


def _portfolio_value(db: Session) -> tuple[float, list[str]]:
    """
    Everything held, in CZK, plus the positions that could not be counted.

    A position with no price or an unconvertible currency is left out of the
    total and named — folding it in at zero would shrink the base every
    percentage here is computed from.
    """
    total = sum(p.cash_balance or 0.0 for p in db.query(Portfolio).all())
    gaps: list[str] = []

    for position in db.query(Position).all():
        shares = position.shares_count or 0.0
        if not position.current_price or not shares:
            gaps.append(
                f"{position.ticker}: bez ceny, do základu pro procenta se "
                f"nepočítá."
            )
            continue
        try:
            rate = CurrencyService.get_rate_to_czk(position.currency or "USD")
        except CurrencyError as e:
            gaps.append(f"{position.ticker}: {e}")
            continue
        total += shares * position.current_price * rate

    return total, gaps
