"""
Buy Guard + dual-source buy policy tests (Phase 1 of the fidelity roadmap).

Locks the hard BUY gates from GOMES_METHODOLOGY_CANON.md §6: buy only when the
market is GREEN, cylinders are known, the stock is not in Wait Time, and the
R/R score beats the deserved score. Also locks the dual-source matrix: Breakout
Investors modulates position size but can never override a Gomes block.
"""

from __future__ import annotations

import pytest

from app.trading.gomes_logic import (
    AGREEMENT_POSITION_CAPS,
    GomesGatekeeper,
    InvestmentVerdict,
    LifecyclePhase,
    MarketAlert,
    evaluate_dual_source_buy,
)

guard = GomesGatekeeper.evaluate_buy_guard

# A fully-passing baseline: GREEN market, 7 cylinders (deserved 3), score 8.
GOOD = dict(
    market_alert="GREEN",
    rr_score=8.0,
    deserved_score=3.0,
    cylinders=7,
    lifecycle_stage="GOLD_MINE",
)


def _with(**overrides):
    return {**GOOD, **overrides}


# ---------------------------------------------------------------------------
# The one way to pass
# ---------------------------------------------------------------------------

def test_all_conditions_pass():
    allowed, reason = guard(**GOOD)
    assert allowed is True
    assert "satisfied" in reason


def test_accepts_enum_inputs():
    allowed, _ = guard(
        market_alert=MarketAlert.GREEN,
        rr_score=8.0,
        deserved_score=3.0,
        cylinders=7,
        lifecycle_stage=LifecyclePhase.GOLD_MINE,
    )
    assert allowed is True


# ---------------------------------------------------------------------------
# Every failure permutation blocks with a named reason
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("alert", ["YELLOW", "ORANGE", "RED"])
def test_non_green_market_blocks(alert):
    allowed, reason = guard(**_with(market_alert=alert))
    assert allowed is False
    assert alert in reason and "GREEN" in reason


def test_unknown_alert_string_blocks():
    allowed, reason = guard(**_with(market_alert="PURPLE"))
    assert allowed is False


@pytest.mark.parametrize("cylinders", [None, 0])
def test_unknown_or_zero_cylinders_block(cylinders):
    """Refuse BUY when quality is unverified — the Wait-Time value-trap guard."""
    allowed, reason = guard(**_with(cylinders=cylinders))
    assert allowed is False
    assert "Cylinders" in reason


def test_wait_time_blocks():
    allowed, reason = guard(**_with(lifecycle_stage="WAIT_TIME"))
    assert allowed is False
    assert "Wait Time" in reason


def test_wait_time_enum_blocks():
    allowed, _ = guard(**_with(lifecycle_stage=LifecyclePhase.WAIT_TIME))
    assert allowed is False


@pytest.mark.parametrize("stage", ["GREAT_FIND", "GOLD_MINE", "UNKNOWN", None])
def test_non_wait_time_stages_do_not_block(stage):
    allowed, _ = guard(**_with(lifecycle_stage=stage))
    assert allowed is True


@pytest.mark.parametrize(
    "rr_score, deserved",
    [(None, 3.0), (8.0, None), (None, None)],
)
def test_missing_scores_block(rr_score, deserved):
    allowed, reason = guard(**_with(rr_score=rr_score, deserved_score=deserved))
    assert allowed is False
    assert "Missing" in reason


@pytest.mark.parametrize(
    "rr_score, deserved",
    [(3.0, 3.0), (2.99, 3.0), (0.0, 3.0)],  # equal or below = not cheap enough
)
def test_score_not_above_deserved_blocks(rr_score, deserved):
    allowed, reason = guard(**_with(rr_score=rr_score, deserved_score=deserved))
    assert allowed is False
    assert "Not cheap enough" in reason


def test_gate_order_market_alert_first():
    """With everything wrong at once, the market alert is the first named gate."""
    allowed, reason = guard(
        market_alert="RED",
        rr_score=None,
        deserved_score=None,
        cylinders=None,
        lifecycle_stage="WAIT_TIME",
    )
    assert allowed is False
    assert "RED" in reason


# ---------------------------------------------------------------------------
# Dual-source matrix (Gomes × Breakout Investors)
# ---------------------------------------------------------------------------

def test_agree_allows_full_tier_size():
    d = evaluate_dual_source_buy(True, "ok", "BULLISH", tier_max_pct=10.0)
    assert d.decision == "ALLOW"
    assert d.agreement == "AGREE"
    assert d.max_position_pct == 10.0  # tier max, within the 15% app cap
    assert d.review_required is False


