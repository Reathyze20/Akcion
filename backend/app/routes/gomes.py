"""
Gomes Analysis API Endpoints
==============================

API endpoints pro Gomes Investment Committee analýzu.
Umožňují frontend přístup ke skórovacímu systému Marka Gomese.

Author: GitHub Copilot with Claude Sonnet 4.5
Date: 2026-01-17
"""

from typing import List, Optional
from datetime import datetime, date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from pydantic import BaseModel, Field

from app.database.connection import get_db
from app.trading.gomes_analyzer import (
    create_gomes_analyzer,
    GomesAnalyzer,
    GomesScore,
    GomesRating
)
from app.models.trading import ActiveWatchlist
from app.models.stock import Stock
from app.models.analysis import AnalystTranscript, TickerMention
from app.config.settings import Settings


# ============================================================================
# ROUTER SETUP
# ============================================================================

router = APIRouter(
    prefix="/api/gomes",
    tags=["Gomes Analysis"]
)

settings = Settings()


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class MarketDataInput(BaseModel):
    """Optional market data input"""
    insider_buying: Optional[bool] = None
    earnings_date: Optional[datetime] = None


class GomesAnalyzeRequest(BaseModel):
    """Request body pro ticker analýzu"""
    ticker: str = Field(..., description="Stock ticker (e.g., AAPL)")
    transcript_text: Optional[str] = Field(None, description="Custom transcript text")
    market_data: Optional[MarketDataInput] = None
    force_refresh: bool = Field(False, description="Force new ML prediction")


class GomesScoreResponse(BaseModel):
    """Response s Gomes skóre"""
    ticker: str
    total_score: int
    rating: str
    
    # Score components
    story_score: int
    breakout_score: int
    insider_score: int
    ml_score: int
    volume_score: int
    earnings_penalty: int
    
    # Metadata
    analysis_timestamp: datetime
    confidence: str
    reasoning: str
    risk_factors: List[str]
    
    # Data sources
    has_transcript: bool
    has_swot: bool
    has_ml_prediction: bool
    earnings_date: Optional[datetime]
    
    class Config:
        from_attributes = True


class WatchlistRanking(BaseModel):
    """Ranked watchlist item"""
    ticker: str
    score: int
    rating: str
    confidence: str
    reasoning: str
    last_analyzed: datetime


class WatchlistRankingResponse(BaseModel):
    """Response s ranked watchlist"""
    total_tickers: int
    analyzed_tickers: int
    rankings: List[WatchlistRanking]
    timestamp: datetime


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _gomes_score_to_response(score: GomesScore) -> GomesScoreResponse:
    """Convert GomesScore dataclass to Pydantic response"""
    return GomesScoreResponse(
        ticker=score.ticker,
        total_score=score.total_score,
        rating=score.rating.value,
        story_score=score.story_score,
        breakout_score=score.breakout_score,
        insider_score=score.insider_score,
        ml_score=score.ml_score,
        volume_score=score.volume_score,
        earnings_penalty=score.earnings_penalty,
        analysis_timestamp=score.analysis_timestamp,
        confidence=score.confidence,
        reasoning=score.reasoning,
        risk_factors=score.risk_factors,
        has_transcript=score.has_transcript,
        has_swot=score.has_swot,
        has_ml_prediction=score.has_ml_prediction,
        earnings_date=score.earnings_date
    )


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post("/analyze", response_model=GomesScoreResponse)
def analyze_ticker_gomes(
    request: GomesAnalyzeRequest,
    db: Session = Depends(get_db)
):
    """
    Analyzovat ticker podle Mark Gomes pravidel.
    
    Vrací strukturované skóre 0-10 s detailním breakdown.
    
    **Score Components:**
    - Story (Catalyst): 0-2 body
    - Breakout Pattern: 0-2 body
    - Insider Buying: 0-2 body
    - ML Prediction: 0-2 body
    - Volume Trend: 0-1 bod
    - Earnings Penalty: -5 bodů (pokud < 14 dní)
    
    **Ratings:**
    - STRONG_BUY: 9-10 bodů
    - BUY: 7-8 bodů
    - HOLD: 5-6 bodů
    - AVOID: 0-4 bodů
    - HIGH_RISK: Earnings < 14 dní
    """
    try:
        # Create analyzer
        analyzer = create_gomes_analyzer(
            db_session=db,
            llm_api_key=getattr(settings, "openai_api_key", None),
            llm_provider="openai"
        )
        
        # Convert market data
        market_data_dict = None
        if request.market_data:
            market_data_dict = {
                "insider_buying": request.market_data.insider_buying,
                "earnings_date": request.market_data.earnings_date
            }
        
        # Analyze
        score = analyzer.analyze_ticker(
            ticker=request.ticker.upper(),
            transcript_text=request.transcript_text,
            market_data=market_data_dict,
            force_refresh=request.force_refresh
        )
        
        return _gomes_score_to_response(score)
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Gomes analysis failed: {str(e)}"
        )


