"""Trading module for Akcion - ML-driven trading intelligence"""

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
    "MLPredictionEngine",
    "KellyCriterion",
    "SignalGenerator",
    "ML_ENGINE_AVAILABLE"
]
