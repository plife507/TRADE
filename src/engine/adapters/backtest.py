"""
Backtest adapters for PlayEngine.

These adapters wrap existing backtest infrastructure:
- BacktestDataProvider: Wraps FeedStore for O(1) array access
- BacktestExchange: Wraps SimulatedExchange for order execution
- ShadowExchange: No-op exchange for shadow mode

Fully integrated with existing backtest engine infrastructure.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import numpy as np

from ..interfaces import (
    Candle,
    DataProvider,
    ExchangeAdapter,
    Order,
    OrderResult,
    Position,
)
from ..play_engine import PlayEngineConfig

if TYPE_CHECKING:
    from ...backtest.play import Play
    from ...backtest.runtime.feed_store import FeedStore


class BacktestDataProvider:
    """
    DataProvider that wraps FeedStore arrays.

    Provides O(1) access to:
    - OHLCV candles
    - Precomputed indicators
    - Structure state from FeedStore.structures

    All data is precomputed; this adapter provides unified access.
    """

    def __init__(self, play: "Play"):
        """
        Initialize with Play configuration.

        Args:
            play: Play instance with feature specs
        """
        self._play = play
        self._feed_store: FeedStore | None = None
        self._ready = False
        self._current_bar_index: int = -1

        # These will be populated during engine initialization
        self._symbol = play.symbol_universe[0]
        self._timeframe = play.execution_tf

    @property
    def num_bars(self) -> int:
        """Total number of bars available."""
        if self._feed_store is None:
            return 0
        return self._feed_store.length

    @property
    def symbol(self) -> str:
        return self._symbol

    @property
    def timeframe(self) -> str:
        return self._timeframe

    @property
    def warmup_bars(self) -> int:
        """Number of warmup bars required before indicators are valid."""
        if self._feed_store is None:
            return 0
        return self._feed_store.warmup_bars

    @property
    def current_bar_index(self) -> int:
        """Current bar index for structure access."""
        return self._current_bar_index

    @current_bar_index.setter
    def current_bar_index(self, value: int) -> None:
        """Set current bar index (called by runner each bar)."""
        self._current_bar_index = value

    def set_feed_store(self, feed_store: "FeedStore") -> None:
        """
        Set the FeedStore after data loading.

        Called by BacktestRunner after loading historical data.
        """
        self._feed_store = feed_store
        self._ready = True

    def get_candle(self, index: int) -> Candle:
        """Get candle at index."""
        if self._feed_store is None:
            raise RuntimeError("FeedStore not initialized. Call set_feed_store() first.")

        if index < 0 or index >= self._feed_store.length:
            raise IndexError(f"Bar index {index} out of bounds [0, {self._feed_store.length})")

        return Candle(
            ts_open=self._feed_store.get_ts_open_datetime(index),
            ts_close=self._feed_store.get_ts_close_datetime(index),
            open=float(self._feed_store.open[index]),
            high=float(self._feed_store.high[index]),
            low=float(self._feed_store.low[index]),
            close=float(self._feed_store.close[index]),
            volume=float(self._feed_store.volume[index]),
        )

    def get_indicator(self, name: str, index: int) -> float:
        """
        Get indicator value at index.

        Args:
            name: Indicator name (e.g., "ema_9", "rsi_14", "atr_14")
            index: Bar index

        Returns:
            Indicator value as float

        Raises:
            RuntimeError: If FeedStore not initialized
            KeyError: If indicator not found
            IndexError: If index out of bounds
        """
        if self._feed_store is None:
            raise RuntimeError("FeedStore not initialized")

        if name not in self._feed_store.indicators:
            available = list(self._feed_store.indicators.keys())
            raise KeyError(
                f"Indicator '{name}' not found. "
                f"Available: {available[:10]}{'...' if len(available) > 10 else ''}"
            )

        arr = self._feed_store.indicators[name]
        if index < 0 or index >= len(arr):
            raise IndexError(f"Index {index} out of bounds for indicator '{name}'")

        value = arr[index]
        # Handle NaN values (warmup period)
        if np.isnan(value):
            return float("nan")
        return float(value)

    def get_structure(self, key: str, field: str) -> float:
        """
        Get current structure field value.

        Uses current_bar_index for "current" access.

        Args:
            key: Structure block key (e.g., "ms_5m", "swing")
            field: Field name (e.g., "swing_high_level", "direction")

        Returns:
            Structure field value

        Raises:
            RuntimeError: If no current bar index set
        """
        if self._current_bar_index < 0:
            raise RuntimeError(
                "No current bar index set. "
                "Use get_structure_at() or set current_bar_index first."
            )
        return self.get_structure_at(key, field, self._current_bar_index)

    def get_structure_at(self, key: str, field: str, index: int) -> float:
        """
        Get structure field at specific index.

        Args:
            key: Structure block key (e.g., "ms_5m", "swing")
            field: Field name (e.g., "swing_high_level", "direction")
            index: Bar index

        Returns:
            Structure field value

        Raises:
            RuntimeError: If FeedStore not initialized
            ValueError: If structure key or field not found
        """
        if self._feed_store is None:
            raise RuntimeError("FeedStore not initialized")

        value = self._feed_store.get_structure_field(key, field, index)
        if value is None:
            return float("nan")
        return float(value)

    def has_indicator(self, name: str) -> bool:
        """Check if indicator exists in FeedStore."""
        if self._feed_store is None:
            return False
        return name in self._feed_store.indicators

    def has_structure(self, key: str) -> bool:
        """Check if structure block exists."""
        if self._feed_store is None:
            return False
        return self._feed_store.has_structure(key)

    def get_indicator_keys(self) -> list[str]:
        """Get all available indicator names."""
        if self._feed_store is None:
            return []
        return list(self._feed_store.indicators.keys())

    def get_structure_keys(self) -> list[str]:
        """Get all available structure block keys."""
        if self._feed_store is None:
            return []
        return list(self._feed_store.structure_key_map.keys())

    def is_ready(self) -> bool:
        """Check if data provider is ready."""
        return self._ready and self._feed_store is not None


class BacktestExchange:
    """
    ExchangeAdapter that wraps SimulatedExchange.

    Provides:
    - Order submission and tracking
    - Position management
    - Balance and equity queries

    Translates between unified Order/Position types and SimulatedExchange types.
    """

    def __init__(self, play: "Play", config: PlayEngineConfig):
        """
        Initialize with Play and config.

        Args:
            play: Play instance
            config: Engine configuration
        """
        self._play = play
        self._config = config
        self._sim_exchange = None  # Set by runner
        self._symbol = play.symbol_universe[0]

        # Order ID mapping (unified -> sim)
        self._order_id_map: dict[str, str] = {}
        self._order_counter: int = 0

        # Deterministic timestamp for backtest (set by runner each bar)
        self._current_bar_ts: datetime | None = None

    def set_current_bar_timestamp(self, ts: datetime) -> None:
        """Set current bar timestamp for deterministic order submission."""
        self._current_bar_ts = ts

    def _get_order_timestamp(self) -> datetime:
        """Get timestamp for order submission (deterministic in backtest)."""
        if self._current_bar_ts is not None:
            return self._current_bar_ts
        return datetime.now()  # Fallback for cases where ts not set

    def set_simulated_exchange(self, sim_exchange) -> None:
        """
        Set the SimulatedExchange after initialization.

        Called by BacktestRunner after creating SimulatedExchange.
        """
        self._sim_exchange = sim_exchange

    def submit_order(self, order: Order) -> OrderResult:
        """
        Submit order for execution.

        Translates unified Order to SimulatedExchange format.

        Args:
            order: Unified Order object

        Returns:
            OrderResult with success status and order ID
        """
        if self._sim_exchange is None:
            return OrderResult(
                success=False,
                error="SimulatedExchange not initialized",
            )

        # Generate unified order ID if not provided
        if not order.client_order_id:
            self._order_counter += 1
            order.client_order_id = f"unified_{self._order_counter:04d}"

        # Translate to SimulatedExchange format
        side = "long" if order.side.lower() == "long" else "short"

        try:
            if order.order_type.upper() == "MARKET":
                sim_order_id = self._sim_exchange.submit_order(
                    side=side,
                    size_usdt=order.size_usdt,
                    stop_loss=order.stop_loss,
                    take_profit=order.take_profit,
                    timestamp=self._get_order_timestamp(),
                )
            elif order.order_type.upper() == "LIMIT":
                if order.limit_price is None:
                    return OrderResult(
                        success=False,
                        error="Limit price required for LIMIT orders",
                    )
                sim_order_id = self._sim_exchange.submit_limit_order(
                    side=side,
                    size_usdt=order.size_usdt,
                    limit_price=order.limit_price,
                    stop_loss=order.stop_loss,
                    take_profit=order.take_profit,
                    timestamp=self._get_order_timestamp(),
                )
            elif order.order_type.upper() in ("STOP", "STOP_MARKET"):
                if order.trigger_price is None:
                    return OrderResult(
                        success=False,
                        error="Trigger price required for STOP orders",
                    )
                sim_order_id = self._sim_exchange.submit_stop_order(
                    side=side,
                    size_usdt=order.size_usdt,
                    trigger_price=order.trigger_price,
                    limit_price=order.limit_price,
                    stop_loss=order.stop_loss,
                    take_profit=order.take_profit,
                    timestamp=self._get_order_timestamp(),
                )
            else:
                return OrderResult(
                    success=False,
                    error=f"Unknown order type: {order.order_type}",
                )

            if sim_order_id is None:
                return OrderResult(
                    success=False,
                    error="Order rejected by exchange",
                )

            # Map IDs
            self._order_id_map[order.client_order_id] = sim_order_id

            return OrderResult(
                success=True,
                order_id=order.client_order_id,
                exchange_order_id=sim_order_id,
            )

        except Exception as e:
            return OrderResult(
                success=False,
                error=str(e),
            )

    def cancel_order(self, order_id: str) -> bool:
        """Cancel pending order."""
        if self._sim_exchange is None:
            return False

        # Try to find in mapping first
        sim_order_id = self._order_id_map.get(order_id, order_id)

        try:
            return self._sim_exchange.cancel_order_by_id(sim_order_id)
        except Exception:
            return False

    def get_position(self, symbol: str) -> Position | None:
        """
        Get current position.

        Translates SimulatedExchange position to unified Position.
        """
        if self._sim_exchange is None:
            return None

        sim_pos = self._sim_exchange.position
        if sim_pos is None:
            return None

        # Calculate liquidation price using LiquidationModel
        cash_balance = self._sim_exchange.cash_balance_usdt
        mmr = self._sim_exchange.maintenance_margin_rate
        liq_price = self._sim_exchange._liquidation.calculate_liquidation_price(
            sim_pos, cash_balance, mmr
        )

        # Get mark price from exchange (last computed during process_bar)
        mark_price = self._sim_exchange.last_mark_price or sim_pos.entry_price

        # Translate to unified Position
        return Position(
            symbol=sim_pos.symbol,
            side=sim_pos.side.value if hasattr(sim_pos.side, "value") else str(sim_pos.side),
            size_usdt=sim_pos.size_usdt,
            size_qty=sim_pos.size,
            entry_price=sim_pos.entry_price,
            mark_price=mark_price,
            unrealized_pnl=0.0,  # Calculated by SimulatedExchange
            leverage=self._sim_exchange.leverage,
            stop_loss=sim_pos.stop_loss,
            take_profit=sim_pos.take_profit,
            liquidation_price=liq_price,
            metadata={
                "entry_time": sim_pos.entry_time.isoformat() if sim_pos.entry_time else None,
                "position_id": sim_pos.position_id,
            },
        )

    def get_balance(self) -> float:
        """Get available balance in USDT."""
        if self._sim_exchange is None:
            return self._config.initial_equity
        return self._sim_exchange.available_balance_usdt

    def get_equity(self) -> float:
        """Get total equity in USDT."""
        if self._sim_exchange is None:
            return self._config.initial_equity
        return self._sim_exchange.equity_usdt

    def get_realized_pnl(self) -> float:
        """
        Get total realized PnL since start.

        Calculated from: cash_balance - initial_capital + total_fees_paid
        """
        if self._sim_exchange is None:
            return 0.0
        ledger = self._sim_exchange._ledger
        initial = ledger._initial_capital
        cash = ledger.state.cash_balance_usdt
        fees = ledger.state.total_fees_paid
        return cash - initial + fees

    def get_pending_orders(self, symbol: str | None = None) -> list[Order]:
        """
        Get pending orders.

        Translates SimulatedExchange orders to unified Order format.
        """
        if self._sim_exchange is None:
            return []

        sim_orders = self._sim_exchange.get_open_orders()
        unified_orders = []

        for sim_order in sim_orders:
            if symbol is not None and sim_order.symbol != symbol:
                continue

            unified_orders.append(Order(
                symbol=sim_order.symbol,
                side=sim_order.side.value if hasattr(sim_order.side, "value") else str(sim_order.side),
                size_usdt=sim_order.size_usdt,
                order_type=sim_order.order_type.value if hasattr(sim_order.order_type, "value") else str(sim_order.order_type),
                limit_price=sim_order.limit_price,
                trigger_price=sim_order.trigger_price,
                stop_loss=sim_order.stop_loss,
                take_profit=sim_order.take_profit,
                client_order_id=sim_order.order_id,
            ))

        return unified_orders

    def step(self, candle: Candle) -> None:
        """
        Process new candle (fills, TP/SL).

        Called each bar to process order fills and position updates.
        Note: In backtest mode, process_bar is called by the runner,
        not by step(). This is here for interface compliance.
        """
        # In backtest mode, the runner calls sim_exchange.process_bar() directly
        # This method is mainly for interface compliance and live mode
        pass

    def submit_close(self, reason: str = "signal", percent: float = 100.0) -> None:
        """
        Request to close position on next bar.

        Args:
            reason: Close reason
            percent: Percentage to close (1-100)
        """
        if self._sim_exchange is None:
            return
        self._sim_exchange.submit_close(reason=reason, percent=percent)

    @property
    def has_position(self) -> bool:
        """Check if there's an open position."""
        if self._sim_exchange is None:
            return False
        return self._sim_exchange.position is not None

    @property
    def entries_disabled(self) -> bool:
        """Check if entries are disabled (e.g., due to starvation)."""
        if self._sim_exchange is None:
            return False
        return self._sim_exchange.entries_disabled

    @property
    def trades(self) -> list:
        """Get completed trades from SimulatedExchange."""
        if self._sim_exchange is None:
            return []
        return self._sim_exchange.trades


