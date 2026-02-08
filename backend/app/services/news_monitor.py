"""
News Monitoring Service - Investment Intelligence

Monitors news sources for watchlist stocks and classifies importance
for long-term investing decisions.

Key Features:
- Polygon.io news API integration
- AI-powered importance classification
- Keyword matching for catalysts/risks
- Entry zone price alerts
"""
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import asyncio
import re

from sqlalchemy.orm import Session
from sqlalchemy import text
from loguru import logger

from app.config.settings import Settings
from app.models.trading import ActiveWatchlist, OHLCVData


# =============================================================================
# ENUMS & DATA CLASSES
# =============================================================================

class NewsUrgency(str, Enum):
    """Urgency level for investment decisions"""
    ACTION_REQUIRED = "ACTION_REQUIRED"  # Price in entry zone, major catalyst
    IMPORTANT = "IMPORTANT"              # Significant news, review soon
    INFORMATIVE = "INFORMATIVE"          # FYI, no action needed
    NOISE = "NOISE"                      # Filtered out, not relevant


class NewsSentiment(str, Enum):
    """News sentiment classification"""
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


@dataclass
class NewsItem:
    """Processed news item with classification"""
    ticker: str
    title: str
    summary: str
    source: str
    published_at: datetime
    url: str
    
    # Classification
    urgency: NewsUrgency
    sentiment: NewsSentiment
    relevance_score: float  # 0-1
    
    # Matched patterns
    matched_catalysts: List[str]
    matched_risks: List[str]
    matched_keywords: List[str]
    
    # Context
    gomes_alignment: Optional[str]  # ALIGNED, CONFLICT, N/A
    action_suggestion: Optional[str]


@dataclass
class PriceAlert:
    """Price-based investment alert"""
    ticker: str
    alert_type: str  # ENTRY_ZONE, TARGET_REACHED, STOP_LOSS
    current_price: float
    trigger_price: float
    message: str
    urgency: NewsUrgency
    gomes_context: Optional[Dict]


# =============================================================================
# NEWS MONITOR SERVICE
# =============================================================================

