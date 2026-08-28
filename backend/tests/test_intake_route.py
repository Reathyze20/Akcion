"""
POST /api/intake/commit — re-enabled 25.8.2026 after being disabled since
24.8. (IMPLEMENTATION_PLAN.md §32: it imported a model that did not exist,
and separately wrote `lifecycle_phase` straight onto `stock_lifecycle`,
bypassing `lifecycle_intake.confirm()` — the ratchet and the human-confirm
gate every other writer of that table goes through).

These tests cover the fixed `/commit` handler in isolation (TestClient +
in-memory SQLite), not the Gemini call in `/analyze` — that endpoint takes
no DB session and is exercised by `test_gomes_intake_flash.py` if present.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models.trading  # noqa: F401 — registers the mapper
import app.routes.intake as intake_route
from app.database.connection import get_db
from app.models.base import Base
from app.models.gomes import StockLifecycleModel
from app.models.score_history import ConvictionScoreHistory
from app.models.stock import Stock


@compiles(JSONB, "sqlite")
def _jsonb_as_text(type_, compiler, **kw):
    return "TEXT"


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(
        engine,
        tables=[Stock.__table__, StockLifecycleModel.__table__, ConvictionScoreHistory.__table__],
    )
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def client(db_session):
    app = FastAPI()
    app.include_router(intake_route.router)
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


PAYLOAD = {
    "ticker": "RDCM",
    "company_name": "Radcom",
    "source_type": "GOMES_VIDEO",
    "speaker": "Mark Gomes",
    "green_line": 10.0,
    "red_line": 20.0,
    "cylinders": 8,
    "lifecycle_phase": "GOLD_MINE",
    "conviction_score": 9,
    "primary_catalyst": "Nová smlouva",
    "summary_cz": "Test shrnutí.",
    "recommended_action": "BUY",
}


def test_commit_creates_stock_and_confirms_phase_through_the_gate(client, db_session):
    resp = client.post("/api/intake/commit", json=PAYLOAD)
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    stock = db_session.query(Stock).filter_by(ticker="RDCM").first()
    assert stock is not None
    assert stock.green_line == 10.0

    lifecycle = db_session.query(StockLifecycleModel).filter_by(ticker="RDCM").first()
    assert lifecycle is not None
    assert lifecycle.phase == "GOLD_MINE"
    # Written through the propose/confirm gate, not a direct field assignment —
    # confirmed_by only appears when `lifecycle_intake.confirm()` ran.
    assert lifecycle.phase_signals["phase_confirmed_by"] == "Tomas"

    scores = db_session.query(ConvictionScoreHistory).filter_by(ticker="RDCM").all()
    assert len(scores) == 1
    assert scores[0].conviction_score == 9


def test_commit_without_score_does_not_journal(client, db_session):
    payload = {**PAYLOAD, "conviction_score": None}
    resp = client.post("/api/intake/commit", json=payload)
    assert resp.status_code == 200
    assert db_session.query(ConvictionScoreHistory).count() == 0


def test_commit_never_demotes_a_confirmed_gold_mine(client, db_session):
    client.post("/api/intake/commit", json=PAYLOAD)  # GOLD_MINE
    resp = client.post("/api/intake/commit", json={**PAYLOAD, "lifecycle_phase": "WAIT_TIME"})
    assert resp.status_code == 200
    lifecycle = db_session.query(StockLifecycleModel).filter_by(ticker="RDCM").first()
    assert lifecycle.phase == "GOLD_MINE"
