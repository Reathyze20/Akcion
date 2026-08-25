"""
Portfolio API Routes

FastAPI endpoints for managing user portfolios and positions.
Supports CSV imports from Trading 212, Degiro, and XTB.

Clean Code Principles Applied:
- Single Responsibility: Each endpoint handles one operation
- Type hints throughout
- Explicit logging instead of print statements
"""

from __future__ import annotations

import logging
import math
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..database.connection import get_db
from ..models.portfolio import (
    BrokerType,
    MarketStatus,
    MarketStatusEnum,
    Portfolio,
    Position,
    InvestmentLog,
    InvestmentLogType,
)
from ..schemas.portfolio import (
    CSVUploadResponse,
    TradeRequest,
    TradeResponse,
    MarketStatusResponse,
    MarketStatusUpdate,
    PortfolioCreate,
    PortfolioResponse,
    PortfolioSummaryResponse,
    PositionCreate,
    PositionResponse,
    PositionUpdate,
    PriceRefreshRequest,
    PriceRefreshResponse,
)
from ..services.currency import CurrencyError, CurrencyService
from ..services.importer import BrokerCSVParser, validate_position_data
from ..services import market_catalyst
from ..services.market_data import MarketDataService
from ..services.portfolio_reconciliation import PortfolioReconciliationService


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("/portfolios", response_model=list[PortfolioResponse])
def get_portfolios(
    owner: str | None = None,
    db: Session = Depends(get_db),
) -> list[PortfolioResponse]:
    """Get all portfolios, optionally filtered by owner."""
    query = db.query(Portfolio)
    
    if owner:
        query = query.filter(Portfolio.owner == owner)
    
    # Explicit order, not whatever the planner returns. The frontend picks a
    # default with portfolios[0]; with two owners in the table an unordered
    # query makes "whose portfolio is this" depend on the query plan.
    portfolios = query.order_by(Portfolio.id).all()
    
    result = []
    for portfolio in portfolios:
        # Stejné pravidlo jako v get_portfolio_summary: prodaná pozice se
        # nepočítá mezi držené.
        positions = (
            db.query(Position)
            .filter(Position.portfolio_id == portfolio.id, Position.shares_count > 0)
            .all()
        )
        valid_values = [
            pos.market_value for pos in positions 
            if not math.isnan(pos.market_value) and not math.isinf(pos.market_value)
        ]
        total_value = sum(valid_values) if valid_values else 0.0
        
        result.append({
            **portfolio.__dict__,
            "position_count": len(positions),
            "total_value": total_value,
            # Bez `or 20000.0`: nula je odpověď („tenhle účet nepřispívá"),
            # ne chybějící údaj, který se má čím doplnit.
            "monthly_contribution": portfolio.monthly_contribution,
        })
    
    return result


@router.post("/portfolios", response_model=PortfolioResponse)
def create_portfolio(
    portfolio: PortfolioCreate,
    db: Session = Depends(get_db),
) -> PortfolioResponse:
    """Create a new portfolio."""
    db_portfolio = Portfolio(**portfolio.model_dump())
    db.add(db_portfolio)
    db.commit()
    db.refresh(db_portfolio)
    
    return {
        **db_portfolio.__dict__,
        "position_count": 0,
        "total_value": 0.0,
    }


@router.get("/portfolios/{portfolio_id}", response_model=PortfolioSummaryResponse)
def get_portfolio_summary(
    portfolio_id: int,
    db: Session = Depends(get_db),
) -> PortfolioSummaryResponse:
    """Get portfolio with all positions and summary stats (totals converted to CZK)."""
    portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    
    # Zero shares means the position is closed, not held. The row stays in the
    # database — `record_trade` zeroes `shares_count` rather than deleting, so
    # `avg_cost` and the ledger link survive — but a holdings view must not
    # list something nobody owns. Without this a sold position lingers at 0 %
    # weight and keeps inflating the position count.
    positions = (
        db.query(Position)
        .filter(Position.portfolio_id == portfolio_id, Position.shares_count > 0)
        .all()
    )

    # Calculate summary stats with currency conversion to CZK
    total_cost_basis_czk = 0.0
    total_market_value_czk = 0.0
    total_unrealized_pl_czk = 0.0
    
    # Positions whose currency we cannot convert. Left out of the totals and
    # named in the response — the old code passed an unknown currency through
    # to a default of the USD rate, which silently valued an ILS holding at
    # 3.3x its worth.
    unconvertible: list[dict[str, str]] = []

    for pos in positions:
        currency = getattr(pos, "currency", None) or "USD"
        try:
            rate = CurrencyService.get_rate_to_czk(currency)
        except CurrencyError as e:
            unconvertible.append({"ticker": pos.ticker, "currency": currency,
                                  "reason": str(e)})
            continue

        cost_basis = pos.cost_basis
        market_value = pos.market_value
        unrealized_pl = pos.unrealized_pl

        # Only add valid values. None = unknown cost (user hasn't filled the
        # buy price yet) — excluded from totals, flagged on the position row.
        if cost_basis is not None and not math.isnan(cost_basis) and not math.isinf(cost_basis):
            total_cost_basis_czk += cost_basis * rate
        if not math.isnan(market_value) and not math.isinf(market_value):
            total_market_value_czk += market_value * rate
        if unrealized_pl is not None and not math.isnan(unrealized_pl) and not math.isinf(unrealized_pl):
            total_unrealized_pl_czk += unrealized_pl * rate
    
    total_unrealized_pl_percent = (
        (total_unrealized_pl_czk / total_cost_basis_czk * 100) if total_cost_basis_czk > 0 else 0.0
    )
    
    # Get last update time
    last_update = None
    for pos in positions:
        if pos.last_price_update:
            if last_update is None or pos.last_price_update > last_update:
                last_update = pos.last_price_update
    
    return {
        "portfolio": {
            **portfolio.__dict__,
            "position_count": len(positions),
            "total_value": total_market_value_czk  # Market value only, cash separate
        },
        "positions": positions,
        "total_cost_basis": total_cost_basis_czk,
        "total_market_value": total_market_value_czk,
        "total_unrealized_pl": total_unrealized_pl_czk,
        "total_unrealized_pl_percent": total_unrealized_pl_percent,
        "cash_balance": portfolio.cash_balance,
        "last_price_update": last_update,
        # Non-empty means the totals above are incomplete, and by how much is
        # not knowable — say so rather than presenting a partial sum as whole.
        "unconvertible_positions": unconvertible,
    }



