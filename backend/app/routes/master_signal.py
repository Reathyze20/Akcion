"""
Master Signal API Routes
=========================

API endpoints for Master Signal Aggregator and Action Center.

Endpoints:
- GET /api/master-signal/{ticker} - Get buy confidence for a ticker
- GET /api/action-center/opportunities - Today's top opportunities
- GET /api/action-center/watchlist - Full watchlist with confidence scores

Author: GitHub Copilot with Claude Sonnet 4.5
Date: 2026-01-17
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.trading.master_signal import (
    MasterSignalAggregator,
    MasterSignalResult,
    calculate_buy_confidence,
    get_top_opportunities,
)


router = APIRouter(prefix="/api/master-signal", tags=["Master Signal"])
action_router = APIRouter(prefix="/api/action-center", tags=["Action Center"])


# ==============================================================================
# Master Signal Endpoints
# ==============================================================================

@router.get("/{ticker}")
async def get_master_signal(
    ticker: str,
    user_id: Optional[int] = Query(None, description="User ID for personalized analysis"),
    current_price: Optional[float] = Query(None, description="Override current price"),
    db: Session = Depends(get_db),
) -> dict:
    """
    Get Master Signal (Buy Confidence) for a ticker.
    
    Returns:
        MasterSignalResult with buy_confidence (0-100) and component breakdown
        
    Example:
        GET /api/master-signal/AAPL?user_id=1
        
        Response:
        {
            "ticker": "AAPL",
            "buy_confidence": 82.5,
            "signal_strength": "STRONG_BUY",
            "components": {
                "gomes_score": 90.0,
                "ml_confidence": 78.5,
                "technical_score": 75.0,
                "gap_score": 100.0,
                "risk_reward_score": 80.0
            },
            "verdict": "STRONG_BUY",
            "entry_price": 185.50,
            "target_price": 205.00,
            "stop_loss": 167.00,
            "risk_reward_ratio": 2.3,
            "kelly_size": 0.15
        }
    """
    try:
        result = calculate_buy_confidence(
            db=db,
            ticker=ticker.upper(),
            user_id=user_id,
            current_price=current_price,
        )
        
        return result.to_dict()
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.get("/batch")
async def get_master_signals_batch(
    tickers: str = Query(..., description="Comma-separated ticker list (e.g., AAPL,GOOGL,MSFT)"),
    user_id: Optional[int] = Query(None, description="User ID for personalized analysis"),
    db: Session = Depends(get_db),
) -> dict:
    """
    Get Master Signals for multiple tickers in one request.
    
    Example:
        GET /api/master-signal/batch?tickers=AAPL,GOOGL,MSFT&user_id=1
        
        Response:
        {
            "results": [
                {"ticker": "AAPL", "buy_confidence": 82.5, ...},
                {"ticker": "GOOGL", "buy_confidence": 75.0, ...},
                {"ticker": "MSFT", "buy_confidence": 68.5, ...}
            ],
            "count": 3
        }
    """
    ticker_list = [t.strip().upper() for t in tickers.split(",")]
    
    if len(ticker_list) > 50:
        raise HTTPException(
            status_code=400,
            detail="Maximum 50 tickers per request"
        )
    
    aggregator = MasterSignalAggregator(db)
    results = []
    
    for ticker in ticker_list:
        try:
            result = aggregator.calculate_master_signal(ticker, user_id)
            results.append(result.to_dict())
        except Exception as e:
            # Log error but continue with other tickers
            results.append({
                "ticker": ticker,
                "error": str(e),
                "buy_confidence": None,
            })
    
    return {
        "results": results,
        "count": len(results),
    }


# ==============================================================================
# Action Center Endpoints
# ==============================================================================

@action_router.get("/opportunities")
async def get_action_center_opportunities(
    user_id: Optional[int] = Query(None, description="User ID for personalized analysis"),
    min_confidence: float = Query(60.0, ge=0, le=100, description="Minimum buy confidence (%)"),
    limit: int = Query(10, ge=1, le=50, description="Max results"),
    db: Session = Depends(get_db),
) -> dict:
    """
    Get TODAY'S TOP OPPORTUNITIES - Action Center widget data.
    
    Returns tickers that PRÁVĚ TEĎ splňují podmínky vstupu.
    
    Args:
        user_id: User ID for personalized gap analysis
        min_confidence: Minimum buy confidence threshold (default 60%)
        limit: Max number of opportunities (default 10)
        
    Returns:
        {
            "opportunities": [
                {
                    "ticker": "AAPL",
                    "buy_confidence": 85.5,
                    "signal_strength": "STRONG_BUY",
                    "entry_price": 185.50,
                    "target_price": 205.00,
                    "stop_loss": 167.00,
                    "risk_reward_ratio": 2.3,
                    "kelly_size": 0.15
                },
                ...
            ],
            "count": 5,
            "last_updated": "2026-01-17T14:30:00Z"
        }
        
    Example:
        GET /api/action-center/opportunities?user_id=1&min_confidence=70
    """
    try:
        opportunities = get_top_opportunities(
            db=db,
            user_id=user_id,
            min_confidence=min_confidence,
            limit=limit,
        )
        
        from datetime import datetime
        
        return {
            "opportunities": [opp.to_dict() for opp in opportunities],
            "count": len(opportunities),
            "last_updated": datetime.utcnow().isoformat(),
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@action_router.get("/watchlist")
async def get_action_center_watchlist(
    user_id: Optional[int] = Query(None, description="User ID for personalized analysis"),
    sort_by: str = Query("confidence", regex="^(confidence|ticker|verdict)$"),
    db: Session = Depends(get_db),
) -> dict:
    """
    Get FULL WATCHLIST with confidence scores for all active tickers.
    
    Returns:
        {
            "watchlist": [
                {
                    "ticker": "AAPL",
                    "buy_confidence": 85.5,
                    "signal_strength": "STRONG_BUY",
                    ...
                },
                ...
            ],
            "count": 25,
            "last_updated": "2026-01-17T14:30:00Z"
        }
        
    Example:
        GET /api/action-center/watchlist?user_id=1&sort_by=confidence
    """
    try:
        from app.models.trading import ActiveWatchlist
        from datetime import datetime
        
        # Get all active watchlist items
        watchlist_items = db.query(ActiveWatchlist).filter(
            ActiveWatchlist.is_active == True
        ).all()
        
        aggregator = MasterSignalAggregator(db)
        results = []
        
        for item in watchlist_items:
            try:
                result = aggregator.calculate_master_signal(
                    ticker=item.ticker,
                    user_id=user_id
                )
                results.append(result.to_dict())
            except Exception as e:
                # Log but continue
                results.append({
                    "ticker": item.ticker,
                    "error": str(e),
                    "buy_confidence": 0,
                })
        
        # Sort results
        if sort_by == "confidence":
            results.sort(key=lambda x: x.get("buy_confidence", 0), reverse=True)
        elif sort_by == "ticker":
            results.sort(key=lambda x: x.get("ticker", ""))
        elif sort_by == "verdict":
            results.sort(key=lambda x: x.get("verdict", ""))
        
        return {
            "watchlist": results,
            "count": len(results),
            "last_updated": datetime.utcnow().isoformat(),
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@action_router.get("/summary")
async def get_action_center_summary(
    user_id: Optional[int] = Query(None, description="User ID for personalized analysis"),
    db: Session = Depends(get_db),
) -> dict:
    """
    Get ACTION CENTER SUMMARY - quick stats for dashboard widget.
    
    Returns:
        {
            "strong_buy_count": 5,
            "buy_count": 8,
            "weak_buy_count": 3,
            "neutral_count": 9,
            "avoid_count": 2,
            "top_opportunity": {
                "ticker": "AAPL",
                "buy_confidence": 85.5
            },
            "last_updated": "2026-01-17T14:30:00Z"
        }
        
    Example:
        GET /api/action-center/summary?user_id=1
    """
    try:
        from app.models.trading import ActiveWatchlist
        from datetime import datetime
        
        watchlist_items = db.query(ActiveWatchlist).filter(
            ActiveWatchlist.is_active == True
        ).all()
        
        aggregator = MasterSignalAggregator(db)
        
        # Count signals by strength
        strong_buy = 0
        buy = 0
        weak_buy = 0
        neutral = 0
        avoid = 0
        
        top_opportunity = None
        max_confidence = 0.0
        
        for item in watchlist_items:
            try:
                result = aggregator.calculate_master_signal(
                    ticker=item.ticker,
                    user_id=user_id
                )
                
                # Count by strength
                if result.signal_strength.value == "STRONG_BUY":
                    strong_buy += 1
                elif result.signal_strength.value == "BUY":
                    buy += 1
                elif result.signal_strength.value == "WEAK_BUY":
                    weak_buy += 1
                elif result.signal_strength.value == "NEUTRAL":
                    neutral += 1
                else:
                    avoid += 1
                
                # Track top opportunity
                if result.buy_confidence > max_confidence:
                    max_confidence = result.buy_confidence
                    top_opportunity = {
                        "ticker": result.ticker,
                        "buy_confidence": round(result.buy_confidence, 2),
                    }
                    
            except Exception:
                avoid += 1
                continue
        
        return {
            "strong_buy_count": strong_buy,
            "buy_count": buy,
            "weak_buy_count": weak_buy,
            "neutral_count": neutral,
            "avoid_count": avoid,
            "top_opportunity": top_opportunity,
            "last_updated": datetime.utcnow().isoformat(),
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")
