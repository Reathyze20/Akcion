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

# Optional routers (may not exist in all deployments).
#
# One `try` per module, deliberately. They shared a single block, so a single
# missing file set ALL of them to None — and `master_signal` was in that block
# after being unwired, which meant deleting its file would silently have taken
# `intelligence`, `trading` and `intelligence_gomes` down with it. A failure
# that disables three working routers is not an optional import, it is a trap.
try:
    from .intelligence import router as intelligence_router
except ImportError:
    intelligence_router = None

try:
    from .trading import router as trading_router
except ImportError:
    trading_router = None

try:
    from .intelligence_gomes import router as intelligence_gomes_router
except ImportError:
    intelligence_gomes_router = None

# `master_signal` was removed from the app on 2026-08-24: a rival engine whose
# "Weinstein phase" read a Green Line as a moving average. Nothing imports it.


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
