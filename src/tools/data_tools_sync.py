"""
Data tools - sync and maintenance tools.

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


# Import helpers and constants from common
from .data_tools_common import (
    TF_GROUP_LOW, TF_GROUP_MID, TF_GROUP_HIGH, ALL_TIMEFRAMES,
    MAX_CHUNK_DAYS, DEFAULT_MAX_HISTORY_YEARS,
    _sync_range_chunked, _days_to_period, 
    _build_extremes_metadata, _persist_extremes_to_db,
)


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




def fill_gaps_tool(
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
    timeframes: list[str] | None = None,
    category: str = "linear",
    max_history_years: float = DEFAULT_MAX_HISTORY_YEARS,
    sync_funding: bool = True,
    sync_oi: bool = True,
    oi_interval: str = "1h",
    fill_gaps_after: bool = True,
    heal_after: bool = True,
    dry_run: bool = False,
    progress_callback: Callable | None = None,
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


