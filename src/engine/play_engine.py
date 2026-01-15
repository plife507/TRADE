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

        # Feature registry from Play
        self._feature_registry: FeatureRegistry | None = play.feature_registry

        # Compiled rules (lazy loaded)
        self._entry_rules: list[CompiledBlock] | None = None
        self._exit_rules: list[CompiledBlock] | None = None

        # Incremental state for structures (swing, trend, zones)
        # This is shared with data_provider in backtest mode
        self._incremental_state: MultiTFIncrementalState | None = None

        # Performance tracking
        self._total_signals: int = 0
        self._total_trades: int = 0
        self._bars_processed: int = 0

        self.logger.info(
            f"PlayEngine initialized: {self.engine_id} "
            f"mode={config.mode} symbol={play.symbol}"
        )

    @property
    def symbol(self) -> str:
        """Trading symbol."""
        return self.play.symbol

    @property
    def timeframe(self) -> str:
        """Execution timeframe."""
        return self.play.tf

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
        1. Applies risk sizing
        2. Validates minimum size
        3. Creates order with TP/SL
        4. Submits to exchange

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
            self.logger.info(
                f"Order filled: {signal.direction} {self.symbol} "
                f"price={result.fill_price:.2f} size={result.fill_usdt:.2f} USDT"
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

        bar_data = BarData(
            timestamp=candle.ts_close,
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            volume=candle.volume,
        )

        self._incremental_state.update(bar_index, bar_data)

    def _evaluate_rules(
        self,
        bar_index: int,
        candle: Candle,
        position: Position | None,
    ) -> "Signal | None":
        """
        Evaluate entry/exit rules and generate signal.

        Returns:
            Signal if rule triggered, None otherwise
        """
        from ..core.risk_manager import Signal

        # No position: evaluate entry rules
        if position is None:
            entry_signal = self._evaluate_entry_rules(bar_index, candle)
            if entry_signal:
                return entry_signal

        # Has position: evaluate exit rules
        else:
            exit_signal = self._evaluate_exit_rules(bar_index, candle, position)
            if exit_signal:
                return Signal(
                    symbol=self.symbol,
                    direction="FLAT",
                    size_usdt=position.size_usdt,
                    confidence=1.0,
                    metadata={"reason": "exit_rule", "position": position},
                )

        return None

    def _evaluate_entry_rules(self, bar_index: int, candle: Candle) -> "Signal | None":
        """
        Evaluate entry rules from Play.

        This is where the Play's compiled rules are evaluated against
        current market state via the data provider.
        """
        # TODO: Implement full rule evaluation using Play's compiled rules
        # For now, return None (no entry signal)
        #
        # The implementation will:
        # 1. Get snapshot view from data provider
        # 2. Evaluate entry_long and entry_short rules
        # 3. Apply position policy (long_only, short_only, long_short)
        # 4. Return Signal if rules pass

        return None

    def _evaluate_exit_rules(
        self,
        bar_index: int,
        candle: Candle,
        position: Position,
    ) -> bool:
        """
        Evaluate exit rules from Play.

        Returns:
            True if exit rule triggered
        """
        # TODO: Implement full rule evaluation using Play's compiled rules
        # For now, return False (no exit signal)
        #
        # The implementation will:
        # 1. Get snapshot view from data provider
        # 2. Evaluate exit_long or exit_short rules based on position
        # 3. Return True if rules pass

        return False

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
