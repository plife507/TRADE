"""
Historical data management tools for TRADE trading bot.

These tools provide access to DuckDB-backed historical market data operations.
"""

from typing import Optional, Dict, Any, List, Callable
from datetime import datetime
from .shared import ToolResult, _get_historical_store


def get_database_stats_tool() -> ToolResult:
    """
    Get database statistics (size, symbol count, candle count, funding, OI).
    
    Returns:
        ToolResult with database stats
    """
    try:
        store = _get_historical_store()
        stats = store.get_database_stats()
        
        ohlcv = stats.get("ohlcv", {})
        funding = stats.get("funding_rates", {})
        oi = stats.get("open_interest", {})
        
        message = (
            f"Database: {stats['file_size_mb']} MB | "
            f"OHLCV: {ohlcv.get('symbols', 0)} symbols, {ohlcv.get('total_candles', 0):,} candles | "
            f"Funding: {funding.get('total_records', 0):,} records | "
            f"OI: {oi.get('total_records', 0):,} records"
        )
        
        return ToolResult(
            success=True,
            message=message,
            data=stats,
            source="duckdb",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Failed to get database stats: {str(e)}",
        )


def list_cached_symbols_tool() -> ToolResult:
    """
    List all symbols currently cached in the database.
    
    Returns:
        ToolResult with list of symbols
    """
    try:
        store = _get_historical_store()
        symbols = store.list_symbols()
        
        return ToolResult(
            success=True,
            message=f"Found {len(symbols)} cached symbols",
            data={
                "symbols": symbols,
                "count": len(symbols),
            },
            source="duckdb",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Failed to list symbols: {str(e)}",
        )


def get_symbol_status_tool(symbol: Optional[str] = None) -> ToolResult:
    """
    Get per-symbol aggregate status (total candles, gaps, timeframe count).
    
    For detailed per-symbol/timeframe breakdown, use get_symbol_timeframe_ranges_tool.
    
    Args:
        symbol: Specific symbol to check (None for all)
    
    Returns:
        ToolResult with symbol status data (aggregated per symbol)
    """
    try:
        store = _get_historical_store()
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


def get_symbol_summary_tool() -> ToolResult:
    """
    Get a high-level summary of all cached symbols (timeframe count, total candles, date range).
    
    This provides a quick overview per symbol. For detailed per-timeframe breakdown,
    use get_symbol_timeframe_ranges_tool.
    
    Returns:
        ToolResult with symbol summary data (one row per symbol)
    """
    try:
        store = _get_historical_store()
        summary = store.get_symbol_summary()
        
        return ToolResult(
            success=True,
            message=f"High-level summary for {len(summary)} symbols (use 'Symbol Timeframe Ranges' for per-TF details)",
            data={"summary": summary},
            source="duckdb",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Failed to get symbol summary: {str(e)}",
        )


