"""
API Routes for Analysis Intelligence Module
Handles analyst transcripts, SWOT analysis, enhanced watchlist,
knowledge synthesis (Brain Logic), and portfolio reconciliation (Sync Logic).
"""
import logging
from datetime import datetime
from datetime import date as date_type
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
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

logger = logging.getLogger(__name__)

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
    min_conviction_score: Optional[float] = Query(None, ge=0, le=10),
    db: Session = Depends(get_db)
):
    """Get watchlist with analysis (uses v_watchlist_analysis view)"""
    query = "SELECT * FROM v_watchlist_analysis"
    params = {}
    
    if min_conviction_score is not None:
        query += " WHERE conviction_score >= :min_score"
        params["min_score"] = min_conviction_score
    
    query += " ORDER BY conviction_score DESC NULLS LAST"
    result = db.execute(text(query), params)
    
    items = []
    for row in result:
        items.append(WatchlistAnalysisResponse(
            id=row.watchlist_id,
            ticker=row.ticker,
            company_name=row.company_name,
            action_verdict=row.action_verdict,
            confidence_score=row.confidence_score,
            conviction_score=row.conviction_score,
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
        conviction_score=result.conviction_score,
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
            conviction_score=float(row.conviction_score),
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
        ActiveWatchlist.conviction_score.isnot(None)
    ).count()
    
    avg_gomes = db.query(func.avg(ActiveWatchlist.conviction_score)).filter(
        ActiveWatchlist.conviction_score.isnot(None)
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
        tickers_with_conviction_score=gomes_count,
        avg_conviction_score=float(avg_gomes) if avg_gomes else None,
        top_sources=top_sources
    )


# ==========================================
# KNOWLEDGE SYNTHESIS (Brain Logic)
# ==========================================

from ..services.knowledge_synthesis import (
    KnowledgeSynthesisService,
    MergeAction,
)
from ..services.portfolio_reconciliation import (
    PortfolioReconciliationService,
)
from ..models.score_history import ThesisDriftAlert, ConvictionScoreHistory
from pydantic import Field


class KnowledgeSynthesisRequest(BaseModel):
    """Request for knowledge synthesis."""
    ticker: str = Field(..., description="Stock ticker symbol")
    new_info: str = Field(..., min_length=10, description="New information to synthesize")
    source: str = Field(default="Manual", description="Source of information")
    force_score: Optional[int] = Field(None, ge=1, le=10, description="Override score")


class KnowledgeSynthesisResponse(BaseModel):
    """Response from knowledge synthesis."""
    success: bool
    action: str
    ticker: str
    old_score: Optional[int] = None
    new_score: Optional[int] = None
    conflicts: List[str] = []
    merged_fields: List[str] = []
    alert_generated: bool = False
    explanation: str


@router.post("/synthesize", response_model=KnowledgeSynthesisResponse)
async def synthesize_knowledge(
    request: KnowledgeSynthesisRequest,
    db: Session = Depends(get_db)
):
    """
    Synthesize new knowledge into existing stock data.
    
    This endpoint implements the "Brain Logic":
    - Never overwrites existing data
    - Merges and refines information
    - Detects conflicts and adjusts scores
    - Correlates price mentions with price lines
    - Generates alerts for significant changes
    
    Use cases:
    - Pasting chat comments about a stock
    - Adding news/PR updates
    - Recording earnings call notes
    - Manual thesis updates
    """
    try:
        service = KnowledgeSynthesisService(db)
        result = await service.synthesize_knowledge(
            ticker=request.ticker,
            new_info=request.new_info,
            source=request.source,
            force_score=request.force_score
        )
        
        return KnowledgeSynthesisResponse(
            success=True,
            action=result.action.value,
            ticker=result.ticker,
            old_score=result.old_score,
            new_score=result.new_score,
            conflicts=result.conflicts,
            merged_fields=result.merged_fields,
            alert_generated=result.alert_generated,
            explanation=result.explanation
        )
        
    except Exception as e:
        logger.error(f"Knowledge synthesis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/quick-note/{ticker}")
async def add_quick_note(
    ticker: str,
    note: str = Query(..., min_length=5, description="Quick note to add"),
    source: str = Query(default="Quick Note"),
    db: Session = Depends(get_db)
):
    """
    Add a quick note to a stock's knowledge base.
    Simplified version of synthesize for fast updates.
    """
    try:
        service = KnowledgeSynthesisService(db)
        result = await service.synthesize_knowledge(
            ticker=ticker.upper(),
            new_info=note,
            source=source
        )
        
        return {
            "success": True,
            "ticker": result.ticker,
            "action": result.action.value,
            "new_score": result.new_score,
            "conflicts_detected": len(result.conflicts) > 0
        }
        
    except Exception as e:
        logger.error(f"Quick note failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# THESIS DRIFT ALERTS
# ==========================================

class ThesisDriftAlertResponse(BaseModel):
    """Thesis drift alert response."""
    id: int
    ticker: str
    alert_type: str
    severity: str
    old_score: Optional[int] = None
    new_score: Optional[int] = None
    message: str
    is_acknowledged: bool = False
    created_at: Optional[str] = None


@router.get("/alerts", response_model=List[ThesisDriftAlertResponse])
async def get_thesis_drift_alerts(
    ticker: Optional[str] = None,
    severity: Optional[str] = None,
    acknowledged: Optional[bool] = None,
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db)
):
    """
    Get thesis drift alerts.
    
    Filters:
    - ticker: Filter by specific stock
    - severity: INFO, WARNING, CRITICAL
    - acknowledged: True/False
    """
    query = db.query(ThesisDriftAlert)
    
    if ticker:
        query = query.filter(ThesisDriftAlert.ticker == ticker.upper())
    if severity:
        query = query.filter(ThesisDriftAlert.severity == severity.upper())
    if acknowledged is not None:
        query = query.filter(ThesisDriftAlert.is_acknowledged == acknowledged)
    
    alerts = query.order_by(ThesisDriftAlert.id.desc()).limit(limit).all()
    
    return [
        ThesisDriftAlertResponse(
            id=a.id,
            ticker=a.ticker,
            alert_type=a.alert_type,
            severity=a.severity,
            old_score=a.old_score,
            new_score=a.new_score,
            message=a.message,
            is_acknowledged=a.is_acknowledged,
            created_at=a.created_at.isoformat() if a.created_at else None
        )
        for a in alerts
    ]


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: int,
    db: Session = Depends(get_db)
):
    """Mark an alert as acknowledged."""
    alert = db.query(ThesisDriftAlert).filter(
        ThesisDriftAlert.id == alert_id
    ).first()
    
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert.is_acknowledged = True
    alert.acknowledged_at = datetime.utcnow()
    db.commit()
    
    return {"success": True, "alert_id": alert_id}


