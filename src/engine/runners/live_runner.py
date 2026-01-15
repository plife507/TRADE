"""
Live runner for PlayEngine.

Drives the PlayEngine in live/demo mode using WebSocket data:
1. Subscribe to real-time candle stream
2. Process each closed candle through engine
3. Execute signals through exchange adapter
4. Handle reconnection and error recovery

Usage:
    from src.engine import PlayEngineFactory
    from src.engine.runners import LiveRunner

    engine = PlayEngineFactory.create(play, mode="demo")
    runner = LiveRunner(engine)
    await runner.start()
    # ... runs until stopped or error
    await runner.stop()
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable

from ..play_engine import PlayEngine

from ...utils.logger import get_logger

if TYPE_CHECKING:
    from ...core.risk_manager import Signal


logger = get_logger()


class RunnerState(str, Enum):
    """State of the live runner."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    RECONNECTING = "reconnecting"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class LiveRunnerStats:
    """Statistics from live runner."""

    started_at: datetime | None = None
    stopped_at: datetime | None = None
    bars_processed: int = 0
    signals_generated: int = 0
    orders_submitted: int = 0
    orders_filled: int = 0
    orders_failed: int = 0
    reconnect_count: int = 0
    last_candle_ts: datetime | None = None
    last_signal_ts: datetime | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.stopped_at or datetime.now()
        return (end - self.started_at).total_seconds()

    def to_dict(self) -> dict:
        return {
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "stopped_at": self.stopped_at.isoformat() if self.stopped_at else None,
            "duration_seconds": self.duration_seconds,
            "bars_processed": self.bars_processed,
            "signals_generated": self.signals_generated,
            "orders_submitted": self.orders_submitted,
            "orders_filled": self.orders_filled,
            "orders_failed": self.orders_failed,
            "reconnect_count": self.reconnect_count,
            "last_candle_ts": self.last_candle_ts.isoformat() if self.last_candle_ts else None,
            "last_signal_ts": self.last_signal_ts.isoformat() if self.last_signal_ts else None,
            "errors": self.errors[-10:],  # Last 10 errors
        }


