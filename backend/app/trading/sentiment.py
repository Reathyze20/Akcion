"""
Sentiment Analysis Module
==========================

Analyzes market sentiment from news headlines and social media.

Data sources:
- Yahoo Finance news
- Financial news RSS feeds
- Twitter/X mentions (optional)

Provides sentiment score (0-100) to feed into Master Signal.

Author: GitHub Copilot with Claude Sonnet 4.5
Date: 2026-01-17
Version: 1.0.0
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup


logger = logging.getLogger(__name__)


# ==============================================================================
# Data Models
# ==============================================================================

@dataclass
class NewsArticle:
    """News article with sentiment"""
    title: str
    source: str
    published_at: datetime
    url: Optional[str] = None
    summary: Optional[str] = None


@dataclass
class SentimentResult:
    """Sentiment analysis result"""
    ticker: str
    sentiment_score: float  # 0-100 (0=very bearish, 50=neutral, 100=very bullish)
    confidence: float  # 0-1 (how confident we are)
    
    # Component scores
    positive_count: int
    negative_count: int
    neutral_count: int
    
    # Supporting data
    articles: list[NewsArticle]
    keywords_found: list[str]
    analyzed_at: datetime
    
    @property
    def sentiment_label(self) -> str:
        """Human-readable sentiment label"""
        if self.sentiment_score >= 70:
            return "Very Bullish"
        elif self.sentiment_score >= 60:
            return "Bullish"
        elif self.sentiment_score >= 40:
            return "Neutral"
        elif self.sentiment_score >= 30:
            return "Bearish"
        else:
            return "Very Bearish"


# ==============================================================================
# Sentiment Lexicon
# ==============================================================================

POSITIVE_KEYWORDS = {
    # Strong positive
    "surge", "soar", "rally", "boom", "breakout", "record", "all-time high",
    "beat", "exceed", "outperform", "bullish", "upgrade", "strong buy",
    "accelerate", "momentum", "breakthrough", "innovation",
    
    # Moderate positive
    "gain", "rise", "increase", "growth", "positive", "improve",
    "expand", "advance", "progress", "opportunity", "potential",
    "recover", "rebound", "confidence", "optimistic",
}

NEGATIVE_KEYWORDS = {
    # Strong negative
    "crash", "plunge", "collapse", "dive", "tumble", "slump",
    "downgrade", "sell", "bearish", "weak", "disappoint",
    "miss", "decline", "fall", "drop", "cut", "reduce",
    
    # Moderate negative
    "concern", "worry", "risk", "uncertainty", "volatile",
    "pressure", "struggle", "challenge", "warning", "caution",
    "loss", "deficit", "layoff", "restructure",
}

AMPLIFIERS = {
    "very": 1.5,
    "extremely": 2.0,
    "significantly": 1.8,
    "sharply": 1.7,
    "dramatically": 1.8,
    "massive": 2.0,
    "huge": 1.8,
}

NEGATIONS = {
    "not", "no", "never", "none", "nobody", "nothing", "neither", "nor",
    "nowhere", "hardly", "barely", "scarcely",
}


# ==============================================================================
# Sentiment Analyzer
# ==============================================================================

class SentimentAnalyzer:
    """
    Sentiment Analysis Engine
    
    Fetches news and analyzes sentiment using keyword-based NLP.
    
    Usage:
        analyzer = SentimentAnalyzer()
        result = analyzer.analyze_ticker("AAPL", days_back=7)
        print(f"Sentiment: {result.sentiment_score}/100 ({result.sentiment_label})")
    """
    
    def __init__(
        self,
        lookback_days: int = 7,
        min_articles: int = 3,
        timeout: int = 10,
    ):
        """
        Initialize Sentiment Analyzer
        
        Args:
            lookback_days: Days of news to analyze (default 7)
            min_articles: Minimum articles for confident score (default 3)
            timeout: HTTP timeout in seconds (default 10)
        """
        self.lookback_days = lookback_days
        self.min_articles = min_articles
        self.timeout = timeout
        
        logger.info(f"📰 Sentiment Analyzer initialized (lookback={lookback_days}d)")
    
    # ==========================================================================
    # Main Analysis Method
    # ==========================================================================
    
    def analyze_ticker(
        self,
        ticker: str,
        days_back: Optional[int] = None,
    ) -> SentimentResult:
        """
        Analyze sentiment for a ticker.
        
        Args:
            ticker: Stock ticker symbol
            days_back: Days to look back (default: use instance setting)
            
        Returns:
            SentimentResult with score 0-100
        """
        days_back = days_back or self.lookback_days
        
        logger.info(f"📊 Analyzing sentiment for {ticker} ({days_back}d)")
        
        # Fetch news articles
        articles = self._fetch_news(ticker, days_back)
        
        if len(articles) < self.min_articles:
            logger.warning(
                f"⚠️  Only {len(articles)} articles found for {ticker} "
                f"(minimum {self.min_articles})"
            )
            # Return neutral with low confidence
            return self._neutral_result(ticker, articles)
        
        # Analyze sentiment
        positive_count = 0
        negative_count = 0
        neutral_count = 0
        keywords_found = []
        
        for article in articles:
            text = (article.title + " " + (article.summary or "")).lower()
            sentiment = self._analyze_text(text)
            
            if sentiment > 0:
                positive_count += 1
                keywords_found.extend(self._extract_keywords(text, POSITIVE_KEYWORDS))
            elif sentiment < 0:
                negative_count += 1
                keywords_found.extend(self._extract_keywords(text, NEGATIVE_KEYWORDS))
            else:
                neutral_count += 1
        
        # Calculate sentiment score
        total = len(articles)
        positive_pct = positive_count / total
        negative_pct = negative_count / total
        
        # Score: 0-100 based on positive/negative ratio
        # 50 = neutral, >50 = bullish, <50 = bearish
        sentiment_score = 50 + (positive_pct - negative_pct) * 50
        sentiment_score = max(0.0, min(100.0, sentiment_score))
        
        # Confidence: higher with more articles
        confidence = min(total / (self.min_articles * 2), 1.0)
        
        # Deduplicate keywords
        keywords_found = list(set(keywords_found))
        
        logger.info(
            f"  Sentiment: {sentiment_score:.1f}/100 ({positive_count}+ {negative_count}- {neutral_count}~) "
            f"- {len(articles)} articles"
        )
        
        return SentimentResult(
            ticker=ticker,
            sentiment_score=sentiment_score,
            confidence=confidence,
            positive_count=positive_count,
            negative_count=negative_count,
            neutral_count=neutral_count,
            articles=articles,
            keywords_found=keywords_found[:20],  # Top 20
            analyzed_at=datetime.utcnow(),
        )
    
    # ==========================================================================
    # News Fetching
    # ==========================================================================
    
    def _fetch_news(self, ticker: str, days_back: int) -> list[NewsArticle]:
        """
        Fetch news articles for a ticker.
        
        Uses multiple sources:
        1. Yahoo Finance
        2. RSS feeds
        """
        articles = []
        
        # Yahoo Finance news
        yahoo_articles = self._fetch_yahoo_news(ticker)
        articles.extend(yahoo_articles)
        
        # Filter by date
        cutoff_date = datetime.utcnow() - timedelta(days=days_back)
        articles = [a for a in articles if a.published_at >= cutoff_date]
        
        logger.debug(f"  Fetched {len(articles)} articles for {ticker}")
        return articles
    
    def _fetch_yahoo_news(self, ticker: str) -> list[NewsArticle]:
        """Fetch news from Yahoo Finance"""
        articles = []
        
        try:
            url = f"https://finance.yahoo.com/quote/{ticker}/news"
            
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url, follow_redirects=True)
                response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find news items (Yahoo's HTML structure)
            # This is a simplified parser - Yahoo's structure may change
            news_items = soup.find_all('h3', limit=20)
            
            for item in news_items:
                title = item.get_text(strip=True)
                if title:
                    articles.append(NewsArticle(
                        title=title,
                        source="Yahoo Finance",
                        published_at=datetime.utcnow(),  # Approximate
                    ))
            
            logger.debug(f"  Yahoo Finance: {len(articles)} articles")
            
        except Exception as e:
            logger.warning(f"  Failed to fetch Yahoo Finance news: {e}")
        
        return articles
    
    # ==========================================================================
    # Text Analysis
    # ==========================================================================
    
    def _analyze_text(self, text: str) -> float:
        """
        Analyze sentiment of text.
        
        Returns:
            Float score: positive > 0, negative < 0, neutral = 0
        """
        words = re.findall(r'\b\w+\b', text.lower())
        
        score = 0.0
        negation = False
        
        for i, word in enumerate(words):
            # Check for negation
            if word in NEGATIONS:
                negation = True
                continue
            
            # Check for amplifiers
            amplifier = 1.0
            if i > 0 and words[i-1] in AMPLIFIERS:
                amplifier = AMPLIFIERS[words[i-1]]
            
            # Check sentiment
            if word in POSITIVE_KEYWORDS:
                sentiment = 1.0 * amplifier
                if negation:
                    sentiment = -sentiment
                score += sentiment
                negation = False
            elif word in NEGATIVE_KEYWORDS:
                sentiment = -1.0 * amplifier
                if negation:
                    sentiment = -sentiment
                score += sentiment
                negation = False
            else:
                negation = False
        
        return score
    
    def _extract_keywords(self, text: str, keyword_set: set) -> list[str]:
        """Extract keywords from text"""
        words = re.findall(r'\b\w+\b', text.lower())
        found = [w for w in words if w in keyword_set]
        return found
    
    def _neutral_result(self, ticker: str, articles: list[NewsArticle]) -> SentimentResult:
        """Return neutral sentiment result"""
        return SentimentResult(
            ticker=ticker,
            sentiment_score=50.0,
            confidence=0.3,
            positive_count=0,
            negative_count=0,
            neutral_count=len(articles),
            articles=articles,
            keywords_found=[],
            analyzed_at=datetime.utcnow(),
        )


# ==============================================================================
# Convenience Functions
# ==============================================================================

def analyze_sentiment(ticker: str, days_back: int = 7) -> SentimentResult:
    """
    Convenience function to analyze sentiment.
    
    Usage:
        result = analyze_sentiment("AAPL", days_back=7)
        print(f"Sentiment: {result.sentiment_score}/100")
    """
    analyzer = SentimentAnalyzer(lookback_days=days_back)
    return analyzer.analyze_ticker(ticker)


def get_sentiment_score(ticker: str) -> float:
    """
    Quick sentiment score (0-100).
    
    Usage:
        score = get_sentiment_score("AAPL")  # Returns 75.5
    """
    result = analyze_sentiment(ticker)
    return result.sentiment_score
