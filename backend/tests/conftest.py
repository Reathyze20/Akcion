"""
Test Configuration
==================

Pytest configuration and fixtures.

Author: GitHub Copilot with Claude Sonnet 4.5
Date: 2025-01-17
Version: 1.0.0
"""

import pytest
import os
from unittest.mock import Mock


# ==============================================================================
# Environment Setup
# ==============================================================================

@pytest.fixture(scope="session", autouse=True)
def setup_test_env():
    """Setup test environment variables"""
    os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
    os.environ['OPENAI_API_KEY'] = 'test-key'
    

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
