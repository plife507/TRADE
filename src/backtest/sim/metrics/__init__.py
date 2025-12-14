"""
Exchange-side metrics for realism and performance tracking.

Tracks slippage costs, funding costs, liquidation events, and execution quality.
These are exchange-level metrics, NOT strategy/indicator metrics.
"""

from .metrics import ExchangeMetrics, ExchangeMetricsSnapshot

__all__ = [
    "ExchangeMetrics",
    "ExchangeMetricsSnapshot",
]

