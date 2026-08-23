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
import smtplib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import httpx


from app.config.settings import Settings

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
            
            logger.info(f"Telegram alert sent for {alert.ticker}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}")
            return False
    
    def _format_message(self, alert: Alert) -> str:
        """Format alert as Telegram message"""
        emoji = "[HOT]" if alert.buy_confidence >= 80 else "[UP]"
        
        msg = f"{emoji} *{alert.ticker}* - {alert.signal_strength}\n\n"
        msg += f"*Buy Confidence:* {alert.buy_confidence:.1f}%\n\n"
        
        if alert.entry_price:
            msg += f"*Entry:* ${alert.entry_price:.2f}\n"
        if alert.target_price:
            msg += f"*Target:* ${alert.target_price:.2f}\n"
        if alert.stop_loss:
            msg += f"*Stop Loss:* ${alert.stop_loss:.2f}\n"
        if alert.kelly_size:
            msg += f"*Position Size:* {alert.kelly_size * 100:.1f}%\n"
        
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
        #: Why the last send failed, in Czech, or None. A channel that cannot
        #: deliver has to be able to say so — silence is the one answer this
        #: app must never give about a message it failed to send.
        self.last_error: str | None = None
    
    async def send(self, alert: Alert) -> bool:
        """Send email notification"""
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"Trading Alert: {alert.ticker} ({alert.buy_confidence:.1f}%)"
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
            
            logger.info(f"Email alert sent for {alert.ticker}")
            self.last_error = None
            return True

        except smtplib.SMTPAuthenticationError as e:
            # Not a hiccup. The credential is dead and stays dead until you
            # replace it — retrying for a week changes nothing. Verified on
            # 2026-08-22: Gmail answered 535 BadCredentials, which is how we
            # learned the app password had expired since January.
            self.last_error = (
                f"E-mail nelze odeslat: server odmítl přihlášení ({e.smtp_code}). "
                f"Nejspíš vypršelo app password — vygeneruj nové a přepiš "
                f"SMTP_PASSWORD v backend/.env"
            )
            logger.error(self.last_error)
            return False

        except Exception as e:
            self.last_error = f"E-mail nelze odeslat: {e}"
            logger.error(f"Failed to send email alert: {e}")
            return False
    
    @staticmethod
    def _money(value: float | None) -> str:
        """A price, or an em dash. Never a crash, never a fabricated zero."""
        return f"${value:.2f}" if value is not None else "—"

    def _format_html(self, alert: Alert) -> str:
        """
        Format alert as HTML email.

        Every row used to be written as `{alert.entry_price:.2f if ... else ...}`.
        A conditional expression is not a format spec, so this raised ValueError
        on every single call — and `send()` swallows exceptions and returns
        False, so the alert simply never arrived and nothing said why.
        """
        color = "#10b981" if alert.buy_confidence >= 80 else "#3b82f6"
        entry = self._money(alert.entry_price)
        target = self._money(alert.target_price)
        stop = self._money(alert.stop_loss)
        size = (
            f"{alert.kelly_size * 100:.1f}%" if alert.kelly_size is not None else "—"
        )
        
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
                <td style="padding: 8px;">{entry}</td>
              </tr>
              <tr>
                <td style="padding: 8px; font-weight: bold;">Target Price:</td>
                <td style="padding: 8px; color: green;">{target}</td>
              </tr>
              <tr>
                <td style="padding: 8px; font-weight: bold;">Stop Loss:</td>
                <td style="padding: 8px; color: red;">{stop}</td>
              </tr>
              <tr>
                <td style="padding: 8px; font-weight: bold;">Position Size:</td>
                <td style="padding: 8px;">{size}</td>
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
        #: Why each channel could not be built. Kept so "nothing was sent" can
        #: be answered with a reason instead of silence.
        self.unconfigured: list[str] = []
        #: Why each channel's last send failed, keyed by channel name.
        self.last_errors: dict[str, str] = {}
    
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
            if not success:
                self.last_errors[channel_name] = (
                    getattr(channel, "last_error", None)
                    or f"{channel_name}: odeslání selhalo bez uvedení důvodu"
                )
            else:
                self.last_errors.pop(channel_name, None)

        if results and not any(results.values()):
            # Every channel failed. This is the state where the app has stopped
            # being able to reach you at all, which for a week away is the
            # difference between the app working and not existing.
            logger.error(
                "ŽÁDNÝ notifikační kanál nedoručil alert %s: %s",
                alert.ticker, "; ".join(self.last_errors.values()),
            )

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
        - SMTP_USERNAME   (also the sender address)
        - SMTP_PASSWORD
        - EMAIL_RECIPIENT

        These are read through `Settings`, the same place the rest of the app
        reads them. They used to come from `os.getenv` under two names —
        SMTP_FROM_EMAIL and SMTP_TO_EMAIL — that appear nowhere in .env and
        nowhere else in the codebase. The `all([...])` check therefore always
        failed, so the scheduler ran every thirty minutes with nothing to send
        through, while a fully configured mailbox sat in .env under the name
        EMAIL_RECIPIENT.

        When a channel cannot be built, the reason is recorded in
        `service.unconfigured` rather than being dropped.
        """
        service = cls()
        settings = Settings()

        # Telegram
        telegram_token = settings.TELEGRAM_BOT_TOKEN
        telegram_chat_id = settings.TELEGRAM_CHAT_ID
        if telegram_token and telegram_chat_id:
            service.add_channel(TelegramChannel(telegram_token, telegram_chat_id))
        else:
            service.unconfigured.append(
                "Telegram: chybí TELEGRAM_BOT_TOKEN nebo TELEGRAM_CHAT_ID"
            )

        # Email. Gmail sends as the account that authenticates, so the sender is
        # SMTP_USERNAME — there is no separate SMTP_FROM_EMAIL to set.
        smtp_user = settings.SMTP_USERNAME
        smtp_pass = settings.SMTP_PASSWORD
        recipient = settings.EMAIL_RECIPIENT

        if smtp_user and smtp_pass and recipient:
            service.add_channel(EmailChannel(
                settings.SMTP_SERVER, settings.SMTP_PORT,
                smtp_user, smtp_pass,
                smtp_user, recipient,
            ))
        else:
            missing = [
                name for name, value in (
                    ("SMTP_USERNAME", smtp_user),
                    ("SMTP_PASSWORD", smtp_pass),
                    ("EMAIL_RECIPIENT", recipient),
                ) if not value
            ]
            service.unconfigured.append(
                f"E-mail: chybí {', '.join(missing)} v backend/.env"
            )

        if not service.channels:
            logger.warning(
                "Žádný notifikační kanál nejde postavit: %s",
                "; ".join(service.unconfigured),
            )

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
    from app.trading.master_signal import get_top_opportunities_v2
    
    if notification_service is None:
        notification_service = NotificationService.from_env()
    
    if not notification_service.channels:
        logger.warning("No notification channels configured")
        return []
    
    # Get top opportunities
    opportunities = get_top_opportunities_v2(
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
