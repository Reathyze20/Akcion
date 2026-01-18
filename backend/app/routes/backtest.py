"""
Backtesting API Routes
======================

Endpoints for running and analyzing backtests.

Author: GitHub Copilot with Claude Sonnet 4.5
Date: 2026-01-17
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.trading.backtest import BacktestEngine, run_backtest


router = APIRouter(prefix="/api/backtest", tags=["Backtesting"])


@router.post("/run/{ticker}")
async def run_ticker_backtest(
    ticker: str,
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    initial_capital: float = Query(100000.0, ge=1000),
    min_confidence: float = Query(60.0, ge=0, le=100),
    db: Session = Depends(get_db),
) -> dict:
    """
    Run backtest for a ticker.
    
    Args:
        ticker: Stock ticker
        start_date: Start date (default: 1 year ago)
        end_date: End date (default: today)
        initial_capital: Starting capital (default: $100k)
        min_confidence: Minimum buy confidence (default: 60%)
        
    Returns:
        Backtest results with trades and metrics
        
    Example:
        POST /api/backtest/run/AAPL?start_date=2023-01-01&end_date=2024-01-01
    """
    # Parse dates
    if end_date:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        end_dt = datetime.utcnow()
    
    if start_date:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    else:
        start_dt = end_dt - timedelta(days=365)
    
    try:
        result = run_backtest(
            db=db,
            ticker=ticker.upper(),
            start_date=start_dt,
            end_date=end_dt,
            initial_capital=initial_capital,
            min_confidence=min_confidence,
        )
        
        return {
            "strategy_name": result.strategy_name,
            "ticker": ticker.upper(),
            "start_date": result.start_date.isoformat(),
            "end_date": result.end_date.isoformat(),
            "initial_capital": result.initial_capital,
            "final_capital": round(result.final_capital, 2),
            "total_return": round(result.total_return, 2),
            "total_return_dollars": round(result.total_return_dollars, 2),
            "total_trades": result.total_trades,
            "winning_trades": result.winning_trades,
            "losing_trades": result.losing_trades,
            "win_rate": round(result.win_rate, 4),
            "avg_return_per_trade": round(result.avg_return_per_trade, 2),
            "max_drawdown": round(result.max_drawdown, 2),
            "sharpe_ratio": round(result.sharpe_ratio, 2),
            "profit_factor": round(result.profit_factor, 2),
            "trades": [
                {
                    "entry_date": t.entry_date.isoformat(),
                    "entry_price": round(t.entry_price, 2),
                    "exit_date": t.exit_date.isoformat(),
                    "exit_price": round(t.exit_price, 2),
                    "shares": t.shares,
                    "pnl": round(t.pnl, 2),
                    "pnl_pct": round(t.pnl_pct, 2),
                    "hold_days": t.hold_days,
                    "confidence": round(t.signal_confidence, 2),
                    "exit_reason": t.reason,
                }
                for t in result.trades
            ],
        }
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest failed: {e}")


@router.get("/quick-stats/{ticker}")
async def get_quick_backtest_stats(
    ticker: str,
    days_back: int = Query(365, ge=30, le=1095),
    db: Session = Depends(get_db),
) -> dict:
    """
    Get quick backtest statistics without full trade details.
    
    Faster endpoint for dashboard display.
    
    Example:
        GET /api/backtest/quick-stats/AAPL?days_back=365
    """
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days_back)
    
    try:
        result = run_backtest(
            db=db,
            ticker=ticker.upper(),
            start_date=start_date,
            end_date=end_date,
        )
        
        return {
            "ticker": ticker.upper(),
            "period_days": days_back,
            "total_return": round(result.total_return, 2),
            "win_rate": round(result.win_rate, 4),
            "total_trades": result.total_trades,
            "sharpe_ratio": round(result.sharpe_ratio, 2),
            "max_drawdown": round(result.max_drawdown, 2),
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Stats failed: {e}")
