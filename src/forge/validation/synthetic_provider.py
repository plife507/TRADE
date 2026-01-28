"""
Synthetic data provider protocol for DataBuilder injection.

This module enables backtests to run with synthetic data instead of
DuckDB, allowing validation to run through the actual engine code path.

Architecture:
    SyntheticDataProvider (Protocol)
        └── get_ohlcv(symbol, tf, start, end) -> DataFrame
        └── get_1m_quotes(symbol, start, end) -> DataFrame

    SyntheticCandlesProvider (Adapter)
        └── Wraps SyntheticCandles from synthetic_data.py
        └── Implements SyntheticDataProvider protocol

Usage:
    from src.forge.validation.synthetic_data import generate_synthetic_candles
    from src.forge.validation.synthetic_provider import SyntheticCandlesProvider

    candles = generate_synthetic_candles(symbol="BTCUSDT", timeframes=["1m", "15m", "1h"])
    provider = SyntheticCandlesProvider(candles)
    df = provider.get_ohlcv("BTCUSDT", "15m", start, end)
"""

from datetime import datetime
from typing import Protocol

import pandas as pd

from src.forge.validation.synthetic_data import SyntheticCandles


class SyntheticDataProvider(Protocol):
    """
    Protocol for providing synthetic data to DataBuilder.

    Mirrors the HistoricalDataStore interface for drop-in replacement.
    """

    def get_ohlcv(
        self,
        symbol: str,
        tf: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """
        Return OHLCV DataFrame for the given parameters.

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            tf: Timeframe string (e.g., "15m", "1h")
            start: Start datetime
            end: End datetime

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        ...

    def get_1m_quotes(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """
        Return 1m quote data for intrabar evaluation.

        Args:
            symbol: Trading symbol
            start: Start datetime
            end: End datetime

        Returns:
            DataFrame with 1m OHLCV data
        """
        ...


class SyntheticCandlesProvider:
    """
    Adapter from SyntheticCandles to SyntheticDataProvider protocol.

    Wraps a SyntheticCandles object and provides the same interface
    as HistoricalDataStore.get_ohlcv() for seamless injection.
    """

    def __init__(self, candles: SyntheticCandles):
        """
        Initialize with pre-generated synthetic candles.

        Args:
            candles: SyntheticCandles object with multi-TF data
        """
        self._candles = candles

    @property
    def symbol(self) -> str:
        """Get the symbol from the synthetic candles."""
        return self._candles.symbol

    @property
    def available_timeframes(self) -> list[str]:
        """Get list of available timeframes."""
        return list(self._candles.timeframes.keys())

    def get_ohlcv(
        self,
        symbol: str,
        tf: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """
        Return OHLCV DataFrame for the given parameters.

        Filters the synthetic data to the requested time range.
        Symbol is validated but synthetic data uses a single symbol.

        Args:
            symbol: Trading symbol (validated against candles.symbol)
            tf: Timeframe string
            start: Start datetime
            end: End datetime

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume

        Raises:
            ValueError: If symbol doesn't match or TF not available
        """
        # Validate symbol matches
        if symbol != self._candles.symbol:
            raise ValueError(
                f"SYMBOL_MISMATCH: Requested {symbol} but synthetic data is for "
                f"{self._candles.symbol}. Generate synthetic data for the correct symbol."
            )

        # Validate TF exists
        if tf not in self._candles.timeframes:
            raise ValueError(
                f"TIMEFRAME_NOT_AVAILABLE: Requested {tf} but synthetic data only has "
                f"{list(self._candles.timeframes.keys())}. "
                f"Generate synthetic data with required timeframes."
            )

        # Get the DataFrame for this TF
        df = self._candles.get_tf(tf).copy()

        # Filter to requested time range
        mask = (df["timestamp"] >= start) & (df["timestamp"] <= end)
        filtered = df[mask].reset_index(drop=True)

        if filtered.empty:
            raise ValueError(
                f"NO_DATA_IN_RANGE: No synthetic data for {symbol} {tf} "
                f"between {start} and {end}. "
                f"Synthetic data range: {df['timestamp'].iloc[0]} to {df['timestamp'].iloc[-1]}"
            )

        return filtered

    def get_1m_quotes(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """
        Return 1m quote data for intrabar evaluation.

        Args:
            symbol: Trading symbol
            start: Start datetime
            end: End datetime

        Returns:
            DataFrame with 1m OHLCV data

        Raises:
            ValueError: If 1m data not available in synthetic candles
        """
        return self.get_ohlcv(symbol, "1m", start, end)

    def has_tf(self, tf: str) -> bool:
        """Check if timeframe is available in synthetic data."""
        return tf in self._candles.timeframes

    def get_data_range(self, tf: str) -> tuple[datetime, datetime]:
        """
        Get the time range for a timeframe.

        Args:
            tf: Timeframe string

        Returns:
            Tuple of (start, end) datetimes

        Raises:
            ValueError: If TF not available
        """
        if tf not in self._candles.timeframes:
            raise ValueError(f"TF {tf} not in synthetic data")

        df = self._candles.get_tf(tf)
        return df["timestamp"].iloc[0], df["timestamp"].iloc[-1]

    def to_dict(self) -> dict:
        """Return metadata about this provider."""
        return {
            "type": "SyntheticCandlesProvider",
            "symbol": self._candles.symbol,
            "timeframes": list(self._candles.timeframes.keys()),
            "bar_counts": self._candles.bar_counts,
            "seed": self._candles.seed,
            "pattern": self._candles.pattern,
            "data_hash": self._candles.data_hash,
        }
