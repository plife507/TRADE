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

        # HTF/MTF forward-fill indices (tracked dynamically like old engine)
        self._current_htf_idx: int = 0
        self._current_mtf_idx: int = 0

        # 1m quote feed for action model (set by parity test or runner)
        # This enables granular 1m evaluation within exec_tf bars
        self._quote_feed = None  # FeedStore for 1m OHLCV
        self._quote_feed_fallback_warned: bool = False  # Track if fallback warning issued

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

        # Update HTF/MTF indices (forward-fill logic)
        self._update_htf_mtf_indices(candle)

        # 1. Update incremental state (structures)
        if self._incremental_state is not None:
            self._update_incremental_state(bar_index, candle)

        # 2. Check readiness (warmup complete, data available)
        if not self._is_ready():
            if bar_index == 100:  # Debug: log early on why not ready
                self.logger.debug(f"Not ready at bar {bar_index}: data.is_ready={self.data.is_ready()}")
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

    def _update_htf_mtf_indices(self, candle: Candle) -> None:
        """
        Update HTF/MTF forward-fill indices based on current candle.

        Uses the same logic as the old BacktestEngine to determine when
        HTF/MTF bars have closed and update the forward-fill indices.

        This ensures that HTF/MTF indicator values are properly forward-filled
        until their bar closes, preventing lookahead.
        """
        # Skip if no HTF/MTF feeds
        if self._htf_feed is None and self._mtf_feed is None:
            return

        # Get exec feed for comparison
        from .adapters.backtest import BacktestDataProvider
        if not isinstance(self._data_provider, BacktestDataProvider):
            return

        exec_feed = self._data_provider._feed_store
        if exec_feed is None:
            return

        exec_ts_close = candle.ts_close

        # Check if HTF bar closed at this exec bar close
        if self._htf_feed is not None and self._htf_feed is not exec_feed:
            htf_idx = self._htf_feed.get_idx_at_ts_close(exec_ts_close)
            if htf_idx is not None and 0 <= htf_idx < self._htf_feed.length:
                self._current_htf_idx = htf_idx

        # Check if MTF bar closed at this exec bar close
        if self._mtf_feed is not None and self._mtf_feed is not exec_feed:
            mtf_idx = self._mtf_feed.get_idx_at_ts_close(exec_ts_close)
            if mtf_idx is not None and 0 <= mtf_idx < self._mtf_feed.length:
                self._current_mtf_idx = mtf_idx

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

            # Use dynamically tracked HTF/MTF indices (updated by _update_htf_mtf_indices)
            # These are forward-fill indices - they hold the last HTF/MTF bar that closed
            # IMPORTANT: In single-TF mode where htf_feed IS exec_feed, pass None
            # so RuntimeSnapshotView uses exec_ctx instead of creating a separate context
            htf_idx = None
            mtf_idx = None
            if self._htf_feed is not None and self._htf_feed is not feed_store:
                htf_idx = self._current_htf_idx
            if self._mtf_feed is not None and self._mtf_feed is not feed_store:
                mtf_idx = self._current_mtf_idx

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

    def _evaluate_with_1m_subloop(
        self,
        bar_index: int,
        candle: Candle,
        position: "Position | None",
    ) -> tuple["Signal | None", datetime | None]:
        """
        Evaluate rules with 1m granularity within the exec_tf bar.

        This mirrors the old BacktestEngine's _evaluate_with_1m_subloop method.
        It iterates through all 1m bars within the current exec bar and
        evaluates the strategy at each 1m price point.

        Args:
            bar_index: Current exec bar index
            candle: Current exec candle data
            position: Current position (if any)

        Returns:
            Tuple of (Signal or None, signal_ts or None)
        """
        from ..core.risk_manager import Signal
        from ..backtest.execution_validation import (
            PlaySignalEvaluator,
            SignalDecision,
        )
        from ..data.historical_data_store import TF_MINUTES

        # Get exec TF minutes for 1m mapping
        exec_tf_minutes = TF_MINUTES.get(self.timeframe.lower(), 15)

        # Check if 1m quote feed is available
        if self._quote_feed is None or self._quote_feed.length == 0:
            # Fallback: evaluate at exec close only (no 1m sub-loop)
            if not self._quote_feed_fallback_warned:
                self.logger.warning(
                    f"1m quote feed unavailable - using exec_tf close for signal evaluation. "
                    f"For full 1m action semantics, wire _quote_feed from old engine."
                )
                self._quote_feed_fallback_warned = True
            signal = self._evaluate_rules_single(bar_index, candle, position)
            return signal, None

        # Get 1m bar range for this exec bar
        start_1m, end_1m = self._quote_feed.get_1m_indices_for_exec(bar_index, exec_tf_minutes)

        # Clamp to available 1m data (both start and end)
        max_valid_idx = self._quote_feed.length - 1
        start_1m = min(start_1m, max_valid_idx)
        end_1m = min(end_1m, max_valid_idx)

        # If start > end after clamping, quote feed doesn't cover this exec bar
        if start_1m > end_1m:
            if not self._quote_feed_fallback_warned:
                self.logger.warning(
                    f"1m quote feed doesn't cover exec bar {bar_index} - using exec_tf close."
                )
                self._quote_feed_fallback_warned = True
            signal = self._evaluate_rules_single(bar_index, candle, position)
            return signal, None

        # Lazy initialize signal evaluator
        if self._signal_evaluator is None:
            try:
                self._signal_evaluator = PlaySignalEvaluator(self.play)
            except ValueError as e:
                self.logger.error(f"Failed to create signal evaluator: {e}")
                return None, None

        # Track previous 1m price for crossover operators
        # Seed with the 1m bar BEFORE start_1m to enable crossover on first iteration
        if start_1m > 0 and start_1m - 1 <= max_valid_idx:
            prev_price_1m: float | None = float(self._quote_feed.close[start_1m - 1])
        else:
            prev_price_1m = None

        # Iterate through 1m bars (mandatory 1m action loop)
        for sub_idx in range(start_1m, end_1m + 1):
            # Skip if entries disabled and no position
            # (allows exits when entries disabled, but blocks new entries)
            entries_disabled = getattr(self._exchange, 'entries_disabled', False)
            if entries_disabled and position is None:
                continue

            # Get 1m close as last_price
            price_1m = float(self._quote_feed.close[sub_idx])

            # Build snapshot with 1m prices and quote_idx for window operators
            snapshot = self._build_snapshot_view_1m(
                bar_index=bar_index,
                candle=candle,
                last_price=price_1m,
                prev_last_price=prev_price_1m,
                quote_idx=sub_idx,
            )

            # Update previous price for next iteration
            prev_price_1m = price_1m

            if snapshot is None:
                continue

            # Determine position state
            has_position = position is not None
            position_side = position.side.lower() if position else None

            # Evaluate using PlaySignalEvaluator
            result = self._signal_evaluator.evaluate(snapshot, has_position, position_side)

            # Convert evaluation result to Signal
            signal = self._result_to_signal(result, position)
            if signal is not None:
                # Get 1m close timestamp for order submission
                signal_ts = self._quote_feed.get_ts_close_datetime(sub_idx)
                return signal, signal_ts

        # No signal triggered
        return None, None

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

            # Create MultiTFFeedStore with HTF/MTF feeds if available
            feeds = MultiTFFeedStore(
                exec_feed=feed_store,
                htf_feed=self._htf_feed,
                mtf_feed=self._mtf_feed,
                tf_mapping=self._tf_mapping,
            )

            # Use dynamically tracked HTF/MTF indices
            htf_idx = None
            mtf_idx = None
            if self._htf_feed is not None and self._htf_feed is not feed_store:
                htf_idx = self._current_htf_idx
            if self._mtf_feed is not None and self._mtf_feed is not feed_store:
                mtf_idx = self._current_mtf_idx

            # Create snapshot view with 1m prices and quote_feed for window operators
            snapshot = RuntimeSnapshotView(
                feeds=feeds,
                exec_idx=bar_index,
                htf_idx=htf_idx,
                mtf_idx=mtf_idx,
                exchange=self._exchange._sim_exchange if hasattr(self._exchange, '_sim_exchange') else None,
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

        return None
