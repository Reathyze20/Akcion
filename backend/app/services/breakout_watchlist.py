"""
Breakout Investors watchlist — the structured half of the second source.

Until now the BREAKOUT_INVESTORS side of the dual-source model had nothing to
read: the position caps in docs/GOMES_METHODOLOGY_CANON.md (AGREE <=15% /
SINGLE <=7% / CONFLICT <=5%) were implemented against a source that only
existed as chat messages. breakoutinvestors.com publishes the group's actual
watchlist with two numbers per name:

    endorsements — how many members back it (crowd conviction)
    upside       — expected gain as a RATIO (0.62 = +62%, 7.0 = +700%)

That complements Gomes rather than duplicating him. He supplies the valuation
band (green/red lines, cylinders, the logarithmic R/R score); they supply
conviction and a target. AEHR is the case that shows why both are needed:
5 endorsements — the group likes it — against +6% upside and a price above
Gomes' red line. Agreement on quality, disagreement on price.

Operational caution
-------------------
These endpoints answer without authentication today, on a site whose
watchlist is a paid product. That is very likely an oversight on their side,
not an invitation. Three rules follow, and they are enforced here rather than
left to discipline:

  * one poll per day (MIN_POLL_INTERVAL), never a tight loop,
  * an honest User-Agent that says what this is,
  * nothing in the app may HARD-DEPEND on this data. If it disappears
    tomorrow, `fetch_watchlist` returns an error and the Gomes side keeps
    working on its own.

Everything returned here is untrusted external input. Text fields are length-
capped and are never interpreted as instructions — they are only ever stored
and displayed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import requests
from loguru import logger

BASE_URL = "https://www.breakoutinvestors.com"
STOCKS_ENDPOINT = f"{BASE_URL}/api/stocks"
QUOTES_ENDPOINT = f"{BASE_URL}/api/stocks/batch"

USER_AGENT = "Akcion/1.0 (personal portfolio tool; subscriber account)"
REQUEST_TIMEOUT = 20

#: Never poll more often than this. The watchlist changes on the order of
#: weeks — `created_at` values sit days to months apart — so a daily read
#: loses nothing and keeps the load negligible.
MIN_POLL_INTERVAL = timedelta(hours=20)

_MAX_TEXT = 200


class WatchlistUnavailable(RuntimeError):
    """The source could not be read. Callers must degrade, never guess."""


@dataclass(frozen=True)
class WatchlistEntry:
    """One name on the Breakout Investors watchlist."""

    symbol: str
    company_name: str | None
    endorsements: int
    #: Expected gain as a ratio. 0.62 means +62%. Kept as the source states it;
    #: converting to a percentage happens at display time only.
    upside_ratio: float | None
    added_at: datetime | None

    @property
    def upside_pct(self) -> float | None:
        return None if self.upside_ratio is None else self.upside_ratio * 100.0


@dataclass(frozen=True)
class WatchlistChange:
    """Something that moved between two reads — the reason to poll at all."""

    symbol: str
    kind: str  # ADDED | REMOVED | ENDORSEMENTS | UPSIDE
    before: float | int | None
    after: float | int | None
    detail: str


def _clip(value: object) -> str | None:
    if value is None:
        return None
    return str(value)[:_MAX_TEXT]


def _parse_entry(raw: dict) -> WatchlistEntry | None:
    """Convert one API object, skipping anything that is not usable."""
    symbol = (raw.get("symbol") or "").strip().upper()[:20]
    if not symbol:
        return None

    try:
        endorsements = int(raw.get("endorsements") or 0)
    except (TypeError, ValueError):
        endorsements = 0

    upside = raw.get("upside")
    try:
        upside_ratio = float(upside) if upside is not None else None
    except (TypeError, ValueError):
        upside_ratio = None

    added_at: datetime | None = None
    created = raw.get("created_at")
    if isinstance(created, str):
        try:
            added_at = datetime.fromisoformat(created.replace("Z", "+00:00"))
        except ValueError:
            added_at = None

    return WatchlistEntry(
        symbol=symbol,
        company_name=_clip(raw.get("companyName")),
        endorsements=endorsements,
        upside_ratio=upside_ratio,
        added_at=added_at,
    )


def parse_watchlist(payload: list) -> list[WatchlistEntry]:
    """Parse the /api/stocks response. Pure — no I/O, so it is testable."""
    if not isinstance(payload, list):
        raise WatchlistUnavailable("Unexpected payload shape (expected a list)")
    entries = [_parse_entry(item) for item in payload if isinstance(item, dict)]
    return [e for e in entries if e is not None]


def fetch_watchlist(*, session: requests.Session | None = None) -> list[WatchlistEntry]:
    """
    Read the current watchlist.

    Raises:
        WatchlistUnavailable: on any network or shape failure. Never returns
            a partial or invented list — an empty watchlist and an unreachable
            one must stay distinguishable.
    """
    http = session or requests.Session()
    try:
        response = http.get(
            STOCKS_ENDPOINT,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        raise WatchlistUnavailable(f"Watchlist request failed: {exc}") from exc
    except ValueError as exc:
        raise WatchlistUnavailable(f"Watchlist returned non-JSON: {exc}") from exc

    entries = parse_watchlist(payload)
    logger.info("Breakout watchlist read: {} names", len(entries))
    return entries


def fetch_quotes(
    symbols: list[str], *, session: requests.Session | None = None
) -> dict[str, float]:
    """Current prices for the given symbols. Missing symbols are simply absent."""
    if not symbols:
        return {}

    http = session or requests.Session()
    try:
        response = http.get(
            QUOTES_ENDPOINT,
            params={"symbols": ",".join(symbols)},
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise WatchlistUnavailable(f"Quote request failed: {exc}") from exc

    out: dict[str, float] = {}
    for item in payload.get("data", []) if isinstance(payload, dict) else []:
        symbol = (item.get("symbol") or "").strip().upper()
        price = item.get("price")
        # A zero price is not a price — the endpoint returns 0 for fields it
        # has no data for, and a 0 would read as a real quote downstream.
        if symbol and isinstance(price, (int, float)) and price > 0:
            out[symbol] = float(price)
    return out


def implied_target(price: float | None, upside_ratio: float | None) -> float | None:
    """
    The group's target price, reconstructed from a quote and their upside.

    They publish `upside` — expected gain as a ratio — rather than the target
    itself, but the two are the same fact stated differently: a target of $0.30
    on a $0.09 quote IS +233 %. Multiplying back recovers numbers that are
    visibly round (WATT $29.40, DAIO $6.50, ADCOF $0.30), which is what a
    stored analyst target looks like and not what an arithmetic coincidence
    looks like.

    Two conditions, and both are refusals rather than fallbacks:

      * no price, or a non-positive one, means no target. Their quote endpoint
        answers 0 for fields it has no data for, and a 0 multiplied by anything
        is a target of zero — a sell signal invented out of a missing quote.
      * no upside means no target. Not "assume flat".

    Accuracy is bounded by the quote the ratio was computed against. Reading
    both in the same pass keeps them consistent; pairing today's upside with
    last week's price would not.
    """
    if price is None or price <= 0 or upside_ratio is None:
        return None
    target = price * (1.0 + upside_ratio)
    return target if target > 0 else None


def diff_watchlist(
    previous: list[WatchlistEntry], current: list[WatchlistEntry]
) -> list[WatchlistChange]:
    """
    What moved between two reads.

    This is the whole point of polling: the owner does not need a daily list
    of 28 names, he needs to know when one of them changed. Pure function so
    the change rules are testable without a network.
    """
    before = {e.symbol: e for e in previous}
    after = {e.symbol: e for e in current}
    changes: list[WatchlistChange] = []

    for symbol in sorted(after.keys() - before.keys()):
        e = after[symbol]
        changes.append(
            WatchlistChange(
                symbol=symbol,
                kind="ADDED",
                before=None,
                after=e.endorsements,
                detail=(
                    f"{symbol} přibyl na watchlist "
                    f"({e.endorsements} podpisů"
                    + (f", upside {e.upside_pct:+.0f} %" if e.upside_pct is not None else "")
                    + ")"
                ),
            )
        )

    for symbol in sorted(before.keys() - after.keys()):
        changes.append(
            WatchlistChange(
                symbol=symbol,
                kind="REMOVED",
                before=before[symbol].endorsements,
                after=None,
                detail=f"{symbol} zmizel z watchlistu",
            )
        )

    for symbol in sorted(before.keys() & after.keys()):
        was, now = before[symbol], after[symbol]

        if was.endorsements != now.endorsements:
            direction = "vzrostla" if now.endorsements > was.endorsements else "klesla"
            changes.append(
                WatchlistChange(
                    symbol=symbol,
                    kind="ENDORSEMENTS",
                    before=was.endorsements,
                    after=now.endorsements,
                    detail=(
                        f"{symbol}: konvikce {direction} "
                        f"{was.endorsements} → {now.endorsements} podpisů"
                    ),
                )
            )

        if was.upside_ratio is not None and now.upside_ratio is not None:
            # Ignore drift smaller than a percentage point of expected gain;
            # `upside` moves with price every day and would otherwise fire
            # constantly, which trains the owner to ignore the alerts.
            if abs(now.upside_ratio - was.upside_ratio) >= 0.01:
                changes.append(
                    WatchlistChange(
                        symbol=symbol,
                        kind="UPSIDE",
                        before=was.upside_ratio,
                        after=now.upside_ratio,
                        detail=(
                            f"{symbol}: očekávaný růst "
                            f"{was.upside_pct:+.0f} % → {now.upside_pct:+.0f} %"
                        ),
                    )
                )

    return changes


def should_poll(last_polled_at: datetime | None, *, now: datetime | None = None) -> bool:
    """
    Whether enough time has passed to read the source again.

    Enforced rather than documented: a retry loop against someone else's
    unauthenticated endpoint is how an integration gets noticed and closed.
    """
    if last_polled_at is None:
        return True
    current = now or datetime.now(timezone.utc)
    if last_polled_at.tzinfo is None:
        last_polled_at = last_polled_at.replace(tzinfo=timezone.utc)
    return (current - last_polled_at) >= MIN_POLL_INTERVAL
