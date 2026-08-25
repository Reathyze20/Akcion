"""
GET /api/gomes/owner-intent/{ticker} — read-only surface for the standing
instruction that suppresses BUY/ACCUMULATE suggestions independently of the
phase gate (see app/services/owner_intent.py and its engine-level tests in
test_owner_intent.py). No write route: set only via scripts/set_owner_intent.py.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models.trading  # noqa: F401 — registers the mapper
import app.routes.gomes as gomes_route
from app.database.connection import get_db
from app.models.base import Base
from app.models.owner_intent import OwnerIntentModel
from app.services import owner_intent as owner_intent_service


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine, tables=[OwnerIntentModel.__table__])
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def client(db_session):
    app = FastAPI()
    app.include_router(gomes_route.router)
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def test_unset_ticker_returns_null(client):
    resp = client.get("/api/gomes/owner-intent/DAIO")
    assert resp.status_code == 200
    assert resp.json() is None


def test_set_ticker_returns_the_intent_and_note(client, db_session):
    owner_intent_service.record(
        db_session, "ECOR", owner_intent_service.EXIT_PENDING,
        note="Čeká na kupní zájem, pak odchod", set_by="Tomas",
    )
    db_session.commit()

    resp = client.get("/api/gomes/owner-intent/ecor")
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] == "EXIT_PENDING"
    assert body["note"] == "Čeká na kupní zájem, pak odchod"
    assert body["set_by"] == "Tomas"
