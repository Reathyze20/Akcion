"""
When each company reports, and how well that is known.

The canon's fourteen-day blackout — do not be holding into a print you cannot
predict — has been implemented since the app was written and has never once
fired. `gomes_analyzer._get_earnings_date` returns None under a TODO, so every
`investment_verdicts.days_to_earnings` ever written is NULL.

What is tested here is the distinction that makes the rule safe to enforce: a
day the provider was told, a window it inferred, and our own arithmetic on
filing periods are three different qualities of knowing. All three block a
purchase, because a delayed purchase is cheaper than a surprise. None of them
may be SHOWN as the others.
"""

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
import app.models.trading  # noqa: F401
from app.models.base import Base
from app.models.earnings import SOURCE_SEC_CADENCE, SOURCE_YAHOO, EarningsDate
from app.models.sec import SecFiling
from app.services import earnings_calendar as ec
from app.trading.gomes_logic import GomesGatekeeper, LifecyclePhase, MarketAlert

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
TODAY = NOW.date()
Gate = GomesGatekeeper.BuyGate


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine, tables=[EarningsDate.__table__, SecFiling.__table__]
    )
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def provider(monkeypatch, value):
    monkeypatch.setattr(ec, "fetch_from_provider", lambda ticker: value)


# ==============================================================================
# Three qualities of knowing
# ==============================================================================

def test_a_single_date_is_taken_as_announced(db, monkeypatch):
    provider(monkeypatch, ec.Guess(
        next_date=date(2026, 11, 9), confirmed=True, source=SOURCE_YAHOO
    ))

    [row] = ec.refresh(db, ["VTSI"], now=NOW)
    db.flush()

    assert row.confirmed is True
    assert row.window_end is None
    assert row.days_until(TODAY) == 78


def test_a_window_is_stored_as_an_estimate(db, monkeypatch):
    """
    Two dates mean the provider worked the timing out from past cadence rather
    than reading an announcement. That difference decides whether the app is
    blocking a purchase on a fact or on a guess.
    """
    provider(monkeypatch, ec.Guess(
        next_date=date(2026, 11, 9), window_end=date(2026, 11, 13),
        confirmed=False, source=SOURCE_YAHOO,
        note="Poskytovatel udává rozmezí, ne oznámené datum",
    ))

    [row] = ec.refresh(db, ["VTSI"], now=NOW)
    db.flush()

    assert row.confirmed is False
    assert row.window_end == date(2026, 11, 13)
    assert "rozmezí" in row.note


def test_the_filing_cadence_is_the_last_resort(db, monkeypatch):
    """
    A quarter after the last quarter, for companies the provider does not
    cover. Only the period a filing REPORTS ON is usable — the day it was filed
    varies by weeks with no pattern, while period ends march in quarters.
    """
    provider(monkeypatch, None)
    db.add(SecFiling(
        ticker="DAIO", cik="0000351998", form="10-Q",
        filed_date=date(2026, 7, 10), period_date=date(2026, 6, 30),
        accession="x", document="y",
    ))
    db.flush()

    [row] = ec.refresh(db, ["DAIO"], now=NOW)
    db.flush()

    assert row.source == SOURCE_SEC_CADENCE
    assert row.confirmed is False
    assert row.next_date == date(2026, 9, 29)      # 30 June + 91 days
    assert "kadence" in row.note


def test_a_cadence_estimate_never_lands_in_the_past(db, monkeypatch):
    """
    A company last read a year ago would otherwise produce a date behind us,
    which reads as "reported already" and is the opposite of the truth.
    """
    provider(monkeypatch, None)
    db.add(SecFiling(
        ticker="OLD", cik="1", form="10-Q",
        filed_date=date(2025, 1, 10), period_date=date(2024, 12, 31),
        accession="x", document="y",
    ))
    db.flush()

    [row] = ec.refresh(db, ["OLD"], now=NOW)
    db.flush()

    # Too many quarters extrapolated from one filing to mean anything.
    assert row.next_date is None
    assert "nezná" in row.note


def test_a_company_nobody_covers_is_recorded_as_unknown(db, monkeypatch):
    """
    Recorded rather than left stale. A date from three months ago is worse than
    no date, because it looks like an answer.
    """
    provider(monkeypatch, None)

    [row] = ec.refresh(db, ["KUYAF"], now=NOW)
    db.flush()

    assert row.next_date is None
    assert row.confirmed is False
    assert row.note


def test_a_stale_row_is_replaced_not_kept(db, monkeypatch):
    provider(monkeypatch, ec.Guess(
        next_date=date(2026, 11, 9), confirmed=True, source=SOURCE_YAHOO
    ))
    ec.refresh(db, ["VTSI"], now=NOW)
    db.flush()

    provider(monkeypatch, None)
    ec.refresh(db, ["VTSI"], now=NOW + ec.REFRESH_AFTER + timedelta(days=1))
    db.flush()

    assert db.query(EarningsDate).one().next_date is None


