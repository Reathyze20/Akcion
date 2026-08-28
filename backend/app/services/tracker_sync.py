"""
Tracker → database. The wire that turns the decision engine on.

Everything downstream of the Green and Red Lines already exists and is tested:
the logarithmic R/R score, the deserved score against cylinders, the 3-point
triggers, the hard Buy Guard, the Daily Action engine's "Co mám dnes udělat?".
All of it reads `stocks.green_line` / `stocks.red_line`, and until now those
were either empty or — worse, until this branch — back-calculated from the
current price. A tested engine computing over invented inputs produces
confident, wrong answers.

This module fills those two columns from riskrewardcharts.com, where the
analyst actually publishes them.

What it will not touch
----------------------
* `cylinders` — operational health, 0-10. It is not on the tracker; it comes
  from what Gomes says in a video or in the group. Since the Buy Guard needs
  known cylinders, a synced band alone still cannot produce a BUY. That is the
  correct outcome, not a gap to paper over.
* `avg_cost` on positions — the owner's own purchase price, never derivable
  from a tracker.
* Anything belonging to another source. Rows are keyed by (ticker, GOMES) so
  a Breakout Investors row for the same ticker stays independent, which is
  what makes cross-source agreement meaningful.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlalchemy.orm import Session

import requests

from app.core.sources import InvestmentSource
from app.models.stock import Stock
from app.models.tracker import TrackerLineChange, TrackerPollState
from app.services.gomes_tracker import (
    OFFICIAL,
    TrackerChange,
    TrackerPick,
    TrackerUnavailable,
    diff_tracker,
    fetch_tracker,
    should_poll,
)

#: Outcomes of one sync attempt. Kept distinct so a caller can tell "nothing
#: changed" from "we did not look" from "we looked and could not see" — three
#: states that a single boolean would flatten into one misleading answer.
STATUS_SYNCED = "SYNCED"
STATUS_TOO_SOON = "TOO_SOON"
STATUS_UNAVAILABLE = "UNAVAILABLE"


@dataclass
class SyncReport:
    """What one sync did — surfaced to the owner, not just logged."""

    picks_read: int = 0
    created: list[str] = field(default_factory=list)
    band_updated: list[str] = field(default_factory=list)
    price_updated: list[str] = field(default_factory=list)
    changes: list[TrackerChange] = field(default_factory=list)
    synced_at: datetime | None = None
    status: str = STATUS_SYNCED
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == STATUS_SYNCED

    @property
    def touched_anything(self) -> bool:
        return bool(self.created or self.band_updated or self.changes)

    def summary_cs(self) -> str:
        if self.status == STATUS_TOO_SOON:
            return "Tracker byl čten před méně než 12 hodinami — nečte se znovu."
        if self.status == STATUS_UNAVAILABLE:
            return f"Tracker nedostupný: {self.error}"
        if not self.touched_anything:
            return f"Tracker beze změn ({self.picks_read} picků)."
        parts: list[str] = []
        if self.created:
            parts.append(f"nové: {', '.join(self.created)}")
        if self.band_updated:
            parts.append(f"přeceněno: {', '.join(self.band_updated)}")
        return f"Tracker: {' · '.join(parts)}"


def snapshot_existing(db: Session) -> list[TrackerPick]:
    """
    Reconstruct the previous tracker state from what is already stored.

    Lets change detection work without a separate history table: the DB is
    the record of what the tracker said last time it was read.
    """
    rows = (
        db.query(Stock)
        .filter(Stock.source_key == InvestmentSource.GOMES.value)
        .filter(Stock.green_line.isnot(None))
        .all()
    )
    return [
        TrackerPick(
            ticker=row.ticker,
            low=row.green_line,
            high=row.red_line,
            pick_type=row.source_type,
            price=row.current_price,
        )
        for row in rows
    ]


def apply_picks(
    db: Session,
    picks: list[TrackerPick],
    *,
    now: datetime | None = None,
    report_changes: bool = True,
) -> SyncReport:
    """
    Write the tracker's bands onto GOMES-sourced stock rows.

    Pure-ish: takes the picks rather than fetching, so a sync can be tested
    against a fixed payload without a network.

    Args:
        report_changes: False on the very first successful read, where every
            pick would otherwise be reported as new. The rows are still
            written — only the news is suppressed.
    """
    moment = now or datetime.now(timezone.utc)
    report = SyncReport(picks_read=len(picks), synced_at=moment)
    previous = snapshot_existing(db)
    report.changes = diff_tracker(previous, picks) if report_changes else []

    for pick in picks:
        if pick.low is None or pick.high is None:
            # A pick without a band carries no decision value and must not
            # overwrite a good one with nulls.
            logger.warning("Tracker pick {} has no band — skipped", pick.ticker)
            continue

        stock = (
            db.query(Stock)
            .filter(Stock.ticker == pick.ticker)
            .filter(Stock.source_key == InvestmentSource.GOMES.value)
            .first()
        )

        if stock is None:
            stock = Stock(
                ticker=pick.ticker,
                source_key=InvestmentSource.GOMES.value,
                speaker="Mark Gomes",
            )
            db.add(stock)
            report.created.append(pick.ticker)
        elif stock.green_line != pick.low or stock.red_line != pick.high:
            report.band_updated.append(pick.ticker)

        stock.green_line = pick.low
        stock.red_line = pick.high
        # Canon §8a: OFFICIAL is the Money Mark Portfolio, NOT OFFICIAL the
        # watchlist. This is the field the app's own split reads.
        stock.source_type = pick.pick_type

        if pick.price is not None:
            if stock.current_price != pick.price:
                report.price_updated.append(pick.ticker)
            stock.current_price = pick.price

    # No commit here. The caller owns the transaction — the route commits, the
    # script commits, and `--dry-run` rolls back. Committing mid-way made
    # `--dry-run` write the poll timestamp it had just promised not to write,
    # which then silently blocked the next real read for twelve hours.
    db.flush()
    logger.info(
        "Tracker sync: {} picks, {} created, {} rebanded, {} notable changes",
        report.picks_read, len(report.created), len(report.band_updated),
        len(report.changes),
    )
    return report


def get_state(db: Session) -> TrackerPollState:
    """The single poll-state row, created on first use."""
    state = db.query(TrackerPollState).order_by(TrackerPollState.id).first()
    if state is None:
        state = TrackerPollState()
        db.add(state)
        db.flush()
    return state


def record_changes(
    db: Session, changes: list[TrackerChange], *, at: datetime
) -> list[TrackerLineChange]:
    """
    Persist what moved, so it can reach the owner exactly once.

    Kept apart from `apply_picks` because the two answer different questions:
    that one updates what the app believes, this one records that the belief
    changed. Only the second is worth waking somebody up for.
    """
    rows: list[TrackerLineChange] = []
    for change in changes:
        row = TrackerLineChange(
            ticker=change.ticker,
            kind=change.kind,
            before_value=(str(change.before)[:60] if change.before is not None else None),
            after_value=(str(change.after)[:60] if change.after is not None else None),
            detail_cs=change.detail,
            detected_at=at,
        )
        db.add(row)
        rows.append(row)
    return rows


def sync_tracker(
    db: Session,
    *,
    force: bool = False,
    session: requests.Session | None = None,
    now: datetime | None = None,
) -> SyncReport:
    """
    Read the tracker once, if it is due, and apply what came back.

    Args:
        force: read even if the 12-hour interval has not elapsed. For the
            manual button and for a first run — never for a loop. The canon
            says these lines move on the order of weeks; polling harder buys
            nothing and costs somebody else's bandwidth.

    Never raises on an unreachable source: it returns UNAVAILABLE and records
    the attempt, so an outage does not turn into a retry loop, and "we could
    not see" stays distinguishable from "there was nothing to see".
    """
    moment = now or datetime.now(timezone.utc)
    state = get_state(db)

    if not force and not should_poll(state.last_attempt_at, now=moment):
        return SyncReport(status=STATUS_TOO_SOON, synced_at=moment)

    state.last_attempt_at = moment

    try:
        picks = fetch_tracker(session=session)
    except TrackerUnavailable as exc:
        message = str(exc)[:300]
        state.last_error = message
        logger.warning("Gomes tracker unavailable: {}", message)
        return SyncReport(status=STATUS_UNAVAILABLE, error=message, synced_at=moment)

    # The first successful read is a baseline, not news. Diffing sixteen picks
    # against an empty table would report sixteen NEW_PICKs and mail the lot —
    # the one message guaranteed to teach the owner to ignore the next one.
    # Conditioned on last_success_at rather than on the snapshot being empty,
    # so a tracker that genuinely empties still reports every REMOVED.
    first_read = state.last_success_at is None

    report = apply_picks(db, picks, now=moment, report_changes=not first_read)
    record_changes(db, report.changes, at=moment)

    state.last_success_at = moment
    state.last_error = None
    state.picks_last_read = report.picks_read
    return report


def official_tickers(picks: list[TrackerPick]) -> set[str]:
    """Tickers Gomes actually holds — the portfolio side of canon §8a."""
    return {p.ticker for p in picks if p.pick_type == OFFICIAL}


#: How long a re-banding stays on the daily list. Two weeks is the window in
#: which the owner might still be acting on numbers computed before the move —
#: long enough to survive a fortnight away, short enough not to become
#: wallpaper he stops reading.
LINE_NOTE_WINDOW = timedelta(days=14)


def recent_line_notes(db: Session, *, now: datetime | None = None) -> list[str]:
    """
    Recent revaluations, as sentences for the daily list.

    Only the two kinds that change what a number MEANS: a moved band, and a
    pick entering or leaving the real portfolio. A new name on the watch side
    is news, but it does not make yesterday's score wrong, so it does not
    belong at the top of a list the owner reads to decide what to do today.

    Never raises: the daily list must still render when this table cannot be
    read. Losing a note is recoverable; losing the morning is not.
    """
    moment = now or datetime.now(timezone.utc)
    try:
        rows = (
            db.query(TrackerLineChange)
            .filter(TrackerLineChange.kind.in_(("LINE_MOVED", "PICK_TYPE")))
            .filter(TrackerLineChange.detected_at >= moment - LINE_NOTE_WINDOW)
            .order_by(TrackerLineChange.detected_at.desc())
            .all()
        )
    except Exception:  # noqa: BLE001 — see docstring
        logger.exception("Změny na trackeru se nepodařilo načíst")
        return []

    return [
        f"⚠️ PŘECENĚNO: {row.detail_cs} — skóre spočítaná před tímhle "
        f"stála na starém pásmu"
        for row in rows
    ]


def unnotified_line_moves(
    db: Session, *, now: datetime | None = None
) -> list[TrackerLineChange]:
    """
    Revaluations the owner has not been told about yet.

    Distinct from `recent_line_notes`, which is what the daily list shows every
    time it renders. This is the away-mode question — has he been told — and it
    reads `notified_at` rather than a time window, so a fortnight away does not
    silently swallow a re-banding that happened on day two.

    Never raises: the away cycle must still run when this table cannot be read.
    """
    moment = now or datetime.now(timezone.utc)
    try:
        return (
            db.query(TrackerLineChange)
            .filter(TrackerLineChange.kind.in_(("LINE_MOVED", "PICK_TYPE")))
            .filter(TrackerLineChange.notified_at.is_(None))
            .filter(TrackerLineChange.detected_at >= moment - LINE_NOTE_WINDOW)
            .order_by(TrackerLineChange.detected_at.desc())
            .all()
        )
    except Exception:  # noqa: BLE001 — see docstring
        logger.exception("Neoznámená přecenění se nepodařilo načíst")
        return []
