"""
Finding out when each company reports, and how well that is known.

The rule this feeds
-------------------
Canon: do not be holding into a print you cannot predict. `GomesGatekeeper`
has enforced a fourteen-day blackout since the app was written and has never
once fired, because nothing ever supplied it a date —
`gomes_analyzer._get_earnings_date` returns None under a TODO and every
`investment_verdicts.days_to_earnings` ever written is NULL.

Three tiers of knowing, and they are not interchangeable
--------------------------------------------------------
1. **A day the provider states outright.** Yahoo returns one date. Treated as
   fact.
2. **A window.** Yahoo returns two dates, meaning it inferred the timing from
   past cadence rather than reading an announcement. Stored as an estimate and
   labelled as one everywhere it is shown.
3. **Our own arithmetic on filing history.** A company that filed its last
   quarter on a given day files the next about ninety days later. Weak, and
   the only thing available for companies the provider does not cover.

All three block a purchase, and that is deliberate: buying two days before a
print is exactly what the canon forbids, and the cost of being wrong about an
estimate is a purchase delayed rather than a loss taken. What differs is what
the app says — a block on a guess must never be presented as a block on a fact.

Reading across listings
-----------------------
Every lookup goes through `variants_of`, because Yahoo answers 404 for `KUYA.V`
and answers properly for `KUYAF`. Four of the five largest positions would
otherwise have no date for no reason but the spelling.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Iterable

from loguru import logger
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.tickers import canonical_ticker, variants_of
from app.models.earnings import SOURCE_SEC_CADENCE, SOURCE_YAHOO, EarningsDate
from app.models.sec import SecFiling

#: A quarter, as the reporting calendar actually spaces them.
QUARTER_DAYS = 91

#: How long a stored date stays good. Dates move, but not daily, and this is a
#: network call per company.
REFRESH_AFTER = timedelta(days=3)

#: Beyond this, a cadence estimate has drifted too far from the filing it was
#: derived from to mean anything.
MAX_ESTIMATE_AGE_DAYS = 200


@dataclass(frozen=True)
class Guess:
    """One answer about when a company reports next."""

    next_date: date
    confirmed: bool
    source: str
    window_end: date | None = None
    note: str | None = None


def fetch_from_provider(ticker: str) -> Guess | None:
    """
    Ask the quote provider, across every listing this company is known by.

    Yahoo returns `Earnings Date` as a list: one entry is a day it has been
    told, two are a window it worked out. Never raises — a provider that cannot
    answer leaves the company without a date, which is a state the caller
    already handles.
    """
    import yfinance as yf

    for symbol in variants_of(ticker) or (ticker.upper(),):
        try:
            calendar = yf.Ticker(symbol).calendar
        except Exception as exc:  # noqa: BLE001 — see docstring
            logger.debug("Kalendář výsledků pro {} selhal: {}", symbol, exc)
            continue

        if not isinstance(calendar, dict):
            continue
        dates = calendar.get("Earnings Date") or []
        if not isinstance(dates, (list, tuple)) or not dates:
            continue

        parsed = [d for d in dates if isinstance(d, date)]
        if not parsed:
            continue

        parsed.sort()
        # One date is an announcement; two are a window the provider inferred
        # from past cadence, and the difference is the whole point of storing
        # `confirmed`.
        single = len(parsed) == 1
        return Guess(
            next_date=parsed[0],
            window_end=None if single else parsed[-1],
            confirmed=single,
            source=SOURCE_YAHOO,
            note=None if single else "Poskytovatel udává rozmezí, ne oznámené datum",
        )
    return None


def estimate_from_filings(db: Session, ticker: str, *, today: date) -> Guess | None:
    """
    A quarter after the last quarter, for companies the provider does not cover.

    The weakest of the three tiers and never presented as anything else. Only
    the period a filing REPORTS ON is usable here — the day it was filed varies
    by weeks with no pattern, while period ends march in quarters.
    """
    symbols = variants_of(ticker) or (ticker.upper(),)
    filing = (
        db.query(SecFiling)
        .filter(SecFiling.ticker.in_(symbols))
        .filter(SecFiling.period_date.isnot(None))
        .order_by(desc(SecFiling.period_date))
        .first()
    )
    if filing is None:
        return None

    # Walk forward a quarter at a time until the estimate is in the future, so
    # a company we last read a year ago does not produce a date in the past.
    guess = filing.period_date + timedelta(days=QUARTER_DAYS)
    while guess < today:
        guess = guess + timedelta(days=QUARTER_DAYS)

    if (guess - filing.period_date).days > MAX_ESTIMATE_AGE_DAYS:
        # Too many quarters extrapolated from one filing to mean anything.
        return None

    return Guess(
        next_date=guess,
        confirmed=False,
        source=SOURCE_SEC_CADENCE,
        note=(
            f"Odhad z kadence podání — poslední vykázané období končilo "
            f"{filing.period_date:%d.%m.%Y}, další čtvrtletí vychází zhruba sem"
        ),
    )


def refresh(
    db: Session,
    tickers: Iterable[str],
    *,
    now: datetime | None = None,
    force: bool = False,
) -> list[EarningsDate]:
    """
    Bring the stored dates up to date. Adds to the session; caller commits.

    Skips anything read in the last few days unless forced: this is a network
    call per company and the dates do not move daily.
    """
    moment = now or datetime.now(timezone.utc)
    today = moment.date()
    touched: list[EarningsDate] = []

    for raw in tickers:
        symbol = canonical_ticker(raw) or raw.upper()
        row = db.query(EarningsDate).filter(EarningsDate.ticker == symbol).first()

        if row is not None and not force and row.fetched_at is not None:
            fetched = row.fetched_at
            if fetched.tzinfo is None:
                fetched = fetched.replace(tzinfo=timezone.utc)
            if moment - fetched < REFRESH_AFTER:
                continue

        guess = fetch_from_provider(symbol) or estimate_from_filings(
            db, symbol, today=today
        )

        if row is None:
            row = EarningsDate(ticker=symbol)
            db.add(row)

        if guess is None:
            # No date from anywhere. Recorded as such rather than left stale:
            # a date from three months ago is worse than none.
            row.next_date = None
            row.window_end = None
            row.confirmed = False
            row.source = SOURCE_YAHOO
            row.note = "Datum výsledků nezná ani poskytovatel, ani kadence podání"
        else:
            row.next_date = guess.next_date
            row.window_end = guess.window_end
            row.confirmed = guess.confirmed
            row.source = guess.source
            row.note = guess.note

        row.fetched_at = moment
        touched.append(row)

    return touched


def upcoming(db: Session, *, today: date | None = None) -> dict[str, EarningsDate]:
    """Stored dates keyed canonically, for the engine to read in one go."""
    rows = db.query(EarningsDate).all()
    return {r.ticker: r for r in rows}


def describe(row: EarningsDate | None, *, today: date | None = None) -> str:
    """One Czech sentence about when a company reports, for a warning line."""
    if row is None or row.next_date is None:
        return "datum výsledků neznám"

    days = row.days_until(today)
    when = f"{row.next_date:%d.%m.%Y}"
    if row.window_end is not None:
        when += f"–{row.window_end:%d.%m.%Y}"

    kind = "oznámeno" if row.confirmed else "odhad"
    return f"výsledky {when} ({kind}, za {days} dní)"
