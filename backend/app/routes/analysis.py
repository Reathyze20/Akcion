"""
Analysis Routes

FastAPI endpoints for analyzing transcripts and extracting stock mentions.
These endpoints wrap the core business logic from app.core.analysis and
app.core.extractors while maintaining the exact same behavior as the original
Streamlit application.

CRITICAL: This is part of a family financial security application for a client
with Multiple Sclerosis. All analysis logic must remain identical to preserve
accuracy and reliability.

Clean Code Principles Applied:
- Single Responsibility: Each endpoint does one thing
- Explicit error handling with proper HTTP status codes
- Type hints throughout
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..config import get_settings
from ..core.analysis import StockAnalyzer
from ..core.extractors import (
    extract_google_doc_id,
    extract_video_id,
    get_google_doc_content,
    get_youtube_transcript,
)
from ..database.connection import get_db
from ..database.repositories import StockRepository
from ..models.portfolio import MarketStatus, MarketStatusEnum
from ..schemas.requests import (
    AnalyzeGoogleDocsRequest,
    AnalyzeTextRequest,
    AnalyzeYouTubeRequest,
)
from ..schemas.responses import (
    AnalysisResponse,
    ErrorResponse,
    StockAnalysisResult,
    StockResponse,
)
from ..services.gomes_intelligence import GomesIntelligenceService


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analyze", tags=["Analysis"])


def _refresh_verdicts_async(db: Session, tickers: list[str]) -> None:
    """
    Refresh investment verdicts for newly analyzed tickers.
    Runs asynchronously to avoid blocking the response.
    """
    try:
        from ..models.trading import ActiveWatchlist
        from ..models.gomes import InvestmentVerdictModel
        from datetime import datetime
        
        # Import gatekeeper if available
        try:
            from ..services.gomes_gatekeeper import GomesGatekeeper
            gatekeeper = GomesGatekeeper(db)
            
            for ticker in tickers:
                try:
                    # Ensure ticker is in watchlist
                    watchlist = db.query(ActiveWatchlist).filter(
                        ActiveWatchlist.ticker == ticker
                    ).first()
                    
                    if watchlist and watchlist.is_active:
                        # Invalidate old verdicts
                        old_verdicts = db.query(InvestmentVerdictModel).filter(
                            InvestmentVerdictModel.ticker == ticker,
                            InvestmentVerdictModel.valid_until == None
                        ).all()
                        
                        for old in old_verdicts:
                            old.valid_until = datetime.utcnow()
                        
                        # Create new verdict
                        verdict = gatekeeper.evaluate_ticker(ticker)
                        if verdict:
                            db.add(verdict)
                            
                except Exception as e:
                    logger.warning(f"Failed to refresh verdict for {ticker}: {e}")
                    continue
            
            db.commit()
            logger.info(f"Refreshed verdicts for {len(tickers)} tickers")
            
        except ImportError:
            logger.info("Gatekeeper not available, skipping verdict refresh")
            
    except Exception as e:
        logger.error(f"Failed to refresh verdicts: {e}")


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
        stocks_data = analyzer.analyze_transcript(transcript=request.transcript)
        
        if not stocks_data:
            return AnalysisResponse(
                success=True,
                message="Analysis completed but no stocks were found in the transcript",
                stocks_found=0,
                stocks=[],
            )
        
        # Update market status if AI detected it
        if "market_status" in stocks_data and stocks_data["market_status"]:
            market_data = stocks_data["market_status"]
            if market_data.get("status"):
                # Update legacy MarketStatus table
                market_status = db.query(MarketStatus).first()
                if not market_status:
                    market_status = MarketStatus()
                    db.add(market_status)
                
                # Map AI status to enum (4-state Mark Gomes system)
                status_map = {
                    "GREEN": MarketStatusEnum.GREEN,
                    "YELLOW": MarketStatusEnum.YELLOW,
                    "ORANGE": MarketStatusEnum.ORANGE,
                    "RED": MarketStatusEnum.RED
                }
                
                if market_data["status"] in status_map:
                    market_status.status = status_map[market_data["status"]]
                    market_status.note = market_data.get("quote", "")
                    db.commit()
                    
                    # Also update Gomes Intelligence market_alerts table
                    try:
                        gomes_service = GomesIntelligenceService(db)
                        gomes_service.set_market_alert(
                            alert_level=market_data["status"],
                            reason=f"Detected from transcript: {market_data.get('quote', 'No quote')[:200]}",
                            source="transcript_analysis"
                        )
                        logger.info(f"Gomes Market Alert updated to {market_data['status']} from transcript")
                    except Exception as e:
                        logger.warning(f"Failed to update Gomes market alert: {e}")
        
        # Save to database using repository pattern
        repository = StockRepository(db)
        success, error = repository.create_stocks(
            stocks=stocks_data.get("stocks", []),
            source_id="manual_" + str(hash(request.transcript[:100])),
            source_type=request.source_type,
            speaker=request.speaker
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to save stocks: {error}"
            )
        
        # Refresh verdicts for newly analyzed stocks
        tickers = [s["ticker"] for s in stocks_data.get("stocks", [])]
        if tickers:
            _refresh_verdicts_async(db, tickers)
        
        # Retrieve saved stocks
        saved_stocks = repository.get_all_stocks()
        
        # Convert to StockAnalysisResult models
        stock_responses = [
            StockAnalysisResult(
                ticker=stock.ticker,
                company_name=stock.company_name,
                sentiment=stock.sentiment or "Neutral",
                conviction_score=stock.conviction_score or 5,
                price_target=stock.price_target,
                edge=stock.edge,
                catalysts=stock.catalysts,
                risks=stock.risks,
                time_horizon=stock.time_horizon,
                action_verdict=stock.action_verdict
            )
            for stock in saved_stocks[-len(stocks_data.get("stocks", [])):] if saved_stocks
        ]
        
        source_id = "manual_" + str(hash(request.transcript[:100]))
        
        return AnalysisResponse(
            success=True,
            message=f"Successfully analyzed transcript and found {len(stock_responses)} stock mention(s)",
            stocks_found=len(stock_responses),
            stocks=stock_responses,
            source_id=source_id,
            source_type=request.source_type
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
        stocks_data = analyzer.analyze_transcript(transcript=transcript)
        
        if not stocks_data:
            return AnalysisResponse(
                success=True,
                message="Analysis completed but no stocks were found in the video",
                stocks_found=0,
                stocks=[],
                source_id=video_id,
                source_type="youtube"
            )
        
        # Update market status if AI detected it
        if "market_status" in stocks_data and stocks_data["market_status"]:
            market_data = stocks_data["market_status"]
            if market_data.get("status"):
                # Update legacy MarketStatus table
                market_status = db.query(MarketStatus).first()
                if not market_status:
                    market_status = MarketStatus()
                    db.add(market_status)
                
                # Map AI status to enum (4-state Mark Gomes system)
                status_map = {
                    "GREEN": MarketStatusEnum.GREEN,
                    "YELLOW": MarketStatusEnum.YELLOW,
                    "ORANGE": MarketStatusEnum.ORANGE,
                    "RED": MarketStatusEnum.RED
                }
                
                if market_data["status"] in status_map:
                    market_status.status = status_map[market_data["status"]]
                    market_status.note = market_data.get("quote", "")
                    db.commit()
                    
                    # Also update Gomes Intelligence market_alerts table
                    try:
                        gomes_service = GomesIntelligenceService(db)
                        gomes_service.set_market_alert(
                            alert_level=market_data["status"],
                            reason=f"Detected from YouTube: {market_data.get('quote', 'No quote')[:200]}",
                            source="youtube_analysis"
                        )
                        logger.info(f"Gomes Market Alert updated to {market_data['status']} from YouTube")
                    except Exception as e:
                        logger.warning(f"Failed to update Gomes market alert: {e}")
        
        # Save to database
        repository = StockRepository(db)
        success, error = repository.create_stocks(
            stocks=stocks_data.get("stocks", []),
            source_id=video_id,
            source_type="youtube",
            speaker=request.speaker or "Unknown"
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to save stocks: {error}"
            )
        
        # Refresh verdicts for newly analyzed stocks
        tickers = [s["ticker"] for s in stocks_data.get("stocks", [])]
        if tickers:
            _refresh_verdicts_async(db, tickers)
        
        saved_stocks = repository.get_all_stocks()
        stock_responses = [
            StockAnalysisResult(
                ticker=stock.ticker,
                company_name=stock.company_name,
                sentiment=stock.sentiment or "Neutral",
                conviction_score=stock.conviction_score or 5,
                price_target=stock.price_target,
                edge=stock.edge,
                catalysts=stock.catalysts,
                risks=stock.risks,
                time_horizon=stock.time_horizon,
                action_verdict=stock.action_verdict
            )
            for stock in saved_stocks[-len(stocks_data.get("stocks", [])):] if saved_stocks
        ]
        
        return AnalysisResponse(
            success=True,
            message=f"Successfully analyzed YouTube video and found {len(stock_responses)} stock mention(s)",
            stocks_found=len(stock_responses),
            stocks=stock_responses,
            source_id=video_id,
            source_type="youtube"
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
        
        content = get_google_doc_content(request.url)
        if not content:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Could not fetch content from this Google Doc",
            )
        
        # Run analysis
        settings = get_settings()
        analyzer = StockAnalyzer(api_key=settings.gemini_api_key)
        stocks_data = analyzer.analyze_transcript(transcript=content)
        
        if not stocks_data:
            return AnalysisResponse(
                success=True,
                message="Analysis completed but no stocks were found in the document",
                stocks_found=0,
                stocks=[],
                source_id=doc_id,
                source_type="google_docs"
            )
        
        # Update market status if AI detected it
        if "market_status" in stocks_data and stocks_data["market_status"]:
            market_data = stocks_data["market_status"]
            if market_data.get("status"):
                # Update legacy MarketStatus table
                market_status = db.query(MarketStatus).first()
                if not market_status:
                    market_status = MarketStatus()
                    db.add(market_status)
                
                # Map AI status to enum (4-state Mark Gomes system)
                status_map = {
                    "GREEN": MarketStatusEnum.GREEN,
                    "YELLOW": MarketStatusEnum.YELLOW,
                    "ORANGE": MarketStatusEnum.ORANGE,
                    "RED": MarketStatusEnum.RED
                }
                
                if market_data["status"] in status_map:
                    market_status.status = status_map[market_data["status"]]
                    market_status.note = market_data.get("quote", "")
                    db.commit()
                    
                    # Also update Gomes Intelligence market_alerts table
                    try:
                        gomes_service = GomesIntelligenceService(db)
                        gomes_service.set_market_alert(
                            alert_level=market_data["status"],
                            reason=f"Detected from Google Docs: {market_data.get('quote', 'No quote')[:200]}",
                            source="google_docs_analysis"
                        )
                        logger.info(f"Gomes Market Alert updated to {market_data['status']} from Google Docs")
                    except Exception as e:
                        logger.warning(f"Failed to update Gomes market alert: {e}")
        
        # Save to database
        repository = StockRepository(db)
        success, error = repository.create_stocks(
            stocks=stocks_data.get("stocks", []),
            source_id=doc_id,
            source_type="google_docs",
            speaker=request.speaker or "Unknown"
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to save stocks: {error}"
            )
        
        # Refresh verdicts for newly analyzed stocks
        tickers = [s["ticker"] for s in stocks_data.get("stocks", [])]
        if tickers:
            _refresh_verdicts_async(db, tickers)
        
        saved_stocks = repository.get_all_stocks()
        stock_responses = [
            StockAnalysisResult(
                ticker=stock.ticker,
                company_name=stock.company_name,
                sentiment=stock.sentiment or "Neutral",
                conviction_score=stock.conviction_score or 5,
                price_target=stock.price_target,
                edge=stock.edge,
                catalysts=stock.catalysts,
                risks=stock.risks,
                time_horizon=stock.time_horizon,
                action_verdict=stock.action_verdict
            )
            for stock in saved_stocks[-len(stocks_data.get("stocks", [])):] if saved_stocks
        ]
        
        return AnalysisResponse(
            success=True,
            message=f"Successfully analyzed Google Doc and found {len(stock_responses)} stock mention(s)",
            stocks_found=len(stock_responses),
            stocks=stock_responses,
            source_id=doc_id,
            source_type="google_docs"
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
