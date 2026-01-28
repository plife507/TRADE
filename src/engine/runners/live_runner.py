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
from src.backtest.runtime.timeframe import tf_minutes

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
    - Subscribe to WebSocket candle stream via RealtimeState
    - Process candles through engine on close
    - Execute signals through exchange adapter
    - Handle reconnection on WebSocket disconnect
    - Report status and statistics

    Integrates with RealtimeBootstrap/RealtimeState for candle events.
    """

    def __init__(
        self,
        engine: PlayEngine,
        on_signal: Callable[["Signal"], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        base_reconnect_delay: float = 1.0,
        max_reconnect_delay: float = 60.0,
        max_reconnect_attempts: int = 10,
        reconcile_interval: float = 300.0,
    ):
        """
        Initialize live runner.

        Args:
            engine: PlayEngine instance (must be in demo or live mode)
            on_signal: Optional callback when signal is generated
            on_error: Optional callback when error occurs
            base_reconnect_delay: Initial delay before reconnecting (exponential backoff)
            max_reconnect_delay: Maximum delay between reconnection attempts
            max_reconnect_attempts: Maximum reconnection attempts before giving up
            reconcile_interval: Seconds between position reconciliation checks (default 5 min)
        """
        self._engine = engine
        self._on_signal = on_signal
        self._on_error = on_error
        self._base_reconnect_delay = base_reconnect_delay
        self._max_reconnect_delay = max_reconnect_delay
        self._max_reconnect_attempts = max_reconnect_attempts
        self._reconcile_interval = reconcile_interval

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
        self._last_reconcile_ts: datetime | None = None

        # RealtimeState integration
        self._realtime_state = None
        self._bootstrap = None
        self._candle_queue: asyncio.Queue = asyncio.Queue()
        self._subscription_task: asyncio.Task | None = None
        self._kline_callback_registered = False

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

            # G0.4: Sync positions before processing signals
            await self._sync_positions_on_startup()

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
        Connect to data provider (WebSocket) and RealtimeState.

        Sets up candle close callbacks for processing through the engine.
        """
        from ..adapters.live import LiveDataProvider
        from ...data.realtime_state import get_realtime_state, EventType
        from ...data.realtime_bootstrap import get_realtime_bootstrap

        # Connect to RealtimeState for events
        self._realtime_state = get_realtime_state()
        self._bootstrap = get_realtime_bootstrap()

        # Start RealtimeBootstrap if not already running
        if not self._bootstrap.is_running:
            self._bootstrap.start(
                symbols=[self._engine.symbol],
                include_private=True,  # Need private for position tracking
            )

        # Ensure our symbol is subscribed
        self._bootstrap.ensure_symbol_subscribed(self._engine.symbol)

        # Register callback for candle closes
        if not self._kline_callback_registered:
            self._realtime_state.on_kline_update(self._on_kline_update)
            self._kline_callback_registered = True
            logger.info(f"Registered kline callback for {self._engine.symbol}")

        # Connect LiveDataProvider
        data_provider = self._engine._data_provider
        if isinstance(data_provider, LiveDataProvider):
            await data_provider.connect()
        else:
            # For testing, allow mock data provider
            logger.warning(
                f"Data provider is {type(data_provider).__name__}, "
                "not LiveDataProvider. WebSocket connection skipped."
            )

        # Connect LiveExchange
        from ..adapters.live import LiveExchange
        exchange = self._engine._exchange
        if isinstance(exchange, LiveExchange):
            await exchange.connect()

    async def _sync_positions_on_startup(self) -> None:
        """
        G0.4: Synchronize existing positions from exchange before processing signals.

        This ensures we don't open duplicate positions or miss existing ones
        when restarting the runner.
        """
        try:
            from ..adapters.live import LiveExchange
            exchange = self._engine._exchange
            if not isinstance(exchange, LiveExchange):
                logger.debug("Skipping position sync: not LiveExchange")
                return

            if hasattr(exchange, '_position_manager') and exchange._position_manager:
                pm = exchange._position_manager
                # Force REST sync to get current state
                if hasattr(pm, 'reconcile_with_rest'):
                    await asyncio.to_thread(pm.reconcile_with_rest)

                positions = pm.get_all_positions()
                if positions:
                    logger.info(f"Position sync: {len(positions)} existing position(s)")
                    for pos in positions:
                        if pos.symbol == self._engine.symbol:
                            logger.info(
                                f"  {pos.symbol}: {pos.side} {pos.size} @ {pos.entry_price}"
                            )
                else:
                    logger.info("Position sync: no existing positions")
        except Exception as e:
            logger.warning(f"Position sync warning (non-fatal): {e}")

        self._last_reconcile_ts = datetime.now()

    async def _maybe_reconcile_positions(self) -> None:
        """
        G5.4: Periodic position reconciliation.

        Syncs positions with exchange at regular intervals to catch any
        missed fills or out-of-sync state from WebSocket gaps.
        """
        now = datetime.now()

        # Skip if recently reconciled
        if self._last_reconcile_ts:
            elapsed = (now - self._last_reconcile_ts).total_seconds()
            if elapsed < self._reconcile_interval:
                return

        try:
            from ..adapters.live import LiveExchange
            exchange = self._engine._exchange
            if not isinstance(exchange, LiveExchange):
                return

            if hasattr(exchange, '_position_manager') and exchange._position_manager:
                pm = exchange._position_manager
                if hasattr(pm, 'reconcile_with_rest'):
                    logger.debug("Periodic position reconciliation...")
                    await asyncio.to_thread(pm.reconcile_with_rest)
                    self._last_reconcile_ts = now

        except Exception as e:
            logger.warning(f"Periodic reconciliation failed (non-fatal): {e}")

    def _on_kline_update(self, kline_data) -> None:
        """
        Handle kline update from RealtimeState.

        Only processes closed candles matching our symbol and timeframe.
        """
        # Filter for our symbol and timeframe
        if kline_data.symbol != self._engine.symbol:
            return

        # Map timeframe (Bybit uses minutes for most TFs)
        expected_tf = self._engine.timeframe.lower()
        kline_tf = kline_data.interval.lower() if kline_data.interval else ""

        # Convert to comparable format
        tf_map = {
            "1": "1m", "3": "3m", "5": "5m", "15": "15m", "30": "30m",
            "60": "1h", "120": "2h", "240": "4h", "360": "6h",
            "720": "12h", "d": "d", "w": "w", "m": "m",
        }
        kline_tf_norm = tf_map.get(kline_tf, kline_tf)

        if kline_tf_norm != expected_tf:
            return

        # Only process closed candles
        if not kline_data.is_closed:
            return

        # Convert to Candle and enqueue
        from ..interfaces import Candle
        from datetime import datetime

        try:
            candle = Candle(
                ts_open=datetime.fromtimestamp(kline_data.start_time / 1000.0),
                ts_close=datetime.fromtimestamp(kline_data.end_time / 1000.0) if kline_data.end_time else datetime.now(),
                open=kline_data.open,
                high=kline_data.high,
                low=kline_data.low,
                close=kline_data.close,
                volume=kline_data.volume,
            )

            # Add to queue (non-blocking)
            try:
                self._candle_queue.put_nowait(candle)
            except asyncio.QueueFull:
                logger.warning("Candle queue full, dropping oldest")

        except Exception as e:
            logger.warning(f"Failed to convert kline to candle: {e}")

    async def _disconnect(self) -> None:
        """Disconnect from data provider."""
        from ..adapters.live import LiveDataProvider, LiveExchange

        # Disconnect LiveDataProvider
        data_provider = self._engine._data_provider
        if isinstance(data_provider, LiveDataProvider):
            await data_provider.disconnect()

        # Disconnect LiveExchange
        exchange = self._engine._exchange
        if isinstance(exchange, LiveExchange):
            await exchange.disconnect()

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

                # G5.4: Periodic position reconciliation
                await self._maybe_reconcile_positions()

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

        Returns candle data when available, None on timeout.
        Includes health check: alerts if no candle received in 2x expected timeframe.
        """
        # Calculate expected candle interval based on timeframe
        tf_mins = tf_minutes(self._engine.timeframe)
        health_timeout = tf_mins * 60 * 2.5  # 2.5x timeframe in seconds
        queue_timeout = min(60.0, health_timeout)  # Check at least every minute

        try:
            # Wait for candle from queue with timeout
            candle = await asyncio.wait_for(
                self._candle_queue.get(),
                timeout=queue_timeout,
            )
            return candle

        except asyncio.TimeoutError:
            # No candle received in timeout period
            # Check if we've exceeded health threshold
            if self._stats.last_candle_ts:
                since_last = (datetime.now() - self._stats.last_candle_ts).total_seconds()
                expected_interval = tf_minutes * 60

                if since_last > expected_interval * 2:
                    logger.warning(
                        f"HEALTH: No candle received for {since_last:.0f}s "
                        f"(expected every {expected_interval}s). "
                        f"Check WebSocket connection."
                    )
                    self._stats.errors.append(
                        f"Health alert: no candle for {since_last:.0f}s"
                    )

            return None

        except asyncio.CancelledError:
            # Runner is stopping
            raise

        except Exception as e:
            logger.warning(f"Error waiting for candle: {e}")
            return None

    async def _process_candle(self, candle) -> None:
        """
        Process a closed candle through the engine.

        Args:
            candle: Candle data from WebSocket
        """
        from ..adapters.live import LiveDataProvider

        self._stats.bars_processed += 1
        self._stats.last_candle_ts = candle.ts_close

        # Update data provider with new candle
        data_provider = self._engine._data_provider
        if isinstance(data_provider, LiveDataProvider):
            data_provider.on_candle_close(candle)

        # Check if data provider is ready (warmup complete)
        if not data_provider.is_ready():
            logger.debug(
                f"Data provider not ready (warmup), skipping signal evaluation. "
                f"Bars: {data_provider.num_bars}"
            )
            return

        # Process through engine (use -1 for latest in live mode)
        try:
            signal = self._engine.process_bar(-1)
        except Exception as e:
            logger.error(f"Error processing bar: {e}")
            self._stats.errors.append(f"Process error: {e}")
            return

        if signal is not None:
            self._stats.signals_generated += 1
            self._stats.last_signal_ts = datetime.now()

            logger.info(
                f"Signal generated: {signal.direction} {self._engine.symbol} "
                f"at {candle.ts_close}"
            )

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
        """Attempt to reconnect to WebSocket with exponential backoff."""
        self._state = RunnerState.RECONNECTING
        self._reconnect_attempts += 1
        self._stats.reconnect_count += 1

        # Exponential backoff: base * 2^(attempts-1), capped at max
        delay = min(
            self._base_reconnect_delay * (2 ** (self._reconnect_attempts - 1)),
            self._max_reconnect_delay,
        )

        logger.warning(
            f"Reconnecting (attempt {self._reconnect_attempts}/"
            f"{self._max_reconnect_attempts}, delay={delay:.1f}s)..."
        )

        await asyncio.sleep(delay)

        try:
            await self._disconnect()
            await self._connect()
            self._state = RunnerState.RUNNING
            self._reconnect_attempts = 0  # Reset on success
            logger.info("Reconnection successful")
        except Exception as e:
            logger.error(f"Reconnection failed: {e}")
            self._stats.errors.append(f"Reconnect error: {e}")
