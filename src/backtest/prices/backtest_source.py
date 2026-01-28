"""
Backtest Price Source.

Implements PriceSource protocol using HistoricalDataStore (DuckDB).
This is the production implementation for backtest mode.

Architecture Principle: Pure Data Fetch
- Wraps HistoricalDataStore for data access
- Stateless: each call fetches fresh data
- Engine caches results as needed
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from src.backtest.prices.source import PriceSource, DataNotAvailableError
from src.backtest.prices.types import HealthCheckResult

if TYPE_CHECKING:
    from src.data.historical_data_store import HistoricalDataStore


class BacktestPriceSource:
    """
    Price source implementation for backtest mode.

    Wraps HistoricalDataStore to implement PriceSource protocol.
    All data comes from DuckDB historical data.

    Usage:
        from src.data.historical_data_store import get_historical_store
        from src.backtest.prices import BacktestPriceSource

        store = get_historical_store(env="live")
        source = BacktestPriceSource(store)

        # Get OHLCV data
        df = source.get_ohlcv("BTCUSDT", "15m", start, end)

        # Get mark price at timestamp
        mark = source.get_mark_price("BTCUSDT", ts)
    """

    SOURCE_NAME = "backtest_duckdb"

    def __init__(self, store: "HistoricalDataStore"):
        """
        Initialize with a HistoricalDataStore.

        Args:
            store: HistoricalDataStore instance for data access
        """
        self._store = store
        # Cache for 1m data used by get_mark_price and get_1m_marks
        self._1m_cache: dict[str, pd.DataFrame] = {}
        # G2-1: Track fallback warnings to avoid spam
        self._fallback_warnings_issued: set[str] = set()

    @property
    def source_name(self) -> str:
        """Unique name identifying this source."""
        return self.SOURCE_NAME

    @property
    def env(self) -> str:
        """Data environment (live/demo)."""
        return self._store.env

    def get_mark_price(
        self,
        symbol: str,
        ts: datetime,
        fallback_tf: str | None = None,
        fallback_close: float | None = None,
    ) -> float | None:
        """
        Get mark price at a specific timestamp.

        Uses 1m close price as mark price.
        G2-1: Falls back to exec-TF close if 1m unavailable, with warning.

        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            ts: Timestamp (UTC)
            fallback_tf: Optional fallback timeframe for warning message
            fallback_close: Optional fallback close price if 1m unavailable

        Returns:
            Mark price or None if not available
        """
        # Get 1m data for this symbol (cached)
        df = self._get_1m_data(symbol)
        if df is None or df.empty:
            # G2-1: Fallback to exec-TF close if provided
            if fallback_close is not None:
                fallback_key = f"{symbol}_1m_fallback"
                if fallback_key not in self._fallback_warnings_issued:
                    import logging
                    logging.getLogger(__name__).warning(
                        f"G2-1: 1m data unavailable for {symbol}, "
                        f"using {fallback_tf or 'exec-TF'} close as mark price fallback. "
                        "This may affect simulation accuracy for SL/TP/liquidation."
                    )
                    self._fallback_warnings_issued.add(fallback_key)
                return fallback_close
            return None

        # Find the bar that closes at or before ts
        # ts_close column is the close timestamp
        ts_naive = ts.replace(tzinfo=None) if ts.tzinfo else ts

        # Look for exact match on close timestamp
        mask = df["ts_close"] <= ts_naive
        if not mask.any():
            # G2-1: Fallback to exec-TF close if provided
            if fallback_close is not None:
                return fallback_close
            return None

        # Get the most recent bar at or before ts
        idx = df.loc[mask, "ts_close"].idxmax()
        return float(df.loc[idx, "close"])

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """
        Get OHLCV data for a symbol and timeframe.

        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            timeframe: Candle timeframe (e.g., '1m', '15m', '1h')
            start: Start timestamp (inclusive, UTC)
            end: End timestamp (inclusive, UTC)

        Returns:
            DataFrame with columns: ts_open, ts_close, open, high, low, close, volume

        Raises:
            DataNotAvailableError: If data is not available for range
        """
        # Strip timezone if present (DuckDB stores naive datetimes)
        start_naive = start.replace(tzinfo=None) if start.tzinfo else start
        end_naive = end.replace(tzinfo=None) if end.tzinfo else end

        try:
            df = self._store.get_ohlcv(
                symbol=symbol,
                tf=timeframe,
                start=start_naive,
                end=end_naive,
            )
        except Exception as e:
            raise DataNotAvailableError(
                symbol=symbol,
                timeframe=timeframe,
                start=start,
                end=end,
                reason=str(e),
            ) from e

        if df is None or df.empty:
            raise DataNotAvailableError(
                symbol=symbol,
                timeframe=timeframe,
                start=start,
                end=end,
                reason="No data found in store",
            )

        # Normalize column names to standard format
        # HistoricalDataStore returns: timestamp, open, high, low, close, volume
        # We need: ts_open, ts_close, open, high, low, close, volume
        df = df.rename(columns={"timestamp": "ts_open"})

        # Add ts_close (computed from ts_open + timeframe)
        tf_minutes = self._parse_timeframe_minutes(timeframe)
        df["ts_close"] = df["ts_open"] + pd.Timedelta(minutes=tf_minutes)

        # Ensure sorted by ts_open
        df = df.sort_values("ts_open").reset_index(drop=True)

        return df

    def get_1m_marks(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> np.ndarray:
        """
        Get 1-minute mark prices for a range.

        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            start: Start timestamp (inclusive, UTC)
            end: End timestamp (inclusive, UTC)

        Returns:
            1D array of mark prices (float64), one per minute

        Raises:
            DataNotAvailableError: If 1m data is not available
        """
        df = self.get_ohlcv(symbol, "1m", start, end)
        return df["close"].values.astype(np.float64)

    def healthcheck(self) -> HealthCheckResult:
        """
        Check if source is ready to serve data.

        Verifies DuckDB connection and table existence.

        Returns:
            HealthCheckResult with status and diagnostics
        """
        try:
            # Check if store is connected and has tables
            conn = self._store.conn
            if conn is None:
                return HealthCheckResult(
                    ok=False,
                    provider_name=self.SOURCE_NAME,
                    message="DuckDB connection not available",
                )

            # Check if OHLCV table exists
            table_name = self._store.table_ohlcv
            result = conn.execute(
                f"SELECT COUNT(*) FROM information_schema.tables WHERE table_name = '{table_name}'"
            ).fetchone()

            if result[0] == 0:
                return HealthCheckResult(
                    ok=False,
                    provider_name=self.SOURCE_NAME,
                    message=f"OHLCV table '{table_name}' does not exist",
                )

            # Get row count for diagnostics
            row_count = conn.execute(
                f"SELECT COUNT(*) FROM {table_name}"
            ).fetchone()[0]

            return HealthCheckResult(
                ok=True,
                provider_name=self.SOURCE_NAME,
                message=f"Ready with {row_count:,} OHLCV rows",
                details={
                    "env": self._store.env,
                    "table": table_name,
                    "row_count": row_count,
                },
            )

        except Exception as e:
            return HealthCheckResult(
                ok=False,
                provider_name=self.SOURCE_NAME,
                message=f"Healthcheck failed: {e}",
            )

    def _get_1m_data(self, symbol: str) -> pd.DataFrame | None:
        """Get cached 1m data for a symbol."""
        if symbol not in self._1m_cache:
            try:
                # Load all available 1m data for this symbol
                df = self._store.get_ohlcv(symbol, "1m")
                if df is not None and not df.empty:
                    # Normalize and cache
                    df = df.rename(columns={"timestamp": "ts_open"})
                    tf_minutes = 1
                    df["ts_close"] = df["ts_open"] + pd.Timedelta(minutes=tf_minutes)
                    df = df.sort_values("ts_open").reset_index(drop=True)
                    self._1m_cache[symbol] = df
                else:
                    return None
            except Exception:
                return None
        return self._1m_cache.get(symbol)

    def clear_cache(self) -> None:
        """Clear the 1m data cache."""
        self._1m_cache.clear()

    @staticmethod
    def _parse_timeframe_minutes(tf: str) -> int:
        """Parse timeframe string to minutes (Bybit intervals only)."""
        # Bybit intervals: 1,3,5,15,30,60,120,240,360,720,D,W,M
        tf_map = {
            "1m": 1,
            "3m": 3,
            "5m": 5,
            "15m": 15,
            "30m": 30,
            "1h": 60,
            "2h": 120,
            "4h": 240,
            "6h": 360,
            "12h": 720,
            "D": 1440,
            "W": 10080,
            "M": 43200,
        }
        if tf not in tf_map:
            raise ValueError(f"Unknown timeframe: {tf}. Use Bybit format.")
        return tf_map[tf]


# Type check: verify BacktestPriceSource implements PriceSource
def _verify_protocol() -> None:
    """Verify BacktestPriceSource implements PriceSource protocol."""
    from src.backtest.prices.source import PriceSource
    source: PriceSource = BacktestPriceSource(None)  # type: ignore
    _ = source  # Silence unused variable warning


# Don't run at import time, just for static type checking
# _verify_protocol()