# ==============================================================================
# Reading politely
# ==============================================================================

def test_a_fresh_row_is_not_re_fetched(db, monkeypatch):
    """One network call per company; the dates do not move daily."""
    calls = []

    def counting(ticker):
        calls.append(ticker)
        return ec.Guess(date(2026, 11, 9), True, SOURCE_YAHOO)

    monkeypatch.setattr(ec, "fetch_from_provider", counting)

    ec.refresh(db, ["VTSI"], now=NOW)
    db.flush()
    ec.refresh(db, ["VTSI"], now=NOW + timedelta(hours=6))
    db.flush()

    assert calls == ["VTSI"]


def test_force_re_reads_anyway(db, monkeypatch):
    calls = []

    def counting(ticker):
        calls.append(ticker)
        return ec.Guess(date(2026, 11, 9), True, SOURCE_YAHOO)

    monkeypatch.setattr(ec, "fetch_from_provider", counting)

    ec.refresh(db, ["VTSI"], now=NOW)
    db.flush()
    ec.refresh(db, ["VTSI"], now=NOW + timedelta(hours=1), force=True)
    db.flush()

    assert len(calls) == 2


def test_one_company_one_row_across_listings(db, monkeypatch):
    """
    KUYA.V at the broker, KUYAF everywhere else. Two rows would be two answers
    about one company's reporting date.
    """
    provider(monkeypatch, ec.Guess(date(2026, 11, 9), True, SOURCE_YAHOO))

    ec.refresh(db, ["KUYA.V", "KUYAF"], now=NOW, force=True)
    db.flush()

    assert db.query(EarningsDate).count() == 1
    assert db.query(EarningsDate).one().ticker == "KUYAF"


# ==============================================================================
# The gate the whole thing exists for
# ==============================================================================

def _guard(**kw):
    base = dict(
        market_alert=MarketAlert.GREEN, rr_score=8.0, deserved_score=5.0,
        cylinders=5, lifecycle_stage=LifecyclePhase.GOLD_MINE,
    )
    base.update(kw)
    return GomesGatekeeper.check_buy_guard(**base)


def test_a_print_inside_the_blackout_stops_the_purchase():
    allowed, gate, reason = _guard(days_to_earnings=5)
    assert allowed is False
    assert gate is Gate.EARNINGS_SOON
    assert "5 dní" in reason


def test_the_edge_of_the_window_still_blocks():
    assert _guard(days_to_earnings=14)[1] is Gate.EARNINGS_SOON
    assert _guard(days_to_earnings=15)[0] is True


def test_an_estimate_blocks_but_says_it_is_an_estimate():
    """
    A delayed purchase is cheaper than a surprise, so a guess blocks like a
    fact. It must never be shown as one — the owner reading "announced" about a
    date nobody announced would stop checking.
    """
    _a, _g, confirmed = _guard(days_to_earnings=5, earnings_confirmed=True)
    _a2, _g2, estimated = _guard(days_to_earnings=5, earnings_confirmed=False)

    assert "oznámeno" in confirmed
    assert "odhad" in estimated


def test_an_unknown_date_does_not_block():
    """
    The one place where absence is NOT treated as danger. Blocking every
    purchase for want of a date nobody publishes would refuse the whole
    Canadian half of the portfolio permanently, and the other gates already
    stand between the owner and a bad buy.
    """
    assert _guard(days_to_earnings=None)[0] is True


def test_a_date_already_past_does_not_block():
    """Yesterday's print is not a reason to wait."""
    assert _guard(days_to_earnings=-3)[0] is True


def test_the_earnings_gate_is_reported_last():
    """
    It is the only gate that passes on its own with time. Recording it as the
    reason when something worse is also true would send the owner waiting for a
    date instead of looking at the price.
    """
    allowed, gate, _ = _guard(days_to_earnings=5, rr_score=2.0)
    assert allowed is False
    assert gate is Gate.NOT_CHEAP_ENOUGH


# ==============================================================================
# How it reads
# ==============================================================================

def test_a_missing_date_says_so_in_words(db):
    assert ec.describe(None) == "datum výsledků neznám"


def test_a_window_is_rendered_as_a_range(db):
    row = EarningsDate(
        ticker="VTSI", next_date=date(2026, 11, 9),
        window_end=date(2026, 11, 13), confirmed=False, source=SOURCE_YAHOO,
    )
    text = ec.describe(row, today=TODAY)
    assert "09.11.2026–13.11.2026" in text
    assert "odhad" in text
