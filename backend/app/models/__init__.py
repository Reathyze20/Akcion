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
    GomesAlert,
    GomesScoreHistory,
)

# Score History models
from .score_history import (
    ConvictionScoreHistory,
    ThesisDriftAlert,
    AlertType,
)

# Score Outcome models (forward returns of each journaled score)
from .score_outcome import (
    ScoreOutcome,
    STATUS_EVALUATED,
    STATUS_PENDING,
    STATUS_UNABLE,
)

# The other half of the record: the buys the guard refused
from .refused_buy import RefusedBuy

# Whose word counts, and for which source
from .analyst_roster import RosterEntry

# Trailing figures kept over time, instead of overwritten
from .fundamental_snapshot import FundamentalSnapshot

# When each company next reports — the canon's blackout rule needs it
from .earnings import SOURCE_SEC_CADENCE, SOURCE_YAHOO, EarningsDate

# Reading the Gomes tracker: when we last looked, and what moved
from .tracker import TRACKER_CHANGE_KINDS, TrackerLineChange, TrackerPollState

# Per-ticker cooldown for POST /api/intelligence/analyze-ticker
from .analyze_ticker import AnalyzeTickerState

# A standing owner instruction the phase gate cannot see (ECOR, SMSI)
from .owner_intent import OwnerIntentModel

# Trading models (imported separately to avoid circular imports)
# from .trading import OHLCVData, ActiveWatchlist, MLPrediction, TradingSignal


# Breakout Investors watchlist (the second source, shown but never obeyed)
from .breakout import (
    BreakoutWatchEntry,
    BreakoutWatchChange,
    BreakoutPollState,
    CHANGE_KINDS,
)

# Vlastní nálezy — nápady majitele a jejich posudky (uzavřené pískoviště)
from .own_find import (
    FIND_STATUSES,
    STATUS_DEFERRED,
    STATUS_DISCARDED,
    STATUS_OPEN,
    OwnFind,
    OwnFindAssessment,
)


# Analytikovy modely tržeb — sledování cizích bottom-up modelů vs. realita
from .revenue_model import (
    CONFIDENCE_ESTIMATE,
    CONFIDENCE_LOCKED,
    CONFIDENCE_VALUES,
    AnalystRevenueModel,
    AnalystRevenueModelLine,
)

from .sec import InsiderTransaction, SecCoverage, SecFiling
from .sec_finding import (
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    SecFinding,
)

__all__ = [
    "SecCoverage",
    "SecFiling",
    "SecFinding",
    "SEVERITY_CRITICAL",
    "SEVERITY_HIGH",
    "SEVERITY_MEDIUM",
    "InsiderTransaction",
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
    "GomesAlert",
    "GomesScoreHistory",
    # Score History
    "ConvictionScoreHistory",
    "ThesisDriftAlert",
    "AlertType",
    # Score Outcomes
    "ScoreOutcome",
    "STATUS_EVALUATED",
    "STATUS_PENDING",
    "STATUS_UNABLE",
    # Refused buys
    "RefusedBuy",
    # Analyst roster
    "RosterEntry",
    # Fundamental history
    "FundamentalSnapshot",
    # Earnings calendar
    "EarningsDate",
    "SOURCE_YAHOO",
    "SOURCE_SEC_CADENCE",
    # Gomes tracker sync
    "TrackerPollState",
    "TrackerLineChange",
    "TRACKER_CHANGE_KINDS",
    # analyze-ticker cooldown
    "AnalyzeTickerState",
    # owner intent (ECOR, SMSI)
    "OwnerIntentModel",
    # Breakout Investors watchlist
    "BreakoutWatchEntry",
    "BreakoutWatchChange",
    "BreakoutPollState",
    "CHANGE_KINDS",
    # Vlastní nálezy
    "OwnFind",
    "OwnFindAssessment",
    "FIND_STATUSES",
    "STATUS_OPEN",
    "STATUS_DEFERRED",
    "STATUS_DISCARDED",
    # Analytikovy modely tržeb
    "AnalystRevenueModel",
    "AnalystRevenueModelLine",
    "CONFIDENCE_LOCKED",
    "CONFIDENCE_ESTIMATE",
    "CONFIDENCE_VALUES",
]
