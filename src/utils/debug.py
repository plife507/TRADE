"""
Debug utilities for TRADE with hash tracing.

Provides structured logging gated on verbose/debug mode.
Context fields (play_hash, symbol, mode) are carried automatically
by structlog contextvars — bound once at engine startup via
``bind_engine_context()`` in ``logging_config.py``.

Usage:
    from src.utils.debug import debug_log, debug_trace, is_debug_enabled

    # Simple debug logging
    debug_log("Engine init", bars=1000, tf="15m")

    # With run hash (when available)
    debug_log("Trade opened", run_hash=run_hash, entry=42150.0)

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
import os
import time
from typing import Any, Callable

from .logger import get_module_logger

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

# Module-level logger under trade.* hierarchy
_logger = get_module_logger(__name__)


def is_debug_enabled() -> bool:
    """Check if debug mode is enabled."""
    return _debug_enabled


def enable_debug(enabled: bool = True) -> None:
    """Enable or disable debug mode programmatically."""
    global _debug_enabled
    _debug_enabled = enabled

    # Also set log level to DEBUG if enabling
    if enabled:
        import logging
        logging.getLogger("trade").setLevel(logging.DEBUG)


def is_verbose_enabled() -> bool:
    """Check if verbose mode is enabled (or debug, which implies verbose)."""
    return _verbose_enabled or _debug_enabled


def enable_verbose(enabled: bool = True) -> None:
    """Enable or disable verbose mode programmatically."""
    global _verbose_enabled
    _verbose_enabled = enabled


def verbose_log(
    message: str,
    *,
    bar_idx: int | None = None,
    **fields: Any,
) -> None:
    """Log a verbose message with structured context.

    Only logs if verbose or debug mode is enabled.
    Uses INFO level so it's visible with normal log handlers.

    Engine context (play_hash, symbol, mode) is automatically included
    via structlog contextvars.  ``bar_idx`` is temporarily bound so it
    appears as a JSON field in JSONL output.
    """
    if not is_verbose_enabled():
        return

    import structlog.contextvars

    # Temporarily bind bar_idx to structlog context for JSONL output
    if bar_idx is not None:
        structlog.contextvars.bind_contextvars(bar_idx=bar_idx)

    try:
        if fields:
            field_strs = [f"{k}={_format_value(v)}" for k, v in fields.items()]
            full_msg = f"{message}: {', '.join(field_strs)}"
        else:
            full_msg = message

        _logger.info(full_msg)
    finally:
        if bar_idx is not None:
            structlog.contextvars.unbind_contextvars("bar_idx")


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
    message: str,
    *,
    run_hash: str | None = None,
    bar_idx: int | None = None,
    **fields: Any,
) -> None:
    """Log a debug message with structured context.

    Only logs if debug mode is enabled (TRADE_DEBUG=1 or --debug).

    Engine context (play_hash, symbol, mode) is automatically included
    via structlog contextvars.  ``bar_idx`` and ``run_hash`` are
    temporarily bound so they appear as JSON fields in JSONL output.

    Args:
        message: Log message.
        run_hash: Optional run hash (for session start/end).
        bar_idx: Optional bar index (for bar-level events).
        **fields: Additional key=value pairs to include.

    Example:
        debug_log("Signal generated", bar_idx=247, action="ENTRY_LONG")
    """
    if not _debug_enabled:
        return

    import structlog.contextvars

    # Temporarily bind bar_idx / run_hash to structlog context
    extra_keys: list[str] = []
    if bar_idx is not None:
        structlog.contextvars.bind_contextvars(bar_idx=bar_idx)
        extra_keys.append("bar_idx")
    if run_hash is not None:
        structlog.contextvars.bind_contextvars(run_hash=run_hash)
        extra_keys.append("run_hash")

    try:
        # Build message with fields
        if fields:
            field_strs = [f"{k}={_format_value(v)}" for k, v in fields.items()]
            full_msg = f"{message}: {', '.join(field_strs)}"
        else:
            full_msg = message

        _logger.debug(full_msg)
    finally:
        # Unbind temporary keys
        if extra_keys:
            structlog.contextvars.unbind_contextvars(*extra_keys)


def _format_value(value: Any) -> str:
    """Format a value for debug output."""
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, (list, tuple)) and len(value) > 5:
        return f"[{len(value)} items]"
    return str(value)


def debug_milestone(
    bar_idx: int,
    total_bars: int,
    elapsed_seconds: float,
) -> None:
    """
    Log a bar processing milestone (every BAR_MILESTONE_INTERVAL bars).

    Only logs if bar_idx is a multiple of BAR_MILESTONE_INTERVAL.

    Args:
        bar_idx: Current bar index
        total_bars: Total bars to process
        elapsed_seconds: Time elapsed since start
    """
    if not _debug_enabled:
        return

    if bar_idx % BAR_MILESTONE_INTERVAL != 0 and bar_idx != total_bars:
        return

    debug_log(
        f"Milestone: {bar_idx}/{total_bars} bars processed ({elapsed_seconds:.1f}s)",
        bar_idx=bar_idx,
    )


def debug_signal(
    bar_idx: int,
    action: str,
    feature_values: dict[str, float] | None = None,
) -> None:
    """
    Log a signal generation event.

    Args:
        bar_idx: Bar index where signal generated
        action: Signal action (ENTRY_LONG, EXIT_LONG, etc.)
        feature_values: Optional dict of feature values that triggered
    """
    if not _debug_enabled:
        return

    fields: dict[str, Any] = {"action": action}
    if feature_values:
        fields.update(feature_values)

    debug_log(f"Signal {action}", bar_idx=bar_idx, **fields)


def debug_trade(
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
    debug_log(f"{trade_label} {event}", bar_idx=bar_idx, **fields)


def debug_run_complete(
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

    debug_log("Complete", run_hash=run_hash, **fields)

    if artifact_path:
        debug_log(f"Artifacts: {artifact_path}", run_hash=run_hash)


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

        _logger.debug(f"[trace] ENTER {func_name}")
        start = time.perf_counter()

        try:
            result = func(*args, **kwargs)
            elapsed = (time.perf_counter() - start) * 1000
            _logger.debug(f"[trace] EXIT {func_name} ({elapsed:.2f}ms)")
            return result
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            _logger.debug(f"[trace] RAISE {func_name} ({elapsed:.2f}ms): {type(e).__name__}")
            raise

    return wrapper


def debug_snapshot(
    bar_idx: int,
    snapshot_data: dict[str, Any],
    *,
    max_features: int = 10,
) -> None:
    """Dump snapshot state for debugging.

    Engine context (play_hash, symbol, mode) is automatically included
    via structlog contextvars.

    Args:
        bar_idx: Current bar index.
        snapshot_data: Dict of snapshot values to log.
        max_features: Maximum number of features to show.
    """
    if not _debug_enabled:
        return

    import structlog.contextvars

    structlog.contextvars.bind_contextvars(bar_idx=bar_idx)
    try:
        _logger.debug("Snapshot dump:")

        items = list(snapshot_data.items())[:max_features]
        for key, value in items:
            _logger.debug(f"  {key}: {_format_value(value)}")

        if len(snapshot_data) > max_features:
            _logger.debug(f"  ... and {len(snapshot_data) - max_features} more")
    finally:
        structlog.contextvars.unbind_contextvars("bar_idx")
