"""
Trade journal for persistent trade logging.

Writes trade events as JSONL (one JSON object per line) for post-analysis.
Each line is a complete JSON object with event type, timestamp, and details.

Journal files are stored at {project_root}/data/journal/{instance_id}.jsonl
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ..utils.logger import get_logger

logger = get_logger()

# Project root: src/engine/journal.py -> two levels up
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class TradeJournal:
    """
    Persistent trade logger writing JSONL files.

    Each trade event is one JSON line with fields varying by event type:
    - signal: timestamp, symbol, direction, size_usdt, strategy, metadata
    - fill: timestamp, symbol, direction, size_usdt, fill_price, order_id, sl, tp
    - error: timestamp, symbol, direction, error
    """

    def __init__(self, instance_id: str):
        self._instance_id = instance_id
        self._journal_dir = _PROJECT_ROOT / "data" / "journal"
        self._journal_dir.mkdir(parents=True, exist_ok=True)
        self._path = self._journal_dir / f"{instance_id}.jsonl"
        logger.info(f"TradeJournal initialized: {self._path}")

    def record_signal(
        self,
        symbol: str,
        direction: str,
        size_usdt: float,
        strategy: str = "",
        metadata: dict | None = None,
    ) -> None:
        """Record a signal event."""
        self._write({
            "event": "signal",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "instance_id": self._instance_id,
            "symbol": symbol,
            "direction": direction,
            "size_usdt": size_usdt,
            "strategy": strategy,
            "metadata": metadata or {},
        })

    def record_fill(
        self,
        symbol: str,
        direction: str,
        size_usdt: float,
        fill_price: float,
        order_id: str = "",
        sl: float | None = None,
        tp: float | None = None,
    ) -> None:
        """Record an order fill event."""
        self._write({
            "event": "fill",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "instance_id": self._instance_id,
            "symbol": symbol,
            "direction": direction,
            "size_usdt": size_usdt,
            "fill_price": fill_price,
            "order_id": order_id,
            "sl": sl,
            "tp": tp,
        })

    def record_error(
        self,
        symbol: str,
        direction: str,
        error: str,
    ) -> None:
        """Record an execution error."""
        self._write({
            "event": "error",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "instance_id": self._instance_id,
            "symbol": symbol,
            "direction": direction,
            "error": error,
        })

    def _write(self, data: dict) -> None:
        """Append a JSON line to the journal file."""
        try:
            with open(self._path, "a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(data, default=str) + "\n")
        except Exception as e:
            logger.warning(f"Failed to write journal entry: {e}")

    @property
    def path(self) -> Path:
        """Path to the journal file."""
        return self._path


class BacktestJournal:
    """Lightweight journal for backtest runs.

    Writes signal/fill/error events to ``events.jsonl`` inside the artifact
    folder so that backtest runs produce the same event log as live/demo runs.
    """

    def __init__(self, artifact_dir: Path, play_id: str, symbol: str):
        self._path = artifact_dir / "events.jsonl"
        self._play_id = play_id
        self._symbol = symbol
        self._count = 0

    def record(self, event: str, bar_idx: int, **fields) -> None:
        """Record a generic backtest event."""
        entry = {
            "event": event,
            "play_id": self._play_id,
            "symbol": self._symbol,
            "bar_idx": bar_idx,
            **fields,
        }
        try:
            with open(self._path, "a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(entry, default=str) + "\n")
            self._count += 1
        except Exception:
            pass  # Never crash on journal write

    def record_signal(self, bar_idx: int, decision: str, reason: str) -> None:
        """Record a signal evaluation that produced an action."""
        self.record("signal", bar_idx, decision=decision, reason=reason)

    def record_fill(
        self, bar_idx: int, side: str, price: float, size_usdt: float,
        sl: float | None = None, tp: float | None = None,
    ) -> None:
        """Record a simulated fill."""
        self.record("fill", bar_idx, side=side, price=price, size_usdt=size_usdt, sl=sl, tp=tp)

    def record_close(
        self, bar_idx: int, side: str, entry_price: float, exit_price: float, pnl: float,
        reason: str = "",
    ) -> None:
        """Record a position close."""
        self.record(
            "close", bar_idx, side=side,
            entry_price=entry_price, exit_price=exit_price, pnl=pnl, reason=reason,
        )

    @property
    def path(self) -> Path:
        return self._path

    @property
    def event_count(self) -> int:
        return self._count
