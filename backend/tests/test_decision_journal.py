"""
The decision journal — what the engine decided, not just what a model scored.

Why these tests exist
---------------------
`conviction_score_history` recorded a model's 0-10 opinion and nothing about
the decision built on it: no R/R score, no deserved level, no cylinders, no
band, no market alert. Calibration matures on 2026-09-22 and fully in August
2027, and it would have arrived able to answer "were the nines better than the
fives?" and unable to answer "did the band engine work?".

The same hole on the other side: `evaluate_buy_guard` returned `(False, reason)`
and every caller discarded it, so the app kept a record of every position it
opened and none of the ones it refused to open. A rule that only shows its
successes cannot be told apart from one that quietly costs money.

None of this is reconstructable after the fact — the journal starts on
2026-08-23 because nothing before it was written down. So what is asserted here
is not "a row appears" but the three properties that make the record worth
having later: the decision is stored beside the score, an absent input stays
absent instead of becoming a number, and a refusal repeated daily does not bury
the signal in duplicates.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

# Registers the before_flush hook; half the journal's guarantees live there.
import app.database.connection  # noqa: F401
import app.models  # noqa: F401
import app.models.trading  # noqa: F401
from app.models.base import Base
from app.models.refused_buy import RefusedBuy
from app.models.score_history import ConvictionScoreHistory
from app.models.stock import Stock
from app.services.daily_actions import Refusal
from app.services.refused_buys import collector, record_many, record_refusal
from app.services.score_journal import SOURCE_MANUAL, record_score
from app.trading.gomes_logic import GomesGatekeeper, LifecyclePhase, MarketAlert

Gate = GomesGatekeeper.BuyGate


@pytest.fixture
def db():
    """A real sqlite session — the de-duplication rule cannot be tested on a mock."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            Stock.__table__,
            ConvictionScoreHistory.__table__,
            RefusedBuy.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


# ==============================================================================
# The journal records the decision, not only the score
# ==============================================================================

def test_the_decision_is_stored_beside_the_score(db):
    """
    The whole point of the migration. CXDO at 6.62 against 3.25/15.50 scores
    5.45 (canon 4a); with 4 cylinders it deserves 6.0, so it is expensive for
    its quality. A year from now that sentence has to be reconstructable from
    the row alone.
    """
    record_score(
        db, ticker="cxdo", score=7, source=SOURCE_MANUAL,
        price=6.62, rr_score=5.45, deserved_score=6.0, cylinders=4,
        green_line=3.25, red_line=15.50, line_currency="USD",
        band="PREPLACENO", market_alert="GREEN", source_key="GOMES",
    )
    db.flush()

    row = db.query(ConvictionScoreHistory).one()
    assert row.ticker == "CXDO"                    # normalized, never split by spelling
    assert row.conviction_score == 7
    assert row.rr_score == Decimal("5.45")
    assert row.deserved_score == Decimal("6.0")
    assert row.cylinders == 4
    assert row.green_line == Decimal("3.25")
    assert row.red_line == Decimal("15.50")
    assert row.line_currency == "USD"
    assert row.band == "PREPLACENO"
    assert row.market_alert == "GREEN"
    assert row.source_key == "GOMES"


def test_unknown_cylinders_stay_null_rather_than_becoming_zero(db):
    """
    A row with no cylinders is the record of a day when no buy could have been
    authorised (the guard refuses on `cylinders is None`). Storing 0 would
    claim the company was measured and found dead, which is a different fact.
    """
    record_score(db, ticker="RDCM", score=5, source=SOURCE_MANUAL, cylinders=None)
    db.flush()

    row = db.query(ConvictionScoreHistory).one()
    assert row.cylinders is None
    assert row.deserved_score is None


def test_an_rr_score_of_zero_survives(db):
    """
    Zero is a real R/R score — it means the price is at or above the Red Line,
    i.e. fully valued. It must not be collapsed into "unknown" the way an
    unparseable value is.
    """
    record_score(db, ticker="AEHR", score=3, source=SOURCE_MANUAL, rr_score=0.0)
    db.flush()

    assert db.query(ConvictionScoreHistory).one().rr_score == Decimal("0")


