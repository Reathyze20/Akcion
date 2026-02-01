"""
Database Models Package

All SQLAlchemy models for the trading application.

Clean Code Principles Applied:
- Single Base definition in base.py
- Models grouped by domain (stock, portfolio, analysis, trading)
- Explicit exports in __all__
"""

# Base must be imported first - all models inherit from it
from .base import Base, BaseModel, TimestampMixin, IdentityMixin, ModelType

# Stock analysis models
from .stock import Stock, SourceType, SentimentType

# Portfolio management models
from .portfolio import (
    Portfolio,
    Position,
    MarketStatus,
    BrokerType,
    MarketStatusEnum,
    InvestmentLog,
    InvestmentLogType,
)

# Analysis intelligence models
from .analysis import AnalystTranscript, SWOTAnalysis

# Gomes Intelligence models
from .gomes import (
    MarketAlertModel,
    StockLifecycleModel,
    PriceLinesModel,
    PositionTierModel,
    InvestmentVerdictModel,
    ImageAnalysisLogModel,
    GomesRulesLogModel,
)

# Score History models
from .score_history import (
    ConvictionScoreHistory,
    ThesisDriftAlert,
    AlertType,
)

# Trading models (imported separately to avoid circular imports)
# from .trading import OHLCVData, ActiveWatchlist, MLPrediction, TradingSignal


__all__ = [
    # Base
    "Base",
    "BaseModel",
    "TimestampMixin",
    "IdentityMixin",
    "ModelType",
    # Stock
    "Stock",
    "SourceType",
    "SentimentType",
    # Portfolio
    "Portfolio",
    "Position",
    "MarketStatus",
    "BrokerType",
    "MarketStatusEnum",
    "InvestmentLog",
    "InvestmentLogType",
    # Analysis
    "AnalystTranscript",
    "SWOTAnalysis",
    # Gomes Intelligence
    "MarketAlertModel",
    "StockLifecycleModel",
    "PriceLinesModel",
    "PositionTierModel",
    "InvestmentVerdictModel",
    "ImageAnalysisLogModel",
    "GomesRulesLogModel",
    # Score History
    "ConvictionScoreHistory",
    "ThesisDriftAlert",
    "AlertType",
]
