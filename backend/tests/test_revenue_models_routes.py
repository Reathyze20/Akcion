"""
Endpointy pro analytikovy modely tržeb.

Hlídá se hlavně:
  1. Žádný endpoint tady nezavolá LLM — je to čistě čtení DB a (u /compare)
     zdarma SEC data.
  2. /compare vrátí pojmenovanou mezeru, když SEC firmu nepokrývá, ne prázdné
     porovnání, které vypadá jako "nic k ukázání".
  3. Model bez jediného řádku se nesmí založit (validace, ne DB constraint).
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.routes.revenue_models as revenue_models_route
from app.database.connection import get_db
from app.models.base import Base
from app.models.revenue_model import AnalystRevenueModel, AnalystRevenueModelLine
from app.models.sec import SecCoverage
from app.models.trading import ActiveWatchlist  # noqa: F401 — registers the mapper


@pytest.fixture
def db_session():
    # TestClient drives the app from a different thread than the test itself;
    # a bare in-memory SQLite connection is not shareable across threads.
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(
        engine,
        tables=[
            AnalystRevenueModel.__table__,
            AnalystRevenueModelLine.__table__,
            SecCoverage.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def client(db_session):
    app = FastAPI()
    app.include_router(revenue_models_route.router)
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


OPTX_PAYLOAD = {
    "ticker": "optx",
    "company_name": "Syntec Optics Holdings",
    "model_name": "OPTX Product Revenue",
    "notes": "Black text = locked orders, Red = evidence-based estimates.",
    "lines": [
        {
            "category": "Medical",
            "item_name": "Disposable Endoscope Optics",
            "period_label": "2025",
            "quantity": 77000,
            "price_per_unit": 65.0,
            "currency": "USD",
        },
        {
            "category": "Defense",
            "item_name": "Objective Lens Assembly",
            "period_label": "2025",
            "amount": 2_220_000,
            "currency": "USD",
            "confidence": "LOCKED",
        },
    ],
}


class TestCreateModel:
    def test_creates_model_with_lines_and_computed_totals(self, client):
        resp = client.post("/api/revenue-models", json=OPTX_PAYLOAD)
        assert resp.status_code == 201
        body = resp.json()
        assert body["ticker"] == "OPTX"  # uppercased
        assert body["line_count"] == 2
        [period] = body["period_totals"]
        assert period["period_label"] == "2025"
        assert period["total"] == pytest.approx(77000 * 65.0 + 2_220_000)
        assert period["unrated_lines"] == 1  # one line has no confidence

    def test_rejects_a_model_with_no_lines(self, client):
        payload = {**OPTX_PAYLOAD, "lines": []}
        resp = client.post("/api/revenue-models", json=payload)
        assert resp.status_code == 422

    def test_rejects_a_line_with_neither_amount_nor_unit_math(self, client):
        payload = {
            **OPTX_PAYLOAD,
            "lines": [{"category": "X", "item_name": "Y", "period_label": "2025"}],
        }
        resp = client.post("/api/revenue-models", json=payload)
        assert resp.status_code == 400


class TestListAndGet:
    def test_list_filters_by_ticker(self, client):
        client.post("/api/revenue-models", json=OPTX_PAYLOAD)
        other = {**OPTX_PAYLOAD, "ticker": "TPCS", "model_name": "TPCS Backlog"}
        client.post("/api/revenue-models", json=other)

        resp = client.get("/api/revenue-models", params={"ticker": "TPCS"})
        assert resp.status_code == 200
        tickers = {m["ticker"] for m in resp.json()}
        assert tickers == {"TPCS"}

    def test_get_detail_includes_lines(self, client):
        created = client.post("/api/revenue-models", json=OPTX_PAYLOAD).json()
        resp = client.get(f"/api/revenue-models/{created['id']}")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["lines"]) == 2
        assert body["lines"][0]["resolved_amount"] == pytest.approx(77000 * 65.0)

    def test_missing_model_is_404(self, client):
        resp = client.get("/api/revenue-models/999999")
        assert resp.status_code == 404


class TestCompare:
    def test_uncovered_ticker_gives_named_gaps_not_empty_success(self, client, monkeypatch):
        created = client.post("/api/revenue-models", json=OPTX_PAYLOAD).json()

        class _NotCoveredResult:
            status = "NOT_AN_SEC_FILER"

        monkeypatch.setattr(
            revenue_models_route, "sync_ticker", lambda *a, **kw: _NotCoveredResult()
        )
        resp = client.post(f"/api/revenue-models/{created['id']}/compare")
        assert resp.status_code == 200
        [comparison] = resp.json()["comparisons"]
        assert comparison["actual"] is None
        assert comparison["gap_cs"] is not None

    def test_sec_failure_is_caught_and_still_returns_a_gap(self, client, monkeypatch):
        created = client.post("/api/revenue-models", json=OPTX_PAYLOAD).json()

        def _boom(*_a, **_kw):
            raise RuntimeError("SEC is down")

        monkeypatch.setattr(revenue_models_route, "sync_ticker", _boom)
        resp = client.post(f"/api/revenue-models/{created['id']}/compare")
        assert resp.status_code == 200
        [comparison] = resp.json()["comparisons"]
        assert comparison["gap_cs"] is not None

    def test_covered_ticker_with_matching_year_returns_variance(self, client, monkeypatch, db_session):
        created = client.post("/api/revenue-models", json=OPTX_PAYLOAD).json()

        class _CoveredResult:
            status = "COVERED"

        from datetime import date as _date

        from app.services.sec_fundamentals import Fundamentals, Point, Series

        def _fake_fundamentals(*_a, **_kw):
            f = Fundamentals(ticker="OPTX", cik="0001234567")
            f.series["revenue"] = Series(
                key="revenue", label_cs="Tržby", unit="USD", tag="Revenues",
                annual=[Point(end=_date(2025, 12, 31), value=28_000_000, form="10-K", fiscal_year=2025)],
            )
            return f

        db_session.add(SecCoverage(ticker="OPTX", cik="0001234567", status="COVERED"))
        db_session.commit()

        monkeypatch.setattr(revenue_models_route, "sync_ticker", lambda *a, **kw: _CoveredResult())
        monkeypatch.setattr(revenue_models_route, "fetch_fundamentals", _fake_fundamentals)

        resp = client.post(f"/api/revenue-models/{created['id']}/compare")
        assert resp.status_code == 200
        [comparison] = resp.json()["comparisons"]
        assert comparison["actual"] == 28_000_000
        assert comparison["gap_cs"] is None


class TestDelete:
    def test_delete_removes_model_and_its_lines(self, client, db_session):
        created = client.post("/api/revenue-models", json=OPTX_PAYLOAD).json()
        resp = client.delete(f"/api/revenue-models/{created['id']}")
        assert resp.status_code == 204
        assert db_session.query(AnalystRevenueModel).count() == 0
        assert db_session.query(AnalystRevenueModelLine).count() == 0