def test_a_caller_that_knows_nothing_extra_still_journals(db):
    """The decision block is optional; the old two-argument call must keep working."""
    record_score(db, ticker="INFU", score=6, source=SOURCE_MANUAL)
    db.flush()

    row = db.query(ConvictionScoreHistory).one()
    assert row.conviction_score == 6
    assert row.rr_score is None and row.band is None


# ==============================================================================
# The Buy Guard names which gate refused
# ==============================================================================

def _guard(**kw):
    base = dict(
        market_alert=MarketAlert.GREEN, rr_score=8.0, deserved_score=5.0,
        cylinders=5, lifecycle_stage=LifecyclePhase.GOLD_MINE,
    )
    base.update(kw)
    return GomesGatekeeper.check_buy_guard(**base)


def test_every_refusal_path_has_its_own_code():
    """
    Grouping a year of refusals by cause has to be a GROUP BY, not a regex over
    prose someone later rewords. Each gate therefore gets a distinct code, and
    the order matters: the first failure is the one recorded, so a stock
    refused for an unset semafor is never filed as "too expensive".
    """
    assert _guard(market_alert="NONSENSE")[1] is Gate.ALERT_UNKNOWN
    assert _guard(market_alert=MarketAlert.YELLOW)[1] is Gate.MARKET_NOT_GREEN
    assert _guard(cylinders=None)[1] is Gate.CYLINDERS_UNKNOWN
    assert _guard(cylinders=0)[1] is Gate.CYLINDERS_UNKNOWN
    assert _guard(lifecycle_stage=LifecyclePhase.WAIT_TIME)[1] is Gate.WAIT_TIME
    assert _guard(rr_score=None)[1] is Gate.SCORE_MISSING
    assert _guard(deserved_score=None)[1] is Gate.SCORE_MISSING
    assert _guard(rr_score=4.0)[1] is Gate.NOT_CHEAP_ENOUGH


def test_a_passing_buy_says_so_explicitly():
    allowed, gate, _reason = _guard()
    assert allowed is True
    assert gate is Gate.PASSED


def test_the_two_value_form_still_answers_the_same_way():
    """The verdict path and the action engine consume `(bool, str)`; that contract holds."""
    allowed, reason = GomesGatekeeper.evaluate_buy_guard(
        market_alert=MarketAlert.YELLOW, rr_score=8.0, deserved_score=5.0,
        cylinders=5, lifecycle_stage=None,
    )
    assert allowed is False
    assert "GREEN" in reason


# ==============================================================================
# Refusals are recorded, once
# ==============================================================================

def _refusal(ticker="TPCS", gate=Gate.MARKET_NOT_GREEN, **kw):
    base = dict(
        ticker=ticker, failed_gate=gate.value, reason="Market Alert is YELLOW",
        source_key="GOMES", price=4.56, green_line=3.25, red_line=14.0,
        rr_score=7.68, deserved_score=None, cylinders=None,
        lifecycle_phase="GOLD_MINE", market_alert="YELLOW",
    )
    base.update(kw)
    return Refusal(**base)


def test_a_refusal_is_recorded_with_the_state_it_was_computed_from(db):
    record_refusal(db, _refusal(), on_day=date(2026, 8, 23))
    db.flush()

    row = db.query(RefusedBuy).one()
    assert row.ticker == "TPCS"
    assert row.failed_gate == Gate.MARKET_NOT_GREEN.value
    assert row.rr_score == Decimal("7.68")
    assert row.cylinders is None          # the unknown that mattered, kept as unknown
    assert row.market_alert == "YELLOW"
    assert row.refused_on == date(2026, 8, 23)


def test_the_same_refusal_twice_in_one_day_is_recorded_once(db):
    """
    The daily engine re-reads the same watchlist every run. One unchanged
    refusal repeated 365 times a year is noise that buries the signal.
    """
    day = date(2026, 8, 23)
    assert record_refusal(db, _refusal(), on_day=day) is not None
    db.flush()
    assert record_refusal(db, _refusal(), on_day=day) is None
    db.flush()

    assert db.query(RefusedBuy).count() == 1


