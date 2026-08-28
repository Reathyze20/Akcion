"""
Trade ledger — recording a BUY/SELL so it can never be lost.

Why this module exists
----------------------
`investment_logs` has had `ticker`/`shares`/`price`/`emotion_tag` columns since
April, and no code path ever wrote a trade into it. Exits were recorded by
overwriting `positions.shares_count`, which throws away the sale price. The
consequences were not cosmetic:

  * realized P/L was unrecoverable — the app could never say what the owner
    actually made or lost,
  * cooldown-after-loss and revenge-trading detection were impossible to build,
    because nothing knew a loss had happened,
  * `emotion_tag` — the column meant to capture *why* a trade was made — had
    no writer at all.

Recording a trade therefore has to do two things **atomically**: append an
immutable ledger row, and move the position. If either half can fail alone,
the two diverge and the ledger stops being evidence.

Honesty rules encoded here (see docs/EFFICIENT_INVESTING_PLAYBOOK.md)
--------------------------------------------------------------------
1. An unknown purchase price stays unknown. Buying more of a position whose
   `avg_cost` is NULL (every pre-2026-07-26 Degiro import) cannot produce a
   weighted average — so it stays NULL rather than silently becoming the new
   purchase price. A wrong cost basis is worse than a missing one: it produces
   a confident, wrong P/L.
2. `realized_pl` is None when the cost basis is unknown. Never 0 — zero is a
   real value meaning "broke even" and must not double as "don't know".
3. You cannot sell more than you hold. That is a bug in the input, not a
   short position; this app does not model shorts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

from loguru import logger
from sqlalchemy.orm import Session

from app.models.portfolio import InvestmentLog, InvestmentLogType, Position
from app.trading.gomes_logic import RiskRewardCalculator


class TradeSide(str, Enum):
    """Direction of a recorded trade."""

    BUY = "BUY"
    SELL = "SELL"


class TradeError(ValueError):
    """Input that cannot describe a real trade (bad size, oversell, ...)."""


@dataclass(frozen=True)
class TradeOutcome:
    """
    Result of applying a trade to a position.

    `avg_cost_known` distinguishes "the average is 0.0" from "we don't know the
    average" — the caller must not collapse those two into one number.
    """

    new_shares: float
    new_avg_cost: float | None
    cost_basis: float | None
    realized_pl: float | None
    gross_amount: float

    @property
    def avg_cost_known(self) -> bool:
        return self.new_avg_cost is not None

    @property
    def closes_position(self) -> bool:
        return self.new_shares == 0


def compute_trade(
    *,
    old_shares: float,
    old_avg_cost: float | None,
    side: TradeSide,
    shares: float,
    price: float,
) -> TradeOutcome:
    """
    Pure trade math — no database, no I/O, fully unit-testable.

    Args:
        old_shares: shares held before the trade
        old_avg_cost: average purchase price before the trade, or None if unknown
        side: BUY or SELL
        shares: size of this trade (must be > 0)
        price: price per share actually paid/received (must be > 0)

    Returns:
        TradeOutcome describing the new position state and what was realized.

    Raises:
        TradeError: on a size/price that cannot describe a real trade.
    """
    if shares <= 0:
        raise TradeError("Počet akcií musí být kladné číslo.")
    if price <= 0:
        raise TradeError("Cena musí být kladné číslo.")

    gross_amount = shares * price

    if side is TradeSide.BUY:
        new_shares = old_shares + shares

        if old_shares <= 0:
            # Opening (or re-opening) a position: this trade *is* the cost basis.
            new_avg_cost: float | None = price
        elif old_avg_cost is None:
            # Rule 1: adding to a position of unknown cost cannot produce a
            # weighted average. Keep it unknown; the owner fills it in via the
            # position-edit form once he has the broker statement.
            new_avg_cost = None
        else:
            new_avg_cost = ((old_shares * old_avg_cost) + gross_amount) / new_shares

        return TradeOutcome(
            new_shares=new_shares,
            new_avg_cost=new_avg_cost,
            cost_basis=old_avg_cost,
            realized_pl=None,  # a purchase realizes nothing
            gross_amount=gross_amount,
        )

    # SELL
    if shares > old_shares:
        raise TradeError(
            f"Nemůžeš prodat {shares:g} akcií, držíš jen {old_shares:g}."
        )

    # Rule 2: no cost basis -> no realized P/L. None, never 0.
    realized_pl = (
        (price - old_avg_cost) * shares if old_avg_cost is not None else None
    )

    return TradeOutcome(
        new_shares=old_shares - shares,
        # Selling does not change what the remaining shares cost.
        new_avg_cost=old_avg_cost,
        cost_basis=old_avg_cost,
        realized_pl=realized_pl,
        gross_amount=gross_amount,
    )


def record_trade(
    db: Session,
    *,
    position_id: int,
    side: TradeSide,
    shares: float,
    price: float,
    emotion_tag: str | None = None,
    note: str | None = None,
    trade_date: date | None = None,
    green_line: float | None = None,
    red_line: float | None = None,
    cylinders: int | None = None,
    line_currency: str | None = None,
) -> tuple[Position, InvestmentLog, TradeOutcome]:
    """
    Append a ledger row and move the position, in one transaction.

    Either both land or neither does — a ledger that can drift from the
    positions it describes is not evidence of anything.

    Args:
        trade_date: the day it happened at the broker. Omit only when it is
            genuinely unknown — recording an old sale without it makes the
            behaviour brakes read it as today's.
        green_line, red_line, cylinders, line_currency: the valuation this
            trade was made at. From these the R/R score at entry is computed
            and stored, which is what makes the canon's 3-point rule (§5)
            possible at all: that rule fires on a 3-point move FROM ENTRY, and
            price alone cannot express it because the analyst moves the lines
            underneath the price. Omit them and the columns stay NULL — the
            rule then stays silent for this position rather than dating the
            move from a starting point that never existed.

    Raises:
        LookupError: no such position.
        TradeError: the trade itself is invalid (size, oversell, price).
    """
    position = db.query(Position).filter(Position.id == position_id).first()
    if position is None:
        raise LookupError(f"Position {position_id} not found")

    outcome = compute_trade(
        old_shares=position.shares_count or 0.0,
        old_avg_cost=position.avg_cost,
        side=side,
        shares=shares,
        price=price,
    )

    # The valuation this trade was made at. `calculate_rr_score` returns None
    # on missing or degenerate lines, so an unknown band produces an unknown
    # entry score rather than a fabricated one.
    entry_score = RiskRewardCalculator.calculate_rr_score(price, green_line, red_line)

    log = InvestmentLog(
        portfolio_id=position.portfolio_id,
        log_type=InvestmentLogType.BUY if side is TradeSide.BUY else InvestmentLogType.SELL,
        ticker=position.ticker,
        amount=outcome.gross_amount,
        shares=shares,
        price=price,
        cost_basis=outcome.cost_basis,
        realized_pl=outcome.realized_pl,
        currency=position.currency,
        rr_score_at_entry=entry_score,
        green_line_at_entry=green_line,
        red_line_at_entry=red_line,
        cylinders_at_entry=cylinders,
        line_currency=line_currency,
        emotion_tag=emotion_tag,
        note=note,
        # Left NULL when the caller does not say. NULL means "unknown" and
        # readers fall back to created_at; stamping today would turn every
        # late-recorded sale into a trade that happened today, which is how
        # three bookkeeping entries set off the over-trading brake.
        trade_date=trade_date,
    )

    try:
        position.shares_count = outcome.new_shares
        position.avg_cost = outcome.new_avg_cost
        db.add(log)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "Trade rolled back: position={} side={} shares={} price={}",
            position_id, side.value, shares, price,
        )
        raise

    db.refresh(position)
    db.refresh(log)

    logger.info(
        "Trade recorded: {} {} {:g} @ {:g} {} (realized_pl={})",
        position.ticker, side.value, shares, price,
        position.currency or "?",
        "unknown" if outcome.realized_pl is None else f"{outcome.realized_pl:.2f}",
    )
    return position, log, outcome
