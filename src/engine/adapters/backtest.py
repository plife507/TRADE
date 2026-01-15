"""
Backtest adapters for PlayEngine.

These adapters wrap existing backtest infrastructure:
- BacktestDataProvider: Wraps FeedStore for O(1) array access
- BacktestExchange: Wraps SimulatedExchange for order execution
- ShadowExchange: No-op exchange for shadow mode

Phase 2 will fully implement these adapters.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

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
    - Incremental structure state

    Phase 2: Full implementation with FeedStore integration.
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

        # These will be populated during engine initialization
        self._symbol = play.symbol
        self._timeframe = play.tf

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
        """Get indicator value at index."""
        if self._feed_store is None:
            raise RuntimeError("FeedStore not initialized")

        # TODO: Implement indicator access from FeedStore
        # FeedStore.get_indicator(name) returns the array
        # Return value at index
        raise NotImplementedError("Phase 2: Implement indicator access")

    def get_structure(self, key: str, field: str) -> float:
        """Get current structure field value."""
        # TODO: Implement structure access from incremental state
        raise NotImplementedError("Phase 2: Implement structure access")

    def get_structure_at(self, key: str, field: str, index: int) -> float:
        """Get structure field at specific index."""
        # TODO: Implement historical structure access
        raise NotImplementedError("Phase 2: Implement historical structure access")

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

    Phase 2: Full implementation with SimulatedExchange integration.
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

        # Track state
        self._balance = config.initial_equity
        self._position: Position | None = None
        self._pending_orders: list[Order] = []

    def set_simulated_exchange(self, sim_exchange) -> None:
        """
        Set the SimulatedExchange after initialization.

        Called by BacktestRunner after creating SimulatedExchange.
        """
        self._sim_exchange = sim_exchange

    def submit_order(self, order: Order) -> OrderResult:
        """Submit order for execution."""
        if self._sim_exchange is None:
            raise RuntimeError("SimulatedExchange not initialized")

        # TODO: Translate Order to SimulatedExchange format and submit
        raise NotImplementedError("Phase 2: Implement order submission")

    def cancel_order(self, order_id: str) -> bool:
        """Cancel pending order."""
        if self._sim_exchange is None:
            return False

        # TODO: Implement order cancellation
        raise NotImplementedError("Phase 2: Implement order cancellation")

    def get_position(self, symbol: str) -> Position | None:
        """Get current position."""
        if self._sim_exchange is None:
            return None

        # TODO: Translate SimulatedExchange position to Position
        raise NotImplementedError("Phase 2: Implement position access")

    def get_balance(self) -> float:
        """Get available balance."""
        if self._sim_exchange is None:
            return self._balance

        # TODO: Get from SimulatedExchange
        raise NotImplementedError("Phase 2: Implement balance access")

    def get_equity(self) -> float:
        """Get total equity."""
        if self._sim_exchange is None:
            return self._balance

        # TODO: Get from SimulatedExchange
        raise NotImplementedError("Phase 2: Implement equity access")

    def get_pending_orders(self, symbol: str | None = None) -> list[Order]:
        """Get pending orders."""
        return self._pending_orders

    def step(self, candle: Candle) -> None:
        """Process new candle (fills, TP/SL)."""
        if self._sim_exchange is None:
            return

        # TODO: Step SimulatedExchange with candle data
        raise NotImplementedError("Phase 2: Implement exchange step")


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

    def step(self, candle: Candle) -> None:
        pass  # No-op

    @property
    def recorded_signals(self) -> list[Order]:
        """Get all recorded signals."""
        return self._signals.copy()
