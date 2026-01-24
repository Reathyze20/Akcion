"""
FastAPI Application - Akcion Investment Analysis API

MISSION: Expose core business logic through REST API endpoints.
CRITICAL: Preserve all Gomes methodology and fiduciary AI behavior.
"""

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional

from .config import get_settings
from .database import initialize_database, get_db, is_connected
from .database.repositories import StockRepository
from .core import (
    StockAnalyzer,
    extract_video_id,
    get_youtube_transcript,
    extract_google_doc_id,
    get_google_doc_content
)
from .schemas import (
    AnalyzeTextRequest,
    AnalyzeYouTubeRequest,
    AnalyzeGoogleDocsRequest,
    AnalysisResponse,
    StockResponse,
    StocksListResponse,
    HealthCheckResponse,
    ErrorResponse,
    StockAnalysisResult
)

# Import new routes
from .routes import portfolio, gap_analysis, trading, intelligence, gomes, analysis, stocks
from .routes import intelligence_gomes, master_signal, notifications
from .routes import investment  # Investment Intelligence
from .routes import currency  # Currency exchange rates

# Import alert scheduler
from .services.alert_scheduler import start_scheduler, stop_scheduler

# ==============================================================================
# Application Setup
# ==============================================================================

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="""
    Akcion Investment Analysis API
    
    Analyzes investment content using Mark Gomes methodology with AI-powered stock extraction.
    
    **Critical Mission**: Family financial security depends on accurate analysis.
    """,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

# ==============================================================================
# CORS Configuration
# ==============================================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================================================================
# Startup/Shutdown Events
# ==============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize database connection and background services on startup"""
    # Database initialization
    success, error = initialize_database(settings.database_url)
    if not success:
        print(f"WARNING: Database initialization failed: {error}")
    else:
        print("SUCCESS: Database connected successfully")
    
    # Start alert scheduler (background monitoring)
    try:
        await start_scheduler()
        print("SUCCESS: Alert scheduler started")
    except Exception as e:
        print(f"WARNING: Alert scheduler failed to start: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    try:
        await stop_scheduler()
        print("SUCCESS: Alert scheduler stopped")
    except Exception as e:
        print(f"WARNING: Error stopping scheduler: {e}")


# ==============================================================================
# Register Routers
# ==============================================================================

app.include_router(portfolio.router)
app.include_router(stocks.router)
app.include_router(gap_analysis.router)
app.include_router(analysis.router)
app.include_router(trading.router)
app.include_router(intelligence.router)
app.include_router(gomes.router)
app.include_router(intelligence_gomes.router)
app.include_router(master_signal.router)
app.include_router(master_signal.action_router)
app.include_router(notifications.router)
app.include_router(investment.router)  # Investment Intelligence
app.include_router(currency.router)  # Currency exchange rates


# ==============================================================================
# Health Check Endpoint
# ==============================================================================

@app.get(
    "/api/health",
    response_model=HealthCheckResponse,
    tags=["System"]
)
async def health_check():
    """
    Check API health and database connectivity.
    """
    from datetime import datetime
    return HealthCheckResponse(
        status="healthy",
        message="API is operational",
        timestamp=datetime.utcnow()
    )


# ==============================================================================
# Analysis Endpoints
# ==============================================================================

@app.post(
    "/api/analyze/text",
    response_model=AnalysisResponse,
    status_code=status.HTTP_200_OK,
    tags=["Analysis"],
    summary="Analyze text transcript",
    description="""
    Analyze investment transcript text using Gemini AI with Mark Gomes methodology.
    
    **Applies**:
    - Fiduciary analyst persona (MS client context)
    - Aggressive stock extraction
    - Gomes Rules (Edge, Catalysts, Risks)
    - Google Search for verification
    """
)
async def analyze_text(
    request: AnalyzeTextRequest,
    db: Session = Depends(get_db)
):
    """Analyze plain text transcript"""
    try:
        # Initialize analyzer with settings
        analyzer = StockAnalyzer(settings.gemini_api_key)
        
        # Analyze transcript
        result = analyzer.analyze_transcript(request.transcript)
        
        if not result or "stocks" not in result:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="AI analysis failed to extract stock data"
            )
        
        stocks = result["stocks"]
        
        # Save to database
        repo = StockRepository(db)
        success, error = repo.create_stocks(
            stocks,
            request.source_id,
            request.source_type,
            request.speaker
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database save failed: {error}"
            )
        
        # Convert to response format
        stock_results = [StockAnalysisResult(**stock) for stock in stocks]
        
        return AnalysisResponse(
            success=True,
            message=f"Successfully analyzed and saved {len(stocks)} stock(s)",
            stocks=stock_results,
            stocks_saved=len(stocks),
            source_id=request.source_id,
            source_type=request.source_type
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {str(e)}"
        )


