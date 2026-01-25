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
    
    Primárně používá data z tabulky Stock, kde je uložený gomes_score.
    Fallback na real-time analýzu pouze pokud není v DB.
    """
    try:
        ticker_upper = ticker.upper()
        
        # First, try to get data from Stock table (pre-analyzed)
        stock = (
            db.query(Stock)
            .filter(Stock.ticker == ticker_upper)
            .filter(Stock.is_latest == True)
            .first()
        )
        
        if stock and stock.gomes_score is not None:
            # Use stored data from Stock table
            # Determine rating from action_verdict and score
            rating = "HOLD"
            if stock.action_verdict == "BUY_NOW":
                rating = "STRONG_BUY"
            elif stock.action_verdict == "ACCUMULATE":
                rating = "BUY"
            elif stock.action_verdict in ["WATCH_LIST"]:
                rating = "HOLD"
            elif stock.action_verdict in ["TRIM", "SELL", "AVOID"]:
                rating = "AVOID"
            elif stock.gomes_score >= 9:
                rating = "STRONG_BUY"
            elif stock.gomes_score >= 7:
                rating = "BUY"
            elif stock.gomes_score >= 5:
                rating = "HOLD"
            else:
                rating = "AVOID"
            
            confidence = "HIGH" if (stock.gomes_score or 0) >= 8 else "MEDIUM" if (stock.gomes_score or 0) >= 6 else "LOW"
            
            # Build reasoning from available fields
            reasoning = stock.trade_rationale or stock.edge or "From transcript analysis"
            
            # Build risk factors
            risk_factors = []
            if stock.risks:
                risk_factors = [r.strip() for r in stock.risks.split(",") if r.strip()]
            
            return GomesScoreResponse(
                ticker=stock.ticker,
                total_score=stock.gomes_score or 0,
                rating=rating,
                story_score=2 if stock.edge else 0,  # Has story/edge
                breakout_score=0,  # Would need OHLCV check
                insider_score=0,   # Would need external data
                ml_score=0,        # Needs ML prediction check
                volume_score=0,    # Would need OHLCV check
                earnings_penalty=0,
                analysis_timestamp=stock.created_at or datetime.now(),
                confidence=confidence,
                reasoning=reasoning,
                risk_factors=risk_factors,
                has_transcript=bool(stock.edge or stock.trade_rationale),
                has_swot=False,
                has_ml_prediction=False,
                earnings_date=None
            )
        
        # Fallback: run real-time analysis if not in Stock table
        analyzer = create_gomes_analyzer(
            db_session=db,
            llm_api_key=getattr(settings, "openai_api_key", None),
            llm_provider="openai"
        )
        
        score = analyzer.analyze_ticker(
            ticker=ticker_upper,
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
# PRICE LINES HISTORY
# ============================================================================

class PriceLinesHistoryItem(BaseModel):
    """Historický záznam price lines"""
    id: int
    ticker: str
    green_line: Optional[float]
    red_line: Optional[float]
    effective_from: date
    valid_until: Optional[date]
    source: Optional[str]
    source_reference: Optional[str]


class PriceLinesHistoryResponse(BaseModel):
    """Response s historií price lines"""
    ticker: str
    total_records: int
    current_green_line: Optional[float]
    current_red_line: Optional[float]
    history: List[PriceLinesHistoryItem]


@router.get("/ticker/{ticker}/price-lines-history", response_model=PriceLinesHistoryResponse)
def get_price_lines_history(
    ticker: str,
    db: Session = Depends(get_db)
):
    """
    Získat historii price lines pro ticker.
    
    Vrací všechny historické záznamy green/red lines, seřazené od nejnovějšího.
    Ukazuje, jak se cenové zóny měnily v čase.
    
    **Use case**: Sledovat vývoj Mark Gomes hodnocení akcie.
    """
    from app.models.gomes import PriceLinesModel
    
    try:
        ticker = ticker.upper()
        
        # Get all price lines for ticker (including historical)
        lines = (
            db.query(PriceLinesModel)
            .filter(PriceLinesModel.ticker == ticker)
            .order_by(desc(PriceLinesModel.effective_from))
            .all()
        )
        
        if not lines:
            return PriceLinesHistoryResponse(
                ticker=ticker,
                total_records=0,
                current_green_line=None,
                current_red_line=None,
                history=[]
            )
        
        # Get current (active) lines
        current = next((l for l in lines if l.valid_until is None), None)
        
        history = [
            PriceLinesHistoryItem(
                id=l.id,
                ticker=l.ticker,
                green_line=float(l.green_line) if l.green_line else None,
                red_line=float(l.red_line) if l.red_line else None,
                effective_from=l.effective_from.date() if hasattr(l.effective_from, 'date') else l.effective_from,
                valid_until=l.valid_until.date() if l.valid_until and hasattr(l.valid_until, 'date') else l.valid_until,
                source=l.source,
                source_reference=l.source_reference
            )
            for l in lines
        ]
        
        return PriceLinesHistoryResponse(
            ticker=ticker,
            total_records=len(lines),
            current_green_line=float(current.green_line) if current and current.green_line else None,
            current_red_line=float(current.red_line) if current and current.red_line else None,
            history=history
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get price lines history: {str(e)}"
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
    - Green/Red price lines (pokud zmíněny)
    
    **Use case**: Přidat AI analýzu k manuálně importovanému transcriptu.
    """
    import json
    import google.generativeai as genai
    from decimal import Decimal
    from app.core.prompts import TICKER_EXTRACTION_PROMPT, GEMINI_MODEL_NAME
    from app.models.gomes import PriceLinesModel
    from app.config.settings import settings
    
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
        
        tickers = [m.ticker for m in mentions]
        
        # Configure Gemini
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL_NAME)
        
        # Build prompt
        prompt = TICKER_EXTRACTION_PROMPT.format(
            tickers=", ".join(tickers),
            transcript=transcript.raw_text[:50000]  # Limit transcript length
        )
        
        # Call AI
        response = model.generate_content(prompt)
        response_text = response.text
        
        # Clean response (remove markdown code blocks)
        if response_text.startswith("```"):
            response_text = response_text.strip("```json\n").strip("```")
        
        # Parse JSON
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            return {
                "message": "AI response was not valid JSON",
                "raw_response": response_text[:500],
                "processed": 0
            }
        
        # Update mentions and create price lines
        processed_count = 0
        price_lines_created = 0
        
        for ticker_data in data.get("tickers", []):
            ticker = ticker_data.get("ticker", "").upper()
            
            # Find mention for this ticker
            mention = next((m for m in mentions if m.ticker == ticker), None)
            if not mention:
                continue
            
            # Update mention
            if ticker_data.get("sentiment"):
                mention.sentiment = ticker_data["sentiment"]
            if ticker_data.get("action_mentioned"):
                mention.action_mentioned = ticker_data["action_mentioned"]
            if ticker_data.get("conviction_level"):
                mention.conviction_level = ticker_data["conviction_level"]
            if ticker_data.get("price_target"):
                mention.price_target = Decimal(str(ticker_data["price_target"]))
            if ticker_data.get("context_snippet"):
                mention.context_snippet = ticker_data["context_snippet"]
            if ticker_data.get("key_points"):
                mention.key_points = ticker_data["key_points"]
            
            mention.ai_extracted = True
            processed_count += 1
            
            # Create price lines if mentioned
            green_line = ticker_data.get("green_line")
            red_line = ticker_data.get("red_line")
            
            if green_line or red_line:
                # Deactivate previous price lines for this ticker
                db.query(PriceLinesModel).filter(
                    PriceLinesModel.ticker == ticker,
                    PriceLinesModel.valid_until.is_(None)
                ).update({"valid_until": transcript.date})
                
                # Create new price lines with transcript date
                new_lines = PriceLinesModel(
                    ticker=ticker,
                    stock_id=mention.stock_id,
                    green_line=Decimal(str(green_line)) if green_line else None,
                    red_line=Decimal(str(red_line)) if red_line else None,
                    source="transcript_ai",
                    source_reference=f"Transcript #{transcript_id}: {transcript.source_name}",
                    transcript_id=transcript_id,
                    effective_from=transcript.date
                )
                db.add(new_lines)
                price_lines_created += 1
        
        # Mark transcript as processed
        transcript.is_processed = True
        transcript.processing_notes = f"AI processed: {processed_count} tickers, {price_lines_created} price lines"
        
        db.commit()
        
        return {
            "message": f"Successfully processed transcript with AI",
            "transcript_id": transcript_id,
            "mentions_processed": processed_count,
            "price_lines_created": price_lines_created,
            "tickers": tickers
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process transcript: {str(e)}"
        )


