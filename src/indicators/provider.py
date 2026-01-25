"""
Unified indicator provider interface.

Provides a common interface for accessing indicator values across backtest and live modes.
This enables the Play/Rule evaluation code to work identically in both environments.

Architecture:
- IndicatorProvider: Protocol defining the common interface
- BacktestIndicatorProvider: Wraps FeedStore arrays for backtest mode
- LiveIndicatorProvider: Wraps LiveIndicatorCache for live mode

Usage:
    # In Play evaluation code:
    def evaluate_condition(provider: IndicatorProvider, bar_idx: int) -> bool:
        ema = provider.get("ema_fast", bar_idx)
        rsi = provider.get("rsi_14", bar_idx)
        return ema > rsi and provider.is_ready("ema_fast")

    # Backtest mode:
    provider = BacktestIndicatorProvider(feed_store, bar_idx=50)

    # Live mode:
    provider = LiveIndicatorProvider(cache)

The provider abstraction ensures:
1. Identical evaluation logic in backtest and live modes
2. Single source of truth for indicator access patterns
3. Clean separation between data storage and access interface
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Protocol, runtime_checkable

import numpy as np

if TYPE_CHECKING:
    from src.backtest.runtime.feed_store import FeedStore


@runtime_checkable
class IndicatorProvider(Protocol):
    """
    Protocol for indicator value access.

    Implemented by both backtest and live adapters to provide a uniform
    interface for indicator value retrieval.
    """

    def get(self, name: str, offset: int = 0) -> float:
        """
        Get indicator value at current bar with optional offset.

        Args:
            name: Indicator name (e.g., "ema_fast", "rsi_14")
            offset: Bars back from current (0 = current, 1 = previous, etc.)

        Returns:
            Indicator value (may be NaN if not ready)

        Raises:
            KeyError: If indicator name not found
        """
        ...

    def has(self, name: str) -> bool:
        """
        Check if indicator is available.

        Args:
            name: Indicator name

        Returns:
            True if indicator exists in this provider
        """
        ...

    def is_ready(self, name: str) -> bool:
        """
        Check if indicator has valid (non-NaN) value at current bar.

        Args:
            name: Indicator name

        Returns:
            True if value is valid (not NaN)
        """
        ...

    @property
    def bar_index(self) -> int:
        """Current bar index in the data."""
        ...

    @property
    def indicator_names(self) -> list[str]:
        """List of all available indicator names."""
        ...


class BacktestIndicatorProvider:
    """
    Indicator provider for backtest mode.

    Wraps FeedStore arrays and provides index-based access.
    The bar_index can be updated to step through the simulation.
    """

    def __init__(self, feed: "FeedStore", bar_idx: int = 0):
        """
        Initialize with FeedStore and starting bar index.

        Args:
            feed: FeedStore with precomputed indicator arrays
            bar_idx: Current bar index (default 0)
        """
        self._feed = feed
        self._bar_idx = bar_idx

    def get(self, name: str, offset: int = 0) -> float:
        """Get indicator value at current bar with optional offset."""
        if name not in self._feed.indicators:
            raise KeyError(f"Indicator '{name}' not found in feed store")

        idx = self._bar_idx - offset
        if idx < 0 or idx >= self._feed.length:
            return np.nan

        return float(self._feed.indicators[name][idx])

    def has(self, name: str) -> bool:
        """Check if indicator is available."""
        return name in self._feed.indicators

    def is_ready(self, name: str) -> bool:
        """Check if indicator has valid value at current bar."""
        if not self.has(name):
            return False
        value = self.get(name)
        return not np.isnan(value)

    @property
    def bar_index(self) -> int:
        """Current bar index."""
        return self._bar_idx

    @bar_index.setter
    def bar_index(self, value: int) -> None:
        """Update current bar index."""
        self._bar_idx = value

    @property
    def indicator_names(self) -> list[str]:
        """List of all available indicator names."""
        return list(self._feed.indicators.keys())

    def step(self) -> None:
        """Advance to next bar."""
        self._bar_idx += 1

    def get_ohlcv(self, field: str, offset: int = 0) -> float:
        """
        Get OHLCV value at current bar with optional offset.

        Args:
            field: One of 'open', 'high', 'low', 'close', 'volume'
            offset: Bars back from current

        Returns:
            OHLCV value
        """
        idx = self._bar_idx - offset
        if idx < 0 or idx >= self._feed.length:
            return np.nan

        arr = getattr(self._feed, field, None)
        if arr is None:
            raise KeyError(f"OHLCV field '{field}' not found")

        return float(arr[idx])


class LiveIndicatorProvider:
    """
    Indicator provider for live/demo mode.

    Wraps LiveIndicatorCache and provides access to the most recent values.
    In live mode, bar_index typically points to the last closed bar.
    """

    def __init__(self, indicators: dict[str, np.ndarray], bar_count: int):
        """
        Initialize with indicator arrays.

        Args:
            indicators: Dict of indicator_name -> numpy array
            bar_count: Number of bars in the arrays
        """
        self._indicators = indicators
        self._bar_count = bar_count

    def get(self, name: str, offset: int = 0) -> float:
        """Get indicator value at current bar with optional offset."""
        if name not in self._indicators:
            raise KeyError(f"Indicator '{name}' not found")

        arr = self._indicators[name]
        idx = len(arr) - 1 - offset  # Most recent is at end

        if idx < 0 or idx >= len(arr):
            return np.nan

        return float(arr[idx])

    def has(self, name: str) -> bool:
        """Check if indicator is available."""
        return name in self._indicators

    def is_ready(self, name: str) -> bool:
        """Check if indicator has valid value at current bar."""
        if not self.has(name):
            return False
        value = self.get(name)
        return not np.isnan(value)

    @property
    def bar_index(self) -> int:
        """Current bar index (last bar)."""
        return self._bar_count - 1 if self._bar_count > 0 else 0

    @property
    def indicator_names(self) -> list[str]:
        """List of all available indicator names."""
        return list(self._indicators.keys())

    @classmethod
    def from_cache(cls, cache: "LiveIndicatorCache") -> "LiveIndicatorProvider":
        """
        Create provider from LiveIndicatorCache.

        Args:
            cache: LiveIndicatorCache instance

        Returns:
            LiveIndicatorProvider wrapping the cache
        """
        return cls(
            indicators=cache._indicators,
            bar_count=cache._bar_count,
        )


# Type alias for type hints
IndicatorProviderType = BacktestIndicatorProvider | LiveIndicatorProvider
