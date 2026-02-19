"""
Debug utilities for TRADE with hash tracing.

Provides hash-prefixed logging for exactitude in debugging.
Every debug log line includes play_hash and optional run_hash
to enable precise correlation with backtest runs.

Usage:
    from src.utils.debug import debug_log, debug_trace, is_debug_enabled

    # Simple debug logging with hash prefix
    debug_log(play_hash, "Engine init", bars=1000, tf="15m")

    # With run hash (when available)
    debug_log(play_hash, "Trade opened", run_hash=run_hash, entry=42150.0)

    # Decorator for function tracing
    @debug_trace
    def process_bar(self, bar_idx: int) -> None:
        ...

Enable debugging:
    - Set environment variable: TRADE_DEBUG=1
    - Or use CLI flag: --debug
"""

from __future__ import annotations

import functools
import logging
import os
import time
from typing import Any, Callable

# =============================================================================
# Configuration
# =============================================================================

# Check for debug mode
_DEBUG_ENV = os.environ.get("TRADE_DEBUG", "").lower() in ("1", "true", "yes")
_debug_enabled = _DEBUG_ENV

# Verbose mode (signal traces, structure events)
_verbose_enabled = False

# Hash display length (first N chars of 16-char hashes)
HASH_DISPLAY_LENGTH = 8

# Logging threshold for bar milestones (log every N bars)
BAR_MILESTONE_INTERVAL = 100


def is_debug_enabled() -> bool:
    """Check if debug mode is enabled."""
    return _debug_enabled


def enable_debug(enabled: bool = True) -> None:
    """Enable or disable debug mode programmatically."""
    global _debug_enabled
    _debug_enabled = enabled

    # Also set log level to DEBUG if enabling
    if enabled:
        logging.getLogger("trade").setLevel(logging.DEBUG)


def is_verbose_enabled() -> bool:
    """Check if verbose mode is enabled (or debug, which implies verbose)."""
    return _verbose_enabled or _debug_enabled


def enable_verbose(enabled: bool = True) -> None:
    """Enable or disable verbose mode programmatically."""
    global _verbose_enabled
    _verbose_enabled = enabled


def verbose_log(
    play_hash: str | None,
    message: str,
    *,
    bar_idx: int | None = None,
    **fields: Any,
) -> None:
    """Log a verbose message with hash prefix.

    Only logs if verbose or debug mode is enabled.
    Uses INFO level so it's visible with normal log handlers.
    """
    if not is_verbose_enabled():
        return

    prefix = format_hash_prefix(play_hash, bar_idx=bar_idx)

    if fields:
        field_strs = [f"{k}={_format_value(v)}" for k, v in fields.items()]
        full_msg = f"{message}: {', '.join(field_strs)}"
    else:
        full_msg = message

    logger = logging.getLogger("trade")
    logger.info(f"{prefix} {full_msg}")


def short_hash(full_hash: str | None) -> str:
    """Format a hash for display (first N chars)."""
    if not full_hash:
        return "--"
    return full_hash[:HASH_DISPLAY_LENGTH]


def format_hash_prefix(
    play_hash: str | None,
    run_hash: str | None = None,
    bar_idx: int | None = None,
) -> str:
    """
    Format consistent hash prefix for debug log lines.

    Examples:
        [play:8f2a9c1d]
        [play:8f2a9c1d] [run:e5f6g7h8]
        [play:8f2a9c1d] [bar:247]
        [play:8f2a9c1d] [run:e5f6g7h8] [bar:247]
    """
    parts = [f"[play:{short_hash(play_hash)}]"]

    if run_hash:
        parts.append(f"[run:{short_hash(run_hash)}]")

    if bar_idx is not None:
        parts.append(f"[bar:{bar_idx}]")

    return " ".join(parts)


def debug_log(
    play_hash: str | None,
    message: str,
    *,
    run_hash: str | None = None,
    bar_idx: int | None = None,
    **fields: Any,
) -> None:
    """
    Log a debug message with hash prefix for exactitude.

    Only logs if debug mode is enabled (TRADE_DEBUG=1 or --debug).

    Args:
        play_hash: Play configuration hash (16 chars, displays first 8)
        message: Log message
        run_hash: Optional run hash (for session start/end)
        bar_idx: Optional bar index (for bar-level events)
        **fields: Additional key=value pairs to include

    Example:
        debug_log("8f2a9c1d", "Signal generated", bar_idx=247, action="ENTRY_LONG")
        # Output: [DEBUG] [play:8f2a9c1d] [bar:247] Signal generated: action=ENTRY_LONG
    """
    if not _debug_enabled:
        return

    # Build prefix
    prefix = format_hash_prefix(play_hash, run_hash, bar_idx)

    # Build message with fields
    if fields:
        field_strs = [f"{k}={_format_value(v)}" for k, v in fields.items()]
        full_msg = f"{message}: {', '.join(field_strs)}"
    else:
        full_msg = message

    # Log via standard logger
    logger = logging.getLogger("trade")
    logger.debug(f"{prefix} {full_msg}")


def _format_value(value: Any) -> str:
    """Format a value for debug output."""
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, (list, tuple)) and len(value) > 5:
        return f"[{len(value)} items]"
    return str(value)


