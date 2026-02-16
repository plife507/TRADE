"""
Price module.

Provides PriceSource protocol for unified backtest/demo/live interface.
MARK is implicit - always available, never declared in Play.
"""

from src.backtest.prices.types import PriceRef, HealthCheckResult, MarkPriceResult
from src.backtest.prices.providers.sim_mark import SimMarkProvider
from src.backtest.prices.source import (
    PriceSource,
    PricePoint,
    DataNotAvailableError,
)

__all__ = [
    # Protocol (W3)
    "PriceSource",
    "PricePoint",
    "DataNotAvailableError",
    # Types
    "PriceRef",
    "HealthCheckResult",
    "MarkPriceResult",
    # Providers
    "SimMarkProvider",
]
