"""
Data tools - common helpers and constants.

Split from data_tools.py for maintainability.
"""

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from .shared import ToolResult, _get_historical_store
from ..config.constants import DataEnv, DEFAULT_DATA_ENV
from ..utils.datetime_utils import (
    MAX_QUERY_RANGE_DAYS,
    normalize_datetime,
    validate_time_range,
    normalize_time_range_params,
)

_normalize_datetime = normalize_datetime
_validate_time_range = validate_time_range
_normalize_time_range_params = normalize_time_range_params


# ==================== CONSTANTS ====================

# Default timeframe groups for full history sync
TF_GROUP_LOW = ["1m", "5m", "15m"]      # LTF (high-resolution)
TF_GROUP_MID = ["1h", "4h"]             # MTF
TF_GROUP_HIGH = ["1d"]                  # HTF

# All standard timeframes
ALL_TIMEFRAMES = TF_GROUP_LOW + TF_GROUP_MID + TF_GROUP_HIGH

# Maximum chunk size for range syncing (days)
MAX_CHUNK_DAYS = 90

# Safety cap to prevent accidental massive pulls (years)
DEFAULT_MAX_HISTORY_YEARS = 5


def _sync_range_chunked(
    store,
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    chunk_days: int = MAX_CHUNK_DAYS,
) -> int:
    """
    Sync a date range in chunks to handle long histories safely.
    
    Returns total candles synced.
    """
    total_synced = 0
    current_start = start
    
    while current_start < end:
        chunk_end = min(current_start + timedelta(days=chunk_days), end)
        
        # Sync this chunk
        result = store.sync_range(
            symbols=[symbol],
            start=current_start,
            end=chunk_end,
            timeframes=[timeframe],
        )
        
        # Accumulate results
        key = f"{symbol}_{timeframe}"
        chunk_count = result.get(key, 0)
        if chunk_count > 0:
            total_synced += chunk_count
        
        current_start = chunk_end
    
    return total_synced




def _days_to_period(days: int) -> str:
    """Convert number of days to a period string."""
    if days >= 365:
        years = max(1, days // 365)
        return f"{years}Y"
    elif days >= 30:
        months = max(1, days // 30)
        return f"{months}M"
    elif days >= 7:
        weeks = max(1, days // 7)
        return f"{weeks}W"
    else:
        return f"{max(1, days)}D"




def _build_extremes_metadata(store, symbol: str, timeframes: list[str]) -> dict[str, Any]:
    """
    Build extremes/bounds metadata for a symbol after sync.
    
    Returns metadata about DB coverage for OHLCV (per tf), funding, and OI.
    """
    extremes = {
        "symbol": symbol,
        "ohlcv": {},
        "funding": {},
        "open_interest": {},
    }
    
    # OHLCV per timeframe
    for tf in timeframes:
        try:
            stats = store.conn.execute(f"""
                SELECT 
                    MIN(timestamp) as earliest_ts,
                    MAX(timestamp) as latest_ts,
                    COUNT(*) as row_count
                FROM {store.table_ohlcv}
                WHERE symbol = ? AND timeframe = ?
            """, [symbol, tf]).fetchone()
            
            if stats and stats[2] > 0:
                extremes["ohlcv"][tf] = {
                    "earliest_ts": stats[0].isoformat() if stats[0] else None,
                    "latest_ts": stats[1].isoformat() if stats[1] else None,
                    "row_count": stats[2],
                }
        except Exception:
            pass
    
    # Funding
    try:
        stats = store.conn.execute(f"""
            SELECT 
                MIN(timestamp) as earliest_ts,
                MAX(timestamp) as latest_ts,
                COUNT(*) as record_count
            FROM {store.table_funding}
            WHERE symbol = ?
        """, [symbol]).fetchone()
        
        if stats and stats[2] > 0:
            extremes["funding"] = {
                "earliest_ts": stats[0].isoformat() if stats[0] else None,
                "latest_ts": stats[1].isoformat() if stats[1] else None,
                "record_count": stats[2],
            }
    except Exception:
        pass
    
    # Open Interest
    try:
        stats = store.conn.execute(f"""
            SELECT 
                MIN(timestamp) as earliest_ts,
                MAX(timestamp) as latest_ts,
                COUNT(*) as record_count
            FROM {store.table_oi}
            WHERE symbol = ?
        """, [symbol]).fetchone()
        
        if stats and stats[2] > 0:
            extremes["open_interest"] = {
                "earliest_ts": stats[0].isoformat() if stats[0] else None,
                "latest_ts": stats[1].isoformat() if stats[1] else None,
                "record_count": stats[2],
            }
    except Exception:
        pass
    
    return extremes




def _persist_extremes_to_db(
    store,
    symbol: str,
    extremes: dict[str, Any],
    launch_time: datetime | None,
    source: str,
):
    """
    Persist extremes metadata to DuckDB table.
    
    Args:
        store: HistoricalDataStore instance
        symbol: Trading symbol
        extremes: Extremes dict from _build_extremes_metadata
        launch_time: Resolved launch time from Bybit API
        source: Source identifier (e.g., "full_from_launch")
    """
    from datetime import datetime as dt
    
    # OHLCV per timeframe
    for tf, tf_data in extremes.get("ohlcv", {}).items():
        earliest = None
        latest = None
        if tf_data.get("earliest_ts"):
            try:
                earliest = dt.fromisoformat(tf_data["earliest_ts"])
            except (ValueError, TypeError):
                pass
        if tf_data.get("latest_ts"):
            try:
                latest = dt.fromisoformat(tf_data["latest_ts"])
            except (ValueError, TypeError):
                pass
        
        store.update_extremes(
            symbol=symbol,
            data_type="ohlcv",
            timeframe=tf,
            earliest_ts=earliest,
            latest_ts=latest,
            row_count=tf_data.get("row_count", 0),
            gap_count=0,  # Gap count would need separate detection
            launch_time=launch_time,
            source=source,
        )
    
    # Funding
    funding_data = extremes.get("funding", {})
    if funding_data:
        earliest = None
        latest = None
        if funding_data.get("earliest_ts"):
            try:
                earliest = dt.fromisoformat(funding_data["earliest_ts"])
            except (ValueError, TypeError):
                pass
        if funding_data.get("latest_ts"):
            try:
                latest = dt.fromisoformat(funding_data["latest_ts"])
            except (ValueError, TypeError):
                pass
        
        store.update_extremes(
            symbol=symbol,
            data_type="funding",
            timeframe=None,
            earliest_ts=earliest,
            latest_ts=latest,
            row_count=funding_data.get("record_count", 0),
            gap_count=0,
            launch_time=launch_time,
            source=source,
        )
    
    # Open Interest
    oi_data = extremes.get("open_interest", {})
    if oi_data:
        earliest = None
        latest = None
        if oi_data.get("earliest_ts"):
            try:
                earliest = dt.fromisoformat(oi_data["earliest_ts"])
            except (ValueError, TypeError):
                pass
        if oi_data.get("latest_ts"):
            try:
                latest = dt.fromisoformat(oi_data["latest_ts"])
            except (ValueError, TypeError):
                pass
        
        store.update_extremes(
            symbol=symbol,
            data_type="open_interest",
            timeframe=None,
            earliest_ts=earliest,
            latest_ts=latest,
            row_count=oi_data.get("record_count", 0),
            gap_count=0,
            launch_time=launch_time,
            source=source,
        )


