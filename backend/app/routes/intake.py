"""
Intake Routes - Rapid Data Intake via Gemini Flash
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database.connection import get_db
from ..models.stock import Stock
from ..core.sources import InvestmentSource
from ..services import lifecycle_intake
from ..services.gomes_intake_flash import IntakeAnalysisResult, analyze_intake_content
from ..services.score_journal import SOURCE_MANUAL, record_score

#: This app has one user; every lifecycle confirmation on record already
#: carries this name (IMPLEMENTATION_PLAN.md §30-31). No separate identity
#: field on the intake form for a single-owner app.
CONFIRMED_BY = "Tomas"

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/intake", tags=["Intake"])


class IntakeRequest(BaseModel):
    text: Optional[str] = Field(None, description="Raw text, transcript or notes")
    url: Optional[str] = Field(None, description="YouTube video URL")
    source_type: str = Field("GOMES_VIDEO", description="GOMES_VIDEO | BREAKOUT_INVESTORS | OTHER")


class IntakeCommitResponse(BaseModel):
    success: bool
    ticker: str
    message: str


@router.post("/analyze", response_model=IntakeAnalysisResult)
async def analyze_intake(request: IntakeRequest) -> IntakeAnalysisResult:
    """
    Rychlá analýza zadaného textu nebo YouTube videa pomocí Gemini 3.7 Flash.
    Vrátí strukturovaný návrh (ticker, linie, válce, stádium, katalyzátory).
    """
    try:
        result = analyze_intake_content(
            text=request.text,
            url=request.url,
            source_type=request.source_type
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Intake analysis error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analýza selhala: {str(e)}"
        )


@router.post("/commit", response_model=IntakeCommitResponse)
async def commit_intake(
    data: IntakeAnalysisResult,
    db: Session = Depends(get_db)
) -> IntakeCommitResponse:
    """
    Uloží ověřený výsledek analýzy do databáze.
    """
    try:
        source_key = (
            InvestmentSource.GOMES.value
            if "GOMES" in data.source_type.upper()
            else InvestmentSource.BREAKOUT_INVESTORS.value
        )
        
        # 1. Najít nebo vytvořit záznam ve `stocks`
        stock = (
            db.query(Stock)
            .filter(Stock.ticker == data.ticker)
            .filter(Stock.source_key == source_key)
            .first()
        )
        
        if not stock:
            stock = Stock(
                ticker=data.ticker,
                company_name=data.company_name,
                source_key=source_key,
                speaker=data.speaker,
                sentiment="BULLISH" if data.recommended_action == "BUY" else "NEUTRAL",
                created_at=datetime.utcnow()
            )
            db.add(stock)

        # Aktualizace polí
        stock.company_name = data.company_name
        stock.speaker = data.speaker
        if data.green_line is not None:
            stock.green_line = data.green_line
        if data.red_line is not None:
            stock.red_line = data.red_line
        if data.grey_line is not None:
            stock.grey_line = data.grey_line
        if data.conviction_score is not None:
            stock.conviction_score = data.conviction_score
        if data.primary_catalyst:
            stock.catalysts = data.primary_catalyst
        if data.summary_cz:
            stock.thesis = data.summary_cz

        # 2. Záznam do score deníku, pokud bylo zadáno skóre. Musí proběhnout
        # PŘED čímkoli, co se dotáže DB (krok 3 níž) — SQLAlchemy autoflush by
        # jinak zapsal `stock.conviction_score` beze deníku a `before_flush`
        # bezpečnostní síť by k němu dopsala duplicitní 'unattributed' řádek
        # (stejné pravidlo jako v `intelligence_gomes.py`: "Journal this
        # scoring event before the flush"). `record_score` navíc nemá
        # `rationale` parametr — dřívější volání by tu padlo na TypeError.
        if data.conviction_score is not None:
            record_score(
                db,
                ticker=data.ticker,
                score=data.conviction_score,
                source=SOURCE_MANUAL,
                stock=stock,
                action_signal=data.recommended_action,
            )

        # 3. Aktualizace fáze cyklu — přes potvrzovací bránu, ne přímým zápisem.
        # Gemini Flash návrh je na obrazovce vždy vidět dřív, než sem vůbec
        # dorazí (POST /analyze), takže tohle je lidmi-schválený vstup do
        # `lifecycle_intake.confirm()`, stejná cesta jako `propose_lifecycle.py
        # --confirm`. Zachovává ráčnu (Gold Mine se nikdy nedegraduje) a
        # zapisuje evidenci do phase_signals místo natvrdo `confidence_score=0.8`
        # na sloupce, které na modelu neexistovaly (IMPLEMENTATION_PLAN.md §32).
        if data.lifecycle_phase and data.lifecycle_phase != "UNKNOWN":
            proposal = lifecycle_intake.propose(db, data.ticker)
            lifecycle_intake.confirm(
                db,
                data.ticker,
                data.lifecycle_phase,
                confirmed_by=CONFIRMED_BY,
                proposal=proposal,
            )

        db.commit()
        db.refresh(stock)

        return IntakeCommitResponse(
            success=True,
            ticker=data.ticker,
            message=f"Úspěšně uloženo pro {data.ticker} ({data.company_name})."
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to commit intake data: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Uložení do DB selhalo: {str(e)}"
        )
