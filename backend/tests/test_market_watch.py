"""
The long-term chart may tighten the semafor. It may never loosen it.

Why the rule changed on 2026-08-23
----------------------------------
The market alert gates every purchase and is a hand-set field. `daily_actions`
stops authorising buys once it is fourteen days old — correct, and it also means
the one thing the owner must do by hand is the one thing that disarms everything
else, exactly during the weeks he cannot do it.

Why it is one-directional
-------------------------
The gauge admits its own blind spot: of the two RED alerts Gomes has called in
his life it finds the end of 1999 and misses the middle of 2007 entirely,
because that top rested on credit and earnings about to vanish and
price-against-trend cannot see that. A measure that can miss a top has not
earned the right to sound an all-clear — but one that says "expensive" is worth
listening to when nobody is at the keyboard.
"""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
import app.models.trading  # noqa: F401
from app.models.base import Base
from app.models.portfolio import MarketStatus, MarketStatusEnum
from app.services.market_gauge import ChannelPosition, Reading
from app.services.market_watch import (
    APPLIED,
    SUGGESTED_ONLY,
    UNAVAILABLE,
    UNCHANGED,
    apply_gauge,
    is_more_cautious,
)

NOW = datetime(2026, 8, 23, 12, 0)


def reading(alert: str) -> Reading:
    """A gauge reading that suggests `alert`; the arithmetic has its own tests."""
    return Reading(
        as_of=NOW.date(), close=5000.0, z_score=1.4, percentile=0.9,
        position=ChannelPosition.EXPENSIVE, suggested_alert=alert,
        trend_value=4200.0, upper_line=6000.0, grey_line=4200.0,
        lower_line=2800.0, trend_pct_per_year=7.1, months=492,
    )


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[MarketStatus.__table__])
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def set_alert(db, level: str) -> None:
    db.add(MarketStatus(status=MarketStatusEnum(level)))
    db.flush()


# ==============================================================================
# The ordering the whole rule rests on
# ==============================================================================

def test_caution_is_compared_as_a_level_not_as_a_string():
    assert is_more_cautious("YELLOW", "GREEN")
    assert is_more_cautious("RED", "ORANGE")
    assert not is_more_cautious("GREEN", "YELLOW")
    assert not is_more_cautious("YELLOW", "YELLOW")


def test_an_unset_semafor_accepts_any_tightening():
    """
    A level nobody has set is not a reason to refuse a tightening — it is the
    clearest reason to accept one.
    """
    assert is_more_cautious("YELLOW", None)
    assert not is_more_cautious(None, "GREEN")


# ==============================================================================
# Tightening, which the app may do
# ==============================================================================

def test_a_stricter_reading_is_applied(db):
    set_alert(db, "GREEN")

    result = apply_gauge(db, reading=reading("YELLOW"), now=NOW)
    db.flush()

    assert result.status == APPLIED
    assert result.changed
    assert db.query(MarketStatus).one().status is MarketStatusEnum.YELLOW


def test_the_change_says_what_it_was_based_on(db):
    """
    An automatic change to the field that gates every purchase has to explain
    itself, or the owner finds a different setting one morning with no account
    of why.
    """
    set_alert(db, "GREEN")

    result = apply_gauge(db, reading=reading("YELLOW"), now=NOW)

    assert "přitvrzen" in result.message_cs
    assert "z-skóre" in result.message_cs
    assert "23.08.2026" in result.message_cs
    # Database values never appear in a sentence meant for a reader.
    assert "GREEN" not in result.message_cs and "YELLOW" not in result.message_cs


def test_the_gauge_may_not_escalate_to_a_grade_that_needs_a_cause(db):
    """
    §V3. ORANGE and RED say a cause has been identified; a z-score has none to
    offer. `market_gauge` no longer proposes either, and this is the second
    lock: this module is the only one that writes the semafor without a person,
    and it never loosens — so an escalation applied here would be one nothing
    could undo. The suggestion is reported and NOT applied.
    """
    set_alert(db, "GREEN")

    result = apply_gauge(db, reading=reading("ORANGE"), now=NOW)
    db.flush()

    assert result.status == SUGGESTED_ONLY
    assert not result.changed
    assert db.query(MarketStatus).one().status is MarketStatusEnum.GREEN
    assert "příčinu" in result.message_cs


