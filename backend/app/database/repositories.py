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

from ..core.sources import normalize_source, summarize_source_agreement
from ..models.stock import Stock


logger = logging.getLogger(__name__)


# ==============================================================================
# Constants
# ==============================================================================

DEFAULT_conviction_score: int = 5
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

        source_key = normalize_source(speaker)
        version = self._handle_existing_versions(ticker, source_key)
        stock = self._create_stock_entity(
            stock_data, ticker, source_type, speaker, version, source_key
        )
        self._session.add(stock)
    
    def _extract_ticker(self, stock_data: dict[str, Any]) -> str | None:
        """Extract and normalize ticker from stock data."""
        ticker = stock_data.get("ticker", "")
        return ticker.upper() if ticker else None
    
    def _handle_existing_versions(self, ticker: str, source_key: str) -> int:
        """
        Prepare version tracking for a new analysis of (ticker, source_key).

        Two things happen:
        - The single "primary" latest (is_latest=True) for this ticker is demoted,
          so the new row becomes the primary. is_latest stays one-per-ticker, which
          keeps all existing portfolio/sizing reads working unchanged.
        - Version numbering and retention cleanup are scoped to THIS source only,
          so pasting a Breakout Investors take never deletes or supersedes the
          Gomes history for the same ticker (the dual-source data-loss fix).

        Returns:
            New per-source version number.
        """
        # Demote the current primary (most-recent-overall) for legacy single-row reads.
        primary = self._get_latest_version(ticker)
        if primary:
            primary.is_latest = False

        # Per-source version + retention (does not touch other sources' rows).
        same_source = (
            self._session.query(Stock)
            .filter(Stock.ticker == ticker, Stock.source_key == source_key)
            .order_by(desc(Stock.created_at))
            .all()
        )
        new_version = (same_source[0].version or 1) + 1 if same_source else 1
        self._cleanup_old_versions(ticker, source_key)
        return new_version

    def _get_latest_version(self, ticker: str) -> Stock | None:
        """Get the current primary (is_latest) row for a ticker (one per ticker)."""
        return self._session.query(Stock).filter(
            Stock.ticker == ticker,
            Stock.is_latest == True,
        ).first()

    def _cleanup_old_versions(self, ticker: str, source_key: str) -> None:
        """
        Keep only the newest MAX_VERSIONS_TO_KEEP rows for THIS (ticker, source_key).

        Scoped by source so trimming one source's history never deletes another
        source's analyses. Called before the new row is added, so we retain
        MAX_VERSIONS_TO_KEEP - 1 existing rows + the incoming one.
        """
        old_versions = (
            self._session.query(Stock)
            .filter(
                Stock.ticker == ticker,
                Stock.source_key == source_key,
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
        source_key: str,
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
            source_key=source_key,
            sentiment=stock_data.get("sentiment", "Neutral"),
            conviction_score=(
                stock_data.get("conviction_score")
                or DEFAULT_conviction_score
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
                desc(Stock.conviction_score),
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
    
    def get_current_by_source(self, ticker: str) -> list[Stock]:
        """
        Get the most recent analysis PER source for a ticker.

        Returns one row per distinct source_key (e.g. one Gomes take + one
        Breakout Investors take), each the latest for that source. This is the
        data behind the side-by-side dual-source view. Uses Postgres DISTINCT ON.
        """
        return (
            self._session.query(Stock)
            .filter(Stock.ticker == ticker.upper())
            .order_by(Stock.source_key, desc(Stock.created_at))
            .distinct(Stock.source_key)
            .all()
        )

    def get_source_comparison(self, ticker: str) -> dict[str, Any]:
        """
        Side-by-side comparison of every source's current take on a ticker,
        plus an agreement summary (AGREE / MIXED / CONFLICT / SINGLE / NONE).
        """
        takes = self.get_current_by_source(ticker)
        take_dicts = [t.to_dict() for t in takes]
        return {
            "ticker": ticker.upper(),
            "sources": take_dicts,
            "agreement": summarize_source_agreement(take_dicts),
        }

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
            .order_by(desc(Stock.conviction_score))
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
            .filter(Stock.conviction_score >= min_score)
            .order_by(desc(Stock.conviction_score))
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
