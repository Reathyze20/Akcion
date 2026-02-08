"""
Investment Intelligence API Routes

Endpoints for long-term investment analysis and alerts.
"""
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from loguru import logger

from app.database.connection import get_db
from app.services.news_monitor import NewsMonitorService, NewsUrgency
from app.services.investment_engine import InvestmentDecisionEngine, InvestmentAction


router = APIRouter(prefix="/api/invest", tags=["investment"])


# =============================================================================
# INVESTMENT DECISION ENDPOINTS
# =============================================================================

@router.get("/analyze/{ticker}")
async def analyze_stock(
    ticker: str,
    db: Session = Depends(get_db)
):
    """
    Get complete investment analysis for a stock.
    
    Combines:
    - Gomes analysis (edge, catalysts, score)
    - ML prediction
    - Recent news
    - Entry zone status
    
    Returns investment recommendation (STRONG_BUY, ACCUMULATE, HOLD, etc.)
    """
    engine = InvestmentDecisionEngine(db)
    decision = await engine.analyze_stock(ticker.upper())
    
    if not decision:
        raise HTTPException(
            status_code=404,
            detail=f"Could not analyze {ticker} - not in watchlist or no data"
        )
    
    return engine.decision_to_dict(decision)


@router.get("/analyze")
async def analyze_watchlist(
    db: Session = Depends(get_db)
):
    """
    Analyze all stocks in active watchlist.
    
    Returns prioritized list of investment decisions.
    """
    engine = InvestmentDecisionEngine(db)
    decisions = await engine.analyze_watchlist()
    
    return {
        "count": len(decisions),
        "analyzed_at": datetime.utcnow().isoformat(),
        "decisions": [engine.decision_to_dict(d) for d in decisions]
    }


@router.get("/opportunities")
async def get_opportunities(
    db: Session = Depends(get_db)
):
    """
    Get current investment opportunities.
    
    Returns stocks with STRONG_BUY or ACCUMULATE recommendations.
    """
    engine = InvestmentDecisionEngine(db)
    decisions = await engine.analyze_watchlist()
    
    opportunities = [
        engine.decision_to_dict(d) for d in decisions
        if d.action in [InvestmentAction.STRONG_BUY, InvestmentAction.ACCUMULATE]
    ]
    
    return {
        "count": len(opportunities),
        "opportunities": opportunities
    }


@router.get("/alerts")
async def get_alerts(
    db: Session = Depends(get_db)
):
    """
    Get all current investment alerts.
    
    Returns entry zone alerts and important news.
    """
    engine = InvestmentDecisionEngine(db)
    news_service = NewsMonitorService(db)
    
    # Get entry zone alerts
    price_alerts = await news_service.check_entry_zones()
    
    # Get decisions requiring action
    decisions = await engine.analyze_watchlist()
    action_alerts = [
        engine.decision_to_dict(d) for d in decisions
        if d.action in [InvestmentAction.STRONG_BUY, InvestmentAction.EXIT]
        or d.in_entry_zone
    ]
    
    return {
        "price_alerts": [news_service.price_alert_to_dict(a) for a in price_alerts],
        "action_alerts": action_alerts,
        "timestamp": datetime.utcnow().isoformat()
    }


# =============================================================================
# NEWS ENDPOINTS
# =============================================================================

@router.get("/news/{ticker}")
async def get_stock_news(
    ticker: str,
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """
    Get classified news for a specific stock.
    """
    from app.models.stock import Stock
    from app.models.trading import ActiveWatchlist
    
    news_service = NewsMonitorService(db)
    
    # Get Gomes context for better classification
    gomes_context = None
    watchlist = db.query(ActiveWatchlist).filter(
        ActiveWatchlist.ticker == ticker.upper(),
        ActiveWatchlist.is_active == True
    ).first()
    
    if watchlist and watchlist.stock_id:
        stock = db.query(Stock).filter(Stock.id == watchlist.stock_id).first()
        if stock:
            gomes_context = {
                'edge': stock.edge,
                'catalysts': stock.catalysts,
                'risks': stock.risks
            }
    
    articles = await news_service.fetch_news_polygon(ticker.upper(), limit=limit)
    
    classified = []
    for article in articles:
        news_item = news_service.classify_news(article, ticker.upper(), gomes_context)
        if news_item.urgency != NewsUrgency.NOISE:
            classified.append(news_service.news_item_to_dict(news_item))
    
    return {
        "ticker": ticker.upper(),
        "count": len(classified),
        "news": classified
    }


@router.get("/news")
async def scan_all_news(
    db: Session = Depends(get_db)
):
    """
    Scan news for all watchlist stocks.
    """
    news_service = NewsMonitorService(db)
    results = await news_service.scan_watchlist()
    
    return {
        "news_count": len(results['news_alerts']),
        "price_alerts_count": len(results['price_alerts']),
        "news_alerts": [news_service.news_item_to_dict(n) for n in results['news_alerts']],
        "price_alerts": [news_service.price_alert_to_dict(a) for a in results['price_alerts']],
        "scanned_at": datetime.utcnow().isoformat()
    }


# =============================================================================
# NOTIFICATION ENDPOINTS
# =============================================================================

@router.post("/notify/test")
async def test_notification(
    db: Session = Depends(get_db)
):
    """
    Send a test notification to verify setup.
    """
    from app.services.notification_service import NotificationService
    
    notifier = NotificationService(db)
    success = await notifier.send_test_notification()
    
    return {
        "success": success,
        "email_enabled": notifier.email_enabled,
        "email_recipient": notifier.email_recipient,
        "telegram_enabled": notifier.telegram_enabled,
        "message": "Test notification sent" if success else "Failed to send - check SMTP credentials"
    }


@router.get("/notify/status")
async def notification_status(
    db: Session = Depends(get_db)
):
    """
    Check notification configuration status.
    """
    from app.services.notification_service import NotificationService
    
    notifier = NotificationService(db)
    
    return {
        "email": {
            "enabled": notifier.email_enabled,
            "recipient": notifier.email_recipient,
            "smtp_server": notifier.smtp_server,
            "smtp_port": notifier.smtp_port,
            "username_set": bool(notifier.smtp_username),
            "password_set": bool(notifier.smtp_password)
        },
        "telegram": {
            "enabled": notifier.telegram_enabled,
            "token_set": bool(notifier.telegram_token),
            "chat_id_set": bool(notifier.telegram_chat_id)
        }
    }


@router.post("/notify/scan")
async def trigger_scan_and_notify(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Trigger a full scan and send notifications for important alerts.
    """
    from app.services.notification_service import NotificationService
    
    async def scan_and_notify():
        engine = InvestmentDecisionEngine(db)
        notifier = NotificationService(db)
        
        decisions = await engine.analyze_watchlist()
        
        # Notify for opportunities and alerts
        for decision in decisions:
            if decision.action == InvestmentAction.STRONG_BUY:
                await notifier.send_opportunity_alert(decision)
            elif decision.action == InvestmentAction.EXIT:
                await notifier.send_exit_alert(decision)
            elif decision.in_entry_zone:
                await notifier.send_entry_zone_alert(decision)
    
    background_tasks.add_task(scan_and_notify)
    
    return {"message": "Scan triggered, notifications will be sent"}
