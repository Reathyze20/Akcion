"""
Database Connection Management

Handles SQLAlchemy engine and session lifecycle.
Designed to work with both Streamlit (secrets) and FastAPI (environment variables).
"""

from typing import Optional
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session as SQLAlchemySession
from sqlalchemy.exc import SQLAlchemyError

from ..models.stock import Base


# ==============================================================================
# Global Database State
# ==============================================================================

_engine = None
_SessionFactory = None


# ==============================================================================
# Connection Management
# ==============================================================================

def initialize_database(connection_url: str) -> tuple[bool, Optional[str]]:
    """
    Initialize database connection and create tables.
    
    Args:
        connection_url: PostgreSQL connection string
                       Format: postgresql://user:pass@host:port/dbname
    
    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    global _engine, _SessionFactory
    
    try:
        # Create engine with connection pooling
        _engine = create_engine(
            connection_url,
            pool_pre_ping=True,  # Verify connections before using
            pool_size=5,
            max_overflow=10
        )
        
        # Create session factory
        _SessionFactory = sessionmaker(bind=_engine)
        
        # Create tables if they don't exist
        Base.metadata.create_all(_engine)
        
        return True, None
        
    except SQLAlchemyError as e:
        _engine = None
        _SessionFactory = None
        return False, f"Database connection failed: {str(e)}"
    except Exception as e:
        _engine = None
        _SessionFactory = None
        return False, f"Unexpected error: {str(e)}"


def get_engine():
    """
    Get the global database engine.
    
    Returns:
        SQLAlchemy Engine or None if not initialized
    """
    return _engine


def get_session() -> Optional[SQLAlchemySession]:
    """
    Create a new database session.
    
    Returns:
        SQLAlchemy Session or None if database not initialized
        
    Usage:
        session = get_session()
        if session:
            try:
                # Use session
                session.add(object)
                session.commit()
            finally:
                session.close()
    """
    if _SessionFactory is None:
        return None
    return _SessionFactory()


def get_db():
    """
    Dependency injection helper for FastAPI.
    
    Yields a database session that is automatically closed.
    
    Usage in FastAPI:
        @app.get("/stocks")
        def get_stocks(db: Session = Depends(get_db)):
            return db.query(Stock).all()
    """
    session = get_session()
    if session is None:
        raise RuntimeError("Database not initialized")
    try:
        yield session
    finally:
        session.close()


def is_connected() -> bool:
    """
    Check if database is connected and operational.
    
    Returns:
        True if database connection is active
    """
    return _engine is not None
