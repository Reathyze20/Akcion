"""
Notification API Endpoints
===========================

REST API for notification management and testing.

Author: GitHub Copilot with Claude Sonnet 4.5
Date: 2025-01-17
Version: 1.0.0
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.database.connection import get_db
from app.services.notifications import (
    NotificationService,
    Alert,
    check_and_send_alerts,
)


router = APIRouter(prefix="/api/notifications", tags=["notifications"])


# ==============================================================================
# Request/Response Models
# ==============================================================================

class NotificationConfig(BaseModel):
    """Notification configuration"""
    telegram_enabled: bool = Field(default=False, description="Enable Telegram notifications")
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    
    email_enabled: bool = Field(default=False, description="Enable email notifications")
    smtp_server: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_to_email: str | None = None
    
    min_confidence: float = Field(default=80.0, ge=0, le=100, description="Minimum buy confidence to trigger alert")


class TestAlertRequest(BaseModel):
    """Test alert request"""
    ticker: str = Field(..., description="Ticker symbol", example="AAPL")
    buy_confidence: float = Field(..., ge=0, le=100, description="Buy confidence")
    entry_price: float | None = None
    target_price: float | None = None
    stop_loss: float | None = None


class AlertResponse(BaseModel):
    """Alert response"""
    ticker: str
    buy_confidence: float
    signal_strength: str
    message: str
    channels_notified: dict[str, bool]


# ==============================================================================
# Endpoints
# ==============================================================================

@router.post("/test-alert", response_model=AlertResponse)
async def send_test_alert(
    request: TestAlertRequest,
    db: Session = Depends(get_db),
):
    """
    Send test alert
    
    Tests notification channels with a sample alert.
    """
    try:
        # Create service from env
        service = NotificationService.from_env()
        
        if not service.channels:
            raise HTTPException(
                status_code=400,
                detail="No notification channels configured. Set environment variables first."
            )
        
        # Create alert
        alert = Alert(
            ticker=request.ticker,
            buy_confidence=request.buy_confidence,
            signal_strength="TEST" if request.buy_confidence >= 80 else "MODERATE",
            entry_price=request.entry_price,
            target_price=request.target_price,
            stop_loss=request.stop_loss,
            kelly_size=None,
            message="This is a test alert from Akcion Trading Intelligence.",
        )
        
        # Send
        results = await service.send_alert(alert)
        
        return AlertResponse(
            ticker=alert.ticker,
            buy_confidence=alert.buy_confidence,
            signal_strength=alert.signal_strength,
            message=alert.message,
            channels_notified=results,
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/check-opportunities")
async def check_opportunities(
    min_confidence: float = 80.0,
    db: Session = Depends(get_db),
):
    """
    Check for high-confidence opportunities and send alerts
    
    Scans all tickers and sends notifications for those above threshold.
    """
    try:
        alerts = await check_and_send_alerts(
            db=db,
            min_confidence=min_confidence,
        )
        
        return {
            "alerts_sent": len(alerts),
            "min_confidence": min_confidence,
            "tickers": [alert.ticker for alert in alerts],
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_notification_status():
    """
    Get notification system status
    
    Returns which channels are configured.
    """
    import os
    
    telegram_configured = bool(
        os.getenv('TELEGRAM_BOT_TOKEN') and os.getenv('TELEGRAM_CHAT_ID')
    )
    
    email_configured = bool(
        os.getenv('SMTP_SERVER') and 
        os.getenv('SMTP_USERNAME') and 
        os.getenv('SMTP_PASSWORD') and
        os.getenv('SMTP_FROM_EMAIL') and
        os.getenv('SMTP_TO_EMAIL')
    )
    
    return {
        "telegram": {
            "configured": telegram_configured,
            "enabled": telegram_configured,
        },
        "email": {
            "configured": email_configured,
            "enabled": email_configured,
        },
        "total_channels": sum([telegram_configured, email_configured]),
    }
