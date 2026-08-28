"""
Read and record the owner's standing instruction for one ticker.

See `app/models/owner_intent.py` for why this is its own table rather than a
field on `stock_lifecycle`. `get()` is what `generate_daily_actions`'
`owner_intent` callback wraps; `record()` is what a human confirms through,
never something the app writes to on its own.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.owner_intent import OwnerIntentModel

EXIT_PENDING = "EXIT_PENDING"
TAX_LOSS_HOLD = "TAX_LOSS_HOLD"


def get(db: Session, ticker: str) -> OwnerIntentModel | None:
    """The standing instruction on record for this ticker, or None."""
    return (
        db.query(OwnerIntentModel)
        .filter(OwnerIntentModel.ticker == ticker.upper())
        .first()
    )


def record(
    db: Session,
    ticker: str,
    intent: str,
    *,
    note: str,
    set_by: str,
    now: datetime | None = None,
) -> OwnerIntentModel:
    """
    Write (or replace) the standing instruction for one ticker.

    Adds to the session without committing — the caller owns the transaction,
    the same discipline `lifecycle_intake.confirm` uses.
    """
    key = ticker.upper()
    row = get(db, key)
    if row is None:
        row = OwnerIntentModel(ticker=key)
        db.add(row)
    row.intent = intent
    row.note = note
    row.set_by = set_by
    row.set_at = now or datetime.now(timezone.utc)
    return row
