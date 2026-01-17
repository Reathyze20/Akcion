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
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..database.connection import get_db
from ..models.portfolio import (
    BrokerType,
    MarketStatus,
    MarketStatusEnum,
    Portfolio,
    Position,
)
from ..schemas.portfolio import (
    CSVUploadResponse,
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
from ..services.currency import CurrencyService
from ..services.importer import BrokerCSVParser, validate_position_data
from ..services.market_data import MarketDataService


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
    
    portfolios = query.all()
    
    result = []
    for portfolio in portfolios:
        positions = db.query(Position).filter(Position.portfolio_id == portfolio.id).all()
        valid_values = [
            pos.market_value for pos in positions 
            if not math.isnan(pos.market_value) and not math.isinf(pos.market_value)
        ]
        total_value = sum(valid_values) if valid_values else 0.0
        
        result.append({
            **portfolio.__dict__,
            "position_count": len(positions),
            "total_value": total_value,
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
    
    positions = db.query(Position).filter(Position.portfolio_id == portfolio_id).all()
    
    # Calculate summary stats with currency conversion to CZK
    total_cost_basis_czk = 0.0
    total_market_value_czk = 0.0
    total_unrealized_pl_czk = 0.0
    
    for pos in positions:
        currency = getattr(pos, "currency", "USD")
        rate = CurrencyService.get_rate_to_czk(currency)
        
        cost_basis = pos.cost_basis
        market_value = pos.market_value
        unrealized_pl = pos.unrealized_pl
        
        # Only add valid (non-NaN) values
        if not math.isnan(cost_basis) and not math.isinf(cost_basis):
            total_cost_basis_czk += cost_basis * rate
        if not math.isnan(market_value) and not math.isinf(market_value):
            total_market_value_czk += market_value * rate
        if not math.isnan(unrealized_pl) and not math.isinf(unrealized_pl):
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
        "last_price_update": last_update
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
        
        # Upsert positions
        for pos_data in positions_data:
            try:
                # Check if position already exists
                existing_pos = db.query(Position).filter(
                    Position.portfolio_id == portfolio_id,
                    Position.ticker == pos_data['ticker']
                ).first()
                
                if existing_pos:
                    # Update existing position
                    existing_pos.shares_count = pos_data['shares_count']
                    existing_pos.avg_cost = pos_data['avg_cost']
                    if 'currency' in pos_data:
                        existing_pos.currency = pos_data['currency']
                    updated_count += 1
                else:
                    # Create new position and try to get company name
                    company_name = None
                    try:
                        stock_info = MarketDataService.get_stock_info(pos_data['ticker'])
                        if stock_info:
                            company_name = stock_info.get('company_name')
                    except Exception as e:
                        print(f"⚠️ Could not fetch company name for {pos_data['ticker']}: {e}")
                    
                    new_pos = Position(
                        portfolio_id=portfolio_id,
                        ticker=pos_data['ticker'],
                        company_name=company_name,
                        shares_count=pos_data['shares_count'],
                        avg_cost=pos_data['avg_cost'],
                        currency=pos_data.get('currency', 'USD')
                    )
                    db.add(new_pos)
                    created_count += 1
                    
            except Exception as e:
                errors.append(f"Error processing {pos_data.get('ticker', 'unknown')}: {str(e)}")
        
        db.commit()
        
        # Automatically refresh prices after successful upload
        refresh_result = {"updated_count": 0, "failed_count": 0}
        try:
            refresh_result = MarketDataService.refresh_portfolio_prices(db, portfolio_id)
            print(f"🔄 Auto-refreshed prices: {refresh_result['updated_count']} updated, {refresh_result['failed_count']} failed")
        except Exception as e:
            print(f"⚠️ Warning: Could not auto-refresh prices: {e}")
            # Don't fail the upload if price refresh fails
        
        return CSVUploadResponse(
            success=True,
            message=f"Imported {created_count + updated_count} positions. Prices updated: {refresh_result['updated_count']}, Failed: {refresh_result['failed_count']}",
            positions_created=created_count,
            positions_updated=updated_count,
            errors=errors
        )
        
    except Exception as e:
        db.rollback()
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
    
    return status


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
    
    status.status = update.status
    if update.note:
        status.note = update.note
    
    db.commit()
    db.refresh(status)
    
    return status
