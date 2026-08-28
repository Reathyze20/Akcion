"""
A sold position must leave the holdings view.

`record_trade` closes a position by setting `shares_count = 0`, not by deleting
the row — `avg_cost` and the ledger link have to survive, otherwise realized P/L
and the score calibration lose their anchor (see services/trade_ledger.py:202).

That is the right storage decision and the wrong display decision. Nothing in
the app filtered those rows out, so selling everything left the ticker sitting
in the table at 0 % weight, still counted in "15 pozic". These tests pin the
filter to the two endpoints that answer "what do I hold right now".
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.database.connection  # noqa: F401
import app.models  # noqa: F401
import app.models.trading  # noqa: F401

from app.database.connection import Base
from app.models.portfolio import BrokerType, Portfolio, Position
from app.routes.portfolio import get_portfolios, get_portfolio_summary
from app.services.currency import CurrencyService


@pytest.fixture
def db():
    """Real session on sqlite — a filter in a query cannot be tested on a mock."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine, tables=[Portfolio.__table__, Position.__table__]
    )
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def portfolio(db):
    p = Portfolio(owner="Tom", name="Hlavní", broker=BrokerType.T212,
                  cash_balance=0.0, monthly_contribution=0.0)
    db.add(p)
    db.flush()

    # Drží se: deset kusů za dvě stě.
    db.add(Position(portfolio_id=p.id, ticker="DRZIM", shares_count=10,
                    avg_cost=180.0, current_price=200.0, currency="USD"))
    # Prodáno: řádek zůstal kvůli historii, ale nikdo to nedrží.
    db.add(Position(portfolio_id=p.id, ticker="PRODANO", shares_count=0,
                    avg_cost=50.0, current_price=70.0, currency="USD"))
    db.commit()
    return p


@pytest.fixture(autouse=True)
def _fixed_rate(monkeypatch):
    """Kurzy sem nepatří — testuje se filtr, ne ČNB."""
    monkeypatch.setattr(CurrencyService, "get_rate_to_czk", classmethod(lambda cls, c: 1.0))


class TestClosedPositionsLeaveTheHoldingsView:

    def test_summary_lists_only_what_is_held(self, db, portfolio):
        out = get_portfolio_summary(portfolio_id=portfolio.id, db=db)
        tickers = [p.ticker for p in out["positions"]]

        assert tickers == ["DRZIM"]
        assert "PRODANO" not in tickers

    def test_position_count_does_not_include_sold(self, db, portfolio):
        [row] = get_portfolios(db=db)

        # Dvě řádky v databázi, jedna držená pozice.
        assert db.query(Position).count() == 2
        assert row["position_count"] == 1

    def test_row_survives_in_the_database(self, db, portfolio):
        """Filtr je jen zobrazení. Historie se mazat nesmí."""
        sold = db.query(Position).filter(Position.ticker == "PRODANO").one()

        assert sold.shares_count == 0
        assert sold.avg_cost == 50.0

    def test_selling_everything_empties_the_view(self, db, portfolio):
        held = db.query(Position).filter(Position.ticker == "DRZIM").one()
        held.shares_count = 0
        db.commit()

        out = get_portfolio_summary(portfolio_id=portfolio.id, db=db)

        assert out["positions"] == []
        # Prázdno, ne chyba — portfolio bez pozic je legitimní stav.
        assert out["total_market_value"] == 0.0
