"""
The earnings countdown, in the one form both tables show it.

Why a service and not two lines in each route
---------------------------------------------
The holdings table and the watchlist ask the same question about different
objects, and the answer has to read identically in both — the same wording, the
same rounding, the same admission when it is a guess. Written twice it drifts
once, and the first thing to drift would be exactly the part that matters.

The part that matters
---------------------
`earnings_calendar` keeps three qualities of knowing apart: a day the provider
was told, a window it inferred, and our own arithmetic on either past filings
or the company's own publishing history. All of them block a purchase, because
a delayed purchase is cheaper than a surprise. **None of them may be shown as
the others**, so an estimate says "asi za 98 dní" and never "za 98 dní", and
the exact date and its provenance ride along for the tooltip.

The blackout flag is the same fourteen days `GomesGatekeeper` refuses purchases
inside (canon: do not be holding into a print you cannot predict). It is sent
rather than recomputed in the browser so the table and the guard cannot
disagree about what is imminent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Iterable

from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.czech import plural
from app.core.tickers import canonical_ticker
from app.models.earnings import EarningsDate
from app.services.earnings_calendar import describe
from app.trading.gomes_logic import GomesGatekeeper

#: The window the Buy Guard refuses purchases inside.
BLACKOUT_DAYS = GomesGatekeeper.EARNINGS_DANGER_DAYS


@dataclass(frozen=True)
class EarningsBadge:
    """One company's next print, ready to put in a cell."""

    next_date: date
    window_end: date | None
    days: int
    confirmed: bool
    source: str
    #: What goes in the cell. Short, and honest about being an estimate.
    label_cs: str
    #: What goes in the tooltip: the date, the quality, the reason.
    detail_cs: str
    #: Inside the fourteen days the Buy Guard refuses purchases in.
    blackout: bool

    def as_dict(self) -> dict:
        return {
            "next_date": self.next_date,
            "window_end": self.window_end,
            "days": self.days,
            "confirmed": self.confirmed,
            "source": self.source,
            "label_cs": self.label_cs,
            "detail_cs": self.detail_cs,
            "blackout": self.blackout,
        }


def _countdown_cs(days: int, *, confirmed: bool) -> str:
    """
    "za 78 dní", "asi za 98 dní", "zítra", "dnes".

    The word "asi" is the whole difference between a date the company announced
    and one this app worked out from a pattern, and it is one word because the
    cell is one cell — the detail says the rest.
    """
    if days < 0:
        # refresh() keeps stored dates in the future, so this means the row has
        # gone stale between writes. Saying so beats counting backwards.
        return "termín prošel"
    if days == 0:
        return "dnes" if confirmed else "asi dnes"
    if days == 1:
        return "zítra" if confirmed else "asi zítra"

    word = plural(days, "den", "dny", "dní")
    return f"za {days} {word}" if confirmed else f"asi za {days} {word}"


def badge(row: EarningsDate | None, *, today: date | None = None) -> EarningsBadge | None:
    """One row turned into a cell, or None when there is nothing to say."""
    if row is None or row.next_date is None:
        return None
    day = today or datetime.now(timezone.utc).date()
    days = row.days_until(day)
    if days is None:
        return None
    return EarningsBadge(
        next_date=row.next_date,
        window_end=row.window_end,
        days=days,
        confirmed=bool(row.confirmed),
        source=row.source,
        label_cs=_countdown_cs(days, confirmed=bool(row.confirmed)),
        detail_cs=(
            f"{describe(row, today=day)}"
            + (f" — {row.note}" if row.note else "")
        ),
        blackout=0 <= days <= BLACKOUT_DAYS,
    )


def badges(
    db: Session,
    tickers: Iterable[str],
    *,
    today: date | None = None,
) -> dict[str, EarningsBadge]:
    """
    A badge per ticker, keyed by whatever the caller asked with.

    One query for the whole table rather than one per row, and the caller does
    not have to know that the position is held as `KUYA.V` while the calendar
    keeps one row per company under `KUYAF`.
    """
    wanted = [t for t in tickers if t]
    if not wanted:
        return {}

    try:
        rows = {r.ticker: r for r in db.query(EarningsDate).all()}
    except SQLAlchemyError:
        # A countdown is a nicety; the holdings table is the point. The same
        # rule `unvalued_findings` follows — failing to compute what the app
        # says ABOUT the money must never take down the money itself. Logged
        # rather than swallowed, because a calendar that has stopped answering
        # is worth knowing about.
        logger.exception("Kalendář výsledků se nepodařilo přečíst")
        return {}
    day = today or datetime.now(timezone.utc).date()

    out: dict[str, EarningsBadge] = {}
    for raw in wanted:
        row = rows.get(raw.upper()) or rows.get(canonical_ticker(raw) or raw.upper())
        made = badge(row, today=day)
        if made is not None:
            out[raw] = made
    return out
