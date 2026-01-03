"""
Simulated Mark Price Provider.

Provides MARK price for backtest/sim mode using historical OHLCV data.
Stage 1: Uses exec bar close price (closed candle only, no lookahead).
"""

from typing import Protocol

import numpy as np

from src.backtest.prices.types import HealthCheckResult, MarkPriceResult


class MarkProvider(Protocol):
    """Protocol for mark price providers."""

    def get_mark_close(self, ts_close_ms: int) -> float | None:
        """Get mark close price at the given exec bar close timestamp."""
        ...

    def healthcheck(self) -> HealthCheckResult:
        """Check if provider is ready to serve mark prices."""
        ...

    @property
    def source_name(self) -> str:
        """Provider source name for logging."""
        ...


class SimMarkProvider:
    """
    Simulated mark price provider for backtest/sim.

    Stage 1 implementation:
    - Uses exec bar close price as mark price
    - Deterministic: same input → same output
    - No lookahead: only uses closed bar data

    The provider receives pre-computed arrays and an index mapping
    to look up mark prices by timestamp.
    """

    SOURCE_NAME = "backtest_exec_close"

    def __init__(
        self,
        ts_close_array: np.ndarray,  # Array of ts_close values (int64, ms)
        close_array: np.ndarray,  # Array of close prices (float64)
    ):
        """
        Initialize with precomputed arrays.

        Args:
            ts_close_array: Array of bar close timestamps (ms since epoch)
            close_array: Array of bar close prices
        """
        if len(ts_close_array) != len(close_array):
            raise ValueError(
                f"Array length mismatch: ts_close={len(ts_close_array)}, "
                f"close={len(close_array)}"
            )

        self._ts_close = ts_close_array
        self._close = close_array
        self._length = len(ts_close_array)

        # Build index lookup for O(1) access
        # Maps ts_close_ms -> array index
        self._ts_to_idx: dict = {}
        for i, ts in enumerate(ts_close_array):
            self._ts_to_idx[int(ts)] = i

    def get_mark_close(self, ts_close_ms: int) -> float | None:
        """
        Get mark close price at the given timestamp.

        Args:
            ts_close_ms: Exec bar close timestamp in milliseconds

        Returns:
            Mark close price, or None if timestamp not found
        """
        idx = self._ts_to_idx.get(ts_close_ms)
        if idx is None:
            return None
        return float(self._close[idx])

    def get_mark_result(self, ts_close_ms: int) -> MarkPriceResult | None:
        """
        Get full mark price result with metadata.

        Args:
            ts_close_ms: Exec bar close timestamp in milliseconds

        Returns:
            MarkPriceResult or None if timestamp not found
        """
        value = self.get_mark_close(ts_close_ms)
        if value is None:
            return None
        return MarkPriceResult(
            value=value,
            source=self.SOURCE_NAME,
            ts_close_ms=ts_close_ms,
        )

    def healthcheck(self) -> HealthCheckResult:
        """Check if provider is ready."""
        if self._length == 0:
            return HealthCheckResult(
                ok=False,
                provider_name=self.SOURCE_NAME,
                message="No data available",
            )

        # Verify we have valid data
        if np.any(np.isnan(self._close)):
            nan_count = int(np.sum(np.isnan(self._close)))
            return HealthCheckResult(
                ok=False,
                provider_name=self.SOURCE_NAME,
                message=f"Data contains {nan_count} NaN values",
                details={"nan_count": nan_count, "total": self._length},
            )

        return HealthCheckResult(
            ok=True,
            provider_name=self.SOURCE_NAME,
            message=f"Ready with {self._length} bars",
            details={"bar_count": self._length},
        )

    @property
    def source_name(self) -> str:
        """Provider source name."""
        return self.SOURCE_NAME

    @property
    def length(self) -> int:
        """Number of available bars."""
        return self._length