@router.delete("/portfolios/{portfolio_id}")
def delete_portfolio(
    portfolio_id: int,
    db: Session = Depends(get_db)
):
    """Delete a portfolio and all its positions"""
    portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    
    db.delete(portfolio)
    db.commit()
    
    return {"success": True, "message": "Portfolio deleted"}


# ==============================================================================
# Manual Position Management
# ==============================================================================

from pydantic import BaseModel, Field

class AddPositionRequest(BaseModel):
    """Request model for manually adding a position."""
    ticker: str = Field(..., min_length=1, max_length=20)
    shares_count: float = Field(..., gt=0)
    avg_cost: float = Field(..., gt=0)
    current_price: float | None = Field(None, gt=0)
    company_name: str | None = None


@router.post("/portfolios/{portfolio_id}/positions")
def add_position(
    portfolio_id: int,
    position_data: AddPositionRequest,
    db: Session = Depends(get_db)
):
    """
    Manually add a position to a portfolio.
    
    If position with same ticker exists, it will be updated (averaged).
    """
    portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    
    ticker = position_data.ticker.upper()
    current_price = position_data.current_price or position_data.avg_cost
    
    # Check if position already exists
    existing = db.query(Position).filter(
        Position.portfolio_id == portfolio_id,
        Position.ticker == ticker
    ).first()
    
    if existing:
        # Update existing - average the cost
        total_shares = existing.shares_count + position_data.shares_count
        if existing.avg_cost is None:
            # Old cost unknown: a combined average is unknowable — keep it
            # unknown rather than invent one (user must fill the real cost).
            existing.shares_count = total_shares
        else:
            total_cost = (existing.shares_count * existing.avg_cost) + (position_data.shares_count * position_data.avg_cost)
            existing.shares_count = total_shares
            existing.avg_cost = total_cost / total_shares
        existing.current_price = current_price
        # cost_basis / market_value / unrealized_pl are computed properties
        # on the model — never assigned.

        db.commit()
        db.refresh(existing)
        
        return {
            "success": True,
            "action": "updated",
            "position": {
                "id": existing.id,
                "ticker": existing.ticker,
                "shares_count": existing.shares_count,
                "avg_cost": existing.avg_cost,
                "current_price": existing.current_price,
                "market_value": existing.market_value,
            }
        }
    else:
        # Create new position (cost_basis / P&L are computed properties)
        new_position = Position(
            portfolio_id=portfolio_id,
            ticker=ticker,
            company_name=position_data.company_name,
            shares_count=position_data.shares_count,
            avg_cost=position_data.avg_cost,
            current_price=current_price,
            currency='USD',
        )
        
        db.add(new_position)
        db.commit()
        db.refresh(new_position)
        
        return {
            "success": True,
            "action": "created",
            "position": {
                "id": new_position.id,
                "ticker": new_position.ticker,
                "shares_count": new_position.shares_count,
                "avg_cost": new_position.avg_cost,
                "current_price": new_position.current_price,
                "market_value": new_position.market_value,
            }
        }


