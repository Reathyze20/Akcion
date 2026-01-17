"""
Data Fetcher - Retrieves OHLCV data from Massive.com API
"""
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import time

from app.config.settings import Settings
from app.services.market_data import MarketDataService
from app.models.trading import OHLCVData, DataSyncLog
from loguru import logger


class DataFetcher:
    """Fetches and stores OHLCV time-series data for watchlist tickers"""
    
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings
    
    async def fetch_historical_data(
        self,
        ticker: str,
        days: int = 60,
        sync_type: str = 'manual'
    ) -> Dict[str, any]:
        """
        Fetch historical OHLCV data for a ticker
        
        Args:
            ticker: Stock ticker symbol
            days: Number of days of historical data
            sync_type: 'daily', 'manual', or 'initial'
        
        Returns:
            Dict with status and records synced
        """
        start_time = time.time()
        from_date = datetime.now() - timedelta(days=days)
        to_date = datetime.now()
        
        logger.info(f"Fetching {days} days of data for {ticker}")
        
        try:
            # Use yfinance for historical data (Massive.com Starter doesn't have historical endpoint)
            import yfinance as yf
            
            stock = yf.Ticker(ticker)
            hist = stock.history(period=f"{days}d")
            
            if hist.empty:
                raise ValueError(f"No data returned for {ticker}")
            
            records_synced = 0
            
            # Store each day's OHLCV data
            for date, row in hist.iterrows():
                ohlcv = OHLCVData(
                    time=date.to_pydatetime().replace(tzinfo=None),
                    ticker=ticker,
                    open=float(row['Open']),
                    high=float(row['High']),
                    low=float(row['Low']),
                    close=float(row['Close']),
                    volume=int(row['Volume']),
                    vwap=float((row['High'] + row['Low'] + row['Close']) / 3)  # Approximation
                )
                
                # Use merge to avoid duplicates
                existing = self.db.query(OHLCVData).filter(
                    OHLCVData.time == ohlcv.time,
                    OHLCVData.ticker == ticker
                ).first()
                
                if not existing:
                    self.db.add(ohlcv)
                    records_synced += 1
            
            self.db.commit()
            
            # Log successful sync
            duration = int(time.time() - start_time)
            log_entry = DataSyncLog(
                ticker=ticker,
                sync_type=sync_type,
                records_synced=records_synced,
                from_date=from_date.date(),
                to_date=to_date.date(),
                status='success',
                duration_seconds=duration
            )
            self.db.add(log_entry)
            self.db.commit()
            
            logger.info(f"Successfully synced {records_synced} records for {ticker} in {duration}s")
            
            return {
                'ticker': ticker,
                'status': 'success',
                'records_synced': records_synced,
                'duration_seconds': duration
            }
            
        except Exception as e:
            # Log failed sync
            duration = int(time.time() - start_time)
            log_entry = DataSyncLog(
                ticker=ticker,
                sync_type=sync_type,
                records_synced=0,
                from_date=from_date.date(),
                to_date=to_date.date(),
                status='failed',
                error_message=str(e),
                duration_seconds=duration
            )
            self.db.add(log_entry)
            self.db.commit()
            
            logger.error(f"Failed to sync {ticker}: {e}")
            
            return {
                'ticker': ticker,
                'status': 'failed',
                'error': str(e),
                'duration_seconds': duration
            }
    
    async def fetch_multiple_tickers(
        self,
        tickers: List[str],
        days: int = 60,
        sync_type: str = 'daily'
    ) -> Dict[str, any]:
        """
        Fetch data for multiple tickers
        
        Returns:
            Summary dict with success/failed counts
        """
        logger.info(f"Starting bulk sync for {len(tickers)} tickers")
        
        results = []
        for ticker in tickers:
            result = await self.fetch_historical_data(ticker, days, sync_type)
            results.append(result)
            
            # Small delay to avoid rate limiting
            time.sleep(0.5)
        
        success_count = sum(1 for r in results if r['status'] == 'success')
        failed_count = len(results) - success_count
        total_records = sum(r.get('records_synced', 0) for r in results)
        
        summary = {
            'total_tickers': len(tickers),
            'successful': success_count,
            'failed': failed_count,
            'total_records_synced': total_records,
            'results': results
        }
        
        logger.info(f"Bulk sync completed: {success_count}/{len(tickers)} successful")
        return summary
    
    def get_latest_data(self, ticker: str, limit: int = 60) -> List[OHLCVData]:
        """Get most recent OHLCV data for a ticker"""
        return self.db.query(OHLCVData).filter(
            OHLCVData.ticker == ticker
        ).order_by(OHLCVData.time.desc()).limit(limit).all()
    
    def get_date_range(self, ticker: str) -> Optional[Dict[str, datetime]]:
        """Get the date range of available data for a ticker"""
        result = self.db.query(
            OHLCVData.ticker,
            self.db.func.min(OHLCVData.time).label('first_date'),
            self.db.func.max(OHLCVData.time).label('last_date')
        ).filter(OHLCVData.ticker == ticker).first()
        
        if result and result.first_date:
            return {
                'ticker': result.ticker,
                'first_date': result.first_date,
                'last_date': result.last_date,
                'days_available': (result.last_date - result.first_date).days
            }
        return None
