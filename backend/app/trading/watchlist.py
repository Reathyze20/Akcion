"""
Watchlist Builder - Extracts BUY/BULLISH tickers from AI analyst verdicts
"""
from typing import List, Dict
from sqlalchemy.orm import Session
from datetime import datetime

from app.models.stock import Stock
from app.models.trading import ActiveWatchlist
from loguru import logger


class WatchlistBuilder:
    """Manages active watchlist based on analyst recommendations"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def sync_watchlist(self) -> Dict[str, int]:
        """
        Synchronize watchlist with latest analyst recommendations
        
        Returns:
            Dict with added/updated/removed counts
        """
        logger.info("Starting watchlist sync...")
        
        # Get BUY-rated stocks from analyst verdicts or Bullish sentiment
        # First try action_verdict, fallback to sentiment
        from sqlalchemy import or_
        
        buy_stocks = self.db.query(Stock).filter(
            or_(
                Stock.action_verdict.in_(['BUY', 'STRONG BUY', 'ACCUMULATE', 'BULLISH']),
                Stock.sentiment.ilike('%bullish%')
            )
        ).all()
        
        buy_tickers = {stock.ticker: stock for stock in buy_stocks}
        logger.info(f"Found {len(buy_tickers)} BUY-rated tickers from analysts")
        
        # Get current active watchlist
        existing_watchlist = {
            w.ticker: w for w in self.db.query(ActiveWatchlist).filter(
                ActiveWatchlist.is_active == True
            ).all()
        }
        
        added_count = 0
        updated_count = 0
        removed_count = 0
        
        # Add new tickers
        for ticker, stock in buy_tickers.items():
            if ticker not in existing_watchlist:
                # Add new entry
                watchlist_entry = ActiveWatchlist(
                    ticker=ticker,
                    stock_id=stock.id,
                    action_verdict=stock.action_verdict,
                    confidence_score=self._parse_confidence(stock.sentiment),
                    notes=f"Added from analyst {stock.company_name or ticker}"
                )
                self.db.add(watchlist_entry)
                added_count += 1
                logger.debug(f"Added {ticker} to watchlist")
            else:
                # Update existing entry
                entry = existing_watchlist[ticker]
                entry.action_verdict = stock.action_verdict
                entry.confidence_score = self._parse_confidence(stock.sentiment)
                entry.last_updated = datetime.utcnow()
                updated_count += 1
                logger.debug(f"Updated {ticker} in watchlist")
        
        # Remove tickers no longer BUY-rated
        for ticker, entry in existing_watchlist.items():
            if ticker not in buy_tickers:
                entry.is_active = False
                entry.notes = f"Removed - no longer BUY rated"
                removed_count += 1
                logger.debug(f"Deactivated {ticker} from watchlist")
        
        self.db.commit()
        
        result = {
            'added': added_count,
            'updated': updated_count,
            'removed': removed_count,
            'total_active': len(buy_tickers)
        }
        
        logger.info(f"Watchlist sync completed: {result}")
        return result
    
    def get_active_tickers(self) -> List[str]:
        """Get list of all active watchlist tickers"""
        return [
            w.ticker for w in self.db.query(ActiveWatchlist.ticker).filter(
                ActiveWatchlist.is_active == True
            ).all()
        ]
    
    def add_ticker(self, ticker: str, stock_id: int, verdict: str, confidence: float = 0.7) -> ActiveWatchlist:
        """Manually add a ticker to watchlist"""
        entry = ActiveWatchlist(
            ticker=ticker,
            stock_id=stock_id,
            action_verdict=verdict,
            confidence_score=confidence,
            notes="Manually added"
        )
        self.db.add(entry)
        self.db.commit()
        logger.info(f"Manually added {ticker} to watchlist")
        return entry
    
    def remove_ticker(self, ticker: str):
        """Remove ticker from active watchlist"""
        entry = self.db.query(ActiveWatchlist).filter(
            ActiveWatchlist.ticker == ticker,
            ActiveWatchlist.is_active == True
        ).first()
        
        if entry:
            entry.is_active = False
            entry.notes = "Manually removed"
            self.db.commit()
            logger.info(f"Removed {ticker} from watchlist")
        
    def _parse_confidence(self, sentiment: str) -> float:
        """Convert sentiment string to confidence score"""
        if not sentiment:
            return 0.7
        
        sentiment = sentiment.upper()
        if 'STRONG' in sentiment or 'HIGH' in sentiment:
            return 0.9
        elif 'MODERATE' in sentiment:
            return 0.7
        elif 'LOW' in sentiment or 'WEAK' in sentiment:
            return 0.5
        else:
            return 0.7
