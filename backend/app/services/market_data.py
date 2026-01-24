"""
Market Data Service

Provides real-time market data from multiple sources:
- Massive.com (Polygon.io) for US stocks
- Finnhub.io for global stocks (TSX, ASX, etc.)

Clean Code Principles Applied:
- Single Responsibility: Each method does one thing
- Dependency Injection ready via settings
- Explicit logging instead of print statements
- Type hints throughout
- Constants extracted to class level
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any, Final

import requests
from sqlalchemy.orm import Session

from ..config.settings import get_settings
from ..models.portfolio import Position


logger = logging.getLogger(__name__)


# ==============================================================================
# Constants
# ==============================================================================

REQUEST_TIMEOUT_SECONDS: Final[int] = 10
RATE_LIMIT_DELAY_SECONDS: Final[float] = 0.1
DEFAULT_MAX_AGE_HOURS: Final[int] = 24


class MarketDataService:
    """
    Service for fetching real-time market data.
    
    Supports multiple data providers with automatic fallback:
    1. Massive.com (US stocks) - Primary
    2. Finnhub.io (Global stocks) - Fallback
    """
    
    # API Endpoints
    MASSIVE_API_BASE: Final[str] = "https://api.massive.com"
    FINNHUB_API_BASE: Final[str] = "https://finnhub.io/api/v1"
    
    # Common company name → ticker mappings (avoids API rate limits)
    COMMON_COMPANY_TICKERS: dict[str, str] = {
        "APPLE": "AAPL",
        "ALPHABET": "GOOGL",
        "GOOGLE": "GOOGL",
        "NVIDIA": "NVDA",
        "MICROSOFT": "MSFT",
        "META": "META",
        "FACEBOOK": "META",
        "AMAZON": "AMZN",
        "TESLA": "TSLA",
        "NETFLIX": "NFLX",
        # Canadian / TSX
        "QUIPT HOME MEDICAL": "QIPT",
        # User portfolio - DEGIRO stocks
        "AEHR TEST SYSTEMS": "AEHR",
        "ELECTROCORE": "ECOR",
        "GATEKEEPER SYSTEMS": "GSI.V",  # TSX Venture
        "INTELLICHECK": "IDN",
        "INTERMAP TECHNOLOGIES": "IMP.V",  # TSX Venture
        "INTERMAP TECHNOLOGIES CORP CLASS A": "IMP.V",
        "INTERMAP TECHNOLOGIES CLASS A": "IMP.V",
        "INTERMAP": "IMP.V",
        "IRIDEX": "IRIX",
        "IRIDEX CORP": "IRIX",
        "KUYA SILVER": "KUYA.V",  # TSX Venture
        "KUYA SILVER CORP": "KUYA.V",
        "NETDRAGON WEBSOFT": "0777.HK",  # Hong Kong
        "NETDRAGON WEBSOFT HOLDINGS": "0777.HK",
        "NETDRAGON WEBSOFT HOLDINGS LTD": "0777.HK",
        "SMITH MICRO SOFTWARE": "SMSI",
        "TECHPRECISION": "TPCS",
        "TECHPRECISION CORP": "TPCS",
        "VIRTRA": "VTSI",
        "VIRTRA INC": "VTSI",
        "UMT UNITED MOBILITY TECHNOLOGY": "UMD",
    }

    # ==========================================================================
    # Price Fetching - Primary APIs
    # ==========================================================================

    @staticmethod
    def _get_price_from_massive(ticker: str) -> float | None:
        """
        Fetch current price from Massive.com API (US stocks only).
        
        Uses previous day close (15-min delayed on Starter plan).
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Price as float or None if fetch failed
        """
        try:
            settings = get_settings()
            api_key = settings.massive_api_key
            
            if not api_key:
                return None
            
            url = f"{MarketDataService.MASSIVE_API_BASE}/v2/aggs/ticker/{ticker}/prev"
            params = {"adjusted": "true", "apiKey": api_key}
            
            response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "OK" and data.get("results"):
                    close_price = data["results"][0].get("c")
                    if close_price:
                        return float(close_price)
            
        except Exception as e:
            logger.warning(f"Massive API error for {ticker}: {e}")
        
        return None

    @staticmethod
    def _get_price_from_finnhub(ticker: str) -> float | None:
        """
        Fetch current price from Finnhub.io API (Global stocks).
        
        Free tier: 60 requests/minute.
        
        Args:
            ticker: Stock ticker (use exchange suffix for non-US, e.g., QIPT.TO)
            
        Returns:
            Price as float or None if fetch failed
        """
        try:
            settings = get_settings()
            api_key = settings.finnhub_api_key
            
            if not api_key:
                logger.debug("Finnhub API key not configured")
                return None
            
            url = f"{MarketDataService.FINNHUB_API_BASE}/quote"
            params = {"symbol": ticker, "token": api_key}
            
            response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
            
            if response.status_code == 200:
                data = response.json()
                current_price = data.get("c")
                if current_price and current_price > 0:
                    return float(current_price)
                prev_close = data.get("pc")
                if prev_close and prev_close > 0:
                    return float(prev_close)
            elif response.status_code == 429:
                logger.warning(f"Finnhub rate limit hit for {ticker}")
            else:
                logger.debug(f"Finnhub API returned {response.status_code} for {ticker}")
            
        except Exception as e:
            logger.warning(f"Finnhub API error for {ticker}: {e}")
        
        return None

    @staticmethod
    def _get_info_from_finnhub(ticker: str) -> dict[str, Any] | None:
        """
        Get company profile from Finnhub.io API.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Dict with company info or None if failed
        """
        try:
            settings = get_settings()
            api_key = settings.finnhub_api_key
            
            if not api_key:
                return None
            
            url = f"{MarketDataService.FINNHUB_API_BASE}/stock/profile2"
            params = {"symbol": ticker, "token": api_key}
            
            response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("name"):
                    return {
                        "ticker": ticker,
                        "company_name": data.get("name"),
                        "sector": data.get("finnhubIndustry"),
                        "industry": data.get("finnhubIndustry"),
                        "currency": data.get("currency", "USD"),
                        "country": data.get("country"),
                        "exchange": data.get("exchange"),
                    }
            
        except Exception as e:
            logger.debug(f"Finnhub profile error for {ticker}: {e}")
        
        return None

    # ==========================================================================
    # Public Price Methods
    # ==========================================================================

    @staticmethod
    def get_current_price(ticker: str, retry_count: int = 2) -> float | None:
        """
        Fetch current price for a single ticker with fallback.
        
        Tries Massive.com API first (US stocks), then Finnhub.io (global).
        
        Args:
            ticker: Stock ticker symbol
            retry_count: Number of retries on failure (unused, kept for API compat)
            
        Returns:
            Current price or None if all sources fail
        """
        # Try Massive API first (US stocks)
        price = MarketDataService._get_price_from_massive(ticker)
        if price is not None:
            logger.info(f"{ticker}: ${price:.2f} (Massive API)")
            return price
        
        # Try Finnhub.io as fallback (global coverage)
        price = MarketDataService._get_price_from_finnhub(ticker)
        if price is not None:
            logger.info(f"{ticker}: ${price:.2f} (Finnhub API)")
            return price
        
        logger.warning(f"No price data for {ticker} from any API")
        return None

    @staticmethod
    def get_multiple_prices(tickers: list[str]) -> dict[str, float | None]:
        """
        Fetch current prices for multiple tickers.
        
        Uses individual API calls (no batch endpoint on Starter plans).
        
        Args:
            tickers: List of ticker symbols
            
        Returns:
            Dict mapping ticker to current price (or None if failed)
        """
        prices: dict[str, float | None] = {}
        
        for ticker in tickers:
            price = MarketDataService.get_current_price(ticker, retry_count=1)
            prices[ticker] = price
            time.sleep(RATE_LIMIT_DELAY_SECONDS)
        
        return prices

    # ==========================================================================
    # Ticker Validation & Resolution
    # ==========================================================================

    # ISIN to Ticker cache (persistent during runtime)
    _ISIN_TICKER_CACHE: dict[str, str | None] = {}

    @staticmethod
    def isin_to_ticker(isin: str) -> str | None:
        """
        Convert ISIN code to stock ticker using yfinance.
        
        Args:
            isin: International Securities Identification Number
            
        Returns:
            Ticker symbol or None if not found
        """
        if not isin or not MarketDataService._is_isin(isin):
            return None
        
        # Check cache first
        if isin in MarketDataService._ISIN_TICKER_CACHE:
            return MarketDataService._ISIN_TICKER_CACHE[isin]
        
        try:
            import yfinance as yf
            
            # yfinance can search by ISIN
            ticker = yf.Ticker(isin)
            info = ticker.info
            
            if info and info.get("symbol"):
                resolved = info["symbol"].upper()
                MarketDataService._ISIN_TICKER_CACHE[isin] = resolved
                logger.info(f"ISIN {isin} resolved to ticker {resolved}")
                return resolved
            
        except Exception as e:
            logger.debug(f"ISIN resolution failed for {isin}: {e}")
        
        # Mark as unresolvable in cache
        MarketDataService._ISIN_TICKER_CACHE[isin] = None
        return None

    @staticmethod
    def _is_isin(value: str) -> bool:
        """
        Check if string looks like an ISIN (International Securities Identification Number).
        
        Format: 2 letter country code + 9 alphanumeric + 1 check digit
        
        Args:
            value: String to check
            
        Returns:
            True if matches ISIN pattern
        """
        if not value:
            return False
        return bool(re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", value.strip().upper()))

    @staticmethod
    def _normalize_name(name: str) -> str:
        """
        Normalize company name for matching against COMMON_COMPANY_TICKERS.
        
        Removes punctuation and common corporate suffixes.
        
        Args:
            name: Company name to normalize
            
        Returns:
            Normalized uppercase name
        """
        s = name.upper()
        s = re.sub(r"[\.,]", "", s)  # Remove punctuation
        s = re.sub(r"\b(INC|CORP(ORATION)?|LTD|PLC|N\s?V|SA|AG|CLASS\s*[A-Z]?)\b", "", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    @staticmethod
    @lru_cache(maxsize=500)
    def validate_ticker(ticker: str) -> bool:
        """
        Validate that a ticker appears to be a real equity symbol.
        
        Uses Massive.com API for US stocks validation.
        For non-US stocks, accepts format-valid tickers.
        
        Args:
            ticker: Ticker symbol to validate
            
        Returns:
            True if ticker appears valid
        """
        if not ticker:
            return False
        
        # Basic format validation
        if not re.match(r"^[A-Z0-9.\-]+$", ticker.upper()):
            return False
        
        # Try Massive API for US stocks
        try:
            settings = get_settings()
            api_key = settings.massive_api_key
            
            if api_key:
                url = f"{MarketDataService.MASSIVE_API_BASE}/v3/reference/tickers/{ticker}"
                params = {"apiKey": api_key}
                response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("status") == "OK" and data.get("results"):
                        return True
        except Exception as e:
            logger.debug(f"Ticker validation API error for {ticker}: {e}")
        
        # For non-US stocks or API failures, trust AI-provided ticker
        return True

    @staticmethod
    def resolve_ticker_by_name(
        name: str, 
        prefer_country: str | None = "United States"
    ) -> str | None:
        """
        Resolve a stock ticker by company name using local mapping.
        
        Uses COMMON_COMPANY_TICKERS dictionary to avoid API rate limits.
        
        Args:
            name: Company name to resolve
            prefer_country: Preferred country (unused, kept for API compat)
            
        Returns:
            Resolved ticker or None if not found
        """
        if not name:
            return None
        
        try:
            norm = MarketDataService._normalize_name(name)
            return MarketDataService.COMMON_COMPANY_TICKERS.get(norm)
        except Exception as e:
            logger.debug(f"Ticker resolution error for '{name}': {e}")
            return None

    @staticmethod
    def fix_ticker(ticker: str | None, company_name: str | None) -> str | None:
        """
        Fix or resolve an incorrect ticker.
        
        Handles:
        - Empty tickers → resolve by company name
        - ISIN codes → resolve via yfinance or company name  
        - Invalid tickers → resolve by company name
        
        Args:
            ticker: Ticker to fix (may be None, empty, or ISIN)
            company_name: Company name for resolution fallback
            
        Returns:
            Corrected ticker or None if unresolvable
        """
        t = (ticker or "").strip().upper()
        
        # If looks like ISIN, try to resolve via yfinance first
        if MarketDataService._is_isin(t):
            resolved = MarketDataService.isin_to_ticker(t)
            if resolved:
                return resolved
            # Fallback to company name resolution
            if company_name:
                resolved = MarketDataService.resolve_ticker_by_name(company_name)
                if resolved:
                    return resolved
            # Return ISIN as-is if unresolvable
            return t
        
        # If empty, try to resolve by name
        if not t:
            if company_name:
                return MarketDataService.resolve_ticker_by_name(company_name)
            return None
        
        # If valid ticker, return it
        if MarketDataService.validate_ticker(t):
            return t
        
        # Try resolving by company name as fallback
        if company_name:
            resolved = MarketDataService.resolve_ticker_by_name(company_name)
            return resolved or t
        
        return t

    # ==========================================================================
    # Portfolio Operations
    # ==========================================================================

    @staticmethod
    def refresh_portfolio_prices(
        db: Session,
        portfolio_id: int | None = None,
        force_refresh: bool = False,
        max_age_hours: int = DEFAULT_MAX_AGE_HOURS,
    ) -> dict[str, Any]:
        """
        Refresh current prices for all positions in portfolio(s).
        
        Uses DB cache - only fetches if prices are stale or force_refresh=True.
        
        Args:
            db: Database session
            portfolio_id: Optional portfolio ID to filter
            force_refresh: If True, fetch prices even if cached
            max_age_hours: Max age before price is considered stale
            
        Returns:
            Dict with stats: updated_count, failed_count, cached_count, tickers
        """
        # Build query
        query = db.query(Position)
        if portfolio_id:
            query = query.filter(Position.portfolio_id == portfolio_id)
        
        positions = query.all()
        
        if not positions:
            return {
                "updated_count": 0,
                "failed_count": 0,
                "cached_count": 0,
                "tickers": [],
            }
        
        # Separate fresh (cached) from stale positions
        now = datetime.utcnow()
        stale_threshold = now - timedelta(hours=max_age_hours)
        
        if force_refresh:
            positions_to_refresh = positions
            cached_positions = []
        else:
            positions_to_refresh = [
                pos for pos in positions
                if pos.last_price_update is None or pos.last_price_update < stale_threshold
            ]
            cached_positions = [
                pos for pos in positions
                if pos.last_price_update and pos.last_price_update >= stale_threshold
            ]
        
        cached_count = len(cached_positions)
        
        if not positions_to_refresh:
            return {
                "updated_count": 0,
                "failed_count": 0,
                "cached_count": cached_count,
                "tickers": list({pos.ticker for pos in positions}),
                "message": f"All prices are fresh (< {max_age_hours}h old). Use force_refresh=true to update anyway.",
            }
        
        # Fetch unique tickers
        tickers_to_fetch = list({pos.ticker for pos in positions_to_refresh})
        logger.info(f"Cache status: {cached_count} cached, {len(positions_to_refresh)} to refresh")
        
        prices = MarketDataService.get_multiple_prices(tickers_to_fetch)
        
        # Update positions
        updated_count = 0
        failed_count = 0
        
        for position in positions_to_refresh:
            price = prices.get(position.ticker)
            if price is not None:
                position.current_price = price
                position.last_price_update = now
                updated_count += 1
            else:
                failed_count += 1
        
        db.commit()
        
        return {
            "updated_count": updated_count,
            "failed_count": failed_count,
            "cached_count": cached_count,
            "tickers": list({pos.ticker for pos in positions}),
            "prices": prices,
        }

    # ==========================================================================
    # Stock Info
    # ==========================================================================

    @staticmethod
    def get_stock_info(ticker: str) -> dict[str, Any] | None:
        """
        Get stock information including company name.
        
        Tries Massive.com API first (US stocks), then Finnhub.io (global).
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Dict with stock info or None if all sources fail
        """
        # Try Massive.com API first
        try:
            settings = get_settings()
            api_key = settings.massive_api_key
            
            if api_key:
                url = f"{MarketDataService.MASSIVE_API_BASE}/v3/reference/tickers/{ticker}"
                params = {"apiKey": api_key}
                
                response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("status") == "OK" and data.get("results"):
                        result = data["results"]
                        return {
                            "ticker": ticker,
                            "company_name": result.get("name"),
                            "sector": result.get("sic_description"),
                            "industry": result.get("sic_description"),
                            "currency": result.get("currency_name", "USD"),
                        }
        except Exception as e:
            logger.warning(f"Massive API info error for {ticker}: {e}")
        
        # Try Finnhub.io as fallback
        finnhub_info = MarketDataService._get_info_from_finnhub(ticker)
        if finnhub_info:
            logger.info(f"Got info for {ticker} from Finnhub API")
            return finnhub_info
        
        logger.debug(f"No API data for {ticker} - using AI-provided info")
        return None
