"""
OHLCV data loader for visualization.

Loads OHLCV data from DuckDB for multiple timeframes.
"""

from datetime import datetime
from pathlib import Path
from typing import Any
import json

import pandas as pd

from .timestamp_utils import to_unix_timestamp


def _parse_timestamp(ts_str: str | None) -> datetime | None:
    """Parse ISO timestamp string to datetime."""
    if ts_str is None:
        return None
    try:
        # Handle both ISO formats: with and without 'T' separator
        if "T" in ts_str:
            return datetime.fromisoformat(ts_str)
        else:
            return datetime.fromisoformat(ts_str.replace(" ", "T"))
    except ValueError:
        return None


def load_ohlcv_from_duckdb(
    symbol: str,
    tf: str,
    start_ts: str | None = None,
    end_ts: str | None = None,
) -> pd.DataFrame | None:
    """
    Load OHLCV from DuckDB historical data store.

    Args:
        symbol: Trading symbol (e.g., BTCUSDT)
        tf: Timeframe (e.g., 15m, 1h)
        start_ts: Start timestamp ISO string
        end_ts: End timestamp ISO string

    Returns:
        DataFrame with OHLCV columns, or None if error
    """
    try:
        from src.data.historical_data_store import HistoricalDataStore

        store = HistoricalDataStore()

        # Convert ISO strings to datetime objects
        start_dt = _parse_timestamp(start_ts)
        end_dt = _parse_timestamp(end_ts)

        df = store.get_ohlcv(
            symbol=symbol,
            tf=tf,
            start=start_dt,
            end=end_dt,
        )

        if df is None or df.empty:
            return None

        return df

    except Exception as e:
        # Log the error for debugging
        import logging
        logging.getLogger(__name__).warning(f"OHLCV load failed: {e}")
        return None


def load_ohlcv_for_timeframes(
    symbol: str,
    timeframes: set[str],
    start_ts: str | None = None,
    end_ts: str | None = None,
) -> dict[str, pd.DataFrame]:
    """
    Load OHLCV for multiple timeframes from DuckDB.

    This is the primary function for MTF visualization support.
    Queries DuckDB once per unique timeframe.

    Args:
        symbol: Trading symbol (e.g., BTCUSDT)
        timeframes: Set of timeframe strings (e.g., {"5m", "1h", "4h"})
        start_ts: Start timestamp ISO string
        end_ts: End timestamp ISO string

    Returns:
        Dict mapping timeframe -> DataFrame
        Missing timeframes are omitted from result
    """
    result = {}

    for tf in timeframes:
        df = load_ohlcv_from_duckdb(
            symbol=symbol,
            tf=tf,
            start_ts=start_ts,
            end_ts=end_ts,
        )
        if df is not None:
            result[tf] = df

    return result


def ohlcv_df_to_chart_data(df: pd.DataFrame) -> list[dict[str, Any]]:
    """
    Convert OHLCV DataFrame to chart-ready list of dicts.

    Args:
        df: DataFrame with OHLCV columns

    Returns:
        List of dicts with Unix timestamps (seconds)
    """
    result = []

    for _, row in df.iterrows():
        # Handle timestamp column naming variations
        ts = row.get("timestamp") or row.get("ts_close") or row.get("time")
        if ts is None:
            continue

        # Convert to Unix seconds using shared utility
        unix_ts = to_unix_timestamp(ts)
        if unix_ts is None:
            continue

        candle = {
            "time": unix_ts,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
        }

        # Add volume if available
        if "volume" in df.columns:
            candle["volume"] = float(row["volume"])

        result.append(candle)

    return result


def get_run_metadata(run_path: Path) -> dict[str, Any] | None:
    """Get run metadata from result.json."""
    result_path = run_path / "result.json"
    if not result_path.exists():
        return None

    try:
        with open(result_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None
