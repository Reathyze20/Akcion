"""
Tests for the score journal.

The journal exists because `conviction_score_history` sat empty while the app
issued scores for months: three write paths recorded their scores and two did
not, and the two that did not were the ones in use. What is tested here is
therefore not "does it insert a row" but the two properties that make the
journal worth trusting later — that nothing gets in without being recorded,
and that nothing gets recorded twice.

The price assertions belong to the same idea from the other side. A baseline
price the app cannot stand behind is worse than no baseline at all, because
every return computed from it would carry the error silently.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Importing connection registers the before_flush hook on Session, which is
# the whole subject of half these tests.
import app.database.connection  # noqa: F401

# Relationships name classes across the model package and SQLAlchemy resolves
# them by name at first use, so every mapper has to be registered even though
# only two tables are created below. `trading` is not re-exported by
# `app.models`, which is why away_check.py imports it by hand too.
import app.models  # noqa: F401
import app.models.trading  # noqa: F401
from app.models.base import Base
from app.models.score_history import ConvictionScoreHistory
from app.models.stock import Stock
from app.services.score_journal import (
    SOURCE_MANUAL,
    SOURCE_UNATTRIBUTED,
    record_score,
    trusted_price,
)


@pytest.fixture
def db():
    """A real session on sqlite: the flush hook cannot be tested against a mock."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine, tables=[Stock.__table__, ConvictionScoreHistory.__table__]
    )
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def rows(db, ticker="TEST"):
    return (
        db.query(ConvictionScoreHistory)
        .filter(ConvictionScoreHistory.ticker == ticker)
        .all()
    )


def make_stock(db, ticker="TEST", score=5):
    """
    A stock already in the database, with the journal cleared afterwards.

    Creating a stock that has a score is itself a journaled event — the safety
    net sees it and writes a row, which is the behaviour asserted in
    `test_catches_a_new_stock_created_with_a_score`. Every other test wants a
    starting position, not that row, so setup is wiped before the test begins.
    """
    stock = Stock(ticker=ticker, conviction_score=score)
    db.add(stock)
    db.commit()

    db.query(ConvictionScoreHistory).delete()
    db.commit()
    return stock


# ==============================================================================
# The sanctioned path
# ==============================================================================

class TestRecordScore:
    def test_records_a_score_that_did_not_change(self, db):
        """
        A reaffirmed nine is a fresh prediction and has to be in the sample.

        Recording only changes would leave the calibration made of nothing but
        tickers whose score moves, which is a different population from the
        one the app actually advises on.
        """
        stock = make_stock(db, score=9)

        record_score(db, ticker="TEST", score=9, source=SOURCE_MANUAL, stock=stock)
        db.commit()

        assert len(rows(db)) == 1
        assert rows(db)[0].conviction_score == 9

    def test_upper_cases_the_ticker(self, db):
        record_score(db, ticker=" test ", score=7, source=SOURCE_MANUAL)
        db.commit()

        assert rows(db)[0].ticker == "TEST"

    def test_missing_price_is_null_never_zero(self, db):
        """
        Zero is a real price for a delisted shell and a catastrophic
        denominator. "We do not know" must not be spelled the same way.
        """
        record_score(db, ticker="TEST", score=6, source=SOURCE_MANUAL, price=None)
        db.commit()

        assert rows(db)[0].price_at_analysis is None

    def test_a_genuine_zero_price_is_kept(self, db):
        record_score(db, ticker="TEST", score=1, source=SOURCE_MANUAL, price=0)
        db.commit()

        assert rows(db)[0].price_at_analysis == Decimal("0")

    def test_unparseable_price_becomes_null(self, db):
        record_score(db, ticker="TEST", score=6, source=SOURCE_MANUAL, price="n/a")
        db.commit()

        assert rows(db)[0].price_at_analysis is None

    def test_no_score_is_not_a_claim(self, db):
        """An absent score is not a neutral 5 — it is nothing, and records nothing."""
        assert record_score(db, ticker="TEST", score=None, source=SOURCE_MANUAL) is None
        db.commit()

        assert rows(db) == []

    def test_no_ticker_records_nothing(self, db):
        assert record_score(db, ticker="  ", score=8, source=SOURCE_MANUAL) is None
        db.commit()

        assert db.query(ConvictionScoreHistory).count() == 0

    def test_stock_object_resolves_the_foreign_key(self, db):
        """
        Passing the object, not the id, so a stock created in the same
        transaction still gets its FK filled at flush time.
        """
        stock = Stock(ticker="TEST", conviction_score=4)
        db.add(stock)

        record_score(db, ticker="TEST", score=4, source=SOURCE_MANUAL, stock=stock)
        db.commit()

        assert rows(db)[0].stock_id == stock.id


