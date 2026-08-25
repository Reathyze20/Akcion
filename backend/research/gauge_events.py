"""
Scoring the assisted semafor against the only labelled events that exist.

`app/services/market_gauge.py` has been checked against exactly two dates in its
life: end-1999, which it finds, and mid-2007, which it misses and says so. Two
points is not a scorecard.

Mark's sheet carries eleven more: six dates he opened an inverse-index ETF or
shorted an index, three he closed one, and two where a note names a level
outright ("ORANGE (LEVEL 2) ALERT LIFTED", "NOW AT YELLOW ALERT"). Each is a
dated, attributable claim about whether the market was dangerous, made by the
person whose method the gauge is trying to reproduce.

What this measures, and what it does not
----------------------------------------
A hedge opening is a claim the market was dangerous; a hedge closing is a claim
it no longer was. The gauge agrees when `z >= EXPENSIVE_Z` at an opening and
`z < EXPENSIVE_Z` at a closing.

It does NOT measure whether Mark was right — several of these hedges lost money.
It measures whether a price-versus-trend reading would have said what he said.
Those are different questions and only the second one is about the gauge.

Eleven events is a scorecard, not a fit. Nothing here should be used to move a
threshold; see the note on `EXPENSIVE_Z` in the module it belongs to.
"""

from __future__ import annotations

import csv
import pathlib
from dataclasses import dataclass
from datetime import date
from typing import Final

from app.services.market_gauge import EXPENSIVE_Z, GaugeError, fit

EVENTS_CSV: Final[pathlib.Path] = (
    pathlib.Path(__file__).resolve().parent / "data" / "gauge_events.csv"
)

#: Labels that claim the market was dangerous at that moment.
CAUTIOUS_LABELS: Final[frozenset[str]] = frozenset({"HEDGE_OPEN", "ALERT_SET"})
#: Labels that claim it no longer was.
CALM_LABELS: Final[frozenset[str]] = frozenset({"HEDGE_CLOSE", "ALERT_LIFTED"})


@dataclass(frozen=True)
class Event:
    """One dated claim about the market, with the evidence for it."""

    event_date: date
    label: str
    #: Only where a note names a level outright. Empty for a hedge trade — an
    #: opened hedge is an act, not a declared level, and inventing one would be
    #: manufacturing the data this whole exercise exists to avoid.
    claimed_level: str
    evidence_row_id: int
    evidence_quote: str

    @property
    def claims_danger(self) -> bool:
        return self.label in CAUTIOUS_LABELS


@dataclass(frozen=True)
class Scored:
    """What the gauge would have said, against what Mark did."""

    event: Event
    z_score: float
    percentile: float
    position: str
    suggested_alert: str
    #: The monthly close the reading actually landed on.
    bar_date: date
    agrees: bool

    @property
    def lag_days(self) -> int:
        """
        How stale the monthly bar is relative to the event.

        Reported rather than hidden: the gauge reads monthly closes, so a query
        for 14 February lands on 1 February. Up to a month of a fast-moving
        market can sit in that gap, and in February 2020 it did.
        """
        return (self.event.event_date - self.bar_date).days


def load_events() -> list[Event]:
    """Every labelled event, oldest first."""
    events: list[Event] = []
    with EVENTS_CSV.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(
            line for line in handle if not line.startswith("#")
        ):
            events.append(
                Event(
                    event_date=date.fromisoformat(row["event_date"]),
                    label=row["label"].strip(),
                    claimed_level=row["claimed_level"].strip(),
                    evidence_row_id=int(row["evidence_row_id"]),
                    evidence_quote=row["evidence_quote"].strip(),
                )
            )
    return sorted(events, key=lambda e: e.event_date)


def score(
    points: list[tuple[date, float]], events: list[Event]
) -> list[Scored]:
    """
    Read the chart as of each event. Events the gauge cannot reach are dropped.

    `MIN_YEARS` is not relaxed for this. An event too early for thirty years of
    history produces no row rather than a reading from a shorter series, because
    a trend fitted through fifteen years of one regime says nothing about where
    the market sits in its history — which is the module's own argument, and it
    does not stop applying because a test would be tidier if it did.
    """
    scored: list[Scored] = []
    for event in events:
        try:
            reading = fit(points, as_of=event.event_date)
        except GaugeError:
            continue
        expensive = reading.z_score >= EXPENSIVE_Z
        scored.append(
            Scored(
                event=event,
                z_score=reading.z_score,
                percentile=reading.percentile,
                position=reading.position.value,
                suggested_alert=reading.suggested_alert,
                bar_date=reading.as_of,
                agrees=(expensive == event.claims_danger),
            )
        )
    return scored