def test_an_unset_semafor_is_set_rather_than_left_empty(db):
    result = apply_gauge(db, reading=reading("YELLOW"), now=NOW)
    db.flush()

    assert result.status == APPLIED
    assert db.query(MarketStatus).one().status is MarketStatusEnum.YELLOW


def test_the_timestamp_moves_so_the_staleness_rule_sees_it(db):
    """
    `daily_actions` stops authorising buys on a semafor fourteen days old. An
    automatic tightening that did not restamp the row would tighten the level
    and leave the app treating it as stale anyway.
    """
    set_alert(db, "GREEN")

    apply_gauge(db, reading=reading("YELLOW"), now=NOW)
    db.flush()

    assert db.query(MarketStatus).one().last_updated == NOW


# ==============================================================================
# Loosening, which it may not
# ==============================================================================

def test_a_looser_reading_is_shown_and_not_applied(db):
    """
    The heart of the rule. This measure misses the 2007 top entirely, so it
    must never be the thing that re-opens buying.
    """
    set_alert(db, "ORANGE")

    result = apply_gauge(db, reading=reading("GREEN"), now=NOW)
    db.flush()

    assert result.status == SUGGESTED_ONLY
    assert not result.changed
    assert db.query(MarketStatus).one().status is MarketStatusEnum.ORANGE
    assert "nezvolním" in result.message_cs


def test_agreement_changes_nothing_and_says_so(db):
    set_alert(db, "YELLOW")

    result = apply_gauge(db, reading=reading("YELLOW"), now=NOW)

    assert result.status == UNCHANGED
    assert "sedí" in result.message_cs


# ==============================================================================
# When the chart cannot be read
# ==============================================================================

def test_an_uncomputable_gauge_leaves_the_semafor_alone(db, monkeypatch):
    """
    The safe direction. With nothing measurable the level stays where it was,
    and the fourteen-day staleness rule stops authorising purchases on its own.
    """
    set_alert(db, "GREEN")

    def boom(*_a, **_kw):
        raise RuntimeError("yahoo down")

    monkeypatch.setattr("app.services.market_watch.current_reading", boom)

    result = apply_gauge(db, now=NOW)
    db.flush()

    assert result.status == UNAVAILABLE
    assert db.query(MarketStatus).one().status is MarketStatusEnum.GREEN
    assert "yahoo down" in result.message_cs


class TestAgreementAndStaleness:
    """
    `daily_actions` stops authorising buys on a semafor fourteen days old. That
    rule exists to force a human to look — and it also disarms the app during
    exactly the weeks nobody can.

    The split follows the standing asymmetry: stale data may make this app more
    cautious, never less. A cautious level confirmed by the chart may be
    refreshed automatically, because a stale ORANGE only goes on de-risking. A
    GREEN may not, because a stale GREEN authorises purchases and this gauge
    misses the 2007 top.
    """

    def test_a_confirmed_cautious_level_is_refreshed(self, db):
        old = datetime(2026, 8, 1, 12, 0)
        db.add(MarketStatus(status=MarketStatusEnum.YELLOW, last_updated=old))
        db.flush()

        result = apply_gauge(db, reading=reading("YELLOW"), now=NOW)
        db.flush()

        assert result.status == UNCHANGED
        assert db.query(MarketStatus).one().last_updated == NOW
        assert "potvrzeno k dnešku" in result.message_cs

    def test_a_confirmed_green_is_not_refreshed(self, db):
        """
        The one case the app may not keep alive on its own. Buying stays gated
        on a human having looked.
        """
        old = datetime(2026, 8, 1, 12, 0)
        db.add(MarketStatus(status=MarketStatusEnum.GREEN, last_updated=old))
        db.flush()

        result = apply_gauge(db, reading=reading("GREEN"), now=NOW)
        db.flush()

        assert result.status == UNCHANGED
        assert db.query(MarketStatus).one().last_updated == old
        assert "na tvém potvrzení" in result.message_cs