@app.post(
    "/api/analyze/youtube",
    response_model=AnalysisResponse,
    tags=["Analysis"],
    summary="Analyze YouTube video"
)
async def analyze_youtube(
    request: AnalyzeYouTubeRequest,
    db: Session = Depends(get_db)
):
    """Extract and analyze YouTube video transcript"""
    try:
        # Extract video ID
        video_id = extract_video_id(request.video_url)
        if not video_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid YouTube URL"
            )
        
        # Get transcript
        transcript = get_youtube_transcript(video_id)
        if not transcript:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No transcript available for this video. Ensure captions/subtitles are enabled."
            )
        
        # Analyze
        analyzer = StockAnalyzer(settings.gemini_api_key)
        result = analyzer.analyze_transcript(transcript)
        
        if not result or "stocks" not in result:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="AI analysis failed to extract stock data"
            )
        
        stocks = result["stocks"]
        
        # Save to database
        repo = StockRepository(db)
        success, error = repo.create_stocks(
            stocks,
            video_id,
            "YouTube",
            request.speaker
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database save failed: {error}"
            )
        
        stock_results = [StockAnalysisResult(**stock) for stock in stocks]
        
        return AnalysisResponse(
            success=True,
            message=f"Successfully analyzed YouTube video and saved {len(stocks)} stock(s)",
            stocks=stock_results,
            stocks_found=len(stocks),
            source_id=video_id,
            source_type="YouTube"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"YouTube analysis failed: {str(e)}"
        )


@app.post(
    "/api/analyze/google-docs",
    response_model=AnalysisResponse,
    tags=["Analysis"],
    summary="Analyze Google Docs document"
)
async def analyze_google_docs(
    request: AnalyzeGoogleDocsRequest,
    db: Session = Depends(get_db)
):
    """Extract and analyze Google Docs content"""
    try:
        # Extract doc ID
        doc_id = extract_google_doc_id(request.url)
        if not doc_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Google Docs URL"
            )
        
        # Get document content
        try:
            content = get_google_doc_content(request.url)
        except PermissionError as e:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(e)
            )
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
        except TimeoutError as e:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail=str(e)
            )
        
        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document is empty or inaccessible"
            )
        
        # Analyze with API key from settings
        analyzer = StockAnalyzer(settings.gemini_api_key)
        result = analyzer.analyze_transcript(content)
        
        if not result or "stocks" not in result:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="AI analysis failed to extract stock data"
            )
        
        stocks = result["stocks"]
        
        # Save to database
        repo = StockRepository(db)
        success, error = repo.create_stocks(
            stocks,
            doc_id,
            "Google Docs",
            request.speaker
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database save failed: {error}"
            )
        
        stock_results = [StockAnalysisResult(**stock) for stock in stocks]
        
        return AnalysisResponse(
            success=True,
            message=f"Successfully analyzed Google Doc and saved {len(stocks)} stock(s)",
            stocks=stock_results,
            stocks_found=len(stocks),
            source_id=doc_id,
            source_type="Google Docs"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Google Docs analysis failed: {str(e)}"
        )


# ==============================================================================
# Portfolio/Stock Query Endpoints
# ==============================================================================

@app.get(
    "/api/stocks",
    response_model=StocksListResponse,
    tags=["Portfolio"],
    summary="Get all stocks",
    description="Retrieve all analyzed stocks, sorted by Gomes score (highest first)"
)
async def get_all_stocks(
    limit: Optional[int] = None,
    min_score: Optional[int] = None,
    sentiment: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get all stocks from portfolio"""
    try:
        repo = StockRepository(db)
        
        # Get stocks
        stocks = repo.get_all_stocks(order_by_score=True, limit=limit)
        
        # Apply filters
        if min_score is not None:
            stocks = [s for s in stocks if s.gomes_score and s.gomes_score >= min_score]
        
        if sentiment:
            stocks = [s for s in stocks if s.sentiment == sentiment]
        
        # Convert to StockResponse objects using Pydantic validation
        stock_responses = [StockResponse.model_validate(stock) for stock in stocks]
        
        return StocksListResponse(
            stocks=stock_responses,
            total_stocks=len(stock_responses)
        )
        
        return {
            "stocks": stock_responses,
            "count": len(stock_responses)
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve stocks: {str(e)}"
        )


@app.get(
    "/api/stocks/{ticker}",
    response_model=StockResponse,
    tags=["Portfolio"],
    summary="Get stock by ticker",
    description="Get most recent analysis for a specific ticker"
)
async def get_stock_by_ticker(
    ticker: str,
    db: Session = Depends(get_db)
):
    """Get latest analysis for a ticker"""
    try:
        repo = StockRepository(db)
        stock = repo.get_stock_by_ticker(ticker)
        
        if not stock:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No analysis found for ticker: {ticker}"
            )
        
        return StockResponse.model_validate(stock)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve stock: {str(e)}"
        )


@app.get(
    "/api/stocks/{ticker}/history",
    response_model=StocksListResponse,
    tags=["Portfolio"],
    summary="Get ticker history",
    description="Get all historical analyses for a ticker"
)
async def get_ticker_history(
    ticker: str,
    db: Session = Depends(get_db)
):
    """Get all analyses for a ticker over time"""
    try:
        repo = StockRepository(db)
        stocks = repo.get_ticker_history(ticker)
        
        if not stocks:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No history found for ticker: {ticker}"
            )
        
        stock_responses = [StockResponse.model_validate(stock) for stock in stocks]
        
        return StocksListResponse(
            stocks=stock_responses,
            total_stocks=len(stock_responses)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve history: {str(e)}"
        )


# ==============================================================================
# Root Endpoint
# ==============================================================================

@app.get("/", tags=["System"])
async def root():
    """API root - redirect to docs"""
    return {
        "message": "Akcion Investment Analysis API",
        "version": settings.app_version,
        "docs": "/api/docs",
        "health": "/api/health"
    }
