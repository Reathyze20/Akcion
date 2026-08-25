"""
Gomes Analysis API Endpoints
==============================

API endpoints pro Gomes Investment Committee analýzu.
Umožňují frontend přístup ke skórovacímu systému Marka Gomese.

Author: GitHub Copilot with Claude Sonnet 4.5
Date: 2026-01-17
"""

import logging
from typing import List, Optional
from datetime import datetime, date

from fastapi import APIRouter, Depends, HTTPException, Query, Body
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
from app.services.score_journal import SOURCE_AI_ANALYST, record_score
from app.config.settings import get_settings

logger = logging.getLogger(__name__)


# ============================================================================
# ROUTER SETUP
# ============================================================================

router = APIRouter(
    prefix="/api/gomes",
    tags=["Gomes Analysis"]
)

# Cached accessor, not a second Settings() instance — a raw instantiation at
# import time crashes test collection wherever backend/.env doesn't exist (CI).
settings = get_settings()


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class MarketDataInput(BaseModel):
    """Optional market data input"""
    insider_buying: Optional[bool] = None
    earnings_date: Optional[datetime] = None


class StockUpdateRequest(BaseModel):
    """Request body pro update stock analýzy"""
    transcript: str = Field(..., min_length=50, description="New information text")
    source_type: str = Field("manual", description="Source: earnings, news, chat, transcript, manual")


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

