"""
Trading Intelligence Models

SQLAlchemy models for trading signals, ML predictions, and market data.

Clean Code Principles Applied:
- Explicit column documentation
- Type hints for all properties
- Proper relationship definitions
- Constants for signal types
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import relationship, Mapped

from .base import Base

if TYPE_CHECKING:
    from .stock import Stock
    from .analysis import SWOTAnalysis


# ==============================================================================
# Constants for Signal Types
# ==============================================================================

class PredictionType:
    """ML prediction direction types."""
    UP: str = "UP"
    DOWN: str = "DOWN"
    NEUTRAL: str = "NEUTRAL"


class SignalType:
    """Trading signal action types."""
    BUY: str = "BUY"
    SELL: str = "SELL"
    HOLD: str = "HOLD"


class OHLCVData(Base):
    """Time-series OHLCV data (TimescaleDB hypertable)"""
    __tablename__ = "ohlcv_data"
    
    time = Column(TIMESTAMP(timezone=True), primary_key=True, nullable=False)
    ticker = Column(String(10), primary_key=True, nullable=False, index=True)
    open = Column(Numeric(12, 4), nullable=False)
    high = Column(Numeric(12, 4), nullable=False)
    low = Column(Numeric(12, 4), nullable=False)
    close = Column(Numeric(12, 4), nullable=False)
    volume = Column(BigInteger, nullable=False)
    vwap = Column(Numeric(12, 4))
    
    __table_args__ = (
        Index('idx_ohlcv_ticker_time', 'ticker', 'time'),
        Index('idx_ohlcv_time', 'time'),
    )
    
    def __repr__(self):
        return f"<OHLCV {self.ticker} @ {self.time}: close={self.close}>"


class ActiveWatchlist(Base):
    """Analyst-recommended tickers for active monitoring"""
    __tablename__ = "active_watchlist"
    
    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), unique=True, nullable=False, index=True)
    stock_id = Column(Integer, ForeignKey('stocks.id', ondelete='CASCADE'))
    action_verdict = Column(String(20))
    confidence_score = Column(Numeric(3, 2))
    added_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    last_updated = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    is_active = Column(Boolean, nullable=False, default=True)
    notes = Column(Text)
    
    # Enhanced analysis fields (added via migration)
    gomes_score = Column(Numeric(4, 2))
    investment_thesis = Column(Text)
    risks = Column(Text)
    
    # Relationships
    stock = relationship("Stock")
    predictions = relationship("MLPrediction", back_populates="watchlist", cascade="all, delete-orphan")
    swot_analyses = relationship("SWOTAnalysis", back_populates="watchlist", cascade="all, delete-orphan")
    
    __table_args__ = (
        CheckConstraint('confidence_score >= 0 AND confidence_score <= 1', name='check_confidence_range'),
        CheckConstraint('gomes_score >= 0 AND gomes_score <= 10', name='check_gomes_score_range'),
        Index('idx_watchlist_active', 'is_active', 'last_updated'),
        Index('idx_watchlist_gomes_score', 'gomes_score', postgresql_where="gomes_score IS NOT NULL"),
    )
    
    def __repr__(self):
        return f"<Watchlist {self.ticker}: {self.action_verdict}>"


class MLPrediction(Base):
    """ML model predictions (PatchTST output)"""
    __tablename__ = "ml_predictions"
    
    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), nullable=False, index=True)
    prediction_type = Column(String(10), nullable=False)  # UP, DOWN, NEUTRAL
    confidence = Column(Numeric(5, 4), nullable=False)
    predicted_price = Column(Numeric(12, 4), nullable=False)
    current_price = Column(Numeric(12, 4), nullable=False)
    kelly_position_size = Column(Numeric(5, 4))
    model_version = Column(String(50))
    horizon_days = Column(Integer, default=5)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow, index=True)
    valid_until = Column(TIMESTAMP(timezone=True))
    stock_id = Column(Integer, ForeignKey('stocks.id', ondelete='SET NULL'))
    watchlist_id = Column(Integer, ForeignKey('active_watchlist.id', ondelete='SET NULL'))
    
    # Relationships
    stock = relationship("Stock")
    watchlist = relationship("ActiveWatchlist", back_populates="predictions")
    signals = relationship("TradingSignal", back_populates="ml_prediction")
    performance_records = relationship("ModelPerformance", back_populates="prediction", cascade="all, delete-orphan")
    
    __table_args__ = (
        CheckConstraint("prediction_type IN ('UP', 'DOWN', 'NEUTRAL')", name='check_prediction_type'),
        CheckConstraint('confidence >= 0 AND confidence <= 1', name='check_confidence'),
        CheckConstraint('kelly_position_size >= 0 AND kelly_position_size <= 1', name='check_kelly'),
        Index('idx_predictions_ticker_time', 'ticker', 'created_at'),
        Index('idx_predictions_valid', 'ticker', 'valid_until'),
        Index('idx_predictions_type', 'prediction_type', 'created_at'),
    )
    
    @property
    def expected_return_pct(self):
        """Calculate expected return percentage"""
        if self.current_price <= 0:
            return 0.0
        return ((self.predicted_price - self.current_price) / self.current_price) * 100
    
    def __repr__(self):
        return f"<Prediction {self.ticker}: {self.prediction_type} @ {self.confidence:.2f}>"


class TradingSignal(Base):
    """Final actionable trading signals"""
    __tablename__ = "trading_signals"
    
    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), nullable=False, index=True)
    signal_type = Column(String(10), nullable=False)  # BUY, SELL, HOLD
    ml_prediction_id = Column(Integer, ForeignKey('ml_predictions.id', ondelete='SET NULL'))
    analyst_source_id = Column(Integer, ForeignKey('stocks.id', ondelete='SET NULL'))
    confidence = Column(Numeric(5, 4), nullable=False)
    kelly_size = Column(Numeric(5, 4), nullable=False)
    entry_price = Column(Numeric(12, 4))
    target_price = Column(Numeric(12, 4))
    stop_loss = Column(Numeric(12, 4))
    risk_reward_ratio = Column(Numeric(5, 2))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow, index=True)
    expires_at = Column(TIMESTAMP(timezone=True))
    is_active = Column(Boolean, nullable=False, default=True)
    executed = Column(Boolean, default=False)
    execution_price = Column(Numeric(12, 4))
    execution_time = Column(TIMESTAMP(timezone=True))
    notes = Column(Text)
    
    # Relationships
    ml_prediction = relationship("MLPrediction", back_populates="signals")
    analyst_source = relationship("Stock")
    
    __table_args__ = (
        CheckConstraint("signal_type IN ('BUY', 'SELL', 'HOLD')", name='check_signal_type'),
        CheckConstraint('confidence >= 0 AND confidence <= 1', name='check_signal_confidence'),
        CheckConstraint('kelly_size >= 0 AND kelly_size <= 1', name='check_signal_kelly'),
        Index('idx_signals_active', 'ticker', 'is_active', 'created_at'),
        Index('idx_signals_type', 'signal_type', 'is_active'),
        Index('idx_signals_expires', 'expires_at'),
    )
    
    @property
    def position_size_pct(self):
        """Get position size as percentage"""
        return float(self.kelly_size * 100)
    
    def __repr__(self):
        return f"<Signal {self.ticker}: {self.signal_type} @ {self.kelly_size*100:.1f}%>"


class ModelPerformance(Base):
    """Track ML model accuracy over time"""
    __tablename__ = "model_performance"
    
    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), nullable=False, index=True)
    model_version = Column(String(50), nullable=False)
    prediction_id = Column(Integer, ForeignKey('ml_predictions.id', ondelete='CASCADE'))
    predicted_direction = Column(String(10))
    actual_direction = Column(String(10))
    predicted_price = Column(Numeric(12, 4))
    actual_price = Column(Numeric(12, 4))
    accuracy = Column(Numeric(5, 4))
    prediction_date = Column(TIMESTAMP(timezone=True), nullable=False)
    evaluation_date = Column(TIMESTAMP(timezone=True), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    
    # Relationships
    prediction = relationship("MLPrediction", back_populates="performance_records")
    
    __table_args__ = (
        Index('idx_performance_ticker', 'ticker', 'evaluation_date'),
        Index('idx_performance_accuracy', 'accuracy'),
    )
    
    def __repr__(self):
        return f"<Performance {self.ticker}: {self.accuracy:.2%}>"


class DataSyncLog(Base):
    """Log background data sync jobs"""
    __tablename__ = "data_sync_log"
    
    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), nullable=False, index=True)
    sync_type = Column(String(20), nullable=False)  # daily, manual, initial
    records_synced = Column(Integer, default=0)
    from_date = Column(TIMESTAMP(timezone=True))
    to_date = Column(TIMESTAMP(timezone=True))
    status = Column(String(20), nullable=False)  # success, failed, partial
    error_message = Column(Text)
    duration_seconds = Column(Integer)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow, index=True)
    
    __table_args__ = (
        CheckConstraint("status IN ('success', 'failed', 'partial')", name='check_sync_status'),
        Index('idx_sync_log_ticker', 'ticker', 'created_at'),
        Index('idx_sync_log_status', 'status', 'created_at'),
    )
    
    def __repr__(self):
        return f"<SyncLog {self.ticker}: {self.status} - {self.records_synced} records>"


# Update Stock model to include relationship
# Add to backend/app/models/stock.py:
# from sqlalchemy.orm import relationship
# watchlist_entries = relationship("ActiveWatchlist", back_populates="stock", cascade="all, delete-orphan")
