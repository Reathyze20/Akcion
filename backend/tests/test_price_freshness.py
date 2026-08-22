"""
Tests for the guard that says how old a price is.

The app is for someone who may not open it for a week at a time. That makes
"how old is this number" a load-bearing question, and it had two answers that
were wrong in the same direction — both made data look fresher than it was.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.services.market_data import MarketDataService


# ==============================================================================
# A failed refresh must not reset the freshness clock
# ==============================================================================

class TestStalePricesKeepTheirAge:
    def _position(self, ticker: str, stamped: datetime | None):
        pos = MagicMock()
        pos.ticker = ticker
        pos.current_price = 10.0
        pos.last_price_update = stamped
        return pos

    def test_failed_refresh_does_not_restamp_the_position(self):
        """
        `daily_actions` flags a price older than STALE_PRICE_AFTER (3 days).
        Every failed fetch used to write utcnow() over that timestamp, so the
        guard could never fire — the more Yahoo failed, the fresher the data
        claimed to be.
        """
        week_old = datetime.utcnow() - timedelta(days=7)
        position = self._position("VTSI", week_old)

        db = MagicMock()
        db.query.return_value.all.return_value = [position]

        stale_row = {
            "current_price": 3.18,
            "is_stale": True,
            "stale_reason": "Stažení z Yahoo selhalo",
        }

        with patch("app.services.market_data.YahooFinanceCache") as cache_cls:
            cache_cls.return_value.get_stock_data.return_value = stale_row
            result = MarketDataService.refresh_portfolio_prices(db)

        assert position.last_price_update == week_old, (
            "a stale price kept its original timestamp"
        )
        assert result["stale_count"] == 1
        assert result["updated_count"] == 0, (
            "serving a cached price is not the same claim as fetching one"
        )

    def test_successful_refresh_does_restamp(self):
        week_old = datetime.utcnow() - timedelta(days=7)
        position = self._position("VTSI", week_old)

        db = MagicMock()
        db.query.return_value.all.return_value = [position]

        fresh_row = {"current_price": 3.42, "is_stale": False, "stale_reason": None}

        with patch("app.services.market_data.YahooFinanceCache") as cache_cls:
            cache_cls.return_value.get_stock_data.return_value = fresh_row
            result = MarketDataService.refresh_portfolio_prices(db)

        assert position.last_price_update > week_old
        assert result["updated_count"] == 1
        assert result["stale_count"] == 0


# ==============================================================================
# A missing quote is missing
# ==============================================================================

class TestFinnhubDoesNotSubstituteYesterday:
    def _respond(self, payload: dict):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = payload
        return response

    def test_missing_quote_returns_none_not_previous_close(self):
        """
        Finnhub answers `c: 0` when it has no quote. The old code then reached
        for `pc` — the previous close — and returned it to the caller as the
        current price, indistinguishable from a real quote.
        """
        with patch("app.services.market_data.requests.get",
                   return_value=self._respond({"c": 0, "pc": 42.5})), \
             patch("app.services.market_data.get_settings") as settings:
            settings.return_value.finnhub_api_key = "key"
            assert MarketDataService._get_price_from_finnhub("VTSI") is None

    def test_real_quote_is_returned(self):
        with patch("app.services.market_data.requests.get",
                   return_value=self._respond({"c": 3.18, "pc": 3.05})), \
             patch("app.services.market_data.get_settings") as settings:
            settings.return_value.finnhub_api_key = "key"
            assert MarketDataService._get_price_from_finnhub("VTSI") == 3.18


class TestMassiveIsNamedForWhatItReturns:
    def test_the_close_based_source_says_so_in_its_name(self):
        """
        The endpoint is `/prev`. Under the old name the app could not tell a
        live quote from a day-old close anywhere in the call chain.
        """
        assert hasattr(MarketDataService, "_get_previous_close_from_massive")
        assert not hasattr(MarketDataService, "_get_price_from_massive")
