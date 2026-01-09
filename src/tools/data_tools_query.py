"""
Data tools - query and composite tools.

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


# Import tools for composite operations
from .data_tools_sync import sync_symbols_tool, sync_funding_tool, sync_open_interest_tool, fill_gaps_tool


def get_funding_history_tool(
    symbol: str,
    period: str | None = None,
    start: datetime | str | None = None,
    end: datetime | str | None = None,
    env: DataEnv = DEFAULT_DATA_ENV,
) -> ToolResult:
    """
    Get funding rate history for a symbol from DuckDB.
    
    Accepts either a relative 'period' OR explicit 'start'/'end' times.
    Start/end can be datetime objects or ISO-format strings (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS).
    
    Args:
        symbol: Trading symbol (required)
        period: Period string (e.g., "1M", "3M") - alternative to start/end
        start: Start datetime or ISO string (e.g., "2024-01-01" or "2024-01-01T00:00:00")
        end: End datetime or ISO string (e.g., "2024-06-01" or "2024-06-01T23:59:59")
        env: Data environment ("live" or "demo"). Defaults to "live".
    
    Returns:
        ToolResult with funding rate data including:
        - records: List of {timestamp, funding_rate} dicts
        - count: Number of records
        - time_range: Metadata about the queried range
    
    Note:
        Maximum range is 365 days when using start/end to prevent bloat.
        Use 'period' for convenience (e.g., "1M" = last month).
    """
    if not symbol:
        return ToolResult(success=False, error="Symbol required")
    
    # Normalize and validate time range
    start_dt, end_dt, range_error = _normalize_time_range_params(start, end)
    if range_error:
        return ToolResult(success=False, symbol=symbol, error=range_error)
    
    try:
        store = _get_historical_store(env=env)
        df = store.get_funding(symbol, period=period, start=start_dt, end=end_dt)
        
        if df.empty:
            return ToolResult(
                success=True,
                symbol=symbol,
                message=f"[{env.upper()}] No funding data for {symbol}",
                data={"records": [], "count": 0, "env": env},
                source="duckdb",
            )
        
        # Convert to list of dicts for JSON serialization
        records = df.to_dict(orient="records")
        
        # Extract time range metadata from actual data
        first_ts = None
        last_ts = None
        
        # Convert timestamps to ISO strings and track range
        for r in records:
            if "timestamp" in r:
                ts = r["timestamp"]
                if hasattr(ts, "isoformat"):
                    if first_ts is None or ts < first_ts:
                        first_ts = ts
                    if last_ts is None or ts > last_ts:
                        last_ts = ts
                    r["timestamp"] = ts.isoformat()
                else:
                    r["timestamp"] = str(ts)
        
        # Build time range info for response
        time_range_info = {
            "period": period,
            "start_requested": start_dt.isoformat() if start_dt else None,
            "end_requested": end_dt.isoformat() if end_dt else None,
            "first_record": first_ts.isoformat() if first_ts else None,
            "last_record": last_ts.isoformat() if last_ts else None,
        }
        
        return ToolResult(
            success=True,
            symbol=symbol,
            message=f"[{env.upper()}] Found {len(records):,} funding rate records for {symbol}",
            data={
                "records": records,
                "count": len(records),
                "symbol": symbol,
                "env": env,
                "time_range": time_range_info,
            },
            source="duckdb",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Failed to get funding history: {str(e)}",
        )


# ==================== OHLCV QUERY TOOLS ====================




def get_ohlcv_history_tool(
    symbol: str,
    timeframe: str = "1h",
    period: str | None = None,
    start: datetime | str | None = None,
    end: datetime | str | None = None,
    limit: int | None = None,
    env: DataEnv = DEFAULT_DATA_ENV,
) -> ToolResult:
    """
    Get OHLCV candlestick history for a symbol from DuckDB.
    
    Accepts either a relative 'period' OR explicit 'start'/'end' times.
    Start/end can be datetime objects or ISO-format strings (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS).
    
    Args:
        symbol: Trading symbol (required)
        timeframe: Candle timeframe (e.g., "1m", "5m", "15m", "1h", "4h", "D"). Defaults to "1h".
        period: Relative period (e.g., "1M", "3M", "6M", "1Y") - alternative to start/end
        start: Start datetime or ISO string (e.g., "2024-01-01" or "2024-01-01T00:00:00")
        end: End datetime or ISO string (e.g., "2024-06-01" or "2024-06-01T23:59:59")
        limit: Maximum number of candles to return (optional, defaults to all within range)
        env: Data environment ("live" or "demo"). Defaults to "live".
    
    Returns:
        ToolResult with OHLCV data including:
        - candles: List of {timestamp, open, high, low, close, volume} dicts
        - count: Number of candles
        - timeframe: The queried timeframe
        - time_range: Metadata about the queried range
    
    Note:
        Maximum range is 365 days when using start/end to prevent bloat.
        Use 'period' for convenience (e.g., "1M" = last month).
        Data must be synced first using sync_symbols_tool or build_symbol_history_tool.
    """
    if not symbol:
        return ToolResult(success=False, error="Symbol required")
    
    # Normalize and validate time range
    start_dt, end_dt, range_error = _normalize_time_range_params(start, end)
    if range_error:
        return ToolResult(success=False, symbol=symbol, error=range_error)
    
    try:
        store = _get_historical_store(env=env)
        df = store.get_ohlcv(symbol, timeframe, period=period, start=start_dt, end=end_dt)
        
        if df.empty:
            return ToolResult(
                success=True,
                symbol=symbol,
                message=f"[{env.upper()}] No OHLCV data for {symbol} ({timeframe})",
                data={
                    "candles": [],
                    "count": 0,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "env": env,
                },
                source="duckdb",
            )
        
        # Apply limit if specified
        if limit and limit > 0 and len(df) > limit:
            df = df.tail(limit)
        
        # Convert to list of dicts for JSON serialization
        candles = df.to_dict(orient="records")
        
        # Extract time range metadata from actual data
        first_ts = None
        last_ts = None
        
        # Convert timestamps to ISO strings and track range
        for c in candles:
            if "timestamp" in c:
                ts = c["timestamp"]
                if hasattr(ts, "isoformat"):
                    if first_ts is None or ts < first_ts:
                        first_ts = ts
                    if last_ts is None or ts > last_ts:
                        last_ts = ts
                    c["timestamp"] = ts.isoformat()
                else:
                    c["timestamp"] = str(ts)
        
        # Build time range info for response
        time_range_info = {
            "period": period,
            "start_requested": start_dt.isoformat() if start_dt else None,
            "end_requested": end_dt.isoformat() if end_dt else None,
            "first_candle": first_ts.isoformat() if first_ts else None,
            "last_candle": last_ts.isoformat() if last_ts else None,
        }
        
        return ToolResult(
            success=True,
            symbol=symbol,
            message=f"[{env.upper()}] Found {len(candles):,} candles for {symbol} ({timeframe})",
            data={
                "candles": candles,
                "count": len(candles),
                "symbol": symbol,
                "timeframe": timeframe,
                "env": env,
                "time_range": time_range_info,
            },
            source="duckdb",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Failed to get OHLCV history: {str(e)}",
        )


# ==================== OPEN INTEREST TOOLS ====================




def get_open_interest_history_tool(
    symbol: str,
    period: str | None = None,
    start: datetime | str | None = None,
    end: datetime | str | None = None,
    env: DataEnv = DEFAULT_DATA_ENV,
) -> ToolResult:
    """
    Get open interest history for a symbol from DuckDB.
    
    Accepts either a relative 'period' OR explicit 'start'/'end' times.
    Start/end can be datetime objects or ISO-format strings (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS).
    
    Args:
        symbol: Trading symbol (required)
        period: Period string (e.g., "1M", "3M") - alternative to start/end
        start: Start datetime or ISO string (e.g., "2024-01-01" or "2024-01-01T00:00:00")
        end: End datetime or ISO string (e.g., "2024-06-01" or "2024-06-01T23:59:59")
        env: Data environment ("live" or "demo"). Defaults to "live".
    
    Returns:
        ToolResult with open interest data including:
        - records: List of {timestamp, open_interest} dicts
        - count: Number of records
        - time_range: Metadata about the queried range
    
    Note:
        Maximum range is 365 days when using start/end to prevent bloat.
        Use 'period' for convenience (e.g., "1M" = last month).
    """
    if not symbol:
        return ToolResult(success=False, error="Symbol required")
    
    # Normalize and validate time range
    start_dt, end_dt, range_error = _normalize_time_range_params(start, end)
    if range_error:
        return ToolResult(success=False, symbol=symbol, error=range_error)
    
    try:
        store = _get_historical_store(env=env)
        df = store.get_open_interest(symbol, period=period, start=start_dt, end=end_dt)
        
        if df.empty:
            return ToolResult(
                success=True,
                symbol=symbol,
                message=f"[{env.upper()}] No open interest data for {symbol}",
                data={"records": [], "count": 0, "env": env},
                source="duckdb",
            )
        
        # Convert to list of dicts for JSON serialization
        records = df.to_dict(orient="records")
        
        # Extract time range metadata from actual data
        first_ts = None
        last_ts = None
        
        # Convert timestamps to ISO strings and track range
        for r in records:
            if "timestamp" in r:
                ts = r["timestamp"]
                if hasattr(ts, "isoformat"):
                    if first_ts is None or ts < first_ts:
                        first_ts = ts
                    if last_ts is None or ts > last_ts:
                        last_ts = ts
                    r["timestamp"] = ts.isoformat()
                else:
                    r["timestamp"] = str(ts)
        
        # Build time range info for response
        time_range_info = {
            "period": period,
            "start_requested": start_dt.isoformat() if start_dt else None,
            "end_requested": end_dt.isoformat() if end_dt else None,
            "first_record": first_ts.isoformat() if first_ts else None,
            "last_record": last_ts.isoformat() if last_ts else None,
        }
        
        return ToolResult(
            success=True,
            symbol=symbol,
            message=f"[{env.upper()}] Found {len(records):,} open interest records for {symbol}",
            data={
                "records": records,
                "count": len(records),
                "symbol": symbol,
                "env": env,
                "time_range": time_range_info,
            },
            source="duckdb",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Failed to get open interest history: {str(e)}",
        )


# ==================== COMPOSITE BUILD TOOLS ====================




def sync_to_now_tool(
    symbols: list[str],
    timeframes: list[str] | None = None,
    env: DataEnv = DEFAULT_DATA_ENV,
) -> ToolResult:
    """
    Sync data forward from the last stored candle to now (no backfill).
    
    This is a lightweight sync that only fetches new data after the last
    stored timestamp, without scanning or backfilling older history.
    Useful for keeping existing data up-to-date.
    
    Args:
        symbols: List of symbols to sync forward
        timeframes: List of timeframes (e.g., ["15m", "1h", "4h"]) or None for all
        env: Data environment ("live" or "demo"). Defaults to "live".
    
    Returns:
        ToolResult with per-symbol/timeframe counts
    """
    if not symbols:
        return ToolResult(success=False, error="No symbols provided")
    
    try:
        store = _get_historical_store(env=env)
        results = store.sync_forward(
            symbols,
            timeframes=timeframes,
            show_spinner=False,
        )
        
        total_synced = sum(v for v in results.values() if v > 0)
        already_current = sum(1 for v in results.values() if v == 0)
        errors = sum(1 for v in results.values() if v < 0)
        
        if errors > 0:
            message = f"[{env.upper()}] Synced {total_synced:,} new candles, {already_current} already current, {errors} errors"
        elif total_synced > 0:
            message = f"[{env.upper()}] Synced {total_synced:,} new candles ({already_current} already current)"
        else:
            message = f"[{env.upper()}] All {len(results)} symbol/timeframe combinations already current"
        
        return ToolResult(
            success=True,
            message=message,
            data={
                "results": results,
                "total_synced": total_synced,
                "already_current": already_current,
                "symbols": symbols,
                "env": env,
            },
            source="duckdb",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Sync forward failed: {str(e)}",
        )




def sync_to_now_and_fill_gaps_tool(
    symbols: list[str],
    timeframes: list[str] | None = None,
    env: DataEnv = DEFAULT_DATA_ENV,
) -> ToolResult:
    """
    Sync data forward to now AND fill any gaps in existing data.
    
    This is a comprehensive sync that:
    1. First syncs forward from last timestamp to now
    2. Then scans for and fills any gaps in the historical data
    
    Use this when you want to ensure data is both current AND complete.
    
    Args:
        symbols: List of symbols to sync and heal
        timeframes: List of timeframes (e.g., ["15m", "1h", "4h"]) or None for all
        env: Data environment ("live" or "demo"). Defaults to "live".
    
    Returns:
        ToolResult with combined sync and gap-fill summary
    """
    if not symbols:
        return ToolResult(success=False, error="No symbols provided")
    
    # Normalize symbols
    symbols = [s.strip().upper() for s in symbols]
    
    results = {
        "symbols": symbols,
        "env": env,
        "sync_forward": {"total_synced": 0, "details": {}},
        "gap_fill": {"total_filled": 0, "details": {}},
    }
    
    errors = []
    
    # 1. Sync forward
    try:
        sync_result = sync_to_now_tool(symbols, timeframes=timeframes, env=env)
        if sync_result.success:
            results["sync_forward"] = {
                "total_synced": sync_result.data.get("total_synced", 0),
                "details": sync_result.data.get("results", {}),
            }
        else:
            errors.append(f"Sync forward: {sync_result.error}")
    except Exception as e:
        errors.append(f"Sync forward: {str(e)}")
    
    # 2. Fill gaps for each symbol/timeframe
    try:
        gap_results = {}
        for symbol in symbols:
            gap_result = fill_gaps_tool(
                symbol=symbol,
                timeframe=None,  # All timeframes for this symbol
                env=env,
            )
            if gap_result.success:
                # Merge per-symbol results
                for key, count in gap_result.data.get("results", {}).items():
                    gap_results[key] = count
        
        total_filled = sum(v for v in gap_results.values() if v > 0)
        results["gap_fill"] = {
            "total_filled": total_filled,
            "details": gap_results,
        }
    except Exception as e:
        errors.append(f"Gap fill: {str(e)}")
    
    # Build summary
    synced = results["sync_forward"]["total_synced"]
    filled = results["gap_fill"]["total_filled"]
    total = synced + filled
    
    if errors:
        message = f"[{env.upper()}] Synced {synced:,} forward + filled {filled:,} gaps (errors: {'; '.join(errors)})"
        success = total > 0
    else:
        message = f"[{env.upper()}] Synced {synced:,} new candles forward + filled {filled:,} gap candles"
        success = True
    
    results["total_records"] = total
    results["errors"] = errors if errors else None
    
    return ToolResult(
        success=success,
        message=message,
        data=results,
        source="duckdb",
    )




def build_symbol_history_tool(
    symbols: list[str],
    period: str = "1M",
    timeframes: list[str] | None = None,
    oi_interval: str | None = None,
    env: DataEnv = DEFAULT_DATA_ENV,
) -> ToolResult:
    """
    Build complete historical data for symbols (OHLCV, funding rates, and open interest).
    
    This is a composite operation that syncs all data types at once for the specified
    symbols, making it easy to fully populate data for new symbols or refresh existing.
    
    Args:
        symbols: List of symbols to build history for (required, no default)
        period: How far back to sync ("1D", "1W", "1M", "3M", "6M", "1Y")
        timeframes: List of OHLCV timeframes (e.g., ["15m", "1h", "4h"]) or None for all
        oi_interval: Open interest interval (5min, 15min, 30min, 1h, 4h, D) or None for "1h"
        env: Data environment ("live" or "demo"). Defaults to "live".
    
    Returns:
        ToolResult with combined sync summary for all data types
    """
    if not symbols:
        return ToolResult(success=False, error="No symbols provided")
    
    # Normalize symbols
    symbols = [s.strip().upper() for s in symbols]
    oi_interval = oi_interval or "1h"
    
    results = {
        "symbols": symbols,
        "period": period,
        "env": env,
        "ohlcv": {"success": False, "total_synced": 0, "details": {}},
        "funding": {"success": False, "total_synced": 0, "details": {}},
        "open_interest": {"success": False, "total_synced": 0, "details": {}},
    }
    
    errors = []
    
    # 1. Sync OHLCV candles
    try:
        ohlcv_result = sync_symbols_tool(symbols, period=period, timeframes=timeframes, env=env)
        if ohlcv_result.success:
            results["ohlcv"] = {
                "success": True,
                "total_synced": ohlcv_result.data.get("total_synced", 0),
                "details": ohlcv_result.data.get("results", {}),
            }
        else:
            errors.append(f"OHLCV: {ohlcv_result.error}")
    except Exception as e:
        errors.append(f"OHLCV: {str(e)}")
    
    # 2. Sync funding rates
    try:
        funding_result = sync_funding_tool(symbols, period=period, env=env)
        if funding_result.success:
            results["funding"] = {
                "success": True,
                "total_synced": funding_result.data.get("total_synced", 0),
                "details": funding_result.data.get("results", {}),
            }
        else:
            errors.append(f"Funding: {funding_result.error}")
    except Exception as e:
        errors.append(f"Funding: {str(e)}")
    
    # 3. Sync open interest
    try:
        oi_result = sync_open_interest_tool(symbols, period=period, interval=oi_interval, env=env)
        if oi_result.success:
            results["open_interest"] = {
                "success": True,
                "total_synced": oi_result.data.get("total_synced", 0),
                "details": oi_result.data.get("results", {}),
            }
        else:
            errors.append(f"Open Interest: {oi_result.error}")
    except Exception as e:
        errors.append(f"Open Interest: {str(e)}")
    
    # Build summary
    ohlcv_count = results["ohlcv"]["total_synced"]
    funding_count = results["funding"]["total_synced"]
    oi_count = results["open_interest"]["total_synced"]
    total_records = ohlcv_count + funding_count + oi_count
    
    all_success = all([
        results["ohlcv"]["success"],
        results["funding"]["success"],
        results["open_interest"]["success"],
    ])
    
    if all_success:
        message = (
            f"[{env.upper()}] Built history for {len(symbols)} symbol(s): "
            f"{ohlcv_count:,} OHLCV candles, "
            f"{funding_count:,} funding records, "
            f"{oi_count:,} OI records"
        )
    else:
        message = (
            f"[{env.upper()}] Partial build for {len(symbols)} symbol(s): "
            f"{ohlcv_count:,} OHLCV, {funding_count:,} funding, {oi_count:,} OI"
        )
        if errors:
            message += f" | Errors: {'; '.join(errors)}"
    
    results["total_records"] = total_records
    results["errors"] = errors if errors else None
    
    return ToolResult(
        success=all_success or total_records > 0,  # Success if any data synced
        message=message,
        data=results,
        source="duckdb",
    )


# ==================== FULL_FROM_LAUNCH BOOTSTRAP TOOLS ====================


# Default timeframe groups for full history sync
TF_GROUP_LOW = ["1m", "5m", "15m"]      # LTF (high-resolution)
TF_GROUP_MID = ["1h", "4h"]             # MTF
TF_GROUP_HIGH = ["D"]                   # HTF (Bybit format)

# All standard timeframes
ALL_TIMEFRAMES = TF_GROUP_LOW + TF_GROUP_MID + TF_GROUP_HIGH

# Maximum chunk size for range syncing (days)
MAX_CHUNK_DAYS = 90

# Safety cap to prevent accidental massive pulls (years)
DEFAULT_MAX_HISTORY_YEARS = 5


