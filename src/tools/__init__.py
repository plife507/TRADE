"""
Tools layer for TRADE trading bot.

This package provides callable tools that can be invoked by:
- The CLI (trade_cli.py)
- Orchestrators/bots via ToolRegistry
- AI agents (function calling format)
- Future FastAPI endpoints

All position management, trading operations, market data, and diagnostics
should go through these tools rather than calling core modules directly,
ensuring a single integration point.

Core Modules:
- shared.py: ToolResult type and common helpers
- tool_registry.py: Tool discovery and orchestration
- position_tools.py: Position listing, TP/SL, trailing stops, close/panic
- account_tools.py: Account balance, exposure, portfolio snapshot
- order_tools.py: Complete order execution (Market, Limit, Stop, Batch)
- diagnostics_tools.py: Connection testing, health checks
- market_data_tools.py: Prices, OHLCV, funding rates, orderbooks
- data_tools.py: Historical data management (DuckDB)

Usage:
    from src.tools import (
        ToolResult,
        # Position tools
        list_open_positions_tool,
        close_position_tool,
        panic_close_all_tool,
        # Account tools
        get_account_balance_tool,
        # Order tools
        market_buy_tool,
        market_sell_tool,
        # Diagnostics tools
        test_connection_tool,
        exchange_health_check_tool,
        # Market data tools
        get_price_tool,
        get_ohlcv_tool,
        # Data tools
        sync_symbols_tool,
    )
    
    # Example: List all open positions
    result = list_open_positions_tool()
    if result.success:
        for pos in result.data["positions"]:
            print(f"{pos['symbol']}: {pos['size']} @ {pos['entry_price']}")
"""

# Shared types
from .shared import ToolResult

# Position tools
from .position_tools import (
    list_open_positions_tool,
    get_position_detail_tool,
    set_stop_loss_tool,
    remove_stop_loss_tool,
    set_take_profit_tool,
    remove_take_profit_tool,
    set_trailing_stop_tool,
    set_trailing_stop_by_percent_tool,
    set_position_tpsl_tool,
    close_position_tool,
    panic_close_all_tool,
    # Position configuration tools
    set_risk_limit_tool,
    get_risk_limits_tool,
    set_tp_sl_mode_tool,
    set_auto_add_margin_tool,
    modify_position_margin_tool,
    switch_margin_mode_tool,
    switch_position_mode_tool,
)

# Account tools
from .account_tools import (
    get_account_balance_tool,
    get_total_exposure_tool,
    get_account_info_tool,
    get_portfolio_snapshot_tool,
    get_order_history_tool,
    get_closed_pnl_tool,
    # Unified account tools
    get_transaction_log_tool,
    get_collateral_info_tool,
    set_collateral_coin_tool,
    get_borrow_history_tool,
    get_coin_greeks_tool,
    set_account_margin_mode_tool,
    get_transferable_amount_tool,
)

# Order tools
from .order_tools import (
    # Market orders
    set_leverage_tool,
    market_buy_tool,
    market_sell_tool,
    market_buy_with_tpsl_tool,
    market_sell_with_tpsl_tool,
    # Limit orders
    limit_buy_tool,
    limit_sell_tool,
    partial_close_position_tool,
    # Stop orders (conditional)
    stop_market_buy_tool,
    stop_market_sell_tool,
    stop_limit_buy_tool,
    stop_limit_sell_tool,
    # Order management
    get_open_orders_tool,
    cancel_order_tool,
    amend_order_tool,
    cancel_all_orders_tool,
    # Batch orders
    batch_market_orders_tool,
    batch_limit_orders_tool,
    batch_cancel_orders_tool,
)

# Diagnostics tools
from .diagnostics_tools import (
    test_connection_tool,
    get_server_time_offset_tool,
    get_rate_limit_status_tool,
    get_ticker_tool,
    get_websocket_status_tool,
    exchange_health_check_tool,
    is_healthy_for_trading_tool,
    get_api_environment_tool,
)

# Market data tools
from .market_data_tools import (
    get_price_tool,
    get_ohlcv_tool,
    get_funding_rate_tool,
    get_open_interest_tool,
    get_orderbook_tool,
    get_instruments_tool,
    run_market_data_tests_tool,
)

# Data tools (historical data / DuckDB)
from .data_tools import (
    get_database_stats_tool,
    list_cached_symbols_tool,
    get_symbol_status_tool,
    get_symbol_summary_tool,
    get_symbol_timeframe_ranges_tool,
    sync_symbols_tool,
    sync_range_tool,
    fill_gaps_tool,
    heal_data_tool,
    delete_symbol_tool,
    cleanup_empty_symbols_tool,
    vacuum_database_tool,
    delete_all_data_tool,
    # Funding rate tools
    sync_funding_tool,
    get_funding_history_tool,
    # Open interest tools
    sync_open_interest_tool,
    get_open_interest_history_tool,
    # OHLCV query tools
    get_ohlcv_history_tool,
    # Sync to now tools
    sync_to_now_tool,
    sync_to_now_and_fill_gaps_tool,
    # Composite build tools
    build_symbol_history_tool,
)

