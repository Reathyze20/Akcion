"""
ML Learning Engine API Routes
==============================

Endpoints for ML performance tracking and learning metrics.

Author: GitHub Copilot with Claude Sonnet 4.5
Date: 2026-01-17
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.trading.ml_learning import MLLearningEngine


router = APIRouter(prefix="/api/ml-learning", tags=["ML Learning"])


# ==============================================================================
# Performance Metrics Endpoints
# ==============================================================================

@router.get("/performance/{ticker}")
async def get_ticker_performance(
    ticker: str,
    lookback_days: int = Query(90, ge=7, le=365),
    db: Session = Depends(get_db),
) -> dict:
    """
    Get ML performance metrics for a specific ticker.
    
    Returns:
        Performance metrics including accuracy, win rate, Gomes correlation
        
    Example:
        GET /api/ml-learning/performance/AAPL?lookback_days=90
    """
    engine = MLLearningEngine(db, lookback_days=lookback_days)
    metrics = engine.get_performance_metrics(ticker.upper())
    
    if metrics is None:
        raise HTTPException(
            status_code=404,
            detail=f"Insufficient performance data for {ticker}"
        )
    
    return {
        "ticker": metrics.ticker,
        "model_version": metrics.model_version,
        "total_predictions": metrics.total_predictions,
        "direction_accuracy": round(metrics.direction_accuracy, 4),
        "avg_price_error_pct": round(metrics.avg_price_error_pct, 2),
        "median_price_error_pct": round(metrics.median_price_error_pct, 2),
        "gomes_agreement_rate": round(metrics.gomes_agreement_rate, 4),
        "gomes_success_rate": round(metrics.gomes_success_rate, 4),
        "win_count": metrics.win_count,
        "loss_count": metrics.loss_count,
        "win_rate": round(metrics.win_rate, 4),
        "avg_return_pct": round(metrics.avg_return_pct, 2),
        "lookback_days": metrics.lookback_days,
        "last_updated": metrics.last_updated.isoformat(),
    }


@router.get("/performance")
async def get_overall_performance(
    lookback_days: int = Query(90, ge=7, le=365),
    db: Session = Depends(get_db),
) -> dict:
    """
    Get overall ML engine performance across all tickers.
    
    Returns:
        Aggregate performance metrics
        
    Example:
        GET /api/ml-learning/performance?lookback_days=90
    """
    engine = MLLearningEngine(db, lookback_days=lookback_days)
    return engine.get_overall_performance()


@router.get("/adjust-confidence")
async def preview_confidence_adjustment(
    ticker: str,
    raw_confidence: float = Query(..., ge=0.0, le=1.0),
    prediction_type: str = Query(..., regex="^(UP|DOWN|NEUTRAL)$"),
    db: Session = Depends(get_db),
) -> dict:
    """
    Preview confidence adjustment for a ticker.
    
    Shows what adjustment would be applied based on historical performance.
    
    Args:
        ticker: Stock ticker
        raw_confidence: Raw ML confidence (0-1)
        prediction_type: UP, DOWN, or NEUTRAL
        
    Returns:
        Adjustment details
        
    Example:
        GET /api/ml-learning/adjust-confidence?ticker=AAPL&raw_confidence=0.85&prediction_type=UP
    """
    engine = MLLearningEngine(db)
    adjustment = engine.adjust_confidence(
        ticker=ticker.upper(),
        raw_confidence=raw_confidence,
        prediction_type=prediction_type,
    )
    
    metrics_dict = None
    if adjustment.metrics_used:
        m = adjustment.metrics_used
        metrics_dict = {
            "direction_accuracy": round(m.direction_accuracy, 4),
            "win_rate": round(m.win_rate, 4),
            "gomes_agreement_rate": round(m.gomes_agreement_rate, 4),
            "total_predictions": m.total_predictions,
        }
    
    return {
        "ticker": ticker.upper(),
        "original_confidence": round(adjustment.original_confidence, 4),
        "adjusted_confidence": round(adjustment.adjusted_confidence, 4),
        "adjustment_factor": round(adjustment.adjustment_factor, 4),
        "reason": adjustment.reason,
        "historical_metrics": metrics_dict,
    }


# ==============================================================================
# Outcome Recording Endpoints
# ==============================================================================

@router.post("/record-outcome")
async def record_prediction_outcome(
    prediction_id: int,
    actual_price: float,
    actual_direction: Optional[str] = None,
    db: Session = Depends(get_db),
) -> dict:
    """
    Record actual outcome for a prediction.
    
    Use this after a trade completes or prediction horizon expires.
    
    Args:
        prediction_id: ID of MLPrediction
        actual_price: Actual price at evaluation
        actual_direction: Actual direction (UP/DOWN/NEUTRAL) - optional
        
    Returns:
        Performance record created
        
    Example:
        POST /api/ml-learning/record-outcome
        {
            "prediction_id": 123,
            "actual_price": 190.50,
            "actual_direction": "UP"
        }
    """
    engine = MLLearningEngine(db)
    
    try:
        performance = engine.record_outcome(
            prediction_id=prediction_id,
            actual_price=actual_price,
            actual_direction=actual_direction,
        )
        
        return {
            "id": performance.id,
            "ticker": performance.ticker,
            "predicted_direction": performance.predicted_direction,
            "actual_direction": performance.actual_direction,
            "accuracy": float(performance.accuracy),
            "evaluation_date": performance.evaluation_date.isoformat(),
        }
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to record outcome: {e}")


@router.post("/evaluate-pending")
async def evaluate_pending_predictions(
    db: Session = Depends(get_db),
) -> dict:
    """
    Evaluate all predictions whose horizon has passed.
    
    Automatically fetches current prices and records outcomes.
    
    Returns:
        Number of predictions evaluated
        
    Example:
        POST /api/ml-learning/evaluate-pending
    """
    engine = MLLearningEngine(db)
    
    try:
        count = engine.evaluate_all_pending_predictions()
        
        return {
            "evaluated_count": count,
            "message": f"Successfully evaluated {count} pending predictions",
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Evaluation failed: {e}"
        )


# ==============================================================================
# Dashboard/Summary Endpoints
# ==============================================================================

@router.get("/leaderboard")
async def get_ticker_leaderboard(
    limit: int = Query(10, ge=1, le=50),
    sort_by: str = Query("accuracy", regex="^(accuracy|win_rate|total_predictions)$"),
    lookback_days: int = Query(90, ge=7, le=365),
    db: Session = Depends(get_db),
) -> dict:
    """
    Get ticker performance leaderboard.
    
    Shows which tickers have the best ML prediction accuracy.
    
    Args:
        limit: Number of results (default 10)
        sort_by: Sort metric (accuracy, win_rate, total_predictions)
        lookback_days: Days to look back (default 90)
        
    Returns:
        Leaderboard of top-performing tickers
        
    Example:
        GET /api/ml-learning/leaderboard?sort_by=accuracy&limit=10
    """
    from app.models.trading import ModelPerformance
    from datetime import datetime, timedelta
    
    cutoff_date = datetime.utcnow() - timedelta(days=lookback_days)
    
    # Get all tickers with performance data
    tickers = db.query(ModelPerformance.ticker).filter(
        ModelPerformance.evaluation_date >= cutoff_date
    ).distinct().all()
    
    ticker_list = [t[0] for t in tickers]
    
    # Get metrics for each ticker
    engine = MLLearningEngine(db, lookback_days=lookback_days)
    results = []
    
    for ticker in ticker_list:
        metrics = engine.get_performance_metrics(ticker)
        if metrics and metrics.total_predictions >= engine.min_samples:
            results.append({
                "ticker": ticker,
                "accuracy": round(metrics.direction_accuracy, 4),
                "win_rate": round(metrics.win_rate, 4),
                "total_predictions": metrics.total_predictions,
                "avg_return_pct": round(metrics.avg_return_pct, 2),
            })
    
    # Sort results
    sort_key = {
        "accuracy": lambda x: x["accuracy"],
        "win_rate": lambda x: x["win_rate"],
        "total_predictions": lambda x: x["total_predictions"],
    }[sort_by]
    
    results.sort(key=sort_key, reverse=True)
    
    return {
        "leaderboard": results[:limit],
        "total_tickers": len(results),
        "sort_by": sort_by,
        "lookback_days": lookback_days,
    }
