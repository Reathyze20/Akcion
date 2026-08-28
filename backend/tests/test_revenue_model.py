"""
Analytikovy modely tržeb: součet po období a porovnání s realitou.

Tři věci se tu hlídají, protože přesně tyhle chyby by v této appce znamenaly
vymyšlené číslo místo přiznané mezery:
  1. Smíchat měny do jednoho součtu je tichá chyba — musí vyhodit, ne mlčet.
  2. Řádek bez čísla (ani amount, ani kusy×cena) se nesmí vůbec uložit.
  3. Chybějící skutečná tržba dá pojmenovanou mezeru, ne None bez vysvětlení.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.revenue_model import AnalystRevenueModel, AnalystRevenueModelLine
# SWOTAnalysis.watchlist references "ActiveWatchlist" by string; the mapper
# registry only resolves it once that module has been imported somewhere in
# the process. Isolated runs of this file need the import explicitly.
from app.models.trading import ActiveWatchlist  # noqa: F401
from app.services import revenue_model as rm
from app.services.sec_fundamentals import Fundamentals, Point, Series


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[AnalystRevenueModel.__table__, AnalystRevenueModelLine.__table__],
    )
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def make_model(db, **kwargs) -> AnalystRevenueModel:
    defaults = dict(ticker="OPTX", model_name="OPTX Product Revenue", source_name="Mark Gomes")
    defaults.update(kwargs)
    model = AnalystRevenueModel(**defaults)
    db.add(model)
    db.commit()
    db.refresh(model)
    return model


def add_line(db, model, **kwargs) -> AnalystRevenueModelLine:
    defaults = dict(category="Medical", item_name="Test", period_label="2025", currency="USD")
    defaults.update(kwargs)
    line = AnalystRevenueModelLine(model_id=model.id, **defaults)
    db.add(line)
    db.commit()
    return line


# ==============================================================================
# 1. Uložení řádku
# ==============================================================================

class TestARowWithoutANumberCannotBeSaved:
    def test_neither_amount_nor_unit_math_is_rejected(self, db):
        model = make_model(db)
        line = AnalystRevenueModelLine(
            model_id=model.id, category="Medical", item_name="Bez čísla", period_label="2025"
        )
        db.add(line)
        with pytest.raises(IntegrityError):
            db.commit()

    def test_amount_alone_is_enough(self, db):
        model = make_model(db)
        add_line(db, model, amount=1000)  # no raise

    def test_quantity_times_price_is_enough(self, db):
        model = make_model(db)
        add_line(db, model, quantity=10, price_per_unit=5)  # no raise

    def test_unknown_confidence_value_is_rejected(self, db):
        model = make_model(db)
        line = AnalystRevenueModelLine(
            model_id=model.id, category="Medical", item_name="X", period_label="2025",
            amount=100, confidence="MAYBE",
        )
        db.add(line)
        with pytest.raises(IntegrityError):
            db.commit()


# ==============================================================================
# 2. period_totals
# ==============================================================================

class TestPeriodTotals:
    def test_sums_amount_lines(self, db):
        model = make_model(db)
        add_line(db, model, period_label="2025", amount=100)
        add_line(db, model, period_label="2025", amount=200)
        totals = rm.period_totals(model)
        assert len(totals) == 1
        assert totals[0].total == 300

    def test_sums_unit_math_lines(self, db):
        model = make_model(db)
        add_line(db, model, period_label="2025", quantity=1000, price_per_unit=65)
        totals = rm.period_totals(model)
        assert totals[0].total == 65_000

    def test_keeps_periods_in_first_seen_order(self, db):
        model = make_model(db)
        add_line(db, model, period_label="2027", amount=1)
        add_line(db, model, period_label="2025", amount=1)
        add_line(db, model, period_label="2026", amount=1)
        totals = rm.period_totals(model)
        assert [t.period_label for t in totals] == ["2027", "2025", "2026"]

    def test_mixed_currencies_in_one_period_raises(self, db):
        model = make_model(db)
        add_line(db, model, period_label="2025", amount=100, currency="USD")
        add_line(db, model, period_label="2025", amount=100, currency="CAD")
        with pytest.raises(ValueError, match="míchá měny"):
            rm.period_totals(model)

    def test_unrated_lines_are_counted_honestly(self, db):
        model = make_model(db)
        add_line(db, model, period_label="2025", amount=100, confidence="LOCKED")
        add_line(db, model, period_label="2025", amount=100, confidence=None)
        add_line(db, model, period_label="2025", amount=100, confidence="ESTIMATE")
        totals = rm.period_totals(model)
        assert totals[0].unrated_lines == 1
        assert totals[0].line_count == 3


# ==============================================================================
# 3. compare_to_actual
# ==============================================================================

def _fundamentals_with_revenue(annual=(), quarterly=()) -> Fundamentals:
    f = Fundamentals(ticker="OPTX", cik="0000000000")
    f.series["revenue"] = Series(
        key="revenue", label_cs="Tržby", unit="USD",
        tag="Revenues", annual=list(annual), quarterly=list(quarterly),
    )
    return f


class TestCompareToActual:
    def test_no_fundamentals_gives_a_named_gap_not_none_silently(self, db):
        model = make_model(db)
        add_line(db, model, period_label="2025", amount=100)
        [cmp] = rm.compare_to_actual(model, None)
        assert cmp.actual is None
        assert cmp.gap_cs is not None
        assert "SEC" in cmp.gap_cs

    def test_matches_annual_point_by_fiscal_year(self, db):
        model = make_model(db)
        add_line(db, model, period_label="2025", amount=28_000_000)
        fundamentals = _fundamentals_with_revenue(
            annual=[Point(end=date(2025, 12, 31), value=27_500_000, form="10-K", fiscal_year=2025)]
        )
        [cmp] = rm.compare_to_actual(model, fundamentals)
        assert cmp.actual == 27_500_000
        assert cmp.gap_cs is None
        # model was 500k over actual: (28M - 27.5M) / 27.5M
        assert cmp.variance_pct == pytest.approx((28_000_000 - 27_500_000) / 27_500_000 * 100)

    def test_year_with_no_matching_annual_point_is_a_named_gap(self, db):
        model = make_model(db)
        add_line(db, model, period_label="2028", amount=100)
        fundamentals = _fundamentals_with_revenue(
            annual=[Point(end=date(2025, 12, 31), value=1, form="10-K", fiscal_year=2025)]
        )
        [cmp] = rm.compare_to_actual(model, fundamentals)
        assert cmp.actual is None
        assert "2028" in cmp.gap_cs

    def test_matches_quarterly_point_by_exact_end_date(self, db):
        model = make_model(db, ticker="TPCS", model_name="TPCS Backlog")
        add_line(db, model, period_label="6/30/24", amount=8_000_000)
        fundamentals = _fundamentals_with_revenue(
            quarterly=[Point(end=date(2024, 6, 30), value=7_960_000, form="10-Q")]
        )
        [cmp] = rm.compare_to_actual(model, fundamentals)
        assert cmp.actual == 7_960_000
        assert cmp.gap_cs is None

    def test_two_digit_year_in_quarter_date_is_expanded_to_2000s(self, db):
        model = make_model(db, ticker="TPCS")
        add_line(db, model, period_label="9/30/24", amount=1)
        fundamentals = _fundamentals_with_revenue(
            quarterly=[Point(end=date(2024, 9, 30), value=2, form="10-Q")]
        )
        [cmp] = rm.compare_to_actual(model, fundamentals)
        assert cmp.actual == 2

    def test_unparseable_period_label_is_a_named_gap_not_a_crash(self, db):
        model = make_model(db)
        add_line(db, model, period_label="Q-whatever", amount=1)
        fundamentals = _fundamentals_with_revenue(annual=[])
        [cmp] = rm.compare_to_actual(model, fundamentals)
        assert cmp.actual is None
        assert cmp.gap_cs is not None

    def test_actual_exceeding_model_gives_negative_variance(self, db):
        model = make_model(db)
        add_line(db, model, period_label="2025", amount=50)
        fundamentals = _fundamentals_with_revenue(
            annual=[Point(end=date(2025, 12, 31), value=100, form="10-K", fiscal_year=2025)]
        )
        [cmp] = rm.compare_to_actual(model, fundamentals)
        assert cmp.variance_pct == pytest.approx(-50.0)