class ShadowExchange:
    """
    No-op exchange for shadow mode.

    Records signals without executing. Used for testing
    signal generation with live data.
    """

    def __init__(self, play: "Play", config: PlayEngineConfig):
        self._play = play
        self._config = config
        self._balance = config.initial_equity
        self._signals: list[Order] = []

    def submit_order(self, order: Order) -> OrderResult:
        """Record order without executing."""
        self._signals.append(order)
        return OrderResult(
            success=True,
            order_id=f"shadow_{len(self._signals)}",
            metadata={"shadow": True},
        )

    def cancel_order(self, order_id: str) -> bool:
        return True

    def get_position(self, symbol: str) -> Position | None:
        return None  # Shadow mode never has positions

    def get_balance(self) -> float:
        return self._balance

    def get_equity(self) -> float:
        return self._balance

    def get_pending_orders(self, symbol: str | None = None) -> list[Order]:
        return []

    def submit_close(self, reason: str = "signal", percent: float = 100.0) -> None:
        """No-op in shadow mode - no positions to close."""
        pass

    def get_realized_pnl(self) -> float:
        """Shadow mode has no realized PnL."""
        return 0.0

    def step(self, candle: Candle) -> None:
        pass  # No-op

    @property
    def recorded_signals(self) -> list[Order]:
        """Get all recorded signals."""
        return self._signals.copy()


# =============================================================================
# PROFESSIONAL NAMING ALIASES
# See docs/specs/ENGINE_NAMING_CONVENTION.md for full naming standards
# =============================================================================

# Sim* prefix for simulation/backtest adapters
SimDataAdapter = BacktestDataProvider
SimExchangeAdapter = BacktestExchange
ShadowExchangeAdapter = ShadowExchange
