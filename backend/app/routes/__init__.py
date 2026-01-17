"""
API Routes Module

FastAPI route handlers for the trading intelligence application.

Routes:
- analysis: Transcript analysis and stock extraction
- stocks: Portfolio stock queries
- portfolio: Portfolio and position management
- gap_analysis: Match signals with positions
- trading: Trading operations
- intelligence: AI insights
- gomes: Gomes scoring system
"""

from .analysis import router as analysis_router
from .gap_analysis import router as gap_analysis_router
from .gomes import router as gomes_router
from .portfolio import router as portfolio_router
from .stocks import router as stocks_router

# Optional routers (may not exist in all deployments)
try:
    from .intelligence import router as intelligence_router
    from .trading import router as trading_router
    from .intelligence_gomes import router as intelligence_gomes_router
except ImportError:
    intelligence_router = None
    trading_router = None
    intelligence_gomes_router = None


__all__ = [
    "analysis_router",
    "gap_analysis_router",
    "gomes_router",
    "portfolio_router",
    "stocks_router",
    "intelligence_router",
    "trading_router",
    "intelligence_gomes_router",
]
