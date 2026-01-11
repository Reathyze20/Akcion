"""
API Routes Package

This package contains all FastAPI route handlers for the investment
analysis application.
"""

from .analysis import router as analysis_router
from .stocks import router as stocks_router

__all__ = ["analysis_router", "stocks_router"]
