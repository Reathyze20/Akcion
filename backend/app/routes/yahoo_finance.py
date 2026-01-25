"""
Yahoo Finance API Routes

Endpoints pro přístup k Yahoo Finance datům přes smart cache.
Implementuje manual refresh button a bulk operations.

GOMES GUARDIAN: Minimalizace Yahoo API calls pro ochranu rate limitů.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.market_hours import get_market_status
from ..database.connection import get_db
from ..services.yahoo_cache import YahooFinanceCache


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/yahoo", tags=["Yahoo Finance"])


# ==============================================================================
# Request/Response Models
# ==============================================================================

class StockDataRequest(BaseModel):
    """Request pro získání stock dat."""
    ticker: str = Field(..., min_length=1, max_length=10, description="Stock ticker symbol")
    data_types: list[Literal["market", "fundamental", "financial", "all"]] | None = Field(
        None,
        description="Which data types to fetch (default: market only)"
    )
    force_refresh: bool = Field(
        False,
        description="Force refresh ignoring cache (Manual Refresh Button)"
    )


class BulkRefreshRequest(BaseModel):
    """Request pro bulk refresh více tickerů."""
    tickers: list[str] = Field(..., min_items=1, max_items=50, description="List of tickers to refresh")
    data_types: list[Literal["market", "fundamental", "financial", "all"]] | None = None
    force: bool = Field(False, description="Force refresh all")


class StockDataResponse(BaseModel):
    """Response s stock daty."""
    ticker: str
    current_price: float | None
    previous_close: float | None
    market_cap: int | None
    pe_ratio: float | None
    company_name: str | None
    currency: str | None
    last_updated: str
    from_cache: bool
    market_status: dict


class BulkRefreshResponse(BaseModel):
    """Response pro bulk refresh."""
    total: int
    successful: int
    failed: int
    results: dict[str, bool]


class CacheStatusResponse(BaseModel):
    """Response s cache status."""
    ticker: str
    exists: bool
    market_data_age_minutes: float | None
    fundamental_data_age_days: float | None
    financial_data_age_days: float | None
    error_count: int
    last_error: str | None


# ==============================================================================
# Endpoints
# ==============================================================================

@router.post(
    "/stock",
    response_model=StockDataResponse,
    status_code=status.HTTP_200_OK,
    summary="Get stock data with smart caching",
    description="Fetch stock data from Yahoo Finance with intelligent caching to minimize API calls"
)
async def get_stock_data(
    request: StockDataRequest,
    db: Session = Depends(get_db)
) -> StockDataResponse:
    """
    Získá data pro ticker s Gomes smart cachingem.
    
    GOMES LOGIKA:
    - Market zavřený → vrací cache
    - Market otevřený + data starší 15 min → refresh
    - Force refresh → vždy refresh (manual button)
    
    Example:
        POST /api/yahoo/stock
        {
            "ticker": "AAPL",
            "force_refresh": false
        }
    """
    try:
        cache = YahooFinanceCache(db)
        
        # Get data with smart caching
        data = cache.get_stock_data(
            ticker=request.ticker.upper(),
            data_types=request.data_types,
            force_refresh=request.force_refresh
        )
        
        if data is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Could not fetch data for {request.ticker}"
            )
        
        # Check if data was from cache
        from_cache = not request.force_refresh
        
        return StockDataResponse(
            ticker=data["ticker"],
            current_price=float(data["current_price"]) if data.get("current_price") else None,
            previous_close=float(data["previous_close"]) if data.get("previous_close") else None,
            market_cap=data.get("market_cap"),
            pe_ratio=float(data["pe_ratio"]) if data.get("pe_ratio") else None,
            company_name=data.get("company_name"),
            currency=data.get("currency", "USD"),
            last_updated=data["last_updated"].isoformat() if data.get("last_updated") else None,
            from_cache=from_cache,
            market_status=get_market_status()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get stock data for {request.ticker}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch stock data: {str(e)}"
        )


@router.post(
    "/bulk-refresh",
    response_model=BulkRefreshResponse,
    status_code=status.HTTP_200_OK,
    summary="Bulk refresh multiple tickers",
    description="Refresh data for multiple tickers at once (for cron jobs or batch operations)"
)
async def bulk_refresh(
    request: BulkRefreshRequest,
    db: Session = Depends(get_db)
) -> BulkRefreshResponse:
    """
    Refreshne více tickerů najednou.
    
    Use case: Noční cron job pro update celého watchlistu.
    
    Example:
        POST /api/yahoo/bulk-refresh
        {
            "tickers": ["AAPL", "GOOGL", "MSFT"],
            "data_types": ["all"],
            "force": false
        }
    """
    try:
        cache = YahooFinanceCache(db)
        
        results = cache.bulk_refresh(
            tickers=request.tickers,
            data_types=request.data_types,
            force=request.force
        )
        
        successful = sum(results.values())
        failed = len(results) - successful
        
        return BulkRefreshResponse(
            total=len(results),
            successful=successful,
            failed=failed,
            results=results
        )
        
    except Exception as e:
        logger.error(f"Bulk refresh failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Bulk refresh failed: {str(e)}"
        )


@router.get(
    "/cache-status/{ticker}",
    response_model=CacheStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get cache status for ticker",
    description="Check cache age and freshness for debugging"
)
async def get_cache_status(
    ticker: str,
    db: Session = Depends(get_db)
) -> CacheStatusResponse:
    """
    Vrátí status cache pro ticker (debugging).
    
    Example:
        GET /api/yahoo/cache-status/AAPL
    """
    try:
        cache = YahooFinanceCache(db)
        status_data = cache.get_cache_status(ticker.upper())
        
        if not status_data.get("exists"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No cache exists for {ticker}"
            )
        
        return CacheStatusResponse(
            ticker=status_data["ticker"],
            exists=status_data["exists"],
            market_data_age_minutes=status_data.get("market_data_age_minutes"),
            fundamental_data_age_days=status_data.get("fundamental_data_age_days"),
            financial_data_age_days=status_data.get("financial_data_age_days"),
            error_count=status_data.get("error_count", 0),
            last_error=status_data.get("last_error")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get cache status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get cache status: {str(e)}"
        )


@router.get(
    "/market-status",
    status_code=status.HTTP_200_OK,
    summary="Get current market status",
    description="Check if NYSE is open/closed and current time"
)
async def market_status():
    """
    Vrátí aktuální status trhů (pro debugging a UI).
    
    Example:
        GET /api/yahoo/market-status
        
        {
            "is_open": true,
            "current_time_est": "2026-01-27 10:30:00 EST",
            "is_weekend": false,
            "is_holiday": false
        }
    """
    return get_market_status()


@router.post(
    "/manual-refresh/{ticker}",
    response_model=StockDataResponse,
    status_code=status.HTTP_200_OK,
    summary="Manual refresh button (force refresh)",
    description="Force refresh data ignoring cache - for Manual Refresh Button in UI"
)
async def manual_refresh(
    ticker: str,
    data_types: list[Literal["market", "fundamental", "financial", "all"]] = Query(
        default=["all"],
        description="Which data types to refresh"
    ),
    db: Session = Depends(get_db)
) -> StockDataResponse:
    """
    MANUAL REFRESH BUTTON - Force refresh pro ticker.
    
    Tento endpoint je pro tlačítko "Hard Refresh" v UI.
    Ignoruje cache a vždy stáhne nová data z Yahoo.
    
    RATE LIMITING: Frontend by měl mít cooldown (1x za minutu).
    
    Example:
        POST /api/yahoo/manual-refresh/AAPL?data_types=all
    """
    request = StockDataRequest(
        ticker=ticker,
        data_types=data_types,
        force_refresh=True  # Always force on manual refresh
    )
    
    return await get_stock_data(request, db)
