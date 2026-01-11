"""
API Request Schemas

Pydantic models for validating incoming requests to FastAPI endpoints.
"""

from pydantic import BaseModel, Field, HttpUrl
from typing import Optional


class AnalyzeTextRequest(BaseModel):
    """Request model for analyzing raw transcript text."""
    
    transcript: str = Field(
        ...,
        description="Raw transcript text to analyze for stock mentions",
        min_length=10
    )
    speaker: str = Field(
        ...,
        description="Name of the speaker/source",
        min_length=1,
        max_length=200
    )
    source_type: str = Field(
        default="manual_input",
        description="Type of source (manual_input, youtube, google_docs)",
        max_length=50
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "transcript": "I'm very bullish on NVDA. The AI revolution is just beginning...",
                "speaker": "Mark Gomes",
                "source_type": "manual_input"
            }
        }


class AnalyzeYouTubeRequest(BaseModel):
    """Request model for analyzing YouTube video transcripts."""
    
    url: str = Field(
        ...,
        description="YouTube video URL",
        min_length=10
    )
    speaker: Optional[str] = Field(
        default=None,
        description="Speaker name (auto-detected if not provided)",
        max_length=200
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "speaker": "Mark Gomes"
            }
        }


class AnalyzeGoogleDocsRequest(BaseModel):
    """Request model for analyzing Google Docs content."""
    
    url: str = Field(
        ...,
        description="Google Docs URL",
        min_length=10
    )
    speaker: str = Field(
        ...,
        description="Name of the speaker/author",
        min_length=1,
        max_length=200
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://docs.google.com/document/d/1ABC123/edit",
                "speaker": "Mark Gomes"
            }
        }