def _conviction_score_to_response(score: GomesScore) -> GomesScoreResponse:
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
        
        return _conviction_score_to_response(score)
        
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
    
    Primárně používá data z tabulky Stock, kde je uložený conviction_score.
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
        
        if stock and stock.conviction_score is not None:
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
            elif stock.conviction_score >= 9:
                rating = "STRONG_BUY"
            elif stock.conviction_score >= 7:
                rating = "BUY"
            elif stock.conviction_score >= 5:
                rating = "HOLD"
            else:
                rating = "AVOID"
            
            confidence = "HIGH" if (stock.conviction_score or 0) >= 8 else "MEDIUM" if (stock.conviction_score or 0) >= 6 else "LOW"
            
            # Build reasoning from available fields
            reasoning = stock.trade_rationale or stock.edge or "From transcript analysis"
            
            # Build risk factors
            risk_factors = []
            if stock.risks:
                risk_factors = [r.strip() for r in stock.risks.split(",") if r.strip()]
            
            return GomesScoreResponse(
                ticker=stock.ticker,
                total_score=stock.conviction_score or 0,
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
        
        return _conviction_score_to_response(score)
        
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
    seřazené podle conviction_score (highest first).
    
    **Use case**: Daily scan pro identifikaci top setups.
    """
    try:
        # Fetch all stocks from database with is_latest=True
        stocks_list = (
            db.query(Stock)
            .filter(Stock.is_latest == True)
            .filter(Stock.conviction_score >= min_score)
            .order_by(desc(Stock.conviction_score))
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
            # Determine rating based on action_verdict and conviction_score
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
                score=stock.conviction_score or 0,
                rating=rating,
                confidence="HIGH" if (stock.conviction_score or 0) >= 8 else "MEDIUM" if (stock.conviction_score or 0) >= 6 else "LOW",
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
                results.append(_conviction_score_to_response(score))
                
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
    from decimal import Decimal
    from app.core.prompts import TICKER_EXTRACTION_PROMPT
    from app.services.llm import LLMError, complete_json
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
        
        # Build prompt
        prompt = TICKER_EXTRACTION_PROMPT.format(
            tickers=", ".join(tickers),
            transcript=transcript.raw_text[:50000]  # Limit transcript length
        )
        
        # Call AI. Fence-stripping and JSON parsing live in services.llm now.
        # The version that used to be here stripped the fence with a call that
        # removes *characters*, not a prefix — so it also ate a leading `{`,
        # `j`, `s`, `o` or `n` from the payload it was meant to clean.
        try:
            data = complete_json(prompt)
        except LLMError as e:
            # Say which call failed and why. "AI response was not valid JSON"
            # was the old blanket answer even when the call never went out.
            return {
                "message": f"Analýza selhala: {e}",
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
                "conviction_score": 8,
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
                "conviction_score": result.data.conviction_score,
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
    request_body: Optional[StockUpdateRequest] = Body(None),
    transcript: Optional[str] = Query(None, min_length=50, description="New information text (deprecated, use body)"),
    source_type: str = Query("manual", description="Source type (deprecated, use body)"),
    db: Session = Depends(get_db),
):
    """
    Update existing stock with new information.
    
    Supports both POST body (preferred) and query params (legacy).
    
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
    
    Example (new):
        POST /api/gomes/update-stock/GKPRF
        Body: {"transcript": "Q4 earnings...", "source_type": "earnings"}
    
    Example (legacy):
        POST /api/gomes/update-stock/GKPRF?transcript=Q4%20earnings...&source_type=earnings
    """
    from app.services.gomes_deep_dd import GomesDeepDueDiligenceService
    from app.schemas.gomes import DeepDueDiligenceRequest
    
    # Support both body and query params (body takes precedence)
    final_transcript = request_body.transcript if request_body else transcript
    final_source_type = request_body.source_type if request_body else source_type
    
    if not final_transcript:
        raise HTTPException(status_code=400, detail="transcript is required (in body or query param)")
    
    try:
        service = GomesDeepDueDiligenceService(db)
        
        # Always include existing data for context
        request = DeepDueDiligenceRequest(
            transcript=final_transcript,
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
            "previous_score": result.score_change + result.data.conviction_score if result.score_change else None,
            "new_score": result.data.conviction_score,
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


@router.post("/update-stock-ai/{ticker}")
async def update_stock_with_ai_analyst(
    ticker: str,
    request_body: StockUpdateRequest = Body(...),
    db: Session = Depends(get_db),
):
    """
    Update stock using Gomes AI Analyst (NEW 2026-01-25).
    
    This endpoint uses structured AI prompts to:
    1. Extract cash metrics (runway, burn rate, total cash)
    2. Detect inflection status (WAIT_TIME, UPCOMING, ACTIVE_GOLD_MINE)
    3. Generate Gomes score (0-10) with specific deltas
    4. Update thesis narrative
    5. Identify catalysts and dates
    
    AI output is validated against structured schema before DB update.
    
    Example:
        POST /api/gomes/update-stock-ai/KUYA.V
        Body: {
            "transcript": "Q4 earnings: Revenue $5M, cash $25M, burn $2M/quarter...",
            "source_type": "quarterly_report"
        }
    
    Returns:
        {
            "success": true,
            "ticker": "KUYA.V",
            "analysis": {
                "conviction_score": 9,
                "score_delta": +2,
                "cash_runway_months": 12,
                "inflection_status": "ACTIVE_GOLD_MINE",
                "primary_catalyst": "Q2 Production Ramp",
                ...
            }
        }
    """
    from app.services.gomes_ai_analyst import AnalystNotImplemented, GomesAIAnalyst
    
    try:
        # Get or create stock
        stock = db.query(Stock).filter(Stock.ticker == ticker.upper()).first()
        if not stock:
            stock = Stock(
                ticker=ticker.upper(),
                company_name=None,  # Will be filled by AI
                source_type=request_body.source_type,
                is_latest=True,
                version=1
            )
            db.add(stock)
            db.flush()
        
        # Run AI analysis
        analyst = GomesAIAnalyst()
        analysis = await analyst.analyze_document(
            ticker=ticker.upper(),
            document_text=request_body.transcript,
            source_type=request_body.source_type,
            current_score=stock.conviction_score,
            previous_thesis=stock.thesis_narrative
        )
        
        # Update stock with AI results
        await analyst.update_stock_from_analysis(stock, analysis)
        
        # Journal the scoring event — unconditionally, not only when the score
        # moved. A reaffirmed nine is as much a prediction as a changed one,
        # and recording only the changes would leave the calibration sample
        # made of nothing but volatile tickers.
        #
        # `thesis_status` stays empty: the column's vocabulary is
        # IMPROVED/STABLE/DETERIORATED/BROKEN and `inflection_status` speaks a
        # different one, so copying it across would file wrong values under a
        # right-looking name.
        record_score(
            db,
            ticker=ticker,
            score=stock.conviction_score,
            source=request_body.source_type or SOURCE_AI_ANALYST,
            stock=stock,
            price=None,
            action_signal=None,
        )

        db.commit()
        db.refresh(stock)
        
        return {
            "success": True,
            "ticker": ticker.upper(),
            "analysis": {
                "conviction_score": stock.conviction_score,
                "score_delta": analysis.score_delta,
                "score_reasoning": analysis.score_reasoning,
                "cash_runway_months": stock.cash_runway_months,
                "total_cash": stock.total_cash,
                "quarterly_burn_rate": stock.quarterly_burn_rate,
                "inflection_status": stock.inflection_status,
                "primary_catalyst": stock.primary_catalyst,
                "catalyst_date": stock.catalyst_date.isoformat() if stock.catalyst_date else None,
                "thesis_narrative": stock.thesis_narrative,
                "insider_activity": stock.insider_activity,
                "red_flags": analysis.red_flags,
                "green_flags": analysis.green_flags,
            },
            "updated_fields": [
                "conviction_score", "cash_runway_months", "total_cash", 
                "quarterly_burn_rate", "inflection_status", "primary_catalyst",
                "catalyst_date", "thesis_narrative", "insider_activity"
            ]
        }
        
    except AnalystNotImplemented as e:
        # 501, not 500: nothing failed. There is no analyst behind this
        # endpoint, and the rollback matters — the handler creates the `stocks`
        # row before asking, so without it a refusal would still leave a new
        # empty ticker in the portfolio.
        db.rollback()
        raise HTTPException(status_code=501, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Validation error: {str(e)}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"AI analysis failed: {str(e)}")


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
        List of score history records with timestamps. An empty list means the
        journal holds nothing for this ticker yet — it is not padded from
        anywhere else.

    There used to be a fallback here that read the `stocks` row and returned
    it as a history entry dated `created_at`. That invented a past: one
    current score, stamped with a day on which nobody claims it was issued,
    rendered as a trend line. The journal
    (`app/services/score_journal.py`) is now the only source, and a query
    failure is allowed to surface as a 500 rather than being disguised as
    "this ticker has no history".
    """
    from sqlalchemy import desc

    from app.models.score_history import ConvictionScoreHistory

    history = db.query(ConvictionScoreHistory).filter(
        ConvictionScoreHistory.ticker == ticker.upper()
    ).order_by(desc(ConvictionScoreHistory.recorded_at)).limit(limit).all()

    return {
        "ticker": ticker.upper(),
        "count": len(history),
        "history": [
            {
                "date": h.recorded_at.isoformat() if h.recorded_at else None,
                "conviction_score": h.conviction_score,
                "thesis_status": h.thesis_status,
                "action_signal": h.action_signal,
                "price_at_analysis": float(h.price_at_analysis) if h.price_at_analysis is not None else None,
                "source": h.analysis_source,
            }
            for h in history
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


# `GET /api/gomes/analyze-position/{ticker}` stood here and published a second
# set of verdicts over the same holdings the band engine judges — HARD_EXIT,
# SELL, TRIM, HOLD, ACCUMULATE, SNIPER — computed by `GomesLogicEngine`, whose
# rule 5 was unreachable and whose rule 4 always fired first. The band engine
# behind `/api/trading/daily-actions` answers the same question with the
# cylinders, the semafor, the per-account caps and the pacing rules attached.


# ============================================================================
# TRACKER SYNC — the feed that gives the bands their numbers
# ============================================================================

class TrackerSyncResponse(BaseModel):
    """
    What one read of the tracker did.

    `status` is kept separate from `error` on purpose: TOO_SOON is not a
    failure and UNAVAILABLE is not a bug, and flattening the three outcomes
    into "did it work" would hide the only one worth acting on.
    """

    status: str = Field(..., description="SYNCED | TOO_SOON | UNAVAILABLE")
    picks_read: int = 0
    created: List[str] = Field(default_factory=list)
    band_updated: List[str] = Field(default_factory=list)
    price_updated: List[str] = Field(default_factory=list)
    #: Bands the analyst has moved. Every score computed before one of these
    #: was measured against a chart that no longer exists.
    changes: List[str] = Field(default_factory=list)
    summary_cs: str
    error: Optional[str] = None
    synced_at: Optional[datetime] = None


@router.post("/tracker/sync", response_model=TrackerSyncResponse)
def sync_gomes_tracker(
    force: bool = Query(
        False,
        description=(
            "Read even if the 12-hour minimum has not elapsed. For a first run "
            "or to check an announced change — never for a loop."
        ),
    ),
    db: Session = Depends(get_db),
):
    """
    Read the Gomes tracker and write its bands onto the GOMES stock rows.

    Three outcomes, kept distinct because collapsing them would hide the one
    that matters: SYNCED (we looked), TOO_SOON (we did not look), UNAVAILABLE
    (we looked and could not see). An unreachable source is not an error here —
    it is recorded and reported, so an outage never becomes a retry loop
    against somebody else's server.

    What it will not touch: `cylinders`, which the tracker does not publish and
    which the Buy Guard requires. A synced band alone therefore still cannot
    produce a BUY, and that is the correct outcome rather than a gap.
    """
    from app.services.tracker_sync import STATUS_SYNCED, sync_tracker

    try:
        report = sync_tracker(db, force=force)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception("Tracker sync failed")
        raise HTTPException(status_code=500, detail=f"Tracker sync failed: {e}")

    if report.status == STATUS_SYNCED and report.touched_anything:
        logger.info(
            "Tracker sync: %s created, %s rebanded, %s changes",
            len(report.created), len(report.band_updated), len(report.changes),
        )

    return TrackerSyncResponse(
        status=report.status,
        picks_read=report.picks_read,
        created=report.created,
        band_updated=report.band_updated,
        price_updated=report.price_updated,
        changes=[c.detail for c in report.changes],
        summary_cs=report.summary_cs(),
        error=report.error,
        synced_at=report.synced_at,
    )


# ============================================================================
# CYLINDERS — proposal, and the confirmation that turns it into permission
# ============================================================================
# `deserved_score = 10 − cylinders` is one half of every buy decision, and the
# Buy Guard refuses outright when cylinders are unknown. They were unknown for
# every company in the app: the only writer hardcoded None. `cylinders.py` now
# computes a number from named, dated facts — but a proposal authorises
# nothing. Only a value the owner has looked at and agreed to reaches the guard.


class CylinderEvidenceItem(BaseModel):
    delta: int
    fact_cs: str
    source: str
    as_of: Optional[date] = None


class CylinderProposalResponse(BaseModel):
    ticker: str
    cylinders: Optional[int] = None
    deserved_score: Optional[float] = None
    layer: str
    confidence: Optional[str] = None
    evidence: List[CylinderEvidenceItem] = Field(default_factory=list)
    unknowns: List[str] = Field(default_factory=list)
    summary_cs: str = ""
    #: What is on record now, so the screen can show "proposed 6, confirmed 5".
    confirmed_cylinders: Optional[int] = None
    confirmed_at: Optional[datetime] = None
    confirmed_by: Optional[str] = None
    valid_until: Optional[datetime] = None


class ConfirmCylindersRequest(BaseModel):
    cylinders: int = Field(..., ge=0, le=10)
    confirmed_by: str = Field(..., min_length=1, max_length=100)
    valid_until: Optional[datetime] = Field(
        None,
        description=(
            "When the agreement lapses. Omit and it defaults to a quarter — "
            "the next report is what can contradict it."
        ),
    )
    phase: Optional[str] = Field(
        None, description="GREAT_FIND | WAIT_TIME | GOLD_MINE | UNKNOWN"
    )
    override: bool = Field(
        False,
        description=(
            "Write this even though a stronger source (an analyst on record) "
            "is still standing. Without it the write is refused with 400 and a "
            "message naming what stands — so the screen can show him what he "
            "would be overwriting before he agrees to it."
        ),
    )


def _proposal_response(db: Session, ticker: str, proposal) -> CylinderProposalResponse:
    from app.models.gomes import StockLifecycleModel
    from app.core.tickers import canonical_ticker

    active = (
        db.query(StockLifecycleModel)
        .filter(StockLifecycleModel.ticker == (canonical_ticker(ticker) or ticker.upper()))
        .filter(StockLifecycleModel.valid_until.is_(None))
        .order_by(desc(StockLifecycleModel.detected_at))
        .first()
    )
    return CylinderProposalResponse(
        ticker=proposal.ticker,
        cylinders=proposal.cylinders,
        deserved_score=proposal.deserved_score,
        layer=proposal.layer,
        confidence=proposal.confidence,
        evidence=[
            CylinderEvidenceItem(
                delta=e.delta, fact_cs=e.fact_cs, source=e.source, as_of=e.as_of
            )
            for e in proposal.evidence
        ],
        unknowns=proposal.unknowns,
        summary_cs=proposal.summary_cs(),
        confirmed_cylinders=(
            active.cylinders_count
            if active is not None and active.cylinders_confirmed_at is not None
            else None
        ),
        confirmed_at=active.cylinders_confirmed_at if active is not None else None,
        confirmed_by=active.cylinders_confirmed_by if active is not None else None,
        valid_until=active.cylinders_valid_until if active is not None else None,
    )


@router.get("/cylinders/{ticker}", response_model=CylinderProposalResponse)
def get_cylinder_proposal(ticker: str, db: Session = Depends(get_db)):
    """
    What the rubric makes of this company, and what is on record.

    Reads only what the database already holds — no SEC or Yahoo call, so the
    screen never waits on somebody else's server. `scripts/propose_cylinders.py`
    is what pulls fresh filings.
    """
    from app.services.cylinder_intake import propose

    try:
        proposal = propose(db, ticker)
    except Exception as e:
        logger.exception("Cylinder proposal failed for %s", ticker)
        raise HTTPException(status_code=500, detail=f"Návrh válců selhal: {e}")

    return _proposal_response(db, ticker, proposal)


@router.post("/cylinders/{ticker}", response_model=CylinderProposalResponse)
def confirm_cylinders(
    ticker: str,
    request: ConfirmCylindersRequest,
    db: Session = Depends(get_db),
):
    """
    Record a cylinder count the owner agrees to. This is what unlocks buying.

    The number is his, not the rubric's: he may confirm something other than
    what was proposed, and that is the point of the step. What the app stores
    alongside it is the evidence he was looking at, so three months later the
    decision can still be judged.
    """
    from app.services.cylinder_intake import confirm, propose

    try:
        proposal = propose(db, ticker)
        confirm(
            db, ticker, request.cylinders,
            confirmed_by=request.confirmed_by,
            proposal=proposal,
            valid_until=request.valid_until,
            phase=request.phase,
            override=request.override,
        )
        db.commit()
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.exception("Cylinder confirmation failed for %s", ticker)
        raise HTTPException(status_code=500, detail=f"Potvrzení válců selhalo: {e}")

    return _proposal_response(db, ticker, proposal)


# ============================================================================
# THE LADDER — every holding, its band, and the two prices that change it
# ============================================================================


class LadderItem(BaseModel):
    """One company on the ladder."""

    ticker: str
    company_name: Optional[str] = None
    band: str
    reason_cs: str
    rr_score: Optional[float] = None
    deserved: Optional[float] = None
    #: The two orders. Derived from the Green and Red Lines rather than from
    #: today's quote, so they survive a stale price feed.
    buy_below: Optional[float] = None
    sell_above: Optional[float] = None
    take_profit_above: Optional[float] = None
    add_below: Optional[float] = None
    line_currency: Optional[str] = None
    trigger: str = "ZADNY"
    trigger_reason: str = ""
    quality_expired: bool = False


class LadderResponse(BaseModel):
    generated_at: datetime
    #: Cheapest first — that is where money would go, so that is what leads.
    items: List[LadderItem] = Field(default_factory=list)
    with_band: int = 0
    outside_method: int = 0


@router.get("/ladder", response_model=LadderResponse)
def get_portfolio_ladder(db: Session = Depends(get_db)):
    """
    The whole portfolio on one ladder: a band per company and two limit prices.

    One row per COMPANY, not per account — the band is a fact about the
    business, and two people holding the same stock should read the same thing.
    What either of them should DO about it depends on his own cost basis and
    cash, and that is the Daily Action engine's job.
    """
    from app.services.currency import CurrencyService
    from app.services.ladder_view import portfolio_ladder
    from app.trading.gomes_logic import Band

    try:
        rows = portfolio_ladder(db, fx_rate_to_czk=CurrencyService.get_rate_to_czk)
    except Exception as e:
        logger.exception("Ladder failed")
        raise HTTPException(status_code=500, detail=f"Žebřík se nepodařilo sestavit: {e}")

    items = [
        LadderItem(
            ticker=r.ticker,
            company_name=r.company_name,
            band=r.reading.band.value,
            reason_cs=r.reading.reason_cs,
            rr_score=r.reading.rr_score,
            deserved=r.reading.deserved,
            buy_below=r.reading.buy_below,
            sell_above=r.reading.sell_above,
            take_profit_above=r.reading.take_profit_above,
            add_below=r.reading.add_below,
            line_currency=r.line_currency,
            trigger=r.trigger.value,
            trigger_reason=r.trigger_reason,
            quality_expired=r.quality_expired,
        )
        for r in rows
    ]
    return LadderResponse(
        generated_at=datetime.now(),
        items=items,
        with_band=sum(1 for r in rows if r.reading.is_tradeable),
        outside_method=sum(1 for r in rows if r.reading.band is Band.MIMO_METODIKU),
    )


# ============================================================================
# WHATSAPP PASTE — who writes in the group, and what they claimed
# ============================================================================
# `whatsapp_intake.parse_export` has existed and had no caller. It is what
# turns the second source from a scraped list of endorsement counts into
# somebody's written opinion — and since 2026-08-23 a written opinion from a
# listed analyst can refuse a purchase, so it has to be able to arrive.


class WhatsAppSpeaker(BaseModel):
    name: str
    messages: int
    listed: bool


class WhatsAppPasteRequest(BaseModel):
    raw: str = Field(..., min_length=1, description="Export zkopírovaný z WhatsAppu")
    pasted_on: Optional[date] = Field(
        None,
        description=(
            "Den, kdy byl export pořízen. WhatsApp píše 'dnes' a 'včera' místo "
            "data, takže bez něj nejde relativní hlavičku přepočítat."
        ),
    )
    extract: bool = Field(
        False,
        description=(
            "Spustit rozbor tvrzení. Bez něj se jen přečte, kdo v exportu píše "
            "— to nestojí nic a je to obvykle první, co chceš vidět."
        ),
    )


class WhatsAppPasteResponse(BaseModel):
    summary_cs: str
    messages: int
    speakers: List[WhatsAppSpeaker] = Field(default_factory=list)
    quoted_messages: int = 0
    skipped_short: int = 0
    first_message_on: Optional[date] = None
    last_message_on: Optional[date] = None
    #: Present only when `extract` was set. Keyed by source, so a failure on
    #: one source does not hide what the other one said.
    claims_by_source: dict = Field(default_factory=dict)
    errors: dict = Field(default_factory=dict)


@router.post("/whatsapp/paste", response_model=WhatsAppPasteResponse)
def ingest_whatsapp_paste(
    request: WhatsAppPasteRequest,
    db: Session = Depends(get_db),
):
    """
    Read a WhatsApp export: who writes in the group, and optionally what they claimed.

    Phone numbers are gone before anything else happens — the parser strips
    them unconditionally, ahead of storage, logging and any model.

    Only a listed analyst's text is sent for extraction. Everyone else's
    messages are counted and their names reported, so the owner can see who
    writes research and decide whether any of them belong on the roster, but
    nobody is attributed to a source on the strength of being in the room.
    """
    from app.services.analyst_roster import load as load_roster
    from app.services.whatsapp_ingest import (
        analyse_paste,
        documents_for_extraction,
        extract_for_sources,
    )

    when = request.pasted_on or date.today()
    try:
        report, quotable = analyse_paste(db, request.raw, pasted_on=when)
    except Exception as e:
        logger.exception("WhatsApp paste failed")
        raise HTTPException(status_code=400, detail=f"Export se nepodařilo přečíst: {e}")

    speakers = [
        WhatsAppSpeaker(name=name, messages=count, listed=name in report.quoted)
        for name, count in sorted(report.speakers.items(), key=lambda kv: -kv[1])
    ]

    response = WhatsAppPasteResponse(
        summary_cs=report.summary_cs(),
        messages=report.messages,
        speakers=speakers,
        quoted_messages=sum(report.quoted.values()),
        skipped_short=report.skipped_short,
        first_message_on=report.dates[0],
        last_message_on=report.dates[1],
    )

    if not request.extract or not quotable:
        return response

    settings = get_settings()
    api_key = getattr(settings, "anthropic_api_key", None)
    if not api_key:
        response.errors["_"] = "Chybí ANTHROPIC_API_KEY — rozbor nespouštím"
        return response

    outcome = extract_for_sources(
        documents_for_extraction(quotable, load_roster(db)),
        today_iso=when.isoformat(),
        api_key=api_key,
    )
    for source, result in outcome.items():
        if isinstance(result, Exception):
            response.errors[source] = f"{type(result).__name__}: {result}"
        else:
            response.claims_by_source[source] = result.model_dump()

    return response
