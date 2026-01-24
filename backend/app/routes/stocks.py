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
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database.connection import get_db
from ..database.repositories import StockRepository
from ..models.stock import Stock
from ..schemas.responses import StockPortfolioResponse, StockResponse
from ..services.market_data import MarketDataService
from ..trading.price_lines_data import EXTRACTED_LINES


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stocks", tags=["Portfolio"])


# ==============================================================================
# Price Data Helpers
# ==============================================================================

def get_price_lines_for_ticker(ticker: str) -> dict:
    """Get price lines data for a ticker from extracted data."""
    for line in EXTRACTED_LINES:
        if line.ticker.upper() == ticker.upper():
            return {
                "green_line": line.green_line,
                "red_line": line.red_line,
                "grey_line": line.grey_line,
            }
    return {"green_line": None, "red_line": None, "grey_line": None}


def calculate_price_position(current_price: float | None, green_line: float | None, red_line: float | None) -> tuple[float | None, str | None]:
    """
    Calculate where current price sits within green-red range.
    
    Gomes Logic:
    - GREEN LINE = Buy zone (undervalued price)
    - RED LINE = Fair/overvalued price (time to trim/sell)
    
    Returns:
        (position_pct, zone) where:
        - position_pct: 0% = at green line, 100% = at red line
        - zone: "DEEP_VALUE", "BUY_ZONE", "FAIR_VALUE", "SELL_ZONE", "OVERVALUED"
    """
    if current_price is None or green_line is None or red_line is None:
        return None, None
    
    if red_line <= green_line:
        return None, None  # Invalid range
    
    # Calculate position as percentage of the range
    range_size = red_line - green_line
    position = current_price - green_line
    position_pct = (position / range_size) * 100
    
    # Determine zone based on Gomes methodology
    if current_price < green_line:
        # Below green line = DEEP VALUE (exceptional opportunity)
        zone = "DEEP_VALUE"
        pct_below = ((green_line - current_price) / green_line) * 100
        position_pct = -pct_below
    elif position_pct <= 25:
        # 0-25% of range = BUY ZONE (strong opportunity)
        zone = "BUY_ZONE"
    elif position_pct <= 50:
        # 25-50% = ACCUMULATE (good value)
        zone = "ACCUMULATE"
    elif position_pct <= 75:
        # 50-75% = FAIR VALUE (hold, don't add)
        zone = "FAIR_VALUE"
    elif position_pct <= 100:
        # 75-100% = SELL ZONE (trim positions)
        zone = "SELL_ZONE"
    else:
        # Above red line = OVERVALUED
        zone = "OVERVALUED"
        pct_above = ((current_price - red_line) / range_size) * 100
        position_pct = 100 + pct_above
    
    return round(position_pct, 1), zone


