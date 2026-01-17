"""
Base Model Module

Provides the SQLAlchemy declarative base and common model utilities.
All models should inherit from Base defined here.

Clean Code Principles Applied:
- Single source of truth for Base
- Centralized model utilities
- Type-safe column helpers
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, TypeVar

from sqlalchemy import Column, DateTime, Integer, func
from sqlalchemy.orm import declarative_base, DeclarativeMeta


# ==============================================================================
# SQLAlchemy Base
# ==============================================================================

Base: DeclarativeMeta = declarative_base()

# Type variable for generic model operations
ModelType = TypeVar("ModelType", bound=Base)


# ==============================================================================
# Common Mixins
# ==============================================================================

class TimestampMixin:
    """
    Mixin providing created_at and updated_at timestamps.
    
    Usage:
        class MyModel(Base, TimestampMixin):
            __tablename__ = "my_table"
            id = Column(Integer, primary_key=True)
    """
    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        doc="Record creation timestamp"
    )
    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
        doc="Last update timestamp"
    )


class IdentityMixin:
    """
    Mixin providing standard integer primary key.
    
    Usage:
        class MyModel(Base, IdentityMixin):
            __tablename__ = "my_table"
            name = Column(String)
    """
    id = Column(
        Integer,
        primary_key=True,
        index=True,
        doc="Unique identifier"
    )


# ==============================================================================
# Base Model with Common Features
# ==============================================================================

class BaseModel(Base, IdentityMixin, TimestampMixin):
    """
    Abstract base model with id, created_at, and updated_at.
    
    Most models should inherit from this instead of raw Base.
    
    Usage:
        class Stock(BaseModel):
            __tablename__ = "stocks"
            ticker = Column(String(20), nullable=False)
    """
    __abstract__ = True
    
    def to_dict(self) -> dict[str, Any]:
        """
        Convert model to dictionary.
        
        Override in subclasses for custom serialization.
        
        Returns:
            Dictionary representation of the model
        """
        result: dict[str, Any] = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)
            if isinstance(value, datetime):
                value = value.isoformat()
            result[column.name] = value
        return result
    
    def __repr__(self) -> str:
        """Generate a readable string representation."""
        class_name = self.__class__.__name__
        pk = getattr(self, 'id', None)
        return f"<{class_name}(id={pk})>"
