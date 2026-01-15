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

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

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

from ..utils.logger import get_logger

if TYPE_CHECKING:
    from ..backtest.play import Play
    from ..backtest.feature_registry import FeatureRegistry
    from ..backtest.incremental.state import MultiTFIncrementalState
    from ..backtest.rules.types import CompiledBlock
    from ..backtest.execution_validation import PlaySignalEvaluator, EvaluationResult, SignalDecision
    from ..backtest.runtime.snapshot_view import RuntimeSnapshotView
    from ..core.risk_manager import Signal


@dataclass(slots=True)
class PlayEngineConfig:
    """Configuration for PlayEngine."""

    # Mode
    mode: Literal["backtest", "demo", "live", "shadow"]

    # Risk parameters
    initial_equity: float = 10000.0
    max_position_pct: float = 95.0
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None
    min_trade_usdt: float = 10.0

    # Fee model
    taker_fee_bps: float = 5.5
    maker_fee_bps: float = 2.0
    slippage_bps: float = 2.0

    # State persistence
    persist_state: bool = False
    state_save_interval: int = 100  # Save every N bars


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

        # Core state
        self._current_bar_index: int = -1
        self._warmup_complete: bool = False
        self._last_signal_ts: datetime | None = None

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

        # HTF/MTF feeds for multi-timeframe indicators (set by parity test or runner)
        self._htf_feed = None  # FeedStore for HTF indicators
        self._mtf_feed = None  # FeedStore for MTF indicators
        self._tf_mapping: dict[str, str] = {}  # TF mapping from Play config

        # Snapshot view for rule evaluation (built per bar)
        self._snapshot_view: RuntimeSnapshotView | None = None

        # Performance tracking
        self._total_signals: int = 0
        self._total_trades: int = 0
        self._bars_processed: int = 0

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
        return self.play.execution_tf

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

        # Get current candle
        try:
            candle = self.data.get_candle(bar_index)
        except IndexError:
            self.logger.warning(f"Bar index {bar_index} out of bounds")
            return None

        # 1. Update incremental state (structures)
        if self._incremental_state is not None:
            self._update_incremental_state(bar_index, candle)

        # 2. Check readiness (warmup complete, data available)
        if not self._is_ready():
            return None

        # 3. Step exchange (process pending orders, check TP/SL)
        self.exchange.step(candle)

        # 4. Get current position
        position = self.exchange.get_position(self.symbol)

        # 5. Evaluate rules and generate signal
        signal = self._evaluate_rules(bar_index, candle, position)

        if signal:
            self._total_signals += 1
            self._last_signal_ts = candle.ts_close

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
        from ..core.risk_manager import Signal as SignalType

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
            return OrderResult(
                success=True,
                order_id=f"close_{uuid.uuid4().hex[:8]}",
                metadata={"close": True, "percent": exit_percent},
            )

        # Entry signals (LONG/SHORT)
        # Apply risk sizing
        sized_usdt = self._size_position(signal)

        # Validate minimum size
        if sized_usdt < self.config.min_trade_usdt:
            return OrderResult(
                success=False,
                error=f"Position size {sized_usdt:.2f} below minimum {self.config.min_trade_usdt}",
            )

        # Create order
        order = Order(
            symbol=self.symbol,
            side=signal.direction,
            size_usdt=sized_usdt,
            order_type="MARKET",
            stop_loss=signal.metadata.get("stop_loss") if signal.metadata else None,
            take_profit=signal.metadata.get("take_profit") if signal.metadata else None,
            metadata={"signal": signal, "bar_index": self._current_bar_index},
        )

        # Submit to exchange
        result = self.exchange.submit_order(order)

        if result.success:
            self._total_trades += 1
            price_str = f"{result.fill_price:.2f}" if result.fill_price else "N/A"
            size_str = f"{result.fill_usdt:.2f}" if result.fill_usdt else "N/A"
            self.logger.info(
                f"Order filled: {signal.direction} {self.symbol} "
                f"price={price_str} size={size_str} USDT"
            )
        else:
            self.logger.warning(f"Order failed: {result.error}")

        return result

    def get_state(self) -> EngineState:
        """
        Get current engine state for persistence.

        Returns:
            EngineState with current position, equity, and metadata
        """
        position = self.exchange.get_position(self.symbol)

        return EngineState(
            engine_id=self.engine_id,
            play_id=self.play.name,
            mode=self.config.mode,
            symbol=self.symbol,
            position=position,
            pending_orders=self.exchange.get_pending_orders(self.symbol),
            equity_usdt=self.exchange.get_equity(),
            realized_pnl=0.0,  # TODO: Track realized PnL
            total_trades=self._total_trades,
            last_bar_ts=self.data.get_candle(self._current_bar_index).ts_close
            if self._current_bar_index >= 0
            else None,
            last_signal_ts=self._last_signal_ts,
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

        self.logger.info(
            f"State restored: {state.engine_id} "
            f"trades={state.total_trades} equity={state.equity_usdt:.2f}"
        )

    # =========================================================================
    # Private Methods
    # =========================================================================

    def _is_ready(self) -> bool:
        """Check if engine is ready for trading (warmup complete)."""
        if self._warmup_complete:
            return True

        # Check data provider readiness
        if not self.data.is_ready():
            return False

        self._warmup_complete = True
        self.logger.debug(f"Warmup complete at bar {self._current_bar_index}")
        return True

    def _update_incremental_state(self, bar_index: int, candle: Candle) -> None:
        """Update incremental structure state with new bar data."""
        from ..backtest.incremental.base import BarData

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
        self._incremental_state.update_exec(bar_data)

    def _evaluate_rules(
        self,
        bar_index: int,
        candle: Candle,
        position: Position | None,
    ) -> "Signal | None":
        """
        Evaluate entry/exit rules and generate signal.

        Uses PlaySignalEvaluator to evaluate the Play's action blocks
        against current market state.

        Returns:
            Signal if rule triggered, None otherwise
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
            except ValueError as e:
                self.logger.error(f"Failed to create signal evaluator: {e}")
                return None

        # Build snapshot view for evaluation
        snapshot = self._build_snapshot_view(bar_index, candle)
        if snapshot is None:
            return None

        # Determine position state
        has_position = position is not None
        position_side = position.side.lower() if position else None

        # Evaluate using PlaySignalEvaluator
        result = self._signal_evaluator.evaluate(snapshot, has_position, position_side)

        # Convert evaluation result to Signal
        if result.decision == SignalDecision.NO_ACTION:
            return None

        elif result.decision == SignalDecision.ENTRY_LONG:
            metadata = {
                "stop_loss": result.stop_loss_price,
                "take_profit": result.take_profit_price,
            }
            if result.resolved_metadata:
                metadata.update(result.resolved_metadata)
            return Signal(
                symbol=self.symbol,
                direction="LONG",
                size_usdt=0.0,  # Sized by execute_signal
                strategy=self.play.name,
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
            return Signal(
                symbol=self.symbol,
                direction="SHORT",
                size_usdt=0.0,
                strategy=self.play.name,
                confidence=1.0,
                metadata=metadata,
            )

        elif result.decision == SignalDecision.EXIT:
            metadata = {}
            if result.exit_percent != 100.0:
                metadata["exit_percent"] = result.exit_percent
            if result.resolved_metadata:
                metadata.update(result.resolved_metadata)
            return Signal(
                symbol=self.symbol,
                direction="FLAT",
                size_usdt=position.size_usdt if position else 0.0,
                strategy=self.play.name,
                confidence=1.0,
                metadata=metadata if metadata else None,
            )

        return None

    def _build_snapshot_view(self, bar_index: int, candle: Candle):
        """
        Build RuntimeSnapshotView for rule evaluation.

        This creates a snapshot that PlaySignalEvaluator can use to
        evaluate rules. In backtest mode, this wraps the FeedStore.

        Args:
            bar_index: Current bar index
            candle: Current candle data

        Returns:
            RuntimeSnapshotView or compatible snapshot object
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

            # Create MultiTFFeedStore with HTF/MTF feeds if available
            feeds = MultiTFFeedStore(
                exec_feed=feed_store,
                htf_feed=self._htf_feed,
                mtf_feed=self._mtf_feed,
                tf_mapping=self._tf_mapping,
            )

            # Compute HTF/MTF indices from bar_index using alignment arrays
            htf_idx = None
            mtf_idx = None
            if self._htf_feed is not None and hasattr(feed_store, 'htf_alignment'):
                if feed_store.htf_alignment is not None and bar_index < len(feed_store.htf_alignment):
                    htf_idx = int(feed_store.htf_alignment[bar_index])
            if self._mtf_feed is not None and hasattr(feed_store, 'mtf_alignment'):
                if feed_store.mtf_alignment is not None and bar_index < len(feed_store.mtf_alignment):
                    mtf_idx = int(feed_store.mtf_alignment[bar_index])

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
                htf_idx=htf_idx,
                mtf_idx=mtf_idx,
                exchange=self._exchange._sim_exchange if hasattr(self._exchange, '_sim_exchange') else None,
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

        # Live mode would build from LiveDataProvider
        # For now, return None (not implemented)
        return None

    def _size_position(self, signal: "Signal") -> float:
        """
        Apply risk sizing to signal.

        Returns:
            Position size in USDT
        """
        balance = self.exchange.get_balance()
        max_size = balance * (self.config.max_position_pct / 100.0)

        # Use signal's requested size, capped at max
        if signal.size_usdt:
            return min(signal.size_usdt, max_size)

        # Default to max position
        return max_size

    def _save_state(self) -> None:
        """Save current state to store."""
        state = self.get_state()
        self.state_store.save_state(self.engine_id, state)
