"""
Unified Play Engine for backtest, demo, and live modes.

This is the core engine that processes bars and generates signals. The key
design principle is that signal generation logic is IDENTICAL across all
modes. Mode differences are isolated to injected adapters.

Architecture:
    PlayEngine receives:
    - Play: Strategy definition (rules, features, structures)
    - DataProvider: Market data access (candles, indicators, structures)
    - ExchangeAdapter: Order execution (simulated or real)
    - StateStore: State persistence (for recovery)

    PlayEngine performs:
    - Bar-by-bar processing via process_bar()
    - Rule evaluation for entry/exit signals
    - Risk sizing for position management
    - Signal execution via adapters

Usage:
    # Engine is created via factory, not directly
    engine = PlayEngineFactory.create(play, mode="backtest")

    # Process bars (called by runner)
    for bar_index in range(num_bars):
        signal = engine.process_bar(bar_index)
        if signal:
            result = engine.execute_signal(signal)
"""


import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Literal, cast

from .interfaces import (
    Candle,
    DataProvider,
    ExchangeAdapter,
    Order,
    OrderResult,
    Position,
    StateStore,
    EngineState,
)
from .signal import SubLoopEvaluator
from .sizing import SizingModel, SizingConfig

from ..utils.logger import get_logger
from ..utils.debug import is_debug_enabled, debug_log, debug_signal, debug_trade, debug_snapshot
from .timeframe import TFIndexManager


# G5.8: Engine phase state machine
class EnginePhase(str, Enum):
    """Operational phase of the PlayEngine."""

    CREATED = "created"      # Initialized, not started
    WARMING_UP = "warming"   # Processing warmup bars
    READY = "ready"          # Warmup complete, ready for signals
    RUNNING = "running"      # Actively processing bars
    STOPPED = "stopped"      # Cleanly stopped
    ERROR = "error"          # Error state


# G5.8: Valid phase transitions
VALID_PHASE_TRANSITIONS: dict[EnginePhase, set[EnginePhase]] = {
    EnginePhase.CREATED: {EnginePhase.WARMING_UP, EnginePhase.READY},
    EnginePhase.WARMING_UP: {EnginePhase.READY, EnginePhase.ERROR},
    EnginePhase.READY: {EnginePhase.RUNNING, EnginePhase.STOPPED, EnginePhase.ERROR},
    EnginePhase.RUNNING: {EnginePhase.READY, EnginePhase.STOPPED, EnginePhase.ERROR},
    EnginePhase.STOPPED: {EnginePhase.CREATED},  # Can restart
    EnginePhase.ERROR: {EnginePhase.STOPPED},    # Must stop before restart
}


if TYPE_CHECKING:
    from ..backtest.play import Play
    from ..backtest.feature_registry import FeatureRegistry
    from src.structures import MultiTFIncrementalState
    from ..backtest.execution_validation import PlaySignalEvaluator, EvaluationResult, SignalDecision
    from ..backtest.runtime.snapshot_view import RuntimeSnapshotView
    from ..backtest.runtime.feed_store import FeedStore
    from ..backtest.simulated_risk_manager import StopLiqValidationResult
    from ..core.risk_manager import Signal


@dataclass(slots=True)
class PlayEngineConfig:
    """Configuration for PlayEngine."""

    # Mode
    mode: Literal["backtest", "demo", "live", "shadow"]

    # Risk parameters
    initial_equity: float = 10000.0
    sizing_model: str = "percent_equity"  # "percent_equity", "risk_based", "fixed_notional"
    risk_per_trade_pct: float = 1.0
    max_leverage: float = 2.0
    min_trade_usdt: float = 10.0
    max_drawdown_pct: float = 0.0  # 0 = disabled, >0 = halt at this drawdown %

    # Risk policy
    risk_mode: str = "none"  # "none" or "rules"

    # Fee model (loaded from DEFAULTS if None)
    taker_fee_rate: float | None = None
    maker_fee_rate: float | None = None
    slippage_bps: float | None = None

    # Entry gate behavior (matches RiskProfileConfig)
    include_est_close_fee_in_entry_gate: bool = False

    # SL vs Liquidation safety check
    # "reject": Reject entry if SL beyond liquidation price (default, safest)
    # "adjust": Auto-tighten SL to safe distance from liquidation
    # "warn": Allow entry but log warning
    on_sl_beyond_liq: str = "reject"
    maintenance_margin_rate: float | None = None

    # State persistence
    persist_state: bool = False
    state_save_interval: int = 100  # Save every N bars

    def __post_init__(self) -> None:
        """Load defaults from config/defaults.yml if not specified."""
        from src.config.constants import DEFAULTS
        if self.taker_fee_rate is None:
            self.taker_fee_rate = DEFAULTS.fees.taker_rate
        if self.maker_fee_rate is None:
            self.maker_fee_rate = DEFAULTS.fees.maker_rate
        if self.slippage_bps is None:
            self.slippage_bps = DEFAULTS.execution.slippage_bps
        if self.maintenance_margin_rate is None:
            self.maintenance_margin_rate = DEFAULTS.margin.maintenance_margin_rate


