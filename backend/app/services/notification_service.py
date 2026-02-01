"""
Notification Service - Investment Alerts

Sends notifications via Email and Telegram for investment opportunities.
Designed for long-term investors who need timely but not overwhelming alerts.

Email Setup (Gmail):
1. Go to Google Account → Security → 2-Step Verification → App passwords
2. Generate an App Password for "Mail"
3. Set SMTP_USERNAME, SMTP_PASSWORD, EMAIL_RECIPIENT in .env

Telegram Setup (optional):
1. Create Telegram bot via @BotFather
2. Get your chat_id by messaging @userinfobot
3. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env
"""
from typing import Optional, List, Dict
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
import asyncio

from sqlalchemy.orm import Session
from loguru import logger

from app.config.settings import Settings


class NotificationService:
    """
    Unified notification service for investment alerts.
    
    Channels:
    - Email (primary)
    - Telegram (optional, real-time)
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.settings = Settings()
        
        # Email config
        self.email_recipient = getattr(self.settings, 'EMAIL_RECIPIENT', None)
        self.smtp_server = getattr(self.settings, 'SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = getattr(self.settings, 'SMTP_PORT', 587)
        self.smtp_username = getattr(self.settings, 'SMTP_USERNAME', None)
        self.smtp_password = getattr(self.settings, 'SMTP_PASSWORD', None)
        
        self.email_enabled = bool(
            self.email_recipient and 
            self.smtp_username and 
            self.smtp_password
        )
        
        # Telegram config
        self.telegram_token = getattr(self.settings, 'TELEGRAM_BOT_TOKEN', None)
        self.telegram_chat_id = getattr(self.settings, 'TELEGRAM_CHAT_ID', None)
        self.telegram_enabled = bool(self.telegram_token and self.telegram_chat_id)
        
        if self.email_enabled:
            logger.info(f"Email notifications enabled -> {self.email_recipient}")
        else:
            logger.warning("Email not configured - set EMAIL_RECIPIENT, SMTP_USERNAME, SMTP_PASSWORD")
        
        if self.telegram_enabled:
            logger.info("Telegram notifications enabled")
    
    # =========================================================================
    # EMAIL METHODS
    # =========================================================================
    
    def _send_email(self, subject: str, body_html: str, body_text: str = None) -> bool:
        """
        Send email via SMTP.
        
        Args:
            subject: Email subject
            body_html: HTML body content
            body_text: Plain text fallback (optional)
        
        Returns:
            True if sent successfully
        """
        if not self.email_enabled:
            logger.warning("Email not configured")
            return False
        
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.smtp_username
            msg['To'] = self.email_recipient
            
            # Plain text version
            if body_text:
                msg.attach(MIMEText(body_text, 'plain'))
            
            # HTML version
            msg.attach(MIMEText(body_html, 'html'))
            
            # Send via SMTP
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.sendmail(
                    self.smtp_username,
                    self.email_recipient,
                    msg.as_string()
                )
            
            logger.info(f"Email sent: {subject}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False
    
    async def _send_email_async(self, subject: str, body_html: str, body_text: str = None) -> bool:
        """Async wrapper for email sending."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, 
            lambda: self._send_email(subject, body_html, body_text)
        )
    
    # =========================================================================
    # TELEGRAM METHODS
    # =========================================================================
    
    async def _send_telegram(self, message: str, parse_mode: str = "HTML") -> bool:
        """Send message via Telegram Bot API."""
        if not self.telegram_enabled:
            return False
        
        import httpx
        
        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json={
                    "chat_id": self.telegram_chat_id,
                    "text": message,
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": True
                })
                
                if response.status_code == 200:
                    logger.info("Telegram message sent")
                    return True
                else:
                    logger.error(f"Telegram error: {response.text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False
    
    # =========================================================================
    # UNIFIED NOTIFICATION METHODS
    # =========================================================================
    
    async def send_test_notification(self) -> bool:
        """Send a test notification to verify setup."""
        
        subject = "Akcion Test Notification"
        
        body_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #10b981;">Akcion Test Notification</h2>
            <p>Your investment alerts are configured correctly!</p>
            <p style="color: #6b7280;">{datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
            <hr style="border: 1px solid #e5e7eb;">
            <p style="font-size: 12px; color: #9ca3af;">
                This is a test email from your Akcion Investment Intelligence system.
            </p>
        </body>
        </html>
        """
        
        email_sent = await self._send_email_async(subject, body_html)
        telegram_sent = await self._send_telegram(
            "<b>Akcion Test Notification</b>\n\n"
            "Your investment alerts are configured correctly!\n\n"
            f"{datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        
        return email_sent or telegram_sent
    
    async def send_opportunity_alert(self, decision) -> bool:
        """Send alert for STRONG_BUY or ACCUMULATE opportunity."""
        from app.services.investment_engine import InvestmentDecision
        
        if not isinstance(decision, InvestmentDecision):
            return False
        
        emoji = "[GREEN]" if decision.action.value == "STRONG_BUY" else "[BLUE]"
        
        subject = f"{emoji} {decision.action.value}: {decision.ticker} @ ${decision.current_price:.2f}"
        
        # Build HTML email
        entry_zone_html = ""
        if decision.in_entry_zone:
            entry_zone_html = f'<p style="color: #10b981; font-weight: bold;">IN ENTRY ZONE ({decision.entry_zone})</p>'
        
        target_html = ""
        if decision.price_vs_target:
            target_html = f'<p>Target: {decision.price_vs_target}</p>'
        
        edge_html = ""
        if decision.edge:
            edge_short = decision.edge[:200] + "..." if len(decision.edge) > 200 else decision.edge
            edge_html = f'<p><strong>Edge:</strong> {edge_short}</p>'
        
        catalysts_html = ""
        if decision.catalysts:
            cat_short = decision.catalysts[:200] + "..." if len(decision.catalysts) > 200 else decision.catalysts
            catalysts_html = f'<p><strong>Catalysts:</strong> {cat_short}</p>'
        
        body_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: {'#10b981' if decision.action.value == 'STRONG_BUY' else '#3b82f6'};">
                {emoji} INVESTMENT OPPORTUNITY
            </h2>
            
            <div style="background: #f3f4f6; padding: 15px; border-radius: 8px; margin: 15px 0;">
                <h3 style="margin: 0;">{decision.ticker} - {decision.company_name or ''}</h3>
                <p style="margin: 5px 0;">Action: <strong>{decision.action.value}</strong></p>
                <p style="margin: 5px 0;">Confidence: <strong>{decision.confidence:.0%}</strong></p>
            </div>
            
            <p><strong>Current Price:</strong> ${decision.current_price:.2f}</p>
            {entry_zone_html}
            {target_html}
            
            <p><strong>Thesis Status:</strong> {decision.thesis_status.value}</p>
            
            {"<p><strong>Conviction Score:</strong> " + str(decision.conviction_score) + "/10</p>" if decision.conviction_score else ""}
            
            {edge_html}
            {catalysts_html}
            
            <div style="background: #ecfdf5; padding: 15px; border-radius: 8px; margin: 15px 0;">
                <p style="margin: 0;"><strong>Recommendation:</strong></p>
                <p style="margin: 5px 0;">{decision.action_detail}</p>
            </div>
            
            <hr style="border: 1px solid #e5e7eb;">
            <p style="font-size: 12px; color: #9ca3af;">
                Generated by Akcion Investment Intelligence - {datetime.now().strftime('%Y-%m-%d %H:%M')}
            </p>
        </body>
        </html>
        """
        
        email_sent = await self._send_email_async(subject, body_html)
        
        # Also send Telegram if configured
        if self.telegram_enabled:
            telegram_msg = (
                f"{emoji} <b>INVESTMENT OPPORTUNITY</b>\n\n"
                f"<b>{decision.ticker}</b> - {decision.company_name or ''}\n"
                f"Action: <b>{decision.action.value}</b>\n"
                f"Confidence: {decision.confidence:.0%}\n\n"
                f"Price: ${decision.current_price:.2f}\n"
            )
            if decision.in_entry_zone:
                telegram_msg += f"<b>IN ENTRY ZONE</b>\n"
            telegram_msg += f"\n{decision.action_detail}"
            
            await self._send_telegram(telegram_msg)
        
        return email_sent
    
    async def send_entry_zone_alert(self, decision) -> bool:
        """Send alert when stock enters buy zone."""
        from app.services.investment_engine import InvestmentDecision
        
        if not isinstance(decision, InvestmentDecision):
            return False
        
        subject = f"ENTRY ZONE: {decision.ticker} @ ${decision.current_price:.2f}"
        
        body_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #f59e0b;">ENTRY ZONE ALERT</h2>
            
            <p><strong>{decision.ticker}</strong> is now in your entry zone!</p>
            
            <div style="background: #fef3c7; padding: 15px; border-radius: 8px; margin: 15px 0;">
                <p style="margin: 5px 0;"><strong>Current Price:</strong> ${decision.current_price:.2f}</p>
                <p style="margin: 5px 0;"><strong>Entry Zone:</strong> {decision.entry_zone}</p>
                <p style="margin: 5px 0;"><strong>Thesis:</strong> {decision.thesis_status.value}</p>
            </div>
            
            {"<p><strong>Conviction Score:</strong> " + str(decision.conviction_score) + "/10</p>" if decision.conviction_score else ""}
            {"<p><strong>Sentiment:</strong> " + decision.gomes_sentiment + "</p>" if decision.gomes_sentiment else ""}
            
            <div style="background: #ecfdf5; padding: 15px; border-radius: 8px; margin: 15px 0;">
                <p style="margin: 0;"><strong>Action:</strong> {decision.action_detail}</p>
            </div>
            
            <hr style="border: 1px solid #e5e7eb;">
            <p style="font-size: 12px; color: #9ca3af;">
                Akcion Investment Intelligence • {datetime.now().strftime('%Y-%m-%d %H:%M')}
            </p>
        </body>
        </html>
        """
        
        email_sent = await self._send_email_async(subject, body_html)
        
        if self.telegram_enabled:
            telegram_msg = (
                f"<b>ENTRY ZONE ALERT</b>\n\n"
                f"<b>{decision.ticker}</b> is now in your entry zone!\n\n"
                f"Current: ${decision.current_price:.2f}\n"
                f"Entry Zone: {decision.entry_zone}\n"
                f"Thesis: {decision.thesis_status.value}"
            )
            await self._send_telegram(telegram_msg)
        
        return email_sent
    
    async def send_exit_alert(self, decision) -> bool:
        """Send alert when thesis is broken or exit recommended."""
        from app.services.investment_engine import InvestmentDecision
        
        if not isinstance(decision, InvestmentDecision):
            return False
        
        subject = f"EXIT ALERT: {decision.ticker} - Thesis {decision.thesis_status.value}"
        
        reasoning_html = "".join([f"<li>{r}</li>" for r in decision.reasoning[:5]])
        risks_html = ""
        if decision.risk_matches:
            risks_html = f'<p style="color: #dc2626;"><strong>Risk Flags:</strong> {", ".join(decision.risk_matches[:3])}</p>'
        
        body_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #dc2626;">EXIT ALERT</h2>
            
            <p><strong>{decision.ticker}</strong> - Consider exiting position</p>
            
            <div style="background: #fef2f2; padding: 15px; border-radius: 8px; margin: 15px 0;">
                <p style="margin: 5px 0;"><strong>Current Price:</strong> ${decision.current_price:.2f}</p>
                <p style="margin: 5px 0;"><strong>Thesis:</strong> <span style="color: #dc2626;">{decision.thesis_status.value}</span></p>
                <p style="margin: 5px 0;"><strong>Confidence:</strong> {decision.confidence:.0%}</p>
            </div>
            
            <p><strong>Reasoning:</strong></p>
            <ul>{reasoning_html}</ul>
            
            {risks_html}
            
            <div style="background: #f3f4f6; padding: 15px; border-radius: 8px; margin: 15px 0;">
                <p style="margin: 0;"><strong>Recommendation:</strong> {decision.action_detail}</p>
            </div>
            
            <hr style="border: 1px solid #e5e7eb;">
            <p style="font-size: 12px; color: #9ca3af;">
                Akcion Investment Intelligence • {datetime.now().strftime('%Y-%m-%d %H:%M')}
            </p>
        </body>
        </html>
        """
        
        email_sent = await self._send_email_async(subject, body_html)
        
        if self.telegram_enabled:
            telegram_msg = (
                f"<b>EXIT ALERT</b>\n\n"
                f"<b>{decision.ticker}</b> - Consider exiting position\n\n"
                f"Current: ${decision.current_price:.2f}\n"
                f"Thesis: <b>{decision.thesis_status.value}</b>\n"
            )
            for reason in decision.reasoning[:3]:
                telegram_msg += f"- {reason}\n"
            await self._send_telegram(telegram_msg)
        
        return email_sent
    
    async def send_news_alert(self, news_item, ticker: str) -> bool:
        """Send alert for important news."""
        from app.services.news_monitor import NewsItem, NewsUrgency
        
        if not isinstance(news_item, NewsItem):
            return False
        
        # Only send for important news
        if news_item.urgency not in [NewsUrgency.ACTION_REQUIRED, NewsUrgency.IMPORTANT]:
            return True  # Skip but return success
        
        sentiment_color = {
            "BULLISH": "#10b981",
            "BEARISH": "#dc2626",
            "NEUTRAL": "#6b7280"
        }.get(news_item.sentiment.value, "#6b7280")
        
        urgency_emoji = "[ALERT]" if news_item.urgency == NewsUrgency.ACTION_REQUIRED else "[NEWS]"
        
        subject = f"{urgency_emoji} {ticker} News: {news_item.title[:50]}..."
        
        body_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2>{urgency_emoji} NEWS ALERT: {ticker}</h2>
            
            <h3 style="color: {sentiment_color};">{news_item.title}</h3>
            
            <p>{news_item.summary or ''}</p>
            
            <div style="background: #f3f4f6; padding: 15px; border-radius: 8px; margin: 15px 0;">
                <p style="margin: 5px 0;"><strong>Sentiment:</strong> 
                    <span style="color: {sentiment_color};">{news_item.sentiment.value}</span>
                </p>
                <p style="margin: 5px 0;"><strong>Relevance:</strong> {news_item.relevance_score:.0%}</p>
                <p style="margin: 5px 0;"><strong>Source:</strong> {news_item.source}</p>
            </div>
            
            {"<p><strong>Catalysts:</strong> " + ", ".join(news_item.matched_catalysts[:3]) + "</p>" if news_item.matched_catalysts else ""}
            {"<p style='color: #dc2626;'><strong>Risks:</strong> " + ", ".join(news_item.matched_risks[:3]) + "</p>" if news_item.matched_risks else ""}
            
            {"<p><strong>Gomes Alignment:</strong> " + news_item.gomes_alignment + "</p>" if news_item.gomes_alignment and news_item.gomes_alignment != 'N/A' else ""}
            
            {"<div style='background: #ecfdf5; padding: 15px; border-radius: 8px;'><p style='margin: 0;'><strong>Suggestion:</strong> " + news_item.action_suggestion + "</p></div>" if news_item.action_suggestion else ""}
            
            <p><a href="{news_item.url}" style="color: #3b82f6;">Read full article →</a></p>
            
            <hr style="border: 1px solid #e5e7eb;">
            <p style="font-size: 12px; color: #9ca3af;">
                Akcion Investment Intelligence • {datetime.now().strftime('%Y-%m-%d %H:%M')}
            </p>
        </body>
        </html>
        """
        
        email_sent = await self._send_email_async(subject, body_html)
        
        if self.telegram_enabled:
            sentiment_emoji = {"BULLISH": "[UP]", "BEARISH": "[DOWN]", "NEUTRAL": "[-]"}.get(news_item.sentiment.value, "[NEWS]")
            telegram_msg = (
                f"{urgency_emoji} <b>NEWS: {ticker}</b>\n\n"
                f"{sentiment_emoji} <b>{news_item.title}</b>\n\n"
                f"Sentiment: {news_item.sentiment.value}\n"
                f"{news_item.url}"
            )
            await self._send_telegram(telegram_msg)
        
        return email_sent
    
    async def send_daily_digest(self, decisions: List) -> bool:
        """Send daily digest of all investment positions."""
        from app.services.investment_engine import InvestmentDecision, InvestmentAction
        
        if not decisions:
            return True
        
        # Group by action
        strong_buys = [d for d in decisions if d.action == InvestmentAction.STRONG_BUY]
        accumulate = [d for d in decisions if d.action == InvestmentAction.ACCUMULATE]
        watch = [d for d in decisions if d.action == InvestmentAction.WATCH]
        holds = [d for d in decisions if d.action == InvestmentAction.HOLD]
        exits = [d for d in decisions if d.action == InvestmentAction.EXIT]
        in_zones = [d for d in decisions if d.in_entry_zone]
        
        subject = f"Akcion Daily Digest - {datetime.now().strftime('%Y-%m-%d')}"
        
        def format_table(items, color):
            if not items:
                return ""
            rows = "".join([
                f"<tr><td style='padding: 5px; border-bottom: 1px solid #e5e7eb;'>{d.ticker}</td>"
                f"<td style='padding: 5px; border-bottom: 1px solid #e5e7eb;'>${d.current_price:.2f}</td>"
                f"<td style='padding: 5px; border-bottom: 1px solid #e5e7eb;'>{d.conviction_score or '-'}/10</td></tr>"
                for d in items
            ])
            return f"<table style='width: 100%; border-collapse: collapse;'><tr style='background: {color}20;'><th style='text-align: left; padding: 5px;'>Ticker</th><th style='text-align: left; padding: 5px;'>Price</th><th style='text-align: left; padding: 5px;'>Score</th></tr>{rows}</table>"
        
        body_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2>Daily Investment Digest</h2>
            <p style="color: #6b7280;">{datetime.now().strftime('%Y-%m-%d')}</p>
            
            {"<div style='margin: 20px 0;'><h3 style='color: #16a34a;'>[GREEN] STRONG BUY</h3>" + format_table(strong_buys, '#16a34a') + "</div>" if strong_buys else ""}
            
            {"<div style='margin: 20px 0;'><h3 style='color: #2563eb;'>[BLUE] ACCUMULATE</h3>" + format_table(accumulate, '#2563eb') + "</div>" if accumulate else ""}
            
            {"<div style='margin: 20px 0;'><h3 style='color: #dc2626;'>[RED] EXIT</h3>" + format_table(exits, '#dc2626') + "</div>" if exits else ""}
            
            <div style="background: #f3f4f6; padding: 15px; border-radius: 8px; margin: 15px 0;">
                <p style="margin: 5px 0;"><strong>Watching:</strong> {len(watch)} stocks</p>
                <p style="margin: 5px 0;"><strong>Holding:</strong> {len(holds)} positions</p>
            </div>
            
            {"<div style='background: #fef3c7; padding: 15px; border-radius: 8px; margin: 15px 0;'><p style='margin: 0;'><strong>In Entry Zone:</strong> " + ', '.join([d.ticker for d in in_zones]) + "</p></div>" if in_zones else ""}
            
            <hr style="border: 1px solid #e5e7eb;">
            <p style="font-size: 12px; color: #9ca3af;">
                Akcion Investment Intelligence
            </p>
        </body>
        </html>
        """
        
        email_sent = await self._send_email_async(subject, body_html)
        
        # Also send Telegram summary
        if self.telegram_enabled:
            telegram_msg = (
                f"<b>DAILY INVESTMENT DIGEST</b>\n"
                f"{datetime.now().strftime('%Y-%m-%d')}\n\n"
            )
            if strong_buys:
                telegram_msg += "[GREEN] <b>STRONG BUY:</b>\n" + "\n".join([f"  - {d.ticker} @ ${d.current_price:.2f}" for d in strong_buys]) + "\n\n"
            if accumulate:
                telegram_msg += "[BLUE] <b>ACCUMULATE:</b>\n" + "\n".join([f"  - {d.ticker} @ ${d.current_price:.2f}" for d in accumulate]) + "\n\n"
            if exits:
                telegram_msg += "[RED] <b>EXIT:</b>\n" + "\n".join([f"  - {d.ticker} @ ${d.current_price:.2f}" for d in exits]) + "\n\n"
            if in_zones:
                telegram_msg += f"<b>In Entry Zone:</b> {', '.join([d.ticker for d in in_zones])}"
            
            await self._send_telegram(telegram_msg)
        
        return email_sent
