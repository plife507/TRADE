"""Subcommand handlers for TRADE CLI.

Re-exports all handle_* functions so existing imports like
``from src.cli.subcommands import handle_backtest_run`` continue to work.
"""

from src.cli.subcommands.backtest import (
    handle_backtest_run,
    handle_backtest_preflight,
    handle_backtest_indicators,
    handle_backtest_data_fix,
    handle_backtest_list,
    handle_backtest_normalize,
    handle_backtest_normalize_batch,
)
from src.cli.subcommands.debug import (
    handle_debug_math_parity,
    handle_debug_snapshot_plumbing,
    handle_debug_determinism,
    handle_debug_metrics,
)
from src.cli.subcommands.play import (
    handle_play_run,
    handle_play_status,
    handle_play_stop,
    handle_play_watch,
    handle_play_logs,
    handle_play_pause,
    handle_play_resume,
)
from src.cli.subcommands.trading import (
    handle_account_balance,
    handle_account_exposure,
    handle_account_info,
    handle_account_history,
    handle_account_pnl,
    handle_account_transactions,
    handle_account_collateral,
    handle_position_list,
    handle_position_close,
    handle_position_set_tp,
    handle_position_set_sl,
    handle_position_set_tpsl,
    handle_position_trailing,
    handle_position_partial_close,
    handle_position_margin,
    handle_position_risk_limit,
    handle_position_detail,
    handle_panic,
)
from src.cli.subcommands.health import (
    handle_health_check,
    handle_health_connection,
    handle_health_rate_limit,
    handle_health_ws,
    handle_health_environment,
)
from src.cli.subcommands.data import (
    handle_data_sync,
    handle_data_info,
    handle_data_symbols,
    handle_data_status,
    handle_data_summary,
    handle_data_query,
    handle_data_heal,
    handle_data_vacuum,
    handle_data_delete,
)
from src.cli.subcommands.market import (
    handle_market_price,
    handle_market_ohlcv,
    handle_market_funding,
    handle_market_oi,
    handle_market_orderbook,
    handle_market_instruments,
)
from src.cli.subcommands.order import (
    handle_order_buy,
    handle_order_sell,
    handle_order_list,
    handle_order_amend,
    handle_order_cancel,
    handle_order_cancel_all,
    handle_order_leverage,
    handle_order_batch,
)

__all__ = [
    # Backtest
    "handle_backtest_run",
    "handle_backtest_preflight",
    "handle_backtest_indicators",
    "handle_backtest_data_fix",
    "handle_backtest_list",
    "handle_backtest_normalize",
    "handle_backtest_normalize_batch",
    # Debug
    "handle_debug_math_parity",
    "handle_debug_snapshot_plumbing",
    "handle_debug_determinism",
    "handle_debug_metrics",
    # Play
    "handle_play_run",
    "handle_play_status",
    "handle_play_stop",
    "handle_play_watch",
    "handle_play_logs",
    "handle_play_pause",
    "handle_play_resume",
    # Trading — Account
    "handle_account_balance",
    "handle_account_exposure",
    "handle_account_info",
    "handle_account_history",
    "handle_account_pnl",
    "handle_account_transactions",
    "handle_account_collateral",
    # Trading — Position
    "handle_position_list",
    "handle_position_close",
    "handle_position_set_tp",
    "handle_position_set_sl",
    "handle_position_set_tpsl",
    "handle_position_trailing",
    "handle_position_partial_close",
    "handle_position_margin",
    "handle_position_risk_limit",
    "handle_position_detail",
    "handle_panic",
    # Health
    "handle_health_check",
    "handle_health_connection",
    "handle_health_rate_limit",
    "handle_health_ws",
    "handle_health_environment",
    # Data
    "handle_data_sync",
    "handle_data_info",
    "handle_data_symbols",
    "handle_data_status",
    "handle_data_summary",
    "handle_data_query",
    "handle_data_heal",
    "handle_data_vacuum",
    "handle_data_delete",
    # Market
    "handle_market_price",
    "handle_market_ohlcv",
    "handle_market_funding",
    "handle_market_oi",
    "handle_market_orderbook",
    "handle_market_instruments",
    # Order
    "handle_order_buy",
    "handle_order_sell",
    "handle_order_list",
    "handle_order_amend",
    "handle_order_cancel",
    "handle_order_cancel_all",
    "handle_order_leverage",
    "handle_order_batch",
]
