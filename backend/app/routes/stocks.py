"""
Stock Portfolio Routes

FastAPI endpoints for retrieving and managing stock portfolio data.

Clean Code Principles Applied:
- Single Responsibility: Each endpoint handles one operation
- Type hints throughout
- Clear error handling
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..database.connection import get_db
from ..database.repositories import StockRepository
from ..schemas.responses import StockPortfolioResponse, StockResponse


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stocks", tags=["Portfolio"])


@router.get(
    "",
    response_model=StockPortfolioResponse,
    summary="Get portfolio stocks",
    description="Retrieve all stocks with optional filtering",
)
async def get_stocks(
    sentiment: Optional[str] = Query(None, description="Filter by sentiment (BULLISH, BEARISH, NEUTRAL)"),
    min_gomes_score: Optional[int] = Query(None, ge=1, le=10, description="Minimum Gomes Score (1-10)"),
    min_conviction: Optional[int] = Query(None, ge=1, le=10, description="Minimum Conviction Score (1-10)"),
    speaker: Optional[str] = Query(None, description="Filter by speaker name"),
    db: Session = Depends(get_db),
) -> StockPortfolioResponse:
    """
    Get all stocks from the portfolio with optional filters.
    
    Filters can be combined to narrow down results.
    """
    try:
        repository = StockRepository(db)
        
        # Start with all stocks
        if sentiment:
            stocks = repository.get_stocks_by_sentiment(sentiment.upper())
        else:
            stocks = repository.get_all_stocks()
        
        # Apply additional filters
        if min_gomes_score is not None:
            stocks = [s for s in stocks if s.gomes_score and s.gomes_score >= min_gomes_score]
        
        if min_conviction is not None:
            stocks = [s for s in stocks if s.conviction_score and s.conviction_score >= min_conviction]
        
        if speaker:
            stocks = [s for s in stocks if s.speaker and speaker.lower() in s.speaker.lower()]
        
        # Convert to response models
        stock_responses = [StockResponse.model_validate(stock) for stock in stocks]
        
        filters_applied = {}
        if sentiment:
            filters_applied["sentiment"] = sentiment
        if min_gomes_score:
            filters_applied["min_gomes_score"] = min_gomes_score
        if min_conviction:
            filters_applied["min_conviction"] = min_conviction
        if speaker:
            filters_applied["speaker"] = speaker
        
        return StockPortfolioResponse(
            total_stocks=len(stock_responses),
            stocks=stock_responses,
            filters_applied=filters_applied if filters_applied else None,
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve stocks: {str(e)}",
        )


@router.get(
    "/high-conviction",
    response_model=StockPortfolioResponse,
    summary="Get high conviction stocks",
    description="Retrieve stocks with Gomes Score >= 7 and Conviction Score >= 7",
)
async def get_high_conviction_stocks(
    db: Session = Depends(get_db),
) -> StockPortfolioResponse:
    """Get high-conviction stock picks (Gomes Score >= 7, Conviction >= 7)."""
    try:
        repository = StockRepository(db)
        stocks = repository.get_high_conviction_stocks()
        
        stock_responses = [StockResponse.model_validate(stock) for stock in stocks]
        
        return StockPortfolioResponse(
            total_stocks=len(stock_responses),
            stocks=stock_responses,
            filters_applied={
                "min_gomes_score": 7,
                "min_conviction_score": 7,
            },
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve high conviction stocks: {str(e)}",
        )


@router.get(
    "/{ticker}",
    response_model=StockResponse,
    summary="Get specific stock",
    description="Retrieve the most recent analysis for a specific ticker",
)
async def get_stock_by_ticker(
    ticker: str,
    db: Session = Depends(get_db),
) -> StockResponse:
    """Get the most recent analysis for a specific ticker symbol."""
    try:
        repository = StockRepository(db)
        stock = repository.get_stock_by_ticker(ticker.upper())
        
        if not stock:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Stock with ticker '{ticker}' not found in portfolio",
            )
        
        return StockResponse.model_validate(stock)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve stock: {str(e)}",
        )


@router.get(
    "/{ticker}/history",
    response_model=List[StockResponse],
    summary="Get ticker history",
    description="Retrieve all historical analyses for a specific ticker",
)
async def get_ticker_history(
    ticker: str,
    db: Session = Depends(get_db),
) -> List[StockResponse]:
    """Get all historical analyses for a ticker (most recent first)."""
    try:
        repository = StockRepository(db)
        stocks = repository.get_ticker_history(ticker.upper())
        
        if not stocks:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No history found for ticker '{ticker}'",
            )
        
        return [StockResponse.model_validate(stock) for stock in stocks]
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve ticker history: {str(e)}",
        )


@router.get(
    "/stats/summary",
    summary="Get portfolio statistics",
    description="Get summary statistics about the portfolio",
)
async def get_portfolio_stats(
    db: Session = Depends(get_db),
):
    """Get portfolio summary statistics."""
    try:
        repository = StockRepository(db)
        all_stocks = repository.get_all_stocks()
        
        bullish = len([s for s in all_stocks if s.sentiment == "BULLISH"])
        bearish = len([s for s in all_stocks if s.sentiment == "BEARISH"])
        neutral = len([s for s in all_stocks if s.sentiment == "NEUTRAL"])
        
        high_conviction = len(repository.get_high_conviction_stocks())
        
        avg_gomes = sum(s.gomes_score for s in all_stocks if s.gomes_score) / len([s for s in all_stocks if s.gomes_score]) if any(s.gomes_score for s in all_stocks) else 0
        avg_conviction = sum(s.conviction_score for s in all_stocks if s.conviction_score) / len([s for s in all_stocks if s.conviction_score]) if any(s.conviction_score for s in all_stocks) else 0
        
        unique_tickers = len(set(s.ticker for s in all_stocks))
        
        return {
            "total_analyses": len(all_stocks),
            "unique_tickers": unique_tickers,
            "sentiment_breakdown": {
                "bullish": bullish,
                "bearish": bearish,
                "neutral": neutral,
            },
            "high_conviction_count": high_conviction,
            "average_gomes_score": round(avg_gomes, 2),
            "average_conviction_score": round(avg_conviction, 2),
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate portfolio stats: {str(e)}",
        )