# ============================================================================
# DEEP DUE DILIGENCE ENDPOINTS (v2.0 - The Treasure Hunter)
# ============================================================================

@router.post("/deep-dd")
async def run_deep_due_diligence(
    transcript: str = Query(..., min_length=100, description="Raw transcript text"),
    ticker: Optional[str] = Query(None, description="Force specific ticker"),
    include_existing: bool = Query(True, description="Include existing data for drift comparison"),
    save_to_db: bool = Query(True, description="Save results to database"),
    db: Session = Depends(get_db),
):
    """
    Run Gomes Deep Due Diligence Analysis.
    
    This is the "Treasure Hunter" endpoint - it analyzes transcripts using
    Mark Gomes' 6-pillar methodology and returns:
    
    1. **Human-readable analysis** (Czech) - for you to read
    2. **Structured JSON data** - for the app to update cards
    
    The 6 Gomes Pillars:
    - ZÁKLADNÍ FILTR: Size & liquidity (under Wall Street radar?)
    - BOD ZVRATU: Inflection point (contract, profitability, mandate)
    - SKIN IN THE GAME: Management ownership, insider buying
    - FINANČNÍ ODOLNOST: Cash runway (12-18 months), debt, dilution risk
    - ASYMETRICKÝ RISK/ZISK: 2x-10x upside vs defined downside
    - THESIS DRIFT: Is the story improving or is management failing?
    
    Example:
        POST /api/gomes/deep-dd?transcript=Mark%20says%20GKPRF%20is...
        
    Returns:
        {
            "analysis_text": "ZÁKLADNÍ FILTR: Gatekeeper...",
            "data": {
                "ticker": "GKPRF",
                "gomes_score": 8,
                "thesis_status": "IMPROVED",
                "action_signal": "ACCUMULATE",
                "kelly_criterion_hint": 10,
                ...
            },
            "thesis_drift": "IMPROVED",
            "score_change": 2
        }
    """
    from app.services.gomes_deep_dd import GomesDeepDueDiligenceService
    from app.schemas.gomes import DeepDueDiligenceRequest
    
    try:
        service = GomesDeepDueDiligenceService(db)
        
        request = DeepDueDiligenceRequest(
            transcript=transcript,
            ticker=ticker,
            include_existing_data=include_existing,
        )
        
        result = await service.analyze(request)
        
        # Optionally save to database
        if save_to_db:
            stock = await service.update_stock_from_analysis(result)
            
            # Also update price lines if provided
            if result.data.green_line or result.data.red_line:
                from app.models.gomes import PriceLinesModel
                from decimal import Decimal
                
                # Deactivate old lines
                db.query(PriceLinesModel).filter(
                    PriceLinesModel.ticker == result.data.ticker.upper(),
                    PriceLinesModel.valid_until.is_(None)
                ).update({"valid_until": datetime.utcnow()})
                
                # Create new lines
                new_lines = PriceLinesModel(
                    ticker=result.data.ticker.upper(),
                    stock_id=stock.id,
                    green_line=Decimal(str(result.data.green_line)) if result.data.green_line else None,
                    red_line=Decimal(str(result.data.red_line)) if result.data.red_line else None,
                    source="deep_dd_ai",
                    source_reference=f"Deep DD {datetime.utcnow().strftime('%Y-%m-%d')}",
                    effective_from=datetime.utcnow()
                )
                db.add(new_lines)
                db.commit()
        
        return {
            "analysis_text": result.analysis_text,
            "data": result.data.model_dump(),
            "thesis_drift": result.thesis_drift,
            "score_change": result.score_change,
            "analyzed_at": result.analyzed_at.isoformat(),
            "source_length": result.source_length,
            "saved_to_db": save_to_db,
        }
        
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.post("/deep-dd/batch")
async def run_deep_due_diligence_batch(
    transcripts: List[str] = Query(..., description="List of transcripts to analyze"),
    save_to_db: bool = Query(True),
    db: Session = Depends(get_db),
):
    """
    Run Deep Due Diligence on multiple transcripts.
    
    Useful for processing multiple webinar transcripts at once.
    """
    from app.services.gomes_deep_dd import GomesDeepDueDiligenceService
    from app.schemas.gomes import DeepDueDiligenceRequest
    
    service = GomesDeepDueDiligenceService(db)
    results = []
    
    for transcript in transcripts[:10]:  # Limit to 10
        try:
            request = DeepDueDiligenceRequest(
                transcript=transcript,
                include_existing_data=True,
            )
            result = await service.analyze(request)
            
            if save_to_db:
                await service.update_stock_from_analysis(result)
            
            results.append({
                "ticker": result.data.ticker,
                "gomes_score": result.data.gomes_score,
                "action_signal": result.data.action_signal,
                "thesis_status": result.data.thesis_status,
                "success": True,
            })
        except Exception as e:
            results.append({
                "ticker": "UNKNOWN",
                "error": str(e),
                "success": False,
            })
    
    return {
        "processed": len(results),
        "successful": sum(1 for r in results if r.get("success")),
        "results": results,
    }


