"""
Notification Service
====================

Sends alerts when Master Signal exceeds thresholds.

Supported channels:
- Telegram bot
- Email (SMTP)

Author: GitHub Copilot with Claude Sonnet 4.5
Date: 2026-01-17
Version: 1.0.0
"""

from __future__ import annotations

import logging
import os
import smtplib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import httpx


logger = logging.getLogger(__name__)


# ==============================================================================
# Data Models
# ==============================================================================

@dataclass
class Alert:
    """Trading alert notification"""
    ticker: str
    buy_confidence: float
    signal_strength: str
    entry_price: Optional[float]
    target_price: Optional[float]
    stop_loss: Optional[float]
    kelly_size: Optional[float]
    message: str


# ==============================================================================
# Notification Channels
# ==============================================================================

class NotificationChannel(ABC):
    """Base class for notification channels"""
    
    @abstractmethod
    async def send(self, alert: Alert) -> bool:
        """Send notification"""
        pass


class TelegramChannel(NotificationChannel):
    """Telegram Bot notifications"""
    
    def __init__(self, bot_token: str, chat_id: str):
        """
        Initialize Telegram channel
        
        Args:
            bot_token: Telegram bot token (from BotFather)
            chat_id: Telegram chat ID to send messages to
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}"
    
    async def send(self, alert: Alert) -> bool:
        """Send Telegram message"""
        try:
            # Format message
            message = self._format_message(alert)
            
            # Send via Telegram API
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/sendMessage",
                    json={
                        "chat_id": self.chat_id,
                        "text": message,
                        "parse_mode": "Markdown",
                    },
                    timeout=10.0,
                )
                response.raise_for_status()
            
            logger.info(f"📱 Telegram alert sent for {alert.ticker}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}")
            return False
    
    def _format_message(self, alert: Alert) -> str:
        """Format alert as Telegram message"""
        emoji = "🚀" if alert.buy_confidence >= 80 else "📈"
        
        msg = f"{emoji} *{alert.ticker}* - {alert.signal_strength}\n\n"
        msg += f"*Buy Confidence:* {alert.buy_confidence:.1f}%\n\n"
        
        if alert.entry_price:
            msg += f"💰 *Entry:* ${alert.entry_price:.2f}\n"
        if alert.target_price:
            msg += f"🎯 *Target:* ${alert.target_price:.2f}\n"
        if alert.stop_loss:
            msg += f"🛑 *Stop Loss:* ${alert.stop_loss:.2f}\n"
        if alert.kelly_size:
            msg += f"📊 *Position Size:* {alert.kelly_size * 100:.1f}%\n"
        
        msg += f"\n{alert.message}"
        
        return msg


class EmailChannel(NotificationChannel):
    """Email notifications via SMTP"""
    
    def __init__(
        self,
        smtp_server: str,
        smtp_port: int,
        username: str,
        password: str,
        from_email: str,
        to_email: str,
    ):
        """
        Initialize Email channel
        
        Args:
            smtp_server: SMTP server hostname
            smtp_port: SMTP port (usually 587 for TLS)
            username: SMTP username
            password: SMTP password
            from_email: Sender email address
            to_email: Recipient email address
        """
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_email = from_email
        self.to_email = to_email
    
    async def send(self, alert: Alert) -> bool:
        """Send email notification"""
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"🚨 Trading Alert: {alert.ticker} ({alert.buy_confidence:.1f}%)"
            msg['From'] = self.from_email
            msg['To'] = self.to_email
            
            # HTML body
            html_body = self._format_html(alert)
            msg.attach(MIMEText(html_body, 'html'))
            
            # Send via SMTP
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)
            
            logger.info(f"📧 Email alert sent for {alert.ticker}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")
            return False
    
    def _format_html(self, alert: Alert) -> str:
        """Format alert as HTML email"""
        color = "#10b981" if alert.buy_confidence >= 80 else "#3b82f6"
        
        html = f"""
        <html>
          <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2 style="color: {color};">{alert.ticker} - {alert.signal_strength}</h2>
            <p style="font-size: 24px; font-weight: bold;">
              Buy Confidence: {alert.buy_confidence:.1f}%
            </p>
            <table style="border-collapse: collapse; margin: 20px 0;">
              <tr>
                <td style="padding: 8px; font-weight: bold;">Entry Price:</td>
                <td style="padding: 8px;">${alert.entry_price:.2f if alert.entry_price else '—'}</td>
              </tr>
              <tr>
                <td style="padding: 8px; font-weight: bold;">Target Price:</td>
                <td style="padding: 8px; color: green;">${alert.target_price:.2f if alert.target_price else '—'}</td>
              </tr>
              <tr>
                <td style="padding: 8px; font-weight: bold;">Stop Loss:</td>
                <td style="padding: 8px; color: red;">${alert.stop_loss:.2f if alert.stop_loss else '—'}</td>
              </tr>
              <tr>
                <td style="padding: 8px; font-weight: bold;">Position Size:</td>
                <td style="padding: 8px;">{alert.kelly_size * 100:.1f if alert.kelly_size else '—'}%</td>
              </tr>
            </table>
            <p>{alert.message}</p>
            <hr>
            <p style="font-size: 12px; color: #666;">
              This is an automated alert from Akcion Trading Intelligence.
            </p>
          </body>
        </html>
        """
        return html


# ==============================================================================
# Notification Service
# ==============================================================================

class NotificationService:
    """
    Notification Service
    
    Manages and sends alerts across multiple channels.
    
    Usage:
        service = NotificationService()
        service.add_channel(TelegramChannel(token, chat_id))
        service.add_channel(EmailChannel(...))
        
        await service.send_alert(Alert(...))
    """
    
    def __init__(self):
        self.channels: list[NotificationChannel] = []
    
    def add_channel(self, channel: NotificationChannel) -> None:
        """Add notification channel"""
        self.channels.append(channel)
        logger.info(f"Added notification channel: {channel.__class__.__name__}")
    
    async def send_alert(self, alert: Alert) -> dict[str, bool]:
        """
        Send alert to all channels
        
        Returns:
            Dict mapping channel name to success status
        """
        results = {}
        
        for channel in self.channels:
            channel_name = channel.__class__.__name__
            success = await channel.send(alert)
            results[channel_name] = success
        
        return results
    
    @classmethod
    def from_env(cls) -> 'NotificationService':
        """
        Create service from environment variables
        
        Environment variables:
        - TELEGRAM_BOT_TOKEN
        - TELEGRAM_CHAT_ID
        - SMTP_SERVER
        - SMTP_PORT
        - SMTP_USERNAME
        - SMTP_PASSWORD
        - SMTP_FROM_EMAIL
        - SMTP_TO_EMAIL
        """
        service = cls()
        
        # Telegram
        telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
        telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')
        if telegram_token and telegram_chat_id:
            service.add_channel(TelegramChannel(telegram_token, telegram_chat_id))
        
        # Email
        smtp_server = os.getenv('SMTP_SERVER')
        smtp_port = int(os.getenv('SMTP_PORT', '587'))
        smtp_user = os.getenv('SMTP_USERNAME')
        smtp_pass = os.getenv('SMTP_PASSWORD')
        from_email = os.getenv('SMTP_FROM_EMAIL')
        to_email = os.getenv('SMTP_TO_EMAIL')
        
        if all([smtp_server, smtp_user, smtp_pass, from_email, to_email]):
            service.add_channel(EmailChannel(
                smtp_server, smtp_port,
                smtp_user, smtp_pass,
                from_email, to_email
            ))
        
        return service


# ==============================================================================
# Alert Trigger
# ==============================================================================

async def check_and_send_alerts(
    db,
    min_confidence: float = 80.0,
    notification_service: Optional[NotificationService] = None,
) -> list[Alert]:
    """
    Check for high-confidence opportunities and send alerts.
    
    Args:
        db: Database session
        min_confidence: Minimum confidence to trigger alert (default 80%)
        notification_service: Service to use (default: from env)
        
    Returns:
        List of alerts sent
    """
    from app.trading.master_signal import get_top_opportunities
    
    if notification_service is None:
        notification_service = NotificationService.from_env()
    
    if not notification_service.channels:
        logger.warning("No notification channels configured")
        return []
    
    # Get top opportunities
    opportunities = get_top_opportunities(
        db=db,
        min_confidence=min_confidence,
        limit=10,
    )
    
    alerts_sent = []
    
    for opp in opportunities:
        alert = Alert(
            ticker=opp.ticker,
            buy_confidence=opp.buy_confidence,
            signal_strength=opp.signal_strength.value,
            entry_price=opp.entry_price,
            target_price=opp.target_price,
            stop_loss=opp.stop_loss,
            kelly_size=opp.kelly_size,
            message=f"Master Signal detected strong opportunity in {opp.ticker}",
        )
        
        await notification_service.send_alert(alert)
        alerts_sent.append(alert)
    
    logger.info(f"Sent {len(alerts_sent)} alerts")
    return alerts_sent
