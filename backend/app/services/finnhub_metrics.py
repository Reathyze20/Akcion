"""
Fundamentals for the companies EDGAR cannot see, from a key the app already has.

The gap this closes
-------------------
SEC XBRL covers seven of the twelve holdings. The other five — four Canadian
listings and an OTC name, together about 60 % of the money — had only Yahoo's
trailing aggregates, and a rolling annual total is not a series: no year-on-year
growth is derivable from it, so the lifecycle rubric kept saying "meziroční růst
tržeb neznám" for the largest part of the portfolio.

Finnhub was already configured (`FINNHUB_API_KEY`) and already used, for prices
only. Its free `/stock/metric` endpoint publishes year-on-year revenue growth,
margins and a 52-week high — and although it returns nothing for `GSI.V` or
`DBO.TO`, it returns a full set for their **US OTC symbols**. The app has mapped
those since `tickers.py` was written:

    GSI.V  → GKPRF   revenue TTM +23,5 %, quarterly +68,0 %
    DBO.TO → DBOXF   revenue TTM +34,6 %, net margin +30,3 %
    IMP.V  → ITMSF   revenue TTM −61,8 %, gross margin −80,4 %
    KUYA.V → KUYAF   no revenue growth — a pre-revenue miner, correctly empty

What this layer is worth, and what it is not
--------------------------------------------
These are a vendor's computations over filings the app never read, not the
filings themselves. That puts them above Yahoo's aggregates — a real
year-on-year comparison rather than a rolling total — and below SEC XBRL, where
the app reads the tagged numbers and can see which period each one covers.

So confidence is capped at medium, exactly as the Yahoo layer is, and the layer
is always named. `KUYAF` returning no revenue growth is a fact about a
pre-revenue silver miner, not a failure, and it stays an unknown rather than
becoming a zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Final

import requests
from loguru import logger

from app.config.settings import get_settings
from app.core.tickers import variants_of

_BASE: Final[str] = "https://finnhub.io/api/v1"

#: Free tier is 60 calls a minute; one company is one call and this runs from a
#: script, so the limit is not close. The timeout matters more — a hung request
#: inside a nightly job is a job that never finishes.
_TIMEOUT_SECONDS: Final[float] = 12.0

#: The fields worth reading, and the name each carries in the response.
_REVENUE_TTM = "revenueGrowthTTMYoy"
_REVENUE_QUARTER = "revenueGrowthQuarterlyYoy"
_GROSS_MARGIN = "grossMarginTTM"
_NET_MARGIN = "netProfitMarginTTM"
_WEEK_HIGH = "52WeekHigh"


@dataclass(frozen=True)
class Metrics:
    """What Finnhub publishes about one company, in the app's own units."""

    symbol: str
    #: Percent, year on year. None for a company with no revenue to compare —
    #: which is a fact about a pre-revenue miner, not a missing reading.
    revenue_yoy_pct: float | None = None
    #: The quarterly comparison, which moves before the trailing one does.
    revenue_quarter_yoy_pct: float | None = None
    gross_margin_pct: float | None = None
    net_margin_pct: float | None = None
    week_high: float | None = None
    fetched_at: datetime | None = None

    @property
    def has_anything(self) -> bool:
        return any(
            v is not None
            for v in (
                self.revenue_yoy_pct,
                self.revenue_quarter_yoy_pct,
                self.gross_margin_pct,
                self.net_margin_pct,
            )
        )

    @property
    def is_profitable(self) -> bool | None:
        """
        Whether the business makes money, or None when nobody said.

        None is not False. A company with no margin reported is unassessed, and
        the rubric must not read that as a loss.
        """
        if self.net_margin_pct is None:
            return None
        return self.net_margin_pct > 0


def fetch(ticker: str, *, get=None) -> Metrics | None:
    """
    Metrics for one company, trying its listings in order.

    `get` is injected so the rules can be exercised without a network call.
    Never raises: a company the vendor cannot serve must not stop the rest.
    """
    settings = get_settings()
    key = getattr(settings, "finnhub_api_key", None)
    if not key:
        logger.warning("FINNHUB_API_KEY není nastavený — vrstva Finnhub se přeskočí")
        return None

    caller = get or _get_json
    # US symbols first: the vendor returns a full set for GKPRF and nothing at
    # all for GSI.V, and the app has mapped the pair since `tickers.py`.
    for symbol in _symbols_us_first(ticker):
        try:
            payload = caller(symbol, key)
        except Exception as e:  # noqa: BLE001 — see docstring
            # The type and a one-line reason, never the exception's own text.
            # `requests` puts the full URL in an HTTPError message and the URL
            # carries the API key, so `logger.exception` here wrote a live
            # credential into the log the first time this ran.
            logger.warning(
                "Finnhub na {} selhal: {}", symbol, _safe_reason(e, key)
            )
            continue

        metrics = _parse(symbol, payload)
        if metrics is not None and metrics.has_anything:
            return metrics
    return None


def _symbols_us_first(ticker: str) -> list[str]:
    """
    The company's listings, US-style symbols before exchange-suffixed ones.

    Not cosmetic: `/stock/metric` answers for `GKPRF` and returns an empty
    object for `GSI.V`, so trying the held symbol first would find nothing and
    report the company as uncovered.
    """
    symbols = list(variants_of(ticker) or ())
    if ticker.upper() not in symbols:
        symbols.append(ticker.upper())
    return sorted(symbols, key=lambda s: ("." in s, s))


def _get_json(symbol: str, key: str) -> dict[str, Any]:
    response = requests.get(
        f"{_BASE}/stock/metric",
        params={"symbol": symbol, "metric": "all", "token": key},
        timeout=_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json() or {}


def _parse(symbol: str, payload: dict[str, Any]) -> Metrics | None:
    metric = (payload or {}).get("metric") or {}
    if not metric:
        return None

    def num(name: str) -> float | None:
        value = metric.get(name)
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    return Metrics(
        symbol=symbol,
        revenue_yoy_pct=num(_REVENUE_TTM),
        revenue_quarter_yoy_pct=num(_REVENUE_QUARTER),
        gross_margin_pct=num(_GROSS_MARGIN),
        net_margin_pct=num(_NET_MARGIN),
        week_high=num(_WEEK_HIGH),
        fetched_at=datetime.now(timezone.utc),
    )


def _safe_reason(error: Exception, key: str) -> str:
    """
    A failure described without the credential that caused it.

    `requests` builds an HTTPError message out of the full request URL, and the
    URL carries `token=<API key>`. Logging the exception verbatim therefore
    writes a live credential into a file — which it did, the first time this ran
    against the real key. The type is enough to debug with; when a message is
    worth keeping, the key is struck out of it first.
    """
    text = str(error)
    if key:
        text = text.replace(key, "<klíč>")
    # Belt and braces: drop any query string, whatever the message shape.
    text = text.split("?", 1)[0]
    return f"{type(error).__name__}: {text[:120]}" if text else type(error).__name__
