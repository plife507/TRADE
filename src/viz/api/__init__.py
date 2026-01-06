"""
Visualization API routes.

All endpoints are mounted under /api prefix.
"""

from .runs import router as runs_router
from .metrics import router as metrics_router
from .charts import router as charts_router
from .trades import router as trades_router
from .equity import router as equity_router
from .indicators import router as indicators_router

__all__ = [
    "runs_router",
    "metrics_router",
    "charts_router",
    "trades_router",
    "equity_router",
    "indicators_router",
]