@router.post("/update-stock/{ticker}")
async def update_stock_analysis(
    ticker: str,
    transcript: str = Query(..., min_length=50, description="New information text (earnings, news, chat)"),
    source_type: str = Query("manual", description="Source: earnings, news, chat, transcript, manual"),
    db: Session = Depends(get_db),
):
    """
    Update existing stock with new information.
    
    Use this to add:
    - Earnings report summaries
    - News updates
    - Chat/discussion notes
    - New video transcripts
    
    The AI will:
    1. Load existing stock data
    2. Analyze new information in context
    3. Update Gomes score if warranted
    4. Track changes in score_history
    5. Create drift alerts if significant change
    
    Example:
        POST /api/gomes/update-stock/GKPRF?transcript=Q4%20earnings%20beat...&source_type=earnings
    """
    from app.services.gomes_deep_dd import GomesDeepDueDiligenceService
    from app.schemas.gomes import DeepDueDiligenceRequest
    
    try:
        service = GomesDeepDueDiligenceService(db)
        
        # Always include existing data for context
        request = DeepDueDiligenceRequest(
            transcript=transcript,
            ticker=ticker.upper(),
            include_existing_data=True,
        )
        
        result = await service.analyze(request)
        
        # Update stock with source tracking
        stock = await service.update_stock_from_analysis(result, analysis_source=source_type)
        
        # Update price lines if provided
        if result.data.green_line or result.data.red_line:
            from app.models.gomes import PriceLinesModel
            from decimal import Decimal
            
            # Deactivate old lines
            db.query(PriceLinesModel).filter(
                PriceLinesModel.ticker == ticker.upper(),
                PriceLinesModel.valid_until.is_(None)
            ).update({"valid_until": datetime.utcnow()})
            
            # Create new lines
            new_lines = PriceLinesModel(
                ticker=ticker.upper(),
                stock_id=stock.id,
                green_line=Decimal(str(result.data.green_line)) if result.data.green_line else None,
                red_line=Decimal(str(result.data.red_line)) if result.data.red_line else None,
                source=source_type,
                source_reference=f"{source_type.title()} Update {datetime.utcnow().strftime('%Y-%m-%d')}",
                effective_from=datetime.utcnow()
            )
            db.add(new_lines)
            db.commit()
        
        return {
            "success": True,
            "ticker": ticker.upper(),
            "previous_score": result.score_change + result.data.gomes_score if result.score_change else None,
            "new_score": result.data.gomes_score,
            "score_change": result.score_change,
            "thesis_drift": result.thesis_drift,
            "action_signal": result.data.action_signal,
            "source_type": source_type,
            "analysis_summary": result.analysis_text[:500] + "..." if len(result.analysis_text) > 500 else result.analysis_text,
        }
        
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Update failed: {str(e)}")


