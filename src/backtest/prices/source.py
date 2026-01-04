"""
Price Source Protocol.

Unified interface for backtest/demo/live price feeds.
Engine uses PriceSource to abstract away data origin.

Architecture Principle: Pure Protocol
- PriceSource defines WHAT to fetch
- Engine decides WHEN to call
- Implementations are stateless data fetchers
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Protocol, runtime_checkable

import numpy as np

from src.backtest.prices.types import HealthCheckResult

if TYPE_CHECKING:
    import pandas as pd


@dataclass(frozen=True, slots=True)
class PricePoint:
    """
    Single price observation at a point in time.

    Used for mark price queries and tick-level data.

    Attributes:
        ts: Timestamp (UTC)
        mark: Mark price (used for PnL, margin calculations)
        last: Last traded price (may differ from mark)
        mid: Mid price ((bid + ask) / 2)
        bid: Best bid price (None if not available)
        ask: Best ask price (None if not available)
    """

    ts: datetime
    mark: float
    last: float | None = None
    mid: float | None = None
    bid: float | None = None
    ask: float | None = None

    @classmethod
    def from_mark(cls, ts: datetime, mark: float) -> PricePoint:
        """Create PricePoint with only mark price (backtest mode)."""
        return cls(ts=ts, mark=mark, last=mark, mid=mark)


@runtime_checkable
class PriceSource(Protocol):
    """
    Protocol for price data sources.

    Unified interface for:
    - Backtest: Historical data from DuckDB
    - Demo: Demo API WebSocket
    - Live: Live API WebSocket

    All implementations must be stateless data fetchers.
    Engine orchestrates calls and caches results.
    """

    @property
    def source_name(self) -> str:
        """Unique name identifying this source (e.g., 'backtest_duckdb', 'live_ws')."""
        ...

    def get_mark_price(self, symbol: str, ts: datetime) -> float | None:
        """
        Get mark price at a specific timestamp.

        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            ts: Timestamp (UTC)

        Returns:
            Mark price or None if not available
        """
        ...

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> "pd.DataFrame":
        """
        Get OHLCV data for a symbol and timeframe.

        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            timeframe: Candle timeframe (e.g., '1m', '15m', '1h')
            start: Start timestamp (inclusive, UTC)
            end: End timestamp (inclusive, UTC)

        Returns:
            DataFrame with columns: ts_open, ts_close, open, high, low, close, volume
            Index is sequential (0, 1, 2, ...)
            Sorted by ts_open ascending

        Raises:
            ValueError: If symbol or timeframe is invalid
            DataNotAvailableError: If data is not available for range
        """
        ...

    def get_1m_marks(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> np.ndarray:
        """
        Get 1-minute mark prices for a range.

        Used for intra-bar TP/SL checking in the 1m evaluation loop.

        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            start: Start timestamp (inclusive, UTC)
            end: End timestamp (inclusive, UTC)

        Returns:
            1D array of mark prices (float64), one per minute
            Length = (end - start) in minutes + 1

        Raises:
            DataNotAvailableError: If 1m data is not available
        """
        ...

    def healthcheck(self) -> HealthCheckResult:
        """
        Check if source is ready to serve data.

        Returns:
            HealthCheckResult with status and diagnostics
        """
        ...


class DataNotAvailableError(Exception):
    """Raised when requested data is not available from the source."""

    def __init__(
        self,
        symbol: str,
        timeframe: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        reason: str = "Data not available",
    ):
        self.symbol = symbol
        self.timeframe = timeframe
        self.start = start
        self.end = end
        self.reason = reason

        parts = [f"symbol={symbol}"]
        if timeframe:
            parts.append(f"tf={timeframe}")
        if start and end:
            parts.append(f"range={start} to {end}")

        super().__init__(f"{reason}: {', '.join(parts)}")
