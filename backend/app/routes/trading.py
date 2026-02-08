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
- Order validation with Gomes Compliance

Author: GitHub Copilot with Claude Opus 4.5
Date: 2026-02-01
Version: 2.1.0 - Added Gomes Compliance Circuit Breakers
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel

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
from app.core.gomes_compliance import (
    OrderRequest,
    ComplianceResult,
    verify_gomes_compliance,
)
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


# ============================================================================
# ORDER VALIDATION ENDPOINT (With Gomes Circuit Breakers)
# ============================================================================

class OrderValidationResponse(BaseModel):
    """Response from order validation endpoint"""
    allowed: bool
    ticker: str
    action: str
    warning: Optional[str] = None
    max_allocation: Optional[float] = None
    blocked_reason: Optional[str] = None


@router.post("/validate-order", response_model=OrderValidationResponse)
async def validate_order(
    order: OrderRequest,
    db: Session = Depends(get_db)
):
    """
    Validate an order against Gomes compliance rules.
    
    This is a "pre-flight" check before executing an order.
    Use this to check if an order would be allowed before sending to broker.
    
    CIRCUIT BREAKERS:
    - 403 Forbidden: Market is RED (defense mode)
    - 422 Unprocessable: Cash runway < 6 months (dilution risk)
    - 422 Unprocessable: Weinstein Stage 4 (falling knife)
    - WARNING: Conviction score < 7 (speculative, max 3%)
    
    Returns:
        OrderValidationResponse with allowed=True/False and any warnings
    """
    try:
        # This will raise HTTPException if order violates rules
        compliance = verify_gomes_compliance(order, db)
        
        return OrderValidationResponse(
            allowed=compliance.passed,
            ticker=compliance.ticker,
            action=compliance.action,
            warning=compliance.warning,
            max_allocation=compliance.max_allocation,
        )
        
    except HTTPException:
        # Re-raise HTTPException (403, 422)
        raise
    except Exception as e:
        logger.error(f"Error validating order: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/order")
async def place_order(
    order: OrderRequest,
    db: Session = Depends(get_db)
):
    """
    Validate and place an order.
    
    This endpoint uses Gomes Compliance as a circuit breaker.
    If the order violates any rules, it will be rejected with appropriate error codes.
    
    NOTE: Actual order execution is not implemented yet.
    This serves as a template for broker integration.
    """
    # Circuit breaker - will raise HTTPException if not compliant
    compliance = verify_gomes_compliance(order, db)
    
    # TODO: Integrate with actual broker API
    # For now, just return success with compliance info
    
    return {
        "status": "validated",
        "message": "Order passed Gomes compliance. Broker integration pending.",
        "ticker": compliance.ticker,
        "action": compliance.action,
        "warning": compliance.warning,
        "max_allocation": compliance.max_allocation,
    }


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


# ============================================================================
# GOMES ALERTS ENDPOINTS (Thesis Drift Notifications)
# ============================================================================

class AlertResponse(BaseModel):
    """Alert response model"""
    id: int
    ticker: str
    alert_type: str
    severity: str
    title: str
    message: str
    recommendation: Optional[str] = None
    previous_score: Optional[int] = None
    current_score: int
    score_delta: int
    is_read: bool
    created_at: str


class AlertActionRequest(BaseModel):
    """Request to take action on an alert"""
    action: str  # acknowledged, dismissed, acted_upon
    notes: Optional[str] = None


