"""
Price Engine.

Provides mark price at every exec bar close.
MARK is implicit - always available, never declared in Play.
"""

from src.backtest.prices.types import PriceRef, HealthCheckResult, MarkPriceResult
from src.backtest.prices.engine import MarkPriceEngine
from src.backtest.prices.providers.sim_mark import SimMarkProvider
from src.backtest.prices.validation import (
    MarkValidationResult,
    validate_mark_price_availability,
    validate_mark_or_fail,
    log_mark_resolution,
)

__all__ = [
    # Types
    "PriceRef",
    "HealthCheckResult",
    "MarkPriceResult",
    "MarkValidationResult",
    # Engine
    "MarkPriceEngine",
    # Providers
    "SimMarkProvider",
    # Validation
    "validate_mark_price_availability",
    "validate_mark_or_fail",
    "log_mark_resolution",
]