class NewsMonitorService:
    """
    Long-term investment news monitoring service.
    
    Philosophy: Not trading signals, but investment intelligence.
    - Filter noise, surface what matters
    - Align with Gomes analysis thesis
    - Entry zone and catalyst alerts
    """
    
    # High-importance keywords for long-term investing
    CATALYST_KEYWORDS = [
        'earnings beat', 'revenue beat', 'guidance raised', 'upgrade',
        'fda approval', 'patent', 'contract win', 'acquisition',
        'buyback', 'dividend increase', 'insider buying',
        'defense budget', 'government contract', 'regulatory approval',
        'expansion', 'new product', 'partnership', 'breakthrough'
    ]
    
    RISK_KEYWORDS = [
        'earnings miss', 'revenue miss', 'guidance cut', 'downgrade',
        'sec investigation', 'lawsuit', 'recall', 'bankruptcy',
        'dilution', 'offering', 'insider selling', 'fraud',
        'delisting', 'going concern', 'default', 'layoffs'
    ]
    
    NOISE_KEYWORDS = [
        'price target', 'analyst note', 'technical analysis',
        'short interest', 'options activity', 'trading volume'
    ]
    
    def __init__(self, db: Session):
        self.db = db
        self.settings = Settings()
        self.polygon_api_key = self.settings.massive_api_key  # Polygon.io API key
        
        logger.info("News Monitor Service initialized")
    
    async def fetch_news_polygon(
        self, 
        ticker: str,
        limit: int = 10,
        days_back: int = 7
    ) -> List[Dict]:
        """
        Fetch news from Polygon.io API
        
        Args:
            ticker: Stock ticker
            limit: Max articles to fetch
            days_back: How many days back to search
        
        Returns:
            List of raw news articles from Polygon
        """
        import httpx
        
        if not self.polygon_api_key:
            logger.warning("No Polygon API key configured")
            return []
        
        try:
            published_after = (datetime.utcnow() - timedelta(days=days_back)).strftime('%Y-%m-%d')
            
            url = (
                f"https://api.polygon.io/v2/reference/news"
                f"?ticker={ticker}"
                f"&published_utc.gte={published_after}"
                f"&limit={limit}"
                f"&sort=published_utc"
                f"&order=desc"
                f"&apiKey={self.polygon_api_key}"
            )
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()
                
                articles = data.get('results', [])
                logger.info(f"Fetched {len(articles)} news articles for {ticker}")
                return articles
                
        except Exception as e:
            logger.error(f"Failed to fetch news for {ticker}: {e}")
            return []
    
    def classify_news(
        self,
        article: Dict,
        ticker: str,
        gomes_context: Optional[Dict] = None
    ) -> NewsItem:
        """
        Classify a news article for investment relevance.
        
        Considers:
        - Keyword matching (catalysts, risks)
        - Alignment with Gomes thesis
        - Source credibility
        - Recency
        """
        title = article.get('title', '').lower()
        description = article.get('description', '').lower()
        full_text = f"{title} {description}"
        
        # Match catalysts and risks
        matched_catalysts = [kw for kw in self.CATALYST_KEYWORDS if kw in full_text]
        matched_risks = [kw for kw in self.RISK_KEYWORDS if kw in full_text]
        is_noise = any(kw in full_text for kw in self.NOISE_KEYWORDS)
        
        # Calculate relevance score
        relevance_score = 0.0
        
        if matched_catalysts:
            relevance_score += 0.3 * len(matched_catalysts)
        if matched_risks:
            relevance_score += 0.3 * len(matched_risks)
        
        # Check Gomes alignment
        gomes_alignment = 'N/A'
        if gomes_context:
            gomes_edge = (gomes_context.get('edge') or '').lower()
            gomes_catalysts = (gomes_context.get('catalysts') or '').lower()
            
            # Check if news aligns with Gomes thesis
            if any(word in full_text for word in gomes_edge.split()[:5] if len(word) > 4):
                gomes_alignment = 'ALIGNED'
                relevance_score += 0.3
            
            if any(word in full_text for word in gomes_catalysts.split()[:5] if len(word) > 4):
                gomes_alignment = 'CATALYST_MATCH'
                relevance_score += 0.4
        
        relevance_score = min(1.0, relevance_score)
        
        # Determine sentiment
        if len(matched_catalysts) > len(matched_risks):
            sentiment = NewsSentiment.BULLISH
        elif len(matched_risks) > len(matched_catalysts):
            sentiment = NewsSentiment.BEARISH
        else:
            sentiment = NewsSentiment.NEUTRAL
        
        # Determine urgency
        if is_noise and relevance_score < 0.3:
            urgency = NewsUrgency.NOISE
        elif relevance_score >= 0.6 or gomes_alignment in ['ALIGNED', 'CATALYST_MATCH']:
            urgency = NewsUrgency.IMPORTANT
        elif relevance_score >= 0.3:
            urgency = NewsUrgency.INFORMATIVE
        else:
            urgency = NewsUrgency.NOISE
        
        # Action suggestion
        action_suggestion = None
        if urgency == NewsUrgency.IMPORTANT:
            if sentiment == NewsSentiment.BULLISH:
                action_suggestion = "Review for potential accumulation opportunity"
            elif sentiment == NewsSentiment.BEARISH:
                action_suggestion = "Review thesis - potential risk to position"
        
        return NewsItem(
            ticker=ticker,
            title=article.get('title', ''),
            summary=article.get('description', ''),
            source=article.get('publisher', {}).get('name', 'Unknown'),
            published_at=datetime.fromisoformat(
                article.get('published_utc', '').replace('Z', '+00:00')
            ) if article.get('published_utc') else datetime.utcnow(),
            url=article.get('article_url', ''),
            urgency=urgency,
            sentiment=sentiment,
            relevance_score=relevance_score,
            matched_catalysts=matched_catalysts,
            matched_risks=matched_risks,
            matched_keywords=matched_catalysts + matched_risks,
            gomes_alignment=gomes_alignment,
            action_suggestion=action_suggestion
        )
    
    async def check_entry_zones(self) -> List[PriceAlert]:
        """
        Check if any watchlist stocks are in their entry zones.
        
        Entry zone = price level where Gomes recommends accumulating.
        """
        from app.models.stock import Stock
        
        alerts = []
        
        try:
            # Get active watchlist with Gomes context
            watchlist_items = self.db.query(ActiveWatchlist).filter(
                ActiveWatchlist.is_active == True,
                ActiveWatchlist.stock_id.isnot(None)
            ).all()
            
            for item in watchlist_items:
                stock = self.db.query(Stock).filter(Stock.id == item.stock_id).first()
                if not stock or not stock.entry_zone:
                    continue
                
                # Get current price
                latest_price = self.db.query(OHLCVData).filter(
                    OHLCVData.ticker == item.ticker
                ).order_by(OHLCVData.time.desc()).first()
                
                if not latest_price:
                    continue
                
                current_price = float(latest_price.close)
                
                # Parse entry zone (e.g., "Under $5", "4.50-5.00", "Pullback to $4")
                entry_price = self._parse_entry_zone(stock.entry_zone, current_price)
                
                if entry_price and current_price <= entry_price:
                    alerts.append(PriceAlert(
                        ticker=item.ticker,
                        alert_type="ENTRY_ZONE",
                        current_price=current_price,
                        trigger_price=entry_price,
                        message=f"{item.ticker} at ${current_price:.2f} - IN ENTRY ZONE (${entry_price:.2f}). Gomes: {stock.action_verdict or 'ACCUMULATE'}",
                        urgency=NewsUrgency.ACTION_REQUIRED,
                        gomes_context={
                            'score': stock.conviction_score,
                            'sentiment': stock.sentiment,
                            'action': stock.action_verdict,
                            'edge': stock.edge,
                            'entry_zone': stock.entry_zone
                        }
                    ))
                    
                    logger.info(f"ENTRY ZONE ALERT: {item.ticker} at ${current_price:.2f}")
            
            return alerts
            
        except Exception as e:
            logger.error(f"Entry zone check failed: {e}")
            return []
    
    def _parse_entry_zone(self, entry_zone: str, current_price: float) -> Optional[float]:
        """
        Parse entry zone string to numeric value.
        
        Examples:
        - "Under $5" → 5.0
        - "$4.50-$5.00" → 5.0 (upper bound)
        - "Pullback to $4" → 4.0
        - "Below 4.50" → 4.5
        """
        if not entry_zone:
            return None
        
        entry_lower = entry_zone.lower()
        
        # Find all dollar amounts
        prices = re.findall(r'\$?([\d.]+)', entry_lower)
        
        if not prices:
            return None
        
        try:
            # If multiple prices, take the higher one as entry ceiling
            float_prices = [float(p) for p in prices if float(p) < current_price * 2]
            if float_prices:
                return max(float_prices)
        except ValueError:
            pass
        
        return None
    
    async def scan_watchlist(self) -> Dict[str, List]:
        """
        Full scan of watchlist for news and price alerts.
        
        Returns:
            Dict with 'news_alerts' and 'price_alerts' lists
        """
        from app.models.stock import Stock
        
        news_alerts = []
        price_alerts = []
        
        # Get active watchlist
        watchlist = self.db.query(ActiveWatchlist).filter(
            ActiveWatchlist.is_active == True
        ).all()
        
        logger.info(f"Scanning {len(watchlist)} watchlist items...")
        
        for item in watchlist:
            # Get Gomes context if available
            gomes_context = None
            if item.stock_id:
                stock = self.db.query(Stock).filter(Stock.id == item.stock_id).first()
                if stock:
                    gomes_context = {
                        'edge': stock.edge,
                        'catalysts': stock.catalysts,
                        'risks': stock.risks,
                        'sentiment': stock.sentiment,
                        'score': stock.conviction_score
                    }
            
            # Fetch and classify news
            articles = await self.fetch_news_polygon(item.ticker)
            
            for article in articles:
                classified = self.classify_news(article, item.ticker, gomes_context)
                
                # Only include important/informative news
                if classified.urgency not in [NewsUrgency.NOISE]:
                    news_alerts.append(classified)
        
        # Check entry zones
        price_alerts = await self.check_entry_zones()
        
        # Sort by urgency and relevance
        news_alerts.sort(key=lambda x: (
            x.urgency == NewsUrgency.ACTION_REQUIRED,
            x.urgency == NewsUrgency.IMPORTANT,
            x.relevance_score
        ), reverse=True)
        
        logger.info(
            f"Scan complete: {len(news_alerts)} news alerts, "
            f"{len(price_alerts)} price alerts"
        )
        
        return {
            'news_alerts': news_alerts,
            'price_alerts': price_alerts
        }
    
    def news_item_to_dict(self, item: NewsItem) -> Dict:
        """Convert NewsItem to JSON-serializable dict"""
        return {
            'ticker': item.ticker,
            'title': item.title,
            'summary': item.summary,
            'source': item.source,
            'published_at': item.published_at.isoformat(),
            'url': item.url,
            'urgency': item.urgency.value,
            'sentiment': item.sentiment.value,
            'relevance_score': item.relevance_score,
            'matched_catalysts': item.matched_catalysts,
            'matched_risks': item.matched_risks,
            'gomes_alignment': item.gomes_alignment,
            'action_suggestion': item.action_suggestion
        }
    
    def price_alert_to_dict(self, alert: PriceAlert) -> Dict:
        """Convert PriceAlert to JSON-serializable dict"""
        return {
            'ticker': alert.ticker,
            'alert_type': alert.alert_type,
            'current_price': alert.current_price,
            'trigger_price': alert.trigger_price,
            'message': alert.message,
            'urgency': alert.urgency.value,
            'gomes_context': alert.gomes_context
        }