def test_a_duplicate_inside_one_flush_is_caught_before_the_constraint_is(db):
    """
    A company held under two listings (KUYAF / KUYA.V) can produce the same
    refusal twice in a single run. Both rows would be pending at once, so the
    check has to see the session, not only the table.
    """
    day = date(2026, 8, 23)
    added = record_many(db, [_refusal(), _refusal()], on_day=day)
    db.flush()

    assert len(added) == 1
    assert db.query(RefusedBuy).count() == 1


def test_a_refusal_that_changes_gate_is_new_information(db):
    """
    The semafor lifts and the answer becomes "not cheap enough" instead of
    "market not green". That is a different fact about the same day.
    """
    day = date(2026, 8, 23)
    record_refusal(db, _refusal(gate=Gate.MARKET_NOT_GREEN), on_day=day)
    record_refusal(db, _refusal(gate=Gate.NOT_CHEAP_ENOUGH), on_day=day)
    db.flush()

    assert db.query(RefusedBuy).count() == 2


def test_the_same_refusal_on_the_next_day_is_recorded_again(db):
    """De-duplication is per day: how long a refusal persisted is the measurement."""
    record_refusal(db, _refusal(), on_day=date(2026, 8, 23))
    record_refusal(db, _refusal(), on_day=date(2026, 8, 24))
    db.flush()

    assert db.query(RefusedBuy).count() == 2


def test_a_refusal_without_a_ticker_is_dropped_not_stored_blank(db):
    assert record_refusal(db, _refusal(ticker="  "), on_day=date(2026, 8, 23)) is None
    db.flush()
    assert db.query(RefusedBuy).count() == 0


def test_a_failing_sink_never_takes_the_days_actions_down(db):
    """
    A lost measurement is recoverable; a lost morning is not. The collector
    swallows its own failure rather than propagating into the action list.
    """
    broken = collector(None)          # a session that cannot do anything
    broken(_refusal())                # must not raise


# ==============================================================================
# A trade records the valuation it was made at
# ==============================================================================
# `avg_cost` says what was paid. `rr_score_at_entry` says what it was WORTH at
# the time, on the canon's own scale — and only the second one makes the
# 3-point rule computable, because the analyst moves the lines underneath the
# price. That is why `should_take_profit` has never had a caller.

@pytest.fixture
def ledger_db():
    from app.models.portfolio import BrokerType, InvestmentLog, Portfolio, Position

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            Portfolio.__table__,
            Position.__table__,
            InvestmentLog.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()
    portfolio = Portfolio(
        name="Test", owner="tomas", broker=BrokerType.DEGIRO, cash_balance=100_000.0
    )
    session.add(portfolio)
    session.flush()
    position = Position(
        portfolio_id=portfolio.id, ticker="CXDO", shares_count=0.0,
        avg_cost=None, currency="USD",
    )
    session.add(position)
    session.commit()
    try:
        yield session, position.id
    finally:
        session.close()


def test_a_buy_records_the_score_it_was_made_at(ledger_db):
    """
    CXDO bought at 6.62 inside the 3.25/15.50 band scores 5.45 (canon 4a).
    Stored now, that number is the starting point the 3-point rule measures
    from; a year later the band may have moved and it could not be re-derived.
    """
    from app.services.trade_ledger import TradeSide, record_trade

    db, position_id = ledger_db
    _pos, log, _outcome = record_trade(
        db, position_id=position_id, side=TradeSide.BUY, shares=10, price=6.62,
        green_line=3.25, red_line=15.50, cylinders=4, line_currency="USD",
    )

    assert float(log.rr_score_at_entry) == pytest.approx(5.45, abs=0.01)
    assert float(log.green_line_at_entry) == 3.25
    assert float(log.red_line_at_entry) == 15.50
    assert log.cylinders_at_entry == 4
    assert log.line_currency == "USD"


