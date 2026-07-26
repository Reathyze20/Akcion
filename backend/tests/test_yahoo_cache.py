"""
Tests for Yahoo Finance Smart Cache

Test coverage:
1. Market hours detection
2. Smart cache logic
3. Manual refresh
4. Bulk operations
5. Error handling
"""

import pytest

pytestmark = pytest.mark.skip(reason="Legacy API-shape tests — superseded by current suites; repair-or-delete tracked in AKCION_SPEC §7")
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.market_hours import (
    is_weekend,
    is_nyse_holiday,
    is_market_open,
    should_refresh_market_data,
    get_market_status,
    MARKET_TIMEZONE
)


class TestMarketHours:
    """Test market hours detection logic."""
    
    def test_weekend_detection(self):
        """Test weekend detection."""
        # Saturday
        saturday = datetime(2026, 1, 24, 10, 0, tzinfo=MARKET_TIMEZONE)
        assert is_weekend(saturday) is True
        
        # Sunday
        sunday = datetime(2026, 1, 25, 10, 0, tzinfo=MARKET_TIMEZONE)
        assert is_weekend(sunday) is True
        
        # Monday
        monday = datetime(2026, 1, 26, 10, 0, tzinfo=MARKET_TIMEZONE)
        assert is_weekend(monday) is False
    
    def test_holiday_detection(self):
        """Test NYSE holiday detection."""
        # New Year's Day
        new_year = datetime(2026, 1, 1, 10, 0, tzinfo=MARKET_TIMEZONE)
        assert is_nyse_holiday(new_year) is True
        
        # Christmas
        christmas = datetime(2026, 12, 25, 10, 0, tzinfo=MARKET_TIMEZONE)
        assert is_nyse_holiday(christmas) is True
        
        # Regular day
        regular = datetime(2026, 1, 27, 10, 0, tzinfo=MARKET_TIMEZONE)
        assert is_nyse_holiday(regular) is False
    
    def test_market_open_regular_hours(self):
        """Test market open during regular hours."""
        # Tuesday 10:00 EST - Market OPEN
        tuesday_10am = datetime(2026, 1, 27, 10, 0, tzinfo=MARKET_TIMEZONE)
        assert is_market_open(tuesday_10am) is True
        
        # Tuesday 17:00 EST - Market CLOSED
        tuesday_5pm = datetime(2026, 1, 27, 17, 0, tzinfo=MARKET_TIMEZONE)
        assert is_market_open(tuesday_5pm) is False
        
        # Tuesday 9:00 EST - Market CLOSED (before open)
        tuesday_9am = datetime(2026, 1, 27, 9, 0, tzinfo=MARKET_TIMEZONE)
        assert is_market_open(tuesday_9am) is False
    
    def test_market_closed_weekend(self):
        """Test market closed on weekend."""
        saturday = datetime(2026, 1, 24, 10, 0, tzinfo=MARKET_TIMEZONE)
        assert is_market_open(saturday) is False
    
    def test_market_closed_holiday(self):
        """Test market closed on holiday."""
        new_year = datetime(2026, 1, 1, 10, 0, tzinfo=MARKET_TIMEZONE)
        assert is_market_open(new_year) is False


class TestSmartCacheLogic:
    """Test smart cache refresh logic."""
    
    def test_force_refresh(self):
        """Force refresh should always refresh."""
        last_updated = datetime.now(MARKET_TIMEZONE) - timedelta(minutes=5)
        should_refresh, reason = should_refresh_market_data(last_updated, force=True)
        assert should_refresh is True
        assert "Manual refresh" in reason
    
    def test_no_cached_data(self):
        """No cache should trigger refresh."""
        should_refresh, reason = should_refresh_market_data(None, force=False)
        assert should_refresh is True
        assert "No cached data" in reason
    
    def test_market_closed_fresh_cache(self):
        """Market closed with fresh cache should NOT refresh."""
        # Simulate Saturday with 1 hour old data
        last_updated = datetime(2026, 1, 24, 9, 0, tzinfo=MARKET_TIMEZONE)  # Saturday morning
        should_refresh, reason = should_refresh_market_data(last_updated, force=False)
        
        # Should use cache (market closed)
        # Note: This test depends on current time, might need mocking in real scenario
        assert "Market closed" in reason or "cache" in reason.lower()
    
    def test_market_open_stale_cache(self):
        """Market open with stale cache (>15 min) should refresh."""
        # During market hours, but data is 20 minutes old
        # This test would need time mocking to be deterministic
        pass  # TODO: Implement with freezegun or similar
    
    def test_market_open_fresh_cache(self):
        """Market open with fresh cache (<15 min) should NOT refresh."""
        # This test would need time mocking to be deterministic
        pass  # TODO: Implement with freezegun


