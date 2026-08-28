"""
Keeping readings that used to be overwritten.

`yahoo_finance_cache` holds one row per ticker and rewrites it every refresh.
For companies SEC covers that costs nothing — XBRL gives real quarterly series.
For the four largest positions, which file nowhere EDGAR can see, it meant the
app could never say whether anything was getting better or worse.

Two properties make the series worth reading, and both are about refusing to
manufacture a trend: a row is written only when something actually changed, and
a year-on-year comparison needs an actual year between the two readings.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
import app.models.trading  # noqa: F401
from app.models.base import Base
from app.models.fundamental_snapshot import FundamentalSnapshot
from app.services.fundamental_history import (
    YOY_MAX,
    YOY_MIN,
    record_snapshot,
    year_on_year,
)

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[FundamentalSnapshot.__table__])
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def reading(**kw):
    base = dict(
        revenue_ttm=10_000_000.0, net_income_ttm=500_000.0,
        operating_margin=0.12, profit_margin=0.05,
        total_cash=8_000_000.0, total_debt=1_000_000.0,
        shares_outstanding=20_000_000.0, market_cap=45_000_000.0,
        currency="CAD",
    )
    base.update(kw)
    return base


# ==============================================================================
# A row means something changed
# ==============================================================================

def test_the_first_reading_is_always_kept(db):
    row = record_snapshot(db, "KUYAF", reading(), now=NOW)
    db.flush()

    assert row is not None
    assert db.query(FundamentalSnapshot).count() == 1


def test_an_identical_reading_is_not_written_again(db):
    """
    The provider moves these on the order of quarters. A nightly job writing
    unconditionally would pad the series with ninety identical rows and make a
    flat line out of not having looked.
    """
    record_snapshot(db, "KUYAF", reading(), now=NOW)
    db.flush()
    second = record_snapshot(db, "KUYAF", reading(), now=NOW + timedelta(days=1))
    db.flush()

    assert second is None
    assert db.query(FundamentalSnapshot).count() == 1


def test_a_changed_figure_is_written(db):
    record_snapshot(db, "KUYAF", reading(), now=NOW)
    db.flush()
    record_snapshot(
        db, "KUYAF", reading(revenue_ttm=12_000_000.0), now=NOW + timedelta(days=90)
    )
    db.flush()

    assert db.query(FundamentalSnapshot).count() == 2


def test_a_moving_market_cap_alone_is_not_a_change(db):
    """
    Price moves every day. Counting it would make every single run look like
    news and defeat the whole point of deduplicating.
    """
    record_snapshot(db, "KUYAF", reading(), now=NOW)
    db.flush()
    second = record_snapshot(
        db, "KUYAF", reading(market_cap=99_000_000.0), now=NOW + timedelta(days=1)
    )
    db.flush()

    assert second is None


def test_a_rounding_wobble_is_not_a_change(db):
    """The provider rounds differently between calls; that is not news."""
    record_snapshot(db, "KUYAF", reading(profit_margin=0.05), now=NOW)
    db.flush()
    second = record_snapshot(
        db, "KUYAF", reading(profit_margin=0.050000001), now=NOW + timedelta(days=1)
    )
    db.flush()

    assert second is None


def test_an_empty_reading_is_not_stored(db):
    """A row with nothing in it is not a reading, and would break the next diff."""
    assert record_snapshot(db, "KUYAF", {"market_cap": 1.0}, now=NOW) is None
    db.flush()
    assert db.query(FundamentalSnapshot).count() == 0


def test_two_listings_stay_two_series(db):
    """
    KUYA.V and KUYAF can report different currencies and different share
    counts. Merging them would turn a units change into a trend.
    """
    record_snapshot(db, "KUYAF", reading(currency="USD"), now=NOW)
    record_snapshot(db, "KUYA.V", reading(currency="CAD"), now=NOW)
    db.flush()

    assert db.query(FundamentalSnapshot).count() == 2


# ==============================================================================
# A year-on-year comparison needs a year
# ==============================================================================

def test_two_readings_a_fortnight_apart_are_not_a_year(db):
    """
    The mistake this refuses to make. Until roughly August 2027 this table
    cannot answer the question at all, and saying so is the honest output.
    """
    record_snapshot(db, "KUYAF", reading(revenue_ttm=10_000_000.0), now=NOW - timedelta(days=14))
    db.flush()
    record_snapshot(db, "KUYAF", reading(revenue_ttm=12_000_000.0), now=NOW)
    db.flush()

    assert year_on_year(db, "KUYAF", "revenue_ttm", now=NOW) is None


def test_a_year_apart_is_compared(db):
    record_snapshot(db, "KUYAF", reading(revenue_ttm=10_000_000.0), now=NOW - timedelta(days=365))
    db.flush()
    record_snapshot(db, "KUYAF", reading(revenue_ttm=12_000_000.0), now=NOW)
    db.flush()

    change = year_on_year(db, "KUYAF", "revenue_ttm", now=NOW)
    assert change is not None
    assert change.pct == pytest.approx(20.0)


def test_the_window_has_both_edges(db):
    """Wide enough for a job that missed a week, still about one year."""
    assert YOY_MIN < timedelta(days=365) < YOY_MAX

    for gap, expected in ((YOY_MIN - timedelta(days=1), None), (YOY_MAX + timedelta(days=1), None)):
        db.query(FundamentalSnapshot).delete()
        record_snapshot(db, "X", reading(revenue_ttm=1.0), now=NOW - gap)
        db.flush()
        record_snapshot(db, "X", reading(revenue_ttm=2.0), now=NOW)
        db.flush()
        assert year_on_year(db, "X", "revenue_ttm", now=NOW) is expected


def test_a_single_reading_compares_with_nothing(db):
    record_snapshot(db, "KUYAF", reading(), now=NOW)
    db.flush()
    assert year_on_year(db, "KUYAF", "revenue_ttm", now=NOW) is None


def test_an_untracked_field_is_a_programming_error_not_a_none(db):
    """
    Silently returning None for a typo would hide a broken caller behind the
    same answer as "not enough history yet".
    """
    with pytest.raises(ValueError):
        year_on_year(db, "KUYAF", "market_cap", now=NOW)


def test_the_change_carries_both_dates(db):
    """
    A finding you cannot date is one you cannot check — and here the dates are
    the measurement, because the gap between them is what makes it a year.
    """
    record_snapshot(db, "KUYAF", reading(total_cash=8_000_000.0), now=NOW - timedelta(days=360))
    db.flush()
    record_snapshot(db, "KUYAF", reading(total_cash=4_000_000.0), now=NOW)
    db.flush()

    change = year_on_year(db, "KUYAF", "total_cash", now=NOW)
    assert change.pct == pytest.approx(-50.0)
    assert change.older_at < change.newer_at
