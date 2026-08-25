"""
Fundamentals for the companies EDGAR cannot see, from a key already in .env.

SEC XBRL covers seven of twelve holdings. The other five — four Canadian
listings and an OTC name, about 60 % of the money — had only Yahoo's trailing
aggregates, from which no year-on-year growth is derivable, so the lifecycle
rubric said "meziroční růst tržeb neznám" for most of the portfolio.

Finnhub returns nothing for `GSI.V` and a full set for `GKPRF`. The whole value
of this module is trying the US symbol first, and the whole risk is the API key
travelling somewhere it should not.
"""

from app.services.finnhub_metrics import (
    Metrics,
    _parse,
    _safe_reason,
    _symbols_us_first,
)

FULL = {
    "metric": {
        "revenueGrowthTTMYoy": 23.49,
        "revenueGrowthQuarterlyYoy": 67.98,
        "grossMarginTTM": 44.43,
        "netProfitMarginTTM": -2.81,
        "52WeekHigh": 3.14,
    }
}


# ==============================================================================
# The US symbol has to be tried first
# ==============================================================================

def test_us_symbols_come_before_exchange_suffixed_ones():
    """
    The vendor answers for GKPRF and returns an empty object for GSI.V. Asking
    in the held symbol's order finds nothing and reports the company as
    uncovered — which is how 60 % of the portfolio stayed unassessed.
    """
    order = _symbols_us_first("GSI.V")
    assert order.index("GKPRF") < order.index("GSI.V")


def test_the_asked_for_symbol_is_never_dropped():
    assert "VTSI" in _symbols_us_first("VTSI")


# ==============================================================================
# Parsing, and the difference between zero and unknown
# ==============================================================================

def test_a_full_response_is_read_into_the_apps_own_units():
    m = _parse("GKPRF", FULL)
    assert m.revenue_yoy_pct == 23.49
    assert m.revenue_quarter_yoy_pct == 67.98
    assert m.net_margin_pct == -2.81


def test_an_empty_response_is_none_not_an_empty_reading():
    assert _parse("GSI.V", {"metric": {}}) is None
    assert _parse("GSI.V", {}) is None


def test_a_company_with_no_revenue_has_no_growth_rather_than_zero():
    """
    KUYAF is a pre-revenue silver miner. "No revenue growth" is a fact about
    the company, and turning it into 0 % would tell the rubric the story failed
    to catch when there is no story to catch yet.
    """
    m = _parse("KUYAF", {"metric": {"52WeekHigh": 1.25}})
    assert m is not None
    assert m.revenue_yoy_pct is None
    assert not m.has_anything


def test_an_unreported_margin_is_unknown_not_a_loss():
    m = _parse("KUYAF", {"metric": {"52WeekHigh": 1.25}})
    assert m.is_profitable is None


def test_a_reported_margin_answers_the_question():
    assert _parse("X", {"metric": {"netProfitMarginTTM": 30.26}}).is_profitable is True
    assert _parse("X", {"metric": {"netProfitMarginTTM": -2.81}}).is_profitable is False


def test_a_junk_value_is_dropped_rather_than_crashing():
    m = _parse("X", {"metric": {"revenueGrowthTTMYoy": "n/a", "grossMarginTTM": 44.4}})
    assert m.revenue_yoy_pct is None
    assert m.gross_margin_pct == 44.4  # the good field survives the bad one


# ==============================================================================
# The API key never reaches a log
# ==============================================================================

def test_the_key_is_struck_out_of_a_failure_message():
    """
    `requests` builds an HTTPError message out of the full URL, and the URL
    carries `token=<key>`. Logging the exception verbatim wrote a live
    credential into the log the first time this ran.
    """
    key = "d5lp8dhr01qidp4hr9gg"
    error = RuntimeError(
        f"403 Forbidden for url: https://finnhub.io/api/v1/stock/metric"
        f"?symbol=X&metric=all&token={key}"
    )
    reason = _safe_reason(error, key)
    assert key not in reason


def test_the_query_string_is_dropped_whatever_the_message_shape():
    reason = _safe_reason(RuntimeError("boom?token=secret&x=1"), "")
    assert "secret" not in reason


def test_the_failure_type_survives_so_it_can_still_be_debugged():
    assert "RuntimeError" in _safe_reason(RuntimeError("x"), "")


def test_an_empty_key_does_not_blank_the_whole_message():
    assert "boom" in _safe_reason(RuntimeError("boom"), "")


# ==============================================================================
# The dataclass, used directly by the intake
# ==============================================================================

def test_a_reading_with_only_a_price_high_carries_nothing_fundamental():
    assert not Metrics(symbol="X", week_high=1.25).has_anything


def test_any_fundamental_field_counts_as_something():
    assert Metrics(symbol="X", gross_margin_pct=44.4).has_anything
