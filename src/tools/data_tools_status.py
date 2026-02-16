"""
Data tools - status and info tools.

Split from data_tools.py for maintainability.
"""

from typing import Any, cast

from .shared import ToolResult, _get_historical_store
from ..config.constants import DataEnv, DEFAULT_DATA_ENV


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
                data=cast(dict[str, Any], []),  # Empty list for consistent table handling
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
        tf_order = {"1m": 1, "5m": 2, "15m": 3, "30m": 4, "1h": 5, "4h": 6, "D": 7}
        
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
            data=cast(dict[str, Any], symbols_data),  # Return as list for table rendering
            source="duckdb",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Failed to list symbols: {str(e)}",
        )




def get_symbol_status_tool(symbol: str | None = None, env: DataEnv = DEFAULT_DATA_ENV) -> ToolResult:
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




def get_symbol_timeframe_ranges_tool(symbol: str | None = None, env: DataEnv = DEFAULT_DATA_ENV) -> ToolResult:
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
        tf_order = {"1m": 1, "5m": 2, "15m": 3, "1h": 4, "4h": 5, "D": 6}
        ranges.sort(key=lambda r: (r["symbol"], tf_order.get(r["timeframe"], 99)))
        
        symbols_count = len(set(r["symbol"] for r in ranges))
        
        return ToolResult(
            success=True,
            symbol=symbol,
            message=f"Found {len(ranges)} symbol/timeframe combinations across {symbols_count} symbol(s)",
            data=cast(dict[str, Any], ranges),  # Return as list for direct table rendering
            source="duckdb",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Failed to get symbol timeframe ranges: {str(e)}",
        )