# ============================================================================
# THESIS DRIFT & SCORE HISTORY ENDPOINTS
# ============================================================================

@router.get("/score-history/{ticker}")
def get_score_history(
    ticker: str,
    limit: int = 30,
    db: Session = Depends(get_db),
):
    """
    Get historical Gomes scores for a ticker.
    
    Used for Thesis Drift visualization - shows how the score
    evolved over time compared to price movements.
    
    Args:
        ticker: Stock ticker symbol
        limit: Max number of records (default 30)
        
    Returns:
        List of score history records with timestamps
    """
    from sqlalchemy import desc
    
    try:
        # Try to get from score_history table first
        from app.models.score_history import GomesScoreHistory
        
        history = db.query(GomesScoreHistory).filter(
            GomesScoreHistory.ticker == ticker.upper()
        ).order_by(desc(GomesScoreHistory.recorded_at)).limit(limit).all()
        
        if history:
            return {
                "ticker": ticker.upper(),
                "count": len(history),
                "history": [
                    {
                        "date": h.recorded_at.isoformat() if h.recorded_at else None,
                        "gomes_score": h.gomes_score,
                        "thesis_status": h.thesis_status,
                        "action_signal": h.action_signal,
                        "price_at_analysis": float(h.price_at_analysis) if h.price_at_analysis else None,
                        "source": h.analysis_source,
                    }
                    for h in history
                ]
            }
    except Exception:
        pass  # Table may not exist yet, fall back to stocks table
    
    # Fallback: Get historical scores from stocks table (versioned records)
    from app.models.stock import Stock
    
    stocks = db.query(Stock).filter(
        Stock.ticker == ticker.upper()
    ).order_by(desc(Stock.created_at)).limit(limit).all()
    
    return {
        "ticker": ticker.upper(),
        "count": len(stocks),
        "history": [
            {
                "date": s.created_at.isoformat() if s.created_at else None,
                "gomes_score": s.gomes_score,
                "thesis_status": None,  # Not tracked in stocks table
                "action_signal": s.action_verdict,
                "price_at_analysis": None,
                "source": s.source_type,
            }
            for s in stocks
        ]
    }


