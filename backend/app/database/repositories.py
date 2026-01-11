"""
Data Access Layer (Repository Pattern)

Provides clean interfaces for database operations.
Separates business logic from SQL queries.
"""

from typing import List, Optional, Dict
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import desc

from ..models.stock import Stock


# ==============================================================================
# Stock Repository
# ==============================================================================

class StockRepository:
    """
    Handles all database operations for Stock entities.
    
    Follows Repository pattern to abstract SQL details from business logic.
    """
    
    def __init__(self, session: Session):
        """
        Initialize repository with database session.
        
        Args:
            session: Active SQLAlchemy session
        """
        self.session = session
    
    def create_stocks(
        self,
        stocks: List[Dict],
        source_id: str,
        source_type: str,
        speaker: str = "Mark Gomes"
    ) -> tuple[bool, Optional[str]]:
        """
        Save multiple stock analyses to database.
        
        Args:
            stocks: List of stock dictionaries from AI analysis
            source_id: Identifier of source (video ID, doc ID, etc.)
            source_type: Type of source (YouTube, Google Docs, etc.)
            speaker: Speaker/analyst name
            
        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        try:
            for stock_data in stocks:
                stock = Stock(
                    ticker=stock_data.get("ticker", ""),
                    company_name=stock_data.get("company_name", stock_data.get("name", "")),
                    source_type=source_type,
                    speaker=speaker,
                    sentiment=stock_data.get("sentiment", "Neutral"),
                    gomes_score=stock_data.get("gomes_score", 5),
                    price_target=stock_data.get("price_target", ""),
                    edge=stock_data.get("edge", ""),
                    catalysts=stock_data.get("catalysts", ""),
                    risks=stock_data.get("risks", ""),
                    raw_notes=stock_data.get("note", stock_data.get("status", "")),
                    time_horizon=stock_data.get("horizon", stock_data.get("time_horizon", "Long-term")),
                    conviction_score=stock_data.get("conviction_score", stock_data.get("gomes_score", 5))
                )
                self.session.add(stock)
            
            self.session.commit()
            return True, None
            
        except SQLAlchemyError as e:
            self.session.rollback()
            return False, f"Database error: {str(e)}"
        except Exception as e:
            self.session.rollback()
            return False, f"Unexpected error: {str(e)}"
    
    def get_all_stocks(
        self,
        order_by_score: bool = True,
        limit: Optional[int] = None
    ) -> List[Stock]:
        """
        Retrieve all stocks from database.
        
        Args:
            order_by_score: If True, sort by Gomes score descending
            limit: Maximum number of results (None = all)
            
        Returns:
            List of Stock objects
        """
        query = self.session.query(Stock)
        
        if order_by_score:
            # Sort by Gomes score descending, then by date
            query = query.order_by(
                desc(Stock.gomes_score),
                desc(Stock.created_at)
            )
        else:
            query = query.order_by(desc(Stock.created_at))
        
        if limit:
            query = query.limit(limit)
        
        return query.all()
    
    def get_stock_by_ticker(self, ticker: str) -> Optional[Stock]:
        """
        Get most recent analysis for a specific ticker.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Stock object or None if not found
        """
        return self.session.query(Stock).filter(
            Stock.ticker == ticker.upper()
        ).order_by(desc(Stock.created_at)).first()
    
    def get_ticker_history(self, ticker: str) -> List[Stock]:
        """
        Get all historical analyses for a ticker.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            List of Stock objects ordered by date descending
        """
        return self.session.query(Stock).filter(
            Stock.ticker == ticker.upper()
        ).order_by(desc(Stock.created_at)).all()
    
    def get_stocks_by_sentiment(self, sentiment: str) -> List[Stock]:
        """
        Filter stocks by sentiment.
        
        Args:
            sentiment: "Bullish", "Bearish", or "Neutral"
            
        Returns:
            List of Stock objects
        """
        return self.session.query(Stock).filter(
            Stock.sentiment == sentiment
        ).order_by(desc(Stock.gomes_score)).all()
    
    def get_high_conviction_stocks(self, min_score: int = 8) -> List[Stock]:
        """
        Get stocks with high Gomes scores.
        
        Args:
            min_score: Minimum Gomes score (default: 8)
            
        Returns:
            List of high-conviction Stock objects
        """
        return self.session.query(Stock).filter(
            Stock.gomes_score >= min_score
        ).order_by(desc(Stock.gomes_score)).all()


# ==============================================================================
# Convenience Functions
# ==============================================================================

def save_analysis(
    session: Session,
    source_id: str,
    source_type: str,
    stocks: List[Dict],
    speaker: str = "Mark Gomes"
) -> tuple[bool, Optional[str]]:
    """
    Legacy function for backward compatibility.
    
    Save stock analysis results to database.
    
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