def enrich_stock_with_price_data(stock_response: StockResponse, prices_cache: dict[str, float | None] = None) -> StockResponse:
    """Enrich stock response with current price and price lines data."""
    ticker = stock_response.ticker
    
    # Get price lines
    price_lines = get_price_lines_for_ticker(ticker)
    
    # Get current price (from cache or fetch)
    if prices_cache and ticker in prices_cache:
        current_price = prices_cache[ticker]
    else:
        current_price = MarketDataService.get_current_price(ticker)
    
    # Calculate position
    position_pct, zone = calculate_price_position(
        current_price,
        price_lines["green_line"],
        price_lines["red_line"]
    )
    
    # Update the response with price data
    stock_response.current_price = current_price
    stock_response.green_line = price_lines["green_line"]
    stock_response.red_line = price_lines["red_line"]
    stock_response.grey_line = price_lines["grey_line"]
    stock_response.price_position_pct = position_pct
    stock_response.price_zone = zone
    
    return stock_response


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
    "/enriched",
    response_model=StockPortfolioResponse,
    summary="Get stocks with price data",
    description="Retrieve all stocks enriched with current price and price lines",
)
async def get_enriched_stocks(
    db: Session = Depends(get_db),
) -> StockPortfolioResponse:
    """
    Get all stocks with current price data and price position.
    
    This endpoint fetches live prices and calculates where each stock
    sits within its green-red price range.
    """
    try:
        repository = StockRepository(db)
        stocks = repository.get_all_stocks()
        
        # Get unique tickers
        tickers = list(set(s.ticker for s in stocks))
        
        # Batch fetch prices
        logger.info(f"Fetching prices for {len(tickers)} tickers")
        prices_cache = MarketDataService.get_multiple_prices(tickers)
        
        # Convert to response models and enrich
        stock_responses = []
        for stock in stocks:
            response = StockResponse.model_validate(stock)
            enriched = enrich_stock_with_price_data(response, prices_cache)
            stock_responses.append(enriched)
        
        return StockPortfolioResponse(
            total_stocks=len(stock_responses),
            stocks=stock_responses,
            filters_applied={"enriched": True},
        )
        
    except Exception as e:
        logger.error(f"Failed to get enriched stocks: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve enriched stocks: {str(e)}",
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


# ==============================================================================
# Manual Price Update Endpoint
# ==============================================================================

from pydantic import BaseModel, Field

class PriceUpdateRequest(BaseModel):
    """Request model for manual price update."""
    current_price: float = Field(..., gt=0, description="Current market price")
    green_line: float | None = Field(None, gt=0, description="Conservative target (buy zone)")
    red_line: float | None = Field(None, gt=0, description="Optimistic target (sell zone)")


@router.put(
    "/{ticker}/price",
    summary="Update stock price manually",
    description="Manually update the current price and price targets for a stock",
)
async def update_stock_price(
    ticker: str,
    price_data: PriceUpdateRequest,
    db: Session = Depends(get_db),
):
    """
    Manually update stock price and targets.
    
    Use this when:
    - API price fetching is unavailable
    - You want to set specific price targets
    - Importing from broker (DEGIRO CSV)
    """
    try:
        from ..models.stock import Stock
        
        # Find the stock
        stock = db.query(Stock).filter(Stock.ticker.ilike(ticker)).first()
        
        if not stock:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Stock '{ticker}' not found",
            )
        
        # Update prices
        stock.current_price = price_data.current_price
        
        if price_data.green_line is not None:
            stock.green_line = price_data.green_line
        
        if price_data.red_line is not None:
            stock.red_line = price_data.red_line
        
        db.commit()
        db.refresh(stock)
        
        # Calculate new position
        position_pct, zone = calculate_price_position(
            stock.current_price,
            stock.green_line,
            stock.red_line
        )
        
        logger.info(f"Updated price for {ticker}: ${price_data.current_price}")
        
        return {
            "success": True,
            "ticker": ticker.upper(),
            "current_price": stock.current_price,
            "green_line": stock.green_line,
            "red_line": stock.red_line,
            "price_position_pct": position_pct,
            "price_zone": zone,
            "message": f"Price updated successfully for {ticker}",
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update price for {ticker}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update price: {str(e)}",
        )


# ==============================================================================
# Manual Gomes Score Update Endpoint
# ==============================================================================

class ScoreUpdateRequest(BaseModel):
    """Request model for manual score update."""
    gomes_score: int = Field(..., ge=0, le=10, description="Gomes score (0-10)")
    edge: Optional[str] = Field(None, description="Investment thesis/edge summary")
    action_verdict: Optional[str] = Field(None, description="BUY, HOLD, SELL, WAIT")
    company_name: Optional[str] = Field(None, description="Company name")


@router.put(
    "/{ticker}/score",
    summary="Update stock Gomes score manually",
    description="Manually update the Gomes score and related data for a stock",
)
async def update_stock_score(
    ticker: str,
    score_data: ScoreUpdateRequest,
    db: Session = Depends(get_db),
):
    """
    Manually update stock Gomes score.
    
    Use this for quick score updates without running full Deep DD.
    """
    try:
        # Find or create stock
        stock = db.query(Stock).filter(Stock.ticker == ticker.upper()).first()
        
        if not stock:
            # Create new stock entry
            stock = Stock(
                ticker=ticker.upper(),
                company_name=score_data.company_name or ticker.upper(),
                gomes_score=score_data.gomes_score,
                edge=score_data.edge,
                action_verdict=score_data.action_verdict or ("BUY" if score_data.gomes_score >= 7 else "HOLD" if score_data.gomes_score >= 5 else "SELL"),
            )
            db.add(stock)
            logger.info(f"Created new stock {ticker} with score {score_data.gomes_score}")
        else:
            # Update existing
            stock.gomes_score = score_data.gomes_score
            if score_data.edge:
                stock.edge = score_data.edge
            if score_data.action_verdict:
                stock.action_verdict = score_data.action_verdict
            if score_data.company_name:
                stock.company_name = score_data.company_name
            logger.info(f"Updated score for {ticker}: {score_data.gomes_score}/10")
        
        db.commit()
        db.refresh(stock)
        
        return {
            "success": True,
            "ticker": ticker.upper(),
            "gomes_score": stock.gomes_score,
            "action_verdict": stock.action_verdict,
            "message": f"Score updated successfully for {ticker}",
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update score for {ticker}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update score: {str(e)}",
        )
