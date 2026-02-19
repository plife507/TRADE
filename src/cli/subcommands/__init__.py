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
    handle_position_list,
    handle_position_close,
    handle_panic,
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
    # Trading
    "handle_account_balance",
    "handle_account_exposure",
    "handle_position_list",
    "handle_position_close",
    "handle_panic",
]
