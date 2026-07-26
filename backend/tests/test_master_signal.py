"""
Master Signal v2 tests — fundamentals-only scoring (Phase 2 of the roadmap).

Locks gap #3 from GOMES_METHODOLOGY_CANON.md: the Weinstein 30 WMA trend check
is technical analysis and canon says the method has "almost NOTHING to do with
technical analysis". These tests guarantee the Weinstein pillar carries ZERO
weight in buy_confidence, never blocks, and is surfaced only as the
informational `technical_overlay_warning` badge.

(The previous version of this file tested the deleted V1 six-component
aggregator and failed at collection; it was rewritten for V2 on 2026-07-26.)
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.trading.master_signal import (
    CashRunwayStatus,
    MasterSignalAggregatorV2,
    MasterSignalResultV2,
    SignalStrength,
    ThesisTrackerScore,
    ValuationCashScore,
    WeightConfigV2,
    WeinsteinGuardScore,
    WeinsteinPhase,
)


# ==============================================================================
# Builders
# ==============================================================================

def make_thesis(score: float = 80.0, red_flags: int = 0) -> ThesisTrackerScore:
    return ThesisTrackerScore(
        conviction_score=score,
        milestones_hit=0,
        red_flags_count=red_flags,
        verdict="BUY",
        combined_score=score,
    )


def make_valuation(
    score: float = 70.0,
    status: CashRunwayStatus = CashRunwayStatus.HEALTHY,
) -> ValuationCashScore:
    return ValuationCashScore(
        cash_on_hand=None,
        total_debt=None,
        burn_rate=None,
        runway_months=18.0 if status == CashRunwayStatus.HEALTHY else 3.0,
        runway_status=status,
        dilution_risk=status != CashRunwayStatus.HEALTHY,
        combined_score=score,
    )


def make_weinstein(
    score: float = 50.0,
    phase: WeinsteinPhase = WeinsteinPhase.PHASE_1_BASE,
) -> WeinsteinGuardScore:
    return WeinsteinGuardScore(
        current_price=10.0,
        wma_30=9.0,
        wma_slope=0.0,
        phase=phase,
        price_vs_wma_pct=0.0,
        combined_score=score,
    )


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    return db


@pytest.fixture
def aggregator(mock_db):
    agg = MasterSignalAggregatorV2(mock_db)
    # Isolate from DB/AI: verdict object only feeds target/stop extraction.
    agg.gomes_service = MagicMock()
    agg.gomes_service.generate_verdict.return_value = None
    return agg


def run_signal(aggregator, thesis, valuation, weinstein) -> MasterSignalResultV2:
    with patch.object(
        MasterSignalAggregatorV2, "_calculate_thesis_tracker", return_value=thesis
    ), patch.object(
        MasterSignalAggregatorV2, "_calculate_valuation_cash", return_value=valuation
    ), patch.object(
        MasterSignalAggregatorV2, "_calculate_weinstein_guard", return_value=weinstein
    ):
        return aggregator.calculate_master_signal("TEST", current_price=10.0)


# ==============================================================================
# Weights — fundamentals only
# ==============================================================================

class TestWeights:
    def test_weights_sum_to_one(self):
        WeightConfigV2.validate()  # must not raise
        total = (
            WeightConfigV2.THESIS_TRACKER
            + WeightConfigV2.VALUATION_CASH
            + WeightConfigV2.WEINSTEIN_GUARD
        )
        assert total == pytest.approx(1.0)

    def test_canonical_split_60_40_0(self):
        assert WeightConfigV2.THESIS_TRACKER == pytest.approx(0.60)
        assert WeightConfigV2.VALUATION_CASH == pytest.approx(0.40)
        assert WeightConfigV2.WEINSTEIN_GUARD == 0.0

    def test_thesis_is_the_authority(self):
        assert WeightConfigV2.THESIS_TRACKER == max(
            WeightConfigV2.THESIS_TRACKER,
            WeightConfigV2.VALUATION_CASH,
            WeightConfigV2.WEINSTEIN_GUARD,
        )


# ==============================================================================
# Score purity — technicals must not move the number
# ==============================================================================

class TestScorePurity:
    def test_confidence_is_thesis_plus_valuation_only(self, aggregator):
        result = run_signal(
            aggregator, make_thesis(80.0), make_valuation(70.0), make_weinstein(50.0)
        )
        assert result.buy_confidence == pytest.approx(80.0 * 0.60 + 70.0 * 0.40)

    def test_weinstein_score_cannot_move_confidence(self, aggregator):
        """Identical fundamentals, extreme opposite technicals -> same number."""
        best_trend = run_signal(
            aggregator, make_thesis(80.0), make_valuation(70.0),
            make_weinstein(100.0, WeinsteinPhase.PHASE_2_ADVANCE),
        )
        worst_trend = run_signal(
            aggregator, make_thesis(80.0), make_valuation(70.0),
            make_weinstein(0.0, WeinsteinPhase.PHASE_4_DECLINE),
        )
        assert best_trend.buy_confidence == pytest.approx(worst_trend.buy_confidence)

    def test_phase_4_does_not_block(self, aggregator):
        result = run_signal(
            aggregator, make_thesis(80.0), make_valuation(70.0),
            make_weinstein(0.0, WeinsteinPhase.PHASE_4_DECLINE),
        )
        assert result.blocked is False
        assert result.blocked_reason is None


# ==============================================================================
# Technical overlay — informational badge only
# ==============================================================================

class TestTechnicalOverlay:
    def test_phase_4_sets_overlay_warning(self, aggregator):
        result = run_signal(
            aggregator, make_thesis(), make_valuation(),
            make_weinstein(0.0, WeinsteinPhase.PHASE_4_DECLINE),
        )
        assert result.technical_overlay_warning is True
        assert "30WMA" in result.technical_overlay_note

    @pytest.mark.parametrize(
        "phase",
        [
            WeinsteinPhase.PHASE_1_BASE,
            WeinsteinPhase.PHASE_2_ADVANCE,
            WeinsteinPhase.PHASE_3_TOP,
        ],
    )
    def test_other_phases_no_warning(self, aggregator, phase):
        result = run_signal(
            aggregator, make_thesis(), make_valuation(), make_weinstein(50.0, phase)
        )
        assert result.technical_overlay_warning is False
        assert result.technical_overlay_note is None

    def test_to_dict_exposes_overlay_and_marks_weinstein_informational(self, aggregator):
        result = run_signal(
            aggregator, make_thesis(), make_valuation(),
            make_weinstein(0.0, WeinsteinPhase.PHASE_4_DECLINE),
        )
        data = result.to_dict()
        assert data["technical_overlay_warning"] is True
        assert "30WMA" in data["technical_overlay_note"]
        assert data["components"]["weinstein_guard"]["informational_only"] is True


# ==============================================================================
# Fundamental blocks still stand
# ==============================================================================

class TestFundamentalBlocks:
    def test_cash_runway_danger_blocks(self, aggregator):
        result = run_signal(
            aggregator, make_thesis(),
            make_valuation(20.0, CashRunwayStatus.DANGER), make_weinstein(),
        )
        assert result.blocked is True
        assert "CASH_RUNWAY_DANGER" in result.blocked_reason

    def test_three_red_flags_block(self, aggregator):
        result = run_signal(
            aggregator, make_thesis(80.0, red_flags=3), make_valuation(), make_weinstein()
        )
        assert result.blocked is True
        assert "RED_FLAGS" in result.blocked_reason

    def test_healthy_fundamentals_not_blocked(self, aggregator):
        result = run_signal(
            aggregator, make_thesis(), make_valuation(), make_weinstein()
        )
        assert result.blocked is False


# ==============================================================================
# Signal strength classification
# ==============================================================================

class TestSignalStrength:
    @pytest.mark.parametrize(
        "confidence, expected",
        [
            (100.0, SignalStrength.STRONG_BUY),
            (80.0, SignalStrength.STRONG_BUY),
            (79.9, SignalStrength.BUY),
            (60.0, SignalStrength.BUY),
            (59.9, SignalStrength.WEAK_BUY),
            (40.0, SignalStrength.WEAK_BUY),
            (39.9, SignalStrength.NEUTRAL),
            (20.0, SignalStrength.NEUTRAL),
            (19.9, SignalStrength.AVOID),
            (0.0, SignalStrength.AVOID),
        ],
    )
    def test_classify_strength(self, aggregator, confidence, expected):
        assert aggregator._classify_strength(confidence) == expected


# ==============================================================================
# Serialization
# ==============================================================================

class TestSerialization:
    def test_to_dict_core_fields(self, aggregator):
        result = run_signal(
            aggregator, make_thesis(80.0), make_valuation(70.0), make_weinstein()
        )
        data = result.to_dict()
        assert data["ticker"] == "TEST"
        assert data["buy_confidence"] == pytest.approx(76.0)
        assert data["components"]["thesis_tracker"]["score"] == 80.0
        assert data["components"]["valuation_cash"]["score"] == 70.0
        assert isinstance(datetime.fromisoformat(data["calculated_at"]), datetime)

    def test_to_dict_handles_missing_prices(self, aggregator):
        result = run_signal(
            aggregator, make_thesis(), make_valuation(), make_weinstein()
        )
        data = result.to_dict()
        assert data["target_price"] is None
        assert data["stop_loss"] is None
        assert data["risk_reward_ratio"] is None
