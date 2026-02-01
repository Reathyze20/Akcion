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
        - Message: "Weinstein Stage 4: Don't catch a falling knife."
    
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
        
        # RULE C: Weinstein Stage 4 (price below falling 30 WMA)
        # Infer from current_price vs green_line (proxy for 30 WMA)
        if (
            stock.current_price is not None and
            stock.green_line is not None and
            stock.inflection_status == 'WAIT_TIME' and
            stock.current_price < stock.green_line * 0.95  # 5% buffer
        ):
            percent_below = ((stock.green_line - stock.current_price) / stock.green_line * 100)
            logger.warning(f"📉 ORDER BLOCKED: {ticker} - Weinstein Stage 4 ({percent_below:.1f}% below support)")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": "WEINSTEIN_STAGE_4",
                    "message": f"Gomes Rule Violation: Weinstein Stage 4. Price is {percent_below:.1f}% below support. Don't catch a falling knife.",
                    "ticker": ticker,
                    "action": action,
                    "current_price": stock.current_price,
                    "support_level": stock.green_line,
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
