"""
Currency Conversion Service

Converts various currencies to CZK for portfolio summary.
Live rates from the Czech National Bank, with a dated snapshot as last resort.

Two things this module used to get wrong, both in the direction of answering
confidently when it did not know:

1. **A silent nineteen-month-old fallback.** Any CNB hiccup dropped through to
   a hardcoded table stamped 2025-01-11, with nothing recording that it had
   happened. Measured against CNB on 2026-08-21 those numbers were 9-10 % off
   for USD, CAD and HKD — and the whole portfolio's CZK value is built on them.
2. **An unknown currency was quietly treated as dollars.** The lookup ended in
   a default of the USD rate. A position held in ILS — a currency the frontend
   has a symbol for and this table did not list — would have been valued at
   22.50 CZK per unit instead of 6.91. That is not a rounding error, it is a
   3.3x overstatement of a real holding.

Both are now impossible: an unknown currency raises, and every rate carries
whether it is live and what day it is from.

Clean Code Principles Applied:
- Single Responsibility: Currency conversion only
- Explicit logging instead of print statements
- Type hints throughout
- Constants extracted to module level
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Final

import requests


logger = logging.getLogger(__name__)


# ==============================================================================
# Constants
# ==============================================================================

CNB_API_URL: Final[str] = (
    "https://www.cnb.cz/en/financial-markets/foreign-exchange-market/"
    "central-bank-exchange-rate-fixing/central-bank-exchange-rate-fixing/daily.txt"
)
REQUEST_TIMEOUT_SECONDS: Final[int] = 5

#: CNB publishes one fixing per working day, shortly after 14:30 Prague time.
#: Re-reading it more often tells us nothing new — and the old code fetched it
#: once per position, so a fourteen-position portfolio meant fourteen
#: round-trips and fourteen chances to fall through to the stale table.
CACHE_TTL: Final[timedelta] = timedelta(hours=6)


class CurrencyError(Exception):
    """A currency cannot be converted. Never silently substituted."""


@dataclass(frozen=True)
class Rate:
    """A rate, plus the two facts that decide whether to trust it."""

    value: float
    is_live: bool
    as_of: date | None

    @property
    def age_days(self) -> int | None:
        return (date.today() - self.as_of).days if self.as_of else None


# ==============================================================================
# Last-resort snapshot
# ==============================================================================

#: Snapshot of the CNB fixing of 2026-08-21 (#161), used only when CNB cannot
#: be reached. Every use is logged, and every Rate built from it reports
#: `is_live=False`, so a stale number can be shown as stale rather than quietly
#: folded into a portfolio total.
FALLBACK_AS_OF: Final[date] = date(2026, 8, 21)
FALLBACK_RATES: Final[dict[str, float]] = {
    "CZK": 1.0000,
    "USD": 20.6200,
    "EUR": 24.1200,
    "GBP": 28.1530,
    "CHF": 25.7910,
    "CAD": 15.0050,
    "AUD": 14.7790,
    "HKD": 2.6300,
    "JPY": 0.1299,
    "SGD": 16.2550,
    "NOK": 2.2190,
    "SEK": 2.1800,
    "ILS": 6.9070,
}


# ==============================================================================
# Cache
# ==============================================================================

_lock = threading.Lock()
_cached_table: dict[str, float] | None = None
_cached_as_of: date | None = None
_cached_at: datetime | None = None


def _cache_is_fresh() -> bool:
    return (
        _cached_table is not None
        and _cached_at is not None
        and datetime.now() - _cached_at < CACHE_TTL
    )


def reset_cache() -> None:
    """Drop the cached CNB table. For tests and for a manual refresh."""
    global _cached_table, _cached_as_of, _cached_at
    with _lock:
        _cached_table = None
        _cached_as_of = None
        _cached_at = None


class CurrencyService:
    """Currency conversion to CZK, carrying the provenance of every rate."""

    FALLBACK_RATES = FALLBACK_RATES

    # ==========================================================================
    # Public Methods
    # ==========================================================================

    @classmethod
    def get_rate(cls, currency: str) -> Rate:
        """
        Get the rate to CZK together with where it came from.

        Raises:
            CurrencyError: if the currency is not one we have any rate for.
                Deliberately not a fallback to USD — see the module docstring.
        """
        currency = (currency or "").upper().strip()
        if not currency:
            raise CurrencyError("Chybí kód měny.")
        if currency == "CZK":
            return Rate(value=1.0, is_live=True, as_of=date.today())

        table, as_of = cls._live_table()
        if table and currency in table:
            return Rate(value=table[currency], is_live=True, as_of=as_of)

        if currency in FALLBACK_RATES:
            logger.warning(
                "Kurz %s: CNB nedostupna, pouzivam zalozni kurz z %s",
                currency, FALLBACK_AS_OF,
            )
            return Rate(
                value=FALLBACK_RATES[currency],
                is_live=False,
                as_of=FALLBACK_AS_OF,
            )

        # The currency exists in the portfolio but nowhere in our data. The old
        # code answered this case with the dollar rate.
        raise CurrencyError(
            f"Neznámá měna {currency} — kurz do CZK nemám. "
            f"Hodnotu této pozice do součtu nezapočítávám."
        )

    @classmethod
    def get_rate_to_czk(cls, currency: str) -> float:
        """
        Rate to CZK as a bare number.

        Raises:
            CurrencyError: for a currency we have no rate for.
        """
        return cls.get_rate(currency).value

    @classmethod
    def convert_to_czk(cls, amount: float, from_currency: str) -> float:
        """
        Convert an amount to CZK.

        Raises:
            CurrencyError: for a currency we have no rate for.
        """
        return amount * cls.get_rate_to_czk(from_currency)

    @classmethod
    def get_all_rates(cls) -> dict[str, float]:
        """Every rate we can currently produce, keyed by currency code."""
        table, _ = cls._live_table()
        if table:
            return {"CZK": 1.0, **table}
        return dict(FALLBACK_RATES)

    @classmethod
    def get_all_rates_detailed(cls) -> dict[str, Rate]:
        """Every rate, each carrying whether it is live and from what day."""
        table, as_of = cls._live_table()
        if table:
            return {
                "CZK": Rate(1.0, True, as_of),
                **{code: Rate(value, True, as_of) for code, value in table.items()},
            }
        return {
            code: Rate(value, False, FALLBACK_AS_OF)
            for code, value in FALLBACK_RATES.items()
        }

    # ==========================================================================
    # Private Methods
    # ==========================================================================

    @classmethod
    def _live_table(cls) -> tuple[dict[str, float] | None, date | None]:
        """
        The whole CNB fixing table, fetched at most once per CACHE_TTL.

        One request covers every currency in the portfolio. Returns
        `(None, None)` when CNB cannot be reached — the caller decides what to
        do about that, rather than being handed a number that looks live.
        """
        global _cached_table, _cached_as_of, _cached_at

        if _cache_is_fresh():
            return _cached_table, _cached_as_of

        with _lock:
            if _cache_is_fresh():
                return _cached_table, _cached_as_of

            try:
                response = requests.get(CNB_API_URL, timeout=REQUEST_TIMEOUT_SECONDS)
                if response.status_code != 200:
                    logger.warning("CNB vratila %s", response.status_code)
                    return None, None

                table, as_of = cls._parse_cnb(response.text)
                if not table:
                    logger.warning("CNB odpovedela, ale tabulka je prazdna")
                    return None, None

                _cached_table = table
                _cached_as_of = as_of
                _cached_at = datetime.now()
                logger.info("Nacteno %d kurzu CNB k %s", len(table), as_of)
                return table, as_of

            except Exception as e:
                logger.warning("CNB nedostupna: %s", e)
                return None, None

    @staticmethod
    def _parse_cnb(payload: str) -> tuple[dict[str, float], date | None]:
        """
        Parse the CNB fixing file.

        Line 1 is the fixing date ("21 Aug 2026 #161"), line 2 the header, then
        one row per currency: Country|Currency|Amount|Code|Rate. `Amount` is
        not always 1 — JPY is quoted per 100 — so the rate is divided by it.
        Getting that wrong would overstate a yen holding by a factor of 100.
        """
        lines = payload.strip().split("\n")
        if not lines:
            return {}, None

        as_of: date | None = None
        try:
            as_of = datetime.strptime(
                lines[0].split("#")[0].strip(), "%d %b %Y"
            ).date()
        except (ValueError, IndexError):
            logger.debug("Nepodarilo se precist datum kurzu z %r", lines[0][:40])

        table: dict[str, float] = {}
        for line in lines[1:]:
            parts = line.split("|")
            if len(parts) < 5:
                continue
            try:
                amount = float(parts[2])
                rate = float(parts[4])
            except ValueError:
                continue  # the header row
            if amount > 0:
                table[parts[3].strip().upper()] = rate / amount

        return table, as_of
