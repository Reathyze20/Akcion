"""
Data Access Layer (Repository Pattern)

Provides clean interfaces for database operations.
Separates business logic from SQL queries.

Clean Code Principles Applied:
- Single Responsibility: Each repository handles one entity
- Explicit error handling with typed returns
- Small, focused methods
- Type hints throughout
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import desc
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..models.stock import Stock


logger = logging.getLogger(__name__)


# ==============================================================================
# Constants
# ==============================================================================

DEFAULT_GOMES_SCORE: int = 5
MAX_VERSIONS_TO_KEEP: int = 2
DEFAULT_TIME_HORIZON: str = "Long-term"


# ==============================================================================
# Stock Repository
# ==============================================================================

class StockRepository:
    """
    Repository for Stock entity database operations.
    
    Follows Repository pattern to abstract SQL details from business logic.
    Each method has a single, clear responsibility.
    """
    
    def __init__(self, session: Session) -> None:
        """
        Initialize repository with database session.
        
        Args:
            session: Active SQLAlchemy session
        """
        self._session = session
    
    # ==========================================================================
    # Create Operations
    # ==========================================================================
    
    def create_stocks(
        self,
        stocks: list[dict[str, Any]],
        source_id: str,
        source_type: str,
        speaker: str = "Mark Gomes",
    ) -> tuple[bool, str | None]:
        """
        Save multiple stock analyses to database with upsert logic.
        
        If stock already exists, marks old version as not latest
        and creates new version. Maintains version history.
        
        Args:
            stocks: List of stock dictionaries from AI analysis
            source_id: Identifier of source (video ID, doc ID, etc.)
            source_type: Type of source (YouTube, Google Docs, etc.)
            speaker: Speaker/analyst name
            
        Returns:
            Tuple of (success: bool, error_message: str | None)
        """
        try:
            for stock_data in stocks:
                self._upsert_stock(stock_data, source_type, speaker)
            
            self._session.commit()
            logger.info(f"Saved {len(stocks)} stocks from {source_type}")
            return True, None
            
        except SQLAlchemyError as e:
            self._session.rollback()
            error_msg = f"Database error: {e}"
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            self._session.rollback()
            error_msg = f"Unexpected error: {e}"
            logger.exception(error_msg)
            return False, error_msg
    
    def _upsert_stock(
        self,
        stock_data: dict[str, Any],
        source_type: str,
        speaker: str,
    ) -> None:
        """
        Upsert single stock - create new version or first entry.
        
        Args:
            stock_data: Stock dictionary from AI analysis
            source_type: Source type for attribution
            speaker: Analyst name
        """
        ticker = self._extract_ticker(stock_data)
        if not ticker:
            return
        
        version = self._handle_existing_versions(ticker)
        stock = self._create_stock_entity(stock_data, ticker, source_type, speaker, version)
        self._session.add(stock)
    
    def _extract_ticker(self, stock_data: dict[str, Any]) -> str | None:
        """Extract and normalize ticker from stock data."""
        ticker = stock_data.get("ticker", "")
        return ticker.upper() if ticker else None
    
    def _handle_existing_versions(self, ticker: str) -> int:
        """
        Handle existing versions of a ticker.
        
        Marks existing latest version as not latest and
        removes old versions beyond the retention limit.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            New version number
        """
        existing = self._get_latest_version(ticker)
        
        if existing:
            existing.is_latest = False
            new_version = (existing.version or 1) + 1
            self._cleanup_old_versions(ticker)
        else:
            new_version = 1
        
        return new_version
    
    def _get_latest_version(self, ticker: str) -> Stock | None:
        """Get the current latest version of a ticker."""
        return self._session.query(Stock).filter(
            Stock.ticker == ticker,
            Stock.is_latest == True,
        ).first()
    
    def _cleanup_old_versions(self, ticker: str) -> None:
        """Remove old versions beyond the retention limit."""
        old_versions = (
            self._session.query(Stock)
            .filter(
                Stock.ticker == ticker,
                Stock.is_latest == False,
            )
            .order_by(desc(Stock.created_at))
            .offset(MAX_VERSIONS_TO_KEEP - 1)
            .all()
        )
        for old in old_versions:
            self._session.delete(old)
    
    def _create_stock_entity(
        self,
        stock_data: dict[str, Any],
        ticker: str,
        source_type: str,
        speaker: str,
        version: int,
    ) -> Stock:
        """
        Create Stock entity from dictionary data.
        
        Args:
            stock_data: Raw stock data dictionary
            ticker: Normalized ticker symbol
            source_type: Source attribution
            speaker: Analyst name
            version: Version number for this entry
            
        Returns:
            New Stock entity (not yet added to session)
        """
        return Stock(
            ticker=ticker,
            company_name=stock_data.get("company_name") or stock_data.get("name", ""),
            source_type=source_type,
            speaker=speaker,
            sentiment=stock_data.get("sentiment", "Neutral"),
            gomes_score=stock_data.get("gomes_score") or DEFAULT_GOMES_SCORE,
            conviction_score=(
                stock_data.get("conviction_score")
                or stock_data.get("gomes_score")
                or DEFAULT_GOMES_SCORE
            ),
            price_target=stock_data.get("price_target", ""),
            time_horizon=(
                stock_data.get("time_horizon")
                or stock_data.get("horizon")
                or DEFAULT_TIME_HORIZON
            ),
            edge=stock_data.get("edge", ""),
            catalysts=stock_data.get("catalysts", ""),
            risks=stock_data.get("risks", ""),
            raw_notes=(
                stock_data.get("note")
                or stock_data.get("status")
                or stock_data.get("raw_notes", "")
            ),
            # Trading action fields
            action_verdict=stock_data.get("action_verdict"),
            entry_zone=stock_data.get("entry_zone"),
            price_target_short=stock_data.get("price_target_short"),
            price_target_long=stock_data.get("price_target_long"),
            stop_loss_risk=stock_data.get("stop_loss_risk"),
            moat_rating=stock_data.get("moat_rating"),
            trade_rationale=stock_data.get("trade_rationale"),
            chart_setup=stock_data.get("chart_setup"),
            # Version tracking
            is_latest=True,
            version=version,
        )
    
    # ==========================================================================
    # Read Operations
    # ==========================================================================
    
    def get_all_stocks(
        self,
        order_by_score: bool = True,
        limit: int | None = None,
        latest_only: bool = True,
    ) -> list[Stock]:
        """
        Retrieve all stocks from database.
        
        Args:
            order_by_score: If True, sort by Gomes score descending
            limit: Maximum number of results (None = all)
            latest_only: If True, return only latest version of each ticker
            
        Returns:
            List of Stock objects
        """
        query = self._session.query(Stock)
        
        if latest_only:
            query = query.filter(Stock.is_latest == True)
        
        if order_by_score:
            query = query.order_by(
                desc(Stock.gomes_score),
                desc(Stock.created_at),
            )
        else:
            query = query.order_by(desc(Stock.created_at))
        
        if limit:
            query = query.limit(limit)
        
        return query.all()
    
    def get_stock_by_ticker(self, ticker: str) -> Stock | None:
        """
        Get most recent analysis for a specific ticker.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Stock object or None if not found
        """
        return (
            self._session.query(Stock)
            .filter(Stock.ticker == ticker.upper())
            .order_by(desc(Stock.created_at))
            .first()
        )
    
    def get_ticker_history(self, ticker: str) -> list[Stock]:
        """
        Get all historical analyses for a ticker.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            List of Stock objects ordered by date descending
        """
        return (
            self._session.query(Stock)
            .filter(Stock.ticker == ticker.upper())
            .order_by(desc(Stock.created_at))
            .all()
        )
    
    def get_stocks_by_sentiment(self, sentiment: str) -> list[Stock]:
        """
        Filter stocks by sentiment.
        
        Args:
            sentiment: "Bullish", "Bearish", or "Neutral"
            
        Returns:
            List of Stock objects matching sentiment
        """
        return (
            self._session.query(Stock)
            .filter(Stock.sentiment == sentiment)
            .order_by(desc(Stock.gomes_score))
            .all()
        )
    
    def get_high_conviction_stocks(self, min_score: int = 8) -> list[Stock]:
        """
        Get stocks with high Gomes scores.
        
        Args:
            min_score: Minimum Gomes score threshold (default: 8)
            
        Returns:
            List of high-conviction Stock objects
        """
        return (
            self._session.query(Stock)
            .filter(Stock.gomes_score >= min_score)
            .order_by(desc(Stock.gomes_score))
            .all()
        )


# ==============================================================================
# Legacy Function (Backward Compatibility)
# ==============================================================================

def save_analysis(
    session: Session,
    source_id: str,
    source_type: str,
    stocks: list[dict[str, Any]],
    speaker: str = "Mark Gomes",
) -> tuple[bool, str | None]:
    """
    Legacy function for backward compatibility.
    
    DEPRECATED: Use StockRepository.create_stocks() directly.
    
    Args:
        session: Database session
        source_id: Source identifier
        source_type: Source type (YouTube, Google Docs, etc.)
        stocks: List of analyzed stocks
        speaker: Analyst name
        
    Returns:
        Tuple of (success, error_message)
    """
    repo = StockRepository(session)
    return repo.create_stocks(stocks, source_id, source_type, speaker)
