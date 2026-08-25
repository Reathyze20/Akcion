"""
Persisting the Breakout Investors watchlist: the target, the baseline, the diff.

The network is stubbed. What is exercised here is what the app does with what
comes back, and the three refusals that keep an absent number from becoming a
confident one:

  * no quote -> no target (not zero, not the last one we had),
  * the first read is a baseline, not twenty-eight pieces of news,
  * a source that could not be reached still records the attempt, so a poll
    interval survives an outage.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  — SQLAlchemy needs every mapper
import app.models.trading  # noqa: F401
from app.models.base import Base
from app.models.breakout import (
    BreakoutPollState,
    BreakoutWatchChange,
    BreakoutWatchEntry,
)
from app.models.portfolio import BrokerType, Portfolio, Position
from app.models.stock import Stock
from app.services import breakout_sync
from app.services.breakout_sync import (
    RELATION_OWNED,
    RELATION_WATCHED,
    STATUS_SYNCED,
    STATUS_TOO_SOON,
    STATUS_UNAVAILABLE,
    our_symbols,
    sync_watchlist,
)
from app.services.breakout_watchlist import (
    WatchlistEntry,
    WatchlistUnavailable,
    implied_target,
)

NOW = datetime(2026, 8, 23, 18, 0, tzinfo=timezone.utc)

TABLES = [
    BreakoutWatchEntry.__table__,
    BreakoutWatchChange.__table__,
    BreakoutPollState.__table__,
    Stock.__table__,
    Portfolio.__table__,
    Position.__table__,
]


def naive(moment):
    """
    The same instant without a zone.

    SQLite has no TIMESTAMPTZ and hands back what it stored, zone dropped.
    Postgres — the only database this app actually runs on — keeps it. The
    comparison is stripped here rather than the code being changed to match a
    test harness.
    """
    return None if moment is None else moment.replace(tzinfo=None)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=TABLES)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def entry(symbol: str, endorsements: int, upside: float | None) -> WatchlistEntry:
    return WatchlistEntry(
        symbol=symbol,
        company_name=f"{symbol} Inc",
        endorsements=endorsements,
        upside_ratio=upside,
        added_at=None,
    )


def stub_source(monkeypatch, entries, quotes):
    """Replace the two network calls with fixed answers."""
    monkeypatch.setattr(
        breakout_sync, "fetch_watchlist", lambda *, session=None: list(entries)
    )
    monkeypatch.setattr(
        breakout_sync, "fetch_quotes", lambda symbols, *, session=None: dict(quotes)
    )


# ==============================================================================
# The target price
# ==============================================================================

class TestImpliedTarget:
    def test_reconstructs_a_round_target(self):
        # ADCOF: +233,33 % on $0.09 is a $0.30 target — theirs, not ours.
        assert implied_target(0.09, 2.3333333333333335) == pytest.approx(0.30)

    def test_no_price_no_target(self):
        assert implied_target(None, 1.5) is None

    def test_zero_price_is_not_a_price(self):
        # Their quote endpoint answers 0 for fields it has no data for. A zero
        # multiplied by anything is a target of zero — a sell signal invented
        # out of a missing quote.
        assert implied_target(0.0, 1.5) is None
        assert implied_target(-1.0, 1.5) is None

    def test_no_upside_no_target(self):
        assert implied_target(10.0, None) is None

    def test_negative_upside_still_gives_a_target(self):
        # They can expect a fall. That is a real number, not a missing one.
        assert implied_target(10.0, -0.4) == pytest.approx(6.0)


# ==============================================================================
# The first read
# ==============================================================================

class TestFirstRead:
    def test_baseline_writes_rows_but_no_changes(self, db, monkeypatch):
        stub_source(
            monkeypatch,
            [entry("AEHR", 5, 0.064), entry("WATT", 5, 1.328)],
            {"AEHR": 101.73, "WATT": 12.63},
        )

        result = sync_watchlist(db, force=True, now=NOW)

        assert result.status == STATUS_SYNCED
        assert result.entries_read == 2
        assert result.changes == []
        assert db.query(BreakoutWatchChange).count() == 0
        assert db.query(BreakoutWatchEntry).count() == 2

    def test_baseline_stores_the_target(self, db, monkeypatch):
        stub_source(monkeypatch, [entry("WATT", 5, 1.328)], {"WATT": 12.63})
        sync_watchlist(db, force=True, now=NOW)

        row = db.query(BreakoutWatchEntry).one()
        assert float(row.price_at_read) == pytest.approx(12.63)
        assert float(row.implied_target) == pytest.approx(29.40, abs=0.01)
        assert naive(row.first_seen_at) == naive(NOW)

    def test_missing_quote_leaves_no_target(self, db, monkeypatch):
        stub_source(monkeypatch, [entry("AEHR", 5, 0.064)], {})
        sync_watchlist(db, force=True, now=NOW)

        row = db.query(BreakoutWatchEntry).one()
        assert row.price_at_read is None
        assert row.implied_target is None
        # The upside is still theirs and still published — only the price is
        # missing, and only the target depends on it.
        assert float(row.upside_ratio) == pytest.approx(0.064)


# ==============================================================================
# The second read
# ==============================================================================

class TestChanges:
    def _baseline(self, db, monkeypatch):
        stub_source(
            monkeypatch,
            [entry("AEHR", 5, 0.064), entry("WATT", 5, 1.328)],
            {"AEHR": 101.73, "WATT": 12.63},
        )
        sync_watchlist(db, force=True, now=NOW)
        db.flush()

    def test_conviction_move_is_recorded(self, db, monkeypatch):
        self._baseline(db, monkeypatch)
        stub_source(
            monkeypatch,
            [entry("AEHR", 7, 0.064), entry("WATT", 5, 1.328)],
            {"AEHR": 101.73, "WATT": 12.63},
        )

        result = sync_watchlist(db, force=True, now=NOW + timedelta(days=1))

        kinds = {(c.symbol, c.kind) for c in result.changes}
        assert ("AEHR", "ENDORSEMENTS") in kinds
        row = db.query(BreakoutWatchChange).filter_by(kind="ENDORSEMENTS").one()
        assert float(row.before_value) == 5
        assert float(row.after_value) == 7
        assert row.notified_at is None  # nothing has been sent yet

    def test_removed_name_leaves_the_snapshot(self, db, monkeypatch):
        self._baseline(db, monkeypatch)
        stub_source(monkeypatch, [entry("AEHR", 5, 0.064)], {"AEHR": 101.73})

        result = sync_watchlist(db, force=True, now=NOW + timedelta(days=1))
        db.flush()

        assert [c.kind for c in result.changes] == ["REMOVED"]
        # The snapshot must not keep showing a target the group no longer backs.
        assert {r.symbol for r in db.query(BreakoutWatchEntry).all()} == {"AEHR"}
        assert db.query(BreakoutWatchChange).filter_by(kind="REMOVED").count() == 1

    def test_target_follows_the_price(self, db, monkeypatch):
        self._baseline(db, monkeypatch)
        stub_source(monkeypatch, [entry("WATT", 5, 1.328)], {"WATT": 20.00})

        sync_watchlist(db, force=True, now=NOW + timedelta(days=1))
        row = db.query(BreakoutWatchEntry).filter_by(symbol="WATT").one()
        assert float(row.implied_target) == pytest.approx(46.56, abs=0.01)


# ==============================================================================
# Reaching the source at all
# ==============================================================================

class TestPolling:
    def test_too_soon_does_not_touch_the_network(self, db, monkeypatch):
        state = BreakoutPollState(last_attempt_at=NOW - timedelta(hours=2))
        db.add(state)
        db.flush()

        def explode(*args, **kwargs):
            raise AssertionError("must not read the source")

        monkeypatch.setattr(breakout_sync, "fetch_watchlist", explode)

        result = sync_watchlist(db, now=NOW)
        assert result.status == STATUS_TOO_SOON

    def test_outage_still_records_the_attempt(self, db, monkeypatch):
        def unavailable(*args, **kwargs):
            raise WatchlistUnavailable("connection refused")

        monkeypatch.setattr(breakout_sync, "fetch_watchlist", unavailable)

        result = sync_watchlist(db, force=True, now=NOW)

        assert result.status == STATUS_UNAVAILABLE
        state = db.query(BreakoutPollState).one()
        # last_attempt_at, not last_success_at: a source that is down must not
        # be retried faster than one that is up.
        assert naive(state.last_attempt_at) == naive(NOW)
        assert state.last_success_at is None
        assert "connection refused" in state.last_error

    def test_outage_does_not_wipe_the_snapshot(self, db, monkeypatch):
        stub_source(monkeypatch, [entry("AEHR", 5, 0.064)], {"AEHR": 101.73})
        sync_watchlist(db, force=True, now=NOW)
        db.flush()

        def unavailable(*args, **kwargs):
            raise WatchlistUnavailable("timeout")

        monkeypatch.setattr(breakout_sync, "fetch_watchlist", unavailable)
        sync_watchlist(db, force=True, now=NOW + timedelta(days=1))

        assert db.query(BreakoutWatchEntry).count() == 1

    def test_quote_outage_persists_nothing(self, db, monkeypatch):
        stub_source(monkeypatch, [entry("AEHR", 5, 0.064)], {"AEHR": 101.73})
        sync_watchlist(db, force=True, now=NOW)
        db.flush()

        monkeypatch.setattr(
            breakout_sync,
            "fetch_watchlist",
            lambda *, session=None: [entry("AEHR", 9, 0.064)],
        )

        def no_quotes(symbols, *, session=None):
            raise WatchlistUnavailable("quote request failed")

        monkeypatch.setattr(breakout_sync, "fetch_quotes", no_quotes)

        result = sync_watchlist(db, force=True, now=NOW + timedelta(days=1))

        # The pair is one read. Half of it is not stored, so the endorsement
        # move is not recorded as seen — the next run picks it up whole.
        assert result.status == STATUS_UNAVAILABLE
        assert db.query(BreakoutWatchEntry).one().endorsements == 5
        assert db.query(BreakoutWatchChange).count() == 0


# ==============================================================================
# Which of their names are ours
# ==============================================================================

class TestOurSymbols:
    def test_owned_outranks_watched(self, db):
        portfolio = Portfolio(name="Test", broker=BrokerType.T212)
        db.add(portfolio)
        db.flush()
        db.add(Stock(ticker="AEHR", company_name="Aehr"))
        db.add(Stock(ticker="WATT", company_name="Energous"))
        db.add(
            Position(portfolio_id=portfolio.id, ticker="AEHR", shares_count=10)
        )
        db.flush()

        relations = our_symbols(db)
        assert relations["AEHR"] == RELATION_OWNED
        assert relations["WATT"] == RELATION_WATCHED

    def test_a_name_we_do_not_track_is_absent(self, db):
        db.add(Stock(ticker="AEHR", company_name="Aehr"))
        db.flush()
        assert "DMIFF" not in our_symbols(db)

    def test_a_canadian_listing_counts_as_owning_the_otc_symbol(self, db):
        """
        The defect this closes: the position is KUYA.V, their list says KUYAF.

        Exact matching called a name we hold "sledujeme", and the card's whole
        point is which of their names are ours.
        """
        portfolio = Portfolio(name="Test", broker=BrokerType.T212)
        db.add(portfolio)
        db.flush()
        db.add(
            Position(portfolio_id=portfolio.id, ticker="KUYA.V", shares_count=100)
        )
        db.flush()

        relations = our_symbols(db)
        assert relations["KUYAF"] == RELATION_OWNED
        assert relations["KUYA.V"] == RELATION_OWNED

    def test_owning_one_listing_is_not_downgraded_by_watching_another(self, db):
        """
        A `stocks` row under the OTC symbol must not turn OWNED back into
        WATCHED. The two tables are read in sequence, so without the guard the
        order of reads would decide what the card says.
        """
        portfolio = Portfolio(name="Test", broker=BrokerType.T212)
        db.add(portfolio)
        db.flush()
        db.add(Stock(ticker="KUYAF", company_name="Kuya Silver Corporation"))
        db.add(
            Position(portfolio_id=portfolio.id, ticker="KUYA.V", shares_count=100)
        )
        db.flush()

        assert our_symbols(db)["KUYAF"] == RELATION_OWNED
