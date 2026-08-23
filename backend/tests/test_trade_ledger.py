"""
Trade ledger math — the numbers that decide what the owner thinks he made.

These cover `compute_trade`, which is deliberately pure so the money math can
be verified without a database. The cases that matter most are the *unknown
cost basis* ones: every Degiro position imported before 2026-07-26 has
`avg_cost = NULL`, and the whole point is that "unknown" never quietly turns
into a number.
"""

import pytest

from app.services.trade_ledger import (
    TradeError,
    TradeSide,
    compute_trade,
)


# ==============================================================================
# BUY
# ==============================================================================

def test_buy_opening_a_position_sets_cost_basis_to_the_price_paid():
    out = compute_trade(
        old_shares=0, old_avg_cost=None, side=TradeSide.BUY, shares=10, price=5.0
    )
    assert out.new_shares == 10
    assert out.new_avg_cost == 5.0
    assert out.realized_pl is None       # a purchase realizes nothing
    assert out.gross_amount == 50.0


def test_buy_adding_to_a_known_position_weights_the_average():
    # 10 @ 5.00 (=50) + 10 @ 7.00 (=70) -> 20 shares, 120/20 = 6.00
    out = compute_trade(
        old_shares=10, old_avg_cost=5.0, side=TradeSide.BUY, shares=10, price=7.0
    )
    assert out.new_shares == 20
    assert out.new_avg_cost == pytest.approx(6.0)
    assert out.cost_basis == 5.0         # what it was before, for the audit trail


def test_buy_weighted_average_handles_uneven_sizes():
    # 3 @ 10.00 (=30) + 1 @ 2.00 (=2) -> 4 shares, 32/4 = 8.00
    out = compute_trade(
        old_shares=3, old_avg_cost=10.0, side=TradeSide.BUY, shares=1, price=2.0
    )
    assert out.new_avg_cost == pytest.approx(8.0)


def test_buy_into_unknown_cost_keeps_it_unknown():
    """
    THE honesty case. Holding 10 shares at an unknown price and buying 5 more
    at 3.00 does not make the average 3.00 — the true average is unknowable
    until the owner supplies the original price. Fabricating one here would
    produce a confident, wrong P/L on a position holding real money.
    """
    out = compute_trade(
        old_shares=10, old_avg_cost=None, side=TradeSide.BUY, shares=5, price=3.0
    )
    assert out.new_shares == 15
    assert out.new_avg_cost is None
    assert out.avg_cost_known is False


# ==============================================================================
# SELL
# ==============================================================================

def test_sell_realizes_profit_and_leaves_average_alone():
    # bought 10 @ 4.00, sell 4 @ 6.00 -> realized (6-4)*4 = 8.00
    out = compute_trade(
        old_shares=10, old_avg_cost=4.0, side=TradeSide.SELL, shares=4, price=6.0
    )
    assert out.new_shares == 6
    assert out.new_avg_cost == 4.0       # selling does not change what the rest cost
    assert out.realized_pl == pytest.approx(8.0)
    assert out.gross_amount == pytest.approx(24.0)


def test_sell_realizes_a_loss_as_a_negative_number():
    out = compute_trade(
        old_shares=10, old_avg_cost=10.0, side=TradeSide.SELL, shares=5, price=6.0
    )
    assert out.realized_pl == pytest.approx(-20.0)


def test_sell_at_exactly_cost_realizes_zero_not_none():
    """0.0 and None must stay distinguishable: broke even != don't know."""
    out = compute_trade(
        old_shares=10, old_avg_cost=5.0, side=TradeSide.SELL, shares=2, price=5.0
    )
    assert out.realized_pl == 0.0
    assert out.realized_pl is not None


def test_sell_with_unknown_cost_reports_none_never_zero():
    """The mirror of the case above — this is the one that used to lie."""
    out = compute_trade(
        old_shares=10, old_avg_cost=None, side=TradeSide.SELL, shares=3, price=9.0
    )
    assert out.realized_pl is None
    assert out.new_shares == 7
    assert out.gross_amount == pytest.approx(27.0)   # proceeds are still known


def test_selling_everything_closes_the_position():
    out = compute_trade(
        old_shares=8, old_avg_cost=2.0, side=TradeSide.SELL, shares=8, price=3.0
    )
    assert out.new_shares == 0
    assert out.closes_position is True
    assert out.realized_pl == pytest.approx(8.0)


# ==============================================================================
# Rejected input — a bad trade must fail loudly, not round itself off
# ==============================================================================

def test_cannot_sell_more_than_held():
    with pytest.raises(TradeError, match="držíš jen"):
        compute_trade(
            old_shares=5, old_avg_cost=1.0, side=TradeSide.SELL, shares=6, price=1.0
        )


@pytest.mark.parametrize("bad_shares", [0, -1, -0.5])
def test_zero_or_negative_size_is_rejected(bad_shares):
    with pytest.raises(TradeError):
        compute_trade(
            old_shares=10, old_avg_cost=1.0, side=TradeSide.BUY,
            shares=bad_shares, price=1.0,
        )


@pytest.mark.parametrize("bad_price", [0, -3.0])
def test_zero_or_negative_price_is_rejected(bad_price):
    """
    A trade at price 0 would silently destroy the cost basis of the whole
    position via the weighted average.
    """
    with pytest.raises(TradeError):
        compute_trade(
            old_shares=10, old_avg_cost=5.0, side=TradeSide.BUY,
            shares=1, price=bad_price,
        )


# ==============================================================================
# Round trip
# ==============================================================================

def test_buy_then_sell_everything_nets_out_to_the_spread():
    """Buy 10 @ 5, buy 10 @ 7 (avg 6), sell all 20 @ 8 -> (8-6)*20 = 40."""
    first = compute_trade(
        old_shares=0, old_avg_cost=None, side=TradeSide.BUY, shares=10, price=5.0
    )
    second = compute_trade(
        old_shares=first.new_shares, old_avg_cost=first.new_avg_cost,
        side=TradeSide.BUY, shares=10, price=7.0,
    )
    exit_ = compute_trade(
        old_shares=second.new_shares, old_avg_cost=second.new_avg_cost,
        side=TradeSide.SELL, shares=20, price=8.0,
    )
    assert second.new_avg_cost == pytest.approx(6.0)
    assert exit_.realized_pl == pytest.approx(40.0)
    assert exit_.closes_position is True
