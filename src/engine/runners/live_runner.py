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


import asyncio
import os
import queue
import threading
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from ..play_engine import PlayEngine
from src.backtest.runtime.timeframe import tf_minutes
from ...core.safety import check_panic_and_halt, get_panic_state

from ...utils.logger import get_logger
from ...utils.debug import is_debug_enabled

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


# G5.7: Valid state transitions
VALID_TRANSITIONS: dict[RunnerState, set[RunnerState]] = {
    RunnerState.STOPPED: {RunnerState.STARTING},
    RunnerState.STARTING: {RunnerState.RUNNING, RunnerState.ERROR},
    RunnerState.RUNNING: {RunnerState.STOPPING, RunnerState.RECONNECTING, RunnerState.ERROR},
    RunnerState.RECONNECTING: {RunnerState.RUNNING, RunnerState.RECONNECTING, RunnerState.STOPPING, RunnerState.ERROR},
    RunnerState.STOPPING: {RunnerState.STOPPED, RunnerState.ERROR},
    RunnerState.ERROR: {RunnerState.STOPPED},  # Can only reset from error
}


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

        # State (G5.7: thread-safe state machine)
        self._state = RunnerState.STOPPED
        self._state_lock = threading.Lock()
        self._stats = LiveRunnerStats()
        self._stop_event = asyncio.Event()
        self._reconnect_attempts = 0
        self._last_reconcile_ts: datetime | None = None

        # Max drawdown tracking (B5)
        self._peak_equity: float = 0.0
        self._equity_initialized: bool = False

        # H4: Track whether exchange has an existing position for our symbol
        self._has_existing_position: bool = False

        # G17.1: Trade journal (initialized in start())
        self._journal = None

        # G17.4: Notification adapter (initialized in start())
        self._notifier = None

        # G17.3: Pause file-based IPC
        self._pause_dir = Path(os.path.expanduser("~/.trade/instances"))
        self._instance_id: str = ""  # Set by EngineManager after construction

        # Multi-timeframe routing
        self._play_timeframes: set[str] = set()
        self._exec_tf: str = ""

        # RealtimeState integration
        self._realtime_state = None
        self._bootstrap = None
        # stdlib Queue (not asyncio.Queue) for thread-safe put from sync WebSocket callbacks
        # Unbounded: candle close events are precious and can't be recovered if dropped
        self._candle_queue: queue.Queue = queue.Queue(maxsize=0)
        self._subscription_task: asyncio.Task | None = None
        self._kline_callback_registered = False

        # H3: Candle deduplication -- keyed by TF, each value is a set of ts_open_epoch
        self._seen_candles: dict[str, set[float]] = {}
        self._SEEN_CANDLE_MAX_PER_TF = 100

    @property
    def _debug(self) -> bool:
        """Check if debug mode is active (reads global flag, responsive to runtime changes)."""
        return is_debug_enabled()

    @property
    def state(self) -> RunnerState:
        """Current runner state (thread-safe read)."""
        with self._state_lock:
            return self._state

    def _transition_state(self, new_state: RunnerState) -> bool:
        """
        G5.7: Thread-safe state transition with validation.

        Returns True if transition was valid, False otherwise.
        Invalid transitions are logged but not raised (fail-safe).
        """
        with self._state_lock:
            valid_next = VALID_TRANSITIONS.get(self._state, set())
            if new_state not in valid_next:
                logger.warning(
                    f"Invalid state transition: {self._state.value} -> {new_state.value} "
                    f"(valid: {[s.value for s in valid_next]})"
                )
                return False
            old_state = self._state
            self._state = new_state
            logger.debug(f"State transition: {old_state.value} -> {new_state.value}")
            return True

    @property
    def stats(self) -> LiveRunnerStats:
        """Current statistics."""
        return self._stats

    @property
    def is_running(self) -> bool:
        """Check if runner is active."""
        return self._state == RunnerState.RUNNING

    @property
    def is_paused(self) -> bool:
        """G17.3: Check if this runner is paused via file-based IPC.

        Checks for {instance_id}.pause file in ~/.trade/instances/.
        The instance_id is set by EngineManager after construction.
        """
        if not self._instance_id or not self._pause_dir.exists():
            return False
        pause_file = self._pause_dir / f"{self._instance_id}.pause"
        return pause_file.exists()

    async def start(self) -> None:
        """
        Start live trading.

        Connects to WebSocket and begins processing candles.
        """
        if not self._transition_state(RunnerState.STARTING):
            logger.warning(f"Cannot start: runner is {self._state.value}")
            return

        self._stats = LiveRunnerStats(started_at=datetime.now())
        self._stop_event.clear()
        self._reconnect_attempts = 0

        # Set play_hash for debug log correlation
        from ...backtest.execution_validation import compute_play_hash
        play_hash = compute_play_hash(self._engine.play)
        self._engine.set_play_hash(play_hash)

        logger.info(
            f"LiveRunner starting: {self._engine.symbol} {self._engine.timeframe} "
            f"mode={self._engine.mode}"
        )

        if self._debug:
            logger.debug(
                f"[DBG] Runner config: symbol={self._engine.symbol} "
                f"exec_tf={self._engine.timeframe} mode={self._engine.mode} "
                f"max_reconnect={self._max_reconnect_attempts} "
                f"reconcile_interval={self._reconcile_interval}s"
            )
            logger.debug(
                f"[DBG] Play: {self._engine.play.name} "
                f"tf_mapping={getattr(self._engine, '_tf_mapping', 'N/A')}"
            )

        try:
            # Connect to data provider
            await self._connect()

            # G0.4: Sync positions before processing signals
            await self._sync_positions_on_startup()

            # G14.5: Seed daily loss tracker from exchange closed PnL
            # so a restart mid-day doesn't reset loss tracking to $0.
            try:
                from ...core.safety import get_daily_loss_tracker
                em = getattr(self._engine._exchange, '_exchange_manager', None)
                if em is not None:
                    tracker = get_daily_loss_tracker()
                    tracker.seed_from_exchange(em, symbol=self._engine.symbol)
            except Exception as e:
                logger.warning(f"Failed to seed daily loss tracker (non-fatal): {e}")

            # G17.1: Initialize trade journal
            from ..journal import TradeJournal
            self._journal = TradeJournal(
                instance_id=f"{self._engine.symbol}_{id(self)}"
            )

            # G17.4: Initialize notification adapter
            from ..notifications import get_notification_adapter
            self._notifier = get_notification_adapter()

            # Start processing loop
            self._subscription_task = asyncio.create_task(self._process_loop())
            self._transition_state(RunnerState.RUNNING)

            logger.info("LiveRunner running")

        except Exception as e:
            self._transition_state(RunnerState.ERROR)
            self._stats.errors.append(str(e))
            if self._debug:
                logger.error(f"[DBG] Failed to start LiveRunner:\n{traceback.format_exc()}")
            else:
                logger.error(f"Failed to start LiveRunner: {e}")
            raise

    async def stop(self) -> None:
        """
        Stop live trading gracefully.

        Disconnects from WebSocket and cleans up.
        """
        if self._state == RunnerState.STOPPED:
            return

        if not self._transition_state(RunnerState.STOPPING):
            return

        self._stop_event.set()

        # Cancel subscription task with timeout
        if self._subscription_task is not None:
            self._subscription_task.cancel()
            try:
                await asyncio.wait_for(self._subscription_task, timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("Subscription task did not stop within 10s timeout")
            except asyncio.CancelledError:
                pass

        # Cancel open orders before disconnect
        try:
            em = getattr(self._engine._exchange, '_exchange_manager', None)
            if em is not None:
                em.cancel_all_orders(self._engine.symbol)
            logger.info(f"Cancelled open orders for {self._engine.symbol} on shutdown")
        except Exception as e:
            logger.error(f"Failed to cancel orders on shutdown: {e}")

        # Disconnect from data provider
        await self._disconnect()

        self._transition_state(RunnerState.STOPPED)
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
        from ...data.realtime_state import get_realtime_state
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

        # Subscribe to all play timeframes (multi-timeframe support)
        # Read TF mapping from data provider (LiveDataProvider populates it;
        # PlayEngine._tf_mapping is empty in live mode).
        dp = self._engine._data_provider
        tf_mapping = getattr(dp, '_tf_mapping', {}) or self._engine._tf_mapping
        unique_tfs = {tf_mapping[role] for role in ("low_tf", "med_tf", "high_tf") if role in tf_mapping}
        self._play_timeframes = {tf.lower() for tf in unique_tfs}
        self._exec_tf = self._engine.timeframe.lower()

        if self._debug:
            logger.debug(
                f"[DBG] Multi-timeframe subscription: play_tfs={self._play_timeframes} "
                f"exec_tf={self._exec_tf} tf_mapping={tf_mapping}"
            )

        from ...data.realtime_models import KlineData
        bybit_intervals = [KlineData.tf_to_bybit(tf) for tf in unique_tfs]
        self._bootstrap.subscribe_kline_intervals(self._engine.symbol, bybit_intervals)

        if self._debug:
            logger.debug(f"[DBG] Bybit intervals subscribed: {bybit_intervals}")

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

            if hasattr(exchange, '_exchange_manager') and exchange._exchange_manager:
                em = exchange._exchange_manager
                # Query all positions via ExchangeManager (has get_all_positions)
                positions = em.get_all_positions()
                if positions:
                    logger.info(f"Position sync: {len(positions)} existing position(s)")
                    for pos in positions:
                        if pos.symbol == self._engine.symbol:
                            self._has_existing_position = True
                            logger.warning(
                                f"ENGINE STARTING WITH OPEN POSITION: "
                                f"{pos.symbol} {pos.side} size={pos.size} "
                                f"entry={pos.entry_price} -- engine will avoid "
                                f"opening duplicates"
                            )
                else:
                    logger.info("Position sync: no existing positions")
                    self._has_existing_position = False
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

        Processes closed candles matching our symbol and any play timeframe.
        KlineData.interval is pre-normalized by from_bybit() (e.g., "15m", "1h").
        """
        # Filter for our symbol
        if kline_data.symbol != self._engine.symbol:
            return

        # Accept any kline matching a play timeframe (not just exec)
        kline_tf = kline_data.interval.lower() if kline_data.interval else ""
        if kline_tf not in self._play_timeframes:
            return

        # Only process closed candles
        if not kline_data.is_closed:
            return

        # H3: Deduplicate candles (WebSocket reconnect can re-deliver)
        ts_open_epoch = float(kline_data.start_time)
        seen_for_tf = self._seen_candles.setdefault(kline_tf, set())
        if ts_open_epoch in seen_for_tf:
            logger.debug(f"Duplicate candle skipped: {kline_tf} ts_open={ts_open_epoch}")
            return
        seen_for_tf.add(ts_open_epoch)
        # Bound set size per TF
        if len(seen_for_tf) > self._SEEN_CANDLE_MAX_PER_TF:
            # Remove oldest entries (smallest timestamps)
            to_remove = sorted(seen_for_tf)[: len(seen_for_tf) - self._SEEN_CANDLE_MAX_PER_TF]
            seen_for_tf.difference_update(to_remove)

        if self._debug:
            logger.debug(
                f"[DBG] Kline closed: symbol={kline_data.symbol} tf={kline_tf} "
                f"o={kline_data.open} h={kline_data.high} l={kline_data.low} "
                f"c={kline_data.close} v={kline_data.volume:.2f} "
                f"start={kline_data.start_time} end={kline_data.end_time}"
            )

        # Convert to Candle and enqueue with timeframe
        from ..interfaces import Candle
        from datetime import datetime, timezone

        try:
            if kline_data.end_time > 0:
                # Bybit end_time is last ms of candle (e.g. 12:14:59.999); +1 = candle close boundary
                close_ts_ms = kline_data.end_time + 1
            else:
                close_ts_ms = kline_data.start_time + tf_minutes(kline_tf) * 60 * 1000
            candle = Candle(
                ts_open=datetime.fromtimestamp(kline_data.start_time / 1000.0, tz=timezone.utc),
                ts_close=datetime.fromtimestamp(close_ts_ms / 1000.0, tz=timezone.utc),
                open=kline_data.open,
                high=kline_data.high,
                low=kline_data.low,
                close=kline_data.close,
                volume=kline_data.volume,
            )

            # Enqueue (candle, timeframe) tuple
            self._candle_queue.put_nowait((candle, kline_data.interval))
            depth = self._candle_queue.qsize()
            if depth > 10:
                logger.warning(f"Candle queue depth={depth}, processing may be falling behind")

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
        # Initialize peak equity for max drawdown tracking (B5)
        self._peak_equity = self._engine._exchange.get_equity()

        while not self._stop_event.is_set():
            try:
                # B3: Check panic state at top of each iteration
                if check_panic_and_halt():
                    logger.warning("Panic state active, stopping LiveRunner")
                    self._stop_event.set()
                    break

                # Wait for next candle close
                result = await self._wait_for_candle()
                if result is None:
                    # Heartbeat: show we're alive while waiting for candles
                    elapsed = self._stats.duration_seconds
                    mins, secs = divmod(int(elapsed), 60)
                    hrs, mins = divmod(mins, 60)
                    last_ts = self._stats.last_candle_ts
                    last_str = last_ts.strftime("%H:%M:%S") if last_ts else "none"
                    logger.info(
                        f"Waiting for candle... | {self._engine.symbol} {self._exec_tf} "
                        f"| uptime={hrs}h{mins:02d}m | bars={self._stats.bars_processed} "
                        f"signals={self._stats.signals_generated} | last={last_str}"
                    )
                    continue

                candle, timeframe = result

                # Process candle
                await self._process_candle(candle, timeframe)

                # B5: Check max drawdown after processing
                await self._check_max_drawdown()

                # G5.4: Periodic position reconciliation
                await self._maybe_reconcile_positions()

            except asyncio.CancelledError:
                self._transition_state(RunnerState.STOPPING)
                self._stop_event.set()
                break

            except (ConnectionError, TimeoutError, OSError) as e:
                # Network/connection errors: attempt reconnection
                self._stats.errors.append(str(e))
                if self._debug:
                    logger.error(f"[DBG] Connection error:\n{traceback.format_exc()}")
                else:
                    logger.error(f"Connection error in process loop: {e}")

                if self._on_error:
                    self._on_error(e)

                if self._reconnect_attempts < self._max_reconnect_attempts:
                    await self._reconnect()
                else:
                    logger.error("Max reconnection attempts reached, stopping")
                    self._transition_state(RunnerState.ERROR)
                    self._stop_event.set()
                    break

            except Exception as e:
                # Logic errors (TypeError, AttributeError, etc.): halt trading
                self._stats.errors.append(str(e))
                if self._debug:
                    logger.error(f"[DBG] Fatal error in process loop:\n{traceback.format_exc()}")
                else:
                    logger.error(f"Fatal error in process loop (non-connection): {e}")

                if self._on_error:
                    self._on_error(e)

                # Logic errors are not recoverable by reconnection -- stop
                self._transition_state(RunnerState.ERROR)
                self._stop_event.set()
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
            # Wait for candle from thread-safe queue via executor
            loop = asyncio.get_running_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    None, lambda: self._candle_queue.get(timeout=queue_timeout)
                ),
                timeout=queue_timeout + 5.0,  # Outer timeout slightly longer
            )
            return result

        except (asyncio.TimeoutError, queue.Empty):
            # No candle received in timeout period
            # Check if we've exceeded health threshold
            if self._stats.last_candle_ts:
                since_last = (datetime.now(timezone.utc) - self._stats.last_candle_ts).total_seconds()
                expected_interval = tf_mins * 60

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

    async def _process_candle(self, candle, timeframe: str) -> None:
        """
        Process a closed candle through the engine.

        Args:
            candle: Candle data from WebSocket
            timeframe: Timeframe string (e.g. "15m", "1h", "D")
        """
        from ..adapters.live import LiveDataProvider

        self._stats.bars_processed += 1
        self._stats.last_candle_ts = candle.ts_close

        if self._debug:
            logger.debug(
                f"[DBG] Processing candle #{self._stats.bars_processed}: "
                f"tf={timeframe} close={candle.close} ts={candle.ts_close} "
                f"o={candle.open} h={candle.high} l={candle.low} v={candle.volume:.2f}"
            )

        # Update data provider with new candle (routes to correct TF buffer)
        data_provider = self._engine._data_provider
        if isinstance(data_provider, LiveDataProvider):
            data_provider.on_candle_close(candle, timeframe=timeframe)

        # Only evaluate signals on execution timeframe candles
        if timeframe.lower() != self._exec_tf:
            logger.debug(f"Non-exec TF candle ({timeframe}), updated indicators only")
            return

        # Check if data provider is ready (warmup complete)
        if not data_provider.is_ready():
            # Show warmup progress per TF buffer
            warmup_target = getattr(data_provider, '_warmup_bars', '?')
            low_n = len(getattr(data_provider, '_low_tf_buffer', []))
            med_n = len(getattr(data_provider, '_med_tf_buffer', []))
            high_n = len(getattr(data_provider, '_high_tf_buffer', []))
            logger.info(
                f"Warmup: {data_provider.num_bars}/{warmup_target} bars "
                f"(low_tf={low_n} med_tf={med_n} high_tf={high_n}) "
                f"| close={candle.close}"
            )
            return

        # Status line on each exec TF candle
        logger.info(
            f"Bar #{self._stats.bars_processed} | {self._engine.symbol} {timeframe} "
            f"close={candle.close} | signals={self._stats.signals_generated}"
        )

        # G17.3: Check pause state -- skip signal evaluation but keep receiving data
        if self.is_paused:
            logger.debug("Runner paused, skipping signal evaluation")
            return

        if self._debug:
            # Dump indicator snapshot before engine processes
            self._debug_dump_indicators(data_provider)

        # Process through engine (use -1 for latest in live mode)
        try:
            signal = self._engine.process_bar(-1)
        except Exception as e:
            if self._debug:
                logger.error(f"[DBG] Error processing bar:\n{traceback.format_exc()}")
            else:
                logger.error(f"Error processing bar: {e}")
            self._stats.errors.append(f"Process error: {e}")
            return

        if self._debug and signal is None:
            logger.debug(
                f"[DBG] No signal at bar #{self._stats.bars_processed} "
                f"(close={candle.close}, ts={candle.ts_close})"
            )

        if signal is not None:
            self._stats.signals_generated += 1
            self._stats.last_signal_ts = datetime.now()

            logger.info(
                f"Signal generated: {signal.direction} {self._engine.symbol} "
                f"at {candle.ts_close}"
            )

            if self._debug:
                logger.debug(
                    f"[DBG] Signal detail: direction={signal.direction} "
                    f"symbol={signal.symbol} size_usdt={signal.size_usdt} "
                    f"strategy={signal.strategy} confidence={signal.confidence} "
                    f"metadata={signal.metadata}"
                )

            # G17.1: Record signal in journal
            if self._journal:
                self._journal.record_signal(
                    symbol=self._engine.symbol,
                    direction=signal.direction,
                    size_usdt=signal.size_usdt,
                    strategy=signal.strategy,
                    metadata=signal.metadata,
                )

            # G17.4: Notify signal
            if self._notifier:
                self._notifier.notify_signal(
                    symbol=self._engine.symbol,
                    direction=signal.direction,
                    size_usdt=signal.size_usdt,
                )

            # B4: Run safety checks before execution
            if not self._run_safety_checks():
                logger.warning("Safety checks failed, skipping signal execution")
                return

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
        if self._debug:
            logger.debug(
                f"[DBG] Executing signal: {signal.direction} {signal.symbol} "
                f"size_usdt={signal.size_usdt} metadata={signal.metadata}"
            )

        try:
            self._stats.orders_submitted += 1
            result = self._engine.execute_signal(signal)

            if result.success:
                self._stats.orders_filled += 1
                logger.info(
                    f"Order filled: {signal.direction} {signal.symbol} "
                    f"id={result.order_id}"
                )
                if self._debug:
                    logger.debug(
                        f"[DBG] Fill detail: order_id={result.order_id} "
                        f"fill_price={result.fill_price} fill_usdt={result.fill_usdt}"
                    )

                # G17.1: Record fill in journal
                if self._journal:
                    self._journal.record_fill(
                        symbol=signal.symbol,
                        direction=signal.direction,
                        size_usdt=result.fill_usdt or signal.size_usdt,
                        fill_price=result.fill_price or 0.0,
                        order_id=result.order_id or "",
                        sl=signal.metadata.get("stop_loss") if signal.metadata else None,
                        tp=signal.metadata.get("take_profit") if signal.metadata else None,
                    )

                # G17.4: Notify fill
                if self._notifier:
                    self._notifier.notify_fill(
                        symbol=signal.symbol,
                        direction=signal.direction,
                        fill_price=result.fill_price or 0.0,
                    )
            else:
                self._stats.orders_failed += 1
                logger.warning(f"Order failed: {result.error}")

                # G17.1: Record error in journal
                if self._journal:
                    self._journal.record_error(
                        symbol=signal.symbol,
                        direction=signal.direction,
                        error=result.error or "Unknown error",
                    )

                # G17.4: Notify error
                if self._notifier:
                    self._notifier.notify_error(
                        f"Order failed for {signal.symbol}: {result.error}"
                    )

        except Exception as e:
            self._stats.orders_failed += 1
            self._stats.errors.append(f"Execute error: {e}")
            if self._debug:
                logger.error(f"[DBG] Failed to execute signal:\n{traceback.format_exc()}")
            else:
                logger.error(f"Failed to execute signal: {e}")

            # G17.1: Record exception in journal
            if self._journal:
                self._journal.record_error(
                    symbol=signal.symbol,
                    direction=signal.direction,
                    error=str(e),
                )

            # G17.4: Notify error
            if self._notifier:
                self._notifier.notify_error(
                    f"Execute exception for {signal.symbol}: {e}"
                )

    async def _reconnect(self) -> None:
        """Attempt to reconnect to WebSocket with exponential backoff."""
        self._transition_state(RunnerState.RECONNECTING)
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
            await self._sync_positions_on_startup()
            self._transition_state(RunnerState.RUNNING)
            self._reconnect_attempts = 0  # Reset on success
            logger.info("Reconnection successful")
        except Exception as e:
            logger.error(f"Reconnection failed: {e}")
            self._stats.errors.append(f"Reconnect error: {e}")

    def _run_safety_checks(self) -> bool:
        """
        B4: Run SafetyChecks before order execution.

        Returns True if all checks pass, False to skip execution.
        Fail-closed: if safety checks cannot run, trading is halted.
        """
        try:
            from ...core.safety import SafetyChecks

            em = getattr(self._engine._exchange, '_exchange_manager', None)
            if em is None:
                logger.error("Safety checks failed: no ExchangeManager available")
                return False

            if not getattr(em, '_initialized', False):
                logger.error("Safety checks failed: ExchangeManager not initialized")
                return False

            checks = SafetyChecks(em, em.config)
            passed, failures = checks.run_all_checks()
            if not passed:
                for reason in failures:
                    logger.error(f"Safety check failed: {reason}")
                    self._stats.errors.append(f"Safety: {reason}")
            return passed

        except Exception as e:
            if self._debug:
                logger.error(f"[DBG] Safety checks exception (fail-closed):\n{traceback.format_exc()}")
            else:
                logger.error(f"Safety checks failed (fail-closed): {e}")
            return False

    def _debug_dump_indicators(self, data_provider) -> None:
        """Dump current indicator values when debug mode is active."""
        from ..adapters.live import LiveDataProvider, LiveIndicatorCache

        if not isinstance(data_provider, LiveDataProvider):
            return

        cache: LiveIndicatorCache | None = data_provider._exec_indicators
        if cache is None:
            logger.debug("[DBG] Indicators: no exec indicator cache")
            return

        with cache._lock:
            indicator_snapshot = {}
            for name, arr in cache._indicators.items():
                if len(arr) > 0:
                    val = arr[-1]
                    try:
                        import math
                        if isinstance(val, (int, float)) and not math.isnan(val):
                            indicator_snapshot[name] = f"{val:.6g}"
                        elif isinstance(val, (int, float)):
                            indicator_snapshot[name] = "NaN"
                        else:
                            indicator_snapshot[name] = str(val)
                    except (TypeError, ValueError):
                        indicator_snapshot[name] = str(val)
                else:
                    indicator_snapshot[name] = "empty"

        if indicator_snapshot:
            lines = [f"    {k}: {v}" for k, v in sorted(indicator_snapshot.items())]
            logger.debug(f"[DBG] Indicator snapshot (exec TF, {len(indicator_snapshot)} values):\n" + "\n".join(lines))
        else:
            logger.debug("[DBG] Indicator snapshot: empty (no indicators computed)")

    async def _check_max_drawdown(self) -> None:
        """
        B5: Check equity vs max_drawdown_pct and trigger panic if breached.

        Ported from BacktestRunner max drawdown logic.
        """
        max_dd_pct = self._engine.config.max_drawdown_pct
        if max_dd_pct <= 0:
            return

        try:
            equity = self._engine._exchange.get_equity()

            # H5: Skip drawdown check until first REAL equity confirmed.
            # On WS/REST failure, get_equity() may return the default initial_equity
            # which can cause a false 80%+ drawdown panic.
            if not self._equity_initialized:
                if equity != self._peak_equity and equity > 0:
                    self._equity_initialized = True
                    self._peak_equity = equity
                    logger.info(f"Equity initialized from exchange: ${equity:.2f}")
                return

            self._peak_equity = max(self._peak_equity, equity)

            if self._peak_equity <= 0:
                return

            current_dd_pct = (self._peak_equity - equity) / self._peak_equity * 100

            if current_dd_pct >= max_dd_pct:
                reason = (
                    f"Max drawdown hit: {current_dd_pct:.2f}% >= {max_dd_pct:.2f}% "
                    f"(equity ${equity:.2f}, peak ${self._peak_equity:.2f})"
                )
                logger.warning(reason)
                self._stats.errors.append(reason)

                # G17.4: Notify panic
                if self._notifier:
                    self._notifier.notify_panic(reason)

                # Trigger panic to halt all trading
                panic = get_panic_state()
                panic.trigger(reason)
                self._stop_event.set()

        except Exception as e:
            logger.warning(f"Max drawdown check failed (non-fatal): {e}")
