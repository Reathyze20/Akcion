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
from app.models.earnings import (
    SOURCE_RELEASE_CADENCE,
    SOURCE_SEC_CADENCE,
    SOURCE_YAHOO,
    EarningsDate,
)
from app.services import release_fundamentals
from app.models.sec import SecFiling

#: A quarter, as the reporting calendar actually spaces them.
QUARTER_DAYS = 91

#: How long a stored date stays good. Dates move, but not daily, and this is a
#: network call per company.
REFRESH_AFTER = timedelta(days=3)

#: Beyond this, a cadence estimate has drifted too far from the filing it was
#: derived from to mean anything.
MAX_ESTIMATE_AGE_DAYS = 200

#: A company does not report again a fortnight after it last reported. Without
#: this the pattern below would answer with the anniversary of a report that
#: has already been published — Kuya put out Q2 on 17 August 2026 and last
#: year's Q2 landed on 2 September, so the naive answer is two weeks away and
#: wrong.
MIN_GAP_AFTER_LAST_PUBLICATION_DAYS = 60

#: Fewer publications than this is not a pattern, it is a coincidence.
MIN_PUBLICATIONS_FOR_PATTERN = 3


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


def estimate_from_release_history(ticker: str, *, today: date) -> Guess | None:
    """
    When the company itself has published results before, and when that is due
    to come round again.

    For the holdings no provider covers and EDGAR cannot see, this is the only
    tier left — and it is better than it sounds, because a small issuer's
    reporting calendar is remarkably stable. Gatekeeper has posted its quarters
    in January, April, July and December every year since 2019.

    Deliberately not a median gap between publications. Gatekeeper's fourth
    quarter takes five months and its other three take three, so an average
    would put the annual report in October and the blackout in the wrong place
    entirely. The pattern that actually holds is the month of the year.

    Precision is never invented. Gatekeeper's IR page dates its statements to
    the month, so the answer is a whole month wide; Kuya's press releases carry
    the day, so the window is a fortnight.
    """
    release = release_fundamentals.for_ticker(ticker)
    if release is None or len(release.publications) < MIN_PUBLICATIONS_FOR_PATTERN:
        return None

    latest = max(release.publications, key=lambda p: (p.year, p.month, p.day or 1))
    earliest_sensible = max(
        today,
        date(latest.year, latest.month, latest.day or 1)
        + timedelta(days=MIN_GAP_AFTER_LAST_PUBLICATION_DAYS),
    )

    # Every publication's anniversary, in this year and the next, kept only if
    # it lands after the company could plausibly report again.
    candidates: list[tuple[date, "release_fundamentals.Publication"]] = []
    for pub in release.publications:
        for year in (earliest_sensible.year, earliest_sensible.year + 1):
            try:
                when = date(year, pub.month, pub.day or 1)
            except ValueError:  # 29 February in a non-leap year
                continue
            if when > earliest_sensible:
                candidates.append((when, pub))
    if not candidates:
        return None

    when, pub = min(candidates, key=lambda c: c[0])

    if pub.exact:
        window_end = when + timedelta(days=14)
        precision = f"loni {when.day}. {when.month}."
    else:
        # Only the month is known, so the whole month is the answer.
        next_month = date(when.year + when.month // 12, when.month % 12 + 1, 1)
        window_end = next_month - timedelta(days=1)
        precision = f"v měsíci {when.month}/{when.year}."

    years = sorted({p.year for p in release.publications})
    count = len(release.publications)
    # Czech counts a small number differently from a large one, and this string
    # is read by the owner rather than parsed.
    word = "zprávy" if count < 5 else "zpráv"
    return Guess(
        next_date=when,
        window_end=window_end,
        confirmed=False,
        source=SOURCE_RELEASE_CADENCE,
        note=(
            f"Odhad z vlastní historie zveřejňování firmy ({count} {word}, "
            f"{years[0]}–{years[-1]}) — výsledky vycházely {precision} "
            f"Není to oznámené datum."
        ),
    )


def _first_future(today: date, *tiers) -> "Guess | None":
    """
    The best tier that answers with a date that has not already happened.

    This module's own rule, applied to every tier instead of only to the
    cadence estimate: "a date from three months ago is worse than none, because
    it looks like an answer." The provider breaks it — for four watchlist names
    it kept returning last quarter's print, weeks after the fact — and a stale
    date is worse here than elsewhere, because it silently hides the real one
    behind something that reads like knowledge.

    A window still open counts as future: the company has not reported yet.
    """
    for tier in tiers:
        guess = tier()
        if guess is None:
            continue
        latest = guess.window_end or guess.next_date
        if latest >= today:
            return guess
    return None


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

        guess = _first_future(
            today,
            lambda: fetch_from_provider(symbol),
            lambda: estimate_from_filings(db, symbol, today=today),
            lambda: estimate_from_release_history(symbol, today=today),
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
            row.note = (
                "Datum výsledků nezná poskytovatel, kadence podání ani vlastní "
                "historie zveřejňování firmy"
            )
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
