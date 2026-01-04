"""
Historical data management tools for TRADE trading bot.

This module re-exports all data tools from their specialized modules:
- data_tools_common: Constants and helper functions
- data_tools_status: Database status and info tools
- data_tools_sync: Sync and maintenance tools
- data_tools_query: Query and composite tools

Environment-aware: All tools default to "live" environment for data operations.
Pass env="demo" to operate on demo history instead.
"""

# Re-export all public symbols from split modules
from .data_tools_common import (
    TF_GROUP_LOW,
    TF_GROUP_MID,
    TF_GROUP_HIGH,
    ALL_TIMEFRAMES,
    MAX_CHUNK_DAYS,
    DEFAULT_MAX_HISTORY_YEARS,
)

from .data_tools_status import (
    get_database_stats_tool,
    list_cached_symbols_tool,
    get_symbol_status_tool,
    get_symbol_summary_tool,
    get_symbol_timeframe_ranges_tool,
    get_data_extremes_tool,
)

from .data_tools_sync import (
    sync_symbols_tool,
    sync_range_tool,
    fill_gaps_tool,
    heal_data_tool,
    delete_symbol_tool,
    cleanup_empty_symbols_tool,
    vacuum_database_tool,
    delete_all_data_tool,
    sync_funding_tool,
    sync_open_interest_tool,
    get_instrument_launch_time_tool,
    sync_full_from_launch_tool,
)

from .data_tools_query import (
    get_funding_history_tool,
    get_ohlcv_history_tool,
    get_open_interest_history_tool,
    sync_to_now_tool,
    sync_to_now_and_fill_gaps_tool,
    build_symbol_history_tool,
)

__all__ = [
    # Constants
    "TF_GROUP_LOW",
    "TF_GROUP_MID",
    "TF_GROUP_HIGH",
    "ALL_TIMEFRAMES",
    "MAX_CHUNK_DAYS",
    "DEFAULT_MAX_HISTORY_YEARS",
    # Status tools
    "get_database_stats_tool",
    "list_cached_symbols_tool",
    "get_symbol_status_tool",
    "get_symbol_summary_tool",
    "get_symbol_timeframe_ranges_tool",
    "get_data_extremes_tool",
    # Sync tools
    "sync_symbols_tool",
    "sync_range_tool",
    "fill_gaps_tool",
    "heal_data_tool",
    "delete_symbol_tool",
    "cleanup_empty_symbols_tool",
    "vacuum_database_tool",
    "delete_all_data_tool",
    "sync_funding_tool",
    "sync_open_interest_tool",
    "get_instrument_launch_time_tool",
    "sync_full_from_launch_tool",
    # Query tools
    "get_funding_history_tool",
    "get_ohlcv_history_tool",
    "get_open_interest_history_tool",
    "sync_to_now_tool",
    "sync_to_now_and_fill_gaps_tool",
    "build_symbol_history_tool",
]
