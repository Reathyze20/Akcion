"""
Database Connection Management

Handles SQLAlchemy engine and session lifecycle.
Supports both FastAPI (environment variables) and Streamlit (secrets) contexts.

Clean Code Principles Applied:
- Single Responsibility: Only connection management
- Dependency Injection ready: get_db for FastAPI
- Explicit error handling
- Type hints throughout
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Final, Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from ..models.base import Base


logger = logging.getLogger(__name__)


# ==============================================================================
# Connection Pool Configuration
# ==============================================================================

DEFAULT_POOL_SIZE: Final[int] = 5
DEFAULT_MAX_OVERFLOW: Final[int] = 10


# ==============================================================================
# Global Database State
# ==============================================================================

_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


# ==============================================================================
# Connection Initialization
# ==============================================================================

def initialize_database(connection_url: str) -> tuple[bool, str | None]:
    """
    Initialize database connection and create tables.
    
    Args:
        connection_url: PostgreSQL connection string
                       Format: postgresql://user:pass@host:port/dbname
    
    Returns:
        Tuple of (success: bool, error_message: str | None)
        
    Example:
        success, error = initialize_database("postgresql://...")
        if not success:
            logger.error(f"Database init failed: {error}")
    """
    global _engine, _SessionFactory
    
    try:
        _engine = _create_engine(connection_url)
        _SessionFactory = sessionmaker(bind=_engine)
        _create_tables()
        
        logger.info("Database initialized successfully")
        return True, None
        
    except SQLAlchemyError as e:
        _reset_globals()
        error_msg = f"Database connection failed: {e}"
        logger.error(error_msg)
        return False, error_msg
    except Exception as e:
        _reset_globals()
        error_msg = f"Unexpected error: {e}"
        logger.exception(error_msg)
        return False, error_msg


def _create_engine(connection_url: str) -> Engine:
    """
    Create SQLAlchemy engine with connection pooling.
    
    Args:
        connection_url: Database connection URL
        
    Returns:
        Configured SQLAlchemy Engine
    """
    return create_engine(
        connection_url,
        pool_pre_ping=True,  # Verify connections before using
        pool_size=DEFAULT_POOL_SIZE,
        max_overflow=DEFAULT_MAX_OVERFLOW,
    )


def _create_tables() -> None:
    """Create all tables if they don't exist."""
    if _engine is not None:
        try:
            Base.metadata.create_all(_engine, checkfirst=True)
        except Exception as e:
            # Ignore errors for existing objects (indexes, constraints, etc.)
            logger.warning(f"Table creation warning (probably already exists): {e}")


def _reset_globals() -> None:
    """Reset global state on initialization failure."""
    global _engine, _SessionFactory
    _engine = None
    _SessionFactory = None


# ==============================================================================
# Session Management
# ==============================================================================

def get_engine() -> Engine | None:
    """
    Get the global database engine.
    
    Returns:
        SQLAlchemy Engine or None if not initialized
    """
    return _engine


def get_session() -> Session | None:
    """
    Create a new database session.
    
    Returns:
        SQLAlchemy Session or None if database not initialized
        
    Note:
        Caller is responsible for closing the session.
        Prefer using get_db() or session_scope() instead.
    """
    if _SessionFactory is None:
        return None
    return _SessionFactory()


def get_db() -> Generator[Session, None, None]:
    """
    Dependency injection helper for FastAPI.
    
    Yields a database session that is automatically closed.
    
    Yields:
        Active database session
        
    Raises:
        RuntimeError: If database not initialized
        
    Example:
        @app.get("/stocks")
        def get_stocks(db: Session = Depends(get_db)):
            return db.query(Stock).all()
    """
    session = get_session()
    if session is None:
        raise RuntimeError("Database not initialized. Call initialize_database() first.")
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """
    Context manager for database sessions with automatic commit/rollback.
    
    Provides a transactional scope around a series of operations.
    
    Yields:
        Active database session
        
    Raises:
        RuntimeError: If database not initialized
        
    Example:
        with session_scope() as session:
            stock = Stock(ticker="AAPL")
            session.add(stock)
            # Auto-commits on success, rollbacks on exception
    """
    session = get_session()
    if session is None:
        raise RuntimeError("Database not initialized. Call initialize_database() first.")
    
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ==============================================================================
# Status Checks
# ==============================================================================

def is_connected() -> bool:
    """
    Check if database is connected and operational.
    
    Returns:
        True if database connection is active
    """
    return _engine is not None
