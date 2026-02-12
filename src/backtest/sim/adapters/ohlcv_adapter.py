"""
OHLCV data adapter.

Converts DuckDB/pandas OHLCV rows to Bar objects.

Handles:
- Dict rows from DuckDB
- pandas Series rows
- Timestamp parsing
- Data validation
- ts_open/ts_close computation
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

# Import canonical Bar from runtime
from ...runtime.types import Bar as CanonicalBar
from ...runtime.timeframe import tf_duration


def adapt_ohlcv_row_canonical(
    row: dict[str, Any] | "pd.Series",
    *,
    symbol: str,
    tf: str,
) -> CanonicalBar:
    """
    Convert a single OHLCV row to a canonical Bar with ts_open/ts_close.
    
    This is the Phase 1+ canonical adapter. It produces the runtime.types.Bar
    with explicit ts_open and ts_close timestamps.
    
    Args:
        row: OHLCV data with keys: timestamp, open, high, low, close, volume
        symbol: Trading symbol (e.g., "SOLUSDT")
        tf: Timeframe string (e.g., "5m", "1h")
        
    Returns:
        CanonicalBar instance with ts_open/ts_close
        
    Raises:
        KeyError: If required columns are missing
        ValueError: If data is invalid
    """
    # Handle pandas Series
    if hasattr(row, "to_dict"):
        row = dict(row)
    
    # Parse timestamp (this is ts_open from DuckDB)
    ts_open = row["timestamp"]
    if isinstance(ts_open, str):
        ts_open = datetime.fromisoformat(ts_open)
    elif hasattr(ts_open, "to_pydatetime"):
        # pandas Timestamp
        ts_open = ts_open.to_pydatetime()  # type: ignore[union-attr]

    # Ensure ts_open is a datetime for type safety
    assert isinstance(ts_open, datetime)

    # Compute ts_close
    ts_close = ts_open + tf_duration(tf)
    
    # Validate OHLC consistency
    o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
    
    if h < l:
        raise ValueError(f"Invalid OHLC: high ({h}) < low ({l}) at {ts_open}")
    if h < o or h < c:
        raise ValueError(f"Invalid OHLC: high ({h}) < open ({o}) or close ({c}) at {ts_open}")
    if l > o or l > c:
        raise ValueError(f"Invalid OHLC: low ({l}) > open ({o}) or close ({c}) at {ts_open}")
    
    return CanonicalBar(
        symbol=symbol,
        tf=tf,
        ts_open=ts_open,
        ts_close=ts_close,
        open=o,
        high=h,
        low=l,
        close=c,
        volume=float(row["volume"]),
        turnover=row.get("turnover"),
    )


def adapt_ohlcv_dataframe_canonical(
    df: "pd.DataFrame",
    *,
    symbol: str,
    tf: str,
) -> list[CanonicalBar]:
    """
    Convert a pandas DataFrame to a list of canonical Bars.
    
    Args:
        df: DataFrame with columns: timestamp, open, high, low, close, volume
        symbol: Trading symbol
        tf: Timeframe string
        
    Returns:
        List of CanonicalBar instances with ts_open/ts_close
        
    Raises:
        KeyError: If required columns are missing
    """
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise KeyError(f"Missing required columns: {missing}")
    
    bars = []
    for _, row in df.iterrows():
        bars.append(adapt_ohlcv_row_canonical(row, symbol=symbol, tf=tf))
    
    return bars


def build_bar_close_ts_map(
    df: "pd.DataFrame",
    *,
    symbol: str,
    tf: str,
) -> dict[datetime, CanonicalBar]:
    """
    Build a mapping from ts_close -> Bar for data-driven close detection.
    
    Used by TimeframeCache to determine when a TF has closed.
    
    Args:
        df: DataFrame with OHLCV data
        symbol: Trading symbol
        tf: Timeframe string
        
    Returns:
        Dict mapping ts_close datetime to CanonicalBar
    """
    bars = adapt_ohlcv_dataframe_canonical(df, symbol=symbol, tf=tf)
    return {bar.ts_close: bar for bar in bars}


# Convenience aliases for cleaner imports
adapt_ohlcv_row = adapt_ohlcv_row_canonical
adapt_ohlcv_dataframe = adapt_ohlcv_dataframe_canonical
