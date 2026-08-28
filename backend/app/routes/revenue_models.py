"""
Analytikovy modely tržeb — čtení uložených modelů a porovnání s realitou.

Žádný endpoint tady nestojí peníze (žádný LLM). `POST /{id}/compare` sahá na
síť (SEC EDGAR), proto je to samostatná akce, ne něco, co běží při každém
načtení stránky — stejný vzor jako `POST /api/finds/{id}/refresh`.

Nic odsud nezapisuje do `stock_lifecycle`, `stocks` ani `positions`.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.revenue_model import AnalystRevenueModel, AnalystRevenueModelLine
from app.models.sec import SecCoverage
from app.services import revenue_model as rm
from app.services.sec_edgar import CoverageStatus, SecEdgarClient
from app.services.sec_fundamentals import fetch_fundamentals
from app.services.sec_sync import sync_ticker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/revenue-models", tags=["Analytikovy modely tržeb"])


# ==============================================================================
# Schémata
# ==============================================================================

class LineIn(BaseModel):
    category: str = Field(min_length=1, max_length=150)
    item_name: str = Field(min_length=1, max_length=200)
    period_label: str = Field(min_length=1, max_length=20)
    quantity: float | None = None
    price_per_unit: float | None = None
    amount: float | None = None
    currency: str = Field(default="USD", max_length=5)
    confidence: str | None = None
    note: str | None = None


class ModelCreate(BaseModel):
    ticker: str = Field(min_length=1, max_length=20)
    company_name: str | None = None
    source_name: str = "Mark Gomes"
    model_name: str = Field(min_length=1, max_length=200)
    document_date: date | None = None
    notes: str | None = None
    lines: list[LineIn] = Field(min_length=1)


def _num(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _line_to_dict(line: AnalystRevenueModelLine) -> dict[str, Any]:
    return {
        "id": line.id,
        "category": line.category,
        "item_name": line.item_name,
        "period_label": line.period_label,
        "quantity": _num(line.quantity),
        "price_per_unit": _num(line.price_per_unit),
        "amount": _num(line.amount),
        "resolved_amount": line.resolved_amount(),
        "currency": line.currency,
        "confidence": line.confidence,
        "note": line.note,
    }


def _model_summary(model: AnalystRevenueModel) -> dict[str, Any]:
    totals = rm.period_totals(model)
    return {
        "id": model.id,
        "ticker": model.ticker,
        "company_name": model.company_name,
        "source_name": model.source_name,
        "model_name": model.model_name,
        "document_date": model.document_date.isoformat() if model.document_date else None,
        "notes": model.notes,
        "line_count": len(model.lines),
        "period_totals": [
            {
                "period_label": t.period_label,
                "total": t.total,
                "currency": t.currency,
                "unrated_lines": t.unrated_lines,
                "line_count": t.line_count,
            }
            for t in totals
        ],
    }


def _get_or_404(db: Session, model_id: int) -> AnalystRevenueModel:
    model = db.query(AnalystRevenueModel).filter(AnalystRevenueModel.id == model_id).first()
    if model is None:
        raise HTTPException(status_code=404, detail=f"Model {model_id} neexistuje.")
    return model


# ==============================================================================
# Endpointy
# ==============================================================================

@router.get("")
def list_models(ticker: str | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    query = db.query(AnalystRevenueModel)
    if ticker:
        query = query.filter(AnalystRevenueModel.ticker == ticker.upper().strip())
    models = query.order_by(AnalystRevenueModel.ticker, AnalystRevenueModel.id).all()
    return [_model_summary(m) for m in models]


@router.get("/{model_id}")
def get_model(model_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    model = _get_or_404(db, model_id)
    out = _model_summary(model)
    out["lines"] = [_line_to_dict(line) for line in model.lines]
    return out


@router.post("", status_code=201)
def create_model(payload: ModelCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    model = AnalystRevenueModel(
        ticker=payload.ticker.upper().strip(),
        company_name=payload.company_name,
        source_name=payload.source_name,
        model_name=payload.model_name,
        document_date=payload.document_date,
        notes=payload.notes,
    )
    for line_in in payload.lines:
        model.lines.append(
            AnalystRevenueModelLine(
                category=line_in.category,
                item_name=line_in.item_name,
                period_label=line_in.period_label,
                quantity=line_in.quantity,
                price_per_unit=line_in.price_per_unit,
                amount=line_in.amount,
                currency=line_in.currency,
                confidence=line_in.confidence,
                note=line_in.note,
            )
        )
    db.add(model)
    try:
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Uložení selhalo: {exc}") from None
    db.refresh(model)
    out = _model_summary(model)
    out["lines"] = [_line_to_dict(line) for line in model.lines]
    return out


@router.post("/{model_id}/compare")
def compare_model(model_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """
    Dotáhne aktuální výkazy z SEC a postaví je vedle modelu, období po období.

    Zahraniční firma bez XBRL nebo firma, na kterou SEC nedosáhne, dostane u
    každého období pojmenovanou mezeru — ne prázdné porovnání, které vypadá
    jako "nemá co ukázat".
    """
    model = _get_or_404(db, model_id)

    fundamentals = None
    try:
        client = SecEdgarClient()
        report = sync_ticker(db, model.ticker, client=client, with_outlook=False, max_filings=2)
        if report.status == CoverageStatus.COVERED.value:
            coverage = (
                db.query(SecCoverage).filter(SecCoverage.ticker == model.ticker).first()
            )
            if coverage and coverage.cik:
                fundamentals = fetch_fundamentals(model.ticker, coverage.cik, client=client)
    except Exception as exc:  # noqa: BLE001
        logger.warning("SEC porovnání pro %s selhalo", model.ticker, exc_info=True)

    comparisons = rm.compare_to_actual(model, fundamentals)
    return {
        "model_id": model.id,
        "ticker": model.ticker,
        "comparisons": [
            {
                "period_label": c.period_label,
                "model_total": c.model_total,
                "currency": c.currency,
                "actual": c.actual,
                "variance_pct": c.variance_pct,
                "gap_cs": c.gap_cs,
            }
            for c in comparisons
        ],
    }


@router.delete("/{model_id}", status_code=204, response_model=None)
def delete_model(model_id: int, db: Session = Depends(get_db)) -> None:
    model = _get_or_404(db, model_id)
    db.delete(model)
    db.commit()
