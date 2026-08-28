"""
The ladder as the portfolio actually sees it.

`test_zone_ladder.py` covers the arithmetic. What is covered here is the
assembly: which band row counts, whose currency the price is restated in,
whether a company held under two symbols becomes one row or two, and what a
proposal that nobody confirmed is allowed to unlock.

Every one of those has already gone wrong once in this codebase.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
import app.models.trading  # noqa: F401
from app.models.base import Base
from app.models.gomes import StockLifecycleModel
from app.models.portfolio import (
    BrokerType,
    InvestmentLog,
    Portfolio,
    Position,
)
from app.models.stock import Stock
from app.services.ladder_view import portfolio_ladder
from app.trading.gomes_logic import Band, Trigger

NOW = datetime(2026, 8, 23, 12, 0)
RATES = {"USD": 25.0, "CZK": 1.0, "EUR": 25.0, "CAD": 15.0}


def fx(currency: str) -> float:
    return RATES[currency.upper()]


@compiles(JSONB, "sqlite")
def _jsonb(type_, compiler, **kw):  # noqa: ARG001
    return "JSON"


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            Portfolio.__table__,
            Position.__table__,
            InvestmentLog.__table__,
            Stock.__table__,
            StockLifecycleModel.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()
    session.add(Portfolio(name="Test", owner="tomas", broker=BrokerType.DEGIRO))
    session.flush()
    try:
        yield session
    finally:
        session.close()


def hold(db, ticker, price, currency="USD", shares=100):
    db.add(Position(
        portfolio_id=1, ticker=ticker, shares_count=shares,
        avg_cost=1.0, current_price=price, currency=currency,
    ))


def band(db, ticker, low=3.25, high=15.50, source="GOMES", currency="USD"):
    db.add(Stock(
        ticker=ticker, source_key=source, green_line=low, red_line=high,
        line_currency=currency,
    ))


def quality(db, ticker, cylinders, *, confirmed=True, valid_days=60):
    db.add(StockLifecycleModel(
        ticker=ticker, phase="GOLD_MINE", is_investable=True,
        cylinders_count=cylinders,
        cylinders_confirmed_at=(NOW - timedelta(days=1)) if confirmed else None,
        cylinders_valid_until=NOW + timedelta(days=valid_days),
    ))


def only(db):
    rows = portfolio_ladder(db, fx_rate_to_czk=fx, now=NOW)
    assert len(rows) == 1
    return rows[0]


# ==============================================================================
# The band and its two prices
# ==============================================================================

def test_a_held_position_gets_a_band_and_two_limits(db):
    hold(db, "CXDO", 6.62)
    band(db, "CXDO")
    quality(db, "CXDO", 4)
    db.flush()

    row = only(db)
    assert row.reading.band is Band.PREPLACENO
    assert row.reading.buy_below == pytest.approx(5.61, abs=0.01)
    assert row.reading.sell_above == pytest.approx(6.56, abs=0.01)
    assert row.line_currency == "USD"


def test_the_limits_are_quoted_in_the_bands_currency_not_the_positions(db):
    """
    GKPRF's band is in dollars; the position trades in Canadian ones. The two
    orders have to be stated in the money the band is written in, or the owner
    places them at the wrong level.
    """
    hold(db, "GSI.V", 1.77, currency="CAD")
    band(db, "GKPRF", low=0.30, high=3.75)
    quality(db, "GKPRF", 5)
    db.flush()

    row = only(db)
    assert row.line_currency == "USD"
    # 1.77 CAD is 1.062 USD at these rates, which is almost exactly fair value
    # for five cylinders. Read as dollars it would look expensive.
    assert row.reading.rr_score == pytest.approx(5.0, abs=0.05)
    assert row.reading.band is Band.DRZET


# ==============================================================================
# One company, one row
# ==============================================================================

def test_a_company_held_under_two_symbols_is_one_row(db):
    """
    KUYA.V at the broker, KUYAF in every analysis. Two rows would be two
    different answers about one company — and the owner would have no way to
    tell which one to act on.
    """
    hold(db, "KUYA.V", 1.00, currency="CAD")
    hold(db, "KUYAF", 0.60, shares=50)
    band(db, "KUYAF", low=0.30, high=3.75)
    quality(db, "KUYAF", 6)
    db.flush()

    rows = portfolio_ladder(db, fx_rate_to_czk=fx, now=NOW)
    assert len(rows) == 1
    assert rows[0].reading.band is not Band.MIMO_METODIKU


def test_the_analysis_is_found_under_the_other_listing(db):
    """The position is Canadian, the band is filed under the US symbol."""
    hold(db, "IMP.V", 0.50, currency="CAD")
    band(db, "ITMSF", low=0.30, high=10.00)
    quality(db, "ITMSF", 5)
    db.flush()

    assert only(db).reading.band is not Band.MIMO_METODIKU


# ==============================================================================
# Two absences, and one that only looks like an absence
# ==============================================================================

def test_a_company_with_no_band_anywhere_says_exactly_that(db):
    hold(db, "DAIO", 3.00)
    quality(db, "DAIO", 3)
    db.flush()

    row = only(db)
    assert row.reading.band is Band.MIMO_METODIKU
    assert "nemám zelenou ani červenou" in row.reading.reason_cs


def test_a_band_from_another_source_is_named_rather_than_used(db):
    """
    Keeping the sources apart is what makes their agreement mean something, so
    a non-Gomes band is never scored as one. But saying "we have no band" when
    one exists sends the owner looking for data he already has.
    """
    hold(db, "KUYA.V", 1.50, currency="CAD")
    band(db, "KUYA.V", low=1.20, high=2.00, source="OTHER")
    quality(db, "KUYA.V", 5)
    db.flush()

    row = only(db)
    assert row.reading.band is Band.MIMO_METODIKU
    assert row.reading.buy_below is None            # not scored
    assert "zadané odjinud" in row.reading.reason_cs
    assert "OTHER" in row.reading.reason_cs


def test_an_unconfirmed_proposal_produces_no_band(db):
    """
    A proposal is not a permission anywhere, including here. Showing a band
    built on an unconfirmed number would put a limit price on screen that the
    Buy Guard would then refuse to act on — two parts of one app disagreeing.
    """
    hold(db, "CXDO", 6.62)
    band(db, "CXDO")
    quality(db, "CXDO", 8, confirmed=False)
    db.flush()

    row = only(db)
    assert row.reading.band is Band.NEZNAME
    assert row.reading.buy_below is None


def test_an_expired_confirmation_still_describes_the_position(db):
    """
    Expiry removes permission to buy, not the ability to see where a stock
    sits. The band still reads, and the row says the quality reading is out of
    date so nothing is silently trusted.
    """
    hold(db, "CXDO", 6.62)
    band(db, "CXDO")
    quality(db, "CXDO", 4, valid_days=-1)
    db.flush()

    row = only(db)
    assert row.reading.band is Band.PREPLACENO
    assert row.quality_expired is True


# ==============================================================================
# Order, and the second axis
# ==============================================================================

def test_the_cheapest_band_leads(db):
    """Ordering is information: it is where money would go if any were going."""
    for ticker, price, cyl in (("AAA", 14.0, 4), ("BBB", 3.20, 4), ("CCC", 6.62, 7)):
        hold(db, ticker, price)
        band(db, ticker)
        quality(db, ticker, cyl)
    db.flush()

    rows = portfolio_ladder(db, fx_rate_to_czk=fx, now=NOW)
    assert [r.reading.band for r in rows] == [
        Band.POD_ZELENOU, Band.NAKUP, Band.PREPLACENO
    ]


def test_the_three_point_rule_stays_silent_without_an_entry_score(db):
    """Every position opened before that column existed — which today is all of them."""
    hold(db, "CXDO", 6.62)
    band(db, "CXDO")
    quality(db, "CXDO", 4)
    db.flush()

    row = only(db)
    assert row.trigger is Trigger.ZADNY
    assert "vstupu neznám" in row.trigger_reason


def test_a_recorded_entry_score_arms_the_three_point_rule(db):
    """
    CXDO bought when it scored 8.8 and now scoring 5.45 has moved 3.3 points
    against the position — canon §5 says take profit, and it says so even
    though the band itself is a perfectly ordinary one.
    """
    from app.models.portfolio import InvestmentLogType

    hold(db, "CXDO", 6.62)
    band(db, "CXDO")
    quality(db, "CXDO", 7)
    db.add(InvestmentLog(
        portfolio_id=1, log_type=InvestmentLogType.BUY, ticker="CXDO",
        shares=100, price=4.00, rr_score_at_entry=8.8,
    ))
    db.flush()

    row = only(db)
    assert row.reading.band is Band.NAKUP        # still cheap for its quality
    assert row.trigger is Trigger.VYBRAT_ZISK    # and still moved 3 points
