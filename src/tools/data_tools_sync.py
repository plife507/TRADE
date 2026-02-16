"""
Data tools - sync and maintenance tools.

Split from data_tools.py for maintainability.
"""

from collections.abc import Callable
from datetime import datetime

from .shared import ToolResult, _get_historical_store
from ..config.constants import DataEnv, DEFAULT_DATA_ENV


def sync_symbols_tool(
    symbols: list[str],
    period: str = "1M",
    timeframes: list[str] | None = None,
    progress_callback: Callable | None = None,
    env: DataEnv = DEFAULT_DATA_ENV,
) -> ToolResult:
    """
    Sync (update) data for symbols from the exchange.
    
    Args:
        symbols: List of symbols to sync
        period: Period string (e.g., "1D", "1W", "1M", "3M", "6M", "1Y")
        timeframes: List of timeframes (e.g., ["15m", "1h", "4h", "D"])
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
    symbols: list[str],
    start: datetime,
    end: datetime,
    timeframes: list[str] | None = None,
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




def sync_data_tool(
    symbol: str | None = None,
    timeframe: str | None = None,
    progress_callback: Callable | None = None,
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
    symbol: str | None = None,
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
        ohlcv_row = store.conn.execute(f"SELECT COUNT(*) FROM {store.table_ohlcv}").fetchone()
        metadata_row = store.conn.execute(f"SELECT COUNT(*) FROM {store.table_sync_metadata}").fetchone()
        funding_row = store.conn.execute(f"SELECT COUNT(*) FROM {store.table_funding}").fetchone()
        funding_meta_row = store.conn.execute(f"SELECT COUNT(*) FROM {store.table_funding_metadata}").fetchone()
        oi_row = store.conn.execute(f"SELECT COUNT(*) FROM {store.table_oi}").fetchone()
        oi_meta_row = store.conn.execute(f"SELECT COUNT(*) FROM {store.table_oi_metadata}").fetchone()
        ohlcv_count = ohlcv_row[0] if ohlcv_row else 0
        metadata_count = metadata_row[0] if metadata_row else 0
        funding_count = funding_row[0] if funding_row else 0
        funding_meta_count = funding_meta_row[0] if funding_meta_row else 0
        oi_count = oi_row[0] if oi_row else 0
        oi_meta_count = oi_meta_row[0] if oi_meta_row else 0
        
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
    symbols: list[str],
    period: str = "3M",
    progress_callback: Callable | None = None,
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




def sync_open_interest_tool(
    symbols: list[str],
    period: str = "1M",
    interval: str = "1h",
    progress_callback: Callable | None = None,
    env: DataEnv = DEFAULT_DATA_ENV,
) -> ToolResult:
    """
    Sync open interest history for symbols.
    
    Args:
        symbols: List of symbols to sync
        period: Period string (e.g., "1M", "3M", "6M", "1Y")
        interval: Data interval (5min, 15min, 30min, 1h, 4h, D)
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
