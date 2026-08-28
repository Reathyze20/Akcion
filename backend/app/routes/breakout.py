"""
Breakout Investors API — the second source's conviction count and target price.

One read endpoint and one refresh button. What comes back is deliberately flat
and factual: their numbers, our numbers, and where the two disagree. The
comparison is left to the reader — nothing in this response changes a position
cap or a verdict (see the module docstring of `app/services/breakout_sync.py`
for why that is a decision rather than an oversight).

The response always says when the source was last reached and whether it
failed. A watchlist that has not been read for a week and a watchlist that has
not changed for a week look identical on screen unless the endpoint says so.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import bindparam, desc, text
from sqlalchemy.orm import Session

from app.core.sources import InvestmentSource
from app.core.tickers import canonical_ticker, variants_of
from app.database.connection import get_db
from app.models.breakout import BreakoutWatchChange, BreakoutWatchEntry
from app.models.stock import Stock
from app.services import breakout_scorecard
from app.services.breakout_sync import (
    RELATION_OWNED,
    RELATION_THEIRS,
    RELATION_WATCHED,
    get_state,
    our_symbols,
    sync_watchlist,
)

router = APIRouter(prefix="/api/breakout", tags=["breakout"])


#: A successful read older than this is called out on screen. Twice the poll
#: interval, so one missed daily run is not yet an alarm.
STALE_AFTER = timedelta(hours=48)

#: Default window for "what moved". Their list changes on the order of weeks.
DEFAULT_CHANGE_DAYS = 14

#: Where the ordering puts each relation. Ours first — the whole point of the
#: view is the overlap, not their twenty-eight names.
_RELATION_RANK = {RELATION_OWNED: 0, RELATION_WATCHED: 1, RELATION_THEIRS: 2}


class EntryOut(BaseModel):
    symbol: str
    company_name: str | None = None
    relation: str = Field(description="OWNED | WATCHED | THEIRS")

    endorsements: int = Field(description="How many of their members back it")
    upside_pct: float | None = Field(
        default=None, description="Their expected gain in percent. None = not published."
    )
    price_at_read: float | None = None
    implied_target: float | None = Field(
        default=None,
        description=(
            "Their target price, reconstructed from the quote and the upside. "
            "None whenever either input was missing — never a zero, never stale."
        ),
    )

    gomes_green_line: float | None = None
    gomes_red_line: float | None = None
    vs_gomes: str | None = Field(
        default=None,
        description=(
            "ABOVE_RED | IN_BAND | BELOW_GREEN — where their target falls in "
            "the Gomes valuation band. None when either side is missing a number."
        ),
    )

    added_at: datetime | None = Field(
        default=None, description="When THEY added the name"
    )
    first_seen_at: datetime | None = Field(
        default=None, description="When WE first saw it"
    )


class ChangeOut(BaseModel):
    symbol: str
    relation: str
    kind: str
    detail_cs: str
    detected_at: datetime


class ScoredNameOut(BaseModel):
    symbol: str
    days_watched: int
    price_then: float
    target_then: float
    price_now: float | None = None
    upside_then_pct: float
    move_pct: float | None = None
    #: Kolik z cesty k cíli uběhlo. `None`, když cíl neleží nad cenou.
    progress_pct: float | None = None
    reached: bool | None = None


class ScorecardOut(BaseModel):
    """
    Jak si vedou jejich cíle — nebo věta, proč se to ještě neříká.

    `too_early` je celý smysl téhle struktury. Úspěšnost spočítaná po týdnu
    měří šum a četla by se jako výsledek, takže se pod horizontem nevydá
    vůbec — ne jako nula, ne jako „zatím 40 %".
    """

    median_days: int | None = None
    too_early: bool
    measurable: int
    reached_total: int | None = None
    min_horizon_days: int
    verdict_cs: str
    names: list[ScoredNameOut] = Field(default_factory=list)


class WatchlistOut(BaseModel):
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error: str | None = None
    stale: bool = Field(
        description="No successful read for over 48 h. The numbers below are old."
    )
    never_read: bool = Field(
        description="The source has never been read. Empty is not 'no names'."
    )

    entries_total: int
    ours_total: int = Field(description="How many of their names we own or watch")
    entries: list[EntryOut]
    changes: list[ChangeOut]
    scorecard: ScorecardOut


def _gomes_lines(db: Session, symbols: set[str]) -> dict[str, tuple[float | None, float | None]]:
    """
    Latest Gomes green/red line per ticker, for the symbols asked about.

    One row per ticker via DISTINCT ON, same shape as
    `StockRepository.get_current_by_source` — the Breakout row for the same
    ticker (if a chat take was ever pasted in) must not shadow the Gomes lines.

    Queried across every listing of each company (`variants_of`). The Breakout
    list names the OTC symbol; the Gomes lines may well have been pasted in
    under the Canadian one, and without the expansion the comparison column
    would just be empty for exactly the four names it matters most for.
    """
    if not symbols:
        return {}

    wanted = {v for symbol in symbols for v in variants_of(symbol)} | symbols

    rows = (
        db.query(Stock.ticker, Stock.green_line, Stock.red_line)
        .filter(Stock.ticker.in_(wanted))
        .filter(Stock.source_key == InvestmentSource.GOMES.value)
        .order_by(Stock.ticker, desc(Stock.created_at))
        .distinct(Stock.ticker)
        .all()
    )

    lines: dict[str, tuple[float | None, float | None]] = {}
    for row in rows:
        if not row.ticker:
            continue
        # A row with no lines at all must not shadow a sibling listing that
        # has them — an empty answer here is what the "čáry nezadané" label
        # means, and it should only appear when no listing carries them.
        if row.green_line is None and row.red_line is None:
            continue
        lines.setdefault(
            canonical_ticker(row.ticker), (row.green_line, row.red_line)
        )

    return {
        symbol: lines[canonical_ticker(symbol)]
        for symbol in symbols
        if canonical_ticker(symbol) in lines
    }


def _f(value) -> float | None:
    return None if value is None else float(value)


def _current_prices(db: Session, symbols: set[str]) -> dict[str, float]:
    """
    Dnešní kurzy z cache. Nesahá na síť — vysvědčení je čtení, ne sběr.

    Chybějící kurz se nedoplňuje: jméno bez ceny se do jmenovatele nezapočítá,
    protože nevědět, kde akcie stojí, není nesplněný cíl.
    """
    if not symbols:
        return {}
    rows = db.execute(
        text(
            "SELECT ticker, current_price FROM yahoo_finance_cache "
            "WHERE ticker IN :symbols AND current_price IS NOT NULL"
        ).bindparams(bindparam("symbols", expanding=True)),
        {"symbols": sorted(symbols)},
    ).mappings().all()
    return {r["ticker"]: float(r["current_price"]) for r in rows}


def _vs_gomes(
    target: float | None, green: float | None, red: float | None
) -> str | None:
    """
    Where their target falls in the Gomes band. None when it cannot be said.

    Deliberately not a verdict. ABOVE_RED means they expect a price Gomes
    treats as overvalued — the AEHR case — and that is a fact about two
    numbers, not a recommendation about either.
    """
    if target is None:
        return None
    if red is not None and target > red:
        return "ABOVE_RED"
    if green is not None and target < green:
        return "BELOW_GREEN"
    if green is None and red is None:
        return None
    return "IN_BAND"


def _build(db: Session, *, change_days: int) -> WatchlistOut:
    state = get_state(db)
    relations = our_symbols(db)

    rows = db.query(BreakoutWatchEntry).all()
    lines = _gomes_lines(db, {r.symbol for r in rows})
    prices = _current_prices(db, {r.symbol for r in rows})

    entries: list[EntryOut] = []
    for row in rows:
        relation = relations.get(row.symbol, RELATION_THEIRS)
        green, red = lines.get(row.symbol, (None, None))
        target = None if row.implied_target is None else float(row.implied_target)
        upside = None if row.upside_ratio is None else float(row.upside_ratio) * 100.0

        entries.append(
            EntryOut(
                symbol=row.symbol,
                company_name=row.company_name,
                relation=relation,
                endorsements=int(row.endorsements or 0),
                upside_pct=upside,
                price_at_read=(
                    None if row.price_at_read is None else float(row.price_at_read)
                ),
                implied_target=target,
                gomes_green_line=green,
                gomes_red_line=red,
                vs_gomes=_vs_gomes(target, green, red),
                added_at=row.added_at,
                first_seen_at=row.first_seen_at,
            )
        )

    entries.sort(
        key=lambda e: (
            _RELATION_RANK.get(e.relation, 9),
            -e.endorsements,
            -(e.upside_pct if e.upside_pct is not None else -1e9),
            e.symbol,
        )
    )

    # Vysvědčení jejich cílů. Vydá se vždy, ale dokud je na soud brzy, nese to
    # místo úspěšnosti větu proč — a to je taky odpověď.
    scorecard = breakout_scorecard.build(
        [
            breakout_scorecard.Reading(
                symbol=row.symbol,
                first_seen_at=row.first_seen_at,
                price_at_first_seen=_f(row.price_at_first_seen),
                target_at_first_seen=_f(row.target_at_first_seen),
                price_now=prices.get(row.symbol),
            )
            for row in rows
        ]
    )

    since = datetime.now(timezone.utc) - timedelta(days=change_days)
    change_rows = (
        db.query(BreakoutWatchChange)
        .filter(BreakoutWatchChange.detected_at >= since)
        .order_by(desc(BreakoutWatchChange.detected_at), BreakoutWatchChange.symbol)
        .limit(200)
        .all()
    )
    changes = [
        ChangeOut(
            symbol=c.symbol,
            relation=relations.get(c.symbol, RELATION_THEIRS),
            kind=c.kind,
            detail_cs=c.detail_cs,
            detected_at=c.detected_at,
        )
        for c in change_rows
    ]

    last_success = state.last_success_at
    stale = last_success is None or (
        datetime.now(timezone.utc) - _aware(last_success)
    ) > STALE_AFTER

    return WatchlistOut(
        last_attempt_at=state.last_attempt_at,
        last_success_at=last_success,
        last_error=state.last_error,
        stale=stale,
        never_read=last_success is None,
        entries_total=len(entries),
        ours_total=sum(1 for e in entries if e.relation != RELATION_THEIRS),
        entries=entries,
        changes=changes,
        scorecard=ScorecardOut(**scorecard.to_dict()),
    )


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


@router.get(
    "/watchlist",
    response_model=WatchlistOut,
    summary="Watchlist Breakout Investors — konvikce a cílová cena",
)
def get_watchlist(
    days: int = Query(
        DEFAULT_CHANGE_DAYS, ge=1, le=180, description="Okno pro seznam změn"
    ),
    db: Session = Depends(get_db),
) -> WatchlistOut:
    """Everything stored, ours first. Reads only — never touches the network."""
    return _build(db, change_days=days)


@router.post(
    "/refresh",
    response_model=WatchlistOut,
    summary="Načíst watchlist teď",
)
def refresh(
    days: int = Query(DEFAULT_CHANGE_DAYS, ge=1, le=180),
    db: Session = Depends(get_db),
) -> WatchlistOut:
    """
    Read the source now, bypassing the daily interval.

    `force=True` is safe here because a button press is a person, not a loop.
    The scheduled job does not force, so an outage cannot turn into a retry
    storm against someone else's server.
    """
    sync_watchlist(db, force=True)
    db.commit()
    return _build(db, change_days=days)