@router.get("/alerts", response_model=List[AlertResponse])
async def get_alerts(
    unread_only: bool = True,
    severity: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """
    Get Gomes alerts (thesis drift notifications)
    
    Args:
        unread_only: Only return unread alerts (default True)
        severity: Filter by severity (CRITICAL, WARNING, INFO, OPPORTUNITY)
        limit: Maximum number of alerts to return
    
    Returns:
        List of alerts sorted by severity (CRITICAL first) and date
    """
    from app.models.gomes import GomesAlert
    
    try:
        query = db.query(GomesAlert)
        
        if unread_only:
            query = query.filter(GomesAlert.is_read == False)
        
        if severity:
            query = query.filter(GomesAlert.severity == severity.upper())
        
        # Order: CRITICAL first, then by date
        alerts = query.order_by(
            GomesAlert.severity.desc(),
            GomesAlert.created_at.desc()
        ).limit(limit).all()
        
        return [
            AlertResponse(
                id=a.id,
                ticker=a.ticker,
                alert_type=a.alert_type,
                severity=a.severity,
                title=a.title,
                message=a.message,
                recommendation=a.recommendation,
                previous_score=a.previous_score,
                current_score=a.current_score,
                score_delta=a.score_delta,
                is_read=a.is_read,
                created_at=a.created_at.isoformat() if a.created_at else ""
            )
            for a in alerts
        ]
        
    except Exception as e:
        logger.error(f"Failed to get alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts/count")
async def get_alert_count(
    db: Session = Depends(get_db)
):
    """
    Get count of unread alerts by severity.
    
    Used for badge display in UI.
    """
    from app.models.gomes import GomesAlert
    from sqlalchemy import func
    
    try:
        counts = (
            db.query(
                GomesAlert.severity,
                func.count(GomesAlert.id)
            )
            .filter(GomesAlert.is_read == False)
            .group_by(GomesAlert.severity)
            .all()
        )
        
        result = {
            "total": sum(c[1] for c in counts),
            "critical": 0,
            "warning": 0,
            "info": 0,
            "opportunity": 0,
        }
        
        for severity, count in counts:
            result[severity.lower()] = count
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to get alert count: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/alerts/{alert_id}/read")
async def mark_alert_read(
    alert_id: int,
    db: Session = Depends(get_db)
):
    """
    Mark an alert as read.
    """
    from app.models.gomes import GomesAlert
    from datetime import datetime
    
    try:
        alert = db.query(GomesAlert).filter(GomesAlert.id == alert_id).first()
        
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        
        alert.is_read = True
        alert.read_at = datetime.utcnow()
        db.commit()
        
        return {"status": "success", "alert_id": alert_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to mark alert read: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/alerts/{alert_id}/action")
async def take_alert_action(
    alert_id: int,
    request: AlertActionRequest,
    db: Session = Depends(get_db)
):
    """
    Take action on an alert (acknowledge, dismiss, acted upon).
    """
    from app.models.gomes import GomesAlert
    from datetime import datetime
    
    valid_actions = ["acknowledged", "dismissed", "acted_upon"]
    
    if request.action not in valid_actions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action. Must be one of: {valid_actions}"
        )
    
    try:
        alert = db.query(GomesAlert).filter(GomesAlert.id == alert_id).first()
        
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        
        alert.action_taken = request.action
        alert.action_notes = request.notes
        alert.is_read = True
        alert.read_at = datetime.utcnow()
        db.commit()
        
        return {
            "status": "success",
            "alert_id": alert_id,
            "action": request.action
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to take alert action: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stocks-needing-review")
async def get_stocks_needing_review(
    db: Session = Depends(get_db)
):
    """
    Get all stocks marked as needing review (THESIS_BROKEN).
    
    These are stocks where the conviction score dropped significantly
    and require immediate attention.
    """
    from app.models.stock import Stock
    
    try:
        stocks = (
            db.query(Stock)
            .filter(Stock.needs_review == True)
            .order_by(Stock.last_review_requested.desc())
            .all()
        )
        
        return {
            "count": len(stocks),
            "stocks": [
                {
                    "ticker": s.ticker,
                    "company_name": s.company_name,
                    "conviction_score": s.conviction_score,
                    "review_reason": s.review_reason,
                    "last_review_requested": s.last_review_requested.isoformat() if s.last_review_requested else None,
                    "current_price": s.current_price,
                    "green_line": s.green_line,
                }
                for s in stocks
            ]
        }
        
    except Exception as e:
        logger.error(f"Failed to get stocks needing review: {e}")
        raise HTTPException(status_code=500, detail=str(e))

