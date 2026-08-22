"""
Tests for currency conversion.

The whole portfolio's CZK value rests on these numbers, and the service had two
ways of producing one it could not justify: a silent nineteen-month-old
fallback, and a default to the dollar rate for any currency it did not know.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.services import currency as currency_module
from app.services.currency import (
    FALLBACK_AS_OF,
    FALLBACK_RATES,
    CurrencyError,
    CurrencyService,
    reset_cache,
)


CNB_PAYLOAD = """21 Aug 2026 #161
Country|Currency|Amount|Code|Rate
Australia|dollar|1|AUD|14.779
Canada|dollar|1|CAD|15.005
EMU|euro|1|EUR|24.120
Israel|new shekel|1|ILS|6.907
Japan|yen|100|JPY|12.991
USA|dollar|1|USD|20.620
"""


@pytest.fixture(autouse=True)
def _clean_cache():
    reset_cache()
    yield
    reset_cache()


def _cnb_ok():
    response = MagicMock()
    response.status_code = 200
    response.text = CNB_PAYLOAD
    return patch("app.services.currency.requests.get", return_value=response)


def _cnb_down():
    return patch("app.services.currency.requests.get",
                 side_effect=OSError("network unreachable"))


# ==============================================================================
# An unknown currency is not dollars
# ==============================================================================

class TestUnknownCurrencyIsRefused:
    def test_unknown_currency_raises(self):
        """
        The lookup used to end in a default of the USD rate. Anything the table
        did not list was valued as though it were dollars.
        """
        with _cnb_ok():
            with pytest.raises(CurrencyError, match="Neznámá měna"):
                CurrencyService.get_rate_to_czk("XYZ")

    def test_empty_currency_raises(self):
        with pytest.raises(CurrencyError, match="Chybí kód měny"):
            CurrencyService.get_rate_to_czk("")

    def test_the_shekel_case_that_motivated_this(self):
        """
        ILS was absent from the old fallback table, so a real holding in it
        would have been valued at the dollar rate: 22.50 CZK per unit against
        an actual 6.91 — a 3.3x overstatement.
        """
        with _cnb_ok():
            rate = CurrencyService.get_rate_to_czk("ILS")
        assert rate == pytest.approx(6.907)
        assert rate < 10, "a shekel must never be priced like a dollar"


# ==============================================================================
# Live rates, and knowing when they are not
# ==============================================================================

class TestProvenance:
    def test_live_rate_is_marked_live_and_dated(self):
        with _cnb_ok():
            rate = CurrencyService.get_rate("USD")
        assert rate.value == pytest.approx(20.620)
        assert rate.is_live is True
        assert rate.as_of == date(2026, 8, 21)

    def test_fallback_is_marked_not_live(self):
        """
        Falling back is allowed — refusing to show a portfolio because CNB is
        down helps nobody. Falling back *silently* is what was wrong.
        """
        with _cnb_down():
            rate = CurrencyService.get_rate("USD")
        assert rate.is_live is False
        assert rate.as_of == FALLBACK_AS_OF

    def test_czk_is_one(self):
        assert CurrencyService.get_rate_to_czk("CZK") == 1.0

    def test_case_and_whitespace_are_tolerated(self):
        with _cnb_ok():
            assert CurrencyService.get_rate_to_czk(" usd ") == pytest.approx(20.620)


# ==============================================================================
# Parsing
# ==============================================================================

class TestCnbParsing:
    def test_amount_column_is_honoured(self):
        """
        JPY is quoted per 100. Ignoring the Amount column would overstate a yen
        holding by a factor of one hundred.
        """
        with _cnb_ok():
            rate = CurrencyService.get_rate_to_czk("JPY")
        assert rate == pytest.approx(0.12991)

    def test_header_row_does_not_become_a_currency(self):
        with _cnb_ok():
            rates = CurrencyService.get_all_rates()
        assert "CODE" not in rates
        assert set(rates) >= {"USD", "EUR", "CAD", "ILS", "JPY", "AUD", "CZK"}

    def test_fixing_date_is_read(self):
        table, as_of = CurrencyService._parse_cnb(CNB_PAYLOAD)
        assert as_of == date(2026, 8, 21)
        assert table["USD"] == pytest.approx(20.620)


# ==============================================================================
# One fetch, not one per position
# ==============================================================================

class TestCaching:
    def test_many_lookups_make_one_request(self):
        """
        `get_rate_to_czk` was called once per position, each one a round-trip —
        fourteen positions meant fourteen chances to drop to the fallback.
        """
        with _cnb_ok() as get:
            for code in ("USD", "EUR", "CAD", "ILS", "JPY", "USD", "EUR"):
                CurrencyService.get_rate_to_czk(code)
            assert get.call_count == 1

    def test_reset_forces_a_refetch(self):
        with _cnb_ok() as get:
            CurrencyService.get_rate_to_czk("USD")
            reset_cache()
            CurrencyService.get_rate_to_czk("USD")
            assert get.call_count == 2


# ==============================================================================
# The snapshot itself
# ==============================================================================

class TestFallbackTableIsPlausible:
    def test_fallback_is_dated_this_year(self):
        """The old table was stamped 2025-01-11 and never revisited."""
        assert FALLBACK_AS_OF.year >= 2026

    def test_fallback_covers_every_currency_the_ui_can_show(self):
        """
        The frontend renders symbols for these. A currency the UI displays but
        the rate table omits is exactly the ILS hole.
        """
        assert {"USD", "EUR", "CAD", "CZK", "GBP", "ILS"} <= set(FALLBACK_RATES)
