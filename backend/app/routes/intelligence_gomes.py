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
    AnalyzeTickerRequest,
    AnalyzeTickerResponse,
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
from app.models.stock import Stock
from app.trading.gomes_logic import (
    MarketAlert,
    MarketAlertSystem,
    PositionSizingEngine,
    RiskRewardCalculator,
)
import logging

logger = logging.getLogger(__name__)


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
        
        # Get stock score (Stock already imported at top)
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


# ============================================================================
# TICKER-SPECIFIC ANALYSIS
# ============================================================================

@router.post("/analyze-ticker", response_model=AnalyzeTickerResponse)
async def analyze_ticker_from_transcript(
    request: AnalyzeTickerRequest,
    db: Session = Depends(get_db),
    use_universal_prompt: bool = Query(True, description="Use Universal Intelligence Unit (multi-source support)")
):
    """
    Analyze specific ticker from transcript/video with intelligent source detection.
    
    Supports TWO MODES:
    1. **Universal Intelligence** (use_universal_prompt=True, DEFAULT):
       - Auto-detects source type (OFFICIAL_FILING, CHAT_DISCUSSION, ANALYST_REPORT)
       - Applies different logic per source (100% reliability for filings, 30% for chat)
       - Returns meta_info, sentiment shifts, rumor flags
    
    2. **Legacy Aggressive Mode** (use_universal_prompt=False):
       - Original "Nejasnost = Riziko" prompt
       - Missing Cash → Score capped at 5
       - Missing Catalyst → -2 points
    
    Updates existing stock data in database (not creates new).
    """
    try:
        logger.info(f"=== ANALYZE TICKER START: {request.ticker} ===")
        logger.info(f"Source: {request.source_type}, Universal: {use_universal_prompt}")
        
        if use_universal_prompt:
            from app.core.prompts_universal_intelligence import (
                UNIVERSAL_INTELLIGENCE_PROMPT,
                get_sentiment_alert_level
            )
            prompt_template = UNIVERSAL_INTELLIGENCE_PROMPT
        else:
            from app.core.prompts_ticker_analysis import (
                TICKER_ANALYSIS_PROMPT,
                get_warning_level
            )
            prompt_template = TICKER_ANALYSIS_PROMPT
        
        from app.config.settings import Settings
        import google.generativeai as genai
        import json
        from decimal import Decimal
        from app.models.portfolio import Position
        
        settings = Settings()
        
        # 1. Get existing stock data from database
        stock = db.query(Stock).filter(Stock.ticker == request.ticker).first()
        if not stock:
            logger.error(f"Stock {request.ticker} not found in database")
            raise HTTPException(status_code=404, detail=f"Stock {request.ticker} not found in portfolio")
        
        logger.info(f"Stock found: {stock.ticker}, current score: {stock.gomes_score}")
        
        # Get portfolio position for shares count and weight (if exists)
        position = db.query(Position).filter(Position.ticker == request.ticker).first()
        logger.info(f"Position found: {position is not None}")
        
        # 2. Prepare template variables
        current_price = float(stock.current_price or 0)
        shares_count = float(position.shares_count if position else 0)
        
        # Calculate portfolio weight if position exists
        current_weight = 0.0
        if position and position.portfolio:
            # Get all positions in the portfolio
            all_positions = db.query(Position).filter(Position.portfolio_id == position.portfolio_id).all()
            total_portfolio_value = sum(p.market_value for p in all_positions if p.current_price)
            if total_portfolio_value > 0:
                current_weight = (position.market_value / total_portfolio_value) * 100
        
        last_score = stock.gomes_score or 0
        
        # 3. Format prompt with actual data
        prompt = prompt_template.format(
            ticker=request.ticker,
            input_text=request.input_text[:30000],  # Limit to avoid token overflow
            current_price=current_price,
            shares_count=shares_count,
            current_weight=current_weight,
            last_score=last_score
        )
        
        # 4. Call Gemini API
        logger.info("Calling Gemini API...")
        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        logger.info(f"Gemini response received, length: {len(response_text)}")
        logger.debug(f"Response preview: {response_text[:500]}")
        
        # Extract JSON from markdown code blocks if present
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
        
        # 5. Parse JSON response
        try:
            logger.info("Parsing JSON response...")
            data = json.loads(response_text)
            logger.info(f"JSON parsed successfully, keys: {list(data.keys())}")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini response: {response_text[:500]}")
            raise HTTPException(status_code=500, detail=f"AI returned invalid JSON: {str(e)}")
        
        # 6. Validate and process response based on prompt mode
        if use_universal_prompt:
            # Universal mode - different JSON structure
            required_fields = ["ticker", "meta_info", "inflection_updates", "financial_updates", "score_impact_recommendation"]
            for field in required_fields:
                if field not in data:
                    raise HTTPException(status_code=500, detail=f"AI response missing required field: {field}")
            
            # Extract from nested structure
            meta = data["meta_info"]
            inflection = data["inflection_updates"]
            financial = data["financial_updates"]
            score_data = data["score_impact_recommendation"]
            
            gomes_score = score_data["gomes_score"]
            inflection_status = data.get("inflection_status", "WAIT_TIME")
            thesis_narrative = data.get("thesis_narrative", stock.thesis_narrative or "")
            next_catalyst = inflection.get("potential_catalyst", "NO CATALYST DETECTED")
            cash_runway_status = financial.get("cash_runway_status", "UNCHANGED")
            recommendation = data.get("recommendation", "HOLD")
            
            # Build warning messages based on source type and findings
            warning_msgs = []
            source_type = meta.get("detected_source_type", "UNKNOWN")
            reliability = meta.get("source_reliability", "0%")
            
            if source_type == "CHAT_DISCUSSION":
                warning_msgs.append(f"📢 CHAT DISKUZE - Spolehlivost {reliability}")
                if inflection.get("management_credibility_alert") != "NO_ISSUES":
                    warning_msgs.append(f"⚠️ Management: {inflection['management_credibility_alert']}")
                if "RUMOR" in next_catalyst.upper() or "UNCONFIRMED" in next_catalyst.upper():
                    warning_msgs.append("🔮 RUMOR: Catalyst datum není potvrzený")
            
            if "UNKNOWN - DATA GAP" in cash_runway_status:
                warning_msgs.append("🚨 CHYBÍ FINANČNÍ DATA - Ochranný mechanismus aktivován")
            
            sentiment = inflection.get("thesis_sentiment_shift", "Neutral")
            if sentiment in ["Negative", "Critical Warning"]:
                warning_msgs.append(f"📉 Sentiment shift: {sentiment}")
            
            # LOGICAL VALIDATION: High Score requires Catalyst
            if gomes_score >= 9 and ("NO CATALYST" in next_catalyst.upper() or not next_catalyst.strip()):
                warning_msgs.append("⚠️ LOGICAL ERROR: High Score (9+) but No Catalyst. Score není obhajitelné bez konkrétního katalyzátoru. Doplň ručně (např. 'Q1 High-Grade Sales').")
                logger.warning(f"Logical error detected for {request.ticker}: Score {gomes_score} but catalyst: {next_catalyst}")
            
            # Store meta info in stock raw_notes field
            meta_notes = f"Source: {source_type} ({reliability})\n" + "\n".join(inflection.get("key_takeaways_bullets", []))
            stock.raw_notes = meta_notes[:500]  # Limit length
            
        else:
            # Legacy mode - original flat structure
            required_fields = [
                "ticker", "gomes_score", "inflection_status", "thesis_narrative",
                "next_catalyst", "cash_runway_status", "recommendation"
            ]
            for field in required_fields:
                if field not in data:
                    raise HTTPException(status_code=500, detail=f"AI response missing required field: {field}")
            
            gomes_score = data["gomes_score"]
            inflection_status = data["inflection_status"]
            thesis_narrative = data["thesis_narrative"]
            next_catalyst = data["next_catalyst"]
            cash_runway_status = data["cash_runway_status"]
            recommendation = data["recommendation"]
            
            # Legacy warning messages
            from app.core.prompts_ticker_analysis import WARNING_MESSAGES
            warning_msgs = []
            if "UNKNOWN - DATA GAP" in cash_runway_status:
                warning_msgs.append(WARNING_MESSAGES["UNKNOWN_CASH"])
            if "NO CATALYST DETECTED" in next_catalyst:
                warning_msgs.append(WARNING_MESSAGES["NO_CATALYST"])
            if gomes_score <= 4:
                warning_msgs.append(WARNING_MESSAGES["LOW_SCORE"])
            
            # LOGICAL VALIDATION: High Score requires Catalyst
            if gomes_score >= 9 and ("NO CATALYST" in next_catalyst.upper() or not next_catalyst.strip()):
                warning_msgs.append("⚠️ LOGICAL ERROR: High Score (9+) but No Catalyst. Score není obhajitelné bez konkrétního katalyzátoru. Doplň ručně (např. 'Q1 High-Grade Sales').")
                logger.warning(f"Logical error detected for {request.ticker}: Score {gomes_score} but catalyst: {next_catalyst}")
        
        # 7. Update stock record in database (common for both modes)
        stock.gomes_score = gomes_score
        stock.inflection_status = inflection_status
        stock.thesis_narrative = thesis_narrative
        stock.next_catalyst = next_catalyst
        stock.cash_runway_months = data.get("financial_updates", data).get("cash_runway_months") if use_universal_prompt else data.get("cash_runway_months")
        stock.cash_runway_status = cash_runway_status
        stock.insider_activity = data.get("financial_updates", data).get("insider_activity", "UNKNOWN") if use_universal_prompt else data.get("insider_activity", "UNKNOWN")
        
        # Update price lines if provided
        price_targets = data.get("price_targets", {}) if use_universal_prompt else data
        if price_targets.get("price_floor"):
            stock.price_floor = Decimal(str(price_targets["price_floor"]))
        if price_targets.get("price_base"):
            stock.price_base = Decimal(str(price_targets["price_base"]))
        if price_targets.get("price_moon"):
            stock.price_moon = Decimal(str(price_targets["price_moon"]))
        if price_targets.get("stop_loss_price"):
            stock.stop_loss_price = Decimal(str(price_targets["stop_loss_price"]))
        
        stock.max_allocation_cap = data.get("max_allocation_cap", 10.0)
        stock.last_updated = datetime.utcnow()
        
        db.commit()
        db.refresh(stock)
        
        # 8. Calculate warning level (mode-dependent)
        if use_universal_prompt:
            from app.core.prompts_universal_intelligence import get_sentiment_alert_level
            sentiment = data["inflection_updates"].get("thesis_sentiment_shift", "Neutral")
            source_type = data["meta_info"].get("detected_source_type", "UNKNOWN")
            warning_level = get_sentiment_alert_level(sentiment, source_type)
        else:
            from app.core.prompts_ticker_analysis import get_warning_level
            warning_level = get_warning_level(data)
        
        # 9. Return response (warning_msgs already built above)
        return AnalyzeTickerResponse(
            ticker=stock.ticker,
            warning_level=warning_level,
            gomes_score=stock.gomes_score,
            inflection_status=stock.inflection_status,
            thesis_narrative=stock.thesis_narrative,
            next_catalyst=stock.next_catalyst,
            cash_runway_status=stock.cash_runway_status,
            recommendation=recommendation,
            updated_at=stock.last_updated,
            warning_messages=warning_msgs
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ticker analysis error for {request.ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