@router.delete("/portfolios/{portfolio_id}/positions/{ticker}")
def delete_position(
    portfolio_id: int,
    ticker: str,
    db: Session = Depends(get_db)
):
    """
    Delete a position from portfolio.
    
    Automatically adds ticker to watchlist if not already present,
    allowing continued monitoring after sale.
    """
    position = db.query(Position).filter(
        Position.portfolio_id == portfolio_id,
        Position.ticker == ticker.upper()
    ).first()
    
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")
    
    ticker_upper = ticker.upper()
    
    # Check if ticker is in watchlist
    from ..models.trading import ActiveWatchlist
    from ..models.stock import Stock
    
    watchlist_item = db.query(ActiveWatchlist).filter(
        ActiveWatchlist.ticker == ticker_upper
    ).first()
    
    # If not in watchlist, add it
    if not watchlist_item:
        # Get latest stock data
        stock = db.query(Stock).filter(
            Stock.ticker == ticker_upper,
            Stock.is_latest == True
        ).first()
        
        new_watchlist = ActiveWatchlist(
            ticker=ticker_upper,
            stock_id=stock.id if stock else None,
            action_verdict=stock.action_verdict if stock else "WATCH",
            conviction_score=stock.conviction_score if stock else None,
            investment_thesis=stock.edge if stock else None,
            risks=stock.risks if stock else None,
            is_active=True,
            notes=f"Auto-added after selling position from portfolio {portfolio_id}"
        )
        db.add(new_watchlist)
    else:
        # Ensure watchlist item is active
        watchlist_item.is_active = True
        watchlist_item.notes = f"Position sold, continuing to monitor (portfolio {portfolio_id})"
    
    # Delete the position
    db.delete(position)
    db.commit()
    
    return {
        "success": True,
        "message": f"Position {ticker_upper} deleted",
        "added_to_watchlist": watchlist_item is None
    }


@router.put("/portfolios/{portfolio_id}/cash-balance")
def update_cash_balance(
    portfolio_id: int,
    cash_balance: float,
    db: Session = Depends(get_db)
):
    """Update cash balance for a portfolio"""
    portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    
    if cash_balance < 0:
        raise HTTPException(status_code=400, detail="Cash balance cannot be negative")
    
    portfolio.cash_balance = cash_balance
    db.commit()
    db.refresh(portfolio)
    
    return {"success": True, "cash_balance": portfolio.cash_balance}


@router.put("/portfolios/{portfolio_id}/monthly-contribution")
def update_monthly_contribution(
    portfolio_id: int,
    monthly_contribution: float,
    db: Session = Depends(get_db)
):
    """Update monthly contribution amount for a portfolio's allocation planning"""
    portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    
    if monthly_contribution < 0:
        raise HTTPException(status_code=400, detail="Monthly contribution cannot be negative")
    
    portfolio.monthly_contribution = monthly_contribution
    db.commit()
    db.refresh(portfolio)
    
    return {
        "success": True, 
        "monthly_contribution": portfolio.monthly_contribution
    }


