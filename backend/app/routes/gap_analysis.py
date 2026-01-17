"""
Gap Analysis API Routes

Endpoints for matching stock analysis signals with user portfolio positions.
Identifies opportunities, accumulation targets, and danger exits.

Clean Code Principles Applied:
- Single Responsibility: Each endpoint handles one type of query
- Type hints throughout
- Clear response models
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database.connection import get_db
from ..models.stock import Stock
from ..schemas.portfolio import (
    EnrichedStockResponse,
    MatchAnalysisRequest,
    MatchAnalysisResponse,
)
from ..services.gap_analysis import GapAnalysisService, MatchSignal


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.get("/match", response_model=MatchAnalysisResponse)
def get_match_analysis(
    portfolio_id: int | None = Query(None, description="Portfolio ID to match against"),
    db: Session = Depends(get_db),
) -> MatchAnalysisResponse:
    """
    Get gap analysis - match stock analysis with user positions
    
    Returns enriched stocks with:
    - user_holding: bool
    - holding_quantity, holding_avg_cost
    - match_signal: OPPORTUNITY, ACCUMULATE, DANGER_EXIT, etc.
    """
    # Get all analyzed stocks
    stocks = db.query(Stock).all()
    
    # Enrich with position data
    enriched_stocks = GapAnalysisService.enrich_stocks_with_positions(
        db, stocks, portfolio_id
    )
    
    # Calculate summary stats
    market_status = GapAnalysisService.get_market_status(db)
    
    signal_counts = {
        "OPPORTUNITY": 0,
        "ACCUMULATE": 0,
        "DANGER_EXIT": 0,
        "WAIT_MARKET_BAD": 0,
    }
    
    for stock in enriched_stocks:
        signal = stock['match_signal']
        if signal in signal_counts:
            signal_counts[signal] += 1
    
    return {
        "total_stocks": len(enriched_stocks),
        "opportunities": signal_counts["OPPORTUNITY"],
        "accumulate": signal_counts["ACCUMULATE"],
        "danger_exits": signal_counts["DANGER_EXIT"],
        "wait_market_bad": signal_counts["WAIT_MARKET_BAD"],
        "market_status": market_status.value,
        "stocks": enriched_stocks
    }


@router.get("/opportunities", response_model=list[EnrichedStockResponse])
def get_opportunities(
    portfolio_id: int | None = Query(None, description="Portfolio ID"),
    db: Session = Depends(get_db),
) -> list[EnrichedStockResponse]:
    """
    Get stocks with OPPORTUNITY signal.
    
    Returns BUY signals for stocks the user doesn't own.
    """
    return GapAnalysisService.get_opportunities(db, portfolio_id)


@router.get("/danger-exits", response_model=list[EnrichedStockResponse])
def get_danger_exits(
    portfolio_id: int | None = Query(None, description="Portfolio ID"),
    db: Session = Depends(get_db),
) -> list[EnrichedStockResponse]:
    """
    Get positions with DANGER_EXIT signal.
    
    Returns SELL signals for stocks the user currently owns.
    """
    return GapAnalysisService.get_danger_exits(db, portfolio_id)