# Backtest tools (SystemConfig-based, legacy)
from .backtest_tools import (
    backtest_list_systems_tool,
    backtest_get_system_tool,
    backtest_run_tool,
    backtest_prepare_data_tool,
    backtest_verify_data_tool,
    backtest_list_strategies_tool,
)

# Backtest CLI wrapper tools (IdeaCard-based, golden path)
from .backtest_cli_wrapper import (
    backtest_preflight_idea_card_tool,
    backtest_run_idea_card_tool,
    backtest_data_fix_tool,
    backtest_list_idea_cards_tool,
    backtest_indicators_tool,
    verify_artifact_parity_tool,
)

__all__ = [
    # Shared types
    "ToolResult",
    
    # Position tools
    "list_open_positions_tool",
    "get_position_detail_tool",
    "set_stop_loss_tool",
    "remove_stop_loss_tool",
    "set_take_profit_tool",
    "remove_take_profit_tool",
    "set_trailing_stop_tool",
    "set_trailing_stop_by_percent_tool",
    "set_position_tpsl_tool",
    "close_position_tool",
    "panic_close_all_tool",
    # Position configuration tools
    "set_risk_limit_tool",
    "get_risk_limits_tool",
    "set_tp_sl_mode_tool",
    "set_auto_add_margin_tool",
    "modify_position_margin_tool",
    "switch_margin_mode_tool",
    "switch_position_mode_tool",
    
    # Account tools
    "get_account_balance_tool",
    "get_total_exposure_tool",
    "get_account_info_tool",
    "get_portfolio_snapshot_tool",
    "get_order_history_tool",
    "get_closed_pnl_tool",
    # Unified account tools
    "get_transaction_log_tool",
    "get_collateral_info_tool",
    "set_collateral_coin_tool",
    "get_borrow_history_tool",
    "get_coin_greeks_tool",
    "set_account_margin_mode_tool",
    "get_transferable_amount_tool",
    
    # Order tools - Market orders
    "set_leverage_tool",
    "market_buy_tool",
    "market_sell_tool",
    "market_buy_with_tpsl_tool",
    "market_sell_with_tpsl_tool",
    # Order tools - Limit orders
    "limit_buy_tool",
    "limit_sell_tool",
    "partial_close_position_tool",
    # Order tools - Stop orders (conditional)
    "stop_market_buy_tool",
    "stop_market_sell_tool",
    "stop_limit_buy_tool",
    "stop_limit_sell_tool",
    # Order tools - Management
    "get_open_orders_tool",
    "cancel_order_tool",
    "amend_order_tool",
    "cancel_all_orders_tool",
    # Order tools - Batch
    "batch_market_orders_tool",
    "batch_limit_orders_tool",
    "batch_cancel_orders_tool",
    # Diagnostics tools
    "test_connection_tool",
    "get_server_time_offset_tool",
    "get_rate_limit_status_tool",
    "get_ticker_tool",
    "get_websocket_status_tool",
    "exchange_health_check_tool",
    "is_healthy_for_trading_tool",
    "get_api_environment_tool",
    
    # Market data tools
    "get_price_tool",
    "get_ohlcv_tool",
    "get_funding_rate_tool",
    "get_open_interest_tool",
    "get_orderbook_tool",
    "get_instruments_tool",
    "run_market_data_tests_tool",
    
    # Data tools
    "get_database_stats_tool",
    "list_cached_symbols_tool",
    "get_symbol_status_tool",
    "get_symbol_summary_tool",
    "get_symbol_timeframe_ranges_tool",
    "sync_symbols_tool",
    "sync_range_tool",
    "fill_gaps_tool",
    "heal_data_tool",
    "delete_symbol_tool",
    "cleanup_empty_symbols_tool",
    "vacuum_database_tool",
    "delete_all_data_tool",
    # Funding rate tools
    "sync_funding_tool",
    "get_funding_history_tool",
    # Open interest tools
    "sync_open_interest_tool",
    "get_open_interest_history_tool",
    # OHLCV query tools
    "get_ohlcv_history_tool",
    # Sync to now tools
    "sync_to_now_tool",
    "sync_to_now_and_fill_gaps_tool",
    # Composite build tools
    "build_symbol_history_tool",
    
    # Backtest tools (SystemConfig-based, legacy)
    "backtest_list_systems_tool",
    "backtest_get_system_tool",
    "backtest_run_tool",
    "backtest_prepare_data_tool",
    "backtest_verify_data_tool",
    "backtest_list_strategies_tool",
    
    # Backtest CLI wrapper tools (IdeaCard-based, golden path)
    "backtest_preflight_idea_card_tool",
    "backtest_run_idea_card_tool",
    "backtest_data_fix_tool",
    "backtest_list_idea_cards_tool",
    "backtest_indicators_tool",
    "verify_artifact_parity_tool",
]
