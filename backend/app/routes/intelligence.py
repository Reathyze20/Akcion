"""
API Routes for Analysis Intelligence Module
Handles analyst transcripts, SWOT analysis, and enhanced watchlist
"""
from datetime import datetime
from datetime import date as date_type
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text, func
from sqlalchemy.orm import Session

from ..database.connection import get_db
from ..models.analysis import AnalystTranscript, SWOTAnalysis
from ..models.trading import ActiveWatchlist
from ..schemas.analysis import (
    TranscriptCreate,
    TranscriptUpdate,
    TranscriptResponse,
    TranscriptSummaryResponse,
    SWOTCreate,
    SWOTUpdate,
    SWOTResponse,
    WatchlistAnalysisUpdate,
    WatchlistAnalysisResponse,
    AnalysisStats,
    TopGomesPick
)


router = APIRouter(prefix="/api/intelligence", tags=["Intelligence"])


# ==========================================
# ANALYST TRANSCRIPTS
# ==========================================

@router.post("/transcripts", response_model=TranscriptResponse, status_code=201)
async def create_transcript(
    transcript: TranscriptCreate,
    db: Session = Depends(get_db)
):
    """Create new analyst transcript"""
    db_transcript = AnalystTranscript(**transcript.model_dump())
    db.add(db_transcript)
    db.commit()
    db.refresh(db_transcript)
    return db_transcript