# ==============================================================================
# The safety net
# ==============================================================================

class TestBeforeFlushNet:
    def test_catches_a_score_written_outside_record_score(self, db):
        """The failure this whole module exists to prevent."""
        stock = make_stock(db, score=5)

        stock.conviction_score = 8
        db.commit()

        assert len(rows(db)) == 1
        assert rows(db)[0].conviction_score == 8
        assert rows(db)[0].analysis_source == SOURCE_UNATTRIBUTED

    def test_catches_a_new_stock_created_with_a_score(self, db):
        db.add(Stock(ticker="TEST", conviction_score=7))
        db.commit()

        assert len(rows(db)) == 1
        assert rows(db)[0].analysis_source == SOURCE_UNATTRIBUTED
        assert rows(db)[0].conviction_score == 7

    def test_does_not_duplicate_what_record_score_already_wrote(self, db):
        """
        Both mechanisms see the same event; only one row may result, and it
        must be the attributed one.
        """
        stock = make_stock(db, score=5)

        stock.conviction_score = 8
        record_score(db, ticker="TEST", score=8, source=SOURCE_MANUAL, stock=stock)
        db.commit()

        assert len(rows(db)) == 1
        assert rows(db)[0].analysis_source == SOURCE_MANUAL

    def test_ignores_a_score_reassigned_to_the_same_value(self, db):
        """
        The hook cannot tell a reaffirmed thesis from an unrelated update that
        touched the field, so it stays out of it. Reaffirmations are the
        sanctioned path's job, where the caller knows an analysis ran.
        """
        stock = make_stock(db, score=6)

        stock.conviction_score = 6
        stock.company_name = "Something Else"
        db.commit()

        assert rows(db) == []

    def test_ignores_updates_that_do_not_touch_the_score(self, db):
        stock = make_stock(db, score=6)

        stock.company_name = "Renamed"
        db.commit()

        assert rows(db) == []

    def test_a_stock_with_no_score_records_nothing(self, db):
        db.add(Stock(ticker="TEST"))
        db.commit()

        assert rows(db) == []


# ==============================================================================
# Baseline prices
# ==============================================================================

class TestTrustedPrice:
    def _cache_returning(self, payload):
        cache = MagicMock()
        cache.return_value.get_stock_data.return_value = payload
        return cache

    def test_a_fresh_quote_is_used(self, db):
        cache = self._cache_returning({"current_price": 12.5, "is_stale": False})
        with patch("app.services.yahoo_cache.YahooFinanceCache", cache):
            assert trusted_price(db, "TEST") == Decimal("12.5")

    def test_a_stale_quote_is_refused(self, db):
        """
        `is_stale` means the refresh failed and the cache served what it had.
        Fine on screen beside its warning; not fine as the denominator of a
        return the app will later present as measured fact.
        """
        cache = self._cache_returning(
            {"current_price": 12.5, "is_stale": True, "stale_reason": "Yahoo selhalo"}
        )
        with patch("app.services.yahoo_cache.YahooFinanceCache", cache):
            assert trusted_price(db, "TEST") is None

    def test_a_broken_cache_does_not_break_the_scoring(self, db):
        """
        A missing baseline is recoverable from historical bars. A missing
        journal row is not, so the fetch must never be able to prevent one.
        """
        cache = MagicMock()
        cache.return_value.get_stock_data.side_effect = RuntimeError("network down")
        with patch("app.services.yahoo_cache.YahooFinanceCache", cache):
            assert trusted_price(db, "TEST") is None
