"""
Analysis Routes

FastAPI endpoints for analyzing transcripts and extracting stock mentions.
These endpoints wrap the core business logic from app.core.analysis and
app.core.extractors while maintaining the exact same behavior as the original
Streamlit application.

CRITICAL: This is part of a family financial security application for a client
with Multiple Sclerosis. All analysis logic must remain identical to preserve
accuracy and reliability.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from ..core.analysis import StockAnalyzer
from ..core.extractors import (
    extract_video_id,
    get_youtube_transcript,
    extract_google_doc_id,
    get_google_doc_content,
)
from ..database.connection import get_db
from ..database.repositories import StockRepository
from ..schemas.requests import (
    AnalyzeTextRequest,
    AnalyzeYouTubeRequest,
    AnalyzeGoogleDocsRequest,
)
from ..schemas.responses import AnalysisResponse, StockResponse, ErrorResponse
from ..config import get_settings

router = APIRouter(prefix="/api/analyze", tags=["Analysis"])


@router.post(
    "/text",
    response_model=AnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Analyze raw transcript text",
    description="Extract stock mentions from raw transcript text using Gemini AI with the Fiduciary Analyst persona",
)
async def analyze_text(
    request: AnalyzeTextRequest,
    db: Session = Depends(get_db),
) -> AnalysisResponse:
    """
    Analyze raw transcript text for stock mentions.
    
    Uses the FIDUCIARY_ANALYST_PROMPT with aggressive extraction rules
    and The Gomes Rules framework (Information Arbitrage, Catalysts, Risks).
    """
    try:
        settings = get_settings()
        analyzer = StockAnalyzer(api_key=settings.gemini_api_key)
        
        # Run analysis using core business logic
        stocks_data = analyzer.analyze_transcript(
            transcript=request.transcript,
            speaker=request.speaker,
            source_type=request.source_type,
        )
        
        if not stocks_data:
            return AnalysisResponse(
                success=True,
                message="Analysis completed but no stocks were found in the transcript",
                stocks_found=0,
                stocks=[],
            )
        
        # Save to database using repository pattern
        repository = StockRepository(db)
        saved_stocks = repository.create_stocks(stocks_data)
        
        # Convert to response models
        stock_responses = [
            StockResponse.model_validate(stock) for stock in saved_stocks
        ]
        
        return AnalysisResponse(
            success=True,
            message=f"Successfully analyzed transcript and found {len(saved_stocks)} stock mention(s)",
            stocks_found=len(saved_stocks),
            stocks=stock_responses,
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {str(e)}",
        )


@router.post(
    "/youtube",
    response_model=AnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Analyze YouTube video transcript",
    description="Fetch YouTube transcript and analyze for stock mentions",
)
async def analyze_youtube(
    request: AnalyzeYouTubeRequest,
    db: Session = Depends(get_db),
) -> AnalysisResponse:
    """
    Analyze YouTube video transcript for stock mentions.
    
    Fetches transcript using youtube_transcript_api, then applies
    the same analysis as analyze_text.
    """
    try:
        # Extract video ID and fetch transcript
        video_id = extract_video_id(request.url)
        if not video_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid YouTube URL format",
            )
        
        transcript = get_youtube_transcript(video_id)
        if not transcript:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Could not fetch transcript for this YouTube video",
            )
        
        # Use speaker from request or default to "YouTube Speaker"
        speaker = request.speaker or "YouTube Speaker"
        
        # Run analysis
        settings = get_settings()
        analyzer = StockAnalyzer(api_key=settings.gemini_api_key)
        stocks_data = analyzer.analyze_transcript(
            transcript=transcript,
            speaker=speaker,
            source_type="youtube",
        )
        
        if not stocks_data:
            return AnalysisResponse(
                success=True,
                message="Analysis completed but no stocks were found in the video",
                stocks_found=0,
                stocks=[],
            )
        
        # Save to database
        repository = StockRepository(db)
        saved_stocks = repository.create_stocks(stocks_data)
        
        stock_responses = [
            StockResponse.model_validate(stock) for stock in saved_stocks
        ]
        
        return AnalysisResponse(
            success=True,
            message=f"Successfully analyzed YouTube video and found {len(saved_stocks)} stock mention(s)",
            stocks_found=len(saved_stocks),
            stocks=stock_responses,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"YouTube analysis failed: {str(e)}",
        )


@router.post(
    "/google-docs",
    response_model=AnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Analyze Google Docs content",
    description="Fetch Google Docs content and analyze for stock mentions",
)
async def analyze_google_docs(
    request: AnalyzeGoogleDocsRequest,
    db: Session = Depends(get_db),
) -> AnalysisResponse:
    """
    Analyze Google Docs content for stock mentions.
    
    Fetches document content using Google Docs API, then applies
    the same analysis as analyze_text.
    """
    try:
        # Extract document ID and fetch content
        doc_id = extract_google_doc_id(request.url)
        if not doc_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Google Docs URL format",
            )
        
        content = get_google_doc_content(doc_id)
        if not content:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Could not fetch content from this Google Doc",
            )
        
        # Run analysis
        settings = get_settings()
        analyzer = StockAnalyzer(api_key=settings.gemini_api_key)
        stocks_data = analyzer.analyze_transcript(
            transcript=content,
            speaker=request.speaker,
            source_type="google_docs",
        )
        
        if not stocks_data:
            return AnalysisResponse(
                success=True,
                message="Analysis completed but no stocks were found in the document",
                stocks_found=0,
                stocks=[],
            )
        
        # Save to database
        repository = StockRepository(db)
        saved_stocks = repository.create_stocks(stocks_data)
        
        stock_responses = [
            StockResponse.model_validate(stock) for stock in saved_stocks
        ]
        
        return AnalysisResponse(
            success=True,
            message=f"Successfully analyzed Google Doc and found {len(saved_stocks)} stock mention(s)",
            stocks_found=len(saved_stocks),
            stocks=stock_responses,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Google Docs analysis failed: {str(e)}",
        )


@router.get(
    "/health",
    summary="Health check for analysis service",
    description="Verify that Gemini AI connection is working",
)
async def health_check():
    """Check if the analysis service is operational."""
    try:
        settings = get_settings()
        analyzer = StockAnalyzer(api_key=settings.gemini_api_key)
        return {
            "status": "healthy",
            "service": "analysis",
            "model": "gemini-3-pro-preview",
            "features": ["google_search", "aggressive_extraction", "gomes_rules"],
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Analysis service unavailable: {str(e)}",
        )