@router.get("/drift-alerts")
def get_drift_alerts(
    acknowledged: Optional[bool] = None,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    """
    Get thesis drift alerts.
    
    Returns alerts generated when:
    - Price rises but score falls (HYPE_AHEAD_OF_FUNDAMENTALS)
    - Score drops significantly (THESIS_BREAKING)
    - New accumulation opportunity (ACCUMULATE_SIGNAL)
    
    Args:
        acknowledged: Filter by acknowledgment status
        limit: Max alerts to return
    """
    try:
        from app.models.score_history import ThesisDriftAlert
        from sqlalchemy import desc
        
        query = db.query(ThesisDriftAlert)
        
        if acknowledged is not None:
            query = query.filter(ThesisDriftAlert.is_acknowledged == acknowledged)
        
        alerts = query.order_by(desc(ThesisDriftAlert.created_at)).limit(limit).all()
        
        return {
            "count": len(alerts),
            "alerts": [
                {
                    "id": a.id,
                    "ticker": a.ticker,
                    "alert_type": a.alert_type,
                    "severity": a.severity,
                    "old_score": a.old_score,
                    "new_score": a.new_score,
                    "price_change_pct": float(a.price_change_pct) if a.price_change_pct else None,
                    "message": a.message,
                    "is_acknowledged": a.is_acknowledged,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                }
                for a in alerts
            ]
        }
    except Exception as e:
        return {"count": 0, "alerts": [], "note": "Alerts table not initialized yet"}


@router.post("/drift-alerts/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: int,
    db: Session = Depends(get_db),
):
    """Mark a thesis drift alert as acknowledged"""
    try:
        from app.models.score_history import ThesisDriftAlert
        from datetime import datetime
        
        alert = db.query(ThesisDriftAlert).filter(
            ThesisDriftAlert.id == alert_id
        ).first()
        
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        
        alert.is_acknowledged = True
        alert.acknowledged_at = datetime.utcnow()
        db.commit()
        
        return {"success": True, "alert_id": alert_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/refresh-all-verdicts")
def refresh_all_verdicts(
    force: bool = Query(False, description="Force refresh all stocks"),
    db: Session = Depends(get_db),
):
    """
    Refresh investment verdicts for all stocks in watchlist.
    
    Called automatically after importing new transcript.
    Updates verdicts based on latest Gomes scores, lifecycle phase,
    price lines, and market alert level.
    """
    try:
        from app.models.gomes import InvestmentVerdictModel
        from app.services.gomes_gatekeeper import GomesGatekeeper
        
        # Get all active watchlist tickers
        watchlist = db.query(ActiveWatchlist).filter(
            ActiveWatchlist.is_active == True
        ).all()
        
        if not watchlist:
            return {
                "success": True,
                "message": "No active watchlist items to refresh",
                "updated_count": 0
            }
        
        gatekeeper = GomesGatekeeper(db)
        updated_count = 0
        errors = []
        
        for item in watchlist:
            try:
                # Run gatekeeper analysis for each ticker
                verdict = gatekeeper.evaluate_ticker(item.ticker)
                
                if verdict:
                    # Invalidate old verdicts
                    old_verdicts = db.query(InvestmentVerdictModel).filter(
                        InvestmentVerdictModel.ticker == item.ticker,
                        InvestmentVerdictModel.valid_until == None
                    ).all()
                    
                    for old in old_verdicts:
                        old.valid_until = datetime.utcnow()
                    
                    # Save new verdict
                    db.add(verdict)
                    updated_count += 1
                    
            except Exception as e:
                errors.append(f"{item.ticker}: {str(e)}")
                continue
        
        db.commit()
        
        return {
            "success": True,
            "message": f"Refreshed verdicts for {updated_count} stocks",
            "updated_count": updated_count,
            "total_watchlist": len(watchlist),
            "errors": errors if errors else None
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to refresh verdicts: {str(e)}"
        )


@router.get("/weekly-summary")
def get_weekly_summary(
    days: int = Query(7, description="Number of days to look back"),
    db: Session = Depends(get_db),
):
    """
    Generate weekly investment summary.
    
    Returns:
    - New transcripts from this week
    - Stocks with score changes (improved/deteriorated)
    - New BUY/SELL signals
    - Thesis drift alerts
    - Top conviction picks
    """
    try:
        from app.services.weekly_summary import WeeklySummary
        from datetime import datetime, timedelta
        
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        summary_service = WeeklySummary(db)
        summary = summary_service.generate_summary(start_date, end_date)
        
        return summary
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate summary: {str(e)}"
        )


@router.post("/weekly-summary/send-email")
def send_weekly_summary_email_endpoint(
    recipient_email: str = Query(..., description="Recipient email address"),
    db: Session = Depends(get_db),
):
    """
    Send weekly summary email to specified address.
    
    Requires SMTP settings in environment variables:
    - EMAIL_HOST
    - EMAIL_PORT
    - EMAIL_USERNAME
    - EMAIL_PASSWORD
    """
    try:
        from app.services.weekly_summary import send_weekly_summary_email
        
        success = send_weekly_summary_email(
            db=db,
            recipient_email=recipient_email
        )
        
        if success:
            return {
                "success": True,
                "message": f"Weekly summary sent to {recipient_email}"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to send email - check SMTP settings"
            )
            
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send email: {str(e)}"
        )



