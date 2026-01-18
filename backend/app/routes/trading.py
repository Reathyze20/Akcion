"""
Trading API Routes - ML-driven trading signals endpoint
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

# Import ML engine with graceful fallback
try:
    from app.trading.ml_engine import MLPredictionEngine
    ML_ENGINE_AVAILABLE = True
except (ImportError, AttributeError):
    MLPredictionEngine = None
    ML_ENGINE_AVAILABLE = False


router = APIRouter(prefix="/api/trading", tags=["trading"])
settings = Settings()


@router.get("/signals", response_model=List[TradingSignalResponse])
async def get_trading_signals(
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """
    Get active trading signals with ML predictions and Kelly position sizing
    
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


@router.post("/predict/{ticker}")
async def generate_prediction(
    ticker: str,
    db: Session = Depends(get_db)
):
    """
    Generate ML prediction for a specific ticker
    
    Returns prediction with Kelly position size
    """
    try:
        # Check if ML engine is available
        if not ML_ENGINE_AVAILABLE or MLPredictionEngine is None:
            raise HTTPException(
                status_code=503,
                detail="ML prediction engine is not available due to dependency issues"
            )
        
        # Run ML prediction
        ml_engine = MLPredictionEngine(db)
        prediction = ml_engine.predict(ticker)
        
        if not prediction:
            raise HTTPException(
                status_code=404,
                detail=f"Cannot generate prediction for {ticker} - insufficient data"
            )
        
        # Generate trading signal
        signal_gen = SignalGenerator(db)
        signal = signal_gen.generate_signal(prediction)
        
        return {
            "ticker": ticker,
            "prediction": {
                "type": prediction.prediction_type,
                "confidence": float(prediction.confidence),
                "predicted_price": float(prediction.predicted_price),
                "current_price": float(prediction.current_price),
                "kelly_size": float(prediction.kelly_position_size) if prediction.kelly_position_size else 0.0
            },
            "signal": {
                "generated": signal is not None,
                "signal_type": signal.signal_type if signal else None,
                "entry_price": float(signal.entry_price) if signal and signal.entry_price else None,
                "target_price": float(signal.target_price) if signal and signal.target_price else None,
                "stop_loss": float(signal.stop_loss) if signal and signal.stop_loss else None
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Prediction failed for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/predict/batch")
async def generate_predictions_batch(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Generate ML predictions for all active watchlist tickers
    
    Runs in background to avoid timeout
    """
    try:
        watchlist_builder = WatchlistBuilder(db)
        tickers = watchlist_builder.get_active_tickers()
        
        if not tickers:
            raise HTTPException(status_code=400, detail="No tickers in active watchlist")
        
        if not ML_ENGINE_AVAILABLE or MLPredictionEngine is None:
            raise HTTPException(
                status_code=503,
                detail="ML prediction engine is not available due to dependency issues"
            )
        
        async def predict_all():
            ml_engine = MLPredictionEngine(db)
            signal_gen = SignalGenerator(db)
            
            predictions = ml_engine.predict_batch(tickers)
            signals = signal_gen.generate_signals_batch(predictions)
            
            logger.info(f"Batch prediction complete: {len(predictions)} predictions, {len(signals)} signals")
        
        background_tasks.add_task(predict_all)
        
        return {
            "status": "started",
            "message": f"Batch prediction started for {len(tickers)} tickers",
            "ticker_count": len(tickers)
        }
        
    except Exception as e:
        logger.error(f"Batch prediction failed: {e}")
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
