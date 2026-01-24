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
    StockPortfolioResponse,
    StocksListResponse,
    HealthCheckResponse,
    ErrorResponse,
)
from .portfolio import (
    PortfolioCreate,
    PortfolioResponse,
    PositionCreate,
    PositionUpdate,
    PositionResponse,
    CSVUploadRequest,
    CSVUploadResponse,
    PriceRefreshRequest,
    PriceRefreshResponse,
    MarketStatusUpdate,
    MarketStatusResponse,
    EnrichedStockResponse,
    MatchAnalysisRequest,
    MatchAnalysisResponse,
    PortfolioSummaryResponse,
)
from .gomes import (
    DeepDueDiligenceRequest,
    DeepDueDiligenceResponse,
    DeepDueDiligenceResult,
    ThesisDriftResult,
    PriceTargetsSchema,
)

__all__ = [
    "AnalyzeTextRequest",
    "AnalyzeYouTubeRequest",
    "AnalyzeGoogleDocsRequest",
    "StockAnalysisResult",
    "StockResponse",
    "AnalysisResponse",
    "StockPortfolioResponse",
    "StocksListResponse",
    "HealthCheckResponse",
    "ErrorResponse",
    # Portfolio schemas
    "PortfolioCreate",
    "PortfolioResponse",
    "PositionCreate",
    "PositionUpdate",
    "PositionResponse",
    "CSVUploadRequest",
    "CSVUploadResponse",
    "PriceRefreshRequest",
    "PriceRefreshResponse",
    "MarketStatusUpdate",
    "MarketStatusResponse",
    "EnrichedStockResponse",
    "MatchAnalysisRequest",
    "MatchAnalysisResponse",
    "PortfolioSummaryResponse",
    # Gomes Deep Due Diligence
    "DeepDueDiligenceRequest",
    "DeepDueDiligenceResponse",
    "DeepDueDiligenceResult",
    "ThesisDriftResult",
    "PriceTargetsSchema",
]
