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
from app.trading.ml_engine import MLPredictionEngine
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
        # Run ML prediction
        ml_engine = MLPredictionEngine(db)
        prediction = ml_engine.predict(ticker)
        
        if not prediction:
            raise HTTPException(
                status_code=404,
                detail=f"Cannot generate prediction for {ticker} - insufficient data"
            )
        
        # Generate trading signal - prediction is a dict
        signal_gen = SignalGenerator(db)
        signal = signal_gen.generate_signal_from_dict(prediction)
        
        return {
            "ticker": ticker,
            "prediction": {
                "type": prediction['prediction_type'],
                "confidence": float(prediction['confidence']),
                "predicted_price": float(prediction['predicted_price']),
                "current_price": float(prediction['current_price']),
                "price_change_pct": float(prediction['price_change_pct']),
                "horizon_days": prediction['horizon_days'],
                "quality": prediction['quality'],
                "ci_80": [float(prediction['ci_80_lower']), float(prediction['ci_80_upper'])],
                "ci_90": [float(prediction['ci_90_lower']), float(prediction['ci_90_upper'])]
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


@router.get("/predictions/{ticker}")
async def get_prediction(
    ticker: str,
    db: Session = Depends(get_db)
):
    """
    Get the latest ML prediction for a specific ticker with Gomes analysis context.
    
    Returns prediction with confidence intervals and analyst insights for charting.
    """
    from app.models.trading import MLPrediction, ActiveWatchlist
    from app.models.stock import Stock
    from datetime import datetime
    
    try:
        # Get latest prediction from database
        prediction = db.query(MLPrediction).filter(
            MLPrediction.ticker == ticker.upper(),
            MLPrediction.valid_until > datetime.utcnow()
        ).order_by(MLPrediction.created_at.desc()).first()
        
        if not prediction:
            raise HTTPException(
                status_code=404,
                detail=f"No valid prediction found for {ticker}"
            )
        
        # Get Gomes/analyst context from watchlist -> stock
        watchlist = db.query(ActiveWatchlist).filter(
            ActiveWatchlist.ticker == ticker.upper(),
            ActiveWatchlist.is_active == True
        ).first()
        
        gomes_context = None
        if watchlist and watchlist.stock_id:
            stock = db.query(Stock).filter(Stock.id == watchlist.stock_id).first()
            if stock:
                gomes_context = {
                    "company_name": stock.company_name,
                    "analyst": stock.speaker or "Mark Gomes",
                    "sentiment": stock.sentiment,
                    "action_verdict": stock.action_verdict,
                    "gomes_score": stock.gomes_score,
                    "edge": stock.edge,
                    "catalysts": stock.catalysts,
                    "risks": stock.risks,
                    "price_target": stock.price_target,
                    "price_target_short": stock.price_target_short,
                    "price_target_long": stock.price_target_long,
                    "time_horizon": stock.time_horizon,
                    "entry_zone": stock.entry_zone,
                    "trade_rationale": stock.trade_rationale,
                    "source_type": stock.source_type,
                }
        
        # Calculate confidence intervals
        current = float(prediction.current_price)
        predicted = float(prediction.predicted_price)
        confidence = float(prediction.confidence)
        
        # Wider intervals for lower confidence
        spread_80 = abs(predicted - current) * (1 - confidence) * 1.5
        spread_90 = abs(predicted - current) * (1 - confidence) * 2.0
        
        # Determine quality based on CI width
        ci_width_pct = (spread_90 * 2 / current) * 100 if current > 0 else 100
        if ci_width_pct < 10:
            quality = "HIGH_CONFIDENCE"
        elif ci_width_pct < 20:
            quality = "MEDIUM_CONFIDENCE"
        else:
            quality = "LOW_CONFIDENCE"
        
        return {
            "ticker": prediction.ticker,
            "prediction_type": prediction.prediction_type,
            "confidence": confidence,
            "current_price": current,
            "predicted_price": predicted,
            "horizon_days": prediction.horizon_days or 30,
            "quality": quality,
            "ci_80_lower": predicted - spread_80,
            "ci_80_upper": predicted + spread_80,
            "ci_90_lower": predicted - spread_90,
            "ci_90_upper": predicted + spread_90,
            "created_at": prediction.created_at.isoformat(),
            "valid_until": prediction.valid_until.isoformat() if prediction.valid_until else None,
            "analyst_context": gomes_context,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get prediction for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
