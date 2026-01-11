"""
Pydantic Schemas for API Request/Response validation

These models define the shape of data flowing through the API.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator


# ==============================================================================
# Request Schemas
# ==============================================================================

class AnalyzeTextRequest(BaseModel):
    """Request body for text analysis endpoint"""
    transcript: str = Field(
        ..., 
        min_length=10,
        description="Investment transcript text to analyze"
    )
    source_id: str = Field(
        default="manual",
        description="Identifier for this analysis source"
    )
    source_type: str = Field(
        default="Manual Entry",
        description="Type of source (YouTube, Google Docs, etc.)"
    )
    speaker: str = Field(
        default="Mark Gomes",
        description="Speaker/analyst name"
    )
    api_key: str = Field(
        ...,
        description="Google Gemini API key"
    )


class AnalyzeYouTubeRequest(BaseModel):
    """Request body for YouTube video analysis"""
    video_url: str = Field(
        ...,
        description="YouTube video URL"
    )
    speaker: str = Field(
        default="Mark Gomes",
        description="Speaker in the video"
    )
    api_key: str = Field(
        ...,
        description="Google Gemini API key"
    )
    
    @field_validator('video_url')
    @classmethod
    def validate_youtube_url(cls, v: str) -> str:
        """Ensure it's a valid YouTube URL"""
        if 'youtube.com' not in v and 'youtu.be' not in v:
            raise ValueError('Must be a valid YouTube URL')
        return v


class AnalyzeGoogleDocsRequest(BaseModel):
    """Request body for Google Docs analysis"""
    doc_url: str = Field(
        ...,
        description="Google Docs sharing URL"
    )
    speaker: str = Field(
        default="Mark Gomes",
        description="Speaker/author"
    )
    api_key: str = Field(
        ...,
        description="Google Gemini API key"
    )
    
    @field_validator('doc_url')
    @classmethod
    def validate_docs_url(cls, v: str) -> str:
        """Ensure it's a valid Google Docs URL"""
        if 'docs.google.com' not in v:
            raise ValueError('Must be a valid Google Docs URL')
        return v


# ==============================================================================
# Response Schemas
# ==============================================================================

class StockAnalysisResult(BaseModel):
    """Individual stock analysis result from AI"""
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


class AnalysisResponse(BaseModel):
    """Response from analysis endpoints"""
    success: bool
    message: str
    stocks: List[StockAnalysisResult] = []
    stocks_saved: int = 0
    source_id: str
    source_type: str


class StockResponse(BaseModel):
    """Single stock database record"""
    id: int
    created_at: datetime
    ticker: str
    company_name: Optional[str] = None
    source_type: Optional[str] = None
    speaker: Optional[str] = None
    sentiment: Optional[str] = None
    gomes_score: Optional[int] = None
    conviction_score: Optional[int] = None
    price_target: Optional[str] = None
    time_horizon: Optional[str] = None
    edge: Optional[str] = None
    catalysts: Optional[str] = None
    risks: Optional[str] = None
    raw_notes: Optional[str] = None
    
    class Config:
        from_attributes = True  # For SQLAlchemy models


class StocksListResponse(BaseModel):
    """Response for listing stocks"""
    success: bool
    count: int
    stocks: List[StockResponse]


class HealthCheckResponse(BaseModel):
    """Health check endpoint response"""
    status: str
    app_name: str
    version: str
    database_connected: bool


class ErrorResponse(BaseModel):
    """Standard error response"""
    success: bool = False
    error: str
    detail: Optional[str] = None