class PlayEngine:
    """
    Unified engine for executing Plays across all modes.

    The engine processes bars, evaluates rules, and generates signals.
    Mode-specific behavior (data access, order execution) is delegated
    to injected adapters, ensuring identical signal logic everywhere.

    Key Methods:
        process_bar(bar_index): Process one bar, return signal if triggered
        execute_signal(signal): Execute signal through exchange adapter
        get_state(): Get current engine state for persistence

    The engine is stateful and tracks:
        - Current bar index
        - Position state (via exchange adapter)
        - Incremental structure state
        - Performance metrics
    """

    def __init__(
        self,
        play: "Play",
        data_provider: DataProvider,
        exchange: ExchangeAdapter,
        state_store: StateStore,
        config: PlayEngineConfig,
    ):
        """
        Initialize PlayEngine with injected adapters.

        Args:
            play: Play instance with strategy definition
            data_provider: Market data provider (backtest or live)
            exchange: Exchange adapter (simulated or real)
            state_store: State persistence (in-memory or file)
            config: Engine configuration
        """
        self.play = play
        self.data = data_provider
        self.exchange = exchange
        self.state_store = state_store
        self.config = config

        self.logger = get_logger()

        # Engine identity
        self.engine_id = f"{play.name}_{config.mode}_{uuid.uuid4().hex[:8]}"
        self._play_hash: str = ""  # Set by runner for debug correlation

        # Core state (G5.8: thread-safe phase machine)
        self._current_bar_index: int = -1
        self._warmup_complete: bool = False
        self._last_signal_ts: datetime | None = None
        self._phase = EnginePhase.CREATED
        self._phase_lock = threading.Lock()

        # Store Play and config as private attributes for adapters
        self._play = play
        self._data_provider = data_provider
        self._exchange = exchange
        self._config = config

        # Feature registry from Play
        self._feature_registry: FeatureRegistry | None = play.feature_registry

        # Signal evaluator (lazy initialized)
        self._signal_evaluator: PlaySignalEvaluator | None = None

        # Incremental state for structures (swing, trend, zones)
        # This is shared with data_provider in backtest mode
        self._incremental_state: MultiTFIncrementalState | None = None

        # 3-feed system for multi-timeframe indicators (set by parity test or runner)
        self._low_tf_feed: FeedStore | None = None   # FeedStore for low_tf (always present)
        self._med_tf_feed: FeedStore | None = None   # FeedStore for med_tf (None if same as low_tf)
        self._high_tf_feed: FeedStore | None = None  # FeedStore for high_tf (None if same as med_tf)
        self._exec_role: str = "low_tf"  # Which feed exec points to
        self._tf_mapping: dict[str, str] = {}  # TF mapping from Play config

        # TF index manager (shared module: src/engine/timeframe/)
        # Manages indices for all 3 TFs relative to exec role
        self._tf_index_manager: TFIndexManager | None = None

        # 1m quote feed for action model (set by parity test or runner)
        # This enables granular 1m evaluation within exec_tf bars
        self._quote_feed: FeedStore | None = None  # FeedStore for 1m OHLCV
        self._quote_feed_fallback_warned: bool = False  # Track if fallback warning issued

        # Snapshot view for rule evaluation (built per bar)
        self._snapshot_view: RuntimeSnapshotView | None = None

        # Unified sizing model
        sizing_config = SizingConfig(
            initial_equity=config.initial_equity,
            sizing_model=config.sizing_model,
            risk_per_trade_pct=config.risk_per_trade_pct,
            max_leverage=config.max_leverage,
            min_trade_usdt=config.min_trade_usdt,
            taker_fee_rate=config.taker_fee_rate,
            include_est_close_fee_in_entry_gate=config.include_est_close_fee_in_entry_gate,
        )
        self._sizing_model = SizingModel(sizing_config)

        # Risk policy for signal filtering
        # Lazy initialized when first signal is evaluated
        self._risk_policy = None

        # Performance tracking
        self._total_signals: int = 0
        self._total_trades: int = 0
        self._bars_processed: int = 0

        # Live mode multi-TF index tracking (set by _update_live_tf_indices)
        self._prev_med_tf_len: int = 0
        self._prev_high_tf_len: int = 0
        self._live_med_tf_idx: int = 0
        self._live_high_tf_idx: int = 0

        # Optional snapshot callback for auditing (set via set_on_snapshot)
        self._on_snapshot: Callable[["RuntimeSnapshotView", int, int, int], None] | None = None

        # Limit order expiry tracking: list of (order_id, submit_bar_index)
        self._pending_limit_orders: list[tuple[str, int]] = []

        # Anchored VWAP post-structure update cache
        # These indicators depend on swing structure versions and must be updated
        # AFTER structures, not during batch pre-computation.
        self._anchored_vwap_cache: dict[str, Any] | None = None  # Lazy init

        self.logger.info(
            f"PlayEngine initialized: {self.engine_id} "
            f"mode={config.mode} symbol={play.symbol_universe[0]}"
        )

    @property
    def symbol(self) -> str:
        """Trading symbol."""
        return self.play.symbol_universe[0]

    @property
    def timeframe(self) -> str:
        """Execution timeframe."""
        return self.play.exec_tf

    @property
    def mode(self) -> str:
        """Current execution mode."""
        return self.config.mode

    @property
    def is_live(self) -> bool:
        """True if running in live mode (real money)."""
        return self.config.mode == "live"

    @property
    def is_demo(self) -> bool:
        """True if running in demo mode (fake money)."""
        return self.config.mode == "demo"

    @property
    def is_shadow(self) -> bool:
        """True if running in shadow mode (signals only)."""
        return self.config.mode == "shadow"

    @property
    def is_backtest(self) -> bool:
        """True if running in backtest mode."""
        return self.config.mode == "backtest"

    @property
    def phase(self) -> EnginePhase:
        """Current engine phase (thread-safe read)."""
        with self._phase_lock:
            return self._phase

    def _transition_phase(self, new_phase: EnginePhase) -> bool:
        """
        G5.8: Thread-safe phase transition with validation.

        Returns True if transition was valid, False otherwise.
        Invalid transitions are logged but not raised (fail-safe).
        """
        with self._phase_lock:
            valid_next = VALID_PHASE_TRANSITIONS.get(self._phase, set())
            if new_phase not in valid_next:
                self.logger.warning(
                    f"Invalid phase transition: {self._phase.value} -> {new_phase.value} "
                    f"(valid: {[s.value for s in valid_next]})"
                )
                return False
            old_phase = self._phase
            self._phase = new_phase
            self.logger.debug(f"Engine phase: {old_phase.value} -> {new_phase.value}")
            return True

    @property
    def _current_high_tf_idx(self) -> int:
        """Current high_tf forward-fill index (from TFIndexManager or live tracking)."""
        if self._tf_index_manager is not None:
            return self._tf_index_manager.high_tf_idx
        return self._live_high_tf_idx

    @property
    def _current_med_tf_idx(self) -> int:
        """Current med_tf forward-fill index (from TFIndexManager or live tracking)."""
        if self._tf_index_manager is not None:
            return self._tf_index_manager.med_tf_idx
        return self._live_med_tf_idx

    def set_play_hash(self, play_hash: str) -> None:
        """Set play hash for debug log correlation."""
        self._play_hash = play_hash

    def set_on_snapshot(
        self,
        callback: "Callable[[RuntimeSnapshotView, int, int, int], None] | None"
    ) -> None:
        """
        Set callback invoked after snapshot build, before rule evaluation.

        This is used by audits to capture snapshot values during backtest runs.
        The callback receives (snapshot, exec_idx, high_tf_idx, med_tf_idx).

        Args:
            callback: Function to call with snapshot data, or None to disable
        """
        self._on_snapshot = callback

    def process_bar(self, bar_index: int) -> "Signal | None":
        """
        Process a single bar and return signal if entry/exit triggered.

        This is the core method called by runners. It performs:
        1. Update incremental state (structures)
        2. Check warmup/readiness
        3. Step exchange (process fills, TP/SL)
        4. Evaluate entry/exit rules
        5. Generate signal if triggered

        Args:
            bar_index: Index into data arrays (0..N-1 for backtest, -1 for live)

        Returns:
            Signal if entry/exit triggered, None otherwise

        Note:
            The same logic runs for backtest and live. The only difference
            is what bar_index means (historical index vs -1 for latest).
        """
        self._current_bar_index = bar_index
        self._bars_processed += 1

        # Refresh equity from exchange for accurate sizing (live/demo only)
        if not self.is_backtest:
            try:
                self._sizing_model.update_equity(self.exchange.get_equity())
            except Exception as e:
                self.logger.error(f"Failed to refresh equity from exchange: {e}. Using last known value.")

        # Get current candle
        try:
            candle = self.data.get_candle(bar_index)
        except IndexError:
            self.logger.warning(f"Bar index {bar_index} out of bounds")
            return None

        # 7.3: Log bar OHLCV when debug enabled
        if is_debug_enabled() and self.is_backtest:
            debug_log(
                self._play_hash, "Bar OHLCV",
                bar_idx=bar_index,
                O=candle.open, H=candle.high, L=candle.low,
                C=candle.close, V=candle.volume,
            )

        # Update high_tf/med_tf indices (forward-fill logic)
        self._update_high_tf_med_tf_indices(candle)

        # 1. Update incremental state (structures)
        if self._incremental_state is not None:
            self._update_incremental_state(bar_index, candle)

        # 2. Check readiness (warmup complete, data available)
        if not self._is_ready():
            if bar_index == 100:  # Debug: log early on why not ready
                self.logger.debug(f"Not ready at bar {bar_index}: data.is_ready={self.data.is_ready()}")
            return None

        # G5.8: Transition to RUNNING when processing post-warmup bars
        if self._phase == EnginePhase.READY:
            self._transition_phase(EnginePhase.RUNNING)

        # 3. Step exchange (process pending orders, check TP/SL)
        self.exchange.step(candle)

        # 3b. Prune filled limit orders and check expiry (after fills are processed)
        if self._pending_limit_orders:
            # Remove orders that were filled during step()
            # In backtest, pending orders use sim order IDs (order_XXXX) as client_order_id
            still_pending = {
                o.client_order_id for o in self.exchange.get_pending_orders(self.symbol)
            }
            self._pending_limit_orders = [
                (oid, bar) for oid, bar in self._pending_limit_orders if oid in still_pending
            ]
            # Check expiry
            if self._pending_limit_orders and self.play.expire_after_bars > 0:
                self._check_limit_expiry(bar_index)

        # 4. Get current position
        position = self.exchange.get_position(self.symbol)

        if is_debug_enabled() and not self.is_backtest:
            self.logger.debug(
                f"[DBG] Engine.process_bar: phase={self._phase.value} "
                f"bar={bar_index} close={candle.close} "
                f"position={'FLAT' if position is None else f'{position.side} {position.size_qty}'}"
            )

        # 5. Evaluate rules and generate signal
        signal = self._evaluate_rules(bar_index, candle, position)

        if signal:
            self._total_signals += 1
            self._last_signal_ts = candle.ts_close

            # 7.3: Log signal evaluation result
            if is_debug_enabled() and self.is_backtest:
                sl = signal.metadata.get("stop_loss") if signal.metadata else None
                tp = signal.metadata.get("take_profit") if signal.metadata else None
                fv: dict[str, float] = {}
                if isinstance(sl, (int, float)):
                    fv["sl"] = float(sl)
                if isinstance(tp, (int, float)):
                    fv["tp"] = float(tp)
                debug_signal(
                    self._play_hash, bar_index,
                    action=signal.direction,
                    feature_values=fv if fv else None,
                )
        elif is_debug_enabled() and self.is_backtest and bar_index % 100 == 0:
            # Log periodic "no signal" milestone so user knows engine is running
            pos_str = "FLAT" if position is None else f"{position.side} {position.size_qty}"
            debug_log(
                self._play_hash, "No signal",
                bar_idx=bar_index,
                position=pos_str,
            )

        # 6. Persist state if configured
        if self.config.persist_state:
            if self._bars_processed % self.config.state_save_interval == 0:
                self._save_state()

        return signal

    def execute_signal(self, signal: "Signal") -> OrderResult:
        """
        Execute a signal through the exchange adapter.

        This method:
        1. For FLAT (exit) signals: Calls submit_close()
        2. For LONG/SHORT (entry) signals:
           - Applies risk sizing
           - Validates minimum size
           - Creates order with TP/SL
           - Submits to exchange

        Args:
            signal: Signal to execute (from process_bar)

        Returns:
            OrderResult with fill info or error

        Note:
            In shadow mode, this logs but doesn't execute.
        """
        # Shadow mode: log but don't execute
        if self.is_shadow:
            self.logger.info(
                f"[SHADOW] Signal: {signal.direction} {self.symbol} "
                f"size={signal.size_usdt:.2f} USDT"
            )
            return OrderResult(
                success=True,
                order_id=f"shadow_{uuid.uuid4().hex[:8]}",
                metadata={"shadow": True, "signal": signal},
            )

        # Handle exit signals (FLAT) differently - submit close request
        if signal.direction.upper() == "FLAT":
            # Get exit percent from metadata (default 100%)
            exit_percent = 100.0
            if signal.metadata and "exit_percent" in signal.metadata:
                exit_percent = signal.metadata["exit_percent"]

            # Submit close request (will be processed on next bar)
            self.exchange.submit_close(reason="signal", percent=exit_percent)
            self.logger.info(
                f"Exit signal: {self.symbol} close {exit_percent}%"
            )

            # 7.3: Log position close via debug_trade
            if is_debug_enabled() and self.is_backtest:
                debug_trade(
                    self._play_hash, self._current_bar_index,
                    event="close_signal",
                    trade_num=self._total_trades,
                )

            return OrderResult(
                success=True,
                order_id=f"close_{uuid.uuid4().hex[:8]}",
                metadata={"close": True, "percent": exit_percent},
            )

        # Entry signals (LONG/SHORT)
        # Apply risk policy filtering (if risk_mode=rules)
        if self.config.risk_mode == "rules":
            decision = self._check_risk_policy(signal)
            if not decision.allowed:
                self.logger.debug(f"Signal blocked by risk policy: {decision.reason}")
                return OrderResult(
                    success=False,
                    error=f"Risk policy blocked: {decision.reason}",
                )

        # Validate SL vs liquidation price (CRITICAL safety check)
        stop_loss = signal.metadata.get("stop_loss") if signal.metadata else None
        if stop_loss is not None and self.config.on_sl_beyond_liq != "disabled":
            sl_validation_result = self._validate_sl_vs_liquidation(signal, stop_loss)
            if not sl_validation_result.valid:
                mode = self.config.on_sl_beyond_liq
                if mode == "reject":
                    self.logger.warning(
                        f"SL vs LIQ REJECTED: {sl_validation_result.reason} "
                        f"(leverage={self.config.max_leverage}x)"
                    )
                    return OrderResult(
                        success=False,
                        error=f"SL beyond liquidation: {sl_validation_result.reason}",
                    )
                elif mode == "adjust" and sl_validation_result.adjusted_stop is not None:
                    self.logger.warning(
                        f"SL AUTO-ADJUSTED: {sl_validation_result.reason} -> "
                        f"new SL={sl_validation_result.adjusted_stop:.2f}"
                    )
                    # Update signal metadata with adjusted stop
                    if signal.metadata is None:
                        signal.metadata = {}
                    signal.metadata["stop_loss"] = sl_validation_result.adjusted_stop
                    signal.metadata["sl_adjusted_from"] = stop_loss
                elif mode == "warn":
                    self.logger.warning(
                        f"SL vs LIQ WARNING: {sl_validation_result.reason} "
                        f"(proceeding anyway - on_sl_beyond_liq=warn)"
                    )

        # Apply risk sizing using unified SizingModel
        sized_usdt = self._size_position(signal)

        # Validate minimum size
        if sized_usdt < self.config.min_trade_usdt:
            self.logger.debug(
                f"Size too small ({sized_usdt:.2f} < {self.config.min_trade_usdt}), skipping"
            )
            return OrderResult(
                success=False,
                error=f"Position size {sized_usdt:.2f} below minimum {self.config.min_trade_usdt}",
            )

        # Create order with order type from Play config
        side = cast(Literal["LONG", "SHORT", "FLAT"], signal.direction.upper())
        order_type = self.play.entry_order_type  # "MARKET" or "LIMIT"
        limit_price: float | None = None

        if order_type == "LIMIT":
            try:
                current_price = self.data.get_candle(self._current_bar_index).close
            except (IndexError, AttributeError):
                current_price = None

            if current_price is not None and self.play.limit_offset_pct > 0:
                offset = self.play.limit_offset_pct / 100.0
                if signal.direction.upper() == "LONG":
                    limit_price = current_price * (1.0 - offset)
                else:
                    limit_price = current_price * (1.0 + offset)
            elif current_price is not None:
                limit_price = current_price  # 0% offset = at current price

        order = Order(
            symbol=self.symbol,
            side=side,
            size_usdt=sized_usdt,
            order_type=cast(Literal["MARKET", "LIMIT", "STOP_MARKET", "STOP_LIMIT"], order_type),
            limit_price=limit_price,
            stop_loss=signal.metadata.get("stop_loss") if signal.metadata else None,
            take_profit=signal.metadata.get("take_profit") if signal.metadata else None,
            time_in_force=self.play.time_in_force,
            tp_order_type=self.play.tp_order_type,
            sl_order_type=self.play.sl_order_type,
            metadata={"signal": signal, "bar_index": self._current_bar_index},
        )

        # Submit to exchange
        result = self.exchange.submit_order(order)

        if result.success:
            self._total_trades += 1
            # Track pending limit orders for expiry (use exchange_order_id for sim exchange)
            if order_type == "LIMIT" and self.play.expire_after_bars > 0:
                track_id = result.exchange_order_id or result.order_id
                if track_id:
                    self._pending_limit_orders.append((track_id, self._current_bar_index))
            # Only log fill details when available (live mode)
            # Backtest fills are logged by BacktestRunner after process_bar
            if result.fill_price and result.fill_usdt:
                self.logger.info(
                    f"Order filled: {signal.direction} {self.symbol} "
                    f"price={result.fill_price:.2f} size={result.fill_usdt:.2f} USDT"
                )

            # 7.3: Log position open via debug_trade
            if is_debug_enabled() and self.is_backtest:
                debug_trade(
                    self._play_hash, self._current_bar_index,
                    event="opened",
                    trade_num=self._total_trades,
                    entry=result.fill_price or order.limit_price,
                    sl=order.stop_loss,
                    tp=order.take_profit,
                )
        else:
            self.logger.warning(f"Order failed: {result.error}")

        return result

    def get_state(self) -> EngineState:
        """
        Get current engine state for persistence.

        Returns:
            EngineState with current position, equity, incremental state, and metadata
        """
        position = self.exchange.get_position(self.symbol)

        # Serialize incremental state if available
        incremental_json: str | None = None
        if self._incremental_state is not None and hasattr(self._incremental_state, 'to_json'):
            try:
                import json as _json
                incremental_json = _json.dumps(self._incremental_state.to_json())
            except Exception as e:
                self.logger.error(f"Failed to serialize incremental state: {e}")

        return EngineState(
            engine_id=self.engine_id,
            play_id=self.play.name or self.engine_id,
            mode=cast(Literal["backtest", "demo", "live", "shadow"], self.config.mode),
            symbol=self.symbol,
            position=position,
            pending_orders=self.exchange.get_pending_orders(self.symbol),
            equity_usdt=self.exchange.get_equity(),
            realized_pnl=self.exchange.get_realized_pnl(),
            total_trades=self._total_trades,
            last_bar_ts=self._get_last_bar_ts(),
            last_signal_ts=self._last_signal_ts,
            incremental_state_json=incremental_json,
            metadata={
                "bars_processed": self._bars_processed,
                "total_signals": self._total_signals,
                "warmup_complete": self._warmup_complete,
            },
        )

    def restore_state(self, state: EngineState) -> None:
        """
        Restore engine state from persistence.

        Args:
            state: Previously saved engine state
        """
        self._total_trades = state.total_trades
        self._last_signal_ts = state.last_signal_ts
        self._bars_processed = state.metadata.get("bars_processed", 0)
        self._total_signals = state.metadata.get("total_signals", 0)
        self._warmup_complete = state.metadata.get("warmup_complete", False)

        # Restore position via exchange adapter if it supports it
        if state.position is not None:
            restore_fn = getattr(self.exchange, 'restore_position', None)
            if restore_fn is not None:
                restore_fn(state.position)
                self.logger.info(
                    f"Position restored: {state.position.side} {state.position.symbol} "
                    f"size={state.position.size_usdt:.2f} entry={state.position.entry_price:.2f}"
                )
            else:
                self.logger.warning(
                    f"Exchange adapter does not support restore_position(). "
                    f"Persisted position ({state.position.side} {state.position.symbol}) "
                    f"will need to be reconciled from exchange state."
                )

        # Restore incremental state if persisted
        if state.incremental_state_json and self._incremental_state is not None:
            try:
                import json as _json
                from src.structures import MultiTFIncrementalState
                if hasattr(self._incremental_state, 'from_json'):
                    parsed_data: dict = _json.loads(state.incremental_state_json)
                    self._incremental_state = MultiTFIncrementalState.from_json(
                        parsed_data
                    )
            except Exception as e:
                self.logger.warning(f"Failed to restore incremental state: {e}")

        self.logger.info(
            f"State restored: {state.engine_id} "
            f"trades={state.total_trades} equity={state.equity_usdt:.2f}"
        )

    # =========================================================================
    # Private Methods
    # =========================================================================

    def _get_last_bar_ts(self) -> datetime | None:
        """Get timestamp of the last processed bar, or None if unavailable."""
        try:
            return self.data.get_candle(self._current_bar_index).ts_close
        except (IndexError, RuntimeError, AttributeError):
            return None

    def _is_ready(self) -> bool:
        """Check if engine is ready for trading (warmup complete)."""
        if self._warmup_complete:
            return True

        # Check data provider readiness
        if not self.data.is_ready():
            # G5.8: Transition to WARMING_UP if not already
            if self._phase == EnginePhase.CREATED:
                self._transition_phase(EnginePhase.WARMING_UP)
            return False

        self._warmup_complete = True
        # G5.8: Transition to READY phase
        self._transition_phase(EnginePhase.READY)
        self.logger.debug(f"Warmup complete at bar {self._current_bar_index}")
        return True

    def _update_high_tf_med_tf_indices(self, candle: Candle) -> None:
        """
        Update high_tf/med_tf forward-fill indices based on current candle.

        Delegates to shared TFIndexManager (src/engine/timeframe/) for backtest,
        and uses timestamp-based tracking for live mode.

        Also updates high_tf/med_tf incremental state when their bars close.
        """
        # Skip if no high_tf/med_tf feeds (single-TF mode)
        if self._high_tf_feed is None and self._med_tf_feed is None:
            # For live mode, check if multi_tf_mode is active via LiveDataProvider
            from .adapters.live import LiveDataProvider
            if isinstance(self._data_provider, LiveDataProvider) and self._data_provider.multi_tf_mode:
                self._update_live_tf_indices(candle)
            return

        if self.is_backtest:
            # Backtest mode: use FeedStore-based TFIndexManager
            low_tf_feed = getattr(self._data_provider, '_feed_store', None)
            if low_tf_feed is None:
                return

            # Lazy-initialize TFIndexManager on first use
            if self._tf_index_manager is None:
                from .timeframe import TFIndexManager
                self._tf_index_manager = TFIndexManager(
                    low_tf_feed=low_tf_feed,
                    med_tf_feed=self._med_tf_feed,
                    high_tf_feed=self._high_tf_feed,
                    exec_role=self._tf_mapping.get("exec", "low_tf"),
                )

            # Update indices via shared manager (single source of truth)
            update = self._tf_index_manager.update_indices(candle.ts_close)

            # Update med_tf incremental state when med_tf bar closes (for structures)
            if update.med_tf_changed:
                self._update_med_tf_incremental_state()

            # Update high_tf incremental state when high_tf bar closes (for structures)
            if update.high_tf_changed:
                self._update_high_tf_incremental_state()
        else:
            # Live mode: use buffer-length-based index tracking
            self._update_live_tf_indices(candle)

    def _update_live_tf_indices(self, candle: Candle) -> None:
        """
        Update TF indices for live mode using buffer lengths.

        In live mode, each TF buffer is maintained by LiveDataProvider.
        The current index for each TF is simply len(buffer) - 1.
        We detect bar closes by comparing buffer lengths between calls.
        """
        from .adapters.live import LiveDataProvider

        if not isinstance(self._data_provider, LiveDataProvider):
            return

        provider = self._data_provider

        # Initialize tracking state on first call (attrs pre-initialized to 0 in __init__)
        if self._prev_med_tf_len == 0 and len(provider.med_tf_buffer) > 0:
            self._prev_med_tf_len = len(provider.med_tf_buffer)
            self._prev_high_tf_len = len(provider.high_tf_buffer)
            self._live_med_tf_idx = max(0, self._prev_med_tf_len - 1)
            self._live_high_tf_idx = max(0, self._prev_high_tf_len - 1)

        # Update med_tf index from buffer length
        med_tf_len = len(provider.med_tf_buffer)
        if med_tf_len > 0:
            new_med_idx = med_tf_len - 1
            med_tf_changed = med_tf_len > self._prev_med_tf_len
            self._prev_med_tf_len = med_tf_len
            self._live_med_tf_idx = new_med_idx

            if med_tf_changed:
                self._update_med_tf_incremental_state()

        # Update high_tf index from buffer length
        high_tf_len = len(provider.high_tf_buffer)
        if high_tf_len > 0:
            new_high_idx = high_tf_len - 1
            high_tf_changed = high_tf_len > self._prev_high_tf_len
            self._prev_high_tf_len = high_tf_len
            self._live_high_tf_idx = new_high_idx

            if high_tf_changed:
                self._update_high_tf_incremental_state()

    def _update_med_tf_incremental_state(self) -> None:
        """Update med_tf incremental state when med_tf bar closes."""
        import numpy as np
        from src.structures import BarData

        if self._incremental_state is None:
            return

        med_tf = self._tf_mapping.get("med_tf")
        if not med_tf or med_tf not in self._incremental_state.med_tf:
            return

        med_tf_feed = self._med_tf_feed
        if med_tf_feed is None:
            return

        med_tf_idx = self._current_med_tf_idx

        # Build med_tf BarData
        med_tf_indicator_values: dict[str, float] = {}
        for key in med_tf_feed.indicators.keys():
            val = med_tf_feed.indicators[key][med_tf_idx]
            if not np.isnan(val):
                med_tf_indicator_values[key] = float(val)

        med_tf_bar_data = BarData(
            idx=med_tf_idx,
            open=float(med_tf_feed.open[med_tf_idx]),
            high=float(med_tf_feed.high[med_tf_idx]),
            low=float(med_tf_feed.low[med_tf_idx]),
            close=float(med_tf_feed.close[med_tf_idx]),
            volume=float(med_tf_feed.volume[med_tf_idx]),
            indicators=med_tf_indicator_values,
        )

        self._incremental_state.update_med_tf(med_tf, med_tf_bar_data)

    def _update_high_tf_incremental_state(self) -> None:
        """Update high_tf incremental state when high_tf bar closes."""
        import numpy as np
        from src.structures import BarData

        if self._incremental_state is None:
            return

        high_tf = self._tf_mapping.get("high_tf")
        if not high_tf or high_tf not in self._incremental_state.high_tf:
            return

        high_tf_feed = self._high_tf_feed
        if high_tf_feed is None:
            return

        high_tf_idx = self._current_high_tf_idx

        # Build high_tf BarData
        high_tf_indicator_values: dict[str, float] = {}
        for key in high_tf_feed.indicators.keys():
            val = high_tf_feed.indicators[key][high_tf_idx]
            if not np.isnan(val):
                high_tf_indicator_values[key] = float(val)

        high_tf_bar_data = BarData(
            idx=high_tf_idx,
            open=float(high_tf_feed.open[high_tf_idx]),
            high=float(high_tf_feed.high[high_tf_idx]),
            low=float(high_tf_feed.low[high_tf_idx]),
            close=float(high_tf_feed.close[high_tf_idx]),
            volume=float(high_tf_feed.volume[high_tf_idx]),
            indicators=high_tf_indicator_values,
        )

        self._incremental_state.update_high_tf(high_tf, high_tf_bar_data)

    def _update_incremental_state(self, bar_index: int, candle: Candle) -> None:
        """Update incremental structure state with new bar data."""
        import numpy as np
        from src.structures import BarData

        # Build indicators dict from feed store if available
        indicators: dict[str, float] = {}
        from .adapters.backtest import BacktestDataProvider
        if isinstance(self._data_provider, BacktestDataProvider):
            feed_store = self._data_provider._feed_store
            if feed_store is not None:
                # Copy indicator values for this bar
                for name, arr in feed_store.indicators.items():
                    if bar_index < len(arr):
                        indicators[name] = float(arr[bar_index])
        else:
            # Live mode: get latest indicator values from exec indicator cache
            from .adapters.live import LiveDataProvider
            if isinstance(self._data_provider, LiveDataProvider):
                cache = self._data_provider._exec_indicators
                if cache is not None:
                    with cache._lock:
                        for name, arr in cache._indicators.items():
                            if len(arr) > 0 and not np.isnan(arr[-1]):
                                indicators[name] = float(arr[-1])

        bar_data = BarData(
            idx=bar_index,
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            volume=candle.volume,
            indicators=indicators,
        )

        # MultiTFIncrementalState uses update_exec() for exec timeframe updates
        assert self._incremental_state is not None
        self._incremental_state.update_exec(bar_data)

        # Post-structure update: wire anchored VWAP to swing versions
        self._update_anchored_vwap(bar_index, candle)

    def _init_anchored_vwap_cache(self) -> dict[str, Any]:
        """Lazy-init anchored VWAP indicators that need swing structure wiring.

        Scans the play's feature registry for anchored_vwap features and creates
        IncrementalAnchoredVWAP instances. Also identifies the swing structure
        key on the exec TF to extract version counters from.

        Returns:
            Dict with 'indicators' (name -> IncrementalAnchoredVWAP) and
            'swing_key' (str or None).
        """
        from src.indicators.incremental.volume import IncrementalAnchoredVWAP

        cache: dict[str, Any] = {"indicators": {}, "swing_key": None}

        if self._feature_registry is None:
            return cache

        # Find anchored_vwap features
        for feature in self._feature_registry.all_features():
            if feature.indicator_type == "anchored_vwap":
                anchor_source = feature.params.get("anchor_source", "swing_any")
                avwap = IncrementalAnchoredVWAP(anchor_source=anchor_source)
                cache["indicators"][feature.id] = avwap

        if not cache["indicators"]:
            return cache

        # Find the first swing structure on exec TF
        if self._incremental_state is not None:
            for key in self._incremental_state.exec.list_structures():
                detector = self._incremental_state.exec.structures[key]
                if getattr(detector, "_type", "") == "swing":
                    cache["swing_key"] = key
                    break

        if cache["swing_key"] is None:
            avwap_names = list(cache["indicators"].keys())
            self.logger.warning(
                f"anchored_vwap features {avwap_names} declared but no swing structure "
                f"found on exec TF. Anchored VWAP will never reset and degrades to "
                f"cumulative VWAP. Add a swing structure to exec to enable anchor resets."
            )

        return cache

    def _update_anchored_vwap(self, bar_index: int, candle: Candle) -> None:
        """Update anchored VWAP indicators with swing structure versions.

        Called AFTER structures are updated so swing versions are fresh.
        Writes corrected values back to FeedStore (backtest) or
        LiveIndicatorCache (live), overwriting any stale batch-computed values.
        """
        import numpy as np

        # Lazy init
        if self._anchored_vwap_cache is None:
            self._anchored_vwap_cache = self._init_anchored_vwap_cache()

        indicators: dict = self._anchored_vwap_cache["indicators"]
        if not indicators:
            return

        swing_key: str | None = self._anchored_vwap_cache["swing_key"]

        # Extract swing versions from exec structure state
        swing_kwargs: dict[str, Any] = {}
        if swing_key is not None and self._incremental_state is not None:
            try:
                exec_state = self._incremental_state.exec
                swing_kwargs["swing_high_version"] = exec_state.get_value(swing_key, "high_version")
                swing_kwargs["swing_low_version"] = exec_state.get_value(swing_key, "low_version")
                swing_kwargs["swing_pair_version"] = exec_state.get_value(swing_key, "pair_version")
                swing_kwargs["swing_pair_direction"] = exec_state.get_value(swing_key, "pair_direction")
            except KeyError:
                pass  # Swing structure not ready yet

        # Update each anchored VWAP and write back (multi-output: value + bars_since_anchor)
        for name, avwap in indicators.items():
            avwap.update(
                high=candle.high,
                low=candle.low,
                close=candle.close,
                volume=candle.volume,
                **swing_kwargs,
            )
            # Multi-output expanded keys: {name}_value, {name}_bars_since_anchor
            outputs = {
                f"{name}_value": avwap.value,
                f"{name}_bars_since_anchor": float(avwap.bars_since_anchor),
            }

            # Write corrected values back to data store
            from .adapters.backtest import BacktestDataProvider
            if isinstance(self._data_provider, BacktestDataProvider):
                feed_store = self._data_provider._feed_store
                if feed_store is not None:
                    for key, val in outputs.items():
                        if key in feed_store.indicators:
                            if bar_index < len(feed_store.indicators[key]):
                                feed_store.indicators[key][bar_index] = val
            else:
                from .adapters.live import LiveDataProvider
                if isinstance(self._data_provider, LiveDataProvider):
                    cache = self._data_provider._exec_indicators
                    if cache is not None:
                        with cache._lock:
                            for key, val in outputs.items():
                                if key in cache._indicators and len(cache._indicators[key]) > 0:
                                    cache._indicators[key][-1] = val

    def _evaluate_rules(
        self,
        bar_index: int,
        candle: Candle,
        position: Position | None,
    ) -> "Signal | None":
        """
        Evaluate entry/exit rules and generate signal.

        When 1m quote feed is available, uses 1m sub-loop for granular
        evaluation. Otherwise falls back to single evaluation at exec close.

        Returns:
            Signal if rule triggered, None otherwise
        """
        # Use 1m sub-loop when quote_feed is available (matches old engine behavior)
        if self._quote_feed is not None:
            signal, signal_ts = self._evaluate_with_1m_subloop(bar_index, candle, position)
            # Note: signal_ts is available for logging but signal execution
            # happens at bar close (order submitted for next bar fill)
            return signal

        # Fallback: single evaluation at exec bar close
        return self._evaluate_rules_single(bar_index, candle, position)

    def _build_snapshot_view(self, bar_index: int, candle: Candle) -> "RuntimeSnapshotView | None":
        """
        Build RuntimeSnapshotView for rule evaluation.

        This creates a snapshot that PlaySignalEvaluator can use to
        evaluate rules. In backtest mode, this wraps the FeedStore.

        Args:
            bar_index: Current bar index
            candle: Current candle data

        Returns:
            RuntimeSnapshotView for rule evaluation
        """
        # In backtest mode, we need to build a proper RuntimeSnapshotView
        # For now, this requires the BacktestDataProvider to have FeedStore set
        from .adapters.backtest import BacktestDataProvider

        if isinstance(self._data_provider, BacktestDataProvider):
            if self._data_provider._feed_store is None:
                return None

            # Import snapshot view builder
            from ..backtest.runtime.snapshot_view import RuntimeSnapshotView
            from ..backtest.runtime.feed_store import MultiTFFeedStore

            feed_store = self._data_provider._feed_store

            # Create MultiTFFeedStore with 3-feed structure
            feeds = MultiTFFeedStore(
                low_tf_feed=feed_store,
                high_tf_feed=self._high_tf_feed,
                med_tf_feed=self._med_tf_feed,
                tf_mapping=self._tf_mapping,
                exec_role=self._tf_mapping.get("exec", "low_tf"),
            )

            # Use dynamically tracked high_tf/med_tf indices (updated by _update_high_tf_med_tf_indices)
            # These are forward-fill indices - they hold the last high_tf/med_tf bar that closed
            # IMPORTANT: In single-TF mode where high_tf_feed IS exec_feed, pass None
            # so RuntimeSnapshotView uses exec_ctx instead of creating a separate context
            high_tf_idx = None
            med_tf_idx = None
            if self._high_tf_feed is not None and self._high_tf_feed is not feed_store:
                high_tf_idx = self._current_high_tf_idx
            if self._med_tf_feed is not None and self._med_tf_feed is not feed_store:
                med_tf_idx = self._current_med_tf_idx

            # Get prev_last_price for crossover operators
            prev_last_price = None
            if bar_index > 0:
                try:
                    prev_candle = self.data.get_candle(bar_index - 1)
                    prev_last_price = prev_candle.close
                except IndexError as e:
                    self.logger.warning(f"Could not get prev candle at {bar_index-1}: {e}")
                    prev_last_price = candle.close  # Fallback to current close

            # Create snapshot view with correct parameters
            snapshot = RuntimeSnapshotView(
                feeds=feeds,
                exec_idx=bar_index,
                high_tf_idx=high_tf_idx,
                med_tf_idx=med_tf_idx,
                exchange=getattr(self._exchange, '_sim_exchange', None),
                mark_price=candle.close,
                mark_price_source="approx_from_ohlcv",
                history_config=None,
                history_ready=True,
                incremental_state=self._incremental_state,
                feature_registry=self._feature_registry,
                last_price=candle.close,
                prev_last_price=prev_last_price,
            )
            return snapshot

        # Live mode: build from LiveDataProvider buffers
        from .adapters.live import LiveDataProvider

        if isinstance(self._data_provider, LiveDataProvider):
            from ..backtest.runtime.snapshot_view import RuntimeSnapshotView
            from ..backtest.runtime.feed_store import FeedStore, MultiTFFeedStore

            provider = self._data_provider

            # Resolve real-time prices + market data from ticker stream (WebSocket)
            # Falls back to candle.close if ticker unavailable or stale
            live_last_price = candle.close
            live_mark_price = candle.close
            mark_source = "live_candle_close"
            live_funding_rate: float | None = None
            live_open_interest: float | None = None
            if provider._realtime_state is not None:
                ticker = provider._realtime_state.get_ticker(provider._symbol)
                if ticker is not None and not provider._realtime_state.is_ticker_stale(provider._symbol):
                    if ticker.last_price > 0:
                        live_last_price = ticker.last_price
                    if ticker.mark_price > 0:
                        live_mark_price = ticker.mark_price
                        mark_source = "live_ticker"
                    live_funding_rate = ticker.funding_rate
                    live_open_interest = ticker.open_interest

            # Build FeedStore from live buffers for each TF
            # OI and funding are injected from ticker into each feed
            low_tf_feed = self._build_live_feed_store(
                provider.low_tf_buffer,
                provider._low_tf_indicators,
                provider._tf_mapping["low_tf"],
                provider.symbol,
                funding_rate=live_funding_rate,
                open_interest=live_open_interest,
            )
            if low_tf_feed is None:
                return None

            med_tf_feed = None
            if provider._multi_tf_mode and provider._tf_mapping["med_tf"] != provider._tf_mapping["low_tf"]:
                med_tf_feed = self._build_live_feed_store(
                    provider.med_tf_buffer,
                    provider._med_tf_indicators,
                    provider._tf_mapping["med_tf"],
                    provider.symbol,
                    funding_rate=live_funding_rate,
                    open_interest=live_open_interest,
                )

            high_tf_feed = None
            if provider._multi_tf_mode and provider._tf_mapping["high_tf"] != provider._tf_mapping["med_tf"]:
                high_tf_feed = self._build_live_feed_store(
                    provider.high_tf_buffer,
                    provider._high_tf_indicators,
                    provider._tf_mapping["high_tf"],
                    provider.symbol,
                    funding_rate=live_funding_rate,
                    open_interest=live_open_interest,
                )

            feeds = MultiTFFeedStore(
                low_tf_feed=low_tf_feed,
                med_tf_feed=med_tf_feed,
                high_tf_feed=high_tf_feed,
                tf_mapping=provider._tf_mapping,
                exec_role=provider._tf_mapping.get("exec", "low_tf"),
            )

            # Use exec buffer length - 1 as exec_idx (latest bar)
            exec_buffer = provider._exec_buffer
            exec_idx = len(exec_buffer) - 1 if exec_buffer else 0

            # Determine high_tf/med_tf indices
            high_tf_idx = None
            med_tf_idx = None
            if high_tf_feed is not None:
                high_tf_idx = self._current_high_tf_idx
            if med_tf_feed is not None:
                med_tf_idx = self._current_med_tf_idx

            # Get prev_last_price for crossover operators
            prev_last_price = None
            if exec_idx > 0:
                try:
                    prev_candle = self.data.get_candle(exec_idx - 1)
                    prev_last_price = prev_candle.close
                except (IndexError, RuntimeError):
                    prev_last_price = candle.close

            # Use exec feed as quote_feed fallback for last_price lookback
            # In live mode there's no 1m quote_feed, so window operators
            # referencing last_price with offset > 1 use exec TF close prices
            exec_feed_for_quote = feeds.exec_feed

            snapshot = RuntimeSnapshotView(
                feeds=feeds,
                exec_idx=exec_idx,
                high_tf_idx=high_tf_idx,
                med_tf_idx=med_tf_idx,
                exchange=self._build_live_exchange_state(),
                mark_price=live_mark_price,
                mark_price_source=mark_source,
                history_config=None,
                history_ready=True,
                incremental_state=self._incremental_state,
                feature_registry=self._feature_registry,
                last_price=live_last_price,
                prev_last_price=prev_last_price,
                quote_feed=exec_feed_for_quote,
                quote_idx=exec_idx,
            )
            return snapshot

        return None

    def _build_live_feed_store(
        self,
        buffer: list[Candle],
        indicator_cache: Any | None,
        tf_str: str,
        symbol: str,
        *,
        funding_rate: float | None = None,
        open_interest: float | None = None,
    ) -> "FeedStore | None":
        """
        Build a FeedStore from a live candle buffer and indicator cache.

        Converts LiveDataProvider's list[Candle] + LiveIndicatorCache arrays
        into a FeedStore that RuntimeSnapshotView can consume.

        Args:
            buffer: Candle buffer from LiveDataProvider
            indicator_cache: LiveIndicatorCache for this TF (may be None)
            tf_str: Timeframe string (e.g. "15m", "1h")
            symbol: Trading symbol
            funding_rate: Current funding rate from ticker (forward-filled into array)
            open_interest: Current open interest from ticker (forward-filled into array)

        Returns:
            FeedStore or None if buffer is empty
        """
        import numpy as np
        from ..backtest.runtime.feed_store import FeedStore

        if not buffer:
            return None

        n = len(buffer)

        # Build OHLCV arrays from candle buffer
        ts_open = np.array([c.ts_open for c in buffer], dtype="datetime64[ms]")
        ts_close = np.array([c.ts_close for c in buffer], dtype="datetime64[ms]")
        open_arr = np.array([c.open for c in buffer], dtype=np.float64)
        high_arr = np.array([c.high for c in buffer], dtype=np.float64)
        low_arr = np.array([c.low for c in buffer], dtype=np.float64)
        close_arr = np.array([c.close for c in buffer], dtype=np.float64)
        volume_arr = np.array([c.volume for c in buffer], dtype=np.float64)

        # Build indicator arrays from cache
        indicators: dict[str, np.ndarray] = {}
        if indicator_cache is not None:
            with indicator_cache._lock:
                for name, arr in indicator_cache._indicators.items():
                    # Align indicator array length to buffer length
                    if len(arr) == n:
                        indicators[name] = arr.copy()
                    elif len(arr) > n:
                        indicators[name] = arr[-n:].copy()
                    else:
                        # Pad front with NaN if indicator has fewer values
                        padded = np.full(n, np.nan, dtype=np.float64)
                        padded[n - len(arr):] = arr
                        indicators[name] = padded

        # Build ts_close_ms_to_idx mapping for TF index lookups
        ts_close_ms_to_idx: dict[int, int] = {}
        close_ts_set: set = set()
        for i, c in enumerate(buffer):
            ts_ms = int(c.ts_close.timestamp() * 1000)
            ts_close_ms_to_idx[ts_ms] = i
            close_ts_set.add(c.ts_close)

        # Build market data arrays (forward-filled from latest ticker value)
        funding_arr = None
        if funding_rate is not None:
            funding_arr = np.full(n, funding_rate, dtype=np.float64)

        oi_arr = None
        if open_interest is not None and open_interest > 0:
            oi_arr = np.full(n, open_interest, dtype=np.float64)

        return FeedStore(
            tf=tf_str,
            symbol=symbol,
            ts_open=ts_open,
            ts_close=ts_close,
            open=open_arr,
            high=high_arr,
            low=low_arr,
            close=close_arr,
            volume=volume_arr,
            indicators=indicators,
            ts_close_ms_to_idx=ts_close_ms_to_idx,
            close_ts_set=close_ts_set,
            length=n,
            funding_rate=funding_arr,
            open_interest=oi_arr,
        )

    def _build_live_exchange_state(self):
        """Build a frozen snapshot of live exchange state for RuntimeSnapshotView."""
        from .adapters.live_state_adapter import LiveExchangeStateAdapter
        return LiveExchangeStateAdapter.from_live_exchange(self._exchange, self.symbol)

    def _size_position(self, signal: "Signal") -> float:
        """
        Apply unified risk sizing to signal.

        Uses the shared SizingModel for position sizing.

        The sizing model supports:
            - percent_equity: Bybit margin model (margin * leverage)
            - risk_based: Size to lose risk_pct if stopped out
            - fixed_notional: Use requested size (capped by leverage)

        Returns:
            Position size in USDT
        """
        # Get current equity from exchange
        equity = self.exchange.get_equity()

        # Sync sizing model equity with exchange
        self._sizing_model.update_equity(equity)

        # Extract stop_loss from signal metadata for risk_based sizing
        stop_loss = None
        entry_price = None
        if signal.metadata:
            stop_loss = signal.metadata.get("stop_loss")
            entry_price = signal.metadata.get("entry_price")

        # If no entry_price in metadata, try to get from current candle
        if entry_price is None:
            try:
                candle = self.data.get_candle(self._current_bar_index)
                entry_price = candle.close
            except (IndexError, AttributeError):
                pass

        # Use unified sizing model
        result = self._sizing_model.size_order(
            equity=equity,
            entry_price=entry_price,
            stop_loss=stop_loss,
            requested_size=signal.size_usdt if signal.size_usdt else None,
        )

        self.logger.debug(
            f"Sizing: {result.method} -> {result.size_usdt:.2f} USDT ({result.details})"
        )

        return result.size_usdt

    def _get_risk_policy(self):
        """
        Get or create the risk policy instance.

        Lazy initialization to avoid import at module level.

        Returns:
            RiskPolicy instance (NoneRiskPolicy or RulesRiskPolicy)
        """
        if self._risk_policy is None:
            from ..backtest.risk_policy import create_risk_policy
            from ..backtest.system_config import RiskProfileConfig

            # Create a RiskProfileConfig from PlayEngineConfig
            # This bridges the config models
            risk_profile = RiskProfileConfig(
                initial_equity=self.config.initial_equity,
                sizing_model=self.config.sizing_model,
                risk_per_trade_pct=self.config.risk_per_trade_pct,
                max_leverage=self.config.max_leverage,
                min_trade_usdt=self.config.min_trade_usdt,
                taker_fee_rate=self.config.taker_fee_rate,
            )

            self._risk_policy = create_risk_policy(
                risk_mode=self.config.risk_mode,
                risk_profile=risk_profile,
            )

        return self._risk_policy

    def _check_risk_policy(self, signal: "Signal"):
        """
        Check if a signal passes risk policy rules.

        Uses current exchange state for accurate risk evaluation.

        Args:
            signal: Trading signal to check

        Returns:
            RiskDecision with allowed/denied status and reason
        """
        policy = self._get_risk_policy()

        # Get current portfolio state from exchange
        equity = self.exchange.get_equity()
        balance = self.exchange.get_balance()
        position = self.exchange.get_position(self.symbol)

        # Calculate exposure and unrealized PnL
        total_exposure = position.size_usdt if position else 0.0
        unrealized_pnl = 0.0
        position_count = 0

        if position:
            position_count = 1
            # Try to get unrealized PnL if exchange supports it
            get_upnl_fn = getattr(self.exchange, 'get_unrealized_pnl', None)
            if get_upnl_fn is not None:
                unrealized_pnl = get_upnl_fn(self.symbol)

        # Check signal against policy
        decision = policy.check(
            signal=signal,
            equity=equity,
            available_balance=balance,
            total_exposure=total_exposure,
            unrealized_pnl=unrealized_pnl,
            position_count=position_count,
        )

        return decision

    def _check_limit_expiry(self, current_bar: int) -> None:
        """Cancel unfilled limit orders after expire_after_bars exec bars."""
        expire_bars = self.play.expire_after_bars
        if expire_bars <= 0:
            return

        remaining: list[tuple[str, int]] = []
        for order_id, submit_bar in self._pending_limit_orders:
            if current_bar - submit_bar >= expire_bars:
                if self.exchange.cancel_order(order_id):
                    self.logger.info(f"Expired limit order {order_id} after {expire_bars} bars")
            else:
                remaining.append((order_id, submit_bar))
        self._pending_limit_orders = remaining

    def _remove_filled_limit_order(self, order_id: str) -> None:
        """Remove a filled limit order from expiry tracking."""
        self._pending_limit_orders = [
            (oid, bar) for oid, bar in self._pending_limit_orders if oid != order_id
        ]

    def _save_state(self) -> None:
        """Save current state to store."""
        state = self.get_state()
        self.state_store.save_state(self.engine_id, state)

    def _validate_sl_vs_liquidation(
        self,
        signal: "Signal",
        stop_loss: float,
    ) -> "StopLiqValidationResult":
        """
        Validate that stop-loss triggers before liquidation price.

        High leverage positions can get liquidated before SL fires if the
        stop distance exceeds the liquidation distance.

        Args:
            signal: Trading signal with direction
            stop_loss: Stop-loss price

        Returns:
            StopLiqValidationResult with validation status
        """
        from ..backtest.simulated_risk_manager import (
            validate_stop_vs_liquidation,
            StopLiqValidationResult,
        )

        # Get entry price approximation (current candle close)
        entry_price = None
        try:
            candle = self.data.get_candle(self._current_bar_index)
            entry_price = candle.close
        except (IndexError, AttributeError):
            pass

        # Also check signal metadata for entry_price
        if entry_price is None and signal.metadata:
            entry_price = signal.metadata.get("entry_price")

        if entry_price is None or entry_price <= 0:
            # Can't validate without entry price, allow entry
            return StopLiqValidationResult(valid=True)

        # Determine direction
        direction = 1 if signal.direction.upper() == "LONG" else -1

        assert self.config.maintenance_margin_rate is not None
        return validate_stop_vs_liquidation(
            entry_price=entry_price,
            stop_price=stop_loss,
            direction=direction,
            leverage=self.config.max_leverage,
            mmr=self.config.maintenance_margin_rate,
        )

    def _evaluate_with_1m_subloop(
        self,
        bar_index: int,
        candle: Candle,
        position: "Position | None",
    ) -> tuple["Signal | None", datetime | None]:
        """
        Evaluate rules with 1m granularity within the exec_tf bar.

        Delegates to shared SubLoopEvaluator for the actual iteration.
        This ensures identical 1m sub-loop behavior across all engines.

        Args:
            bar_index: Current exec bar index
            candle: Current exec candle data
            position: Current position (if any)

        Returns:
            Tuple of (Signal or None, signal_ts or None)
        """
        # Create evaluator (could cache, but overhead is minimal)
        evaluator = SubLoopEvaluator(
            quote_feed=self._quote_feed,
            exec_tf=self.timeframe,
            logger=self.logger,
        )

        # Create context for this evaluation
        context = _PlayEngineSubLoopContext(
            engine=self,
            bar_index=bar_index,
            candle=candle,
            position=position,
        )

        # Delegate to shared evaluator
        result = evaluator.evaluate(
            exec_idx=bar_index,
            context=context,
            exec_close=candle.close,
            exec_ts_open=candle.ts_open,
            exec_ts_close=candle.ts_close,
        )

        return result.signal, result.signal_ts

    def _evaluate_rules_single(
        self,
        bar_index: int,
        candle: Candle,
        position: "Position | None",
    ) -> "Signal | None":
        """
        Evaluate rules at a single point (exec bar close).

        This is the fallback when no 1m quote feed is available.
        """
        from ..core.risk_manager import Signal
        from ..backtest.execution_validation import (
            PlaySignalEvaluator,
            SignalDecision,
        )

        # Lazy initialize signal evaluator
        if self._signal_evaluator is None:
            try:
                self._signal_evaluator = PlaySignalEvaluator(self.play)
                # Wire setup expressions into evaluator cache
                if self.play.setups:
                    self._signal_evaluator._blocks_executor._evaluator._setup_expr_cache = dict(self.play.setups)
            except ValueError as e:
                self.logger.error(f"Failed to create signal evaluator: {e}")
                return None

        # Build snapshot view for evaluation
        snapshot = self._build_snapshot_view(bar_index, candle)
        if snapshot is None:
            return None

        # Call audit callback if registered
        if self._on_snapshot is not None:
            self._on_snapshot(snapshot, bar_index, self._current_high_tf_idx, self._current_med_tf_idx)

        # Determine position state
        has_position = position is not None
        position_side = position.side.lower() if position else None

        # Evaluate using PlaySignalEvaluator
        result = self._signal_evaluator.evaluate(snapshot, has_position, position_side)

        if is_debug_enabled() and not self.is_backtest:
            self.logger.debug(
                f"[DBG] Rule evaluation: decision={result.decision.value} "
                f"has_pos={has_position} pos_side={position_side} "
                f"sl={result.stop_loss_price} tp={result.take_profit_price}"
            )

        # 7.4: Dump indicator snapshot at signal bars (backtest debug)
        if is_debug_enabled() and self.is_backtest and result.decision != SignalDecision.NO_ACTION:
            if snapshot is not None:
                snapshot_data: dict[str, Any] = {
                    "decision": result.decision.value,
                    "close": candle.close,
                }
                if result.stop_loss_price is not None:
                    snapshot_data["sl"] = result.stop_loss_price
                if result.take_profit_price is not None:
                    snapshot_data["tp"] = result.take_profit_price
                # Add indicator values from snapshot
                try:
                    for key in snapshot.available_indicators:
                        val = snapshot.indicator(key)
                        if val is not None:
                            snapshot_data[key] = val
                except Exception:
                    pass  # Don't fail on snapshot read errors
                debug_snapshot(self._play_hash, bar_index, snapshot_data)

        # Convert evaluation result to Signal
        return self._result_to_signal(result, position)

    def _result_to_signal(
        self,
        result: "EvaluationResult",
        position: "Position | None",
    ) -> "Signal | None":
        """Convert EvaluationResult to Signal."""
        from ..core.risk_manager import Signal
        from ..backtest.execution_validation import SignalDecision

        if result.decision == SignalDecision.NO_ACTION:
            return None

        elif result.decision == SignalDecision.ENTRY_LONG:
            metadata = {
                "stop_loss": result.stop_loss_price,
                "take_profit": result.take_profit_price,
            }
            if result.resolved_metadata:
                metadata.update(result.resolved_metadata)
            strategy = self.play.name or ""
            return Signal(
                symbol=self.symbol,
                direction="LONG",
                size_usdt=0.0,  # Sized by execute_signal
                strategy=strategy,
                confidence=1.0,
                metadata=metadata,
            )

        elif result.decision == SignalDecision.ENTRY_SHORT:
            metadata = {
                "stop_loss": result.stop_loss_price,
                "take_profit": result.take_profit_price,
            }
            if result.resolved_metadata:
                metadata.update(result.resolved_metadata)
            strategy = self.play.name or ""
            return Signal(
                symbol=self.symbol,
                direction="SHORT",
                size_usdt=0.0,
                strategy=strategy,
                confidence=1.0,
                metadata=metadata,
            )

        elif result.decision == SignalDecision.EXIT:
            metadata = {}
            if result.exit_percent != 100.0:
                metadata["exit_percent"] = result.exit_percent
            if result.resolved_metadata:
                metadata.update(result.resolved_metadata)
            strategy = self.play.name or ""
            return Signal(
                symbol=self.symbol,
                direction="FLAT",
                size_usdt=position.size_usdt if position else 0.0,
                strategy=strategy,
                confidence=1.0,
                metadata=metadata if metadata else None,
            )

        return None

    def _build_snapshot_view_1m(
        self,
        bar_index: int,
        candle: Candle,
        last_price: float,
        prev_last_price: float | None,
        quote_idx: int,
    ):
        """
        Build RuntimeSnapshotView for 1m sub-loop evaluation.

        This is similar to _build_snapshot_view but passes the 1m-specific
        prices and quote_idx for proper window operator support.

        Args:
            bar_index: Current exec bar index
            candle: Current exec candle data
            last_price: 1m close price for signal evaluation
            prev_last_price: Previous 1m close price for crossover operators
            quote_idx: Current 1m bar index in quote_feed

        Returns:
            RuntimeSnapshotView or None if not ready
        """
        from .adapters.backtest import BacktestDataProvider

        if isinstance(self._data_provider, BacktestDataProvider):
            if self._data_provider._feed_store is None:
                return None

            from ..backtest.runtime.snapshot_view import RuntimeSnapshotView
            from ..backtest.runtime.feed_store import MultiTFFeedStore

            feed_store = self._data_provider._feed_store

            # Create MultiTFFeedStore with 3-feed structure
            feeds = MultiTFFeedStore(
                low_tf_feed=feed_store,
                high_tf_feed=self._high_tf_feed,
                med_tf_feed=self._med_tf_feed,
                tf_mapping=self._tf_mapping,
                exec_role=self._tf_mapping.get("exec", "low_tf"),
            )

            # Use dynamically tracked high_tf/med_tf indices
            high_tf_idx = None
            med_tf_idx = None
            if self._high_tf_feed is not None and self._high_tf_feed is not feed_store:
                high_tf_idx = self._current_high_tf_idx
            if self._med_tf_feed is not None and self._med_tf_feed is not feed_store:
                med_tf_idx = self._current_med_tf_idx

            # Create snapshot view with 1m prices and quote_feed for window operators
            snapshot = RuntimeSnapshotView(
                feeds=feeds,
                exec_idx=bar_index,
                high_tf_idx=high_tf_idx,
                med_tf_idx=med_tf_idx,
                exchange=getattr(self._exchange, '_sim_exchange', None),
                mark_price=last_price,  # Use 1m close as mark_price
                mark_price_source="1m_quote",
                history_config=None,
                history_ready=True,
                incremental_state=self._incremental_state,
                feature_registry=self._feature_registry,
                last_price=last_price,  # 1m close for signal evaluation
                prev_last_price=prev_last_price,  # For crossover operators
                quote_feed=self._quote_feed,  # For window operators
                quote_idx=quote_idx,  # Current 1m index
            )
            return snapshot

        # Live mode: build 1m snapshot from LiveDataProvider buffers
        from .adapters.live import LiveDataProvider

        if isinstance(self._data_provider, LiveDataProvider):
            from ..backtest.runtime.snapshot_view import RuntimeSnapshotView
            from ..backtest.runtime.feed_store import MultiTFFeedStore

            provider = self._data_provider

            # Build FeedStore from live buffers (same pattern as _build_snapshot_view)
            low_tf_feed = self._build_live_feed_store(
                provider.low_tf_buffer,
                provider._low_tf_indicators,
                provider._tf_mapping["low_tf"],
                provider.symbol,
            )
            if low_tf_feed is None:
                return None

            med_tf_feed = None
            if provider._multi_tf_mode and provider._tf_mapping["med_tf"] != provider._tf_mapping["low_tf"]:
                med_tf_feed = self._build_live_feed_store(
                    provider.med_tf_buffer,
                    provider._med_tf_indicators,
                    provider._tf_mapping["med_tf"],
                    provider.symbol,
                )

            high_tf_feed = None
            if provider._multi_tf_mode and provider._tf_mapping["high_tf"] != provider._tf_mapping["med_tf"]:
                high_tf_feed = self._build_live_feed_store(
                    provider.high_tf_buffer,
                    provider._high_tf_indicators,
                    provider._tf_mapping["high_tf"],
                    provider.symbol,
                )

            feeds = MultiTFFeedStore(
                low_tf_feed=low_tf_feed,
                med_tf_feed=med_tf_feed,
                high_tf_feed=high_tf_feed,
                tf_mapping=provider._tf_mapping,
                exec_role=provider._tf_mapping.get("exec", "low_tf"),
            )

            # Use exec buffer length - 1 as exec_idx (latest bar)
            exec_buffer = provider._exec_buffer
            exec_idx = len(exec_buffer) - 1 if exec_buffer else 0

            # Determine high_tf/med_tf indices
            high_tf_idx = None
            med_tf_idx = None
            if high_tf_feed is not None:
                high_tf_idx = self._current_high_tf_idx
            if med_tf_feed is not None:
                med_tf_idx = self._current_med_tf_idx

            # Build exec TF close array as quote_feed fallback for last_price lookback
            quote_feed = self._build_live_feed_store(
                provider._exec_buffer,
                provider._exec_indicators,
                provider._tf_mapping[provider._exec_role],
                provider.symbol,
            )

            snapshot = RuntimeSnapshotView(
                feeds=feeds,
                exec_idx=exec_idx,
                high_tf_idx=high_tf_idx,
                med_tf_idx=med_tf_idx,
                exchange=self._build_live_exchange_state(),
                mark_price=last_price,
                mark_price_source="1m_quote_live",
                history_config=None,
                history_ready=True,
                incremental_state=self._incremental_state,
                feature_registry=self._feature_registry,
                last_price=last_price,
                prev_last_price=prev_last_price,
                quote_feed=quote_feed,
                quote_idx=quote_idx,
            )
            return snapshot

        return None


