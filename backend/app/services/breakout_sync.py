"""
Persisting the Breakout Investors watchlist — the read, the diff, the record.

`breakout_watchlist.py` knows how to talk to the source and how to compare two
reads. This module is what turns that into rows: it decides whether a poll is
due, writes the snapshot, records what moved, and marks whether the source was
reachable.

What this module deliberately does NOT do
-----------------------------------------
It writes nothing into `stocks`, and nothing here reaches
`evaluate_dual_source_buy`. That is a decision, not an omission (2026-08-23).

The dual-source policy in `app/trading/gomes_logic.py` reads a Breakout
Investors *stance* — a take someone actually formed on a company — and turns
AGREE into a 15 % position cap where a lone Gomes call gets 7 %. A scraped
watchlist is not a stance. If every name on their list were written in as
BULLISH, the app would silently double the allowed size of twenty-eight
positions on the strength of a scrape nobody read. Their conviction count and
their target are shown next to ours and compared by eye; the caps stay where
the Gomes side puts them.

The only automatic judgement made here is a factual one: whether their target
sits below the Gomes red line, which is a disagreement worth naming and never a
reason to size anything differently.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

import requests
from loguru import logger
from sqlalchemy.orm import Session

from app.models.breakout import (
    BreakoutPollState,
    BreakoutWatchChange,
    BreakoutWatchEntry,
)
from app.services.breakout_watchlist import (
    WatchlistChange,
    WatchlistEntry,
    WatchlistUnavailable,
    diff_watchlist,
    fetch_quotes,
    fetch_watchlist,
    implied_target,
    should_poll,
)

#: Outcomes of one sync attempt. Kept distinct so a caller can tell "nothing
#: changed" from "we did not look" from "we looked and could not see".
STATUS_SYNCED = "SYNCED"
STATUS_TOO_SOON = "TOO_SOON"
STATUS_UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class SyncResult:
    status: str
    entries_read: int
    changes: list[WatchlistChange]
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == STATUS_SYNCED


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)


def get_state(db: Session) -> BreakoutPollState:
    """The single poll-state row, created on first use."""
    state = db.query(BreakoutPollState).order_by(BreakoutPollState.id).first()
    if state is None:
        state = BreakoutPollState()
        db.add(state)
        db.flush()
    return state


def _stored_entries(db: Session) -> list[BreakoutWatchEntry]:
    return db.query(BreakoutWatchEntry).order_by(BreakoutWatchEntry.symbol).all()


def _as_watchlist_entry(row: BreakoutWatchEntry) -> WatchlistEntry:
    """A stored row in the shape `diff_watchlist` compares."""
    return WatchlistEntry(
        symbol=row.symbol,
        company_name=row.company_name,
        endorsements=int(row.endorsements or 0),
        upside_ratio=(None if row.upside_ratio is None else float(row.upside_ratio)),
        added_at=row.added_at,
    )


def _dec(value: float | None, places: str) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).quantize(Decimal(places))


def sync_watchlist(
    db: Session,
    *,
    force: bool = False,
    session: requests.Session | None = None,
    now: datetime | None = None,
) -> SyncResult:
    """
    Read the source once, if it is due, and record what came back.

    Args:
        force: read even if the interval has not elapsed. For the manual
            button and for a first run — never for a loop.

    The watchlist and the quotes are treated as ONE read. A partial result is
    not persisted: pairing today's upside with a price that failed to load
    would produce a target computed from two different moments, and a wrong
    target is worse than no target.
    """
    moment = _now(now)
    state = get_state(db)

    if not force and not should_poll(state.last_attempt_at, now=moment):
        return SyncResult(status=STATUS_TOO_SOON, entries_read=0, changes=[])

    state.last_attempt_at = moment

    http = session or requests.Session()
    try:
        current = fetch_watchlist(session=http)
        quotes = fetch_quotes([e.symbol for e in current], session=http)
    except WatchlistUnavailable as exc:
        message = str(exc)[:300]
        state.last_error = message
        logger.warning("Breakout watchlist unavailable: {}", message)
        return SyncResult(
            status=STATUS_UNAVAILABLE, entries_read=0, changes=[], error=message
        )

    stored = _stored_entries(db)
    previous = [_as_watchlist_entry(r) for r in stored]

    # The first successful read is a baseline, not news. Diffing it against an
    # empty table would call all twenty-eight names ADDED and mail the lot,
    # which is the one message guaranteed to teach the owner to ignore the
    # next one. `first_seen_at` records that we started looking today; nothing
    # moved. Conditioned on last_success_at rather than on `previous` being
    # empty, so a list that genuinely empties still reports every REMOVED.
    first_read = state.last_success_at is None
    changes = [] if first_read else diff_watchlist(previous, current)

    by_symbol = {r.symbol: r for r in stored}
    seen: set[str] = set()

    for entry in current:
        seen.add(entry.symbol)
        price = quotes.get(entry.symbol)
        target = implied_target(price, entry.upside_ratio)

        row = by_symbol.get(entry.symbol)
        if row is None:
            row = BreakoutWatchEntry(symbol=entry.symbol, first_seen_at=moment)
            db.add(row)

        # The starting line, written once. Everything else on this row is the
        # latest poll and gets overwritten; these two must not, or their one
        # falsifiable prediction stops being measurable the moment we poll
        # again. `is None` rather than `not row.price_at_first_seen`, so a name
        # first seen at a price we could not read stays honestly empty instead
        # of silently adopting today's.
        if row.price_at_first_seen is None and price is not None:
            row.price_at_first_seen = _dec(price, "0.0001")
            row.target_at_first_seen = _dec(target, "0.0001")

        row.company_name = entry.company_name
        row.endorsements = entry.endorsements
        row.upside_ratio = _dec(entry.upside_ratio, "0.000001")
        row.price_at_read = _dec(price, "0.0001")
        row.implied_target = _dec(target, "0.0001")
        row.added_at = entry.added_at
        row.last_seen_at = moment

    # Off the list is off the list. The REMOVED change row is the record that
    # it was ever there; keeping the snapshot row would show a stale target as
    # if the group still stood behind it.
    for symbol, row in by_symbol.items():
        if symbol not in seen:
            db.delete(row)

    for change in changes:
        db.add(
            BreakoutWatchChange(
                symbol=change.symbol,
                kind=change.kind,
                before_value=_dec(
                    None if change.before is None else float(change.before), "0.000001"
                ),
                after_value=_dec(
                    None if change.after is None else float(change.after), "0.000001"
                ),
                detail_cs=change.detail,
                detected_at=moment,
            )
        )

    state.last_success_at = moment
    state.last_error = None
    state.entries_last_read = len(current)

    logger.info(
        "Breakout watchlist synced: {} names, {} changes", len(current), len(changes)
    )
    return SyncResult(status=STATUS_SYNCED, entries_read=len(current), changes=changes)


# ==============================================================================
# Which of their names are ours
# ==============================================================================

RELATION_OWNED = "OWNED"
RELATION_WATCHED = "WATCHED"
RELATION_THEIRS = "THEIRS"


def our_symbols(db: Session) -> dict[str, str]:
    """
    Map ticker -> OWNED / WATCHED for everything this portfolio tracks.

    Keyed on `canonical_ticker`, not the raw symbol. Four of these positions
    are held on a Canadian exchange while the Breakout list names the American
    OTC listing of the same company, so exact matching reported `KUYAF` as
    merely watched while the owner held `KUYA.V`. Both the raw symbol and its
    canonical form are written into the map, so a caller can look up either.

    Owned wins over watched: a position is usually on the watchlist too, and
    the stronger relation is the one worth showing.

    Trading 212 suffixes its own symbols ("ECOR_US_EQ"); `T212Position
    .plain_ticker` already strips that before anything reaches `positions`.
    """
    from app.core.tickers import canonical_ticker
    from app.models.portfolio import Position
    from app.models.stock import Stock

    relations: dict[str, str] = {}

    def mark(ticker: str | None, relation: str) -> None:
        if not ticker:
            return
        raw = ticker.strip().upper()
        for key in {raw, canonical_ticker(raw)}:
            # OWNED must not be downgraded by a later WATCHED row for the same
            # company — the two tables are read in sequence, not merged.
            if relations.get(key) != RELATION_OWNED:
                relations[key] = relation

    for (ticker,) in db.query(Stock.ticker).distinct():
        mark(ticker, RELATION_WATCHED)

    for (ticker,) in db.query(Position.ticker).distinct():
        mark(ticker, RELATION_OWNED)

    return relations
