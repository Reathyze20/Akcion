"""
API Integration Tests
======================

End-to-end tests for Trading Intelligence API endpoints.

Tests:
- Master Signal API
- ML Learning API
- Backtest API
- Notifications API
- Action Center API

Author: GitHub Copilot with Claude Opus 4.5
Date: 2026-01-18
Version: 1.0.0
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient

# FastAPI app import
from app.main import app


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture
def client():
    """Create test client"""
    return TestClient(app)


@pytest.fixture
def mock_db_session():
    """Mock database session for dependency injection"""
    mock = Mock()
    mock.query.return_value.filter.return_value.first.return_value = None
    mock.query.return_value.filter.return_value.all.return_value = []
    return mock


@pytest.fixture
def sample_master_signal_response():
    """Sample Master Signal API response"""
    return {
        "ticker": "AAPL",
        "buy_confidence": 82.5,
        "signal_strength": "STRONG_BUY",
        "components": {
            "gomes_score": 90.0,
            "ml_confidence": 78.5,
            "technical_score": 75.0,
            "sentiment_score": 80.0,
            "gap_score": 100.0,
            "risk_reward_score": 80.0,
        },
        "verdict": "STRONG_BUY",
        "blocked_reason": None,
        "entry_price": 185.50,
        "target_price": 205.00,
        "stop_loss": 167.00,
        "risk_reward_ratio": 2.3,
        "kelly_size": 0.15,
        "calculated_at": "2026-01-18T10:00:00",
        "expires_at": "2026-01-18T16:00:00",
    }


# ==============================================================================
# Health Check Tests
# ==============================================================================

class TestHealthCheck:
    """Tests for health check endpoint"""
    
    def test_health_check_returns_200(self, client):
        """Health check should return 200 OK"""
        response = client.get("/api/health")
        
        assert response.status_code == 200
    
    def test_health_check_response_format(self, client):
        """Health check should return expected format"""
        response = client.get("/api/health")
        data = response.json()
        
        assert "status" in data
        assert data["status"] == "healthy"
        assert "timestamp" in data


# ==============================================================================
# Master Signal API Tests
# ==============================================================================

class TestMasterSignalAPI:
    """Tests for Master Signal endpoints"""
    
    @patch('app.routes.master_signal.calculate_buy_confidence')
    def test_get_master_signal_success(self, mock_calc, client, sample_master_signal_response):
        """GET /api/master-signal/{ticker} should return signal data"""
        # Mock the calculation
        mock_result = Mock()
        mock_result.to_dict.return_value = sample_master_signal_response
        mock_calc.return_value = mock_result
        
        response = client.get("/api/master-signal/AAPL")
        
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "AAPL"
        assert "buy_confidence" in data
    
    def test_get_master_signal_invalid_ticker(self, client):
        """Invalid ticker should return 404"""
        with patch('app.routes.master_signal.calculate_buy_confidence') as mock_calc:
            mock_calc.side_effect = ValueError("Ticker not found")
            
            response = client.get("/api/master-signal/INVALID123")
            
            assert response.status_code == 404
    
    @patch('app.routes.master_signal.MasterSignalAggregator')
    def test_batch_signals(self, mock_aggregator, client):
        """Batch endpoint should handle multiple tickers"""
        mock_instance = mock_aggregator.return_value
        mock_result = Mock()
        mock_result.to_dict.return_value = {"ticker": "AAPL", "buy_confidence": 80.0}
        mock_instance.calculate_master_signal.return_value = mock_result
        
        response = client.get("/api/master-signal/batch?tickers=AAPL,GOOGL")
        
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
    
    def test_batch_signals_limit(self, client):
        """Batch should reject >50 tickers"""
        tickers = ",".join([f"TICK{i}" for i in range(60)])
        
        response = client.get(f"/api/master-signal/batch?tickers={tickers}")
        
        assert response.status_code == 400


# ==============================================================================
# Action Center API Tests
# ==============================================================================

class TestActionCenterAPI:
    """Tests for Action Center endpoints"""
    
    @patch('app.routes.master_signal.get_top_opportunities_v2')
    def test_get_opportunities(self, mock_get, client):
        """GET /api/action-center/opportunities should return top opportunities"""
        mock_get.return_value = []
        
        response = client.get("/api/action-center/opportunities")
        
        assert response.status_code == 200
        data = response.json()
        assert "opportunities" in data
        assert "count" in data
        assert "last_updated" in data
    
    @patch('app.routes.master_signal.get_top_opportunities_v2')
    def test_opportunities_with_min_confidence(self, mock_get, client):
        """Should filter by min_confidence parameter"""
        mock_get.return_value = []
        
        response = client.get("/api/action-center/opportunities?min_confidence=80")
        
        assert response.status_code == 200
        mock_get.assert_called()
    
    def test_opportunities_limit_validation(self, client):
        """Limit should be validated"""
        response = client.get("/api/action-center/opportunities?limit=100")
        
        # Should fail validation (max is 50)
        assert response.status_code == 422


# ==============================================================================
# ML Learning API Tests
# ==============================================================================

class TestMLLearningAPI:
    """Tests for ML Learning endpoints"""
    
    @patch('app.routes.ml_learning.MLLearningEngine')
    def test_get_ticker_performance(self, mock_engine, client):
        """GET /api/ml-learning/performance/{ticker} should return metrics"""
        mock_instance = mock_engine.return_value
        mock_metrics = Mock()
        mock_metrics.ticker = "AAPL"
        mock_metrics.model_version = "PatchTST-v1.0"
        mock_metrics.total_predictions = 50
        mock_metrics.direction_accuracy = 0.72
        mock_metrics.avg_price_error_pct = 3.5
        mock_metrics.median_price_error_pct = 2.8
        mock_metrics.gomes_agreement_rate = 0.85
        mock_metrics.gomes_success_rate = 0.78
        mock_metrics.win_count = 36
        mock_metrics.loss_count = 14
        mock_metrics.win_rate = 0.72
        mock_metrics.avg_return_pct = 2.1
        mock_metrics.lookback_days = 90
        mock_metrics.last_updated = datetime.utcnow()
        mock_instance.get_performance_metrics.return_value = mock_metrics
        
        response = client.get("/api/ml-learning/performance/AAPL")
        
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "AAPL"
    
    @patch('app.routes.ml_learning.MLLearningEngine')
    def test_performance_not_found(self, mock_engine, client):
        """Should return 404 for ticker with no data"""
        mock_instance = mock_engine.return_value
        mock_instance.get_performance_metrics.return_value = None
        
        response = client.get("/api/ml-learning/performance/NODATA")
        
        assert response.status_code == 404
    
    @patch('app.routes.ml_learning.MLLearningEngine')
    def test_adjust_confidence_preview(self, mock_engine, client):
        """Should preview confidence adjustment"""
        mock_instance = mock_engine.return_value
        mock_adjustment = Mock()
        mock_adjustment.original_confidence = 0.7
        mock_adjustment.adjusted_confidence = 0.75
        mock_adjustment.adjustment_factor = 1.07
        mock_adjustment.reason = "Good historical performance"
        mock_adjustment.metrics_used = None
        mock_instance.adjust_confidence.return_value = mock_adjustment
        
        response = client.get(
            "/api/ml-learning/adjust-confidence"
            "?ticker=AAPL&raw_confidence=0.7&prediction_type=UP"
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "adjusted_confidence" in data


# ==============================================================================
# Backtest API Tests
# ==============================================================================

class TestBacktestAPI:
    """Tests for Backtest endpoints"""
    
    @patch('app.routes.backtest.run_backtest')
    def test_run_backtest(self, mock_run, client):
        """POST /api/backtest/run/{ticker} should run backtest"""
        mock_result = Mock()
        mock_result.strategy_name = "Master Signal"
        mock_result.start_date = datetime(2025, 1, 1)
        mock_result.end_date = datetime(2025, 12, 31)
        mock_result.initial_capital = 100000.0
        mock_result.final_capital = 115000.0
        mock_result.total_return = 15.0
        mock_result.total_return_dollars = 15000.0
        mock_result.total_trades = 10
        mock_result.winning_trades = 7
        mock_result.losing_trades = 3
        mock_result.win_rate = 0.7
        mock_result.avg_return_per_trade = 1.5
        mock_result.max_drawdown = 8.5
        mock_result.sharpe_ratio = 1.8
        mock_result.profit_factor = 2.5
        mock_result.trades = []
        mock_run.return_value = mock_result
        
        response = client.post("/api/backtest/run/AAPL")
        
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "AAPL"
        assert "total_return" in data
        assert "win_rate" in data
    
    @patch('app.routes.backtest.run_backtest')
    def test_backtest_with_date_range(self, mock_run, client):
        """Should accept date range parameters"""
        mock_result = Mock()
        mock_result.strategy_name = "Master Signal"
        mock_result.start_date = datetime(2025, 1, 1)
        mock_result.end_date = datetime(2025, 6, 30)
        mock_result.initial_capital = 100000.0
        mock_result.final_capital = 108000.0
        mock_result.total_return = 8.0
        mock_result.total_return_dollars = 8000.0
        mock_result.total_trades = 5
        mock_result.winning_trades = 3
        mock_result.losing_trades = 2
        mock_result.win_rate = 0.6
        mock_result.avg_return_per_trade = 1.6
        mock_result.max_drawdown = 5.0
        mock_result.sharpe_ratio = 1.2
        mock_result.profit_factor = 1.8
        mock_result.trades = []
        mock_run.return_value = mock_result
        
        response = client.post(
            "/api/backtest/run/AAPL"
            "?start_date=2025-01-01&end_date=2025-06-30"
        )
        
        assert response.status_code == 200
    
    @patch('app.routes.backtest.run_backtest')
    def test_quick_stats(self, mock_run, client):
        """GET /api/backtest/quick-stats/{ticker} should return summary"""
        mock_result = Mock()
        mock_result.total_return = 12.5
        mock_result.win_rate = 0.65
        mock_result.total_trades = 8
        mock_result.sharpe_ratio = 1.5
        mock_result.max_drawdown = 7.0
        mock_run.return_value = mock_result
        
        response = client.get("/api/backtest/quick-stats/AAPL?days_back=180")
        
        assert response.status_code == 200
        data = response.json()
        assert "total_return" in data
        assert "win_rate" in data


# ==============================================================================
# Notifications API Tests
# ==============================================================================

class TestNotificationsAPI:
    """Tests for Notification endpoints"""
    
    def test_notification_status(self, client):
        """GET /api/notifications/status should return channel status"""
        response = client.get("/api/notifications/status")
        
        assert response.status_code == 200
        data = response.json()
        assert "telegram" in data
        assert "email" in data
        assert "total_channels" in data
    
    @patch('app.routes.notifications.NotificationService')
    def test_send_test_alert(self, mock_service, client):
        """POST /api/notifications/test-alert should send test"""
        mock_instance = mock_service.from_env.return_value
        mock_instance.channels = [Mock()]  # At least one channel
        mock_instance.send_alert = AsyncMock(return_value={"TelegramChannel": True})
        
        response = client.post(
            "/api/notifications/test-alert",
            json={
                "ticker": "AAPL",
                "buy_confidence": 85.0,
                "entry_price": 185.0,
                "target_price": 200.0,
            }
        )
        
        assert response.status_code == 200
    
    @patch('app.routes.notifications.NotificationService')
    def test_test_alert_no_channels(self, mock_service, client):
        """Should fail if no channels configured"""
        mock_instance = mock_service.from_env.return_value
        mock_instance.channels = []  # No channels
        
        response = client.post(
            "/api/notifications/test-alert",
            json={
                "ticker": "AAPL",
                "buy_confidence": 85.0,
            }
        )
        
        assert response.status_code == 400


# ==============================================================================
# Error Handling Tests
# ==============================================================================

class TestErrorHandling:
    """Tests for API error handling"""
    
    def test_invalid_endpoint_returns_404(self, client):
        """Invalid endpoint should return 404"""
        response = client.get("/api/nonexistent")
        
        assert response.status_code == 404
    
    def test_validation_error_returns_422(self, client):
        """Validation errors should return 422"""
        # Invalid min_confidence (over 100)
        response = client.get("/api/action-center/opportunities?min_confidence=150")
        
        assert response.status_code == 422
    
    @patch('app.routes.master_signal.calculate_buy_confidence')
    def test_internal_error_returns_500(self, mock_calc, client):
        """Internal errors should return 500"""
        mock_calc.side_effect = Exception("Database error")
        
        response = client.get("/api/master-signal/AAPL")
        
        assert response.status_code == 500


# ==============================================================================
# Integration Tests
# ==============================================================================

@pytest.mark.integration
class TestAPIIntegration:
    """Full API integration tests (requires real services)"""
    
    def test_full_trading_workflow(self, client):
        """Test complete trading analysis workflow"""
        # 1. Get Master Signal
        # 2. Check ML Performance
        # 3. Run Backtest
        # 4. Verify consistency
        pass
    
    def test_cross_endpoint_consistency(self, client):
        """Data should be consistent across endpoints"""
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
