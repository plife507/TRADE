"""
Shadow runner for PlayEngine.

Runs the PlayEngine in shadow mode:
- Receives real-time market data
- Generates signals using the same logic as live
- Logs signals without executing orders
- Useful for paper testing before going live

Usage:
    from src.engine import PlayEngineFactory
    from src.engine.runners import ShadowRunner

    engine = PlayEngineFactory.create(play, mode="shadow")
    runner = ShadowRunner(engine)
    await runner.start()
    # ... runs until stopped
    await runner.stop()
"""


import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ..play_engine import PlayEngine

from ...utils.logger import get_logger

if TYPE_CHECKING:
    from ...core.risk_manager import Signal


logger = get_logger()


@dataclass
class ShadowSignal:
    """Record of a signal generated in shadow mode."""

    timestamp: datetime
    direction: str  # "LONG", "SHORT", "FLAT"
    symbol: str
    size_usdt: float
    stop_loss: float | None
    take_profit: float | None
    bar_index: int
    candle_close: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "direction": self.direction,
            "symbol": self.symbol,
            "size_usdt": self.size_usdt,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "bar_index": self.bar_index,
            "candle_close": self.candle_close,
            "metadata": self.metadata,
        }


@dataclass
class ShadowStats:
    """Statistics from shadow mode run."""

    started_at: datetime | None = None
    stopped_at: datetime | None = None
    bars_processed: int = 0
    signals_generated: int = 0
    long_signals: int = 0
    short_signals: int = 0
    exit_signals: int = 0
    signals: list[ShadowSignal] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        if self.started_at is None or self.stopped_at is None:
            return 0.0
        return (self.stopped_at - self.started_at).total_seconds()

    def to_dict(self) -> dict:
        return {
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "stopped_at": self.stopped_at.isoformat() if self.stopped_at else None,
            "duration_seconds": self.duration_seconds,
            "bars_processed": self.bars_processed,
            "signals_generated": self.signals_generated,
            "long_signals": self.long_signals,
            "short_signals": self.short_signals,
            "exit_signals": self.exit_signals,
            "signals": [s.to_dict() for s in self.signals],
        }


class ShadowRunner:
    """
    Runner that executes PlayEngine in shadow mode.

    Shadow mode:
    - Processes real-time candle data
    - Generates signals using PlayEngine
    - Records signals without executing
    - Provides statistics and signal history

    Can be used with:
    - Historical data (replay mode)
    - Real-time WebSocket data (live shadow)
    """

    def __init__(
        self,
        engine: PlayEngine,
        log_signals: bool = True,
        max_signal_history: int = 1000,
    ):
        """
        Initialize shadow runner.

        Args:
            engine: PlayEngine instance (should be in shadow mode)
            log_signals: If True, log each signal to console
            max_signal_history: Maximum signals to keep in memory
        """
        self._engine = engine
        self._log_signals = log_signals
        self._max_signal_history = max_signal_history

        # Validate mode
        if not engine.is_shadow:
            logger.warning(
                f"ShadowRunner created with engine in {engine.mode} mode. "
                "For proper shadow behavior, use mode='shadow'"
            )

        # State
        self._running = False
        self._stats = ShadowStats()
        self._stop_event = asyncio.Event()

    @property
    def stats(self) -> ShadowStats:
        """Get current shadow statistics."""
        return self._stats

    @property
    def is_running(self) -> bool:
        """Check if runner is active."""
        return self._running

    async def start(self) -> None:
        """
        Start shadow mode processing.

        This method begins the WebSocket subscription and
        processes candles as they arrive.
        """
        if self._running:
            logger.warning("ShadowRunner already running")
            return

        self._running = True
        self._stats = ShadowStats(started_at=datetime.now())
        self._stop_event.clear()

        logger.info(
            f"ShadowRunner started: {self._engine.symbol} {self._engine.timeframe}"
        )

        # In live shadow mode, this would subscribe to WebSocket
        # For now, we just mark as running

    async def stop(self) -> None:
        """
        Stop shadow mode processing.

        Gracefully stops the WebSocket subscription and
        returns final statistics.
        """
        if not self._running:
            return

        self._stop_event.set()
        self._running = False
        self._stats.stopped_at = datetime.now()

        logger.info(
            f"ShadowRunner stopped: {self._stats.signals_generated} signals "
            f"in {self._stats.duration_seconds:.1f}s"
        )

    async def run_replay(
        self,
        start_idx: int = 0,
        end_idx: int | None = None,
    ) -> ShadowStats:
        """
        Run shadow mode over historical data (replay).

        This is useful for testing signal generation on past data
        without affecting live systems.

        Args:
            start_idx: Starting bar index
            end_idx: Ending bar index (None = all data)

        Returns:
            ShadowStats with signal history
        """
        await self.start()

        try:
            # Get data bounds
            data_provider = self._engine._data_provider
            if end_idx is None:
                end_idx = data_provider.num_bars

            # Process each bar
            for bar_idx in range(start_idx, end_idx):
                if self._stop_event.is_set():
                    break

                # Process bar
                signal = self._engine.process_bar(bar_idx)
                self._stats.bars_processed += 1

                if signal is not None:
                    self._record_signal(signal, bar_idx)

        finally:
            await self.stop()

        return self._stats

    def _record_signal(self, signal: "Signal", bar_idx: int) -> None:
        """
        Record a generated signal.

        Args:
            signal: Signal that was generated
            bar_idx: Bar index where signal occurred
        """
        # Get candle data for context
        try:
            candle = self._engine._data_provider.get_candle(bar_idx)
            candle_close = candle.close
            timestamp = candle.ts_close
        except Exception as e:
            logger.warning(f"Failed to get candle at bar_idx={bar_idx}, using fallback: {e}")
            candle_close = 0.0
            timestamp = datetime.now()

        # Create shadow signal record
        shadow_signal = ShadowSignal(
            timestamp=timestamp,
            direction=signal.direction,
            symbol=signal.symbol,
            size_usdt=signal.size_usdt,
            stop_loss=signal.metadata.get("stop_loss") if signal.metadata else None,
            take_profit=signal.metadata.get("take_profit") if signal.metadata else None,
            bar_index=bar_idx,
            candle_close=candle_close,
            metadata=signal.metadata or {},
        )

        # Update stats
        self._stats.signals_generated += 1
        if signal.direction == "LONG":
            self._stats.long_signals += 1
        elif signal.direction == "SHORT":
            self._stats.short_signals += 1
        elif signal.direction == "FLAT":
            self._stats.exit_signals += 1

        # Store signal (with max history limit)
        self._stats.signals.append(shadow_signal)
        if len(self._stats.signals) > self._max_signal_history:
            self._stats.signals = self._stats.signals[-self._max_signal_history:]

        # Log if enabled
        if self._log_signals:
            self._log_signal(shadow_signal)

    def _log_signal(self, signal: ShadowSignal) -> None:
        """Log a shadow signal."""
        sl_str = f" SL={signal.stop_loss:.2f}" if signal.stop_loss else ""
        tp_str = f" TP={signal.take_profit:.2f}" if signal.take_profit else ""

        logger.info(
            f"[SHADOW] {signal.direction} {signal.symbol} "
            f"@ {signal.candle_close:.2f}{sl_str}{tp_str}"
        )
