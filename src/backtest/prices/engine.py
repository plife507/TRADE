"""
Mark Price Engine.

Single producer of mark_price and mark_price_source for snapshot construction.
MARK is always available (implicit, never declared in IdeaCard).
"""

import logging
from typing import Optional, Tuple

import numpy as np

from src.backtest.prices.types import HealthCheckResult, PriceRef
from src.backtest.prices.providers.sim_mark import SimMarkProvider, MarkProvider

logger = logging.getLogger(__name__)


class MarkPriceEngine:
    """
    Mark Price Engine for backtest/sim.

    Stage 1 responsibilities:
    - Provide mark close price at every exec bar
    - Single source of truth for mark_price and mark_price_source
    - Validate data availability at preflight
    - Log provider resolution once per run

    Stage 6+ will extend to provide mark high/low for zone interaction.
    """

    def __init__(self, provider: MarkProvider):
        """
        Initialize with a mark provider.

        Args:
            provider: Mark price provider (SimMarkProvider for backtest)
        """
        self._provider = provider
        self._resolution_logged = False

    @classmethod
    def from_feed_arrays(
        cls,
        ts_close_array: np.ndarray,
        close_array: np.ndarray,
    ) -> "MarkPriceEngine":
        """
        Create engine from feed arrays (convenience factory for backtest).

        Args:
            ts_close_array: Array of bar close timestamps (ms)
            close_array: Array of bar close prices

        Returns:
            MarkPriceEngine configured with SimMarkProvider
        """
        provider = SimMarkProvider(ts_close_array, close_array)
        return cls(provider)

    def get_mark_close(self, ts_close_ms: int) -> float:
        """
        Get mark close price at the given timestamp.

        Args:
            ts_close_ms: Exec bar close timestamp in milliseconds

        Returns:
            Mark close price

        Raises:
            ValueError: If mark price not available for timestamp
        """
        value = self._provider.get_mark_close(ts_close_ms)
        if value is None:
            raise ValueError(
                f"MARK price not available for ts_close_ms={ts_close_ms}. "
                f"Ensure historical data covers this timestamp."
            )
        return value

    def get_mark_close_safe(self, ts_close_ms: int) -> Optional[float]:
        """
        Get mark close price, returning None if not available.

        Use get_mark_close() for production code that should fail loud.
        """
        return self._provider.get_mark_close(ts_close_ms)

    def get_mark_for_snapshot(self, ts_close_ms: int) -> Tuple[float, str]:
        """
        Get mark price and source for snapshot construction.

        This is the primary interface for the backtest engine.

        Args:
            ts_close_ms: Exec bar close timestamp in milliseconds

        Returns:
            Tuple of (mark_price, mark_price_source)

        Raises:
            ValueError: If mark price not available
        """
        value = self.get_mark_close(ts_close_ms)
        return (value, self._provider.source_name)

    def healthcheck(self) -> HealthCheckResult:
        """
        Check if engine is ready to serve mark prices.

        Returns:
            HealthCheckResult with status and details
        """
        return self._provider.healthcheck()

    def validate(self) -> None:
        """
        Validate engine is ready, raising on failure.

        Call during preflight to fail fast.

        Raises:
            RuntimeError: If health check fails
        """
        result = self.healthcheck()
        if not result.ok:
            raise RuntimeError(
                f"MarkPriceEngine validation failed: {result.message} "
                f"(provider={result.provider_name})"
            )

    def log_resolution(self) -> None:
        """
        Log provider resolution once per run.

        Call after validation, before simulation loop.
        """
        if self._resolution_logged:
            return

        result = self.healthcheck()
        logger.info(
            "MarkPriceEngine resolved: provider=%s, status=%s, details=%s",
            self._provider.source_name,
            "ready" if result.ok else "failed",
            result.details,
        )
        self._resolution_logged = True

    @property
    def provider_name(self) -> str:
        """Get the provider source name."""
        return self._provider.source_name
