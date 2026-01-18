"""
Notification Service - Investment Alerts

Sends notifications via Telegram and Email for investment opportunities.
Designed for long-term investors who need timely but not overwhelming alerts.

Setup:
1. Create Telegram bot via @BotFather
2. Get your chat_id by messaging @userinfobot
3. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env
"""
from typing import Optional, List, Dict
from datetime import datetime
import asyncio

from sqlalchemy.orm import Session
from loguru import logger

from app.config.settings import Settings


class NotificationService:
    """
    Unified notification service for investment alerts.
    
    Channels:
    - Telegram (primary, real-time)
    - Email (digest, daily/weekly)
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.settings = Settings()
        
        # Telegram config
        self.telegram_token = getattr(self.settings, 'TELEGRAM_BOT_TOKEN', None)
        self.telegram_chat_id = getattr(self.settings, 'TELEGRAM_CHAT_ID', None)
        
        self.telegram_enabled = bool(self.telegram_token and self.telegram_chat_id)
        
        if self.telegram_enabled:
            logger.info("📱 Telegram notifications enabled")
        else:
            logger.warning("📱 Telegram not configured - set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
    
    async def _send_telegram(self, message: str, parse_mode: str = "HTML") -> bool:
        """
        Send message via Telegram Bot API.
        
        Args:
            message: Message text (supports HTML formatting)
            parse_mode: "HTML" or "Markdown"
        
        Returns:
            True if sent successfully
        """
        if not self.telegram_enabled:
            logger.warning("Telegram not configured")
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
                    logger.info("📤 Telegram message sent")
                    return True
                else:
                    logger.error(f"Telegram error: {response.text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False
    
    async def send_test_notification(self) -> bool:
        """Send a test notification to verify setup."""
        
        message = (
            "🧪 <b>Akcion Test Notification</b>\n\n"
            "✅ Your investment alerts are configured correctly!\n\n"
            f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        
        return await self._send_telegram(message)
    
    async def send_opportunity_alert(self, decision) -> bool:
        """
        Send alert for STRONG_BUY opportunity.
        
        This is the most important alert - price is right and thesis is strong.
        """
        from app.services.investment_engine import InvestmentDecision
        
        if not isinstance(decision, InvestmentDecision):
            return False
        
        emoji = "🟢" if decision.action.value == "STRONG_BUY" else "🔵"
        
        message = (
            f"{emoji} <b>INVESTMENT OPPORTUNITY</b>\n\n"
            f"<b>{decision.ticker}</b> - {decision.company_name or ''}\n"
            f"Action: <b>{decision.action.value}</b>\n"
            f"Confidence: {decision.confidence:.0%}\n\n"
            f"💰 Price: ${decision.current_price:.2f}\n"
        )
        
        if decision.in_entry_zone:
            message += f"✅ <b>IN ENTRY ZONE</b> ({decision.entry_zone})\n"
        
        if decision.price_vs_target:
            message += f"🎯 {decision.price_vs_target}\n"
        
        message += f"\n📊 Thesis: {decision.thesis_status.value}\n"
        
        if decision.gomes_score:
            message += f"⭐ Gomes Score: {decision.gomes_score}/10\n"
        
        if decision.edge:
            edge_short = decision.edge[:100] + "..." if len(decision.edge) > 100 else decision.edge
            message += f"\n💡 Edge: {edge_short}\n"
        
        if decision.catalysts:
            cat_short = decision.catalysts[:100] + "..." if len(decision.catalysts) > 100 else decision.catalysts
            message += f"🚀 Catalysts: {cat_short}\n"
        
        message += f"\n📝 {decision.action_detail}"
        
        return await self._send_telegram(message)
    
    async def send_entry_zone_alert(self, decision) -> bool:
        """
        Send alert when stock enters buy zone.
        """
        from app.services.investment_engine import InvestmentDecision
        
        if not isinstance(decision, InvestmentDecision):
            return False
        
        message = (
            f"🎯 <b>ENTRY ZONE ALERT</b>\n\n"
            f"<b>{decision.ticker}</b> is now in your entry zone!\n\n"
            f"💰 Current: ${decision.current_price:.2f}\n"
            f"📍 Entry Zone: {decision.entry_zone}\n"
            f"📊 Thesis: {decision.thesis_status.value}\n"
        )
        
        if decision.gomes_score:
            message += f"⭐ Gomes Score: {decision.gomes_score}/10\n"
        
        if decision.gomes_sentiment:
            message += f"📈 Sentiment: {decision.gomes_sentiment}\n"
        
        message += f"\n💡 <b>Action:</b> {decision.action_detail}"
        
        return await self._send_telegram(message)
    
    async def send_exit_alert(self, decision) -> bool:
        """
        Send alert when thesis is broken or exit recommended.
        """
        from app.services.investment_engine import InvestmentDecision
        
        if not isinstance(decision, InvestmentDecision):
            return False
        
        message = (
            f"🔴 <b>EXIT ALERT</b>\n\n"
            f"<b>{decision.ticker}</b> - Consider exiting position\n\n"
            f"💰 Current: ${decision.current_price:.2f}\n"
            f"📊 Thesis: <b>{decision.thesis_status.value}</b>\n"
            f"⚠️ Confidence: {decision.confidence:.0%}\n\n"
            f"<b>Reasoning:</b>\n"
        )
        
        for reason in decision.reasoning[:5]:
            message += f"• {reason}\n"
        
        if decision.risk_matches:
            message += f"\n⚠️ Risk flags: {', '.join(decision.risk_matches[:3])}\n"
        
        message += f"\n📝 {decision.action_detail}"
        
        return await self._send_telegram(message)
    
    async def send_news_alert(self, news_item, ticker: str) -> bool:
        """
        Send alert for important news.
        """
        from app.services.news_monitor import NewsItem, NewsUrgency
        
        if not isinstance(news_item, NewsItem):
            return False
        
        # Only send for important news
        if news_item.urgency not in [NewsUrgency.ACTION_REQUIRED, NewsUrgency.IMPORTANT]:
            return True  # Skip but return success
        
        sentiment_emoji = {
            "BULLISH": "📈",
            "BEARISH": "📉",
            "NEUTRAL": "➖"
        }.get(news_item.sentiment.value, "📰")
        
        urgency_emoji = "🚨" if news_item.urgency == NewsUrgency.ACTION_REQUIRED else "📰"
        
        message = (
            f"{urgency_emoji} <b>NEWS: {ticker}</b>\n\n"
            f"{sentiment_emoji} <b>{news_item.title}</b>\n\n"
        )
        
        if news_item.summary:
            summary = news_item.summary[:200] + "..." if len(news_item.summary) > 200 else news_item.summary
            message += f"{summary}\n\n"
        
        message += f"📊 Sentiment: {news_item.sentiment.value}\n"
        message += f"🎯 Relevance: {news_item.relevance_score:.0%}\n"
        
        if news_item.matched_catalysts:
            message += f"🚀 Catalysts: {', '.join(news_item.matched_catalysts[:3])}\n"
        
        if news_item.matched_risks:
            message += f"⚠️ Risks: {', '.join(news_item.matched_risks[:3])}\n"
        
        if news_item.gomes_alignment and news_item.gomes_alignment != 'N/A':
            message += f"🔗 Gomes Alignment: {news_item.gomes_alignment}\n"
        
        if news_item.action_suggestion:
            message += f"\n💡 <b>{news_item.action_suggestion}</b>\n"
        
        message += f"\n🔗 {news_item.url}"
        
        return await self._send_telegram(message)
    
    async def send_daily_digest(self, decisions: List) -> bool:
        """
        Send daily digest of all investment positions.
        """
        from app.services.investment_engine import InvestmentDecision, InvestmentAction
        
        if not decisions:
            return True
        
        # Group by action
        strong_buys = [d for d in decisions if d.action == InvestmentAction.STRONG_BUY]
        accumulate = [d for d in decisions if d.action == InvestmentAction.ACCUMULATE]
        watch = [d for d in decisions if d.action == InvestmentAction.WATCH]
        holds = [d for d in decisions if d.action == InvestmentAction.HOLD]
        exits = [d for d in decisions if d.action == InvestmentAction.EXIT]
        
        message = (
            f"📊 <b>DAILY INVESTMENT DIGEST</b>\n"
            f"📅 {datetime.now().strftime('%Y-%m-%d')}\n\n"
        )
        
        if strong_buys:
            message += "🟢 <b>STRONG BUY:</b>\n"
            for d in strong_buys:
                message += f"  • {d.ticker} @ ${d.current_price:.2f}\n"
        
        if accumulate:
            message += "\n🔵 <b>ACCUMULATE:</b>\n"
            for d in accumulate:
                message += f"  • {d.ticker} @ ${d.current_price:.2f}\n"
        
        if exits:
            message += "\n🔴 <b>EXIT:</b>\n"
            for d in exits:
                message += f"  • {d.ticker} @ ${d.current_price:.2f}\n"
        
        message += f"\n📈 Watching: {len(watch)} stocks\n"
        message += f"💼 Holding: {len(holds)} positions\n"
        
        # Entry zone summary
        in_zones = [d for d in decisions if d.in_entry_zone]
        if in_zones:
            message += f"\n🎯 <b>In Entry Zone:</b> {', '.join([d.ticker for d in in_zones])}"
        
        return await self._send_telegram(message)
