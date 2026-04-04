"""
Shadow journal — JSONL append-only logging for trades and snapshots.

One journal file per engine instance:
  data/shadow/{instance_id}/events.jsonl

Designed for minimal I/O: buffered writes, flush on trade events
and periodic snapshots. No per-bar writes.
"""

import json

from ..config.constants import PROJECT_ROOT
from ..utils.logger import get_module_logger

from .types import ShadowSnapshot, ShadowTrade

logger = get_module_logger(__name__)

SHADOW_DATA_DIR = PROJECT_ROOT / "data" / "shadow"


class ShadowJournal:
    """Append-only JSONL journal for a single shadow engine instance.

    Writes are buffered by the OS file buffer and flushed on each
    trade/snapshot event. No per-bar I/O.
    """

    def __init__(self, instance_id: str) -> None:
        self._instance_id = instance_id
        self._dir = SHADOW_DATA_DIR / instance_id
        self._dir.mkdir(parents=True, exist_ok=True)
        self._events_path = self._dir / "events.jsonl"
        self._fd = open(self._events_path, "a", encoding="utf-8", newline="\n")

    def record_trade(self, trade: ShadowTrade) -> None:
        """Record a completed trade."""
        self._write({"event": "trade", **trade.to_dict()})

    def record_snapshot(self, snapshot: ShadowSnapshot) -> None:
        """Record a periodic equity snapshot."""
        self._write({"event": "snapshot", **snapshot.to_dict()})

    def record_signal(self, direction: str, symbol: str, price: float, timestamp_iso: str) -> None:
        """Record a signal generation (lightweight)."""
        self._write({
            "event": "signal",
            "direction": direction,
            "symbol": symbol,
            "price": price,
            "timestamp": timestamp_iso,
        })

    def record_error(self, error: str, timestamp_iso: str) -> None:
        """Record an error event."""
        self._write({
            "event": "error",
            "error": error,
            "timestamp": timestamp_iso,
        })

    def _write(self, data: dict) -> None:
        """Write a single JSON line and flush."""
        try:
            self._fd.write(json.dumps(data, separators=(",", ":")) + "\n")
            self._fd.flush()
        except OSError as e:
            logger.warning("Journal write failed for %s: %s", self._instance_id, e)

    def close(self) -> None:
        """Close the journal file."""
        try:
            self._fd.close()
        except OSError:
            pass
