"""
Gomes Intelligence API Endpoints
==================================

REST API for Gomes Investment Gatekeeper system.
These endpoints provide access to the complete Gomes methodology.

Author: GitHub Copilot with Claude Opus 4.5
Date: 2026-01-17
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.schemas.gomes import (
    CalculatePositionRequest,
    ClassifyLifecycleRequest,
    GenerateVerdictRequest,
    GomesDashboardResponse,
    GomesStockItem,
    GomesStocksListResponse,
    GomesVerdictResponse,
    ImageLinesImportResponse,
    LifecyclePhaseResponse,
    MarketAlertResponse,
    PositionSizeResponse,
    PriceLinesResponse,
    ScanWatchlistRequest,
    SetMarketAlertRequest,
    SetPriceLinesRequest,
    WatchlistScanResponse,
)
from app.services.gomes_intelligence import GomesIntelligenceService
from app.trading.gomes_logic import (
    MarketAlert,
    MarketAlertSystem,
    PositionSizingEngine,
    RiskRewardCalculator,
)


# ============================================================================
# ROUTER SETUP
# ============================================================================

router = APIRouter(
    prefix="/api/intelligence",
    tags=["Gomes Intelligence"]
)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _verdict_to_response(verdict) -> GomesVerdictResponse:
    """Convert GomesVerdict to response schema"""
    # Determine price zone
    price_zone = None
    if verdict.current_price and (verdict.green_line or verdict.red_line):
        zone, _ = RiskRewardCalculator.get_action_zone(
            verdict.current_price,
            verdict.green_line,
            verdict.red_line
        )
        price_zone = zone
    
    return GomesVerdictResponse(
        ticker=verdict.ticker,
        verdict=verdict.verdict.value if hasattr(verdict.verdict, 'value') else verdict.verdict,
        passed_gomes_filter=verdict.passed_gomes_filter,
        blocked_reason=verdict.blocked_reason,
        gomes_score=verdict.gomes_score,
        ml_prediction_score=verdict.ml_prediction_score,
        ml_direction=verdict.ml_direction,
        lifecycle_phase=verdict.lifecycle_phase.value if hasattr(verdict.lifecycle_phase, 'value') else verdict.lifecycle_phase,
        market_alert=verdict.market_alert.value if hasattr(verdict.market_alert, 'value') else verdict.market_alert,
        position_tier=verdict.position_tier.value if verdict.position_tier and hasattr(verdict.position_tier, 'value') else verdict.position_tier,
        max_position_pct=verdict.max_position_pct,
        current_price=verdict.current_price,
        green_line=verdict.green_line,
        red_line=verdict.red_line,
        price_zone=price_zone,
        risk_factors=verdict.risk_factors,
        days_to_earnings=verdict.days_to_earnings,
        has_catalyst=verdict.has_catalyst,
        catalyst_type=verdict.catalyst_type,
        catalyst_description=verdict.catalyst_description,
        bull_case=verdict.bull_case,
        bear_case=verdict.bear_case,
        confidence=verdict.confidence,
        reasoning=verdict.reasoning,
        created_at=verdict.created_at
    )


# ============================================================================
# MARKET ALERT ENDPOINTS
# ============================================================================

@router.get("/market-alert", response_model=MarketAlertResponse)
def get_market_alert(db: Session = Depends(get_db)):
    """
    Get current market alert level and portfolio allocation.
    
    **Alert Levels:**
    - GREEN ALERT (OFFENSE): Aggressively deploying capital - Good time to buy
    - YELLOW ALERT (SELECTIVE): Only best setups
    - ORANGE ALERT (DEFENSE): Reducing exposure
    - RED ALERT (CASH IS KING): Preserve capital
    
    **Ref:** Minute 15:00-18:00 - Market Alert System
    """
    service = GomesIntelligenceService(db)
    alert = service.get_current_market_alert()
    allocation = service.get_market_allocation()
    mode_name, mode_description = MarketAlertSystem.get_description(alert)
    
    return MarketAlertResponse(
        alert_level=alert.value,
        mode_name=mode_name,
        mode_description=mode_description,
        stocks_pct=allocation.stocks_pct,
        cash_pct=allocation.cash_pct,
        hedge_pct=allocation.hedge_pct,
        hedge_ticker=allocation.hedge_ticker,
        reason="Current market state",
        effective_from=datetime.now()
    )


@router.post("/market-alert", response_model=MarketAlertResponse)
def set_market_alert(
    request: SetMarketAlertRequest,
    db: Session = Depends(get_db)
):
    """
    Set new market alert level.
    
    WARNING: This affects ALL investment decisions!
    
    **Impact:**
    - YELLOW (SELECTIVE): Speculative positions blocked
    - ORANGE (DEFENSE): Only primary positions allowed (reduced)
    - RED (CASH IS KING): All new positions blocked
    """
    try:
        service = GomesIntelligenceService(db)
        alert_model = service.set_market_alert(
            alert_level=request.alert_level,
            reason=request.reason,
            source=request.source
        )
        
        allocation = MarketAlertSystem.get_allocation(request.alert_level)
        mode_name, mode_description = MarketAlertSystem.get_description(request.alert_level)
        
        return MarketAlertResponse(
            alert_level=alert_model.alert_level,
            mode_name=mode_name,
            mode_description=mode_description,
            stocks_pct=float(alert_model.stocks_pct),
            cash_pct=float(alert_model.cash_pct),
            hedge_pct=float(alert_model.hedge_pct),
            hedge_ticker="RWM",
            reason=alert_model.reason,
            effective_from=alert_model.effective_from
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# LIFECYCLE ENDPOINTS
# ============================================================================

@router.get("/lifecycle/{ticker}", response_model=LifecyclePhaseResponse)
def get_lifecycle_phase(
    ticker: str,
    db: Session = Depends(get_db)
):
    """
    Get current lifecycle phase for a stock.
    
    **Phases:**
    - GREAT_FIND: Early opportunity, unknown gem
    - WAIT_TIME: Dead money - DO NOT INVEST
    - GOLD_MINE: Proven execution, safe buy
    
    **Ref:** Minute 25:00-31:28 - Stock Life Phases
    """
    service = GomesIntelligenceService(db)
    lifecycle = service.get_stock_lifecycle(ticker.upper())
    
    if not lifecycle:
        raise HTTPException(
            status_code=404,
            detail=f"No lifecycle data for {ticker}. Use POST /lifecycle to classify."
        )
    
    return LifecyclePhaseResponse(
        ticker=lifecycle.ticker,
        phase=lifecycle.phase,
        is_investable=lifecycle.is_investable,
        firing_on_all_cylinders=lifecycle.firing_on_all_cylinders,
        cylinders_count=lifecycle.cylinders_count,
        reasoning=lifecycle.phase_reasoning,
        confidence=lifecycle.confidence or "MEDIUM",
        detected_at=lifecycle.detected_at
    )


@router.post("/lifecycle", response_model=LifecyclePhaseResponse)
def classify_lifecycle(
    request: ClassifyLifecycleRequest,
    db: Session = Depends(get_db)
):
    """
    Classify stock into lifecycle phase.
    
    Provide transcript text for AI-based classification.
    
    **WAIT_TIME signals:** delays, no orders, execution problems
    **GOLD_MINE signals:** profitable, record revenue, firing on all cylinders
    """
    try:
        service = GomesIntelligenceService(db)
        lifecycle = service.classify_stock_lifecycle(
            ticker=request.ticker,
            transcript_text=request.transcript_text
        )
        
        return LifecyclePhaseResponse(
            ticker=lifecycle.ticker,
            phase=lifecycle.phase,
            is_investable=lifecycle.is_investable,
            firing_on_all_cylinders=lifecycle.firing_on_all_cylinders,
            cylinders_count=lifecycle.cylinders_count,
            reasoning=lifecycle.phase_reasoning,
            confidence=lifecycle.confidence or "MEDIUM",
            detected_at=lifecycle.detected_at
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# PRICE LINES ENDPOINTS
# ============================================================================

@router.get("/price-lines/{ticker}", response_model=PriceLinesResponse)
def get_price_lines(
    ticker: str,
    db: Session = Depends(get_db)
):
    """
    Get price target lines for a stock.
    
    **Lines:**
    - Green Line: Buy zone (undervalued)
    - Red Line: Sell zone (overvalued)
    - Grey Line: Neutral zone
    
    **Ref:** Minute 35:00 - Price Target Lines
    """
    service = GomesIntelligenceService(db)
    lines = service.get_price_lines(ticker.upper())
    
    if not lines:
        raise HTTPException(
            status_code=404,
            detail=f"No price lines for {ticker}. Use POST /price-lines to set."
        )
    
    # Calculate price zone
    price_zone = None
    if lines.current_price:
        zone, _ = RiskRewardCalculator.get_action_zone(
            float(lines.current_price),
            float(lines.green_line) if lines.green_line else None,
            float(lines.red_line) if lines.red_line else None
        )
        price_zone = zone
    
    return PriceLinesResponse(
        ticker=lines.ticker,
        green_line=float(lines.green_line) if lines.green_line else None,
        red_line=float(lines.red_line) if lines.red_line else None,
        grey_line=float(lines.grey_line) if lines.grey_line else None,
        current_price=float(lines.current_price) if lines.current_price else None,
        is_undervalued=lines.is_undervalued,
        is_overvalued=lines.is_overvalued,
        price_zone=price_zone,
        source=lines.source,
        image_path=lines.image_path
    )


@router.post("/price-lines", response_model=PriceLinesResponse)
def set_price_lines(
    request: SetPriceLinesRequest,
    db: Session = Depends(get_db)
):
    """
    Set price target lines for a stock.
    
    **Rules:**
    - Buy near/below Green Line
    - Sell near/above Red Line
    - Doubling Rule: +100% = sell half
    """
    try:
        service = GomesIntelligenceService(db)
        lines = service.set_price_lines(
            ticker=request.ticker,
            green_line=request.green_line,
            red_line=request.red_line,
            grey_line=request.grey_line,
            current_price=request.current_price,
            source=request.source,
            source_reference=request.source_reference
        )
        
        price_zone = None
        if request.current_price:
            zone, _ = RiskRewardCalculator.get_action_zone(
                request.current_price,
                request.green_line,
                request.red_line
            )
            price_zone = zone
        
        return PriceLinesResponse(
            ticker=lines.ticker,
            green_line=float(lines.green_line) if lines.green_line else None,
            red_line=float(lines.red_line) if lines.red_line else None,
            grey_line=float(lines.grey_line) if lines.grey_line else None,
            current_price=float(lines.current_price) if lines.current_price else None,
            is_undervalued=lines.is_undervalued,
            is_overvalued=lines.is_overvalued,
            price_zone=price_zone,
            source=lines.source
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/price-lines/import-images", response_model=ImageLinesImportResponse)
def import_price_lines_from_images(db: Session = Depends(get_db)):
    """
    Import price lines from screenshot images.
    
    Loads pre-extracted lines from img/ folder screenshots.
    """
    try:
        service = GomesIntelligenceService(db)
        results = service.load_price_lines_from_images()
        
        return ImageLinesImportResponse(
            imported_count=len(results),
            tickers=[r.ticker for r in results],
            message=f"Successfully imported {len(results)} price lines from images"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# VERDICT ENDPOINTS
# ============================================================================

@router.post("/verdict", response_model=GomesVerdictResponse)
def generate_verdict(
    request: GenerateVerdictRequest,
    db: Session = Depends(get_db)
):
    """
    Generate complete investment verdict for a stock.
    
    **THE GATEKEEPER** - Synthesizes ALL Gomes rules:
    1. Market Alert constraints
    2. Lifecycle phase filter (WAIT_TIME = BLOCKED)
    3. Earnings 14-day rule
    4. Position tier constraints
    5. Price line analysis
    6. ML prediction integration
    
    **Verdict Types:**
    - STRONG_BUY: Score 9-10, all filters pass
    - BUY: Score 7-8
    - ACCUMULATE: Buy on dips
    - HOLD: Keep position
    - TRIM: Reduce position
    - SELL: Exit
    - AVOID: Don't enter
    - BLOCKED: Failed Gomes filter
    """
    try:
        service = GomesIntelligenceService(db)
        verdict = service.generate_verdict(
            ticker=request.ticker,
            gomes_score=request.gomes_score,
            current_price=request.current_price,
            earnings_date=request.earnings_date,
            transcript_text=request.transcript_text,
            force_ml_refresh=request.force_ml_refresh
        )
        
        return _verdict_to_response(verdict)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/verdict/{ticker}", response_model=GomesVerdictResponse)
def get_verdict(
    ticker: str,
    current_price: float | None = Query(None, description="Current market price"),
    db: Session = Depends(get_db)
):
    """
    Get investment verdict for a stock (simple GET).
    
    Uses stored data from database. Optionally provide current price.
    """
    try:
        service = GomesIntelligenceService(db)
        verdict = service.generate_verdict(
            ticker=ticker,
            current_price=current_price
        )
        
        return _verdict_to_response(verdict)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# SCAN ENDPOINTS
# ============================================================================

@router.post("/scan", response_model=WatchlistScanResponse)
def scan_watchlist(
    request: ScanWatchlistRequest,
    db: Session = Depends(get_db)
):
    """
    Scan entire watchlist and generate verdicts.
    
    Returns ranked list of opportunities with passed/blocked status.
    
    **Use Case:** Daily morning scan for top setups.
    """
    try:
        service = GomesIntelligenceService(db)
        
        # Get market alert
        market_alert = service.get_current_market_alert()
        
        # Scan watchlist
        verdicts = service.scan_watchlist(
            min_score=request.min_score,
            limit=request.limit
        )
        
        # Get blocked stocks
        blocked = service.get_blocked_stocks()
        
        # Count stats
        passed_count = len([v for v in verdicts if v.passed_gomes_filter])
        blocked_count = len(blocked)
        
        return WatchlistScanResponse(
            total_scanned=len(verdicts) + blocked_count,
            passed_filter=passed_count,
            blocked=blocked_count,
            top_opportunities=[_verdict_to_response(v) for v in verdicts],
            blocked_stocks=blocked,
            market_alert=market_alert.value,
            scan_timestamp=datetime.now()
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/top-opportunities", response_model=list[dict])
def get_top_opportunities(
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """
    Get top investment opportunities (passed filter, highest score).
    
    Quick endpoint for dashboard widget.
    """
    try:
        service = GomesIntelligenceService(db)
        return service.get_top_opportunities(limit=limit)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/blocked", response_model=list[dict])
def get_blocked_stocks(db: Session = Depends(get_db)):
    """
    Get list of stocks blocked by Gomes filter.
    
    These stocks should NOT be invested in regardless of other signals.
    """
    try:
        service = GomesIntelligenceService(db)
        return service.get_blocked_stocks()
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# POSITION SIZING ENDPOINTS
# ============================================================================

@router.post("/position-size", response_model=PositionSizeResponse)
def calculate_position_size(
    request: CalculatePositionRequest,
    db: Session = Depends(get_db)
):
    """
    Calculate recommended position size for a stock.
    
    **Tiers (Ref: Minute 50:00):**
    - PRIMARY: 10% max (proven Gold Mine)
    - SECONDARY: 5% max (Great Find)
    - TERTIARY: 2% max (speculative)
    
    **Alert Constraints:**
    - YELLOW: No TERTIARY positions
    - ORANGE: Only PRIMARY (reduced 50%)
    - RED: No new positions
    """
    try:
        service = GomesIntelligenceService(db)
        
        # Get lifecycle and market alert
        lifecycle = service.get_stock_lifecycle(request.ticker)
        market_alert = service.get_current_market_alert()
        
        # Determine tier
        lifecycle_phase = None
        if lifecycle:
            from app.trading.gomes_logic import LifecyclePhase
            lifecycle_phase = LifecyclePhase(lifecycle.phase)
        
        # Get stock score
        from app.models.stock import Stock
        stock = (
            service.db.query(Stock)
            .filter(Stock.ticker == request.ticker.upper())
            .filter(Stock.is_latest == True)
            .first()
        )
        gomes_score = stock.gomes_score if stock else 5
        
        # Calculate tier and limits
        tier = PositionSizingEngine.determine_tier(
            lifecycle_phase=lifecycle_phase or LifecyclePhase.UNKNOWN,
            gomes_score=gomes_score
        )
        
        limit = PositionSizingEngine.get_position_limit(tier, request.ticker)
        limit = PositionSizingEngine.adjust_for_market_alert(limit, market_alert)
        
        return PositionSizeResponse(
            ticker=request.ticker.upper(),
            tier=tier.value,
            max_portfolio_pct=limit.max_portfolio_pct,
            recommended_pct=limit.recommended_pct,
            allowed_at_current_alert=limit.max_portfolio_pct > 0,
            current_alert=market_alert.value,
            reasoning=limit.reasoning
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ML STOCKS LIST ENDPOINT
# ============================================================================

@router.get("/ml-stocks", response_model=GomesStocksListResponse)
def get_ml_stocks_list(db: Session = Depends(get_db)):
    """
    Get all Gomes stocks with price lines for ML prediction page.
    
    Returns list of stocks from Gomes videos with:
    - Gomes score and sentiment
    - Green/Red price lines
    - Current ML prediction status
    - Lifecycle phase
    
    **Use Case:** ML Prediction page with stock list and chart detail.
    """
    try:
        service = GomesIntelligenceService(db)
        
        # Get market alert
        market_alert = service.get_current_market_alert()
        
        # Get stocks with lines
        stocks_data = service.get_gomes_stocks_with_lines()
        
        # Convert to response models
        stocks = [
            GomesStockItem(
                ticker=s["ticker"],
                company_name=s.get("company_name"),
                gomes_score=s.get("gomes_score"),
                sentiment=s.get("sentiment"),
                action_verdict=s.get("action_verdict"),
                lifecycle_phase=s.get("lifecycle_phase"),
                green_line=s.get("green_line"),
                red_line=s.get("red_line"),
                current_price=s.get("current_price"),
                price_zone=s.get("price_zone"),
                price_position_pct=s.get("price_position_pct"),
                has_ml_prediction=s.get("has_ml_prediction", False),
                ml_direction=s.get("ml_direction"),
                ml_confidence=s.get("ml_confidence"),
                video_date=s.get("video_date"),
                notes=s.get("notes"),
            )
            for s in stocks_data
        ]
        
        return GomesStocksListResponse(
            stocks=stocks,
            total_count=len(stocks),
            stocks_with_lines=len([s for s in stocks if s.green_line or s.red_line]),
            stocks_with_ml=len([s for s in stocks if s.has_ml_prediction]),
            market_alert=market_alert.value
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# DASHBOARD ENDPOINT
# ============================================================================

@router.get("/dashboard", response_model=GomesDashboardResponse)
def get_dashboard(db: Session = Depends(get_db)):
    """
    Get complete Gomes Intelligence dashboard.
    
    Combines all data for frontend display:
    - Current market alert and allocation
    - Top opportunities
    - Blocked stocks
    - Statistics
    """
    try:
        service = GomesIntelligenceService(db)
        
        # Market alert
        market_alert = service.get_current_market_alert()
        allocation = service.get_market_allocation()
        
        # Top opportunities
        opportunities = service.get_top_opportunities(limit=10)
        
        # Blocked stocks
        blocked = service.get_blocked_stocks()
        
        # Statistics (from watchlist)
        from app.models.trading import ActiveWatchlist
        from sqlalchemy import func
        
        total = service.db.query(func.count(ActiveWatchlist.id)).filter(ActiveWatchlist.is_active == True).scalar() or 0
        avg_score = service.db.query(func.avg(ActiveWatchlist.gomes_score)).filter(ActiveWatchlist.is_active == True).scalar() or 0
        
        return GomesDashboardResponse(
            market_alert=MarketAlertResponse(
                alert_level=market_alert.value,
                stocks_pct=allocation.stocks_pct,
                cash_pct=allocation.cash_pct,
                hedge_pct=allocation.hedge_pct,
                hedge_ticker=allocation.hedge_ticker,
                reason="Current state",
                effective_from=datetime.now()
            ),
            recommended_allocation={
                "stocks": allocation.stocks_pct,
                "cash": allocation.cash_pct,
                "hedge": allocation.hedge_pct
            },
            top_opportunities=[],  # Would need conversion
            blocked_count=len(blocked),
            blocked_stocks=blocked,
            total_watchlist=total,
            investable_count=total - len(blocked),
            avg_gomes_score=float(avg_score),
            last_updated=datetime.now()
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
