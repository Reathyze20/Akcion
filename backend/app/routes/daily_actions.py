"""
Daily Actions API — Path 1: "Co mám dnes udělat?"

One endpoint that answers the daily question in ≤2 minutes: at most 3 ranked
executable actions with exact CZK amounts, or the rest state "Nic. Drž."
All rule logic lives in app.services.daily_actions (pure, unit-tested);
this module only loads the DB snapshot and delegates.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.gomes import StockLifecycleModel
from app.core.tickers import canonical_ticker
from app.models.portfolio import (
    InvestmentLog,
    InvestmentLogType,
    MarketStatus,
    Portfolio,
    Position,
)
from app.models.stock import Stock
from app.schemas.daily_actions import (
    BoardCardOut,
    BoardResponse,
    DailyActionResponse,
    DailyActionsByOwner,
    OwnerActions,
)
from app.services.breakout_lookup import breakout_views
from app.services.currency import CurrencyService
from app.services.emotional_brakes import check_reentry, collect_brakes
from app.services.daily_actions import (
    AnalysisInput,
    PositionInput,
    generate_daily_actions,
)
from app.services.earnings_calendar import upcoming
from app.services.concentration_lookup import portfolio_concentration
from app.services.pacing import pacing_check
from app.services.unvalued_lookup import unvalued_findings
from app.services.refused_buys import collector
from app.services import market_catalyst
from app.services.tracker_sync import recent_line_notes

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
    portfolio_id: int | None = None,
) -> tuple[
    str | None, datetime | None, list[PositionInput], list[AnalysisInput], float | None
]:
    """
    Snapshot everything the engine needs. Kept separate so tests can patch it.

    Returns (market_alert, alert_updated_at, positions, analyses, cash_czk).
    market_alert is None when the semafor was never set — the engine warns
    instead of defaulting to GREEN, and the timestamp lets it tell a current
    reading from one that has been sitting there for months.

    `portfolio_id` scopes the positions AND the cash to one account. Without it
    this function summed both accounts into a pot that exists nowhere: a
    holding worth 12 % of one account came out as 6 % of the total and passed a
    cap it should have failed, and one person's cash silently funded a purchase
    offered to the other. Every caller in the app now names an account; the
    unscoped form remains only because a portfolio-less database is still a
    valid state on first run.
    """
    status_row = db.query(MarketStatus).first()
    market_alert = status_row.status.value if status_row else None
    alert_updated_at = status_row.last_updated if status_row else None

    portfolio_query = db.query(Portfolio)
    if portfolio_id is not None:
        portfolio_query = portfolio_query.filter(Portfolio.id == portfolio_id)
    portfolios = portfolio_query.all()
    # cash_balance is CZK by app convention (see portfolio summary endpoint).
    cash_czk = sum(p.cash_balance or 0.0 for p in portfolios) if portfolios else None

    position_query = db.query(Position).filter(Position.shares_count > 0)
    if portfolio_id is not None:
        position_query = position_query.filter(Position.portfolio_id == portfolio_id)

    positions = [
        PositionInput(
            ticker=pos.ticker,
            shares=pos.shares_count or 0.0,
            avg_cost=pos.avg_cost,  # None = unknown, engine warns
            currency=pos.currency or "USD",
            currency_confirmed=bool(pos.currency_confirmed),
            current_price=pos.current_price,
            last_price_update=pos.last_price_update,
        )
        # shares_count > 0: prodaná pozice zůstává v databázi kvůli historii
        # (trade_ledger.py:202 ji nuluje, nemaže), ale pokyn se k ní vydávat
        # nemá — aplikace by radila k něčemu, co člověk nedrží.
        for pos in position_query.all()
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

    # The R/R score each position was opened at, keyed canonically so a
    # purchase recorded as KUYAF is found for a position held as KUYA.V.
    # Absent for everything bought before the column existed, and the
    # three-point rule then stays silent rather than inventing a starting
    # point.
    entry_scores: dict[str, float] = {}
    for log in (
        db.query(InvestmentLog)
        .filter(InvestmentLog.log_type == InvestmentLogType.BUY)
        .filter(InvestmentLog.rr_score_at_entry.isnot(None))
        .order_by(desc(InvestmentLog.created_at))
        .all()
    ):
        key = canonical_ticker(log.ticker or "")
        if key and key not in entry_scores:
            entry_scores[key] = float(log.rr_score_at_entry)

    # When each company reports. The canon's fourteen-day blackout has been
    # implemented since the app was written and has never fired, because
    # nothing ever supplied it a date.
    earnings = upcoming(db)
    today = datetime.utcnow().date()

    analyses: list[AnalysisInput] = []
    for stock in stock_rows:
        ticker = (stock.ticker or "").upper()
        if not ticker:
            continue
        lifecycle = lifecycle_by_ticker.get(ticker)
        # ONLY the confirmed lifecycle row. `stocks.inflection_status` used to
        # stand in when the row was missing, and it is a legacy field nobody
        # confirmed — GSI.V, IRIX and KUYA.V all carry WAIT_TIME on it from an
        # import in January. A yellow market sells Wait Time outright, so that
        # fallback was an unconfirmed field authorising a sale. A company with
        # no confirmed stage is UNKNOWN and the app names it instead.
        phase = lifecycle.phase if lifecycle is not None else None
        analyses.append(
            AnalysisInput(
                ticker=ticker,
                source_key=stock.source_key or "OTHER",
                green_line=stock.green_line,
                red_line=stock.red_line,
                line_currency=stock.line_currency,
                asset_class=stock.asset_class,
                cylinders=lifecycle.cylinders_count if lifecycle is not None else None,
                # Proposal versus confirmation. The engine reads the first two
                # for selling and requires all three for buying.
                cylinders_confirmed_at=(
                    lifecycle.cylinders_confirmed_at if lifecycle is not None else None
                ),
                cylinders_valid_until=(
                    lifecycle.cylinders_valid_until if lifecycle is not None else None
                ),
                entry_score=entry_scores.get(canonical_ticker(ticker)),
                days_to_earnings=(
                    row.days_until(today)
                    if (row := earnings.get(canonical_ticker(ticker))) is not None
                    else None
                ),
                earnings_confirmed=(
                    bool(row.confirmed)
                    if (row := earnings.get(canonical_ticker(ticker))) is not None
                    else True
                ),
                lifecycle_phase=phase,
                rough_patch=bool(
                    lifecycle.rough_patch if lifecycle is not None else False
                ),
                rough_patch_since=(
                    lifecycle.rough_patch_since if lifecycle is not None else None
                ),
                conviction_score=stock.conviction_score,
                action_verdict=stock.action_verdict,
                current_price=stock.current_price,
            )
        )

    # Breakout's side, as a second row per company rather than as fields on the
    # first. Two sources that overwrite each other cannot disagree, and the
    # whole point of the second one is that it may refuse.
    #
    # These rows carry a target and usually no floor, which is deliberate: the
    # buy loop iterates the GOMES rows only, so a Breakout row can never open a
    # position by itself. It is read for one thing — whether a named analyst
    # said no.
    for ticker, view in breakout_views(db).items():
        analyses.append(
            AnalysisInput(
                ticker=view.ticker,
                source_key="BREAKOUT_INVESTORS",
                green_line=view.green_line,
                red_line=view.red_line,
                # Their targets quote the US listing, same as Gomes'.
                line_currency="USD",
                action_verdict=view.action_verdict,
            )
        )

    return market_alert, alert_updated_at, positions, analyses, cash_czk


def _actions_for(db: Session, portfolio: Portfolio) -> DailyActionResponse:
    """
    One account's answer, with every weight measured against that account.

    The engine is called once per portfolio rather than once over the sum,
    because a position cap is a statement about a share of ONE account and
    means nothing against a total nobody holds.
    """
    (
        market_alert,
        alert_updated_at,
        positions,
        analyses,
        cash_czk,
    ) = load_daily_action_inputs(db, portfolio_id=portfolio.id)

    # Read separately from the snapshot above, which tests patch wholesale. A
    # missing row is not a problem here: no row means no cause recorded, and
    # `note_for` stays silent unless the grade actually claims one.
    status_row = db.query(MarketStatus).first()

    def brakes(portfolio_value_czk: float) -> list[str]:
        """What the trade ledger says about the last few days."""
        return [brake.message for brake in collect_brakes(db, portfolio_value_czk)]

    response = generate_daily_actions(
        market_alert=market_alert,
        market_alert_updated_at=alert_updated_at,
        positions=positions,
        analyses=analyses,
        cash_czk=cash_czk,
        fx_rate_to_czk=CurrencyService.get_rate_to_czk,
        behaviour_brakes=brakes,
        reentry_note=lambda ticker: (
            brake.message
            if (brake := check_reentry(db, ticker)) is not None
            else None
        ),
        refusal_sink=collector(db),
        source_notes=recent_line_notes(db),
        alert_note=market_catalyst.note_for(market_alert, status_row),
        pacing=pacing_check(db, portfolio_id=portfolio.id),
        unvalued=unvalued_findings(db, positions),
        concentration=portfolio_concentration(db, positions),
    )

    # Whose instruction this is. Stamped here rather than threaded through the
    # engine: the engine answers about one account at a time and does not need
    # to know which, but a screen showing both does.
    response.actions = [
        action.model_copy(
            update={"portfolio_id": portfolio.id, "owner": portfolio.owner}
        )
        for action in response.actions
    ]
    return response


def _commit_refusals(db: Session) -> None:
    """
    The refusals are the other half of the record, committed on their own.

    If this write fails the owner still gets today's actions: a lost
    measurement is recoverable, a lost morning is not.
    """
    try:
        db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("Odmítnuté nákupy se nepodařilo zapsat")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            logger.exception("Rollback po neúspěšném zápisu selhal")


@router.get("/daily-actions/by-owner", response_model=DailyActionsByOwner)
def get_daily_actions_by_owner(db: Session = Depends(get_db)):
    """
    Every account answered separately, never merged.

    Two people use this app and their positions differ, so the same stock can
    be a trim for one and a hold for the other — the weight it takes up is a
    fact about an account. A single merged list could not say whose turn it is
    to act, and the caps behind it would be wrong for both.
    """
    try:
        portfolios = db.query(Portfolio).order_by(Portfolio.id).all()
        sections = [
            OwnerActions(
                portfolio_id=p.id,
                owner=p.owner,
                portfolio_name=p.name,
                response=_actions_for(db, p),
            )
            for p in portfolios
        ]
        _commit_refusals(db)
    except Exception as e:
        logger.exception("Daily actions by owner failed")
        raise HTTPException(status_code=500, detail=f"Daily actions failed: {e}")

    alert = sections[0].response.market_alert if sections else "UNKNOWN"
    return DailyActionsByOwner(market_alert=alert, sections=sections)


@router.get("/daily-actions", response_model=DailyActionResponse)
def get_daily_actions(
    portfolio_id: int | None = Query(
        None,
        description=(
            "Which account to answer for. Omit and every account is answered "
            "separately and the results listed together — never summed."
        ),
    ),
    db: Session = Depends(get_db),
) -> DailyActionResponse:
    """
    "Co mám dnes udělat?" — ranked actions per account, or "Nic. Drž."

    - De-risk first: Yellow/Orange/Red sells Wait-Time and alert-blocked tiers.
    - Doubling rule and R/R-vs-cylinders trims on held positions.
    - BUYs only through the hard Buy Guard (GREEN + confirmed cylinders + score
      above deserved), sized by dual-source agreement and the account's cash.
    - Missing data becomes a warning ("CHYBÍ ÚDAJE"), never a number.

    Without `portfolio_id` the accounts are still computed one at a time and
    only then listed together, so no cap is ever measured against a total
    nobody holds. `/daily-actions/by-owner` keeps them in labelled sections.
    """
    try:
        query = db.query(Portfolio).order_by(Portfolio.id)
        if portfolio_id is not None:
            query = query.filter(Portfolio.id == portfolio_id)
        portfolios = query.all()

        if portfolio_id is not None and not portfolios:
            raise HTTPException(status_code=404, detail="Portfolio nenalezeno")

        if not portfolios:
            # No account on record at all — a valid first-run state, and the
            # engine still has something to say about the market itself.
            (
                market_alert,
                alert_updated_at,
                positions,
                analyses,
                cash_czk,
            ) = load_daily_action_inputs(db)
            return generate_daily_actions(
                market_alert=market_alert,
                market_alert_updated_at=alert_updated_at,
                positions=positions,
                analyses=analyses,
                cash_czk=cash_czk,
                fx_rate_to_czk=CurrencyService.get_rate_to_czk,
            )

        answers = [_actions_for(db, p) for p in portfolios]
        _commit_refusals(db)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Daily actions failed")
        # Honest failure: an error response, never a fake empty "Nic. Drž."
        raise HTTPException(status_code=500, detail=f"Daily actions failed: {e}")

    if len(answers) == 1:
        return answers[0]

    # Several accounts, one list. Each account kept its own cap; what is merged
    # is only the presentation, and every item still says whose it is.
    merged_actions = sorted(
        (a for answer in answers for a in answer.actions),
        key=lambda a: (-a.urgency_score, a.owner or "", a.ticker),
    )
    seen: set[str] = set()
    merged_warnings: list[str] = []
    for answer in answers:
        for warning in answer.warnings:
            if warning not in seen:
                seen.add(warning)
                merged_warnings.append(warning)

    return DailyActionResponse(
        market_alert=answers[0].market_alert,
        available_cash_czk=round(sum(a.available_cash_czk for a in answers), 2),
        status="ACTION_REQUIRED" if merged_actions else "HOLD_HOLD_HOLD",
        actions=merged_actions,
        warnings=merged_warnings,
    )


@router.get("/board", response_model=BoardResponse)
def get_board(db: Session = Depends(get_db)):
    """
    One card per company: the band, its two limit prices, what Breakout thinks,
    and an instruction for each account.

    Why this exists next to `/daily-actions`
    ----------------------------------------
    The daily list answers "what do I do today" and deliberately shows at most
    three things. This answers the other question two people holding one
    portfolio actually ask — "what is our position on each of these" — and it
    answers it for both of them at once, on one screen, without either having to
    read the other's numbers to work out their own.

    The band is computed once per company; the instruction is computed once per
    account and never against the two summed. A holding that is 12 % of her
    account is 6 % of the total, and measuring caps against the total let it
    pass a limit it was meant to fail.
    """
    from app.services.decision_board import build_board

    try:
        cards, warnings = build_board(
            db,
            fx_rate_to_czk=CurrencyService.get_rate_to_czk,
            actions_for_portfolio=_actions_for,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("Tabuli se nepodařilo sestavit")
        raise HTTPException(status_code=500, detail=f"Tabuli nelze sestavit: {e}")

    _commit_refusals(db)

    # Read the same way `load_daily_action_inputs` reads it, so the board and
    # the daily list can never show two different semafor levels.
    status_row = db.query(MarketStatus).first()

    return BoardResponse(
        generated_at=datetime.utcnow(),
        cards=[BoardCardOut.model_validate(c, from_attributes=True) for c in cards],
        warnings=warnings,
        market_alert=status_row.status.value if status_row else None,
    )
