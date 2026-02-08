"""Trading module for Akcion - Simplified trading intelligence

Removed ML/PyTorch components - Gomes doesn't need neural nets for micro-caps.
Focus: Thesis Tracker + Cash/Valuation + Weinstein 30 WMA
"""

from .watchlist import WatchlistBuilder
from .data_fetcher import DataFetcher
from .kelly import KellyCriterion
from .signals import SignalGenerator

# Import ML engine with graceful fallback for pytorch_lightning compatibility issues
try:
    from .ml_engine import MLPredictionEngine
    ML_ENGINE_AVAILABLE = True
except (ImportError, AttributeError) as e:
    MLPredictionEngine = None
    ML_ENGINE_AVAILABLE = False
    import warnings
    warnings.warn(f"ML Engine not available due to dependency issue: {e}")

__all__ = [
    "WatchlistBuilder",
    "DataFetcher", 
    "KellyCriterion",
    "SignalGenerator",
    "ML_ENGINE_AVAILABLE"
]
