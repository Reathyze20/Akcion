"""
Building a trend out of readings that used to be thrown away.

Each refresh of `yahoo_finance_cache` overwrote the last one. For the companies
SEC covers that cost nothing — XBRL gives real quarterly series with real period
boundaries. For the four largest positions, which file nowhere EDGAR can see, it
meant the app could never say whether anything was getting better or worse.

Two rules make the series worth reading
---------------------------------------
**A row means something changed.** Deduplication is by value, not by date: the
provider moves these figures on the order of quarters, so a nightly job that
wrote unconditionally would pad the series with ninety identical rows and make
a flat line out of not having looked.

**A year-on-year comparison needs a year.** `year_on_year` will not compare two
readings a fortnight apart and call the difference growth. Until roughly August
2027 this returns None for everything, and that is the honest answer rather
than a number computed across too short a gap.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Final

from loguru import logger
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.fundamental_snapshot import FundamentalSnapshot

#: Fields that decide whether a reading is new. Prices and market cap are
#: deliberately absent: they move every day and would make every run look like
#: a change, which is exactly the padding this guards against.
TRACKED: Final[tuple[str, ...]] = (
    "revenue_ttm",
    "net_income_ttm",
    "operating_margin",
    "profit_margin",
    "total_cash",
    "total_debt",
    "shares_outstanding",
)

#: How far apart two readings must sit before their difference is called a
#: year-on-year change. Wide enough to tolerate a job that missed a week,
#: narrow enough that it is still about one year.
YOY_MIN = timedelta(days=300)
YOY_MAX = timedelta(days=430)


@dataclass(frozen=True)
class Change:
    """One year-on-year move, with the two dates it was measured between."""

    field: str
    older: float
    newer: float
    older_at: datetime
    newer_at: datetime

    @property
    def pct(self) -> float | None:
        if not self.older:
            return None
        return (self.newer - self.older) / abs(self.older) * 100.0


def record_snapshot(
    db: Session, ticker: str, data: dict[str, Any], *, now: datetime | None = None
) -> FundamentalSnapshot | None:
    """
    Keep this reading, unless it says exactly what the last one said.

    Adds to the session without committing; the caller owns the transaction.
    Returns None when nothing changed, which is the common case and not a
    failure.

    Never raises: a snapshot is a bonus on top of a cache refresh that has
    already succeeded, and losing one must not cost the refresh.
    """
    symbol = (ticker or "").strip().upper()
    if not symbol:
        return None

    values = {field: _num(data.get(field)) for field in TRACKED}
    if all(v is None for v in values.values()):
        return None  # a reading with nothing in it is not a reading

    try:
        last = (
            db.query(FundamentalSnapshot)
            .filter(FundamentalSnapshot.ticker == symbol)
            .order_by(desc(FundamentalSnapshot.captured_at))
            .first()
        )
    except Exception:  # noqa: BLE001 — see docstring
        logger.exception("Historii fundamentů pro {} nešlo přečíst", symbol)
        return None

    if last is not None and all(
        _same(getattr(last, field, None), values[field]) for field in TRACKED
    ):
        return None

    row = FundamentalSnapshot(
        ticker=symbol,
        captured_at=now or datetime.now(timezone.utc),
        market_cap=_num(data.get("market_cap")),
        currency=(data.get("currency") or None),
        **values,
    )
    db.add(row)
    logger.debug("Snímek fundamentů {} uložen", symbol)
    return row


def year_on_year(
    db: Session, ticker: str, field: str, *, now: datetime | None = None
) -> Change | None:
    """
    The change in one figure across roughly a year, or None.

    None until two readings sit far enough apart — which for a table that
    started on 2026-08-23 means None for everything until about August 2027.
    Comparing readings a fortnight apart and calling it growth is the mistake
    this exists to refuse.
    """
    if field not in TRACKED:
        raise ValueError(f"{field} se nesleduje v čase")

    moment = now or datetime.now(timezone.utc)
    rows = (
        db.query(FundamentalSnapshot)
        .filter(FundamentalSnapshot.ticker == (ticker or "").strip().upper())
        .order_by(desc(FundamentalSnapshot.captured_at))
        .all()
    )
    if len(rows) < 2:
        return None

    newest = rows[0]
    newer_value = getattr(newest, field, None)
    if newer_value is None:
        return None

    newest_at = _naive(newest.captured_at)
    for older in rows[1:]:
        older_value = getattr(older, field, None)
        if older_value is None:
            continue
        gap = newest_at - _naive(older.captured_at)
        if YOY_MIN <= gap <= YOY_MAX:
            return Change(
                field=field,
                older=float(older_value),
                newer=float(newer_value),
                older_at=older.captured_at,
                newer_at=newest.captured_at,
            )
    return None


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _same(a: Any, b: Any) -> bool:
    """
    Whether two readings of the same figure are the same reading.

    A relative tolerance, because the provider rounds differently between
    calls and a 0.0001 wobble in a margin is not news.
    """
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    a, b = float(a), float(b)
    if a == b:
        return True
    scale = max(abs(a), abs(b))
    return abs(a - b) <= scale * 1e-6


def _naive(value: datetime) -> datetime:
    return value.replace(tzinfo=None) if value.tzinfo is not None else value
