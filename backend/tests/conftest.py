"""
Test Configuration
==================

Pytest configuration and fixtures.

Author: GitHub Copilot with Claude Opus 4.5
Date: 2026-01-18
Version: 1.0.0
"""

import pytest
import os
from unittest.mock import Mock, MagicMock
from datetime import datetime


# ==============================================================================
# Environment Setup
# ==============================================================================

@pytest.fixture(scope="session", autouse=True)
def setup_test_env():
    """Setup test environment variables"""
    os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
    os.environ['OPENAI_API_KEY'] = 'test-key'
    os.environ['GEMINI_API_KEY'] = 'test-key'
    

# ==============================================================================
# Database Fixtures
# ==============================================================================

@pytest.fixture
def mock_db():
    """Create a mock database session"""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.all.return_value = []
    db.add = Mock()
    db.commit = Mock()
    db.rollback = Mock()
    db.close = Mock()
    return db


@pytest.fixture
def mock_db_with_data(mock_db):
    """Mock database with sample data"""
    from app.models.trading import ActiveWatchlist, MLPrediction
    
    # Sample watchlist
    watchlist_item = MagicMock()
    watchlist_item.id = 1
    watchlist_item.ticker = "AAPL"
    watchlist_item.is_active = True
    
    mock_db.query.return_value.filter.return_value.all.return_value = [watchlist_item]
    
    return mock_db


# ==============================================================================
# Sample Data Fixtures
# ==============================================================================

@pytest.fixture
def sample_stock_data():
    """Sample stock analysis data"""
    return {
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "sentiment": "BULLISH",
        "gomes_score": 8,
        "edge": "Strong iPhone sales momentum",
        "catalysts": ["New product launch", "AI integration"],
        "risks": ["China exposure", "Regulation"],
        "price_target": "$220",
        "time_horizon": "12 months"
    }


@pytest.fixture
def sample_prediction_data():
    """Sample ML prediction data"""
    return {
        "ticker": "AAPL",
        "prediction_type": "UP",
        "confidence": 0.85,
        "predicted_price": 195.50,
        "current_price": 185.00,
        "horizon_days": 5,
        "model_version": "PatchTST-v1.0",
        "created_at": datetime.utcnow(),
    }


# ==============================================================================
# Pytest Configuration
# ==============================================================================

def pytest_configure(config):
    """Pytest initialization"""
    config.addinivalue_line(
        "markers", "asyncio: mark test as async"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )


def pytest_collection_modifyitems(config, items):
    """Skip integration tests by default unless --run-integration is specified"""
    if config.getoption("--run-integration", default=False):
        return
    
    skip_integration = pytest.mark.skip(reason="Use --run-integration to run")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)


def pytest_addoption(parser):
    """Add custom command line options"""
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run integration tests"
    )
    parser.addoption(
        "--run-slow",
        action="store_true",
        default=False,
        help="Run slow tests"
    )