@router.get("/analyze/{ticker}", response_model=GomesScoreResponse)
def analyze_ticker_simple(
    ticker: str,
    force_refresh: bool = Query(False, description="Force new ML prediction"),
    db: Session = Depends(get_db)
):
    """
    Analyzovat ticker (simplified GET endpoint).
    
    Použije data z databáze (transcripts, SWOT, ML predictions).
    """
    try:
        analyzer = create_gomes_analyzer(
            db_session=db,
            llm_api_key=getattr(settings, "openai_api_key", None),
            llm_provider="openai"
        )
        
        score = analyzer.analyze_ticker(
            ticker=ticker.upper(),
            force_refresh=force_refresh
        )
        
        return _gomes_score_to_response(score)
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Gomes analysis failed: {str(e)}"
        )


@router.post("/scan-watchlist", response_model=WatchlistRankingResponse)
def scan_watchlist_gomes(
    min_score: int = Query(5, ge=0, le=10, description="Minimum Gomes score"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    force_refresh: bool = Query(False, description="Force new predictions"),
    db: Session = Depends(get_db)
):
    """
    Scanovat celý watchlist a rank podle Gomes skóre.
    
    Analyzuje všechny akcie z tabulky stocks a vrací je
    seřazené podle gomes_score (highest first).
    
    **Use case**: Daily scan pro identifikaci top setups.
    """
    try:
        # Fetch all stocks from database with is_latest=True
        stocks_list = (
            db.query(Stock)
            .filter(Stock.is_latest == True)
            .filter(Stock.gomes_score >= min_score)
            .order_by(desc(Stock.gomes_score))
            .limit(limit)
            .all()
        )
        
        if not stocks_list:
            return WatchlistRankingResponse(
                total_tickers=0,
                analyzed_tickers=0,
                rankings=[],
                timestamp=datetime.now()
            )
        
        # Convert stocks to rankings
        rankings = []
        
        for stock in stocks_list:
            # Determine rating based on action_verdict and gomes_score
            rating = "HOLD"
            if stock.action_verdict == "BUY_NOW":
                rating = "STRONG_BUY"
            elif stock.action_verdict == "ACCUMULATE":
                rating = "BUY"
            elif stock.action_verdict in ["WATCH_LIST"]:
                rating = "HOLD"
            elif stock.action_verdict in ["TRIM", "SELL", "AVOID"]:
                rating = "AVOID"
            
            rankings.append(WatchlistRanking(
                ticker=stock.ticker,
                score=stock.gomes_score or 0,
                rating=rating,
                confidence="HIGH" if (stock.gomes_score or 0) >= 8 else "MEDIUM" if (stock.gomes_score or 0) >= 6 else "LOW",
                reasoning=stock.trade_rationale or stock.edge or "From transcript analysis",
                last_analyzed=stock.created_at
            ))
        
        return WatchlistRankingResponse(
            total_tickers=db.query(Stock).filter(Stock.is_latest == True).count(),
            analyzed_tickers=len(rankings),
            rankings=rankings,
            timestamp=datetime.now()
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Watchlist scan failed: {str(e)}"
        )


@router.get("/top-picks", response_model=WatchlistRankingResponse)
def get_top_gomes_picks(
    min_rating: str = Query(
        "BUY",
        description="Minimum rating (STRONG_BUY, BUY, HOLD)"
    ),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """
    Získat top picks podle Gomes kritérií.
    
    Vrací pouze tickery s rating >= min_rating, seřazené podle skóre.
    
    **Use case**: Dashboard "Top Picks of the Day".
    """
    try:
        # Scan watchlist
        scan_result = scan_watchlist_gomes(
            min_score=7 if min_rating == "BUY" else 9,  # BUY=7, STRONG_BUY=9
            limit=limit,
            force_refresh=False,
            db=db
        )
        
        # Filter by rating
        valid_ratings = []
        if min_rating == "STRONG_BUY":
            valid_ratings = ["STRONG_BUY"]
        elif min_rating == "BUY":
            valid_ratings = ["STRONG_BUY", "BUY"]
        elif min_rating == "HOLD":
            valid_ratings = ["STRONG_BUY", "BUY", "HOLD"]
        
        filtered_rankings = [
            r for r in scan_result.rankings
            if r.rating in valid_ratings
        ]
        
        return WatchlistRankingResponse(
            total_tickers=scan_result.total_tickers,
            analyzed_tickers=len(filtered_rankings),
            rankings=filtered_rankings,
            timestamp=datetime.now()
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get top picks: {str(e)}"
        )


@router.get("/stats")
def get_gomes_stats(db: Session = Depends(get_db)):
    """
    Statistiky Gomes analýz.
    
    Vrací přehled rating distribution, průměrné skóre, atd.
    """
    try:
        # This would require storing Gomes scores in database
        # For now, return placeholder
        
        return {
            "total_analyzed": 0,
            "rating_distribution": {
                "STRONG_BUY": 0,
                "BUY": 0,
                "HOLD": 0,
                "AVOID": 0,
                "HIGH_RISK": 0
            },
            "average_score": 0.0,
            "last_updated": datetime.now()
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get stats: {str(e)}"
        )


# ============================================================================
# BATCH OPERATIONS
# ============================================================================

class BatchAnalyzeRequest(BaseModel):
    """Request pro batch analýzu"""
    tickers: List[str] = Field(..., description="List of tickers to analyze")
    force_refresh: bool = Field(False, description="Force new predictions")


class BatchAnalyzeResponse(BaseModel):
    """Response z batch analýzy"""
    total_requested: int
    successful: int
    failed: int
    results: List[GomesScoreResponse]
    errors: List[dict]


@router.post("/analyze/batch", response_model=BatchAnalyzeResponse)
def analyze_batch_gomes(
    request: BatchAnalyzeRequest,
    db: Session = Depends(get_db)
):
    """
    Batch analýza více tickerů najednou.
    
    **Use case**: Analyze multiple tickers from user selection.
    """
    try:
        analyzer = create_gomes_analyzer(
            db_session=db,
            llm_api_key=getattr(settings, "openai_api_key", None),
            llm_provider="openai"
        )
        
        results = []
        errors = []
        
        for ticker in request.tickers:
            try:
                score = analyzer.analyze_ticker(
                    ticker=ticker.upper(),
                    force_refresh=request.force_refresh
                )
                results.append(_gomes_score_to_response(score))
                
            except Exception as e:
                errors.append({
                    "ticker": ticker,
                    "error": str(e)
                })
        
        return BatchAnalyzeResponse(
            total_requested=len(request.tickers),
            successful=len(results),
            failed=len(errors),
            results=results,
            errors=errors
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Batch analysis failed: {str(e)}"
        )


# ============================================================================
# TRANSCRIPT IMPORT & TIMELINE
# ============================================================================

class TranscriptImportRequest(BaseModel):
    """Request pro import transcriptu"""
    source_name: str = Field("Mark Gomes", description="Zdroj (např. 'Mark Gomes', 'Breakout Investors')")
    video_date: date = Field(..., description="Datum videa/transcriptu (YYYY-MM-DD)")
    raw_text: str = Field(..., min_length=100, description="Celý text transcriptu")
    video_url: Optional[str] = Field(None, description="URL videa")
    transcript_quality: Optional[str] = Field("medium", description="Kvalita: high, medium, low")


class TranscriptImportResponse(BaseModel):
    """Response z importu transcriptu"""
    transcript_id: int
    source_name: str
    video_date: date
    detected_tickers: List[str]
    ticker_mentions_created: int
    message: str


class TickerMentionResponse(BaseModel):
    """Jednotlivá zmínka tickeru"""
    id: int
    ticker: str
    mention_date: date
    sentiment: str
    action_mentioned: Optional[str]
    context_snippet: Optional[str]
    key_points: Optional[List[str]]
    price_target: Optional[float]
    conviction_level: Optional[str]
    source_name: str
    video_url: Optional[str]
    weight: float
    age_days: int


class TickerTimelineResponse(BaseModel):
    """Timeline zmínek pro ticker"""
    ticker: str
    total_mentions: int
    latest_sentiment: Optional[str]
    latest_action: Optional[str]
    weighted_sentiment_score: float  # -1 to +1
    mentions: List[TickerMentionResponse]


@router.post("/transcripts/import", response_model=TranscriptImportResponse)
def import_transcript(
    request: TranscriptImportRequest,
    db: Session = Depends(get_db)
):
    """
    Import transcriptu s možností zadat historické datum.
    
    Automaticky:
    - Detekuje tickery v textu
    - Vytvoří zmínky pro každý ticker
    - Extrahuje sentiment a akce pomocí AI (pokud dostupné)
    
    **Use case**: Import starších videí pro budování historické databáze.
    """
    try:
        from app.core.extractors import extract_tickers_from_text
        
        # Detect tickers in transcript
        detected_tickers = extract_tickers_from_text(request.raw_text)
        
        # Create transcript record
        transcript = AnalystTranscript(
            source_name=request.source_name,
            raw_text=request.raw_text,
            detected_tickers=detected_tickers,
            date=request.video_date,
            video_url=request.video_url,
            transcript_quality=request.transcript_quality,
            is_processed=False
        )
        db.add(transcript)
        db.flush()  # Get ID
        
        # Create basic ticker mentions (can be enhanced by AI later)
        mentions_created = 0
        for ticker in detected_tickers:
            # Find stock if exists
            stock = db.query(Stock).filter(
                Stock.ticker == ticker,
                Stock.is_latest == True
            ).first()
            
            mention = TickerMention(
                ticker=ticker,
                transcript_id=transcript.id,
                stock_id=stock.id if stock else None,
                mention_date=request.video_date,
                sentiment='NEUTRAL',  # Will be updated by AI processing
                ai_extracted=False,
                is_current=True
            )
            db.add(mention)
            mentions_created += 1
        
        # Mark older mentions as not current
        for ticker in detected_tickers:
            db.query(TickerMention).filter(
                TickerMention.ticker == ticker,
                TickerMention.transcript_id != transcript.id,
                TickerMention.is_current == True
            ).update({"is_current": False})
        
        db.commit()
        
        return TranscriptImportResponse(
            transcript_id=transcript.id,
            source_name=request.source_name,
            video_date=request.video_date,
            detected_tickers=detected_tickers,
            ticker_mentions_created=mentions_created,
            message=f"Transcript imported successfully. Found {len(detected_tickers)} tickers."
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Transcript import failed: {str(e)}"
        )


@router.get("/ticker/{ticker}/timeline", response_model=TickerTimelineResponse)
def get_ticker_timeline(
    ticker: str,
    limit: int = Query(20, ge=1, le=100, description="Max mentions to return"),
    db: Session = Depends(get_db)
):
    """
    Získat historickou timeline zmínek pro ticker.
    
    Vrací všechny zmínky seřazené od nejnovější, včetně:
    - Sentiment a doporučená akce
    - Kontext ze transcriptu
    - Váha zmínky (novější = vyšší)
    - Agregovaný weighted sentiment score
    
    **Use case**: Zobrazit historii co Mark Gomes říkal o akcii.
    """
    try:
        import math
        
        ticker = ticker.upper()
        
        # Fetch all mentions for ticker
        mentions = (
            db.query(TickerMention, AnalystTranscript)
            .join(AnalystTranscript)
            .filter(TickerMention.ticker == ticker)
            .order_by(desc(TickerMention.mention_date))
            .limit(limit)
            .all()
        )
        
        if not mentions:
            return TickerTimelineResponse(
                ticker=ticker,
                total_mentions=0,
                latest_sentiment=None,
                latest_action=None,
                weighted_sentiment_score=0.0,
                mentions=[]
            )
        
        # Build response
        mention_responses = []
        total_weight = 0.0
        weighted_sentiment = 0.0
        
        sentiment_scores = {
            'VERY_BULLISH': 1.0,
            'BULLISH': 0.5,
            'NEUTRAL': 0.0,
            'BEARISH': -0.5,
            'VERY_BEARISH': -1.0
        }
        
        for mention, transcript in mentions:
            # Calculate weight (exponential decay, 30-day half-life)
            age_days = (date.today() - mention.mention_date).days
            weight = math.exp(-0.023 * age_days)
            
            mention_responses.append(TickerMentionResponse(
                id=mention.id,
                ticker=mention.ticker,
                mention_date=mention.mention_date,
                sentiment=mention.sentiment,
                action_mentioned=mention.action_mentioned,
                context_snippet=mention.context_snippet,
                key_points=mention.key_points if mention.key_points else None,
                price_target=float(mention.price_target) if mention.price_target else None,
                conviction_level=mention.conviction_level,
                source_name=transcript.source_name,
                video_url=transcript.video_url,
                weight=round(weight, 3),
                age_days=age_days
            ))
            
            # Accumulate weighted sentiment
            sentiment_value = sentiment_scores.get(mention.sentiment, 0.0)
            weighted_sentiment += sentiment_value * weight
            total_weight += weight
        
        # Calculate final weighted sentiment
        final_sentiment = weighted_sentiment / total_weight if total_weight > 0 else 0.0
        
        # Get latest values
        latest_mention = mentions[0][0]
        
        return TickerTimelineResponse(
            ticker=ticker,
            total_mentions=len(mention_responses),
            latest_sentiment=latest_mention.sentiment,
            latest_action=latest_mention.action_mentioned,
            weighted_sentiment_score=round(final_sentiment, 3),
            mentions=mention_responses
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get ticker timeline: {str(e)}"
        )


@router.get("/transcripts", response_model=List[dict])
def list_transcripts(
    source: Optional[str] = Query(None, description="Filter by source name"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Seznam všech importovaných transcriptů.
    """
    try:
        query = db.query(AnalystTranscript).order_by(desc(AnalystTranscript.date))
        
        if source:
            query = query.filter(AnalystTranscript.source_name == source)
        
        transcripts = query.limit(limit).all()
        
        return [
            {
                "id": t.id,
                "source_name": t.source_name,
                "date": t.date.isoformat(),
                "video_url": t.video_url,
                "detected_tickers": t.detected_tickers,
                "ticker_count": len(t.detected_tickers) if t.detected_tickers else 0,
                "is_processed": t.is_processed,
                "quality": t.transcript_quality,
                "created_at": t.created_at.isoformat() if t.created_at else None
            }
            for t in transcripts
        ]
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list transcripts: {str(e)}"
        )


@router.post("/transcripts/{transcript_id}/process")
def process_transcript_ai(
    transcript_id: int,
    db: Session = Depends(get_db)
):
    """
    Zpracovat transcript pomocí AI.
    
    Aktualizuje všechny ticker mentions s:
    - Extrahovaným sentimentem
    - Doporučenou akcí
    - Klíčovými body
    - Kontextovým snippetem
    
    **Use case**: Přidat AI analýzu k manuálně importovanému transcriptu.
    """
    try:
        transcript = db.query(AnalystTranscript).filter(
            AnalystTranscript.id == transcript_id
        ).first()
        
        if not transcript:
            raise HTTPException(status_code=404, detail="Transcript not found")
        
        # Get mentions for this transcript
        mentions = db.query(TickerMention).filter(
            TickerMention.transcript_id == transcript_id
        ).all()
        
        if not mentions:
            return {"message": "No ticker mentions to process", "processed": 0}
        
        # TODO: Implement AI processing
        # For now, return placeholder
        # This would call the LLM to extract sentiment, actions, key points
        
        return {
            "message": "AI processing not yet implemented. Mentions created with NEUTRAL sentiment.",
            "transcript_id": transcript_id,
            "mentions_count": len(mentions),
            "tickers": [m.ticker for m in mentions]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process transcript: {str(e)}"
        )

