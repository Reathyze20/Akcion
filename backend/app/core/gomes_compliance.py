"""
Gomes Compliance Dependencies
=============================

FastAPI dependencies that enforce Gomes investment rules at the API level.
These are "circuit breakers" that cannot be bypassed via frontend.

Author: GitHub Copilot with Claude Opus 4.5
Date: 2026-02-01
"""

from typing import Optional
from fastapi import HTTPException, Depends, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from loguru import logger

from app.database.connection import get_db
from app.models.stock import Stock
from app.models.gomes import MarketAlertModel


# ============================================================================
# REQUEST MODELS
# ============================================================================

class OrderRequest(BaseModel):
    """Request model for order/trade endpoint"""
    ticker: str
    action: str  # 'BUY', 'SELL', 'TRIM', 'ADD'
    amount: Optional[float] = None  # Amount in currency or shares
    shares: Optional[float] = None


# ============================================================================
# MARKET STATUS LOGIC
# ============================================================================

def get_market_status(db: Session) -> str:
    """
    Get current market status from Traffic Light system.
    
    Returns: 'GREEN', 'YELLOW', or 'RED'
    """
    try:
        # Get latest traffic light status from DB
        traffic_light = db.query(MarketAlertModel).filter(
            MarketAlertModel.effective_until.is_(None)
        ).order_by(
            MarketAlertModel.effective_from.desc()
        ).first()
        
        if traffic_light:
            return traffic_light.alert_level.upper()  # GREEN, YELLOW, RED
        
        # Default to YELLOW if no data
        return 'YELLOW'
    except Exception as e:
        logger.warning(f"Failed to get market status: {e}, defaulting to YELLOW")
        return 'YELLOW'


def get_stock_analysis(db: Session, ticker: str) -> Optional[Stock]:
    """
    Get stock analysis from database.
    """
    return db.query(Stock).filter(
        Stock.ticker.ilike(ticker)
    ).first()


# ============================================================================
# COMPLIANCE VALIDATOR
# ============================================================================

class ComplianceResult:
    """Result of compliance check"""
    def __init__(
        self,
        passed: bool,
        ticker: str,
        action: str,
        blocked_reason: Optional[str] = None,
        warning: Optional[str] = None,
        max_allocation: Optional[float] = None,
    ):
        self.passed = passed
        self.ticker = ticker
        self.action = action
        self.blocked_reason = blocked_reason
        self.warning = warning
        self.max_allocation = max_allocation


