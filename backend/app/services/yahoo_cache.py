"""
Yahoo Finance Smart Cache Service

Inteligentní wrapper pro Yahoo Finance API s minimalizací API calls.
Implementuje Gomes pravidla pro cachování market a fundamental dat.

GOMES PRAVIDLA:
1. Market zavřený (víkend/po zavíračce) → Použij cache, nevol API
2. Market otevřený → Aktualizuj každých 15 minut
3. Fundamentální data → Max 1x týdně
4. Financial data → Max 1x čtvrtletí
5. Manual refresh → Ignoruj cache, vždy refresh

CRITICAL: Část aplikace pro finanční zabezpečení rodiny s MS.
Musí být 100% spolehlivý a šetřit Yahoo API limity.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

import yfinance as yf
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..core.market_hours import should_refresh_market_data, get_current_market_time


logger = logging.getLogger(__name__)


# ==============================================================================
# Type Definitions
# ==============================================================================

DataType = Literal["market", "fundamental", "financial", "all"]
RefreshType = Literal["auto", "manual", "scheduled"]


# ==============================================================================
# Yahoo Finance Cache Service
# ==============================================================================

class YahooFinanceCache:
    """
    Smart caching wrapper pro Yahoo Finance API.
    
    Implementuje inteligentní cachování podle market hours a stáří dat.
    Minimalizuje API calls pro ochranu před rate limiting.
    """
    
    # Cache duration constants (Gomes pravidla)
    CACHE_MARKET_DATA_MINUTES = 15          # Market data během obchodování
    CACHE_FUNDAMENTAL_DATA_DAYS = 7         # Fundamentální data
    CACHE_FINANCIAL_DATA_DAYS = 90          # Účetní data (čtvrtletní)
    
    def __init__(self, db_session: Session):
        """
        Initialize Yahoo Finance Cache service.
        
        Args:
            db_session: SQLAlchemy database session
        """
        self.db = db_session
    
    # ==========================================================================
    # Main Public API
    # ==========================================================================
    
    def get_stock_data(
        self,
        ticker: str,
        data_types: list[DataType] | None = None,
        force_refresh: bool = False
    ) -> dict[str, Any] | None:
        """
        Získá data pro ticker s inteligentním cachováním.
        
        GOMES LOGIKA:
        1. Zkontroluj cache v databázi
        2. Rozhodní jestli refreshovat podle market hours a stáří dat
        3. Pokud refresh potřeba → volej Yahoo API
        4. Ulož do cache a vrať data
        
        Args:
            ticker: Stock ticker symbol (e.g., "AAPL", "KUYAF")
            data_types: Které typy dat načíst ["market", "fundamental", "financial"]
                       Default: ["market"] pokud force=False, jinak ["all"]
            force_refresh: True = ignoruj cache, vždy refresh (manual button)
            
        Returns:
            dict s daty nebo None při chybě
            
        Example:
            >>> cache = YahooFinanceCache(db)
            >>> data = cache.get_stock_data("AAPL", force_refresh=False)
            >>> print(data["current_price"])
            150.25
        """
        ticker = ticker.upper().strip()
        
        if data_types is None:
            data_types = ["all"] if force_refresh else ["market"]
        
        logger.info(f"Fetching {ticker} data (types: {data_types}, force: {force_refresh})")
        
        # 1. Load cache from database
        cached = self._get_cached_data(ticker)
        
        # 2. Decide what needs refreshing
        needs_refresh = self._determine_refresh_needs(
            cached=cached,
            data_types=data_types,
            force=force_refresh
        )
        
        # 3. Refresh data if needed
        if any(needs_refresh.values()):
            logger.info(f"{ticker} refresh needed: {needs_refresh}")
            
            success = self._fetch_and_cache_data(
                ticker=ticker,
                refresh_market=needs_refresh.get("market", False),
                refresh_fundamental=needs_refresh.get("fundamental", False),
                refresh_financial=needs_refresh.get("financial", False),
                refresh_type="manual" if force_refresh else "auto"
            )
            
            if not success:
                logger.warning(f"Failed to refresh {ticker}, returning stale cache")
                return cached  # Return stale data rather than None
            
            # Reload from DB after refresh
            cached = self._get_cached_data(ticker)
        else:
            logger.info(f"{ticker} using cache (fresh)")
        
        return cached
    
    def bulk_refresh(
        self,
        tickers: list[str],
        data_types: list[DataType] | None = None,
        force: bool = False
    ) -> dict[str, bool]:
        """
        Refreshne více tickerů najednou (batch operation).
        
        Použití: Noční cron job pro update všech watchlist tickerů.
        
        Args:
            tickers: List tickerů k refreshi
            data_types: Které typy dat refreshnout
            force: Ignorovat cache
            
        Returns:
            dict[ticker -> success]
            
        Example:
            >>> results = cache.bulk_refresh(["AAPL", "GOOGL", "MSFT"])
            >>> print(f"Success: {sum(results.values())}/{len(results)}")
        """
        if data_types is None:
            data_types = ["all"] if force else ["market"]
        
        results = {}
        
        logger.info(f"Bulk refresh starting: {len(tickers)} tickers")
        
        for ticker in tickers:
            try:
                data = self.get_stock_data(
                    ticker=ticker,
                    data_types=data_types,
                    force_refresh=force
                )
                results[ticker] = data is not None
                
            except Exception as e:
                logger.error(f"Bulk refresh failed for {ticker}: {e}")
                results[ticker] = False
        
        success_count = sum(results.values())
        logger.info(f"Bulk refresh complete: {success_count}/{len(tickers)} succeeded")
        
        return results
    
    def get_cache_status(self, ticker: str) -> dict[str, Any]:
        """
        Vrátí detailní status cache pro ticker (pro debugging).
        
        Args:
            ticker: Stock ticker
            
        Returns:
            dict s informacemi o cache stáří
        """
        cached = self._get_cached_data(ticker)
        
        if not cached:
            return {"exists": False}
        
        now = get_current_market_time()
        
        market_age = (now - cached["market_data_updated"]).total_seconds() / 60 if cached.get("market_data_updated") else None
        fundamental_age = (now - cached["fundamental_data_updated"]).days if cached.get("fundamental_data_updated") else None
        financial_age = (now - cached["financial_data_updated"]).days if cached.get("financial_data_updated") else None
        
        return {
            "exists": True,
            "ticker": ticker,
            "last_updated": cached.get("last_updated"),
            "market_data_age_minutes": market_age,
            "fundamental_data_age_days": fundamental_age,
            "financial_data_age_days": financial_age,
            "error_count": cached.get("error_count", 0),
            "last_error": cached.get("last_fetch_error"),
        }
    
    # ==========================================================================
    # Private Helper Methods
    # ==========================================================================
    
    def _get_cached_data(self, ticker: str) -> dict[str, Any] | None:
        """Načte cached data z databáze."""
        try:
            result = self.db.execute(
                text("""
                    SELECT 
                        ticker, current_price, previous_close, day_low, day_high, volume,
                        market_cap, pe_ratio, forward_pe, pb_ratio, dividend_yield, beta,
                        shares_outstanding, revenue_ttm, net_income_ttm, operating_margin,
                        profit_margin, total_cash, total_debt, company_name, sector,
                        industry, exchange, currency, last_updated, market_data_updated,
                        fundamental_data_updated, financial_data_updated, last_fetch_error,
                        error_count, raw_data
                    FROM yahoo_finance_cache
                    WHERE ticker = :ticker
                """),
                {"ticker": ticker}
            ).fetchone()
            
            if result is None:
                return None
            
            # Convert to dict
            return dict(result._mapping)
            
        except Exception as e:
            logger.error(f"Error loading cache for {ticker}: {e}")
            return None
    
    def _determine_refresh_needs(
        self,
        cached: dict[str, Any] | None,
        data_types: list[DataType],
        force: bool
    ) -> dict[str, bool]:
        """
        Rozhodne které typy dat potřebují refresh.
        
        Returns:
            {"market": bool, "fundamental": bool, "financial": bool}
        """
        needs = {"market": False, "fundamental": False, "financial": False}
        
        # Force refresh = vše
        if force:
            if "all" in data_types:
                return {"market": True, "fundamental": True, "financial": True}
            return {dt: True for dt in data_types}
        
        # Žádná cache = refresh vše
        if cached is None:
            if "all" in data_types:
                return {"market": True, "fundamental": True, "financial": True}
            return {dt: True for dt in data_types}
        
        now = get_current_market_time()
        
        # Check market data
        if "market" in data_types or "all" in data_types:
            if cached.get("market_data_updated"):
                should_refresh, reason = should_refresh_market_data(
                    last_updated=cached["market_data_updated"],
                    force=False
                )
                needs["market"] = should_refresh
            else:
                needs["market"] = True
        
        # Check fundamental data (weekly)
        if "fundamental" in data_types or "all" in data_types:
            if cached.get("fundamental_data_updated"):
                age_days = (now - cached["fundamental_data_updated"]).days
                needs["fundamental"] = age_days >= self.CACHE_FUNDAMENTAL_DATA_DAYS
            else:
                needs["fundamental"] = True
        
        # Check financial data (quarterly)
        if "financial" in data_types or "all" in data_types:
            if cached.get("financial_data_updated"):
                age_days = (now - cached["financial_data_updated"]).days
                needs["financial"] = age_days >= self.CACHE_FINANCIAL_DATA_DAYS
            else:
                needs["financial"] = True
        
        return needs
    
    def _fetch_and_cache_data(
        self,
        ticker: str,
        refresh_market: bool,
        refresh_fundamental: bool,
        refresh_financial: bool,
        refresh_type: RefreshType = "auto"
    ) -> bool:
        """
        Fetchne data z Yahoo API a uloží do cache.
        
        Returns:
            bool: True pokud úspěch
        """
        start_time = datetime.now()
        
        try:
            # Fetch from Yahoo Finance
            logger.info(f"Calling Yahoo API for {ticker}")
            stock = yf.Ticker(ticker)
            
            # Prepare data dict
            data: dict[str, Any] = {"ticker": ticker}
            now = get_current_market_time()
            
            # Market data
            if refresh_market:
                try:
                    info = stock.info
                    fast_info = stock.fast_info
                    
                    data.update({
                        "current_price": fast_info.get("last_price"),
                        "previous_close": fast_info.get("previous_close"),
                        "day_low": fast_info.get("day_low"),
                        "day_high": fast_info.get("day_high"),
                        "volume": fast_info.get("volume"),
                        "market_data_updated": now,
                    })
                    
                    # Also extract basic info
                    if not refresh_fundamental:  # Avoid duplicate if we'll fetch fundamental anyway
                        data.update({
                            "company_name": info.get("longName") or info.get("shortName"),
                            "exchange": info.get("exchange"),
                            "currency": info.get("currency", "USD"),
                        })
                    
                except Exception as e:
                    logger.warning(f"Failed to fetch market data for {ticker}: {e}")
            
            # Fundamental data
            if refresh_fundamental:
                try:
                    info = stock.info
                    
                    data.update({
                        "market_cap": info.get("marketCap"),
                        "pe_ratio": info.get("trailingPE"),
                        "forward_pe": info.get("forwardPE"),
                        "pb_ratio": info.get("priceToBook"),
                        "dividend_yield": info.get("dividendYield"),
                        "beta": info.get("beta"),
                        "shares_outstanding": info.get("sharesOutstanding"),
                        "company_name": info.get("longName") or info.get("shortName"),
                        "sector": info.get("sector"),
                        "industry": info.get("industry"),
                        "exchange": info.get("exchange"),
                        "currency": info.get("currency", "USD"),
                        "fundamental_data_updated": now,
                    })
                    
                except Exception as e:
                    logger.warning(f"Failed to fetch fundamental data for {ticker}: {e}")
            
            # Financial data
            if refresh_financial:
                try:
                    info = stock.info
                    
                    data.update({
                        "revenue_ttm": info.get("totalRevenue"),
                        "net_income_ttm": info.get("netIncomeToCommon"),
                        "operating_margin": info.get("operatingMargins"),
                        "profit_margin": info.get("profitMargins"),
                        "total_cash": info.get("totalCash"),
                        "total_debt": info.get("totalDebt"),
                        "financial_data_updated": now,
                    })
                    
                except Exception as e:
                    logger.warning(f"Failed to fetch financial data for {ticker}: {e}")
            
            # Store raw data for future analysis
            try:
                import json
                data["raw_data"] = json.dumps(stock.info) if stock.info else None
            except:
                data["raw_data"] = None
            
            # Save to database
            self._upsert_cache(data)
            
            # Log success
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            self._log_refresh(
                ticker=ticker,
                refresh_type=refresh_type,
                data_types=[k for k, v in {
                    "market": refresh_market,
                    "fundamental": refresh_fundamental,
                    "financial": refresh_financial
                }.items() if v],
                success=True,
                duration_ms=duration_ms
            )
            
            logger.info(f"Successfully fetched and cached {ticker} ({duration_ms}ms)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to fetch {ticker} from Yahoo: {e}")
            
            # Log failure
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            self._log_refresh(
                ticker=ticker,
                refresh_type=refresh_type,
                data_types=["market", "fundamental", "financial"],
                success=False,
                error_message=str(e),
                duration_ms=duration_ms
            )
            
            # Update error count in cache
            self._increment_error_count(ticker, str(e))
            
            return False
    
    def _upsert_cache(self, data: dict[str, Any]) -> None:
        """Upsert data do yahoo_finance_cache tabulky."""
        try:
            # Build dynamic query based on provided fields
            columns = list(data.keys())
            placeholders = [f":{col}" for col in columns]
            
            # Ensure last_updated is set
            if "last_updated" not in data:
                data["last_updated"] = get_current_market_time()
                columns.append("last_updated")
                placeholders.append(":last_updated")
            
            # Build update clause (all columns except ticker)
            update_cols = [f"{col} = EXCLUDED.{col}" for col in columns if col != "ticker"]
            
            query = f"""
                INSERT INTO yahoo_finance_cache ({', '.join(columns)})
                VALUES ({', '.join(placeholders)})
                ON CONFLICT (ticker)
                DO UPDATE SET
                    {', '.join(update_cols)},
                    error_count = 0,
                    last_successful_fetch = NOW()
            """
            
            self.db.execute(text(query), data)
            self.db.commit()
            
        except Exception as e:
            logger.error(f"Failed to upsert cache: {e}")
            self.db.rollback()
            raise
    
    def _increment_error_count(self, ticker: str, error_message: str) -> None:
        """Zvýší error count pro ticker."""
        try:
            self.db.execute(
                text("""
                    UPDATE yahoo_finance_cache
                    SET 
                        error_count = COALESCE(error_count, 0) + 1,
                        last_fetch_error = :error,
                        last_updated = NOW()
                    WHERE ticker = :ticker
                """),
                {"ticker": ticker, "error": error_message}
            )
            self.db.commit()
        except Exception as e:
            logger.error(f"Failed to increment error count: {e}")
            self.db.rollback()
    
    def _log_refresh(
        self,
        ticker: str,
        refresh_type: RefreshType,
        data_types: list[str],
        success: bool,
        duration_ms: int,
        error_message: str | None = None,
        triggered_by: str = "system"
    ) -> None:
        """Zaloguje refresh do audit table."""
        try:
            self.db.execute(
                text("""
                    INSERT INTO yahoo_refresh_log 
                    (ticker, refresh_type, data_types, success, error_message, duration_ms, triggered_by)
                    VALUES 
                    (:ticker, :refresh_type, :data_types, :success, :error_message, :duration_ms, :triggered_by)
                """),
                {
                    "ticker": ticker,
                    "refresh_type": refresh_type,
                    "data_types": data_types,
                    "success": success,
                    "error_message": error_message,
                    "duration_ms": duration_ms,
                    "triggered_by": triggered_by,
                }
            )
            self.db.commit()
        except Exception as e:
            logger.error(f"Failed to log refresh: {e}")
            self.db.rollback()