@router.post("/upload-csv", response_model=CSVUploadResponse)
async def upload_csv(
    portfolio_id: int = Form(...),
    broker: BrokerType = Form(...),
    file: UploadFile = File(...)
):
    """
    Upload CSV file to import positions
    Supports upsert logic - updates existing or creates new positions
    """
    db = next(get_db())
    
    with open('csv_upload.log', 'a') as f:
        f.write(f"\n[{__import__('datetime').datetime.now()}] CSV UPLOAD: portfolio {portfolio_id}, broker {broker}\n")
        f.flush()
    
    try:
        # Check if portfolio exists
        portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
        if not portfolio:
            raise HTTPException(status_code=404, detail="Portfolio not found")
        
        # Read CSV content
        content = await file.read()
        # Try multiple encodings
        csv_content = None
        for encoding in ['utf-8', 'utf-8-sig', 'cp1250', 'iso-8859-2', 'latin-1']:
            try:
                csv_content = content.decode(encoding)
                with open('csv_upload.log', 'a') as f:
                    f.write(f"Successfully decoded with {encoding}\n")
                    f.flush()
                break
            except:
                continue
        
        if csv_content is None:
            return CSVUploadResponse(
                success=False,
                message="Could not decode CSV file with any encoding",
                positions_created=0,
                positions_updated=0,
                errors=["Encoding error"]
            )
        
        with open('csv_upload.log', 'a') as f:
            f.write(f"Read {len(csv_content)} bytes from file\n")
            f.flush()
        
        # Parse CSV based on broker type
        try:
            with open('csv_upload.log', 'a') as f:
                f.write(f"Calling parser for broker {broker}\n")
                f.flush()
            positions_data = BrokerCSVParser.parse_broker_csv(csv_content, broker)
            with open('csv_upload.log', 'a') as f:
                f.write(f"Parser returned {len(positions_data)} positions\n")
                f.flush()
            positions_data = validate_position_data(positions_data)
            with open('csv_upload.log', 'a') as f:
                f.write(f"After validation: {len(positions_data)} positions\n")
                f.flush()
        except ValueError as e:
            with open('csv_upload.log', 'a') as f:
                f.write(f"ERROR: {str(e)}\n")
                f.flush()
            return CSVUploadResponse(
                success=False,
                message=str(e),
                positions_created=0,
                positions_updated=0,
                errors=[str(e)]
            )
        
        created_count = 0
        updated_count = 0
        errors = []
        missing_avg_cost: list[str] = []

        logger.info(f"Processing {len(positions_data)} positions for portfolio {portfolio_id}")

        # Upsert positions
        for pos_data in positions_data:
            try:
                logger.debug(f"Processing position: {pos_data}")
                imported_cost = pos_data.get('avg_cost')  # None for Degiro (no buy price in export)
                imported_price = pos_data.get('current_price')

                # Check if position already exists
                existing_pos = db.query(Position).filter(
                    Position.portfolio_id == portfolio_id,
                    Position.ticker == pos_data['ticker']
                ).first()

                if existing_pos:
                    # Update existing position. NEVER overwrite a known
                    # purchase price with nothing — a Degiro re-import must
                    # not erase the cost the user filled in by hand.
                    existing_pos.shares_count = pos_data['shares_count']
                    if imported_cost is not None:
                        existing_pos.avg_cost = imported_cost
                    if imported_price is not None:
                        existing_pos.current_price = imported_price
                        existing_pos.last_price_update = datetime.utcnow()
                    if 'currency' in pos_data:
                        existing_pos.currency = pos_data['currency']
                    # Update company name if provided and not already set
                    if pos_data.get('company_name') and not existing_pos.company_name:
                        existing_pos.company_name = pos_data['company_name']
                    if existing_pos.avg_cost is None:
                        missing_avg_cost.append(existing_pos.ticker)
                    updated_count += 1
                else:
                    # Get company name from CSV data first, fallback to API
                    company_name = pos_data.get('company_name')
                    if not company_name:
                        try:
                            stock_info = MarketDataService.get_stock_info(pos_data['ticker'])
                            if stock_info:
                                company_name = stock_info.get('company_name')
                        except Exception as e:
                            logger.debug(f"Could not fetch company name for {pos_data['ticker']}: {e}")

                    # avg_cost stays None when the broker export has no buy
                    # price (Degiro) — the user fills it in; it is NEVER
                    # faked from the closing price.
                    new_pos = Position(
                        portfolio_id=portfolio_id,
                        ticker=pos_data['ticker'],
                        company_name=company_name,
                        shares_count=pos_data['shares_count'],
                        avg_cost=imported_cost,
                        current_price=imported_price if imported_price is not None else imported_cost,
                        last_price_update=datetime.utcnow() if imported_price is not None else None,
                        currency=pos_data.get('currency', 'USD')
                    )
                    db.add(new_pos)
                    if imported_cost is None:
                        missing_avg_cost.append(pos_data['ticker'])
                    created_count += 1
                    logger.info(f"Created position: {pos_data['ticker']}")

            except Exception as e:
                logger.error(f"Error processing {pos_data.get('ticker', 'unknown')}: {str(e)}")
                errors.append(f"Error processing {pos_data.get('ticker', 'unknown')}: {str(e)}")

        db.commit()
        logger.info(f"Committed {created_count} new, {updated_count} updated positions")
        
        # Automatically refresh prices after successful upload
        refresh_result = {"updated_count": 0, "failed_count": 0}
        try:
            refresh_result = MarketDataService.refresh_portfolio_prices(db, portfolio_id)
            print(f"🔄 Auto-refreshed prices: {refresh_result['updated_count']} updated, {refresh_result['failed_count']} failed")
        except Exception as e:
            print(f"Warning: Could not auto-refresh prices: {e}")
            # Don't fail the upload if price refresh fails
        
        missing_avg_cost = sorted(set(missing_avg_cost))
        message = (
            f"Imported {created_count + updated_count} positions. "
            f"Prices updated: {refresh_result['updated_count']}, Failed: {refresh_result['failed_count']}"
        )
        if missing_avg_cost:
            message += (
                f" · ⚠️ {len(missing_avg_cost)} pozic bez nákupní ceny "
                f"({', '.join(missing_avg_cost)}) — doplň je v detailu pozice"
            )

        return CSVUploadResponse(
            success=True,
            message=message,
            positions_created=created_count,
            positions_updated=updated_count,
            errors=errors,
            missing_avg_cost=missing_avg_cost,
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload-csv-smart")
async def upload_csv_with_reconciliation(
    portfolio_id: int = Form(...),
    broker: BrokerType = Form(...),
    file: UploadFile = File(...),
    detect_sales: bool = Form(default=True),
):
    """
    Smart CSV upload with automatic reconciliation.
    
    This endpoint implements the "Sync Logic":
    - Detects sold positions when they're missing in new import
    - Automatically moves sold positions to Active Watchlist
    - Preserves all thesis data and history
    - Tracks changes in investment log
    - Returns detailed notifications about changes
    
    Args:
        portfolio_id: Target portfolio ID
        broker: Broker type for CSV parsing
        file: CSV file from broker
        detect_sales: If True, missing positions are marked as sold
    """
    db = next(get_db())
    
    try:
        # Check if portfolio exists
        portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
        if not portfolio:
            raise HTTPException(status_code=404, detail="Portfolio not found")
        
        # Read and decode CSV content
        content = await file.read()
        csv_content = None
        for encoding in ['utf-8', 'utf-8-sig', 'cp1250', 'iso-8859-2', 'latin-1']:
            try:
                csv_content = content.decode(encoding)
                break
            except:
                continue
        
        if csv_content is None:
            raise HTTPException(
                status_code=400, 
                detail="Could not decode CSV file with any supported encoding"
            )
        
        # Parse CSV based on broker type
        try:
            positions_data = BrokerCSVParser.parse_broker_csv(csv_content, broker)
            positions_data = validate_position_data(positions_data)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        
        if not positions_data:
            raise HTTPException(
                status_code=400, 
                detail="No valid positions found in CSV file"
            )
        
        logger.info(f"Smart upload: {len(positions_data)} positions for portfolio {portfolio_id}")
        
        # Use reconciliation service
        reconciliation_service = PortfolioReconciliationService(db)
        
        # Preview what will happen
        preview = reconciliation_service.preview_reconciliation(
            portfolio_id=portfolio_id,
            new_positions=positions_data
        )
        
        # Execute reconciliation
        result = reconciliation_service.reconcile_import(
            portfolio_id=portfolio_id,
            new_positions=positions_data,
            broker_type=broker
        )
        
        # Automatically refresh prices after successful upload
        refresh_result = {"updated_count": 0, "failed_count": 0}
        try:
            refresh_result = MarketDataService.refresh_portfolio_prices(db, portfolio_id)
            logger.info(f"Auto-refreshed prices: {refresh_result['updated_count']} updated")
        except Exception as e:
            logger.warning(f"Could not auto-refresh prices: {e}")
        
        return {
            "success": True,
            "portfolio": result.portfolio_name,
            "summary": result.summary(),
            "positions_before": result.total_positions_before,
            "positions_after": result.total_positions_after,
            "changes": {
                "added": result.new_positions,
                "updated": result.updated_positions,
                "sold": result.sales_detected,
            },
            "notifications": result.notifications,
            "price_refresh": {
                "updated": refresh_result.get('updated_count', 0),
                "failed": refresh_result.get('failed_count', 0)
            }
        }
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Smart CSV upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/refresh", response_model=PriceRefreshResponse)
def refresh_prices(
    request: PriceRefreshRequest,
    force_refresh: bool = False,
    db: Session = Depends(get_db)
):
    """
    Refresh current prices for all positions in portfolio(s)
    Uses DB cache - only fetches stale prices (>24h) unless force_refresh=true
    """
    try:
        result = MarketDataService.refresh_portfolio_prices(
            db, 
            request.portfolio_id,
            force_refresh=force_refresh
        )
        
        # If using cache, return success
        if result.get('cached_count', 0) > 0 and result['updated_count'] == 0:
            return PriceRefreshResponse(
                success=True,
                message=result.get('message', 'Using cached prices'),
                **result
            )
        
        # If all updates failed AND there are no cached prices, provide helpful message
        if result['updated_count'] == 0 and result['failed_count'] > 0 and result.get('cached_count', 0) == 0:
            raise HTTPException(
                status_code=503, 
                detail=f"Unable to fetch initial prices from Yahoo Finance (rate limited). Tried {result['failed_count']} tickers. Please try again in a few minutes."
            )
        
        # Partial failure - some prices updated or cached
        return PriceRefreshResponse(
            success=True,
            message=f"Updated {result['updated_count']} prices, using {result.get('cached_count', 0)} cached, {result['failed_count']} failed",
            **result
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/positions", response_model=List[PositionResponse])
def get_positions(
    portfolio_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get all positions, optionally filtered by portfolio"""
    query = db.query(Position)
    
    if portfolio_id:
        query = query.filter(Position.portfolio_id == portfolio_id)
    
    positions = query.all()
    return positions


@router.post("/positions", response_model=PositionResponse)
def create_position(
    position: PositionCreate,
    db: Session = Depends(get_db)
):
    """Create a new position manually"""
    # Check if position already exists
    existing = db.query(Position).filter(
        Position.portfolio_id == position.portfolio_id,
        Position.ticker == position.ticker
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Position already exists for this ticker")
    
    db_position = Position(**position.model_dump())
    db.add(db_position)
    db.commit()
    db.refresh(db_position)
    
    return db_position


@router.put("/positions/{position_id}", response_model=PositionResponse)
def update_position(
    position_id: int,
    position: PositionUpdate,
    db: Session = Depends(get_db)
):
    """Update an existing position"""
    db_position = db.query(Position).filter(Position.id == position_id).first()
    
    if not db_position:
        raise HTTPException(status_code=404, detail="Position not found")
    
    update_data = position.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_position, key, value)
    
    db.commit()
    db.refresh(db_position)
    
    return db_position


def _band_at_trade(db: Session, ticker: str | None) -> dict:
    """
    The valuation in force for `ticker` right now, for stamping onto a trade.

    Read at the moment of the trade rather than looked up later, because the
    analyst moves the Green and Red Lines and a score re-derived next year
    would be measured against a band that did not exist when the money moved.
    That stamped score is what makes the canon's 3-point rule (§5) computable
    at all.

    Returns whatever is known and nothing else. An absent band yields an empty
    dict, the ledger columns stay NULL, and the 3-point rule stays silent for
    that position — which is the correct outcome, not a gap to paper over.
    """
    from ..core.sources import InvestmentSource
    from ..core.tickers import variants_of
    from ..models.gomes import StockLifecycleModel
    from ..models.stock import Stock

    symbols = variants_of(ticker)
    if not symbols:
        return {}

    stock = (
        db.query(Stock)
        .filter(Stock.ticker.in_(symbols))
        .filter(Stock.source_key == InvestmentSource.GOMES.value)
        .filter(Stock.green_line.isnot(None))
        .order_by(desc(Stock.created_at))
        .first()
    )

    lifecycle = (
        db.query(StockLifecycleModel)
        .filter(StockLifecycleModel.ticker.in_(symbols))
        .filter(StockLifecycleModel.valid_until.is_(None))
        .order_by(desc(StockLifecycleModel.detected_at))
        .first()
    )

    return {
        "green_line": stock.green_line if stock else None,
        "red_line": stock.red_line if stock else None,
        # The tracker quotes the US OTC listing, so a band is in dollars even
        # when the position is held on a Canadian exchange.
        "line_currency": "USD" if stock else None,
        "cylinders": lifecycle.cylinders_count if lifecycle else None,
    }


@router.post("/positions/{position_id}/trade", response_model=TradeResponse)
def record_position_trade(
    position_id: int,
    trade: TradeRequest,
    db: Session = Depends(get_db),
):
    """
    Record a BUY/SELL the owner already executed at his broker.

    Writes an immutable `investment_logs` row AND moves the position, in one
    transaction. Before this existed, exits were recorded by overwriting
    `shares_count`, which discarded the sale price — realized P/L was
    unrecoverable and the loss-cooldown guardrail had nothing to read.

    `realized_pl` comes back as null (never 0) when the position's purchase
    price was never known, e.g. a Degiro import predating 2026-07-26.
    """
    from ..services.trade_ledger import TradeError, TradeSide, record_trade

    position_row = db.query(Position).filter(Position.id == position_id).first()
    band = _band_at_trade(db, position_row.ticker if position_row else None)

    try:
        position, log, outcome = record_trade(
            db,
            position_id=position_id,
            side=TradeSide(trade.side),
            shares=trade.shares,
            price=trade.price,
            emotion_tag=trade.emotion_tag,
            note=trade.note,
            trade_date=trade.trade_date,
            green_line=band.get("green_line"),
            red_line=band.get("red_line"),
            cylinders=band.get("cylinders"),
            line_currency=band.get("line_currency"),
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Position not found")
    except TradeError as e:
        # A bad trade is the caller's mistake, not a server fault — say what.
        raise HTTPException(status_code=400, detail=str(e))

    if outcome.realized_pl is None and trade.side == "SELL":
        pl_msg = "realizovaný zisk nelze spočítat — chybí nákupní cena"
    elif trade.side == "SELL":
        pl_msg = f"realizováno {outcome.realized_pl:+.2f} {position.currency or ''}".strip()
    else:
        pl_msg = "pozice navýšena"

    logger.info(
        "Trade recorded via API: position=%s %s %s @ %s",
        position_id, trade.side, trade.shares, trade.price,
    )

    return TradeResponse(
        success=True,
        log_id=log.id,
        ticker=position.ticker,
        side=trade.side,
        shares=trade.shares,
        price=trade.price,
        currency=position.currency,
        gross_amount=outcome.gross_amount,
        realized_pl=outcome.realized_pl,
        cost_basis=outcome.cost_basis,
        new_shares_count=outcome.new_shares,
        new_avg_cost=outcome.new_avg_cost,
        avg_cost_known=outcome.avg_cost_known,
        position_closed=outcome.closes_position,
        message=pl_msg,
    )


@router.delete("/positions/{position_id}")
def delete_position(
    position_id: int,
    db: Session = Depends(get_db)
):
    """Delete a position"""
    position = db.query(Position).filter(Position.id == position_id).first()
    
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")
    
    db.delete(position)
    db.commit()
    
    return {"success": True, "message": "Position deleted"}


@router.delete("/portfolios/{portfolio_id}/positions")
def delete_all_positions(
    portfolio_id: int,
    db: Session = Depends(get_db)
):
    """Delete all positions in a portfolio"""
    # Check if portfolio exists
    portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    
    # Delete all positions
    deleted_count = db.query(Position).filter(Position.portfolio_id == portfolio_id).delete()
    db.commit()
    
    return {"success": True, "message": f"Deleted {deleted_count} positions", "deleted_count": deleted_count}


def _with_catalyst(status: MarketStatus) -> MarketStatusResponse:
    """
    The semafor plus whether the grade it stands on is backed by anything.

    §V3. ORANGE and RED are claims about an identified cause. The verdict is
    computed on read rather than stored, because the interesting part is its
    AGE: a cause recorded during a scare and never revisited keeps the Buy
    Guard refusing every purchase, and nothing in this app lowers the semafor
    on its own. Reading it fresh each time is what makes that visible.
    """
    out = MarketStatusResponse.model_validate(status)
    verdict = market_catalyst.check(
        status.status.value if status.status else None,
        market_catalyst.of_row(status),
    )
    out.catalyst_supported = verdict.supported
    out.catalyst_stale = verdict.stale
    out.catalyst_message_cs = verdict.message_cs or None
    return out


@router.get("/market-status", response_model=MarketStatusResponse)
def get_market_status(db: Session = Depends(get_db)):
    """Get current market status (Traffic Light)"""
    status = db.query(MarketStatus).first()
    
    if not status:
        # Create default GREEN status
        status = MarketStatus(status=MarketStatusEnum.GREEN)
        db.add(status)
        db.commit()
        db.refresh(status)
    
    return _with_catalyst(status)


@router.get("/owners", response_model=List[str])
def get_owners(db: Session = Depends(get_db)):
    """Get list of unique portfolio owners"""
    owners = db.query(Portfolio.owner).distinct().all()
    return [owner[0] for owner in owners]


@router.put("/market-status", response_model=MarketStatusResponse)
def update_market_status(
    update: MarketStatusUpdate,
    db: Session = Depends(get_db)
):
    """Update market status (Traffic Light)"""
    status = db.query(MarketStatus).first()
    
    if not status:
        status = MarketStatus()
        db.add(status)
    
    # §V3. ORANGE and RED say a cause has been identified, so one has to be
    # named. Refused rather than defaulted: an escalation nobody can justify
    # sells most of a portfolio (ORANGE targets 25/35/40), and — worse — it is
    # never undone, because nothing in this app lowers the semafor by itself.
    level = update.status.value if hasattr(update.status, "value") else str(update.status)
    if level in market_catalyst.NEEDS_CAUSE and not (
        update.catalyst_description or status.catalyst_description
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                f"Stupeň {level} znamená pojmenovanou příčinu, ne jen drahý trh. "
                f"Napiš, co se děje (catalyst_description). Samotná drahota je žlutá."
            ),
        )

    status.status = update.status
    if update.note:
        status.note = update.note

    if update.catalyst_description:
        # Re-dated only when the text changes. A cause restated in the same
        # words is the same cause, and restamping it would reset the age that
        # is the only thing making a forgotten alert visible.
        if update.catalyst_description != status.catalyst_description:
            status.catalyst_description = update.catalyst_description
            status.catalyst_identified_at = datetime.utcnow()
        status.catalyst_severity_known = bool(update.catalyst_severity_known)
    elif level not in market_catalyst.NEEDS_CAUSE:
        # Back to GREEN or YELLOW: the cause is over and is cleared with it.
        status.catalyst_description = None
        status.catalyst_identified_at = None
        status.catalyst_severity_known = False

    db.commit()
    db.refresh(status)
    
    return _with_catalyst(status)


# ============================================================================
# KELLY ALLOCATOR ENDPOINTS
# ============================================================================

@router.post("/allocate/{portfolio_id}")
def calculate_allocation(
    portfolio_id: int,
    available_eur: float = 0,
    additional_czk: float = 0,
    db: Session = Depends(get_db)
):
    """
    Calculate optimal allocation using Kelly Criterion.
    
    Based on Gomes scores and current portfolio weights, returns
    recommendations for where to deploy available capital.
    
    Args:
        portfolio_id: Target portfolio
        available_eur: Available EUR to invest
        additional_czk: Additional CZK to invest (e.g., new deposit)
        
    Returns:
        Allocation plan with prioritized recommendations
    """
    from app.services.kelly_allocator import KellyAllocatorService
    
    try:
        allocator = KellyAllocatorService(db)
        plan = allocator.calculate_allocation(
            portfolio_id=portfolio_id,
            available_cash_eur=available_eur,
            additional_cash_czk=additional_czk
        )
        
        return {
            "available_capital_eur": plan.available_capital,
            "available_capital_czk": plan.available_capital_czk,
            "recommendations": [
                {
                    "ticker": r.ticker,
                    "company_name": r.company_name,
                    "conviction_score": r.conviction_score,
                    "current_weight_pct": r.current_weight_pct,
                    "recommended_weight_pct": r.recommended_weight_pct,
                    "recommended_amount_eur": r.recommended_amount,
                    "recommended_amount_czk": r.recommended_amount_czk,
                    "priority": r.priority,
                    "reasoning": r.reasoning,
                }
                for r in plan.recommendations
            ],
            "total_allocated_eur": plan.total_allocated,
            "remaining_cash_eur": plan.remaining_cash,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Allocation calculation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Allocation failed: {e}")


@router.get("/family-audit")
def family_audit(db: Session = Depends(get_db)):
    """
    Detect gaps between family member portfolios.
    
    Compares portfolios of different owners and identifies positions
    that one member has but another doesn't (potential "family gap").
    
    Returns:
        List of family gaps with priority and recommendations
    """
    from app.services.kelly_allocator import KellyAllocatorService
    
    try:
        # Get all portfolios grouped by owner
        portfolios = db.query(Portfolio).order_by(Portfolio.id).all()
        
        if len(portfolios) < 2:
            return {
                "message": "Need at least 2 portfolios for family audit",
                "gaps": []
            }
        
        # Build owner -> portfolio_id mapping (use first portfolio per owner)
        owner_portfolios = {}
        for p in portfolios:
            if p.owner not in owner_portfolios:
                owner_portfolios[p.owner] = p.id
        
        if len(owner_portfolios) < 2:
            return {
                "message": "Need portfolios from different owners for family audit",
                "gaps": []
            }
        
        allocator = KellyAllocatorService(db)
        gaps = allocator.detect_family_gaps(owner_portfolios)
        
        return {
            "owners_analyzed": list(owner_portfolios.keys()),
            "gaps_found": len(gaps),
            "gaps": [
                {
                    "ticker": g.ticker,
                    "company_name": g.company_name,
                    "conviction_score": g.conviction_score,
                    "owner_with_position": g.owner_with_position,
                    "owner_weight_pct": g.owner_weight_pct,
                    "missing_owner": g.missing_owner,
                    "priority": g.priority,
                    "message": g.message,
                }
                for g in gaps
            ]
        }
    except Exception as e:
        logger.error(f"Family audit failed: {e}")
        raise HTTPException(status_code=500, detail=f"Family audit failed: {e}")


# ==============================================================================
# Investment Logs Endpoints (Gamification)
# ==============================================================================

@router.post("/logs")
def create_investment_log(
    log_type: str,
    amount: float = None,
    ticker: str = None,
    shares: float = None,
    price: float = None,
    emotion_tag: str = None,
    note: str = None,
    badge_id: str = None,
    portfolio_id: int = None,
    db: Session = Depends(get_db)
):
    """Create a new investment log entry for gamification/journaling."""
    try:
        log_type_enum = InvestmentLogType(log_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid log type: {log_type}")
    
    log = InvestmentLog(
        portfolio_id=portfolio_id,
        log_type=log_type_enum,
        ticker=ticker,
        amount=amount,
        shares=shares,
        price=price,
        emotion_tag=emotion_tag,
        note=note,
        badge_id=badge_id
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    
    return {
        "success": True,
        "log_id": log.id,
        "message": f"Investment log created: {log_type}"
    }


@router.get("/logs")
def get_investment_logs(
    portfolio_id: int = None,
    log_type: str = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get investment logs with optional filtering."""
    query = db.query(InvestmentLog)
    
    if portfolio_id:
        query = query.filter(InvestmentLog.portfolio_id == portfolio_id)
    if log_type:
        try:
            log_type_enum = InvestmentLogType(log_type)
            query = query.filter(InvestmentLog.log_type == log_type_enum)
        except ValueError:
            pass
    
    logs = query.order_by(InvestmentLog.created_at.desc()).limit(limit).all()
    
    return {
        "logs": [
            {
                "id": log.id,
                "portfolio_id": log.portfolio_id,
                "log_type": log.log_type.value,
                "ticker": log.ticker,
                "amount": log.amount,
                "shares": log.shares,
                "price": log.price,
                "emotion_tag": log.emotion_tag,
                "note": log.note,
                "badge_id": log.badge_id,
                "created_at": log.created_at.isoformat() if log.created_at else None
            }
            for log in logs
        ],
        "count": len(logs)
    }


@router.get("/logs/monthly-summary")
def get_monthly_summary(
    year: int,
    month: int,
    db: Session = Depends(get_db)
):
    """Get monthly investment summary for AI journaling."""
    from datetime import datetime
    from calendar import monthrange
    
    start_date = datetime(year, month, 1)
    _, last_day = monthrange(year, month)
    end_date = datetime(year, month, last_day, 23, 59, 59)
    
    logs = db.query(InvestmentLog).filter(
        InvestmentLog.created_at >= start_date,
        InvestmentLog.created_at <= end_date
    ).order_by(InvestmentLog.created_at).all()
    
    # Aggregate stats
    total_deposits = sum(log.amount or 0 for log in logs if log.log_type == InvestmentLogType.DEPOSIT)
    total_buys = sum(log.amount or 0 for log in logs if log.log_type == InvestmentLogType.BUY)
    total_sells = sum(log.amount or 0 for log in logs if log.log_type == InvestmentLogType.SELL)
    badges_earned = [log.badge_id for log in logs if log.log_type == InvestmentLogType.BADGE and log.badge_id]
    tickers_traded = list(set(log.ticker for log in logs if log.ticker))
    
    return {
        "year": year,
        "month": month,
        "total_deposits": total_deposits,
        "total_buys": total_buys,
        "total_sells": total_sells,
        "net_investment": total_deposits + total_sells - total_buys,
        "badges_earned": badges_earned,
        "tickers_traded": tickers_traded,
        "activity_count": len(logs),
        "logs": [
            {
                "id": log.id,
                "log_type": log.log_type.value,
                "ticker": log.ticker,
                "amount": log.amount,
                "emotion_tag": log.emotion_tag,
                "note": log.note,
                "created_at": log.created_at.isoformat() if log.created_at else None
            }
            for log in logs
        ]
    }


