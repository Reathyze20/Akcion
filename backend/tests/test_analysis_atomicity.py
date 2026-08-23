"""
Tests that a failed analysis leaves the database alone.

The failure this guards against is the worst kind available: the UI said
"analýza selhala" while the conviction score in the database had already
changed — and without the history row that would have recorded why. You would
have been looking at a new number with no explanation attached to it, believing
nothing had happened.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.schemas.gomes import (
    DeepDueDiligenceResponse,
    DeepDueDiligenceResult,
    PriceTargetsSchema,
)
from app.services.gomes_deep_dd import GomesDeepDueDiligenceService

# SQLAlchemy resolves relationship targets by name at first instantiation, and
# ConvictionScoreHistory reaches ActiveWatchlist that way. Importing the module
# registers it; without this the mapper raises KeyError before the code under
# test runs.
import app.models.trading  # noqa: F401,E402


def _result(*, score: int = 7, current_price: float | None = 4.56):
    data = DeepDueDiligenceResult(
        ticker="TPCS",
        company_name="TechPrecision",
        conviction_score=score,
        thesis_status="STABLE",
        inflection_point_status="ACTIVE",
        upside_potential="200%",
        risk_level="MEDIUM",
        action_signal="BUY",
        kelly_criterion_hint=5.0,
        price_targets=PriceTargetsSchema(),
        green_line=3.25,
        red_line=14.00,
        current_price=current_price,
    )
    return DeepDueDiligenceResponse(
        analysis_text="Analýza.",
        data=data,
        thesis_drift="STABLE",
        source_length=1234,
    )


def _service_with_existing_stock(old_score: int = 3):
    """A service whose DB already holds TPCS at `old_score`."""
    stock = MagicMock()
    stock.id = 1
    stock.ticker = "TPCS"
    stock.conviction_score = old_score

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = stock

    with patch("app.services.gomes_deep_dd.Settings"):
        service = GomesDeepDueDiligenceService(db)
    return service, db, stock


# ==============================================================================
# The schema carries what the writer reads
# ==============================================================================

class TestSchemaCarriesCurrentPrice:
    def test_current_price_is_a_field(self):
        """
        It was parsed out of the model's answer from the beginning and then
        dropped, because there was no field to put it in — while the writer
        read `data.current_price` regardless.
        """
        assert "current_price" in DeepDueDiligenceResult.model_fields

    def test_grey_line_is_a_field(self):
        """Parsed and discarded the same way, though the Stock model has it."""
        assert "grey_line" in DeepDueDiligenceResult.model_fields

    def test_reading_current_price_does_not_raise(self):
        assert _result().data.current_price == 4.56

    def test_absent_current_price_is_none_not_an_error(self):
        assert _result(current_price=None).data.current_price is None


# ==============================================================================
# All of it lands, or none of it
# ==============================================================================

class TestWriteIsAtomic:
    @pytest.mark.asyncio
    async def test_a_failure_rolls_back(self):
        """
        Nothing may be committed before the whole analysis has been written.
        """
        service, db, _ = _service_with_existing_stock(old_score=3)
        db.add.side_effect = RuntimeError("boom while saving score history")

        with pytest.raises(RuntimeError):
            await service.update_stock_from_analysis(_result(score=9))

        db.rollback.assert_called_once()
        db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_success_commits_exactly_once(self):
        """
        Two commits with a fragile line between them was the whole defect. The
        first one is now a flush, which is all the stock id ever needed.
        """
        service, db, _ = _service_with_existing_stock(old_score=3)

        await service.update_stock_from_analysis(_result(score=9))

        assert db.commit.call_count == 1
        assert db.flush.call_count == 1
        db.rollback.assert_not_called()

    @pytest.mark.asyncio
    async def test_the_score_still_gets_written_on_success(self):
        service, db, stock = _service_with_existing_stock(old_score=3)

        await service.update_stock_from_analysis(_result(score=9))

        assert stock.conviction_score == 9