def test_agree_caps_at_app_level_15pct():
    d = evaluate_dual_source_buy(True, "ok", "BULLISH", tier_max_pct=20.0)
    assert d.max_position_pct == AGREEMENT_POSITION_CAPS["AGREE"] == 15.0


def test_single_source_standard_size():
    d = evaluate_dual_source_buy(True, "ok", None, tier_max_pct=10.0)
    assert d.decision == "ALLOW"
    assert d.agreement == "SINGLE"
    assert d.max_position_pct == 7.0
    assert d.review_required is False


def test_neutral_breakout_is_mixed_standard_size():
    d = evaluate_dual_source_buy(True, "ok", "NEUTRAL", tier_max_pct=10.0)
    assert d.agreement == "MIXED"
    assert d.max_position_pct == 7.0


def test_conflict_capped_small_and_flagged():
    d = evaluate_dual_source_buy(True, "ok", "BEARISH", tier_max_pct=10.0)
    assert d.decision == "ALLOW"
    assert d.agreement == "CONFLICT"
    assert d.max_position_pct == 5.0
    assert d.review_required is True


def test_breakout_bullish_never_overrides_gomes_block():
    """GOMES_NO_BUY: valuation veto stands even when the crowd is euphoric."""
    d = evaluate_dual_source_buy(
        False, "Market Alert is YELLOW (BUY requires GREEN)", "BULLISH", 10.0
    )
    assert d.decision == "REJECT"
    assert d.agreement == "GOMES_NO_BUY"
    assert d.max_position_pct == 0.0
    assert "YELLOW" in d.reason


def test_gomes_block_without_breakout_still_rejects():
    d = evaluate_dual_source_buy(False, "Cylinders unknown or zero", None, 10.0)
    assert d.decision == "REJECT"
    assert d.max_position_pct == 0.0


def test_tier_smaller_than_cap_wins():
    """A TERTIARY tier (2%) stays 2% even when sources agree."""
    d = evaluate_dual_source_buy(True, "ok", "BULLISH", tier_max_pct=2.0)
    assert d.max_position_pct == 2.0


# ---------------------------------------------------------------------------
# Verdict-path integration: GomesGatekeeper.evaluate() cannot emit a buy-side
# verdict that the Buy Guard would refuse (Path 2 end-to-end enforcement)
# ---------------------------------------------------------------------------

# A setup that historically produced BUY: high conviction, Gold Mine,
# price near the green line (cheap), cylinders strong.
BUYABLE_EVAL = dict(
    ticker="CXDO",
    conviction_score=8,
    lifecycle_phase=LifecyclePhase.GOLD_MINE,
    current_price=6.0,
    green_line=5.0,
    red_line=20.0,
    cylinders_count=8,
)

BUY_SIDE = {
    InvestmentVerdict.STRONG_BUY,
    InvestmentVerdict.BUY,
    InvestmentVerdict.ACCUMULATE,
}


def test_evaluate_green_buyable_still_buys():
    verdict = GomesGatekeeper(MarketAlert.GREEN).evaluate(**BUYABLE_EVAL)
    assert verdict.verdict in BUY_SIDE


def test_evaluate_yellow_never_emits_buy():
    """Canon §6: buy only when GREEN — even a perfect setup on YELLOW holds."""
    verdict = GomesGatekeeper(MarketAlert.YELLOW).evaluate(**BUYABLE_EVAL)
    assert verdict.verdict not in BUY_SIDE
    assert any("BUY GUARD" in r for r in verdict.risk_factors)


def test_evaluate_unknown_cylinders_never_emits_buy():
    """No quality data -> no BUY, however high the conviction score."""
    verdict = GomesGatekeeper(MarketAlert.GREEN).evaluate(
        **{**BUYABLE_EVAL, "cylinders_count": None}
    )
    assert verdict.verdict not in BUY_SIDE
    assert any("Cylinders" in r for r in verdict.risk_factors)


def test_evaluate_price_above_deserved_never_emits_buy():
    """Score at/below deserved (10 − cylinders) -> not cheap enough to buy."""
    verdict = GomesGatekeeper(MarketAlert.GREEN).evaluate(
        **{**BUYABLE_EVAL, "cylinders_count": 1, "current_price": 19.0}
    )
    assert verdict.verdict not in BUY_SIDE


def test_evaluate_guard_downgrade_is_hold_not_blocked():
    """Failing the guard means 'don't buy', not 'sell/blocked'."""
    verdict = GomesGatekeeper(MarketAlert.YELLOW).evaluate(**BUYABLE_EVAL)
    assert verdict.verdict == InvestmentVerdict.HOLD
    assert verdict.passed_gomes_filter is True