class LiveRunner:
    """
    Runner that executes PlayEngine in live/demo mode.

    Responsibilities:
    - Subscribe to WebSocket candle stream
    - Process candles through engine on close
    - Execute signals through exchange adapter
    - Handle reconnection on WebSocket disconnect
    - Report status and statistics

    The runner maintains connection to the exchange and
    processes events in an async event loop.
    """

    def __init__(
        self,
        engine: PlayEngine,
        on_signal: Callable[["Signal"], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        reconnect_delay: float = 5.0,
        max_reconnect_attempts: int = 10,
    ):
        """
        Initialize live runner.

        Args:
            engine: PlayEngine instance (must be in demo or live mode)
            on_signal: Optional callback when signal is generated
            on_error: Optional callback when error occurs
            reconnect_delay: Seconds to wait before reconnecting
            max_reconnect_attempts: Maximum reconnection attempts
        """
        self._engine = engine
        self._on_signal = on_signal
        self._on_error = on_error
        self._reconnect_delay = reconnect_delay
        self._max_reconnect_attempts = max_reconnect_attempts

        # Validate mode
        if engine.is_backtest:
            raise ValueError(
                "LiveRunner cannot be used with backtest mode. "
                "Use BacktestRunner instead."
            )

        # State
        self._state = RunnerState.STOPPED
        self._stats = LiveRunnerStats()
        self._stop_event = asyncio.Event()
        self._reconnect_attempts = 0

        # WebSocket client (will be initialized on start)
        self._ws_client = None
        self._subscription_task: asyncio.Task | None = None

    @property
    def state(self) -> RunnerState:
        """Current runner state."""
        return self._state

    @property
    def stats(self) -> LiveRunnerStats:
        """Current statistics."""
        return self._stats

    @property
    def is_running(self) -> bool:
        """Check if runner is active."""
        return self._state == RunnerState.RUNNING

    async def start(self) -> None:
        """
        Start live trading.

        Connects to WebSocket and begins processing candles.
        """
        if self._state != RunnerState.STOPPED:
            logger.warning(f"Cannot start: runner is {self._state.value}")
            return

        self._state = RunnerState.STARTING
        self._stats = LiveRunnerStats(started_at=datetime.now())
        self._stop_event.clear()
        self._reconnect_attempts = 0

        logger.info(
            f"LiveRunner starting: {self._engine.symbol} {self._engine.timeframe} "
            f"mode={self._engine.mode}"
        )

        try:
            # Connect to data provider
            await self._connect()

            # Start processing loop
            self._subscription_task = asyncio.create_task(self._process_loop())
            self._state = RunnerState.RUNNING

            logger.info("LiveRunner running")

        except Exception as e:
            self._state = RunnerState.ERROR
            self._stats.errors.append(str(e))
            logger.error(f"Failed to start LiveRunner: {e}")
            raise

    async def stop(self) -> None:
        """
        Stop live trading gracefully.

        Disconnects from WebSocket and cleans up.
        """
        if self._state == RunnerState.STOPPED:
            return

        self._state = RunnerState.STOPPING
        self._stop_event.set()

        # Cancel subscription task
        if self._subscription_task is not None:
            self._subscription_task.cancel()
            try:
                await self._subscription_task
            except asyncio.CancelledError:
                pass

        # Disconnect from data provider
        await self._disconnect()

        self._state = RunnerState.STOPPED
        self._stats.stopped_at = datetime.now()

        logger.info(
            f"LiveRunner stopped: {self._stats.bars_processed} bars, "
            f"{self._stats.signals_generated} signals, "
            f"{self._stats.duration_seconds:.1f}s"
        )

    async def wait_until_stopped(self) -> None:
        """Wait until runner stops."""
        await self._stop_event.wait()

    async def _connect(self) -> None:
        """
        Connect to data provider (WebSocket).

        This will be implemented when LiveDataProvider is complete.
        """
        # Import live data provider
        from ..adapters.live import LiveDataProvider

        data_provider = self._engine._data_provider
        if isinstance(data_provider, LiveDataProvider):
            await data_provider.connect()
        else:
            # For testing, allow mock data provider
            logger.warning(
                f"Data provider is {type(data_provider).__name__}, "
                "not LiveDataProvider. WebSocket connection skipped."
            )

    async def _disconnect(self) -> None:
        """Disconnect from data provider."""
        from ..adapters.live import LiveDataProvider

        data_provider = self._engine._data_provider
        if isinstance(data_provider, LiveDataProvider):
            await data_provider.disconnect()

    async def _process_loop(self) -> None:
        """
        Main processing loop.

        Waits for candle closes and processes through engine.
        """
        while not self._stop_event.is_set():
            try:
                # Wait for next candle close
                candle = await self._wait_for_candle()
                if candle is None:
                    continue

                # Process candle
                await self._process_candle(candle)

            except asyncio.CancelledError:
                break

            except Exception as e:
                self._stats.errors.append(str(e))
                logger.error(f"Error in process loop: {e}")

                if self._on_error:
                    self._on_error(e)

                # Attempt reconnection
                if self._reconnect_attempts < self._max_reconnect_attempts:
                    await self._reconnect()
                else:
                    logger.error("Max reconnection attempts reached, stopping")
                    break

    async def _wait_for_candle(self):
        """
        Wait for next candle close.

        Returns candle data when available, None on timeout/error.
        """
        # This will integrate with LiveDataProvider's candle stream
        # For now, return None (placeholder)
        await asyncio.sleep(1.0)  # Placeholder wait
        return None

    async def _process_candle(self, candle) -> None:
        """
        Process a closed candle through the engine.

        Args:
            candle: Candle data from WebSocket
        """
        self._stats.bars_processed += 1
        self._stats.last_candle_ts = datetime.now()

        # Process through engine (use -1 for latest in live mode)
        signal = self._engine.process_bar(-1)

        if signal is not None:
            self._stats.signals_generated += 1
            self._stats.last_signal_ts = datetime.now()

            # Notify callback
            if self._on_signal:
                self._on_signal(signal)

            # Execute signal
            await self._execute_signal(signal)

    async def _execute_signal(self, signal: "Signal") -> None:
        """
        Execute a signal through the exchange.

        Args:
            signal: Signal to execute
        """
        try:
            self._stats.orders_submitted += 1
            result = self._engine.execute_signal(signal)

            if result.success:
                self._stats.orders_filled += 1
                logger.info(
                    f"Order filled: {signal.direction} {signal.symbol} "
                    f"id={result.order_id}"
                )
            else:
                self._stats.orders_failed += 1
                logger.warning(f"Order failed: {result.error}")

        except Exception as e:
            self._stats.orders_failed += 1
            self._stats.errors.append(f"Execute error: {e}")
            logger.error(f"Failed to execute signal: {e}")

    async def _reconnect(self) -> None:
        """Attempt to reconnect to WebSocket."""
        self._state = RunnerState.RECONNECTING
        self._reconnect_attempts += 1
        self._stats.reconnect_count += 1

        logger.warning(
            f"Reconnecting (attempt {self._reconnect_attempts}/"
            f"{self._max_reconnect_attempts})..."
        )

        await asyncio.sleep(self._reconnect_delay)

        try:
            await self._disconnect()
            await self._connect()
            self._state = RunnerState.RUNNING
            logger.info("Reconnection successful")
        except Exception as e:
            logger.error(f"Reconnection failed: {e}")
            self._stats.errors.append(f"Reconnect error: {e}")
