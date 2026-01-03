"""
Event log writer (append-only JSONL).

Streams events.jsonl during simulation:
- Step events (bar open/close, mark_price)
- Fill events
- Funding events
- Liquidation events
- Entry-disabled events
- HTF/MTF refresh events
- Custom events

Phase 4 additions:
- Snapshot context events (per-TF timestamps + staleness)
- Trade entry/exit events with bar indices and readiness

Each line is a self-contained JSON object.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class EventLogWriter:
    """
    Append-only event log writer for backtest runs.
    
    Writes events.jsonl with one JSON object per line.
    Thread-safe for single-writer usage (typical for backtests).
    """
    
    def __init__(
        self,
        run_dir: Path,
        filename: str = "events.jsonl",
    ):
        """
        Initialize event log writer.
        
        Args:
            run_dir: Directory for run artifacts
            filename: Name of the event log file
        """
        self.run_dir = Path(run_dir)
        self.filename = filename
        self._file = None
        self._event_count = 0
        self._started = False
    
    def start(self) -> None:
        """Start the event log (create/truncate file)."""
        self.run_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.run_dir / self.filename
        self._file = open(log_path, "w")
        self._started = True
        
        # Write header event
        self.log_event("log_started", {
            "timestamp": datetime.now().isoformat(),
        })
    
    def log_event(
        self,
        event_type: str,
        data: dict[str, Any],
        timestamp: datetime | None = None,
    ) -> None:
        """
        Log a single event.
        
        Args:
            event_type: Type of event (e.g., "step", "fill", "funding")
            data: Event data dict
            timestamp: Optional timestamp (defaults to now)
        """
        if not self._started:
            return
        
        event = {
            "event_type": event_type,
            "event_id": self._event_count,
            "timestamp": (timestamp or datetime.now()).isoformat(),
            **data,
        }
        
        self._file.write(json.dumps(event, default=str, sort_keys=True) + "\n")
        self._file.flush()
        self._event_count += 1
    
    def log_step(
        self,
        ts_open: datetime,
        ts_close: datetime,
        mark_price: float,
        mark_price_source: str,
        bar_ohlcv: dict[str, float],
        exchange_state: dict[str, Any],
    ) -> None:
        """
        Log a simulation step event.
        
        Args:
            ts_open: Bar open timestamp
            ts_close: Bar close timestamp (step time)
            mark_price: Mark price at step
            mark_price_source: How mark was computed
            bar_ohlcv: OHLCV dict
            exchange_state: Exchange state snapshot
        """
        self.log_event("step", {
            "ts_open": ts_open.isoformat(),
            "ts_close": ts_close.isoformat(),
            "mark_price": mark_price,
            "mark_price_source": mark_price_source,
            "bar": bar_ohlcv,
            "exchange_state": exchange_state,
        }, timestamp=ts_close)
    
    def log_fill(
        self,
        fill_data: dict[str, Any],
        timestamp: datetime | None = None,
    ) -> None:
        """Log a fill event."""
        self.log_event("fill", fill_data, timestamp)
    
    def log_funding(
        self,
        funding_data: dict[str, Any],
        timestamp: datetime | None = None,
    ) -> None:
        """Log a funding event."""
        self.log_event("funding", funding_data, timestamp)
    
    def log_liquidation(
        self,
        liquidation_data: dict[str, Any],
        timestamp: datetime | None = None,
    ) -> None:
        """Log a liquidation event."""
        self.log_event("liquidation", liquidation_data, timestamp)
    
    def log_entries_disabled(
        self,
        reason: str,
        timestamp: datetime | None = None,
    ) -> None:
        """Log an entries-disabled event."""
        self.log_event("entries_disabled", {"reason": reason}, timestamp)
    
    def log_htf_refresh(
        self,
        tf: str,
        ts_close: datetime,
        features: dict[str, float],
    ) -> None:
        """Log an HTF cache refresh event."""
        self.log_event("htf_refresh", {
            "tf": tf,
            "ts_close": ts_close.isoformat(),
            "features": features,
        }, timestamp=ts_close)
    
    def log_mtf_refresh(
        self,
        tf: str,
        ts_close: datetime,
        features: dict[str, float],
    ) -> None:
        """Log an MTF cache refresh event."""
        self.log_event("mtf_refresh", {
            "tf": tf,
            "ts_close": ts_close.isoformat(),
            "features": features,
        }, timestamp=ts_close)
    
    def log_snapshot_context(
        self,
        bar_index: int,
        exec_ts_close: datetime,
        snapshot_ready: bool,
        exec_ctx: dict[str, Any] | None = None,
        htf_ctx: dict[str, Any] | None = None,
        mtf_ctx: dict[str, Any] | None = None,
    ) -> None:
        """
        Log per-TF snapshot context for debugging (Phase 4).
        
        Includes per-TF ctx_ts_close, features_ts_close, and staleness.
        This is designed for debug mode - buffered and written at end.
        
        Args:
            bar_index: Current simulation bar index
            exec_ts_close: Execution timeframe bar close timestamp
            snapshot_ready: Whether snapshot was ready for strategy evaluation
            exec_ctx: Exec TF context dict {ts_close, features_ts_close, is_stale}
            htf_ctx: HTF context dict {tf, ts_close, features_ts_close, is_stale}
            mtf_ctx: MTF context dict {tf, ts_close, features_ts_close, is_stale}
        """
        self.log_event("snapshot_context", {
            "bar_index": bar_index,
            "exec_ts_close": exec_ts_close.isoformat(),
            "snapshot_ready": snapshot_ready,
            "exec_ctx": exec_ctx,
            "htf_ctx": htf_ctx,
            "mtf_ctx": mtf_ctx,
        }, timestamp=exec_ts_close)
    
    def log_trade_entry(
        self,
        trade_id: str,
        bar_index: int,
        entry_time: datetime,
        entry_price: float,
        side: str,
        size_usdt: float,
        snapshot_ready: bool,
    ) -> None:
        """Log a trade entry event (Phase 4)."""
        self.log_event("trade_entry", {
            "trade_id": trade_id,
            "bar_index": bar_index,
            "entry_price": entry_price,
            "side": side,
            "size_usdt": size_usdt,
            "snapshot_ready": snapshot_ready,
        }, timestamp=entry_time)
    
    def log_trade_exit(
        self,
        trade_id: str,
        bar_index: int,
        exit_time: datetime,
        exit_price: float,
        exit_reason: str,
        exit_price_source: str,
        net_pnl: float,
        snapshot_ready: bool,
    ) -> None:
        """Log a trade exit event (Phase 4)."""
        self.log_event("trade_exit", {
            "trade_id": trade_id,
            "bar_index": bar_index,
            "exit_price": exit_price,
            "exit_reason": exit_reason,
            "exit_price_source": exit_price_source,
            "net_pnl": net_pnl,
            "snapshot_ready": snapshot_ready,
        }, timestamp=exit_time)
    
    def finish(self) -> None:
        """Finish and close the event log."""
        if self._started and self._file:
            self.log_event("log_finished", {
                "total_events": self._event_count,
            })
            self._file.close()
            self._file = None
            self._started = False
    
    def get_path(self) -> Path:
        """Get path to event log file."""
        return self.run_dir / self.filename
    
    @property
    def event_count(self) -> int:
        """Get number of events logged."""
        return self._event_count
    
    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.finish()
        return False

