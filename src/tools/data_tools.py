"""
Historical data management tools for TRADE trading bot.

These tools provide access to DuckDB-backed historical market data operations.
"""

from typing import Optional, Dict, Any, List, Callable
from datetime import datetime
from .shared import ToolResult, _get_historical_store


def get_database_stats_tool() -> ToolResult:
    """
    Get database statistics (size, symbol count, candle count).
    
    Returns:
        ToolResult with database stats
    """
    try:
        store = _get_historical_store()
        stats = store.get_database_stats()
        
        return ToolResult(
            success=True,
            message=f"Database: {stats['file_size_mb']} MB, {stats['symbols']} symbols, {stats['total_candles']:,} candles",
            data={
                "db_path": stats.get("db_path"),
                "file_size_mb": stats.get("file_size_mb"),
                "symbols": stats.get("symbols"),
                "total_candles": stats.get("total_candles"),
            },
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
    Get status information for cached symbols.
    
    Args:
        symbol: Specific symbol to check (None for all)
    
    Returns:
        ToolResult with symbol status data
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
        
        # Summarize status
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
            message=f"Status for {len(summary)} symbol(s)",
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
    Get a summary of all cached symbols.
    
    Returns:
        ToolResult with symbol summary data
    """
    try:
        store = _get_historical_store()
        summary = store.get_symbol_summary()
        
        return ToolResult(
            success=True,
            message=f"Summary for {len(summary)} symbols",
            data={"summary": summary},
            source="duckdb",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Failed to get symbol summary: {str(e)}",
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
    progress_callback: Optional[Callable] = None,
) -> ToolResult:
    """
    Auto-detect and fill gaps in cached data.
    
    Args:
        symbol: Specific symbol to fill gaps for (None for all)
        progress_callback: Optional callback for progress updates
    
    Returns:
        ToolResult with gap fill results
    """
    try:
        store = _get_historical_store()
        
        if symbol:
            # Fill gaps for specific symbol
            results = store.fill_gaps(symbols=[symbol], progress_callback=progress_callback)
        else:
            # Fill gaps for all symbols
            results = store.fill_gaps(progress_callback=progress_callback)
        
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
    timeframe: Optional[str] = None,
    fix_duplicates: bool = True,
    fix_invalid_prices: bool = True,
    fix_gaps: bool = True,
    fix_future_dates: bool = True,
) -> ToolResult:
    """
    Run comprehensive data integrity check and repair.
    
    Args:
        symbol: Specific symbol to heal (None for all)
        timeframe: Specific timeframe (None for all)
        fix_duplicates: Remove duplicate candles
        fix_invalid_prices: Fix zero/negative prices
        fix_gaps: Fill data gaps
        fix_future_dates: Remove candles with future timestamps
    
    Returns:
        ToolResult with heal report
    """
    try:
        store = _get_historical_store()
        report = store.heal(
            symbol=symbol,
            timeframe=timeframe,
            fix_duplicates=fix_duplicates,
            fix_invalid_prices=fix_invalid_prices,
            fix_gaps=fix_gaps,
            fix_future_dates=fix_future_dates,
        )
        
        return ToolResult(
            success=True,
            symbol=symbol,
            message="Data heal completed",
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