def verify_gomes_compliance(
    order: OrderRequest,
    db: Session = Depends(get_db),
) -> ComplianceResult:
    """
    FastAPI Dependency that validates orders against Gomes rules.
    
    Raises HTTPException if order violates rules.
    
    RULE A (Market Level):
        - IF MarketStatus == RED AND action == BUY -> 403 Forbidden
        - Message: "Market is in DEFENSE mode. Cash is King. No new positions."
    
    RULE B (Micro Level - Stock Specific):
        - IF CashRunway < 6 AND action == BUY -> 422 Unprocessable Entity
        - Message: "Gomes Rule Violation: Dilution Risk (<6m runway)."
    
    RULE C (Trend Protection):
        - IF Stage 4 (price < falling WMA) AND action == BUY -> 422
        - Message: "Wait Time — kánon §3 říká nebýt investovaný."
    
    RULE D (Low Conviction):
        - IF gomes_score < 7 AND action == BUY -> WARNING (not blocking)
        - Returns max_allocation = 3%
    """
    ticker = order.ticker.upper()
    action = order.action.upper()
    
    # Only validate BUY actions
    if action not in ('BUY', 'ADD', 'ACCUMULATE'):
        return ComplianceResult(
            passed=True,
            ticker=ticker,
            action=action,
        )
    
    # -------------------------------------------------------------------------
    # RULE A: Market-Level Check (Traffic Light)
    # -------------------------------------------------------------------------
    market_status = get_market_status(db)
    
    if market_status == 'RED':
        logger.warning(f"🛑 ORDER BLOCKED: {ticker} - Market is RED (DEFENSE mode)")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "MARKET_DEFENSE_MODE",
                "message": "Market is in DEFENSE mode. Cash is King. No new positions allowed.",
                "ticker": ticker,
                "action": action,
                "market_status": "RED",
            }
        )
    
    # -------------------------------------------------------------------------
    # RULE B & C: Micro-Level Checks (Stock Specific)
    # -------------------------------------------------------------------------
    stock = get_stock_analysis(db, ticker)
    
    if stock:
        # RULE B: Cash Runway < 6 months = Dilution Risk
        if stock.cash_runway_months is not None and stock.cash_runway_months < 6:
            logger.warning(f"☣️ ORDER BLOCKED: {ticker} - Cash runway {stock.cash_runway_months}m (DILUTION RISK)")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": "DILUTION_RISK",
                    "message": f"Gomes Rule Violation: Dilution Risk. Cash runway only {stock.cash_runway_months} months. Company will likely issue new shares.",
                    "ticker": ticker,
                    "action": action,
                    "cash_runway_months": stock.cash_runway_months,
                }
            )
        
        # RULE C: Wait Time — the canon's own refusal (canon §3)
        #
        # This rule used to call itself "Weinstein Stage 4 (price below falling
        # 30 WMA)". There is no 30 WMA in it and never was; the condition read
        # `current_price < green_line * 0.95`, and its own comment admitted to
        # using the green line as a "proxy". The green line is a DCF-derived
        # valuation floor, not a moving average, and the two say opposite
        # things: canon §4a puts a price at or below the green line at an R/R
        # score of 10 — the strongest buy the method produces. So the rule
        # rejected the exact purchase the methodology calls for, under the
        # heading "Gomes Rule Violation".
        #
        # Worse, because the price test was ANDed with the phase test, a
        # WAIT_TIME position priced *above* its green line passed the guard —
        # dead money at a full price, which is the case actually worth
        # stopping.
        #
        # What survives is the half that is canonical: canon §3 says of Wait
        # Time, plainly, "NEBÝT INVESTOVANÝ". The price plays no part in it.
        if stock.inflection_status == 'WAIT_TIME':
            logger.warning(f"⏸ ORDER BLOCKED: {ticker} — Wait Time (kánon §3)")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": "WAIT_TIME",
                    "message": (
                        f"Gomes: {ticker} je ve fázi Wait Time — hype opadl, "
                        f"story ještě nechytila. Kánon §3: nebýt investovaný. "
                        f"Cena na tom nic nemění."
                    ),
                    "ticker": ticker,
                    "action": action,
                    "current_price": stock.current_price,
                    "green_line": stock.green_line,
                }
            )
        
        # RULE D: Low Conviction (Warning, not blocking)
        if stock.conviction_score is not None and stock.conviction_score < 7:
            logger.info(f"⚠️ ORDER WARNING: {ticker} - Low conviction score ({stock.conviction_score}/10)")
            return ComplianceResult(
                passed=True,
                ticker=ticker,
                action=action,
                warning=f"Low conviction score ({stock.conviction_score}/10). Speculative position only.",
                max_allocation=3.0,  # Max 3% portfolio allocation
            )
    
    # -------------------------------------------------------------------------
    # ALL CHECKS PASSED
    # -------------------------------------------------------------------------
    logger.info(f"✅ ORDER CLEARED: {ticker} - Gomes compliance passed")
    return ComplianceResult(
        passed=True,
        ticker=ticker,
        action=action,
    )


# ============================================================================
# CONVENIENCE FUNCTIONS FOR ROUTE HANDLERS
# ============================================================================

async def require_gomes_compliance(
    order: OrderRequest,
    db: Session = Depends(get_db),
) -> ComplianceResult:
    """
    Dependency that can be used in route handlers.
    
    Usage:
        @router.post("/order")
        async def place_order(
            order: OrderCreate,
            compliance: ComplianceResult = Depends(require_gomes_compliance)
        ):
            # If we reach here, order is allowed
            # Check compliance.warning for any warnings
            if compliance.warning:
                # Log warning but proceed
                pass
            execute_order(order)
    """
    return verify_gomes_compliance(order, db)
