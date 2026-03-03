"""
Per-run logging for backtests.

Provides organized log structure:
1. Per-run logs in artifact folder: backtests/.../logs/engine_debug.log
2. Global play-indexed logs: logs/backtests/{play_hash}/index.jsonl

Usage:
    from src.backtest.logging import RunLogger, get_run_logger

    # Initialize at run start
    run_logger = RunLogger(
        play_hash="8f2a9c1d",
        run_id="e5f6g7h8",
        artifact_dir=Path("backtests/_validation/V_100/BTCUSDT/e5f6g7h8/"),
    )

    # Log messages (writes to both per-run and global)
    run_logger.debug("Engine init", bars=1000, tf="15m")
    run_logger.info("Signal generated", action="ENTRY_LONG")

    # Finalize at run end (writes index entry)
    run_logger.finalize(net_pnl=125.50, trades_count=12)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ...utils.datetime_utils import utc_now

# Global logs directory
GLOBAL_LOGS_DIR = Path("logs/backtests")

# Per-run logs directory name (inside artifact folder)
RUN_LOGS_DIR = "logs"


@dataclass
class RunLogContext:
    """Context for a backtest run."""

    play_hash: str
    run_id: str
    play_id: str | None = None
    symbol: str | None = None
    tf: str | None = None


from ...utils.debug import short_hash


class RunLogger:
    """
    Per-run logger that writes to:
    1. Per-run log file in artifact folder
    2. Global play-indexed log directory
    """

    def __init__(
        self,
        play_hash: str,
        run_id: str,
        artifact_dir: Path | None = None,
        *,
        play_id: str | None = None,
        symbol: str | None = None,
        tf: str | None = None,
    ):
        """
        Initialize per-run logger.

        Args:
            play_hash: Play configuration hash (16 chars)
            run_id: Run identifier (8-12 chars hash or UUID)
            artifact_dir: Path to artifact directory (for per-run logs)
            play_id: Play identifier (e.g., "V_100_blocks_basic")
            symbol: Trading symbol (e.g., "BTCUSDT")
            tf: Timeframe (e.g., "15m")
        """
        self.play_hash = play_hash
        self.run_id = run_id
        self.artifact_dir = Path(artifact_dir) if artifact_dir else None
        self.play_id = play_id
        self.symbol = symbol
        self.tf = tf

        self._ts_start = utc_now()
        self._ts_end: datetime | None = None

        # Get standard logger FIRST (needed by _setup_run_log)
        self._logger = logging.getLogger("trade.backtest.run")

        # Setup per-run log file (if artifact_dir provided)
        self._run_log_file: Path | None = None
        self._run_log_handler: logging.FileHandler | None = None
        if self.artifact_dir:
            self._setup_run_log()

        # Setup global play-indexed directory
        self._play_log_dir = GLOBAL_LOGS_DIR / short_hash(play_hash)
        self._play_log_dir.mkdir(parents=True, exist_ok=True)

    def _setup_run_log(self) -> None:
        """Setup per-run log file in artifact directory."""
        if not self.artifact_dir:
            return

        # Create logs subdirectory in artifact folder
        logs_dir = self.artifact_dir / RUN_LOGS_DIR
        logs_dir.mkdir(parents=True, exist_ok=True)

        # Create engine_debug.log file
        self._run_log_file = logs_dir / "engine_debug.log"

        # Create file handler
        self._run_log_handler = logging.FileHandler(
            self._run_log_file, mode="w", encoding="utf-8"
        )
        self._run_log_handler.setLevel(logging.DEBUG)
        self._run_log_handler.setFormatter(
            logging.Formatter(
                "[%(levelname)s] %(message)s",
                datefmt="%H:%M:%S",
            )
        )

        # Add handler to logger
        self._logger.addHandler(self._run_log_handler)

    def _log_with_fields(
        self,
        level: str,
        message: str,
        bar_idx: int | None,
        fields: dict[str, Any],
    ) -> None:
        """Log a message with bar_idx and **fields as temporary contextvars."""
        import structlog.contextvars

        bound_keys: list[str] = []
        if bar_idx is not None:
            structlog.contextvars.bind_contextvars(bar_idx=bar_idx)
            bound_keys.append("bar_idx")
        if fields:
            structlog.contextvars.bind_contextvars(**fields)
            bound_keys.extend(fields.keys())

        try:
            getattr(self._logger, level)(message)
        finally:
            if bound_keys:
                structlog.contextvars.unbind_contextvars(*bound_keys)

    def debug(
        self, message: str, *, bar_idx: int | None = None, **fields: Any
    ) -> None:
        """Log debug message with structured context."""
        self._log_with_fields("debug", message, bar_idx, fields)

    def info(
        self, message: str, *, bar_idx: int | None = None, **fields: Any
    ) -> None:
        """Log info message with structured context."""
        self._log_with_fields("info", message, bar_idx, fields)

    def warning(
        self, message: str, *, bar_idx: int | None = None, **fields: Any
    ) -> None:
        """Log warning message with structured context."""
        self._log_with_fields("warning", message, bar_idx, fields)

    def error(
        self, message: str, *, bar_idx: int | None = None, **fields: Any
    ) -> None:
        """Log error message with structured context."""
        self._log_with_fields("error", message, bar_idx, fields)

    def finalize(
        self,
        *,
        net_pnl: float | None = None,
        trades_count: int | None = None,
        status: str = "success",
        trades_hash: str | None = None,
        run_hash: str | None = None,
    ) -> None:
        """
        Finalize run logging.

        - Closes per-run log file
        - Writes summary log to global play directory
        - Appends entry to index.jsonl

        Args:
            net_pnl: Net PnL in USDT
            trades_count: Number of trades
            status: Run status (success, error, stopped)
            trades_hash: Determinism hash of trades output
            run_hash: Combined run hash (trades + equity + play)
        """
        self._ts_end = utc_now()

        # Close per-run file handler
        if self._run_log_handler:
            self._run_log_handler.close()
            self._logger.removeHandler(self._run_log_handler)

        # Write summary log to global directory
        timestamp_str = self._ts_start.strftime("%Y%m%d_%H%M%S")
        summary_filename = f"run_{timestamp_str}_{short_hash(self.run_id)}.log"
        summary_path = self._play_log_dir / summary_filename

        elapsed = (self._ts_end - self._ts_start).total_seconds()
        summary_lines = [
            f"Run: {short_hash(self.run_id)} | Play: {short_hash(self.play_hash)} ({self.play_id or 'unknown'})",
            f"Symbol: {self.symbol or 'unknown'} | TF: {self.tf or 'unknown'}",
            f"Result: {trades_count or 0} trades, {net_pnl or 0:+.2f} USDT, {elapsed:.1f}s",
            f"Status: {status}",
        ]
        if self.artifact_dir:
            summary_lines.append(f"Artifacts: {self.artifact_dir}/")

        with open(summary_path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(summary_lines) + "\n")

        # Append to index.jsonl
        write_run_index_entry(
            play_hash=self.play_hash,
            run_id=self.run_id,
            ts_start=self._ts_start,
            ts_end=self._ts_end,
            net_pnl=net_pnl,
            trades_count=trades_count,
            artifact_path=str(self.artifact_dir) if self.artifact_dir else None,
            status=status,
            trades_hash=trades_hash,
            run_hash=run_hash,
        )


def write_run_index_entry(
    play_hash: str,
    run_id: str,
    ts_start: datetime,
    ts_end: datetime,
    net_pnl: float | None = None,
    trades_count: int | None = None,
    artifact_path: str | None = None,
    status: str = "success",
    trades_hash: str | None = None,
    run_hash: str | None = None,
) -> None:
    """
    Append entry to play-indexed index.jsonl.

    Args:
        play_hash: Play configuration hash
        run_id: Run identifier
        ts_start: Run start timestamp
        ts_end: Run end timestamp
        net_pnl: Net PnL in USDT
        trades_count: Number of trades
        artifact_path: Path to artifacts
        status: Run status
        trades_hash: Determinism hash of trades output
        run_hash: Combined run hash (trades + equity + play)
    """
    play_log_dir = GLOBAL_LOGS_DIR / short_hash(play_hash)
    play_log_dir.mkdir(parents=True, exist_ok=True)

    index_path = play_log_dir / "index.jsonl"

    entry: dict[str, Any] = {
        "run_id": run_id,
        "ts_start": ts_start.isoformat(),
        "ts_end": ts_end.isoformat(),
        "elapsed_s": (ts_end - ts_start).total_seconds(),
        "pnl": net_pnl,
        "trades": trades_count,
        "status": status,
    }
    if artifact_path:
        entry["path"] = artifact_path
    if trades_hash:
        entry["trades_hash"] = trades_hash
    if run_hash:
        entry["run_hash"] = run_hash

    import fcntl

    with open(index_path, "a", encoding="utf-8", newline="\n") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.write(json.dumps(entry, separators=(",", ":")) + "\n")
            f.flush()
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


# Singleton for current run logger
_current_run_logger: RunLogger | None = None


def get_run_logger() -> RunLogger | None:
    """Get the current run logger (if active)."""
    return _current_run_logger


def set_run_logger(logger: RunLogger | None) -> None:
    """Set the current run logger."""
    global _current_run_logger
    _current_run_logger = logger
