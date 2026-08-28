"""
Writing down the buys the guard refused.

`app/services/daily_actions.py` emits a `Refusal` for every purchase the Gomes
Buy Guard turns down. This module is what puts it in the database, and it is
deliberately the only place that knows how.

Why the split: the action engine is a pure function — inject a clock, inject
FX, get the same answer every time — and that property is what makes its rules
testable against the canon's own fixtures. Handing it a Session would end that.
So it reports refusals and this module records them.

The measurement this makes possible
-----------------------------------
In a year, `refused_buys` joined against prices answers a question the app
cannot ask today: of the purchases the discipline blocked, how many would have
made money? A gate that blocks winners is mis-set, and until the refusals are
on disk there is no way to notice. Note that the answer takes a year — the
score journal opened 2026-08-23 and nothing before it can be reconstructed, so
the only way to have this data in 2027 is to start writing it now.

One row per ticker per day per gate
-----------------------------------
The daily engine re-reads the same watchlist every run. An unchanged refusal
repeated 365 times is noise that buries the signal, so a repeat within the same
day is silently skipped. A refusal whose *gate* changes is different news — the
market alert lifted and the answer became "not cheap enough" — and gets its own
row.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from loguru import logger
from sqlalchemy.orm import Session

from app.models.refused_buy import RefusedBuy
from app.services.daily_actions import Refusal


def record_refusal(
    db: Session,
    refusal: Refusal,
    *,
    on_day: date | None = None,
) -> RefusedBuy | None:
    """
    Add one refusal to the session, unless the same one is already on record today.

    Adds to the session without committing: the caller's transaction owns that,
    so a day's refusals land together with whatever else that request wrote.

    Args:
        on_day: the day to file it under. Injectable so the de-duplication rule
            can be tested without waiting for midnight.

    Returns:
        The pending row, or None when this ticker already has this gate
        recorded for this day.
    """
    ticker = (refusal.ticker or "").strip().upper()
    if not ticker:
        logger.warning("Odmítnutý nákup bez tickeru se nezapisuje ({})", refusal.failed_gate)
        return None

    day = on_day or datetime.now(timezone.utc).date()

    already = (
        db.query(RefusedBuy)
        .filter(RefusedBuy.ticker == ticker)
        .filter(RefusedBuy.refused_on == day)
        .filter(RefusedBuy.failed_gate == refusal.failed_gate)
        .first()
    )
    if already is not None:
        return None

    # A pending row from earlier in this same flush counts too — the engine can
    # produce the same refusal twice in one run when a company is held under
    # two listings, and the unique constraint would fail at flush time.
    for pending in db.new:
        if (
            isinstance(pending, RefusedBuy)
            and pending.ticker == ticker
            and pending.refused_on == day
            and pending.failed_gate == refusal.failed_gate
        ):
            return None

    row = RefusedBuy(
        ticker=ticker,
        refused_on=day,
        failed_gate=refusal.failed_gate,
        reason=refusal.reason,
        source_key=refusal.source_key,
        price=_num(refusal.price),
        green_line=_num(refusal.green_line),
        red_line=_num(refusal.red_line),
        line_currency=refusal.line_currency,
        rr_score=_num(refusal.rr_score),
        deserved_score=_num(refusal.deserved_score),
        cylinders=refusal.cylinders,
        lifecycle_phase=refusal.lifecycle_phase,
        market_alert=refusal.market_alert,
    )
    db.add(row)
    return row


def collector(db: Session, *, on_day: date | None = None):
    """
    A sink to hand `generate_daily_actions(refusal_sink=...)`.

    Swallows its own failures on purpose. A refusal that cannot be recorded is
    a lost measurement; a refusal that takes down the daily action list is a
    lost morning. The first is recoverable, the second is the thing this app
    exists to prevent.
    """

    def sink(refusal: Refusal) -> None:
        try:
            record_refusal(db, refusal, on_day=on_day)
        except Exception:  # noqa: BLE001 — see docstring
            logger.exception("Odmítnutý nákup {} se nepodařilo zapsat", refusal.ticker)

    return sink


def record_many(
    db: Session, refusals: Iterable[Refusal], *, on_day: date | None = None
) -> list[RefusedBuy]:
    """Record a batch, skipping duplicates. Returns the rows actually added."""
    added: list[RefusedBuy] = []
    for refusal in refusals:
        row = record_refusal(db, refusal, on_day=on_day)
        if row is not None:
            added.append(row)
    return added


def _num(value: Any) -> Decimal | None:
    """
    A number as Decimal, or None — never zero standing in for "unknown".

    Zero is a real R/R score (it means the price is at or above the Red Line),
    so a genuine 0 is kept and only unparseable input becomes None.
    """
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        logger.warning("Hodnota {!r} v odmítnutém nákupu není číslo — ukládám NULL", value)
        return None
