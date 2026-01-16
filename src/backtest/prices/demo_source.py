"""
Demo Price Source.

Implements PriceSource protocol for demo mode (api-demo.bybit.com).
Uses HistoricalDataStore with env="demo" for historical/warm-up data.

Architecture:
- Wraps HistoricalDataStore(env="demo") for historical data
- Future: Add WebSocket for real-time price updates
- Uses market_data_demo.duckdb for warm-up data

Usage:
    from src.backtest.prices.demo_source import DemoPriceSource

    source = DemoPriceSource()
    df = source.get_ohlcv("BTCUSDT", "15m", start, end)
    mark = source.get_mark_price("BTCUSDT", ts)
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from src.backtest.prices.source import PriceSource, DataNotAvailableError
from src.backtest.prices.types import HealthCheckResult
from src.data.historical_data_store import get_historical_store

if TYPE_CHECKING:
    pass


class DemoPriceSource:
    """
    Price source for demo mode.

    Uses HistoricalDataStore(env="demo") backed by market_data_demo.duckdb.
    Data is synced from api-demo.bybit.com (demo/testnet API).

    For demo trading warm-up:
    - Historical data loaded from market_data_demo.duckdb
    - Indicator warm-up computed from historical bars
    - Real-time updates (future) via WebSocket

    Use demo mode for paper trading before going live.
    """

    SOURCE_NAME = "demo_duckdb"

    def __init__(self) -> None:
        """Initialize demo source."""
        self._store = get_historical_store(env="demo")
        # Cache for 1m data used by get_mark_price
        self._1m_cache: dict[str, pd.DataFrame] = {}

    @property
    def source_name(self) -> str:
        """Unique name identifying this source."""
        return self.SOURCE_NAME

    @property
    def env(self) -> str:
        """Data environment."""
        return "demo"

    def get_mark_price(self, symbol: str, ts: datetime) -> float | None:
        """
        Get mark price at a specific timestamp.

        Uses 1m close price as mark price.
        Returns None if data not available.

        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            ts: Timestamp (UTC)

        Returns:
            Mark price or None if not available
        """
        df = self._get_1m_data(symbol)
        if df is None or df.empty:
            return None

        ts_naive = ts.replace(tzinfo=None) if ts.tzinfo else ts

        mask = df["ts_close"] <= ts_naive
        if not mask.any():
            return None

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
                reason="No data found in demo store",
            )

        # Normalize column names
        df = df.rename(columns={"timestamp": "ts_open"})
        tf_minutes = self._parse_timeframe_minutes(timeframe)
        df["ts_close"] = df["ts_open"] + pd.Timedelta(minutes=tf_minutes)
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

        Returns:
            HealthCheckResult with status and diagnostics
        """
        try:
            conn = self._store.conn
            if conn is None:
                return HealthCheckResult(
                    ok=False,
                    provider_name=self.SOURCE_NAME,
                    message="DuckDB connection not available",
                )

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

            row_count = conn.execute(
                f"SELECT COUNT(*) FROM {table_name}"
            ).fetchone()[0]

            return HealthCheckResult(
                ok=True,
                provider_name=self.SOURCE_NAME,
                message=f"Ready with {row_count:,} OHLCV rows (demo env)",
                details={
                    "env": "demo",
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
                df = self._store.get_ohlcv(symbol, "1m")
                if df is not None and not df.empty:
                    df = df.rename(columns={"timestamp": "ts_open"})
                    df["ts_close"] = df["ts_open"] + pd.Timedelta(minutes=1)
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
