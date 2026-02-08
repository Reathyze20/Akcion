"""
Services Module

Business logic layer for the trading application.

Services:
- CurrencyService: Currency conversion to CZK
- GapAnalysisService: Match stock signals with user positions
- MarketDataService: Real-time market data from APIs
- BrokerCSVParser: Parse broker portfolio exports
"""

from .currency import CurrencyService
from .gap_analysis import GapAnalysisService, MatchSignal
from .gomes_deep_dd import GomesDeepDueDiligenceService
from .importer import BrokerCSVParser, resolve_ticker_from_isin, validate_position_data
from .kelly_allocator import KellyAllocatorService, AllocationRecommendation, FamilyGap
from .market_data import MarketDataService


__all__ = [
    # Services
    "CurrencyService",
    "GapAnalysisService",
    "GomesDeepDueDiligenceService",
    "KellyAllocatorService",
    "MarketDataService",
    "BrokerCSVParser",
    # Utilities
    "MatchSignal",
    "resolve_ticker_from_isin",
    "validate_position_data",
    "AllocationRecommendation",
    "FamilyGap",
]
