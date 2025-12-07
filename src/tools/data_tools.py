"""
Historical data management tools for TRADE trading bot.

These tools provide access to DuckDB-backed historical market data operations.

Environment-aware: All tools default to "live" environment for data operations.
Pass env="demo" to operate on demo history instead.

Time Range Support:
- All query tools accept either 'period' (e.g., "1M", "3M") OR 'start'/'end' datetimes
- Start/end can be datetime objects or ISO-format strings (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
- Large ranges may be limited to prevent bloat (configurable per tool)
"""

from typing import Optional, Dict, Any, List, Callable, Union, Tuple
from datetime import datetime, timedelta
from .shared import ToolResult, _get_historical_store
from ..config.constants import DataEnv, DEFAULT_DATA_ENV


# =============================================================================
# Datetime Normalization Helpers
# =============================================================================

# Maximum allowed range in days for query tools (to prevent bloat)
MAX_QUERY_RANGE_DAYS = 365


def _normalize_datetime(
    value: Optional[Union[datetime, str]],
    param_name: str = "datetime",
) -> Tuple[Optional[datetime], Optional[str]]:
    """
    Normalize a datetime value from various input formats.
    
    Args:
        value: A datetime object, ISO-format string, or None
        param_name: Parameter name for error messages
    
    Returns:
        Tuple of (normalized_datetime, error_message)
        - If successful: (datetime, None)
        - If failed: (None, error_string)
    """
    if value is None:
        return None, None
    
    if isinstance(value, datetime):
        return value, None
    
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None, None
        
        # Try multiple common ISO formats
        formats = [
            "%Y-%m-%dT%H:%M:%S",      # Full ISO
            "%Y-%m-%dT%H:%M",          # ISO without seconds
            "%Y-%m-%d %H:%M:%S",       # Space separator with seconds
            "%Y-%m-%d %H:%M",          # Space separator without seconds
            "%Y-%m-%d",                # Date only
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(value, fmt), None
            except ValueError:
                continue
        
        # Try fromisoformat as fallback (handles more edge cases)
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")), None
        except ValueError:
            pass
        
        return None, f"Invalid {param_name} format: '{value}'. Use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS"
    
    return None, f"Invalid {param_name} type: expected datetime or string, got {type(value).__name__}"


def _validate_time_range(
    start: Optional[datetime],
    end: Optional[datetime],
    max_days: int = MAX_QUERY_RANGE_DAYS,
) -> Tuple[bool, Optional[str]]:
    """
    Validate a time range for reasonableness.
    
    Args:
        start: Start datetime
        end: End datetime
        max_days: Maximum allowed range in days
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if start is None and end is None:
        return True, None
    
    if start is not None and end is not None:
        if start >= end:
            return False, "Start time must be before end time"
        
        duration = end - start
        if duration.days > max_days:
            return False, f"Time range too large: {duration.days} days exceeds maximum of {max_days} days"
    
    return True, None


def _normalize_time_range_params(
    start: Optional[Union[datetime, str]],
    end: Optional[Union[datetime, str]],
    max_days: int = MAX_QUERY_RANGE_DAYS,
) -> Tuple[Optional[datetime], Optional[datetime], Optional[str]]:
    """
    Normalize and validate start/end time range parameters.
    
    Args:
        start: Start time as datetime or ISO string
        end: End time as datetime or ISO string
        max_days: Maximum allowed range in days
    
    Returns:
        Tuple of (start_dt, end_dt, error_message)
        - If successful: (start_datetime, end_datetime, None)
        - If failed: (None, None, error_string)
    """
    # Normalize start
    start_dt, start_err = _normalize_datetime(start, "start")
    if start_err:
        return None, None, start_err
    
    # Normalize end
    end_dt, end_err = _normalize_datetime(end, "end")
    if end_err:
        return None, None, end_err
    
    # Validate range
    is_valid, range_err = _validate_time_range(start_dt, end_dt, max_days)
    if not is_valid:
        return None, None, range_err
    
    return start_dt, end_dt, None


def get_database_stats_tool(env: DataEnv = DEFAULT_DATA_ENV) -> ToolResult:
    """
    Get database statistics (size, symbol count, candle count, funding, OI).
    
    Args:
        env: Data environment ("live" or "demo"). Defaults to "live".
    
    Returns:
        ToolResult with database stats
    """
    try:
        store = _get_historical_store(env=env)
        stats = store.get_database_stats()
        
        ohlcv = stats.get("ohlcv", {})
        funding = stats.get("funding_rates", {})
        oi = stats.get("open_interest", {})
        
        message = (
            f"[{env.upper()}] Database: {stats['file_size_mb']} MB | "
            f"OHLCV: {ohlcv.get('symbols', 0)} symbols, {ohlcv.get('total_candles', 0):,} candles | "
            f"Funding: {funding.get('total_records', 0):,} records | "
            f"OI: {oi.get('total_records', 0):,} records"
        )
        
        return ToolResult(
            success=True,
            message=message,
            data={**stats, "env": env},
            source="duckdb",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Failed to get database stats: {str(e)}",
        )


def list_cached_symbols_tool(env: DataEnv = DEFAULT_DATA_ENV) -> ToolResult:
    """
    List all symbols with their data summary (timeframes, date range, candle count).
    
    This provides an enriched view of cached symbols, not just names.
    Each symbol includes: timeframe list, total candles, earliest and latest dates.
    
    Args:
        env: Data environment ("live" or "demo"). Defaults to "live".
    
    Returns:
        ToolResult with list of symbols and their summary data
    """
    try:
        store = _get_historical_store(env=env)
        
        # Get detailed status to extract actual timeframe names
        status = store.status()
        
        if not status:
            return ToolResult(
                success=True,
                message=f"[{env.upper()}] No symbols cached in database",
                data=[],  # Empty list for consistent table handling
                source="duckdb",
            )
        
        # Group by symbol and collect timeframes + date ranges
        symbols_data_map = {}
        for key, info in status.items():
            sym = info["symbol"]
            if sym not in symbols_data_map:
                symbols_data_map[sym] = {
                    "symbol": sym,
                    "timeframes": [],
                    "candles": 0,
                    "earliest": None,
                    "latest": None,
                }
            
            symbols_data_map[sym]["timeframes"].append(info["timeframe"])
            symbols_data_map[sym]["candles"] += info["candle_count"]
            
            # Track earliest/latest across all timeframes
            if info["first_timestamp"]:
                if symbols_data_map[sym]["earliest"] is None or info["first_timestamp"] < symbols_data_map[sym]["earliest"]:
                    symbols_data_map[sym]["earliest"] = info["first_timestamp"]
            if info["last_timestamp"]:
                if symbols_data_map[sym]["latest"] is None or info["last_timestamp"] > symbols_data_map[sym]["latest"]:
                    symbols_data_map[sym]["latest"] = info["last_timestamp"]
        
        # Sort timeframes in logical order and format for display
        tf_order = {"1m": 1, "5m": 2, "15m": 3, "30m": 4, "1h": 5, "4h": 6, "1d": 7, "1D": 7}
        
        symbols_data = []
        for sym, data in sorted(symbols_data_map.items()):
            # Sort timeframes
            tfs = sorted(data["timeframes"], key=lambda t: tf_order.get(t, 99))
            symbols_data.append({
                "symbol": sym,
                "timeframes": ", ".join(tfs),
                "candles": data["candles"],
                "from": data["earliest"].strftime("%Y-%m-%d") if data["earliest"] else "N/A",
                "to": data["latest"].strftime("%Y-%m-%d") if data["latest"] else "N/A",
            })
        
        return ToolResult(
            success=True,
            message=f"[{env.upper()}] Found {len(symbols_data)} cached symbols",
            data=symbols_data,  # Return as list for table rendering
            source="duckdb",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Failed to list symbols: {str(e)}",
        )


def get_symbol_status_tool(symbol: Optional[str] = None, env: DataEnv = DEFAULT_DATA_ENV) -> ToolResult:
    """
    Get per-symbol aggregate status (total candles, gaps, timeframe count).
    
    For detailed per-symbol/timeframe breakdown, use get_symbol_timeframe_ranges_tool.
    
    Args:
        symbol: Specific symbol to check (None for all)
        env: Data environment ("live" or "demo"). Defaults to "live".
    
    Returns:
        ToolResult with symbol status data (aggregated per symbol)
    """
    try:
        store = _get_historical_store(env=env)
        status = store.status(symbol) if symbol else store.status()
        
        if not status:
            return ToolResult(
                success=True,
                symbol=symbol,
                message="No data cached",
                data={"status": {}},
                source="duckdb",
            )
        
        # Summarize status (aggregate per symbol)
        symbols_data = {}
        for key, info in status.items():
            sym = info["symbol"]
            if sym not in symbols_data:
                symbols_data[sym] = []
            symbols_data[sym].append(info)
        
        summary = {}
        for sym, infos in symbols_data.items():
            total_candles = sum(i["candle_count"] for i in infos)
            gaps = sum(i["gaps"] for i in infos)
            timeframes = [i["timeframe"] for i in infos]
            summary[sym] = {
                "timeframes": timeframes,
                "total_candles": total_candles,
                "gaps": gaps,
                "is_valid": total_candles > 0,
            }
        
        return ToolResult(
            success=True,
            symbol=symbol,
            message=f"Per-symbol aggregate status for {len(summary)} symbol(s)",
            data={
                "summary": summary,
                "raw_status": status,
            },
            source="duckdb",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Failed to get status: {str(e)}",
        )


def get_symbol_summary_tool(env: DataEnv = DEFAULT_DATA_ENV) -> ToolResult:
    """
    Get a high-level summary of all cached symbols (timeframe count, total candles, date range).
    
    This provides a quick overview per symbol. For detailed per-timeframe breakdown,
    use get_symbol_timeframe_ranges_tool.
    
    Args:
        env: Data environment ("live" or "demo"). Defaults to "live".
    
    Returns:
        ToolResult with symbol summary data (one row per symbol)
    """
    try:
        store = _get_historical_store(env=env)
        summary = store.get_symbol_summary()
        
        return ToolResult(
            success=True,
            message=f"[{env.upper()}] High-level summary for {len(summary)} symbols (use 'Symbol Timeframe Ranges' for per-TF details)",
            data={"summary": summary, "env": env},
            source="duckdb",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Failed to get symbol summary: {str(e)}",
        )


def get_symbol_timeframe_ranges_tool(symbol: Optional[str] = None, env: DataEnv = DEFAULT_DATA_ENV) -> ToolResult:
    """
    Get detailed per-symbol/timeframe breakdown showing date ranges and health.
    
    Returns a flat list of rows with: symbol, timeframe, first_timestamp, last_timestamp,
    candle_count, gaps, is_current. Optimized for tabular display.
    
    Args:
        symbol: Specific symbol to check (None for all symbols)
        env: Data environment ("live" or "demo"). Defaults to "live".
    
    Returns:
        ToolResult with list of per-symbol/timeframe range details
    """
    try:
        store = _get_historical_store(env=env)
        status = store.status(symbol) if symbol else store.status()
        
        if not status:
            return ToolResult(
                success=True,
                symbol=symbol,
                message="No data cached" + (f" for {symbol}" if symbol else ""),
                data={"ranges": [], "count": 0},
                source="duckdb",
            )
        
        # Flatten into list of dicts for tabular display
        ranges = []
        for key, info in status.items():
            ranges.append({
                "symbol": info["symbol"],
                "timeframe": info["timeframe"],
                "first_timestamp": info["first_timestamp"].isoformat() if info["first_timestamp"] else None,
                "last_timestamp": info["last_timestamp"].isoformat() if info["last_timestamp"] else None,
                "candle_count": info["candle_count"],
                "gaps": info["gaps"],
                "is_current": info["is_current"],
            })
        
        # Sort by symbol, then timeframe
        tf_order = {"1m": 1, "5m": 2, "15m": 3, "1h": 4, "4h": 5, "1d": 6}
        ranges.sort(key=lambda r: (r["symbol"], tf_order.get(r["timeframe"], 99)))
        
        symbols_count = len(set(r["symbol"] for r in ranges))
        
        return ToolResult(
            success=True,
            symbol=symbol,
            message=f"Found {len(ranges)} symbol/timeframe combinations across {symbols_count} symbol(s)",
            data=ranges,  # Return as list for direct table rendering
            source="duckdb",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Failed to get symbol timeframe ranges: {str(e)}",
        )


def sync_symbols_tool(
    symbols: List[str],
    period: str = "1M",
    timeframes: Optional[List[str]] = None,
    progress_callback: Optional[Callable] = None,
    env: DataEnv = DEFAULT_DATA_ENV,
) -> ToolResult:
    """
    Sync (update) data for symbols from the exchange.
    
    Args:
        symbols: List of symbols to sync
        period: Period string (e.g., "1D", "1W", "1M", "3M", "6M", "1Y")
        timeframes: List of timeframes (e.g., ["15m", "1h", "4h", "1d"])
        progress_callback: Optional callback for progress updates
        env: Data environment ("live" or "demo"). Defaults to "live".
    
    Returns:
        ToolResult with sync results
    """
    if not symbols:
        return ToolResult(success=False, error="No symbols provided")
    
    try:
        store = _get_historical_store(env=env)
        # Reset cancellation flag at start
        store.reset_cancellation()
        
        results = store.sync(
            symbols,
            period=period,
            timeframes=timeframes,
            progress_callback=progress_callback,
            show_spinner=False,
        )
        
        total_synced = sum(v for v in results.values() if v > 0)
        
        # Check if operation was cancelled
        if store._cancelled:
            return ToolResult(
                success=False,
                error="Operation cancelled by user",
                data={
                    "results": results,
                    "total_synced": total_synced,
                    "symbols": symbols,
                    "period": period,
                    "cancelled": True,
                    "env": env,
                },
                source="duckdb",
            )
        
        return ToolResult(
            success=True,
            message=f"[{env.upper()}] Synced {total_synced:,} candles",
            data={
                "results": results,
                "total_synced": total_synced,
                "symbols": symbols,
                "period": period,
                "env": env,
            },
            source="duckdb",
        )
    except KeyboardInterrupt:
        store = _get_historical_store(env=env)
        store.cancel()
        raise  # Re-raise to be caught by CLI
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Sync failed: {str(e)}",
        )


def sync_range_tool(
    symbols: List[str],
    start: datetime,
    end: datetime,
    timeframes: Optional[List[str]] = None,
    env: DataEnv = DEFAULT_DATA_ENV,
) -> ToolResult:
    """
    Sync data for a specific date range.
    
    Args:
        symbols: List of symbols to sync
        start: Start datetime
        end: End datetime
        timeframes: List of timeframes
        env: Data environment ("live" or "demo"). Defaults to "live".
    
    Returns:
        ToolResult with sync results
    """
    if not symbols:
        return ToolResult(success=False, error="No symbols provided")
    
    try:
        store = _get_historical_store(env=env)
        results = store.sync_range(symbols, start=start, end=end, timeframes=timeframes)
        
        total_synced = sum(v for v in results.values() if v > 0)
        
        return ToolResult(
            success=True,
            message=f"[{env.upper()}] Synced {total_synced:,} candles ({start.date()} to {end.date()})",
            data={
                "results": results,
                "total_synced": total_synced,
                "symbols": symbols,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "env": env,
            },
            source="duckdb",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Sync range failed: {str(e)}",
        )


def fill_gaps_tool(
    symbol: Optional[str] = None,
    timeframe: Optional[str] = None,
    progress_callback: Optional[Callable] = None,
    env: DataEnv = DEFAULT_DATA_ENV,
) -> ToolResult:
    """
    Auto-detect and fill gaps in cached data.
    
    Args:
        symbol: Specific symbol to fill gaps for (None for all)
        timeframe: Specific timeframe to fill gaps for (None for all)
        progress_callback: Optional callback for progress updates
        env: Data environment ("live" or "demo"). Defaults to "live".
    
    Returns:
        ToolResult with gap fill results
    """
    try:
        store = _get_historical_store(env=env)
        results = store.fill_gaps(
            symbol=symbol,
            timeframe=timeframe,
            progress_callback=progress_callback,
        )
        
        total_filled = sum(v for v in results.values() if v > 0)
        
        return ToolResult(
            success=True,
            symbol=symbol,
            message=f"[{env.upper()}] Filled {total_filled:,} gap candles",
            data={
                "results": results,
                "total_filled": total_filled,
                "env": env,
            },
            source="duckdb",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Gap fill failed: {str(e)}",
        )


def heal_data_tool(
    symbol: Optional[str] = None,
    fix_issues: bool = True,
    fill_gaps_after: bool = True,
    env: DataEnv = DEFAULT_DATA_ENV,
) -> ToolResult:
    """
    Run comprehensive data integrity check and repair.
    
    Checks for:
    - Duplicate timestamps
    - Invalid OHLCV (high < low, open/close outside high-low range)
    - Negative/zero volumes
    - NULL values in critical columns
    - Symbol casing inconsistencies
    - Time gaps
    
    Args:
        symbol: Specific symbol to heal (None for all)
        fix_issues: If True, automatically fix found issues
        fill_gaps_after: If True, fill gaps after fixing other issues
        env: Data environment ("live" or "demo"). Defaults to "live".
    
    Returns:
        ToolResult with heal report
    """
    try:
        store = _get_historical_store(env=env)
        report = store.heal(
            symbol=symbol,
            fix_issues=fix_issues,
            fill_gaps_after=fill_gaps_after,
        )
        
        issues_found = report.get("issues_found", 0)
        issues_fixed = report.get("issues_fixed", 0)
        
        if issues_found == 0:
            message = f"[{env.upper()}] Data is healthy - no issues found"
        else:
            message = f"[{env.upper()}] Found {issues_found} issues, fixed {issues_fixed}"
        
        return ToolResult(
            success=True,
            symbol=symbol,
            message=message,
            data={"report": report, "env": env},
            source="duckdb",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Heal failed: {str(e)}",
        )


def delete_symbol_tool(symbol: str, vacuum: bool = True, env: DataEnv = DEFAULT_DATA_ENV) -> ToolResult:
    """
    Delete all data for a symbol.
    
    Args:
        symbol: Symbol to delete
        vacuum: Whether to vacuum the database after deletion
        env: Data environment ("live" or "demo"). Defaults to "live".
    
    Returns:
        ToolResult with deletion result
    """
    if not symbol or not isinstance(symbol, str):
        return ToolResult(success=False, error="Invalid symbol parameter")
    
    try:
        store = _get_historical_store(env=env)
        deleted = store.delete_symbol(symbol)
        
        if vacuum:
            store.vacuum()
        
        return ToolResult(
            success=True,
            symbol=symbol,
            message=f"[{env.upper()}] Deleted {deleted:,} candles for {symbol}",
            data={
                "symbol": symbol,
                "deleted_count": deleted,
                "vacuumed": vacuum,
                "env": env,
            },
            source="duckdb",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Delete failed: {str(e)}",
        )


def cleanup_empty_symbols_tool(env: DataEnv = DEFAULT_DATA_ENV) -> ToolResult:
    """
    Remove symbols with no data (invalid symbols).
    
    Args:
        env: Data environment ("live" or "demo"). Defaults to "live".
    
    Returns:
        ToolResult with cleanup results
    """
    try:
        store = _get_historical_store(env=env)
        cleaned = store.cleanup_empty_symbols()
        
        return ToolResult(
            success=True,
            message=f"[{env.upper()}] Cleaned up {len(cleaned)} invalid symbol(s)",
            data={
                "cleaned_symbols": cleaned,
                "count": len(cleaned),
                "env": env,
            },
            source="duckdb",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Cleanup failed: {str(e)}",
        )


def vacuum_database_tool(env: DataEnv = DEFAULT_DATA_ENV) -> ToolResult:
    """
    Vacuum the database to reclaim space.
    
    Args:
        env: Data environment ("live" or "demo"). Defaults to "live".
    
    Returns:
        ToolResult with vacuum status
    """
    try:
        store = _get_historical_store(env=env)
        store.vacuum()
        
        return ToolResult(
            success=True,
            message=f"[{env.upper()}] Database vacuumed successfully",
            data={"vacuumed": True, "env": env},
            source="duckdb",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Vacuum failed: {str(e)}",
        )


def delete_all_data_tool(vacuum: bool = True, env: DataEnv = DEFAULT_DATA_ENV) -> ToolResult:
    """
    Delete ALL data from the historical database (OHLCV, funding, open interest).
    
    WARNING: This is destructive and cannot be undone. Use with caution.
    Only affects historical market data in DuckDB, not trading positions or balances.
    
    Args:
        vacuum: Whether to vacuum the database after deletion (default True)
        env: Data environment ("live" or "demo"). Defaults to "live".
    
    Returns:
        ToolResult with deletion stats (rows deleted per table)
    """
    try:
        store = _get_historical_store(env=env)
        
        # Count rows before deletion
        ohlcv_count = store.conn.execute(f"SELECT COUNT(*) FROM {store.table_ohlcv}").fetchone()[0]
        metadata_count = store.conn.execute(f"SELECT COUNT(*) FROM {store.table_sync_metadata}").fetchone()[0]
        funding_count = store.conn.execute(f"SELECT COUNT(*) FROM {store.table_funding}").fetchone()[0]
        funding_meta_count = store.conn.execute(f"SELECT COUNT(*) FROM {store.table_funding_metadata}").fetchone()[0]
        oi_count = store.conn.execute(f"SELECT COUNT(*) FROM {store.table_oi}").fetchone()[0]
        oi_meta_count = store.conn.execute(f"SELECT COUNT(*) FROM {store.table_oi_metadata}").fetchone()[0]
        
        # Delete all data from all tables
        store.conn.execute(f"DELETE FROM {store.table_ohlcv}")
        store.conn.execute(f"DELETE FROM {store.table_sync_metadata}")
        store.conn.execute(f"DELETE FROM {store.table_funding}")
        store.conn.execute(f"DELETE FROM {store.table_funding_metadata}")
        store.conn.execute(f"DELETE FROM {store.table_oi}")
        store.conn.execute(f"DELETE FROM {store.table_oi_metadata}")
        
        total_deleted = ohlcv_count + metadata_count + funding_count + funding_meta_count + oi_count + oi_meta_count
        
        if vacuum:
            store.vacuum()
        
        return ToolResult(
            success=True,
            message=f"[{env.upper()}] Deleted ALL data: {total_deleted:,} total rows",
            data={
                "env": env,
                "deleted": {
                    "ohlcv": ohlcv_count,
                    "sync_metadata": metadata_count,
                    "funding": funding_count,
                    "funding_metadata": funding_meta_count,
                    "open_interest": oi_count,
                    "oi_metadata": oi_meta_count,
                },
                "total_deleted": total_deleted,
                "vacuumed": vacuum,
            },
            source="duckdb",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Delete all data failed: {str(e)}",
        )


# ==================== FUNDING RATE TOOLS ====================


def sync_funding_tool(
    symbols: List[str],
    period: str = "3M",
    progress_callback: Optional[Callable] = None,
    env: DataEnv = DEFAULT_DATA_ENV,
) -> ToolResult:
    """
    Sync funding rate history for symbols.
    
    Args:
        symbols: List of symbols to sync
        period: Period string (e.g., "1M", "3M", "6M", "1Y")
        progress_callback: Optional callback for progress updates
        env: Data environment ("live" or "demo"). Defaults to "live".
    
    Returns:
        ToolResult with sync results
    """
    if not symbols:
        return ToolResult(success=False, error="No symbols provided")
    
    try:
        store = _get_historical_store(env=env)
        results = store.sync_funding(
            symbols,
            period=period,
            progress_callback=progress_callback,
            show_spinner=False,
        )
        
        total_synced = sum(v for v in results.values() if v > 0)
        
        return ToolResult(
            success=True,
            message=f"[{env.upper()}] Synced {total_synced:,} funding rate records",
            data={
                "results": results,
                "total_synced": total_synced,
                "symbols": symbols,
                "period": period,
                "env": env,
            },
            source="duckdb",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Funding sync failed: {str(e)}",
        )


def get_funding_history_tool(
    symbol: str,
    period: Optional[str] = None,
    start: Optional[Union[datetime, str]] = None,
    end: Optional[Union[datetime, str]] = None,
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
    period: Optional[str] = None,
    start: Optional[Union[datetime, str]] = None,
    end: Optional[Union[datetime, str]] = None,
    limit: Optional[int] = None,
    env: DataEnv = DEFAULT_DATA_ENV,
) -> ToolResult:
    """
    Get OHLCV candlestick history for a symbol from DuckDB.
    
    Accepts either a relative 'period' OR explicit 'start'/'end' times.
    Start/end can be datetime objects or ISO-format strings (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS).
    
    Args:
        symbol: Trading symbol (required)
        timeframe: Candle timeframe (e.g., "1m", "5m", "15m", "1h", "4h", "1d"). Defaults to "1h".
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


def sync_open_interest_tool(
    symbols: List[str],
    period: str = "1M",
    interval: str = "1h",
    progress_callback: Optional[Callable] = None,
    env: DataEnv = DEFAULT_DATA_ENV,
) -> ToolResult:
    """
    Sync open interest history for symbols.
    
    Args:
        symbols: List of symbols to sync
        period: Period string (e.g., "1M", "3M", "6M", "1Y")
        interval: Data interval (5min, 15min, 30min, 1h, 4h, 1d)
        progress_callback: Optional callback for progress updates
        env: Data environment ("live" or "demo"). Defaults to "live".
    
    Returns:
        ToolResult with sync results
    """
    if not symbols:
        return ToolResult(success=False, error="No symbols provided")
    
    try:
        store = _get_historical_store(env=env)
        results = store.sync_open_interest(
            symbols,
            period=period,
            interval=interval,
            progress_callback=progress_callback,
            show_spinner=False,
        )
        
        total_synced = sum(v for v in results.values() if v > 0)
        
        return ToolResult(
            success=True,
            message=f"[{env.upper()}] Synced {total_synced:,} open interest records",
            data={
                "results": results,
                "total_synced": total_synced,
                "symbols": symbols,
                "period": period,
                "interval": interval,
                "env": env,
            },
            source="duckdb",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Open interest sync failed: {str(e)}",
        )


def get_open_interest_history_tool(
    symbol: str,
    period: Optional[str] = None,
    start: Optional[Union[datetime, str]] = None,
    end: Optional[Union[datetime, str]] = None,
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
    symbols: List[str],
    timeframes: Optional[List[str]] = None,
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
    symbols: List[str],
    timeframes: Optional[List[str]] = None,
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
    symbols: List[str],
    period: str = "1M",
    timeframes: Optional[List[str]] = None,
    oi_interval: Optional[str] = None,
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
        oi_interval: Open interest interval (5min, 15min, 30min, 1h, 4h, 1d) or None for "1h"
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

