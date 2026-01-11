"""
API Request/Response Schemas

This module exports Pydantic models for FastAPI request validation
and response serialization.
"""

from .requests import (
    AnalyzeTextRequest,
    AnalyzeYouTubeRequest,
    AnalyzeGoogleDocsRequest,
)
from .responses import (
    StockAnalysisResult,
    StockResponse,
    AnalysisResponse,
    PortfolioResponse,
    StocksListResponse,
    HealthCheckResponse,
    ErrorResponse,
)

__all__ = [
    "AnalyzeTextRequest",
    "AnalyzeYouTubeRequest",
    "AnalyzeGoogleDocsRequest",
    "StockAnalysisResult",
    "StockResponse",
    "AnalysisResponse",
    "PortfolioResponse",
    "StocksListResponse",
    "HealthCheckResponse",
    "ErrorResponse",
]
