"""
Pydantic schemas for Analysis Intelligence Module
"""
from datetime import datetime
from datetime import date as date_type
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator


# ==========================================
# Analyst Transcript Schemas
# ==========================================

class TranscriptBase(BaseModel):
    """Base transcript schema"""
    source_name: str = Field(..., description="Source name (e.g., 'Mark Gomes', 'Breakout Investors')")
    raw_text: str = Field(..., description="Raw transcript text")
    detected_tickers: List[str] = Field(default=[], description="Detected stock tickers")
    date: date_type = Field(..., description="Video/transcript date")
    video_url: Optional[str] = Field(None, description="Video URL")
    transcript_quality: Optional[str] = Field(None, description="Quality: high, medium, low")


class TranscriptCreate(TranscriptBase):
    """Create new transcript"""
    pass


class TranscriptUpdate(BaseModel):
    """Update transcript (all fields optional)"""
    processed_summary: Optional[str] = None
    is_processed: Optional[bool] = None
    processing_notes: Optional[str] = None


class TranscriptResponse(TranscriptBase):
    """Transcript response"""
    id: int
    processed_summary: Optional[str] = None
    is_processed: bool
    processing_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    ticker_count: int
    
    model_config = {"from_attributes": True}


class TranscriptSummaryResponse(BaseModel):
    """Transcript summary (for list views)"""
    id: int
    source_name: str
    date: date_type
    ticker_count: int
    detected_tickers: List[str]
    summary_preview: Optional[str]
    is_processed: bool
    created_at: datetime
    
    model_config = {"from_attributes": True}


# ==========================================
# SWOT Analysis Schemas
# ==========================================

class SWOTData(BaseModel):
    """SWOT data structure"""
    strengths: List[str] = Field(..., description="List of strengths")
    weaknesses: List[str] = Field(..., description="List of weaknesses")
    opportunities: List[str] = Field(..., description="List of opportunities")
    threats: List[str] = Field(..., description="List of threats")
    
    @field_validator('strengths', 'weaknesses', 'opportunities', 'threats')
    @classmethod
    def validate_not_empty(cls, v):
        if not v or len(v) == 0:
            raise ValueError("Each SWOT category must have at least one item")
        return v


class SWOTCreate(BaseModel):
    """Create new SWOT analysis"""
    ticker: str = Field(..., description="Stock ticker")
    swot_data: SWOTData = Field(..., description="SWOT analysis data")
    ai_model_version: str = Field(..., description="AI model version used")
    confidence_score: Optional[float] = Field(None, ge=0, le=1, description="Confidence score 0-1")
    stock_id: Optional[int] = None
    watchlist_id: Optional[int] = None
    transcript_id: Optional[int] = None
    notes: Optional[str] = None
    expires_at: Optional[datetime] = None


class SWOTUpdate(BaseModel):
    """Update SWOT analysis"""
    swot_data: Optional[SWOTData] = None
    confidence_score: Optional[float] = Field(None, ge=0, le=1)
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class SWOTResponse(BaseModel):
    """SWOT analysis response"""
    id: int
    ticker: str
    swot_data: Dict[str, List[str]]
    ai_model_version: str
    confidence_score: Optional[float]
    generated_at: datetime
    expires_at: Optional[datetime]
    is_active: bool
    notes: Optional[str]
    stock_id: Optional[int]
    watchlist_id: Optional[int]
    transcript_id: Optional[int]
    total_points: int
    
    model_config = {"from_attributes": True}


class SWOTWithContext(BaseModel):
    """SWOT with additional context"""
    id: int
    ticker: str
    company_name: Optional[str]
    swot_data: Dict[str, List[str]]
    confidence_score: Optional[float]
    ai_model_version: str
    generated_at: datetime
    conviction_score: Optional[float]
    action_verdict: Optional[str]
    transcript_source: Optional[str]
    transcript_date: Optional[date_type]


# ==========================================
# Watchlist Enhancement Schemas
# ==========================================

class WatchlistAnalysisUpdate(BaseModel):
    """Update watchlist with analysis fields"""
    conviction_score: Optional[float] = Field(None, ge=0, le=10, description="Conviction Score 0-10")
    investment_thesis: Optional[str] = Field(None, description="Investment thesis")
    risks: Optional[str] = Field(None, description="Identified risks")


class WatchlistAnalysisResponse(BaseModel):
    """Enhanced watchlist response with analysis"""
    id: int
    ticker: str
    company_name: Optional[str]
    action_verdict: Optional[str]
    confidence_score: Optional[float]
    conviction_score: Optional[float]
    investment_thesis: Optional[str]
    risks: Optional[str]
    last_updated: datetime
    swot_data: Optional[Dict[str, List[str]]]
    swot_model: Optional[str]
    swot_generated_at: Optional[datetime]


# ==========================================
# Batch Operations
# ==========================================

class BatchTranscriptCreate(BaseModel):
    """Create multiple transcripts"""
    transcripts: List[TranscriptCreate] = Field(..., min_length=1)


class BatchSWOTCreate(BaseModel):
    """Create multiple SWOT analyses"""
    analyses: List[SWOTCreate] = Field(..., min_length=1)


# ==========================================
# Search & Filter Schemas
# ==========================================

class TranscriptSearchParams(BaseModel):
    """Search parameters for transcripts"""
    source_name: Optional[str] = None
    ticker: Optional[str] = None
    date_from: Optional[date_type] = None
    date_to: Optional[date_type] = None
    is_processed: Optional[bool] = None
    limit: int = Field(50, ge=1, le=200)


class SWOTSearchParams(BaseModel):
    """Search parameters for SWOT analyses"""
    ticker: Optional[str] = None
    is_active: bool = True
    min_confidence: Optional[float] = Field(None, ge=0, le=1)
    limit: int = Field(50, ge=1, le=200)


# ==========================================
# Statistics & Reports
# ==========================================

class AnalysisStats(BaseModel):
    """Statistics about analysis data"""
    total_transcripts: int
    processed_transcripts: int
    total_swots: int
    active_swots: int
    tickers_with_conviction_score: int
    avg_conviction_score: Optional[float]
    top_sources: List[Dict[str, Any]]


class TopGomesPick(BaseModel):
    """Top Conviction Score ticker"""
    ticker: str
    conviction_score: float
    company_name: Optional[str]
    action_verdict: Optional[str]
    investment_thesis: Optional[str]
