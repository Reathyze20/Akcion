"""
Data Fetcher - Retrieves OHLCV data from Polygon.io API
"""
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import time
import requests

from app.config.settings import Settings
from app.models.trading import OHLCVData, DataSyncLog
from loguru import logger


# Constants
POLYGON_API_BASE = "https://api.polygon.io/v2"
REQUEST_TIMEOUT = 10


class DataFetcher:
    """Fetches and stores OHLCV time-series data for watchlist tickers"""
    
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings
    
    def _fetch_from_polygon(self, ticker: str, from_date: str, to_date: str) -> Optional[Dict]:
        """
        Fetch historical candle data from Polygon.io API.
        
        Args:
            ticker: Stock ticker symbol
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
            
        Returns:
            Dict with results array or None
        """
        api_key = self.settings.massive_api_key
        if not api_key:
            logger.warning("Polygon.io API key not configured")
            return None
        
        url = f"{POLYGON_API_BASE}/aggs/ticker/{ticker}/range/1/day/{from_date}/{to_date}"
        params = {
            "adjusted": "true",
            "sort": "asc",
            "apiKey": api_key
        }
        
        try:
            response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
            
            if response.status_code == 200:
                data = response.json()
                # Accept both OK and DELAYED status (DELAYED still has data)
                if data.get("status") in ("OK", "DELAYED") and data.get("results"):
                    return data
                else:
                    logger.warning(f"No Polygon data for {ticker}: {data.get('status')}")
                    return None
            elif response.status_code == 429:
                logger.warning("Polygon rate limit hit")
                time.sleep(1)
                return None
            else:
                logger.warning(f"Polygon returned {response.status_code} for {ticker}")
                return None
                
        except Exception as e:
            logger.error(f"Polygon API error: {e}")
            return None
    
    async def fetch_historical_data(
        self,
        ticker: str,
        days: int = 120,
        sync_type: str = 'manual'
    ) -> Dict[str, any]:
        """
        Fetch historical OHLCV data for a ticker from Polygon.io.
        
        Args:
            ticker: Stock ticker symbol
            days: Number of days of historical data
            sync_type: 'daily', 'manual', or 'initial'
        
        Returns:
            Dict with status and records synced
        """
        start_time = time.time()
        from_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        to_date = datetime.now().strftime('%Y-%m-%d')
        
        logger.info(f"Fetching {days} days of data for {ticker} from Polygon.io")
        
        try:
            # Fetch from Polygon
            data = self._fetch_from_polygon(ticker, from_date, to_date)
            
            if not data:
                raise ValueError(f"No data returned for {ticker}")
            
            records_synced = 0
            results = data.get('results', [])
            
            # Parse Polygon response format
            # Each result: {'v': volume, 'vw': vwap, 'o': open, 'c': close, 'h': high, 'l': low, 't': timestamp_ms}
            for r in results:
                dt = datetime.fromtimestamp(r['t'] / 1000)  # Polygon uses milliseconds
                
                # Check for existing record
                existing = self.db.query(OHLCVData).filter(
                    OHLCVData.time == dt,
                    OHLCVData.ticker == ticker
                ).first()
                
                if not existing:
                    ohlcv = OHLCVData(
                        time=dt,
                        ticker=ticker,
                        open=float(r['o']),
                        high=float(r['h']),
                        low=float(r['l']),
                        close=float(r['c']),
                        volume=int(r['v']),
                        vwap=float(r.get('vw', (r['h'] + r['l'] + r['c']) / 3))
                    )
                    self.db.add(ohlcv)
                    records_synced += 1
            
            self.db.commit()
            
            # Log successful sync
            duration = int(time.time() - start_time)
            from_dt = datetime.strptime(from_date, '%Y-%m-%d').date()
            to_dt = datetime.strptime(to_date, '%Y-%m-%d').date()
            log_entry = DataSyncLog(
                ticker=ticker,
                sync_type=sync_type,
                records_synced=records_synced,
                from_date=from_dt,
                to_date=to_dt,
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
            from_dt = datetime.strptime(from_date, '%Y-%m-%d').date()
            to_dt = datetime.strptime(to_date, '%Y-%m-%d').date()
            log_entry = DataSyncLog(
                ticker=ticker,
                sync_type=sync_type,
                records_synced=0,
                from_date=from_dt,
                to_date=to_dt,
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