class TestMarketStatus:
    """Test market status API."""
    
    def test_get_market_status(self):
        """Test getting market status."""
        status = get_market_status()
        
        assert "is_open" in status
        assert "current_time_est" in status
        assert "is_weekend" in status
        assert "is_holiday" in status
        assert "weekday" in status
        assert isinstance(status["is_open"], bool)


# ==============================================================================
# Integration Tests (require database)
# ==============================================================================

@pytest.mark.integration
class TestYahooFinanceCache:
    """Integration tests for Yahoo Finance Cache service."""
    
    def test_get_stock_data_aapl(self, db_session):
        """Test fetching AAPL data."""
        from app.services.yahoo_cache import YahooFinanceCache
        
        cache = YahooFinanceCache(db_session)
        
        # First call - should fetch from API
        data = cache.get_stock_data("AAPL", force_refresh=True)
        
        assert data is not None
        assert data["ticker"] == "AAPL"
        assert data["current_price"] is not None
        assert data["company_name"] is not None
    
    def test_cache_reuse(self, db_session):
        """Test that cache is reused properly."""
        from app.services.yahoo_cache import YahooFinanceCache
        
        cache = YahooFinanceCache(db_session)
        
        # First call - fetch from API
        cache.get_stock_data("AAPL", force_refresh=True)
        
        # Second call - should use cache (if market closed)
        data = cache.get_stock_data("AAPL", force_refresh=False)
        
        assert data is not None
        assert data["ticker"] == "AAPL"
    
    def test_bulk_refresh(self, db_session):
        """Test bulk refresh operation."""
        from app.services.yahoo_cache import YahooFinanceCache
        
        cache = YahooFinanceCache(db_session)
        
        tickers = ["AAPL", "GOOGL", "MSFT"]
        results = cache.bulk_refresh(tickers, force=True)
        
        assert len(results) == len(tickers)
        assert all(ticker in results for ticker in tickers)
    
    def test_cache_status(self, db_session):
        """Test getting cache status."""
        from app.services.yahoo_cache import YahooFinanceCache
        
        cache = YahooFinanceCache(db_session)
        
        # Ensure data exists
        cache.get_stock_data("AAPL", force_refresh=True)
        
        # Get status
        status = cache.get_cache_status("AAPL")
        
        assert status["exists"] is True
        assert status["ticker"] == "AAPL"
        assert "market_data_age_minutes" in status


# ==============================================================================
# API Endpoint Tests
# ==============================================================================

@pytest.mark.api
class TestYahooFinanceEndpoints:
    """Test Yahoo Finance API endpoints."""
    
    def test_get_stock_endpoint(self, client):
        """Test POST /api/yahoo/stock endpoint."""
        response = client.post(
            "/api/yahoo/stock",
            json={
                "ticker": "AAPL",
                "force_refresh": False
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "AAPL"
        assert "current_price" in data
    
    def test_manual_refresh_endpoint(self, client):
        """Test POST /api/yahoo/manual-refresh endpoint."""
        response = client.post("/api/yahoo/manual-refresh/AAPL")
        
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "AAPL"
    
    def test_market_status_endpoint(self, client):
        """Test GET /api/yahoo/market-status endpoint."""
        response = client.get("/api/yahoo/market-status")
        
        assert response.status_code == 200
        data = response.json()
        assert "is_open" in data
        assert "current_time_est" in data
    
    def test_cache_status_endpoint(self, client, db_session):
        """Test GET /api/yahoo/cache-status endpoint."""
        # First create some cached data
        from app.services.yahoo_cache import YahooFinanceCache
        cache = YahooFinanceCache(db_session)
        cache.get_stock_data("AAPL", force_refresh=True)
        
        # Then check status
        response = client.get("/api/yahoo/cache-status/AAPL")
        
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "AAPL"
        assert data["exists"] is True


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture
def db_session():
    """Provide database session for tests."""
    from app.database.connection import get_db
    db = next(get_db())
    yield db
    db.rollback()  # Rollback any changes


@pytest.fixture
def client():
    """Provide test client for API tests."""
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)
