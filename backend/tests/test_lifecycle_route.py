"""
GET/POST /api/gomes/lifecycle/{ticker} — the confirm loop that was missing:
until now the only way to write a lifecycle stage was
`scripts/propose_lifecycle.py --confirm`, a CLI. This mirrors the cylinder
route's own test shape (TestClient + in-memory SQLite).

Only `stock_lifecycle` is in the schema on purpose: `lifecycle_intake.propose`
reads `positions` first and, since that table does not exist here, degrades
to an empty proposal instead of raising — the same path a ticker with no
position takes in production. That keeps this test from ever reaching
`_from_finnhub`'s live HTTP call, which `propose()` would otherwise attempt
for any ticker without XBRL fundamentals supplied.
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
import app.routes.gomes as gomes_route
from app.database.connection import get_db
from app.models.base import Base
from app.models.gomes import StockLifecycleModel


@compiles(JSONB, "sqlite")
def _jsonb_as_text(type_, compiler, **kw):
    return "TEXT"


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine, tables=[StockLifecycleModel.__table__])
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def client(db_session):
    app = FastAPI()
    app.include_router(gomes_route.router)
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def test_get_with_no_position_degrades_instead_of_crashing(client):
    resp = client.get("/api/gomes/lifecycle/RDCM")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "RDCM"
    assert body["confirmed_phase"] is None
    assert body["unknowns"]


def test_confirm_writes_a_row_with_evidence(client, db_session):
    resp = client.post(
        "/api/gomes/lifecycle/RDCM",
        json={"phase": "GOLD_MINE", "confirmed_by": "Tomas"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["confirmed_phase"] == "GOLD_MINE"
    assert body["confirmed_by"] == "Tomas"
    assert body["confirmed_at"] is not None

    row = db_session.query(StockLifecycleModel).filter_by(ticker="RDCM").first()
    assert row is not None
    assert row.phase == "GOLD_MINE"
    assert row.phase_reached == "GOLD_MINE"
    assert row.phase_signals["phase_confirmed_by"] == "Tomas"


def test_ratchet_refuses_to_demote_gold_mine(client):
    client.post(
        "/api/gomes/lifecycle/RDCM",
        json={"phase": "GOLD_MINE", "confirmed_by": "Tomas"},
    )
    resp = client.post(
        "/api/gomes/lifecycle/RDCM",
        json={"phase": "WAIT_TIME", "confirmed_by": "Tomas"},
    )
    assert resp.status_code == 200
    body = resp.json()
    # §V1: a Gold Mine reading never demotes — the row keeps its high-water mark.
    assert body["confirmed_phase"] == "GOLD_MINE"
