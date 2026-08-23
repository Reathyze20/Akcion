"""
Trading 212 — read-only account sync.

The owner holds part of his portfolio here and part at Degiro, and the same
instrument can sit at both (electroCore is at both today). Degiro gives a
transaction CSV; Trading 212 gives a real API, which means positions with a
genuine average price and no manual export step.

Deliberately read-only
----------------------
Trading 212 exposes POST /api/v0/equity/orders, which places real orders with
real money. This module has no method that can reach it and never will. The
owner's requirement was explicit — the app advises, he executes at the broker
— and there is a second, stronger guard: the API key itself should be created
WITHOUT the `orders` permission, so the capability does not exist even if this
file were changed. See docs/SETUP_GUIDE.md.

Endpoint surface (verified 2026-08-22 by probing for 401 vs 404; the official
docs sit behind a Redocly login):
    equity/portfolio            open positions
    equity/account/cash         cash balance
    equity/account/info         account currency and id
    equity/metadata/instruments instrument catalogue — ISIN <-> ticker
    equity/history/orders       executed order history
    equity/history/dividends    dividends received
    history/transactions        cash movements

`metadata/instruments` matters beyond this broker: it is a free ISIN-to-ticker
map, which is exactly what the Degiro import needs — that export identifies
instruments only by ISIN and product name, and seven of the owner's positions
are currently stored as raw ISINs because nothing could resolve them.

Rate limits
-----------
Trading 212 throttles aggressively and answers 429 rather than degrading. All
calls go through one place that respects a minimum spacing and surfaces a 429
as a typed error instead of an empty result — an empty portfolio and a
throttled request must never look the same.
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from datetime import datetime

import requests
from loguru import logger

BASE_URL = "https://live.trading212.com/api/v0"
REQUEST_TIMEOUT = 30

#: Minimum spacing PER ENDPOINT, in seconds. Trading 212 throttles each path
#: separately and answers 429 rather than degrading, so a single global gap is
#: not enough: six quick calls across different paths still tripped the limit
#: during setup. These are deliberately generous — this data changes on the
#: order of hours, and being rate-limited out of a portfolio read is worse
#: than waiting.
ENDPOINT_SPACING_S: dict[str, float] = {
    "equity/account/info": 60.0,
    "equity/metadata/instruments": 60.0,
    "equity/portfolio": 10.0,
    "equity/account/cash": 10.0,
    "equity/history/orders": 10.0,
    "equity/history/dividends": 10.0,
    "history/transactions": 10.0,
}
DEFAULT_SPACING_S = 10.0


class Trading212Error(RuntimeError):
    """Any failure talking to Trading 212. Callers degrade, never guess."""


class Trading212AuthError(Trading212Error):
    """Key missing, wrong, or lacking the permission for this endpoint."""


class Trading212RateLimited(Trading212Error):
    """Throttled. Distinct from 'no data' on purpose."""


@dataclass(frozen=True)
class T212Position:
    """One open position as the broker reports it."""

    ticker: str            # T212's own symbol, e.g. "ECOR_US_EQ"
    quantity: float        # fractional shares are normal here
    average_price: float   # in the instrument's currency
    current_price: float | None
    ppl: float | None      # unrealised P/L as T212 computes it
    initial_fill_date: datetime | None = None

    @property
    def plain_ticker(self) -> str:
        """
        "ECOR_US_EQ" -> "ECOR".

        T212 suffixes its symbols with market and instrument type. The bare
        symbol is what the Gomes tracker and the Breakout watchlist use.
        """
        return self.ticker.split("_", 1)[0].upper()


@dataclass(frozen=True)
class T212Instrument:
    """Catalogue entry — the ISIN/ticker bridge."""

    ticker: str
    isin: str | None
    name: str | None
    currency: str | None
    type_: str | None

    @property
    def plain_ticker(self) -> str:
        return self.ticker.split("_", 1)[0].upper()


def _parse_dt(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _num(raw: object) -> float | None:
    try:
        return float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


class Trading212Client:
    """
    Read-only client.

    Every request goes through `_get`, which is the only place that talks to
    the network — so throttling, auth errors and shape checks are enforced
    once rather than per call site.
    """

    def __init__(
        self, api_key: str, key_id: str | None = None, *, base_url: str = BASE_URL
    ) -> None:
        """
        Args:
            api_key: the API SECRET KEY.
            key_id: the API KEY ID that pairs with it.

        Trading 212 issues two credentials and authenticates with HTTP Basic
        over `id:secret`. Sending the secret alone — in any header shape, on
        live or demo — answers 401, so both are required. Verified 2026-08-22
        against a real key.
        """
        if not api_key or not api_key.strip():
            raise Trading212AuthError("Chybí T212_API_KEY v backend/.env")
        if not key_id or not key_id.strip():
            raise Trading212AuthError("Chybí T212_API_KEY_ID v backend/.env")
        self._key = api_key.strip()
        self._key_id = key_id.strip()
        self._auth = "Basic " + base64.b64encode(
            f"{self._key_id}:{self._key}".encode()
        ).decode()
        self._base = base_url.rstrip("/")
        self._session = requests.Session()
        #: Last call time per endpoint — the limits are per path, not global.
        self._last_call_at: dict[str, float] = {}

    # -- transport ---------------------------------------------------------

    def _get(self, path: str, **params) -> object:
        key = path.strip("/")
        spacing = ENDPOINT_SPACING_S.get(key, DEFAULT_SPACING_S)
        elapsed = time.monotonic() - self._last_call_at.get(key, 0.0)
        if elapsed < spacing:
            wait = spacing - elapsed
            logger.debug("T212 {}: waiting {:.1f}s for rate limit", key, wait)
            time.sleep(wait)

        url = f"{self._base}/{path.lstrip('/')}"
        try:
            response = self._session.get(
                url,
                headers={"Authorization": self._auth, "Accept": "application/json"},
                params=params or None,
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise Trading212Error(f"Trading 212 nedostupné: {exc}") from exc
        finally:
            self._last_call_at[key] = time.monotonic()

        if response.status_code == 401:
            raise Trading212AuthError(
                "Trading 212 odmítlo přihlášení (401). Zkontroluj T212_API_KEY_ID "
                "a T212_API_KEY, nebo omezení na IP adresu u toho klíče."
            )
        if response.status_code == 403:
            raise Trading212AuthError(
                f"Klíč nemá oprávnění pro {path} (403). To je v pořádku, pokud "
                f"jsi mu záměrně nedal práva navíc."
            )
        if response.status_code == 429:
            raise Trading212RateLimited(
                "Trading 212 omezuje četnost dotazů (429). Zkus to za chvíli."
            )
        if not response.ok:
            raise Trading212Error(f"Trading 212 vrátilo HTTP {response.status_code}")

        try:
            return response.json()
        except ValueError as exc:
            raise Trading212Error(f"Trading 212 nevrátilo JSON: {exc}") from exc

    # -- reads -------------------------------------------------------------

    def get_positions(self) -> list[T212Position]:
        """Open positions. An empty list means no positions, never an error."""
        payload = self._get("equity/portfolio")
        if not isinstance(payload, list):
            raise Trading212Error("Nečekaný tvar odpovědi u portfolia")

        out: list[T212Position] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            ticker = (item.get("ticker") or "").strip()
            quantity = _num(item.get("quantity"))
            avg = _num(item.get("averagePrice"))
            if not ticker or quantity is None or avg is None:
                logger.warning("T212 position skipped, incomplete: {}", ticker or "?")
                continue
            out.append(
                T212Position(
                    ticker=ticker,
                    quantity=quantity,
                    average_price=avg,
                    current_price=_num(item.get("currentPrice")),
                    ppl=_num(item.get("ppl")),
                    initial_fill_date=_parse_dt(item.get("initialFillDate")),
                )
            )
        logger.info("Trading 212: {} open positions", len(out))
        return out

    def get_cash(self) -> dict[str, float | None]:
        """Cash balance. Keys mirror the API: free, total, invested, ppl, result."""
        payload = self._get("equity/account/cash")
        if not isinstance(payload, dict):
            raise Trading212Error("Nečekaný tvar odpovědi u hotovosti")
        return {k: _num(v) for k, v in payload.items()}

    def get_account_info(self) -> dict[str, object]:
        payload = self._get("equity/account/info")
        if not isinstance(payload, dict):
            raise Trading212Error("Nečekaný tvar odpovědi u účtu")
        return payload

    def get_instruments(self) -> list[T212Instrument]:
        """
        The full instrument catalogue.

        Large (thousands of rows) and near-static, so callers should cache it.
        Its value is the ISIN-to-ticker mapping the Degiro import needs.
        """
        payload = self._get("equity/metadata/instruments")
        if not isinstance(payload, list):
            raise Trading212Error("Nečekaný tvar odpovědi u instrumentů")

        out: list[T212Instrument] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            ticker = (item.get("ticker") or "").strip()
            if not ticker:
                continue
            out.append(
                T212Instrument(
                    ticker=ticker,
                    isin=(item.get("isin") or None),
                    name=(item.get("name") or None),
                    currency=(item.get("currencyCode") or None),
                    type_=(item.get("type") or None),
                )
            )
        logger.info("Trading 212: {} instruments in catalogue", len(out))
        return out

    def build_isin_index(self) -> dict[str, str]:
        """ISIN -> bare ticker, for resolving the Degiro export."""
        return {
            inst.isin.upper(): inst.plain_ticker
            for inst in self.get_instruments()
            if inst.isin
        }

    # NOTE: there is intentionally no method for POST equity/orders.
    # This client cannot place a trade, and that is a feature.
