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
    Get database statistics with per-symbol and per-timeframe breakdowns.
    
    Shows:
    - Overall stats (file size, symbol counts, total records)
    - Per-symbol OHLCV breakdown with timeframes and candle counts
    - Per-symbol funding rates breakdown
    - Per-symbol open interest breakdown
    
    Args:
        env: Data environment ("live" or "demo"). Defaults to "live".
    
    Returns:
        ToolResult with detailed database stats
    """
    try:
        store = _get_historical_store(env=env)
        stats = store.get_database_stats()
        
        ohlcv = stats.get("ohlcv", {})
        funding = stats.get("funding_rates", {})
        oi = stats.get("open_interest", {})
        
        # Build summary message
        summary_lines = [
            f"[{env.upper()}] Database: {stats['file_size_mb']} MB",
            f"OHLCV: {ohlcv.get('symbols', 0)} symbols, {ohlcv.get('symbol_timeframe_combinations', 0)} combinations, {ohlcv.get('total_candles', 0):,} candles",
            f"Funding: {funding.get('symbols', 0)} symbols, {funding.get('total_records', 0):,} records",
            f"Open Interest: {oi.get('symbols', 0)} symbols, {oi.get('total_records', 0):,} records",
        ]
        
        # Build detailed per-symbol breakdown
        detail_lines = ["\n=== OHLCV Data by Symbol ==="]
        ohlcv_by_symbol = ohlcv.get("by_symbol", {})
        if ohlcv_by_symbol:
            for symbol in sorted(ohlcv_by_symbol.keys()):
                sym_data = ohlcv_by_symbol[symbol]
                detail_lines.append(f"\n{symbol}:")
                detail_lines.append(f"  Total: {sym_data.get('total_candles', 0):,} candles")
                if sym_data.get("earliest"):
                    detail_lines.append(f"  Range: {sym_data.get('earliest', 'N/A')[:10]} to {sym_data.get('latest', 'N/A')[:10]}")
                detail_lines.append(f"  Timeframes:")
                for tf_data in sym_data.get("timeframes", []):
                    tf = tf_data.get("timeframe", "N/A")
                    candles = tf_data.get("candles", 0)
                    detail_lines.append(f"    {tf:>4s}: {candles:>8,} candles")
        else:
            detail_lines.append("  No OHLCV data")
        
        detail_lines.append("\n=== Funding Rates by Symbol ===")
        funding_by_symbol = funding.get("by_symbol", {})
        if funding_by_symbol:
            for symbol in sorted(funding_by_symbol.keys()):
                sym_data = funding_by_symbol[symbol]
                records = sym_data.get("records", 0)
                earliest = sym_data.get("earliest", "")[:10] if sym_data.get("earliest") else "N/A"
                latest = sym_data.get("latest", "")[:10] if sym_data.get("latest") else "N/A"
                detail_lines.append(f"  {symbol}: {records:>6,} records ({earliest} to {latest})")
        else:
            detail_lines.append("  No funding rate data")
        
        detail_lines.append("\n=== Open Interest by Symbol ===")
        oi_by_symbol = oi.get("by_symbol", {})
        if oi_by_symbol:
            for symbol in sorted(oi_by_symbol.keys()):
                sym_data = oi_by_symbol[symbol]
                records = sym_data.get("records", 0)
                earliest = sym_data.get("earliest", "")[:10] if sym_data.get("earliest") else "N/A"
                latest = sym_data.get("latest", "")[:10] if sym_data.get("latest") else "N/A"
                detail_lines.append(f"  {symbol}: {records:>6,} records ({earliest} to {latest})")
        else:
            detail_lines.append("  No open interest data")
        
        # Combine summary and details
        full_message = "\n".join(summary_lines) + "\n" + "\n".join(detail_lines)
        
        return ToolResult(
            success=True,
            message=full_message,
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


# ==================== FULL_FROM_LAUNCH BOOTSTRAP TOOLS ====================


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


def get_instrument_launch_time_tool(
    symbol: str,
    category: str = "linear",
    env: DataEnv = DEFAULT_DATA_ENV,
) -> ToolResult:
    """
    Get the launch timestamp for a trading instrument from Bybit API.
    
    Args:
        symbol: Trading symbol (e.g., "BTCUSDT", "SOLUSDT")
        category: Product category ("linear", "inverse", "spot", "option")
        env: Data environment for API selection
        
    Returns:
        ToolResult with launch_time_ms, launch_datetime, and instrument_info
    """
    try:
        store = _get_historical_store(env=env)
        launch_ms = store.client.get_instrument_launch_time(symbol, category=category)
        
        if launch_ms is None:
            return ToolResult(
                success=False,
                symbol=symbol,
                error=f"Could not find launchTime for {symbol} (category={category})",
            )
        
        launch_dt = datetime.fromtimestamp(launch_ms / 1000)
        
        return ToolResult(
            success=True,
            symbol=symbol,
            message=f"{symbol} launched on {launch_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC",
            data={
                "symbol": symbol,
                "category": category,
                "launch_time_ms": launch_ms,
                "launch_datetime": launch_dt.isoformat(),
                "env": env,
            },
            source="bybit_api",
        )
        
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Failed to get launch time: {str(e)}",
        )


def sync_full_from_launch_tool(
    symbol: str,
    timeframes: Optional[List[str]] = None,
    category: str = "linear",
    max_history_years: float = DEFAULT_MAX_HISTORY_YEARS,
    sync_funding: bool = True,
    sync_oi: bool = True,
    oi_interval: str = "1h",
    fill_gaps_after: bool = True,
    heal_after: bool = True,
    dry_run: bool = False,
    progress_callback: Optional[Callable] = None,
    env: DataEnv = DEFAULT_DATA_ENV,
) -> ToolResult:
    """
    Bootstrap full historical data for a symbol from its launchTime to now.
    
    This is the FULL_FROM_LAUNCH mode for Phase -1 preflight bootstrap.
    It syncs all required data types (OHLCV, funding, OI) from instrument
    launchTime → now, using chunk-safe pagination.
    
    Args:
        symbol: Trading symbol (e.g., "SOLUSDT")
        timeframes: List of timeframes to sync (default: all standard TFs)
        category: Product category ("linear", "inverse")
        max_history_years: Safety cap to limit how far back to sync
        sync_funding: Whether to sync funding rates
        sync_oi: Whether to sync open interest
        oi_interval: Open interest interval (5min, 15min, 30min, 1h, 4h, 1d)
        fill_gaps_after: Whether to run gap fill after sync
        heal_after: Whether to run heal after sync
        dry_run: If True, only estimate work without syncing
        progress_callback: Optional callback for progress updates
        env: Data environment ("live" or "demo")
        
    Returns:
        ToolResult with sync results and extremes metadata
    """
    symbol = symbol.strip().upper()
    timeframes = timeframes or ALL_TIMEFRAMES
    
    try:
        store = _get_historical_store(env=env)
        
        # Step 1: Get instrument launchTime from Bybit API
        launch_ms = store.client.get_instrument_launch_time(symbol, category=category)
        
        if launch_ms is None:
            return ToolResult(
                success=False,
                symbol=symbol,
                error=f"Could not find launchTime for {symbol} (category={category}). "
                      f"Symbol may not exist or API unavailable.",
            )
        
        launch_dt = datetime.fromtimestamp(launch_ms / 1000)
        now_dt = datetime.now()
        
        # Apply safety cap
        earliest_allowed = now_dt - timedelta(days=max_history_years * 365)
        effective_start = max(launch_dt, earliest_allowed)
        
        days_to_sync = (now_dt - effective_start).days
        
        # Dry run: estimate only
        if dry_run:
            # Estimate candles per timeframe
            tf_minutes = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}
            estimates = {}
            total_candles = 0
            
            for tf in timeframes:
                minutes = tf_minutes.get(tf, 60)
                candles = int((days_to_sync * 24 * 60) / minutes)
                estimates[tf] = candles
                total_candles += candles
            
            # Estimate funding records (8-hour intervals)
            funding_estimate = int(days_to_sync * 3) if sync_funding else 0
            
            # Estimate OI records
            oi_intervals = {"5min": 12*24, "15min": 4*24, "30min": 2*24, "1h": 24, "4h": 6, "1d": 1}
            oi_estimate = int(days_to_sync * oi_intervals.get(oi_interval, 24)) if sync_oi else 0
            
            return ToolResult(
                success=True,
                symbol=symbol,
                message=f"[DRY RUN] Would sync {symbol} from {effective_start.date()} to now ({days_to_sync} days)",
                data={
                    "dry_run": True,
                    "symbol": symbol,
                    "launch_datetime": launch_dt.isoformat(),
                    "effective_start": effective_start.isoformat(),
                    "days_to_sync": days_to_sync,
                    "timeframes": timeframes,
                    "ohlcv_estimates": estimates,
                    "total_candles_estimate": total_candles,
                    "funding_estimate": funding_estimate,
                    "oi_estimate": oi_estimate,
                    "safety_cap_applied": launch_dt < earliest_allowed,
                    "env": env,
                },
                source="estimate",
            )
        
        # Step 2: Sync OHLCV in chunks
        results = {
            "symbol": symbol,
            "launch_datetime": launch_dt.isoformat(),
            "effective_start": effective_start.isoformat(),
            "effective_end": now_dt.isoformat(),
            "days_synced": days_to_sync,
            "env": env,
            "ohlcv": {"success": False, "total_synced": 0, "by_timeframe": {}},
            "funding": {"success": False, "total_synced": 0},
            "open_interest": {"success": False, "total_synced": 0},
            "gaps_filled": 0,
            "healed": False,
        }
        
        errors = []
        
        # Sync OHLCV per timeframe using chunked approach
        ohlcv_total = 0
        for tf in timeframes:
            if progress_callback:
                progress_callback(symbol, f"Syncing {tf} OHLCV...")
            
            try:
                # Use sync_range with chunking internally
                tf_result = _sync_range_chunked(
                    store=store,
                    symbol=symbol,
                    timeframe=tf,
                    start=effective_start,
                    end=now_dt,
                    chunk_days=MAX_CHUNK_DAYS,
                )
                results["ohlcv"]["by_timeframe"][tf] = tf_result
                ohlcv_total += tf_result
                
            except Exception as e:
                errors.append(f"OHLCV {tf}: {str(e)}")
                results["ohlcv"]["by_timeframe"][tf] = -1
        
        results["ohlcv"]["total_synced"] = ohlcv_total
        results["ohlcv"]["success"] = ohlcv_total > 0
        
        # Step 3: Sync funding rates
        if sync_funding:
            if progress_callback:
                progress_callback(symbol, "Syncing funding rates...")
            
            try:
                # Calculate period string based on days
                period = _days_to_period(days_to_sync)
                funding_result = store.sync_funding(
                    symbols=[symbol],
                    period=period,
                    show_spinner=False,
                )
                funding_count = funding_result.get(symbol, 0)
                results["funding"]["total_synced"] = funding_count
                results["funding"]["success"] = funding_count > 0 or funding_count == 0  # 0 is ok if no data
                
            except Exception as e:
                errors.append(f"Funding: {str(e)}")
        
        # Step 4: Sync open interest
        if sync_oi:
            if progress_callback:
                progress_callback(symbol, "Syncing open interest...")
            
            try:
                period = _days_to_period(days_to_sync)
                oi_result = store.sync_open_interest(
                    symbols=[symbol],
                    period=period,
                    interval=oi_interval,
                    show_spinner=False,
                )
                oi_count = oi_result.get(symbol, 0)
                results["open_interest"]["total_synced"] = oi_count
                results["open_interest"]["success"] = oi_count > 0 or oi_count == 0
                
            except Exception as e:
                errors.append(f"Open Interest: {str(e)}")
        
        # Step 5: Fill gaps
        if fill_gaps_after:
            if progress_callback:
                progress_callback(symbol, "Filling gaps...")
            
            try:
                gap_result = fill_gaps_tool(symbol=symbol, env=env)
                if gap_result.success:
                    results["gaps_filled"] = gap_result.data.get("total_filled", 0)
            except Exception as e:
                errors.append(f"Gap fill: {str(e)}")
        
        # Step 6: Heal data
        if heal_after:
            if progress_callback:
                progress_callback(symbol, "Healing data...")
            
            try:
                heal_result = heal_data_tool(
                    symbol=symbol,
                    fix_issues=True,
                    fill_gaps_after=False,  # Already did gap fill
                    env=env,
                )
                results["healed"] = heal_result.success
            except Exception as e:
                errors.append(f"Heal: {str(e)}")
        
        # Step 7: Build and persist extremes metadata
        extremes = _build_extremes_metadata(store, symbol, timeframes)
        results["extremes"] = extremes
        
        # Persist extremes to DuckDB table
        launch_dt_for_db = datetime.fromtimestamp(launch_ms / 1000) if launch_ms else None
        _persist_extremes_to_db(store, symbol, extremes, launch_dt_for_db, "full_from_launch")
        
        # Build summary
        total_records = (
            results["ohlcv"]["total_synced"] +
            results["funding"]["total_synced"] +
            results["open_interest"]["total_synced"]
        )
        results["total_records"] = total_records
        results["errors"] = errors if errors else None
        
        success = total_records > 0 and len(errors) == 0
        
        if success:
            message = (
                f"[{env.upper()}] Full bootstrap for {symbol}: "
                f"{results['ohlcv']['total_synced']:,} OHLCV, "
                f"{results['funding']['total_synced']:,} funding, "
                f"{results['open_interest']['total_synced']:,} OI "
                f"({days_to_sync} days from {effective_start.date()})"
            )
        else:
            message = (
                f"[{env.upper()}] Partial bootstrap for {symbol}: "
                f"{total_records:,} records | Errors: {'; '.join(errors)}"
            )
        
        return ToolResult(
            success=success,
            symbol=symbol,
            message=message,
            data=results,
            source="duckdb",
        )
        
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Full bootstrap failed: {str(e)}",
        )


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


def _build_extremes_metadata(store, symbol: str, timeframes: List[str]) -> Dict[str, Any]:
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
    extremes: Dict[str, Any],
    launch_time: Optional[datetime],
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


def get_data_extremes_tool(
    symbol: Optional[str] = None,
    env: DataEnv = DEFAULT_DATA_ENV,
) -> ToolResult:
    """
    Get extremes/bounds metadata for symbol(s) in the database.
    
    Returns coverage information: earliest_ts, latest_ts, row_count per data type.
    
    Args:
        symbol: Specific symbol or None for all symbols
        env: Data environment ("live" or "demo")
        
    Returns:
        ToolResult with extremes metadata per symbol
    """
    try:
        store = _get_historical_store(env=env)
        
        # Get all symbols if not specified
        if symbol:
            symbols = [symbol.upper()]
        else:
            symbols = store.list_symbols()
        
        if not symbols:
            return ToolResult(
                success=True,
                message=f"[{env.upper()}] No symbols in database",
                data={"extremes": {}, "env": env},
                source="duckdb",
            )
        
        all_extremes = {}
        for sym in symbols:
            # Get all timeframes for this symbol
            status = store.status(sym)
            timeframes = list(set(info["timeframe"] for info in status.values()))
            all_extremes[sym] = _build_extremes_metadata(store, sym, timeframes)
        
        return ToolResult(
            success=True,
            message=f"[{env.upper()}] Extremes metadata for {len(symbols)} symbol(s)",
            data={
                "extremes": all_extremes,
                "symbol_count": len(symbols),
                "env": env,
            },
            source="duckdb",
        )
        
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Failed to get extremes: {str(e)}",
        )