def debug_milestone(
    play_hash: str | None,
    bar_idx: int,
    total_bars: int,
    elapsed_seconds: float,
) -> None:
    """
    Log a bar processing milestone (every BAR_MILESTONE_INTERVAL bars).

    Only logs if bar_idx is a multiple of BAR_MILESTONE_INTERVAL.

    Args:
        play_hash: Play configuration hash
        bar_idx: Current bar index
        total_bars: Total bars to process
        elapsed_seconds: Time elapsed since start
    """
    if not _debug_enabled:
        return

    if bar_idx % BAR_MILESTONE_INTERVAL != 0 and bar_idx != total_bars:
        return

    debug_log(
        play_hash,
        f"Milestone: {bar_idx}/{total_bars} bars processed ({elapsed_seconds:.1f}s)",
        bar_idx=bar_idx,
    )


def debug_signal(
    play_hash: str | None,
    bar_idx: int,
    action: str,
    feature_values: dict[str, float] | None = None,
) -> None:
    """
    Log a signal generation event.

    Args:
        play_hash: Play configuration hash
        bar_idx: Bar index where signal generated
        action: Signal action (ENTRY_LONG, EXIT_LONG, etc.)
        feature_values: Optional dict of feature values that triggered
    """
    if not _debug_enabled:
        return

    fields: dict[str, Any] = {"action": action}
    if feature_values:
        fields.update(feature_values)

    debug_log(play_hash, f"Signal {action}", bar_idx=bar_idx, **fields)


def debug_trade(
    play_hash: str | None,
    bar_idx: int,
    event: str,
    *,
    trade_num: int | None = None,
    entry: float | None = None,
    exit: float | None = None,
    sl: float | None = None,
    tp: float | None = None,
    pnl: float | None = None,
    pnl_pct: float | None = None,
) -> None:
    """
    Log a trade event (opened, closed, SL hit, TP hit).

    Args:
        play_hash: Play configuration hash
        bar_idx: Bar index of event
        event: Event type (opened, closed, sl_hit, tp_hit)
        trade_num: Trade number in sequence
        entry: Entry price
        exit: Exit price
        sl: Stop loss level
        tp: Take profit level
        pnl: PnL in USDT
        pnl_pct: PnL as percentage
    """
    if not _debug_enabled:
        return

    fields: dict[str, Any] = {}
    if trade_num is not None:
        fields["trade"] = f"#{trade_num}"
    if entry is not None:
        fields["entry"] = entry
    if exit is not None:
        fields["exit"] = exit
    if sl is not None:
        fields["sl"] = sl
    if tp is not None:
        fields["tp"] = tp
    if pnl is not None:
        fields["pnl"] = f"{'+' if pnl >= 0 else ''}{pnl:.2f}"
    if pnl_pct is not None:
        fields["pnl_pct"] = f"{'+' if pnl_pct >= 0 else ''}{pnl_pct:.2f}%"

    trade_label = f"Trade #{trade_num}" if trade_num else "Trade"
    debug_log(play_hash, f"{trade_label} {event}", bar_idx=bar_idx, **fields)


def debug_run_complete(
    play_hash: str | None,
    run_hash: str | None,
    *,
    trades_hash: str | None = None,
    equity_hash: str | None = None,
    trades_count: int | None = None,
    elapsed_seconds: float | None = None,
    artifact_path: str | None = None,
) -> None:
    """
    Log run completion with all hashes for verification.

    Args:
        play_hash: Play configuration hash
        run_hash: Combined run hash
        trades_hash: Trade sequence hash
        equity_hash: Equity curve hash
        trades_count: Number of trades
        elapsed_seconds: Total run time
        artifact_path: Path to artifacts
    """
    if not _debug_enabled:
        return

    fields: dict[str, Any] = {}
    if trades_hash:
        fields["trades_hash"] = short_hash(trades_hash)
    if equity_hash:
        fields["equity_hash"] = short_hash(equity_hash)
    if trades_count is not None:
        fields["trades"] = trades_count
    if elapsed_seconds is not None:
        fields["elapsed"] = f"{elapsed_seconds:.1f}s"

    debug_log(play_hash, "Complete", run_hash=run_hash, **fields)

    if artifact_path:
        debug_log(play_hash, f"Artifacts: {artifact_path}", run_hash=run_hash)


def debug_trace(func: Callable) -> Callable:
    """
    Decorator to trace function entry/exit with timing.

    Only traces if debug mode is enabled.

    Usage:
        @debug_trace
        def process_bar(self, bar_idx: int) -> None:
            ...
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if not _debug_enabled:
            return func(*args, **kwargs)

        func_name = func.__qualname__
        logger = logging.getLogger("trade")

        logger.debug(f"[trace] ENTER {func_name}")
        start = time.perf_counter()

        try:
            result = func(*args, **kwargs)
            elapsed = (time.perf_counter() - start) * 1000
            logger.debug(f"[trace] EXIT {func_name} ({elapsed:.2f}ms)")
            return result
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            logger.debug(f"[trace] RAISE {func_name} ({elapsed:.2f}ms): {type(e).__name__}")
            raise

    return wrapper


def debug_snapshot(
    play_hash: str | None,
    bar_idx: int,
    snapshot_data: dict[str, Any],
    *,
    max_features: int = 10,
) -> None:
    """
    Dump snapshot state for debugging.

    Args:
        play_hash: Play configuration hash
        bar_idx: Current bar index
        snapshot_data: Dict of snapshot values to log
        max_features: Maximum number of features to show
    """
    if not _debug_enabled:
        return

    prefix = format_hash_prefix(play_hash, bar_idx=bar_idx)
    logger = logging.getLogger("trade")

    logger.debug(f"{prefix} Snapshot dump:")

    items = list(snapshot_data.items())[:max_features]
    for key, value in items:
        logger.debug(f"{prefix}   {key}: {_format_value(value)}")

    if len(snapshot_data) > max_features:
        logger.debug(f"{prefix}   ... and {len(snapshot_data) - max_features} more")