def test_a_buy_without_a_known_band_stores_no_entry_score(ledger_db):
    """
    THE honesty case for this column. Most held positions have no lines at all.
    Deriving an entry score from today's band would date the move from a
    starting point that never existed — so the rule stays silent instead.
    """
    from app.services.trade_ledger import TradeSide, record_trade

    db, position_id = ledger_db
    _pos, log, _outcome = record_trade(
        db, position_id=position_id, side=TradeSide.BUY, shares=10, price=6.62,
    )

    assert log.rr_score_at_entry is None
    assert log.green_line_at_entry is None
    assert log.cylinders_at_entry is None


def test_inverted_lines_do_not_produce_an_entry_score(ledger_db):
    """A degenerate band is bad data, not a score of zero."""
    from app.services.trade_ledger import TradeSide, record_trade

    db, position_id = ledger_db
    _pos, log, _outcome = record_trade(
        db, position_id=position_id, side=TradeSide.BUY, shares=10, price=6.62,
        green_line=15.50, red_line=3.25,
    )

    assert log.rr_score_at_entry is None


# ==============================================================================
# The band is stamped from whichever listing carries the analysis
# ==============================================================================

# `stock_lifecycle` stores its evidence in a Postgres JSONB column, which
# sqlite cannot render. Teaching the sqlite dialect to emit plain JSON for it
# keeps this test on a real session instead of a mock — the query semantics
# (which listing, which source, which lifecycle row is still valid) are the
# whole point and a mock would assert nothing about them.
@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(type_, compiler, **kw):  # noqa: ARG001
    return "JSON"


@pytest.fixture
def band_db():
    from app.models.gomes import StockLifecycleModel

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine, tables=[Stock.__table__, StockLifecycleModel.__table__]
    )
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def test_a_canadian_position_finds_the_band_filed_under_its_us_listing(band_db):
    """
    The reason `variants_of` is in this path. KUYA.V is held on the TSX Venture
    and every analysis of it — Gomes' and Breakout's alike — names KUYAF, the
    US OTC symbol. Matching on the literal ticker would stamp no band at all on
    four of the five largest positions.
    """
    from app.models.gomes import StockLifecycleModel
    from app.routes.portfolio import _band_at_trade

    band_db.add(Stock(
        ticker="KUYAF", source_key="GOMES", green_line=0.30, red_line=3.75,
    ))
    band_db.add(StockLifecycleModel(
        ticker="KUYAF", phase="GOLD_MINE", is_investable=True, cylinders_count=6,
    ))
    band_db.commit()

    band = _band_at_trade(band_db, "KUYA.V")

    assert band["green_line"] == 0.30
    assert band["red_line"] == 3.75
    assert band["cylinders"] == 6
    # The band is quoted on the OTC listing, so it is in dollars even though
    # the position itself trades in Canadian ones. Naming the currency here is
    # what lets the score be computed on comparable numbers.
    assert band["line_currency"] == "USD"


def test_a_ticker_with_no_band_stamps_nothing(band_db):
    """Most held positions have no lines. Absent stays absent."""
    from app.routes.portfolio import _band_at_trade

    band_db.add(Stock(ticker="DAIO", source_key="GOMES"))
    band_db.commit()

    band = _band_at_trade(band_db, "DAIO")
    assert band["green_line"] is None
    assert band["line_currency"] is None
    assert band["cylinders"] is None


def test_a_breakout_row_does_not_supply_the_gomes_band(band_db):
    """
    Sources stay separate. A Breakout target is not a Gomes valuation line, and
    letting it stand in would make cross-source agreement meaningless — the two
    would be comparing the same number to itself.
    """
    from app.routes.portfolio import _band_at_trade

    band_db.add(Stock(
        ticker="TPCS", source_key="BREAKOUT_INVESTORS",
        green_line=4.00, red_line=9.00,
    ))
    band_db.commit()

    assert _band_at_trade(band_db, "TPCS")["green_line"] is None
