"""
riskrewardcharts.com — the structured Gomes source.

docs/GOMES_METHODOLOGY_CANON.md §8 names this tracker as where the method's
numbers actually live, and §4a's logarithmic scoring formula was recovered
from it on 2026-07-25. The site publishes a JSON endpoint carrying everything
the canon needs per pick:

    ticker, low (Green Line), high (Red Line), pickType, price, chartUrl

`pickType` is the piece that has no substitute. OFFICIAL means the pick is in
the Money Mark Portfolio — a real, timestamped position — and NOT OFFICIAL
means it is being watched. That maps 1:1 onto the app's portfolio/watchlist
split (canon §8a), and it is not derivable from anything else.

Why polling this matters more than it looks
-------------------------------------------
The canon is explicit that these lines are NOT real-time and change rarely.
That is exactly why a change is worth an alert: when a Green or Red Line
moves, the analyst has revalued the company, and every downstream number —
the R/R score, the deserved score against cylinders, the 3-point triggers,
the buy guard — was computed against the old band until this moment. A pick
flipping OFFICIAL <-> NOT OFFICIAL is bigger still: it means he moved real
money in or out.

Scoring is not reimplemented here. RiskRewardCalculator.calculate_rr_score in
app/trading/gomes_logic.py is the canonical implementation, already verified
against this tracker's own output; this module only feeds it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import requests
from loguru import logger

from app.trading.gomes_logic import RiskRewardCalculator

BASE_URL = "https://www.riskrewardcharts.com"
TICKERS_ENDPOINT = f"{BASE_URL}/api/tickers"

USER_AGENT = "Akcion/1.0 (personal portfolio tool)"
REQUEST_TIMEOUT = 20

#: The tracker's own page says prices load gradually "to respect free data
#: limits", and the canon says the lines change rarely. Twice a day is already
#: generous for a source that moves on the order of weeks.
MIN_POLL_INTERVAL = timedelta(hours=12)

OFFICIAL = "OFFICIAL"
NOT_OFFICIAL = "NOT OFFICIAL"


class TrackerUnavailable(RuntimeError):
    """The tracker could not be read. Callers degrade; they never guess."""


@dataclass(frozen=True)
class TrackerPick:
    """One pick as the tracker publishes it."""

    ticker: str
    low: float | None      # Green Line — buy zone
    high: float | None     # Red Line — sell zone
    pick_type: str | None  # OFFICIAL (portfolio) | NOT OFFICIAL (watchlist)
    price: float | None
    chart_url: str | None = None

    @property
    def is_official(self) -> bool:
        return self.pick_type == OFFICIAL

    @property
    def rr_score(self) -> float | None:
        """
        Logarithmic R/R score, 10 at the Green Line down to 0 at the Red Line.

        Delegates to the canonical implementation, which returns None on
        unusable input rather than a fabricated number.
        """
        return RiskRewardCalculator.calculate_rr_score(self.price, self.low, self.high)


@dataclass(frozen=True)
class TrackerChange:
    """Something moved on the tracker. All four kinds are worth waking up for."""

    ticker: str
    kind: str  # NEW_PICK | REMOVED | LINE_MOVED | PICK_TYPE
    detail: str
    before: str | None = None
    after: str | None = None


def _num(value: object) -> float | None:
    """A price/line or nothing. Zero is not a price — it is missing data."""
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def parse_tracker(payload: dict) -> list[TrackerPick]:
    """Parse the /api/tickers response. Pure, so the shape rules are testable."""
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise TrackerUnavailable("Unexpected payload shape (expected {'items': [...]})")

    picks: list[TrackerPick] = []
    for item in payload["items"]:
        if not isinstance(item, dict):
            continue
        ticker = (item.get("ticker") or "").strip().upper()[:20]
        if not ticker:
            continue

        pick_type = item.get("pickType")
        if pick_type not in (OFFICIAL, NOT_OFFICIAL):
            # An unrecognised classification must not silently become
            # "watchlist" — that would hide a real portfolio position.
            pick_type = None

        picks.append(
            TrackerPick(
                ticker=ticker,
                low=_num(item.get("low")),
                high=_num(item.get("high")),
                pick_type=pick_type,
                price=_num(item.get("price")),
                chart_url=(str(item["chartUrl"])[:500] if item.get("chartUrl") else None),
            )
        )
    return picks


def fetch_tracker(*, session: requests.Session | None = None) -> list[TrackerPick]:
    """
    Read the current tracker.

    Raises:
        TrackerUnavailable: on any network or shape failure — never a partial
            list, so "unreachable" stays distinct from "no picks".
    """
    http = session or requests.Session()
    try:
        response = http.get(
            TICKERS_ENDPOINT,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        raise TrackerUnavailable(f"Tracker request failed: {exc}") from exc
    except ValueError as exc:
        raise TrackerUnavailable(f"Tracker returned non-JSON: {exc}") from exc

    picks = parse_tracker(payload)
    logger.info(
        "Gomes tracker read: {} picks ({} official)",
        len(picks), sum(1 for p in picks if p.is_official),
    )
    return picks


def diff_tracker(
    previous: list[TrackerPick], current: list[TrackerPick]
) -> list[TrackerChange]:
    """
    What changed between two reads.

    Deliberately ignores price movement: price changes every day and is read
    live elsewhere. What matters here is the analyst changing his mind — the
    band, or whether he actually owns it.
    """
    before = {p.ticker: p for p in previous}
    after = {p.ticker: p for p in current}
    changes: list[TrackerChange] = []

    for ticker in sorted(after.keys() - before.keys()):
        p = after[ticker]
        band = f"{p.low}–{p.high}" if p.low and p.high else "bez linek"
        changes.append(
            TrackerChange(
                ticker=ticker,
                kind="NEW_PICK",
                detail=f"{ticker}: nový pick ({p.pick_type or 'neznámý typ'}, pásmo {band})",
                after=p.pick_type,
            )
        )

    for ticker in sorted(before.keys() - after.keys()):
        changes.append(
            TrackerChange(
                ticker=ticker,
                kind="REMOVED",
                detail=f"{ticker}: zmizel z trackeru",
                before=before[ticker].pick_type,
            )
        )

    for ticker in sorted(before.keys() & after.keys()):
        was, now = before[ticker], after[ticker]

        # The big one: money moved in or out of the real portfolio.
        if was.pick_type != now.pick_type:
            if now.pick_type == OFFICIAL:
                detail = f"{ticker}: povýšen na OFFICIAL — Gomes ho má v portfoliu"
            elif was.pick_type == OFFICIAL:
                detail = f"{ticker}: sesazen z OFFICIAL — Gomes ho už v portfoliu nemá"
            else:
                detail = f"{ticker}: změna typu {was.pick_type} → {now.pick_type}"
            changes.append(
                TrackerChange(
                    ticker=ticker,
                    kind="PICK_TYPE",
                    detail=detail,
                    before=was.pick_type,
                    after=now.pick_type,
                )
            )

        # A moved band means every score computed until now used the old one.
        if was.low != now.low or was.high != now.high:
            changes.append(
                TrackerChange(
                    ticker=ticker,
                    kind="LINE_MOVED",
                    detail=(
                        f"{ticker}: přeceněno — pásmo {was.low}–{was.high} "
                        f"→ {now.low}–{now.high}"
                    ),
                    before=f"{was.low}–{was.high}",
                    after=f"{now.low}–{now.high}",
                )
            )

    return changes


def should_poll(last_polled_at: datetime | None, *, now: datetime | None = None) -> bool:
    """Whether enough time has passed to read the tracker again."""
    if last_polled_at is None:
        return True
    current = now or datetime.now(timezone.utc)
    if last_polled_at.tzinfo is None:
        last_polled_at = last_polled_at.replace(tzinfo=timezone.utc)
    return (current - last_polled_at) >= MIN_POLL_INTERVAL