@router.get("/transcripts", response_model=List[TranscriptSummaryResponse])
async def list_transcripts(
    source_name: Optional[str] = None,
    ticker: Optional[str] = None,
    date_from: Optional[date_type] = None,
    date_to: Optional[date_type] = None,
    is_processed: Optional[bool] = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """List transcripts with filtering"""
    query = db.query(AnalystTranscript)
    
    if source_name:
        query = query.filter(AnalystTranscript.source_name.ilike(f"%{source_name}%"))
    if ticker:
        query = query.filter(AnalystTranscript.detected_tickers.contains([ticker]))
    if date_from:
        query = query.filter(AnalystTranscript.date >= date_from)
    if date_to:
        query = query.filter(AnalystTranscript.date <= date_to)
    if is_processed is not None:
        query = query.filter(AnalystTranscript.is_processed == is_processed)
    
    transcripts = query.order_by(AnalystTranscript.date.desc()).limit(limit).all()
    return transcripts


@router.get("/transcripts/{transcript_id}", response_model=TranscriptResponse)
async def get_transcript(transcript_id: int, db: Session = Depends(get_db)):
    """Get transcript by ID"""
    transcript = db.query(AnalystTranscript).filter(AnalystTranscript.id == transcript_id).first()
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found")
    return transcript


@router.patch("/transcripts/{transcript_id}", response_model=TranscriptResponse)
async def update_transcript(
    transcript_id: int,
    updates: TranscriptUpdate,
    db: Session = Depends(get_db)
):
    """Update transcript after processing"""
    transcript = db.query(AnalystTranscript).filter(AnalystTranscript.id == transcript_id).first()
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found")
    
    for key, value in updates.model_dump(exclude_unset=True).items():
        setattr(transcript, key, value)
    
    db.commit()
    db.refresh(transcript)
    return transcript


@router.delete("/transcripts/{transcript_id}", status_code=204)
async def delete_transcript(transcript_id: int, db: Session = Depends(get_db)):
    """Delete transcript"""
    transcript = db.query(AnalystTranscript).filter(AnalystTranscript.id == transcript_id).first()
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found")
    db.delete(transcript)
    db.commit()


# ==========================================
# SWOT ANALYSIS
# ==========================================

@router.post("/swot", response_model=SWOTResponse, status_code=201)
async def create_swot(swot: SWOTCreate, db: Session = Depends(get_db)):
    """Create SWOT analysis (deactivates previous active SWOT for ticker)"""
    # Deactivate previous
    db.query(SWOTAnalysis).filter(
        SWOTAnalysis.ticker == swot.ticker,
        SWOTAnalysis.is_active == True
    ).update({"is_active": False})
    
    # Create new
    db_swot = SWOTAnalysis(
        **swot.model_dump(exclude={"swot_data"}),
        swot_data=swot.swot_data.model_dump()
    )
    db.add(db_swot)
    db.commit()
    db.refresh(db_swot)
    return db_swot


@router.get("/swot", response_model=List[SWOTResponse])
async def list_swots(
    ticker: Optional[str] = None,
    is_active: bool = True,
    min_confidence: Optional[float] = Query(None, ge=0, le=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """List SWOT analyses"""
    query = db.query(SWOTAnalysis)
    
    if ticker:
        query = query.filter(SWOTAnalysis.ticker == ticker.upper())
    if is_active:
        query = query.filter(SWOTAnalysis.is_active == True)
    if min_confidence is not None:
        query = query.filter(SWOTAnalysis.confidence_score >= min_confidence)
    
    swots = query.order_by(SWOTAnalysis.generated_at.desc()).limit(limit).all()
    return swots


@router.get("/swot/ticker/{ticker}", response_model=SWOTResponse)
async def get_latest_swot(ticker: str, db: Session = Depends(get_db)):
    """Get latest active SWOT for ticker"""
    swot = db.query(SWOTAnalysis).filter(
        SWOTAnalysis.ticker == ticker.upper(),
        SWOTAnalysis.is_active == True
    ).order_by(SWOTAnalysis.generated_at.desc()).first()
    
    if not swot:
        raise HTTPException(status_code=404, detail=f"No SWOT found for {ticker}")
    return swot


@router.patch("/swot/{swot_id}", response_model=SWOTResponse)
async def update_swot(
    swot_id: int,
    updates: SWOTUpdate,
    db: Session = Depends(get_db)
):
    """Update SWOT analysis"""
    swot = db.query(SWOTAnalysis).filter(SWOTAnalysis.id == swot_id).first()
    if not swot:
        raise HTTPException(status_code=404, detail="SWOT not found")
    
    for key, value in updates.model_dump(exclude_unset=True).items():
        if key == "swot_data" and value:
            setattr(swot, key, value.model_dump())
        else:
            setattr(swot, key, value)
    
    db.commit()
    db.refresh(swot)
    return swot


@router.post("/swot/expire-old", response_model=dict)
async def expire_old_swots(db: Session = Depends(get_db)):
    """Expire SWOT analyses older than 90 days"""
    result = db.execute(text("SELECT expire_old_swot_analyses()")).scalar()
    return {"expired_count": result}


# ==========================================
# ENHANCED WATCHLIST
# ==========================================

@router.patch("/watchlist/{ticker}", response_model=WatchlistAnalysisResponse)
async def update_watchlist_analysis(
    ticker: str,
    updates: WatchlistAnalysisUpdate,
    db: Session = Depends(get_db)
):
    """Update watchlist with Gomes score and analysis"""
    watchlist = db.query(ActiveWatchlist).filter(
        ActiveWatchlist.ticker == ticker.upper()
    ).first()
    
    if not watchlist:
        raise HTTPException(status_code=404, detail=f"Ticker {ticker} not in watchlist")
    
    for key, value in updates.model_dump(exclude_unset=True).items():
        setattr(watchlist, key, value)
    
    db.commit()
    db.refresh(watchlist)
    
    return await get_watchlist_with_analysis(ticker, db)


@router.get("/watchlist", response_model=List[WatchlistAnalysisResponse])
async def list_watchlist_with_analysis(
    min_gomes_score: Optional[float] = Query(None, ge=0, le=10),
    db: Session = Depends(get_db)
):
    """Get watchlist with analysis (uses v_watchlist_analysis view)"""
    query = "SELECT * FROM v_watchlist_analysis"
    params = {}
    
    if min_gomes_score is not None:
        query += " WHERE gomes_score >= :min_score"
        params["min_score"] = min_gomes_score
    
    query += " ORDER BY gomes_score DESC NULLS LAST"
    result = db.execute(text(query), params)
    
    items = []
    for row in result:
        items.append(WatchlistAnalysisResponse(
            id=row.watchlist_id,
            ticker=row.ticker,
            company_name=row.company_name,
            action_verdict=row.action_verdict,
            confidence_score=row.confidence_score,
            gomes_score=row.gomes_score,
            investment_thesis=row.investment_thesis,
            risks=row.risks,
            last_updated=row.last_updated,
            swot_data=row.swot_data,
            swot_model=row.swot_model,
            swot_generated_at=row.swot_generated_at
        ))
    return items


@router.get("/watchlist/{ticker}", response_model=WatchlistAnalysisResponse)
async def get_watchlist_with_analysis(ticker: str, db: Session = Depends(get_db)):
    """Get watchlist item with full analysis"""
    result = db.execute(
        text("SELECT * FROM v_watchlist_analysis WHERE ticker = :ticker"),
        {"ticker": ticker.upper()}
    ).first()
    
    if not result:
        raise HTTPException(status_code=404, detail=f"Ticker {ticker} not in watchlist")
    
    return WatchlistAnalysisResponse(
        id=result.watchlist_id,
        ticker=result.ticker,
        company_name=result.company_name,
        action_verdict=result.action_verdict,
        confidence_score=result.confidence_score,
        gomes_score=result.gomes_score,
        investment_thesis=result.investment_thesis,
        risks=result.risks,
        last_updated=result.last_updated,
        swot_data=result.swot_data,
        swot_model=result.swot_model,
        swot_generated_at=result.swot_generated_at
    )


@router.get("/top-gomes/{limit}", response_model=List[TopGomesPick])
async def get_top_gomes_picks(limit: int = 10, db: Session = Depends(get_db)):
    """Get top tickers by Gomes score"""
    result = db.execute(
        text("SELECT * FROM get_top_gomes_tickers(:limit)"),
        {"limit": limit}
    )
    
    picks = []
    for row in result:
        picks.append(TopGomesPick(
            ticker=row.ticker,
            gomes_score=float(row.gomes_score),
            company_name=row.company_name,
            action_verdict=row.action_verdict,
            investment_thesis=row.investment_thesis
        ))
    return picks


# ==========================================
# STATISTICS
# ==========================================

@router.get("/stats", response_model=AnalysisStats)
async def get_analysis_stats(db: Session = Depends(get_db)):
    """Get overall statistics"""
    total_transcripts = db.query(AnalystTranscript).count()
    processed_transcripts = db.query(AnalystTranscript).filter(
        AnalystTranscript.is_processed == True
    ).count()
    
    total_swots = db.query(SWOTAnalysis).count()
    active_swots = db.query(SWOTAnalysis).filter(SWOTAnalysis.is_active == True).count()
    
    gomes_count = db.query(ActiveWatchlist).filter(
        ActiveWatchlist.gomes_score.isnot(None)
    ).count()
    
    avg_gomes = db.query(func.avg(ActiveWatchlist.gomes_score)).filter(
        ActiveWatchlist.gomes_score.isnot(None)
    ).scalar()
    
    top_sources_query = db.query(
        AnalystTranscript.source_name,
        func.count(AnalystTranscript.id).label('count')
    ).group_by(AnalystTranscript.source_name).order_by(text('count DESC')).limit(5)
    
    top_sources = [
        {"source": row.source_name, "count": row.count}
        for row in top_sources_query
    ]
    
    return AnalysisStats(
        total_transcripts=total_transcripts,
        processed_transcripts=processed_transcripts,
        total_swots=total_swots,
        active_swots=active_swots,
        tickers_with_gomes_score=gomes_count,
        avg_gomes_score=float(avg_gomes) if avg_gomes else None,
        top_sources=top_sources
    )
