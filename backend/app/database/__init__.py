"""
Database Package

Provides database connection management and data access layer.

Modules:
- connection: Engine/session lifecycle, dependency injection
- repositories: Repository pattern for entity operations
"""

from .connection import (
    initialize_database,
    get_engine,
    get_session,
    get_db,
    session_scope,
    is_connected,
    DEFAULT_POOL_SIZE,
    DEFAULT_MAX_OVERFLOW,
)
from .repositories import (
    StockRepository,
    save_analysis,
    DEFAULT_GOMES_SCORE,
    MAX_VERSIONS_TO_KEEP,
)


__all__ = [
    # Connection
    "initialize_database",
    "get_engine",
    "get_session",
    "get_db",
    "session_scope",
    "is_connected",
    "DEFAULT_POOL_SIZE",
    "DEFAULT_MAX_OVERFLOW",
    # Repositories
    "StockRepository",
    "save_analysis",
    "DEFAULT_GOMES_SCORE",
    "MAX_VERSIONS_TO_KEEP",
]
