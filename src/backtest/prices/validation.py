"""
Mark Price Validation.

Stage 1: Validates MARK availability for backtest/sim.
MARK is always required (not conditional on IdeaCard).
"""

import logging
from dataclasses import dataclass
from typing import Optional

from src.backtest.prices.engine import MarkPriceEngine
from src.backtest.prices.types import HealthCheckResult

logger = logging.getLogger(__name__)


@dataclass
class MarkValidationResult:
    """Result of mark price validation."""

    ok: bool
    provider_name: str
    message: str
    bar_count: int = 0

    def __bool__(self) -> bool:
        return self.ok


def validate_mark_price_availability(engine: MarkPriceEngine) -> MarkValidationResult:
    """
    Validate that MarkPriceEngine is ready to serve mark prices.

    This is the Stage 1 preflight check for MARK. Call during engine setup.
    MARK is always required (not conditional on IdeaCard).

    Args:
        engine: MarkPriceEngine instance

    Returns:
        MarkValidationResult with status
    """
    health = engine.healthcheck()

    if not health.ok:
        return MarkValidationResult(
            ok=False,
            provider_name=health.provider_name,
            message=f"MARK validation failed: {health.message}",
        )

    bar_count = health.details.get("bar_count", 0) if health.details else 0

    return MarkValidationResult(
        ok=True,
        provider_name=health.provider_name,
        message=f"MARK available via {health.provider_name}",
        bar_count=bar_count,
    )


def validate_mark_or_fail(engine: MarkPriceEngine) -> None:
    """
    Validate MARK and raise if not available.

    Use this for hard-fail validation during engine setup.

    Args:
        engine: MarkPriceEngine instance

    Raises:
        RuntimeError: If MARK validation fails
    """
    result = validate_mark_price_availability(engine)
    if not result.ok:
        raise RuntimeError(
            f"MARK price validation failed: {result.message}. "
            "Ensure historical data is loaded before engine run."
        )


def log_mark_resolution(engine: MarkPriceEngine) -> None:
    """
    Log mark price resolution once per run.

    Call after validation, before simulation loop.
    """
    engine.log_resolution()
