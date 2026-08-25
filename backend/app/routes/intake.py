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
from ..models.trading import StockLifecycle
from ..core.sources import InvestmentSource
from ..services.gomes_intake_flash import IntakeAnalysisResult, analyze_intake_content
from ..services.score_journal import SOURCE_MANUAL, record_score

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

        # 2. Aktualizace životního cyklu
        if data.lifecycle_phase and data.lifecycle_phase != "UNKNOWN":
            lifecycle = (
                db.query(StockLifecycle)
                .filter(StockLifecycle.ticker == data.ticker)
                .first()
            )
            if not lifecycle:
                lifecycle = StockLifecycle(
                    ticker=data.ticker,
                    current_stage=data.lifecycle_phase,
                    stage_entered_date=datetime.utcnow(),
                    confidence_score=0.8,
                    stage_rationale=data.summary_cz
                )
                db.add(lifecycle)
            else:
                lifecycle.current_stage = data.lifecycle_phase
                lifecycle.stage_rationale = data.summary_cz
                lifecycle.stage_entered_date = datetime.utcnow()

        # 3. Záznam do score deníku, pokud bylo zadáno skóre
        if data.conviction_score is not None:
            record_score(
                db,
                ticker=data.ticker,
                score=data.conviction_score,
                source=SOURCE_MANUAL,
                rationale=data.summary_cz
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
