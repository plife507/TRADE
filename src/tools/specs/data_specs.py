"""
Data tool specifications.

NO LEGACY FALLBACKS - Forward coding only.
"""

from .shared_params import DATA_ENV_PARAM


def get_imports():
    """Return dict of function_name -> import path."""
    from .. import (
        get_database_stats_tool, list_cached_symbols_tool,
        get_symbol_status_tool, get_symbol_summary_tool,
        get_symbol_timeframe_ranges_tool,
        sync_symbols_tool, sync_range_tool,
        sync_funding_tool, sync_open_interest_tool,
        sync_to_now_tool, sync_forward_tool,
        build_symbol_history_tool,
        sync_data_tool, heal_data_tool,
        delete_symbol_tool, cleanup_empty_symbols_tool, vacuum_database_tool,
        delete_all_data_tool,
        get_funding_history_tool, get_open_interest_history_tool, get_ohlcv_history_tool,
    )
    return {
        "get_database_stats": get_database_stats_tool,
        "list_cached_symbols": list_cached_symbols_tool,
        "get_symbol_status": get_symbol_status_tool,
        "get_symbol_summary": get_symbol_summary_tool,
        "get_symbol_timeframe_ranges": get_symbol_timeframe_ranges_tool,
        "sync_symbols": sync_symbols_tool,
        "sync_range": sync_range_tool,
        "sync_funding": sync_funding_tool,
        "sync_open_interest": sync_open_interest_tool,
        "sync_to_now": sync_to_now_tool,
        "sync_forward": sync_forward_tool,
        "build_symbol_history": build_symbol_history_tool,
        "sync_data": sync_data_tool,
        "heal_data": heal_data_tool,
        "delete_symbol": delete_symbol_tool,
        "cleanup_empty_symbols": cleanup_empty_symbols_tool,
        "vacuum_database": vacuum_database_tool,
        "delete_all_data": delete_all_data_tool,
        "get_funding_history": get_funding_history_tool,
        "get_open_interest_history": get_open_interest_history_tool,
        "get_ohlcv_history": get_ohlcv_history_tool,
    }


