"""
Tests for the emotional brakes.

Two properties matter more than the thresholds themselves:

1. They **warn, never block.** A brake that silently refuses a trade is
   unjudgeable — the reasoning never reaches the person deciding.
2. They stay quiet when they do not know. An unknown cost basis means we cannot
   say whether a sale was a loss, and "we do not know" must not become "it was
   a loss" any more than it becomes "it was fine".
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app.models.portfolio import InvestmentLogType
from app.services.emotional_brakes import (
    BURST_THRESHOLD,
    REENTRY_WINDOW,
    check_burst,
    check_recent_loss,
    check_reentry,
    collect_brakes,
)


NOW = datetime(2026, 8, 22, 12, 0)


def _trade(ticker: str, *, side=InvestmentLogType.SELL, realized_pl=None, days_ago=1):
    log = MagicMock()
    log.ticker = ticker
    log.log_type = side
    log.realized_pl = realized_pl
    log.created_at = NOW - timedelta(days=days_ago)
    return log


def _db(trades: list):
    """A session whose filtered, ordered ledger query yields `trades`."""
    db = MagicMock()
    chain = db.query.return_value.filter.return_value
    chain.filter.return_value = chain
    chain.order_by.return_value.all.return_value = trades
    return db


# ==============================================================================
# Buying back what you sold at a loss
# ==============================================================================

class TestReentryAfterLoss:
    def test_a_loss_sale_inside_the_window_is_named(self):
        db = _db([_trade("TPCS", realized_pl=-18000.0, days_ago=6)])
        brake = check_reentry(db, "TPCS", now=NOW)

        assert brake is not None
        assert brake.kind == "REENTRY_AFTER_LOSS"
        assert "TPCS" in brake.message
        assert "6 dny" in brake.message or "6 dní" in brake.message

    def test_the_message_asks_rather_than_forbids(self):
        """
        The whole design: it puts the question next to the buy. It does not
        remove the buy, and nothing here returns a veto.
        """
        db = _db([_trade("TPCS", realized_pl=-18000.0, days_ago=3)])
        brake = check_reentry(db, "TPCS", now=NOW)
        assert "zeptej se" in brake.message
        assert not hasattr(brake, "blocked")

    def test_a_profitable_sale_says_nothing(self):
        db = _db([_trade("TPCS", realized_pl=42000.0, days_ago=3)])
        assert check_reentry(db, "TPCS", now=NOW) is None

    def test_an_unknown_cost_basis_says_nothing(self):
        """
        `realized_pl` is None when the purchase price was never known — every
        pre-2026-07-26 Degiro import. We cannot call that a loss.
        """
        db = _db([_trade("TPCS", realized_pl=None, days_ago=3)])
        assert check_reentry(db, "TPCS", now=NOW) is None

    def test_a_different_ticker_says_nothing(self):
        db = _db([_trade("VTSI", realized_pl=-18000.0, days_ago=3)])
        assert check_reentry(db, "TPCS", now=NOW) is None

    def test_a_buy_is_not_mistaken_for_a_sale(self):
        db = _db([_trade("TPCS", side=InvestmentLogType.BUY, realized_pl=-100.0)])
        assert check_reentry(db, "TPCS", now=NOW) is None

    def test_case_is_ignored(self):
        db = _db([_trade("tpcs", realized_pl=-18000.0, days_ago=3)])
        assert check_reentry(db, "TPCS", now=NOW) is not None

    def test_the_window_is_a_month_of_holding_horizon(self):
        assert REENTRY_WINDOW == timedelta(days=30)


# ==============================================================================
# Trading more than the method calls for
# ==============================================================================

class TestBurst:
    def test_a_week_of_churn_is_named(self):
        trades = [
            _trade("TPCS", days_ago=1), _trade("VTSI", days_ago=2),
            _trade("IZEA", days_ago=4),
        ]
        brake = check_burst(_db(trades), now=NOW)

        assert brake is not None
        assert brake.kind == "TRADE_BURST"
        assert "IZEA, TPCS, VTSI" in brake.message

    def test_below_the_threshold_says_nothing(self):
        trades = [_trade("TPCS", days_ago=1)] * (BURST_THRESHOLD - 1)
        assert check_burst(_db(trades), now=NOW) is None

    def test_it_does_not_call_the_activity_a_mistake(self):
        trades = [_trade(f"T{i}", days_ago=i + 1) for i in range(BURST_THRESHOLD)]
        brake = check_burst(_db(trades), now=NOW)
        assert "není to samo o sobě chyba" in brake.message.lower()


# ==============================================================================
# The days after a loss
# ==============================================================================

class TestRecentLoss:
    def test_a_significant_loss_is_flagged(self):
        db = _db([_trade("TPCS", realized_pl=-60000.0, days_ago=1)])
        brake = check_recent_loss(db, portfolio_value_czk=800_000.0, now=NOW)

        assert brake is not None
        assert brake.kind == "RECENT_SIGNIFICANT_LOSS"
        assert "7.5" in brake.message

    def test_a_small_loss_is_not(self):
        db = _db([_trade("TPCS", realized_pl=-4000.0, days_ago=1)])
        assert check_recent_loss(db, portfolio_value_czk=800_000.0, now=NOW) is None

    def test_no_portfolio_value_means_no_claim(self):
        """
        Without a denominator there is no "significant" to measure against, and
        picking one would be inventing the finding.
        """
        db = _db([_trade("TPCS", realized_pl=-60000.0, days_ago=1)])
        assert check_recent_loss(db, portfolio_value_czk=None, now=NOW) is None
        assert check_recent_loss(db, portfolio_value_czk=0.0, now=NOW) is None


# ==============================================================================
# Collection
# ==============================================================================

class TestCollectBrakes:
    def test_a_quiet_week_produces_nothing(self):
        assert collect_brakes(_db([]), 800_000.0, now=NOW) == []

    def test_a_fresh_loss_comes_before_the_burst(self):
        trades = [
            _trade("TPCS", realized_pl=-60000.0, days_ago=1),
            _trade("VTSI", days_ago=2),
            _trade("IZEA", days_ago=3),
        ]
        brakes = collect_brakes(_db(trades), 800_000.0, now=NOW)

        assert [b.kind for b in brakes] == [
            "RECENT_SIGNIFICANT_LOSS", "TRADE_BURST",
        ]
