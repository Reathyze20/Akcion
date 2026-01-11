"""
API Response Schemas

Pydantic models for serializing responses from FastAPI endpoints.
"""

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class StockAnalysisResult(BaseModel):
    """Individual stock analysis result from AI - Trading focused."""
    
    ticker: str
    company_name: Optional[str] = None
    sentiment: str = "Neutral"
    gomes_score: int = Field(ge=1, le=10)
    price_target: Optional[str] = None
    edge: Optional[str] = None
    catalysts: Optional[str] = None
    risks: Optional[str] = None
    status: Optional[str] = None
    time_horizon: Optional[str] = "Long-term"
    conviction_score: Optional[int] = Field(default=None, ge=1, le=10)
    
    # Trading action fields
    action_verdict: Optional[str] = "WATCH_LIST"  # BUY_NOW, ACCUMULATE, WATCH_LIST, TRIM, SELL, AVOID
    entry_zone: Optional[str] = None
    price_target_short: Optional[str] = None
    price_target_long: Optional[str] = None
    stop_loss_risk: Optional[str] = None
    moat_rating: Optional[int] = Field(default=3, ge=1, le=5)
    trade_rationale: Optional[str] = None
    chart_setup: Optional[str] = None


class StockResponse(BaseModel):
    """Response model for individual stock data."""
    
    id: int
    created_at: datetime
    ticker: str
    company_name: Optional[str]
    source_type: str
    speaker: str
    sentiment: Optional[str]
    gomes_score: Optional[int]
    conviction_score: Optional[int]
    price_target: Optional[str]
    time_horizon: Optional[str]
    edge: Optional[str]  # Information Arbitrage
    catalysts: Optional[str]
    risks: Optional[str]
    raw_notes: Optional[str]
    
    # Trading action fields
    action_verdict: Optional[str] = None
    entry_zone: Optional[str] = None
    price_target_short: Optional[str] = None
    price_target_long: Optional[str] = None
    stop_loss_risk: Optional[str] = None
    moat_rating: Optional[int] = None
    trade_rationale: Optional[str] = None
    chart_setup: Optional[str] = None
    
    class Config:
        from_attributes = True  # Allows SQLAlchemy model conversion
        json_schema_extra = {
            "example": {
                "id": 1,
                "created_at": "2026-01-10T12:00:00",
                "ticker": "NVDA",
                "company_name": "NVIDIA Corporation",
                "source_type": "youtube",
                "speaker": "Mark Gomes",
                "sentiment": "BULLISH",
                "gomes_score": 9,
                "conviction_score": 8,
                "price_target": "$1200 in 12-18 months",
                "time_horizon": "12-18 months",
                "edge": "First-mover advantage in AI chip architecture",
                "catalysts": "AI adoption acceleration, new product launches",
                "risks": "Competitive pressure from AMD, supply chain constraints",
                "raw_notes": "Strong buy recommendation based on AI tailwinds"
            }
        }


class AnalysisResponse(BaseModel):
    """Response model for analysis operations."""
    
    success: bool
    message: str
    stocks_found: int
    stocks: List[StockAnalysisResult]
    source_id: str
    source_type: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Successfully analyzed transcript and found 3 stock mentions",
                "stocks_found": 3,
                "stocks": [],
                "source_id": "video_123",
                "source_type": "YouTube"
            }
        }


class PortfolioResponse(BaseModel):
    """Response model for portfolio data."""
    
    total_stocks: int
    stocks: List[StockResponse]
    filters_applied: Optional[dict] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_stocks": 10,
                "stocks": [],
                "filters_applied": {
                    "sentiment": "BULLISH",
                    "min_gomes_score": 7
                }
            }
        }


class StocksListResponse(BaseModel):
    """Response model for list of stocks."""
    
    stocks: List[StockResponse]
    total_stocks: int
    filters_applied: Optional[dict] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "stocks": [],
                "total_stocks": 10,
                "filters_applied": None
            }
        }


class HealthCheckResponse(BaseModel):
    """Response model for health check endpoint."""
    
    status: str
    message: str
    timestamp: datetime
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "message": "API is running",
                "timestamp": "2026-01-10T12:00:00"
            }
        }


class ErrorResponse(BaseModel):
    """Response model for error messages."""
    
    success: bool = False
    error: str
    detail: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": False,
                "error": "Analysis failed",
                "detail": "Could not extract transcript from YouTube URL"
            }
        }
