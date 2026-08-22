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
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.orm import Session

from app.core.sources import InvestmentSource
from app.models.stock import Stock
from app.services.gomes_tracker import (
    OFFICIAL,
    TrackerChange,
    TrackerPick,
    diff_tracker,
    fetch_tracker,
)


@dataclass
class SyncReport:
    """What one sync did — surfaced to the owner, not just logged."""

    picks_read: int = 0
    created: list[str] = field(default_factory=list)
    band_updated: list[str] = field(default_factory=list)
    price_updated: list[str] = field(default_factory=list)
    changes: list[TrackerChange] = field(default_factory=list)
    synced_at: datetime | None = None

    @property
    def touched_anything(self) -> bool:
        return bool(self.created or self.band_updated or self.changes)

    def summary_cs(self) -> str:
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


def apply_picks(db: Session, picks: list[TrackerPick]) -> SyncReport:
    """
    Write the tracker's bands onto GOMES-sourced stock rows.

    Pure-ish: takes the picks rather than fetching, so a sync can be tested
    against a fixed payload without a network.
    """
    report = SyncReport(picks_read=len(picks), synced_at=datetime.now(timezone.utc))
    previous = snapshot_existing(db)
    report.changes = diff_tracker(previous, picks)

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

    db.commit()
    logger.info(
        "Tracker sync: {} picks, {} created, {} rebanded, {} notable changes",
        report.picks_read, len(report.created), len(report.band_updated),
        len(report.changes),
    )
    return report


def sync_tracker(db: Session) -> SyncReport:
    """Read the tracker and apply it. Raises TrackerUnavailable on failure."""
    return apply_picks(db, fetch_tracker())


def official_tickers(picks: list[TrackerPick]) -> set[str]:
    """Tickers Gomes actually holds — the portfolio side of canon §8a."""
    return {p.ticker for p in picks if p.pick_type == OFFICIAL}