SPECS = [
    # Info tools
    {
        "name": "get_database_stats",
        "description": "Get database statistics (size, symbol count, candle count)",
        "category": "data.info",
        "parameters": {"env": DATA_ENV_PARAM},
        "required": [],
    },
    {
        "name": "list_cached_symbols",
        "description": "List all symbols currently cached in the database",
        "category": "data.info",
        "parameters": {"env": DATA_ENV_PARAM},
        "required": [],
    },
    {
        "name": "get_symbol_status",
        "description": "Get per-symbol aggregate status (total candles, gaps, timeframe count)",
        "category": "data.info",
        "parameters": {
            "symbol": {"type": "string", "description": "Specific symbol to check", "optional": True},
            "env": DATA_ENV_PARAM,
        },
        "required": [],
    },
    {
        "name": "get_symbol_summary",
        "description": "Get high-level summary of all cached symbols",
        "category": "data.info",
        "parameters": {"env": DATA_ENV_PARAM},
        "required": [],
    },
    {
        "name": "get_symbol_timeframe_ranges",
        "description": "Get detailed per-symbol/timeframe breakdown with date ranges and health",
        "category": "data.info",
        "parameters": {
            "symbol": {"type": "string", "description": "Specific symbol to check", "optional": True},
            "env": DATA_ENV_PARAM,
        },
        "required": [],
    },
    # Sync tools
    {
        "name": "sync_symbols",
        "description": "Sync OHLCV data for symbols by period",
        "category": "data.sync",
        "parameters": {
            "symbols": {"type": "array", "items": {"type": "string"}, "description": "List of symbols to sync"},
            "period": {"type": "string", "description": "Period (1D, 1W, 1M, 3M, 6M, 1Y)", "default": "1M"},
            "timeframes": {"type": "array", "items": {"type": "string"}, "description": "Timeframes to sync", "optional": True},
            "env": DATA_ENV_PARAM,
        },
        "required": ["symbols"],
    },
    {
        "name": "sync_range",
        "description": "Sync OHLCV data for a specific date range",
        "category": "data.sync",
        "parameters": {
            "symbols": {"type": "array", "items": {"type": "string"}, "description": "List of symbols to sync"},
            "start": {"type": "string", "description": "Start datetime (ISO format)"},
            "end": {"type": "string", "description": "End datetime (ISO format)"},
            "timeframes": {"type": "array", "items": {"type": "string"}, "description": "Timeframes to sync", "optional": True},
            "env": DATA_ENV_PARAM,
        },
        "required": ["symbols", "start", "end"],
    },
    {
        "name": "sync_funding",
        "description": "Sync funding rate history for symbols",
        "category": "data.sync",
        "parameters": {
            "symbols": {"type": "array", "items": {"type": "string"}, "description": "List of symbols to sync"},
            "period": {"type": "string", "description": "Period (1M, 3M, 6M, 1Y)", "default": "3M"},
            "env": DATA_ENV_PARAM,
        },
        "required": ["symbols"],
    },
    {
        "name": "sync_open_interest",
        "description": "Sync open interest history for symbols",
        "category": "data.sync",
        "parameters": {
            "symbols": {"type": "array", "items": {"type": "string"}, "description": "List of symbols to sync"},
            "period": {"type": "string", "description": "Period (1D, 1W, 1M, 3M)", "default": "1M"},
            "interval": {"type": "string", "description": "Data interval (5min, 15min, 30min, 1h, 4h, D)", "default": "1h"},
            "env": DATA_ENV_PARAM,
        },
        "required": ["symbols"],
    },
    {
        "name": "sync_to_now",
        "description": "Sync data forward from last stored candle to now (no backfill)",
        "category": "data.sync",
        "parameters": {
            "symbols": {"type": "array", "items": {"type": "string"}, "description": "List of symbols to sync forward"},
            "timeframes": {"type": "array", "items": {"type": "string"}, "description": "Timeframes to sync", "optional": True},
            "env": DATA_ENV_PARAM,
        },
        "required": ["symbols"],
    },
    {
        "name": "sync_forward",
        "description": "Sync forward to now AND fill any gaps in existing data",
        "category": "data.sync",
        "parameters": {
            "symbols": {"type": "array", "items": {"type": "string"}, "description": "List of symbols to sync and heal"},
            "timeframes": {"type": "array", "items": {"type": "string"}, "description": "Timeframes to sync", "optional": True},
            "env": DATA_ENV_PARAM,
        },
        "required": ["symbols"],
    },
    {
        "name": "build_symbol_history",
        "description": "Build complete historical data (OHLCV + funding + open interest) for symbols",
        "category": "data.sync",
        "parameters": {
            "symbols": {"type": "array", "items": {"type": "string"}, "description": "List of symbols to build history for"},
            "period": {"type": "string", "description": "Period (1D, 1W, 1M, 3M, 6M, 1Y)", "default": "1M"},
            "timeframes": {"type": "array", "items": {"type": "string"}, "description": "OHLCV timeframes", "optional": True},
            "oi_interval": {"type": "string", "description": "Open interest interval", "optional": True},
            "env": DATA_ENV_PARAM,
        },
        "required": ["symbols"],
    },
    # Maintenance tools
    {
        "name": "sync_data",
        "description": "Auto-detect and sync gaps in cached data",
        "category": "data.maintenance",
        "parameters": {
            "symbol": {"type": "string", "description": "Specific symbol (None for all)", "optional": True},
            "timeframe": {"type": "string", "description": "Specific timeframe (None for all)", "optional": True},
            "env": DATA_ENV_PARAM,
        },
        "required": [],
    },
    {
        "name": "heal_data",
        "description": "Run comprehensive data integrity check and repair",
        "category": "data.maintenance",
        "parameters": {
            "symbol": {"type": "string", "description": "Specific symbol (None for all)", "optional": True},
            "fix_issues": {"type": "boolean", "description": "Auto-fix issues", "default": True},
            "fill_gaps_after": {"type": "boolean", "description": "Fill gaps after fixing", "default": True},
            "env": DATA_ENV_PARAM,
        },
        "required": [],
    },
    {
        "name": "delete_symbol",
        "description": "Delete all data for a symbol",
        "category": "data.maintenance",
        "parameters": {
            "symbol": {"type": "string", "description": "Symbol to delete"},
            "vacuum": {"type": "boolean", "description": "Vacuum database after deletion", "default": True},
            "env": DATA_ENV_PARAM,
        },
        "required": ["symbol"],
    },
    {
        "name": "cleanup_empty_symbols",
        "description": "Remove symbols with no data (invalid symbols)",
        "category": "data.maintenance",
        "parameters": {"env": DATA_ENV_PARAM},
        "required": [],
    },
    {
        "name": "vacuum_database",
        "description": "Vacuum the database to reclaim space",
        "category": "data.maintenance",
        "parameters": {"env": DATA_ENV_PARAM},
        "required": [],
    },
    {
        "name": "delete_all_data",
        "description": "Delete ALL data from the database (OHLCV, funding, OI). DESTRUCTIVE - cannot be undone.",
        "category": "data.maintenance",
        "parameters": {
            "vacuum": {"type": "boolean", "description": "Whether to vacuum after deletion", "default": True, "optional": True},
            "env": DATA_ENV_PARAM,
        },
        "required": [],
    },
    # Query tools
    {
        "name": "get_funding_history",
        "description": "Get funding rate history for a symbol from DuckDB. Use either 'period' OR 'start'/'end' (max 365 days).",
        "category": "data.query",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol (required)"},
            "period": {"type": "string", "description": "Relative period (1M, 3M, 6M, 1Y) - alternative to start/end", "optional": True},
            "start": {"type": "string", "description": "Start datetime ISO string", "optional": True},
            "end": {"type": "string", "description": "End datetime ISO string", "optional": True},
            "env": DATA_ENV_PARAM,
        },
        "required": ["symbol"],
    },
    {
        "name": "get_open_interest_history",
        "description": "Get open interest history for a symbol from DuckDB. Use either 'period' OR 'start'/'end' (max 365 days).",
        "category": "data.query",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol (required)"},
            "period": {"type": "string", "description": "Relative period (1M, 3M, 6M, 1Y) - alternative to start/end", "optional": True},
            "start": {"type": "string", "description": "Start datetime ISO string", "optional": True},
            "end": {"type": "string", "description": "End datetime ISO string", "optional": True},
            "env": DATA_ENV_PARAM,
        },
        "required": ["symbol"],
    },
    {
        "name": "get_ohlcv_history",
        "description": "Get OHLCV candlestick history for a symbol from DuckDB. Use either 'period' OR 'start'/'end' (max 365 days).",
        "category": "data.query",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol (required)"},
            "timeframe": {"type": "string", "description": "Candle timeframe (1m, 5m, 15m, 1h, 4h, D)", "default": "1h"},
            "period": {"type": "string", "description": "Relative period (1M, 3M, 6M, 1Y) - alternative to start/end", "optional": True},
            "start": {"type": "string", "description": "Start datetime ISO string", "optional": True},
            "end": {"type": "string", "description": "End datetime ISO string", "optional": True},
            "limit": {"type": "integer", "description": "Max number of candles to return", "optional": True},
            "env": DATA_ENV_PARAM,
        },
        "required": ["symbol"],
    },
]
