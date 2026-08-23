"""
Tests for the order guard that runs before a trade is accepted.

Its third rule called itself "Weinstein Stage 4 (price below falling 30 WMA)".
Nothing in it was a moving average — it compared the price to the green line,
which is a DCF-derived valuation floor. The two say opposite things: canon §4a
puts a price at or below the green line at an R/R score of 10, the strongest
buy the method produces. So the rule rejected the exact purchase the
methodology calls for, under the heading "Gomes Rule Violation".
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.core.gomes_compliance import verify_gomes_compliance


def _order(ticker: str = "TPCS", action: str = "BUY"):
    order = MagicMock()
    order.ticker = ticker
    order.action = action
    order.side = action
    order.quantity = 100
    return order


def _db_with_stock(**fields):
    stock = MagicMock()
    stock.ticker = "TPCS"
    stock.current_price = 4.56
    stock.green_line = 3.25
    stock.red_line = 14.00
    stock.inflection_status = "ACTIVE"
    stock.conviction_score = 7
    stock.cash_runway_months = 24
    for key, value in fields.items():
        setattr(stock, key, value)

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = stock
    return db, stock


def _blocked_error(db, order) -> dict | None:
    """Return the guard's rejection detail, or None if it allowed the order."""
    try:
        verify_gomes_compliance(order, db)
    except HTTPException as e:
        return e.detail if isinstance(e.detail, dict) else {"error": str(e.detail)}
    return None


# ==============================================================================
# A cheap price is not a reason to refuse a buy
# ==============================================================================

class TestPriceBelowGreenLineIsNotAViolation:
    def test_a_bargain_outside_wait_time_is_allowed(self):
        """
        Canon §4a: at or below the green line the R/R score caps at 10 — the
        method's maximum buy. The old rule blocked at 5 % below it.
        """
        db, _ = _db_with_stock(
            current_price=2.00,        # well under the 3.25 green line
            inflection_status="GOLD_MINE",
        )
        assert _blocked_error(db, _order()) is None

    def test_deep_value_is_not_reported_as_a_gomes_violation(self):
        db, _ = _db_with_stock(current_price=1.50, inflection_status="ACTIVE")
        error = _blocked_error(db, _order())
        assert error is None or error.get("error") != "WEINSTEIN_STAGE_4"


# ==============================================================================
# Wait Time is the canonical refusal, and the price plays no part in it
# ==============================================================================

class TestWaitTimeBlocksRegardlessOfPrice:
    def test_wait_time_below_the_green_line_is_blocked(self):
        db, _ = _db_with_stock(current_price=2.00, inflection_status="WAIT_TIME")
        error = _blocked_error(db, _order())
        assert error is not None
        assert error["error"] == "WAIT_TIME"

    def test_wait_time_above_the_green_line_is_also_blocked(self):
        """
        The case the old rule let through. Its price and phase tests were
        ANDed, so a Wait Time position at a full price passed the guard —
        dead money at the worst entry, which is the one worth stopping.
        """
        db, _ = _db_with_stock(current_price=12.00, inflection_status="WAIT_TIME")
        error = _blocked_error(db, _order())
        assert error is not None
        assert error["error"] == "WAIT_TIME"

    def test_the_message_cites_the_canon_not_a_chart(self):
        db, _ = _db_with_stock(inflection_status="WAIT_TIME")
        error = _blocked_error(db, _order())
        assert "Wait Time" in error["message"]
        assert "Weinstein" not in error["message"]
        assert "WMA" not in error["message"]


# ==============================================================================
# The pillar's weight, and what the prompt says about it
# ==============================================================================

class TestTechnicalAnalysisCarriesNoWeight:
    def test_weinstein_weight_is_zero(self):
        from app.trading.master_signal import WeightConfigV2
        assert WeightConfigV2.WEINSTEIN_GUARD == 0.0

    def test_the_prompt_does_not_advertise_a_weight_the_engine_ignores(self):
        """
        The engine scored it at 0 % while the prompt told the model 15 %.
        """
        from app.core import prompts_enterprise_v2 as prompts

        source = prompts.ENTERPRISE_ANALYST_PROMPT_V2
        assert "WEINSTEIN GUARD (15% váhy)" not in source
        assert "WEINSTEIN GUARD (0% váhy" in source

    def test_the_prompt_says_it_is_not_gomes(self):
        from app.core import prompts_enterprise_v2 as prompts
        assert "NENÍ z Gomesovy metody" in prompts.ENTERPRISE_ANALYST_PROMPT_V2
