"""
A standing owner instruction (ECOR: EXIT_PENDING, SMSI: TAX_LOSS_HOLD) must
suppress BUY/ACCUMULATE suggestions even when the phase gate would allow one
— that is the whole reason it exists instead of a `stock_lifecycle` field.
Mirrors test_daily_actions_endpoint.py's fixtures for the engine half; the
service half gets its own small SQLite roundtrip.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.base import Base
from app.models.owner_intent import OwnerIntentModel
from app.services import owner_intent as owner_intent_service
from app.services.daily_actions import AnalysisInput, PositionInput, generate_daily_actions

NOW = datetime(2026, 7, 26, 12, 0, 0)

RATES = {"USD": 25.0, "CZK": 1.0}


def fx(currency: str) -> float:
    return RATES[currency.upper()]


def run(positions=(), analyses=(), cash_czk=0.0, owner_intent=None, **kw):
    return generate_daily_actions(
        market_alert="GREEN",
        market_alert_updated_at=NOW,
        positions=list(positions),
        analyses=list(analyses),
        cash_czk=cash_czk,
        fx_rate_to_czk=fx,
        now=NOW,
        owner_intent=owner_intent,
        **kw,
    )


def gomes(ticker, **kw) -> AnalysisInput:
    kw.setdefault("cylinders_confirmed_at", NOW - timedelta(days=1))
    kw.setdefault("cylinders_valid_until", NOW + timedelta(days=60))
    kw.setdefault("line_currency", "USD")
    return AnalysisInput(ticker=ticker, source_key="GOMES", **kw)


def position(ticker, shares=100, avg_cost=10.0, price=12.0, **kw) -> PositionInput:
    return PositionInput(
        ticker=ticker, shares=shares, avg_cost=avg_cost, current_price=price,
        last_price_update=NOW, **kw
    )


BUYABLE = dict(
    green_line=5.0, red_line=20.0, cylinders=8,
    lifecycle_phase="GOLD_MINE", conviction_score=8, current_price=6.0,
)


class TestWatchlistBuySuppressed:
    def test_no_override_buys_normally(self):
        result = run(analyses=[gomes("ECOR", **BUYABLE)], cash_czk=100_000.0)
        assert len(result.actions) == 1
        assert result.actions[0].ticker == "ECOR"

    def test_exit_pending_suppresses_the_buy(self):
        result = run(
            analyses=[gomes("ECOR", **BUYABLE)],
            cash_czk=100_000.0,
            owner_intent=lambda t: "EXIT_PENDING" if t == "ECOR" else None,
        )
        assert result.actions == []
        assert result.status == "HOLD_HOLD_HOLD"

    def test_override_is_per_ticker_not_global(self):
        """A standing instruction on ECOR must not silence an unrelated buy."""
        result = run(
            analyses=[gomes("ECOR", **BUYABLE), gomes("DAIO", **BUYABLE)],
            cash_czk=100_000.0,
            owner_intent=lambda t: "EXIT_PENDING" if t == "ECOR" else None,
        )
        assert [a.ticker for a in result.actions] == ["DAIO"]


class TestHeldPositionAddSuppressed:
    def test_tax_loss_hold_suppresses_topping_up(self):
        """
        SMSI: WAIT_TIME already blocks the buy path via the phase gate — the
        point of owner_intent is that the SAME block must hold even if a
        future reading moves the phase off WAIT_TIME, which this proves by
        using a GOLD_MINE reading that would otherwise clearly pass.
        """
        held = position("SMSI", shares=10, avg_cost=50.0, price=3.0)
        result = run(
            positions=[held],
            analyses=[gomes("SMSI", **{**BUYABLE, "current_price": 3.0})],
            cash_czk=100_000.0,
            owner_intent=lambda t: "TAX_LOSS_HOLD" if t == "SMSI" else None,
        )
        assert result.actions == []


class TestOwnerIntentService:
    @pytest.fixture
    def db_session(self):
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(engine, tables=[OwnerIntentModel.__table__])
        session = sessionmaker(bind=engine)()
        yield session
        session.close()

    def test_unset_ticker_reads_as_none(self, db_session):
        assert owner_intent_service.get(db_session, "ECOR") is None

    def test_record_then_get_roundtrips(self, db_session):
        owner_intent_service.record(
            db_session, "ecor", owner_intent_service.EXIT_PENDING,
            note="čeká na kupní zájem", set_by="Tomas",
            now=datetime(2026, 8, 25, tzinfo=timezone.utc),
        )
        db_session.commit()

        row = owner_intent_service.get(db_session, "ECOR")
        assert row is not None
        assert row.intent == "EXIT_PENDING"
        assert row.set_by == "Tomas"

    def test_record_replaces_rather_than_duplicates(self, db_session):
        owner_intent_service.record(
            db_session, "SMSI", owner_intent_service.EXIT_PENDING,
            note="a", set_by="Tomas",
        )
        db_session.commit()
        owner_intent_service.record(
            db_session, "SMSI", owner_intent_service.TAX_LOSS_HOLD,
            note="b", set_by="Tomas",
        )
        db_session.commit()

        assert db_session.query(OwnerIntentModel).count() == 1
        assert owner_intent_service.get(db_session, "SMSI").intent == "TAX_LOSS_HOLD"