class _PlayEngineSubLoopContext:
    """SubLoopContext implementation for PlayEngine.

    Provides the engine-specific snapshot building and signal evaluation
    for the shared SubLoopEvaluator.
    """

    def __init__(
        self,
        engine: PlayEngine,
        bar_index: int,
        candle: Candle,
        position: "Position | None",
    ):
        self._engine = engine
        self._bar_index = bar_index
        self._candle = candle
        self._position = position

        # Lazy initialize signal evaluator if needed
        if engine._signal_evaluator is None:
            from ..backtest.execution_validation import PlaySignalEvaluator
            try:
                engine._signal_evaluator = PlaySignalEvaluator(engine.play)
                # Wire setup expressions into evaluator cache
                if engine.play.setups:
                    engine._signal_evaluator._blocks_executor._evaluator._setup_expr_cache = dict(engine.play.setups)
            except ValueError as e:
                engine.logger.error(f"Failed to create signal evaluator: {e}")

    def build_snapshot_1m(
        self,
        exec_idx: int,
        price_1m: float,
        prev_price_1m: float | None,
        quote_idx: int,
    ) -> Any:
        """Build snapshot with 1m prices for signal evaluation."""
        snapshot = self._engine._build_snapshot_view_1m(
            bar_index=exec_idx,
            candle=self._candle,
            last_price=price_1m,
            prev_last_price=prev_price_1m,
            quote_idx=quote_idx,
        )
        # Call audit callback if registered
        if self._engine._on_snapshot is not None and snapshot is not None:
            self._engine._on_snapshot(
                snapshot, exec_idx,
                self._engine._current_high_tf_idx, self._engine._current_med_tf_idx
            )
        return snapshot

    def evaluate_signal(self, snapshot: Any) -> "Signal | None":
        """Evaluate rules and convert to Signal."""
        if self._engine._signal_evaluator is None:
            return None

        # Determine position state
        has_position = self._position is not None
        position_side = self._position.side.lower() if self._position else None

        # Evaluate using PlaySignalEvaluator
        result = self._engine._signal_evaluator.evaluate(
            snapshot, has_position, position_side
        )

        # 7.4: Dump indicator snapshot at signal bars (sub-loop path)
        from ..backtest.execution_validation import SignalDecision
        if is_debug_enabled() and self._engine.is_backtest and result.decision != SignalDecision.NO_ACTION:
            if snapshot is not None:
                snap_data: dict[str, Any] = {
                    "decision": result.decision.value,
                    "close": self._candle.close,
                }
                if result.stop_loss_price is not None:
                    snap_data["sl"] = result.stop_loss_price
                if result.take_profit_price is not None:
                    snap_data["tp"] = result.take_profit_price
                try:
                    for key in snapshot.available_indicators:
                        val = snapshot.indicator(key)
                        if val is not None:
                            snap_data[key] = val
                except Exception:
                    pass
                debug_snapshot(self._engine._play_hash, self._bar_index, snap_data)

        # Convert to Signal
        return self._engine._result_to_signal(result, self._position)

    def should_skip_entry(self) -> bool:
        """Check if entries are disabled and no position exists."""
        entries_disabled = getattr(self._engine._exchange, 'entries_disabled', False)
        return entries_disabled and self._position is None

    def build_fallback_snapshot(self, exec_idx: int, exec_close: float) -> Any:
        """Build snapshot for fallback evaluation."""
        snapshot = self._engine._build_snapshot_view(exec_idx, self._candle)
        # Call audit callback if registered
        if self._engine._on_snapshot is not None and snapshot is not None:
            self._engine._on_snapshot(
                snapshot, exec_idx,
                self._engine._current_high_tf_idx, self._engine._current_med_tf_idx
            )
        return snapshot