@router.post("/alerts/acknowledge-all")
async def acknowledge_all_alerts(
    ticker: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Acknowledge all unacknowledged alerts."""
    query = db.query(ThesisDriftAlert).filter(
        ThesisDriftAlert.is_acknowledged == False
    )
    
    if ticker:
        query = query.filter(ThesisDriftAlert.ticker == ticker.upper())
    
    count = query.update({
        "is_acknowledged": True,
        "acknowledged_at": datetime.utcnow()
    })
    db.commit()
    
    return {"success": True, "acknowledged_count": count}


# ==========================================
# SCORE HISTORY
# ==========================================

@router.get("/score-history/{ticker}")
async def get_score_history(
    ticker: str,
    limit: int = Query(default=30, le=100),
    db: Session = Depends(get_db)
):
    """Get score history for a ticker."""
    history = db.query(ConvictionScoreHistory).filter(
        ConvictionScoreHistory.ticker == ticker.upper()
    ).order_by(ConvictionScoreHistory.id.desc()).limit(limit).all()
    
    return [
        {
            "id": h.id,
            "score": h.conviction_score,
            "source": h.analysis_source,
            "thesis_status": h.thesis_status,
            "action_signal": h.action_signal,
            "recorded_at": h.recorded_at.isoformat() if h.recorded_at else None
        }
        for h in history
    ]


# ==========================================
# PORTFOLIO RECONCILIATION (Sync Logic)
# ==========================================

class ReconciliationPreviewRequest(BaseModel):
    """Request to preview reconciliation."""
    portfolio_id: int
    positions: List[dict]


@router.post("/reconcile/preview")
async def preview_reconciliation(
    request: ReconciliationPreviewRequest,
    db: Session = Depends(get_db)
):
    """
    Preview what a reconciliation would do before committing.
    
    Shows which positions would be:
    - Added (new in import)
    - Removed (sold - will be moved to watchlist)
    - Updated (quantity/price changes)
    """
    try:
        service = PortfolioReconciliationService(db)
        preview = service.preview_reconciliation(
            portfolio_id=request.portfolio_id,
            new_positions=request.positions
        )
        
        return preview
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Reconciliation preview failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reconcile/{portfolio_id}")
async def reconcile_portfolio(
    portfolio_id: int,
    positions: List[dict],
    db: Session = Depends(get_db)
):
    """
    Reconcile portfolio with new position data.
    
    This endpoint implements the "Sync Logic":
    - Detects sales when positions are missing
    - Automatically moves sold positions to Watchlist
    - Tracks all changes in investment log
    - Generates notifications for user awareness
    """
    try:
        service = PortfolioReconciliationService(db)
        result = service.reconcile_import(
            portfolio_id=portfolio_id,
            new_positions=positions
        )
        
        return {
            "success": True,
            "portfolio": result.portfolio_name,
            "summary": result.summary(),
            "positions_before": result.total_positions_before,
            "positions_after": result.total_positions_after,
            "sales_detected": result.sales_detected,
            "new_positions": result.new_positions,
            "updated_positions": result.updated_positions,
            "notifications": result.notifications,
        }
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Reconciliation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# UNIFIED NOTIFICATIONS
# ==========================================

@router.get("/notifications")
async def get_all_notifications(
    include_acknowledged: bool = Query(default=False),
    limit: int = Query(default=20, le=100),
    db: Session = Depends(get_db)
):
    """
    Get all notifications from various sources.
    
    Aggregates:
    - Thesis drift alerts
    - Score change notifications
    - Reconciliation alerts
    """
    notifications = []
    
    # Get thesis drift alerts
    alerts_query = db.query(ThesisDriftAlert)
    if not include_acknowledged:
        alerts_query = alerts_query.filter(ThesisDriftAlert.is_acknowledged == False)
    
    alerts = alerts_query.order_by(ThesisDriftAlert.id.desc()).limit(limit).all()
    
    for alert in alerts:
        notifications.append({
            "id": f"alert-{alert.id}",
            "type": "THESIS_DRIFT",
            "severity": alert.severity,
            "ticker": alert.ticker,
            "title": f"{alert.alert_type} Alert for {alert.ticker}",
            "message": alert.message,
            "is_read": alert.is_acknowledged,
            "timestamp": alert.created_at.isoformat() if alert.created_at else None,
            "data": {
                "old_score": alert.old_score,
                "new_score": alert.new_score
            }
        })
    
    # Get recent significant score changes
    recent_history = db.query(ConvictionScoreHistory).order_by(
        ConvictionScoreHistory.id.desc()
    ).limit(limit).all()
    
    for h in recent_history:
        if h.source and "conflict" in h.source.lower():
            notifications.append({
                "id": f"score-{h.id}",
                "type": "SCORE_CHANGE",
                "severity": "INFO",
                "ticker": h.ticker,
                "title": f"Score Updated for {h.ticker}",
                "message": h.note or f"New score: {h.score}",
                "is_read": True,  # Score changes are informational
                "timestamp": h.created_at.isoformat() if h.created_at else None,
                "data": {
                    "new_score": h.score,
                    "source": h.source
                }
            })
    
    # Sort by timestamp descending
    notifications.sort(
        key=lambda x: x.get("timestamp") or "",
        reverse=True
    )
    
    return notifications[:limit]
