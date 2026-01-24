"""
Trading API Routes - Simplified (No ML)
========================================

REMOVED (v2.0):
- ML predictions (micro-caps are unpredictable)
- ML batch predictions
- ML-based signals

KEPT:
- Watchlist sync
- OHLCV data fetch
- Signal expiration

Author: GitHub Copilot with Claude Opus 4.5
Date: 2026-01-24
Version: 2.0.0
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.config.settings import Settings
from app.schemas.trading import (
    TradingSignalResponse,
    DataSyncRequest,
    DataSyncResponse,
    WatchlistSyncResponse
)
from app.trading.watchlist import WatchlistBuilder
from app.trading.data_fetcher import DataFetcher
from app.trading.signals import SignalGenerator
from loguru import logger


router = APIRouter(prefix="/api/trading", tags=["trading"])
settings = Settings()


@router.get("/signals", response_model=List[TradingSignalResponse])
async def get_trading_signals(
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """
    Get active trading signals with Kelly position sizing
    
    Returns list of actionable BUY signals sorted by Kelly size (best opportunities first)
    """
    try:
        signal_gen = SignalGenerator(db)
        signals = signal_gen.get_active_signals(limit=limit)
        
        return signals
        
    except Exception as e:
        logger.error(f"Error fetching trading signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync/watchlist", response_model=WatchlistSyncResponse)
async def sync_watchlist(
    db: Session = Depends(get_db)
):
    """
    Synchronize watchlist with latest analyst recommendations
    
    Adds tickers with BUY/BULLISH verdicts to active watchlist
    """
    try:
        watchlist_builder = WatchlistBuilder(db)
        result = watchlist_builder.sync_watchlist()
        
        return WatchlistSyncResponse(
            status="success",
            added=result['added'],
            updated=result['updated'],
            removed=result['removed'],
            total_active=result['total_active']
        )
        
    except Exception as e:
        logger.error(f"Watchlist sync failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync/data", response_model=DataSyncResponse)
async def sync_historical_data(
    request: DataSyncRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Fetch historical OHLCV data for watchlist tickers
    
    This runs in background to avoid blocking the request
    """
    try:
        watchlist_builder = WatchlistBuilder(db)
        tickers = request.tickers or watchlist_builder.get_active_tickers()
        
        if not tickers:
            raise HTTPException(status_code=400, detail="No tickers to sync")
        
        # Run data fetch in background
        data_fetcher = DataFetcher(db, settings)
        
        async def fetch_data():
            await data_fetcher.fetch_multiple_tickers(
                tickers=tickers,
                days=request.days,
                sync_type='manual'
            )
        
        background_tasks.add_task(fetch_data)
        
        return DataSyncResponse(
            status="started",
            message=f"Data sync started for {len(tickers)} tickers",
            ticker_count=len(tickers)
        )
        
    except Exception as e:
        logger.error(f"Data sync failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ohlcv/{ticker}")
async def get_ohlcv_data(
    ticker: str,
    days: int = 60,
    db: Session = Depends(get_db)
):
    """
    Get historical OHLCV data for a ticker
    
    Args:
        ticker: Stock ticker symbol
        days: Number of days of history (default 60)
    
    Returns:
        List of OHLCV data points
    """
    from app.models.trading import OHLCVData
    from sqlalchemy import desc
    
    try:
        data = (
            db.query(OHLCVData)
            .filter(OHLCVData.ticker == ticker.upper())
            .order_by(desc(OHLCVData.time))
            .limit(days)
            .all()
        )
        
        if not data:
            raise HTTPException(
                status_code=404,
                detail=f"No OHLCV data found for {ticker}"
            )
        
        # Return in chronological order (oldest first)
        result = [
            {
                "date": d.time.strftime("%Y-%m-%d"),
                "open": float(d.open),
                "high": float(d.high),
                "low": float(d.low),
                "close": float(d.close),
                "volume": d.volume
            }
            for d in reversed(data)
        ]
        
        return {
            "ticker": ticker.upper(),
            "count": len(result),
            "data": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching OHLCV for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/signals/expire")
async def expire_old_signals(
    db: Session = Depends(get_db)
):
    """
    Mark expired signals as inactive
    
    Signals expire after 7 days or when their valid_until date passes
    """
    try:
        signal_gen = SignalGenerator(db)
        count = signal_gen.expire_old_signals()
        
        return {
            "status": "success",
            "expired_count": count
        }
        
    except Exception as e:
        logger.error(f"Failed to expire signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/watchlist")
async def get_watchlist(
    db: Session = Depends(get_db)
):
    """
    Get current active watchlist
    
    Returns list of tickers being tracked
    """
    try:
        watchlist_builder = WatchlistBuilder(db)
        tickers = watchlist_builder.get_active_tickers()
        
        return {
            "tickers": tickers,
            "count": len(tickers)
        }
        
    except Exception as e:
        logger.error(f"Failed to get watchlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))
