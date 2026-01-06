"""
Backtest logging module.

Provides organized per-run and play-indexed logging for backtests.
"""

from .run_logger import (
    RunLogger,
    RunLogContext,
    write_run_index_entry,
    get_run_logger,
    set_run_logger,
)

__all__ = [
    "RunLogger",
    "RunLogContext",
    "write_run_index_entry",
    "get_run_logger",
    "set_run_logger",
]