def get_symbol_timeframe_ranges_tool(symbol: Optional[str] = None) -> ToolResult:
    """
    Get detailed per-symbol/timeframe breakdown showing date ranges and health.
    
    Returns a flat list of rows with: symbol, timeframe, first_timestamp, last_timestamp,
    candle_count, gaps, is_current. Optimized for tabular display.
    
    Args:
        symbol: Specific symbol to check (None for all symbols)
    
    Returns:
        ToolResult with list of per-symbol/timeframe range details
    """
    try:
        store = _get_historical_store()
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
) -> ToolResult:
    """
    Sync (update) data for symbols from the exchange.
    
    Args:
        symbols: List of symbols to sync
        period: Period string (e.g., "1D", "1W", "1M", "3M", "6M", "1Y")
        timeframes: List of timeframes (e.g., ["15m", "1h", "4h", "1d"])
        progress_callback: Optional callback for progress updates
    
    Returns:
        ToolResult with sync results
    """
    if not symbols:
        return ToolResult(success=False, error="No symbols provided")
    
    try:
        store = _get_historical_store()
        results = store.sync(
            symbols,
            period=period,
            timeframes=timeframes,
            progress_callback=progress_callback,
            show_spinner=False,
        )
        
        total_synced = sum(v for v in results.values() if v > 0)
        
        return ToolResult(
            success=True,
            message=f"Synced {total_synced:,} candles",
            data={
                "results": results,
                "total_synced": total_synced,
                "symbols": symbols,
                "period": period,
            },
            source="duckdb",
        )
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
) -> ToolResult:
    """
    Sync data for a specific date range.
    
    Args:
        symbols: List of symbols to sync
        start: Start datetime
        end: End datetime
        timeframes: List of timeframes
    
    Returns:
        ToolResult with sync results
    """
    if not symbols:
        return ToolResult(success=False, error="No symbols provided")
    
    try:
        store = _get_historical_store()
        results = store.sync_range(symbols, start=start, end=end, timeframes=timeframes)
        
        total_synced = sum(v for v in results.values() if v > 0)
        
        return ToolResult(
            success=True,
            message=f"Synced {total_synced:,} candles ({start.date()} to {end.date()})",
            data={
                "results": results,
                "total_synced": total_synced,
                "symbols": symbols,
                "start": start.isoformat(),
                "end": end.isoformat(),
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
) -> ToolResult:
    """
    Auto-detect and fill gaps in cached data.
    
    Args:
        symbol: Specific symbol to fill gaps for (None for all)
        timeframe: Specific timeframe to fill gaps for (None for all)
        progress_callback: Optional callback for progress updates
    
    Returns:
        ToolResult with gap fill results
    """
    try:
        store = _get_historical_store()
        results = store.fill_gaps(
            symbol=symbol,
            timeframe=timeframe,
            progress_callback=progress_callback,
        )
        
        total_filled = sum(v for v in results.values() if v > 0)
        
        return ToolResult(
            success=True,
            symbol=symbol,
            message=f"Filled {total_filled:,} gap candles",
            data={
                "results": results,
                "total_filled": total_filled,
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
    
    Returns:
        ToolResult with heal report
    """
    try:
        store = _get_historical_store()
        report = store.heal(
            symbol=symbol,
            fix_issues=fix_issues,
            fill_gaps_after=fill_gaps_after,
        )
        
        issues_found = report.get("issues_found", 0)
        issues_fixed = report.get("issues_fixed", 0)
        
        if issues_found == 0:
            message = "Data is healthy - no issues found"
        else:
            message = f"Found {issues_found} issues, fixed {issues_fixed}"
        
        return ToolResult(
            success=True,
            symbol=symbol,
            message=message,
            data={"report": report},
            source="duckdb",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Heal failed: {str(e)}",
        )


def delete_symbol_tool(symbol: str, vacuum: bool = True) -> ToolResult:
    """
    Delete all data for a symbol.
    
    Args:
        symbol: Symbol to delete
        vacuum: Whether to vacuum the database after deletion
    
    Returns:
        ToolResult with deletion result
    """
    if not symbol or not isinstance(symbol, str):
        return ToolResult(success=False, error="Invalid symbol parameter")
    
    try:
        store = _get_historical_store()
        deleted = store.delete_symbol(symbol)
        
        if vacuum:
            store.vacuum()
        
        return ToolResult(
            success=True,
            symbol=symbol,
            message=f"Deleted {deleted:,} candles for {symbol}",
            data={
                "symbol": symbol,
                "deleted_count": deleted,
                "vacuumed": vacuum,
            },
            source="duckdb",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Delete failed: {str(e)}",
        )


def cleanup_empty_symbols_tool() -> ToolResult:
    """
    Remove symbols with no data (invalid symbols).
    
    Returns:
        ToolResult with cleanup results
    """
    try:
        store = _get_historical_store()
        cleaned = store.cleanup_empty_symbols()
        
        return ToolResult(
            success=True,
            message=f"Cleaned up {len(cleaned)} invalid symbol(s)",
            data={
                "cleaned_symbols": cleaned,
                "count": len(cleaned),
            },
            source="duckdb",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Cleanup failed: {str(e)}",
        )


def vacuum_database_tool() -> ToolResult:
    """
    Vacuum the database to reclaim space.
    
    Returns:
        ToolResult with vacuum status
    """
    try:
        store = _get_historical_store()
        store.vacuum()
        
        return ToolResult(
            success=True,
            message="Database vacuumed successfully",
            data={"vacuumed": True},
            source="duckdb",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Vacuum failed: {str(e)}",
        )


# ==================== FUNDING RATE TOOLS ====================


def sync_funding_tool(
    symbols: List[str],
    period: str = "3M",
    progress_callback: Optional[Callable] = None,
) -> ToolResult:
    """
    Sync funding rate history for symbols.
    
    Args:
        symbols: List of symbols to sync
        period: Period string (e.g., "1M", "3M", "6M", "1Y")
        progress_callback: Optional callback for progress updates
    
    Returns:
        ToolResult with sync results
    """
    if not symbols:
        return ToolResult(success=False, error="No symbols provided")
    
    try:
        store = _get_historical_store()
        results = store.sync_funding(
            symbols,
            period=period,
            progress_callback=progress_callback,
            show_spinner=False,
        )
        
        total_synced = sum(v for v in results.values() if v > 0)
        
        return ToolResult(
            success=True,
            message=f"Synced {total_synced:,} funding rate records",
            data={
                "results": results,
                "total_synced": total_synced,
                "symbols": symbols,
                "period": period,
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
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> ToolResult:
    """
    Get funding rate history for a symbol.
    
    Args:
        symbol: Trading symbol
        period: Period string (e.g., "1M", "3M") - alternative to start/end
        start: Start datetime
        end: End datetime
    
    Returns:
        ToolResult with funding rate data
    """
    if not symbol:
        return ToolResult(success=False, error="Symbol required")
    
    try:
        store = _get_historical_store()
        df = store.get_funding(symbol, period=period, start=start, end=end)
        
        if df.empty:
            return ToolResult(
                success=True,
                symbol=symbol,
                message=f"No funding data for {symbol}",
                data={"records": [], "count": 0},
                source="duckdb",
            )
        
        # Convert to list of dicts for JSON serialization
        records = df.to_dict(orient="records")
        
        # Convert timestamps to ISO strings
        for r in records:
            if "timestamp" in r:
                r["timestamp"] = r["timestamp"].isoformat() if hasattr(r["timestamp"], "isoformat") else str(r["timestamp"])
        
        return ToolResult(
            success=True,
            symbol=symbol,
            message=f"Found {len(records):,} funding rate records for {symbol}",
            data={
                "records": records,
                "count": len(records),
                "symbol": symbol,
            },
            source="duckdb",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Failed to get funding history: {str(e)}",
        )


# ==================== OPEN INTEREST TOOLS ====================


def sync_open_interest_tool(
    symbols: List[str],
    period: str = "1M",
    interval: str = "1h",
    progress_callback: Optional[Callable] = None,
) -> ToolResult:
    """
    Sync open interest history for symbols.
    
    Args:
        symbols: List of symbols to sync
        period: Period string (e.g., "1M", "3M", "6M", "1Y")
        interval: Data interval (5min, 15min, 30min, 1h, 4h, 1d)
        progress_callback: Optional callback for progress updates
    
    Returns:
        ToolResult with sync results
    """
    if not symbols:
        return ToolResult(success=False, error="No symbols provided")
    
    try:
        store = _get_historical_store()
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
            message=f"Synced {total_synced:,} open interest records",
            data={
                "results": results,
                "total_synced": total_synced,
                "symbols": symbols,
                "period": period,
                "interval": interval,
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
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> ToolResult:
    """
    Get open interest history for a symbol.
    
    Args:
        symbol: Trading symbol
        period: Period string (e.g., "1M", "3M") - alternative to start/end
        start: Start datetime
        end: End datetime
    
    Returns:
        ToolResult with open interest data
    """
    if not symbol:
        return ToolResult(success=False, error="Symbol required")
    
    try:
        store = _get_historical_store()
        df = store.get_open_interest(symbol, period=period, start=start, end=end)
        
        if df.empty:
            return ToolResult(
                success=True,
                symbol=symbol,
                message=f"No open interest data for {symbol}",
                data={"records": [], "count": 0},
                source="duckdb",
            )
        
        # Convert to list of dicts for JSON serialization
        records = df.to_dict(orient="records")
        
        # Convert timestamps to ISO strings
        for r in records:
            if "timestamp" in r:
                r["timestamp"] = r["timestamp"].isoformat() if hasattr(r["timestamp"], "isoformat") else str(r["timestamp"])
        
        return ToolResult(
            success=True,
            symbol=symbol,
            message=f"Found {len(records):,} open interest records for {symbol}",
            data={
                "records": records,
                "count": len(records),
                "symbol": symbol,
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
) -> ToolResult:
    """
    Sync data forward from the last stored candle to now (no backfill).
    
    This is a lightweight sync that only fetches new data after the last
    stored timestamp, without scanning or backfilling older history.
    Useful for keeping existing data up-to-date.
    
    Args:
        symbols: List of symbols to sync forward
        timeframes: List of timeframes (e.g., ["15m", "1h", "4h"]) or None for all
    
    Returns:
        ToolResult with per-symbol/timeframe counts
    """
    if not symbols:
        return ToolResult(success=False, error="No symbols provided")
    
    try:
        store = _get_historical_store()
        results = store.sync_forward(
            symbols,
            timeframes=timeframes,
            show_spinner=False,
        )
        
        total_synced = sum(v for v in results.values() if v > 0)
        already_current = sum(1 for v in results.values() if v == 0)
        errors = sum(1 for v in results.values() if v < 0)
        
        if errors > 0:
            message = f"Synced {total_synced:,} new candles, {already_current} already current, {errors} errors"
        elif total_synced > 0:
            message = f"Synced {total_synced:,} new candles ({already_current} already current)"
        else:
            message = f"All {len(results)} symbol/timeframe combinations already current"
        
        return ToolResult(
            success=True,
            message=message,
            data={
                "results": results,
                "total_synced": total_synced,
                "already_current": already_current,
                "symbols": symbols,
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
    
    Returns:
        ToolResult with combined sync and gap-fill summary
    """
    if not symbols:
        return ToolResult(success=False, error="No symbols provided")
    
    # Normalize symbols
    symbols = [s.strip().upper() for s in symbols]
    
    results = {
        "symbols": symbols,
        "sync_forward": {"total_synced": 0, "details": {}},
        "gap_fill": {"total_filled": 0, "details": {}},
    }
    
    errors = []
    
    # 1. Sync forward
    try:
        sync_result = sync_to_now_tool(symbols, timeframes=timeframes)
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
        message = f"Synced {synced:,} forward + filled {filled:,} gaps (errors: {'; '.join(errors)})"
        success = total > 0
    else:
        message = f"Synced {synced:,} new candles forward + filled {filled:,} gap candles"
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
        "ohlcv": {"success": False, "total_synced": 0, "details": {}},
        "funding": {"success": False, "total_synced": 0, "details": {}},
        "open_interest": {"success": False, "total_synced": 0, "details": {}},
    }
    
    errors = []
    
    # 1. Sync OHLCV candles
    try:
        ohlcv_result = sync_symbols_tool(symbols, period=period, timeframes=timeframes)
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
        funding_result = sync_funding_tool(symbols, period=period)
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
        oi_result = sync_open_interest_tool(symbols, period=period, interval=oi_interval)
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
            f"Built history for {len(symbols)} symbol(s): "
            f"{ohlcv_count:,} OHLCV candles, "
            f"{funding_count:,} funding records, "
            f"{oi_count:,} OI records"
        )
    else:
        message = (
            f"Partial build for {len(symbols)} symbol(s): "
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

