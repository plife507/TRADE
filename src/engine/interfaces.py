"""
Protocol definitions for unified Play Engine.

These protocols define the contracts for mode-specific adapters:
- DataProvider: Access to candles, indicators, and structures
- ExchangeAdapter: Order submission and position management
- StateStore: Engine state persistence for recovery

All adapters must implement these protocols to work with PlayEngine.
The protocols ensure identical signal generation logic across all modes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable


# =============================================================================
# Data Types
# =============================================================================


@dataclass(slots=True, frozen=True)
class Candle:
    """OHLCV candle data."""

    ts_open: datetime
    ts_close: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def ohlc4(self) -> float:
        """Average of OHLC."""
        return (self.open + self.high + self.low + self.close) / 4

    @property
    def hlc3(self) -> float:
        """Average of HLC (typical price)."""
        return (self.high + self.low + self.close) / 3

    @property
    def hl2(self) -> float:
        """Average of HL (midpoint)."""
        return (self.high + self.low) / 2


@dataclass(slots=True)
class Order:
    """Order to be submitted to exchange."""

    symbol: str
    side: Literal["LONG", "SHORT", "FLAT"]
    size_usdt: float
    order_type: Literal["MARKET", "LIMIT", "STOP_MARKET", "STOP_LIMIT"] = "MARKET"
    limit_price: float | None = None
    trigger_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    client_order_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class OrderResult:
    """Result from order submission."""

    success: bool
    order_id: str | None = None
    exchange_order_id: str | None = None  # Exchange-native order ID
    fill_price: float | None = None
    fill_qty: float | None = None
    fill_usdt: float | None = None
    fee_usdt: float | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Position:
    """Current position state."""

    symbol: str
    side: Literal["LONG", "SHORT"]
    size_usdt: float
    size_qty: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    leverage: float = 1.0
    stop_loss: float | None = None
    take_profit: float | None = None
    liquidation_price: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_long(self) -> bool:
        return self.side == "LONG"

    @property
    def is_short(self) -> bool:
        return self.side == "SHORT"


@dataclass(slots=True)
class EngineState:
    """
    Serializable engine state for persistence and recovery.

    Used by StateStore to save/load engine state across restarts.
    """

    engine_id: str
    play_id: str
    mode: Literal["backtest", "demo", "live", "shadow"]
    symbol: str

    # Position state
    position: Position | None = None
    pending_orders: list[Order] = field(default_factory=list)

    # Equity tracking
    equity_usdt: float = 0.0
    realized_pnl: float = 0.0
    total_trades: int = 0

    # Timing
    last_bar_ts: datetime | None = None
    last_signal_ts: datetime | None = None

    # Incremental state (serialized)
    incremental_state_json: str | None = None

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Protocol Definitions
# =============================================================================


@runtime_checkable
class DataProvider(Protocol):
    """
    Protocol for providing market data to the engine.

    Implementations:
    - BacktestDataProvider: Wraps FeedStore arrays for O(1) access
    - LiveDataProvider: Wraps WebSocket stream + indicator cache

    The index parameter semantics differ by mode:
    - Backtest: 0..N-1 index into historical arrays
    - Live: -1 = latest, -2 = previous, etc. (negative indexing)
    """

    @property
    def num_bars(self) -> int:
        """Total number of bars available (backtest) or buffer size (live)."""
        ...

    @property
    def symbol(self) -> str:
        """Trading symbol."""
        ...

    @property
    def timeframe(self) -> str:
        """Execution timeframe (e.g., '15m', '1h')."""
        ...

    def get_candle(self, index: int) -> Candle:
        """
        Get candle at index.

        Args:
            index: Bar index (0..N-1 for backtest, -1 for latest in live)

        Returns:
            Candle with OHLCV data

        Raises:
            IndexError: If index out of bounds
        """
        ...

    def get_indicator(self, name: str, index: int) -> float:
        """
        Get indicator value at index.

        Args:
            name: Indicator key (e.g., 'ema_20', 'rsi_14')
            index: Bar index

        Returns:
            Indicator value (float)

        Raises:
            KeyError: If indicator not found
            IndexError: If index out of bounds
        """
        ...

    def get_structure(self, key: str, field: str) -> float:
        """
        Get structure field value (current state).

        Args:
            key: Structure key (e.g., 'swing', 'trend')
            field: Field name (e.g., 'high_level', 'direction')

        Returns:
            Structure field value

        Raises:
            KeyError: If structure or field not found
        """
        ...

    def get_structure_at(self, key: str, field: str, index: int) -> float:
        """
        Get structure field value at specific bar index.

        Args:
            key: Structure key
            field: Field name
            index: Bar index

        Returns:
            Structure field value at index

        Raises:
            KeyError: If structure or field not found
            IndexError: If index out of bounds
        """
        ...

    def is_ready(self) -> bool:
        """
        Check if data provider is ready for trading.

        Returns:
            True if warmup complete and data available
        """
        ...


@runtime_checkable
class ExchangeAdapter(Protocol):
    """
    Protocol for exchange operations.

    Implementations:
    - BacktestExchange: Wraps SimulatedExchange for historical simulation
    - LiveExchange: Wraps OrderExecutor + PositionManager for real trading

    All implementations must provide identical semantics for:
    - Order submission and tracking
    - Position management
    - Balance queries
    """

    def submit_order(self, order: Order) -> OrderResult:
        """
        Submit order for execution.

        Args:
            order: Order to submit

        Returns:
            OrderResult with fill info or error

        For market orders, this should fill immediately (backtest)
        or return pending status (live).
        """
        ...

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel pending order.

        Args:
            order_id: Order ID to cancel

        Returns:
            True if cancelled, False if not found or already filled
        """
        ...

    def get_position(self, symbol: str) -> Position | None:
        """
        Get current position for symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Position if open, None if flat
        """
        ...

    def get_balance(self) -> float:
        """
        Get available balance in USDT.

        Returns:
            Available balance for trading
        """
        ...

    def get_equity(self) -> float:
        """
        Get total equity (balance + unrealized PnL).

        Returns:
            Total account equity in USDT
        """
        ...

    def get_realized_pnl(self) -> float:
        """
        Get total realized PnL since start.

        Returns:
            Cumulative realized profit/loss in USDT
        """
        ...

    def get_pending_orders(self, symbol: str | None = None) -> list[Order]:
        """
        Get pending orders.

        Args:
            symbol: Optional filter by symbol

        Returns:
            List of pending orders
        """
        ...

    def step(self, candle: Candle) -> None:
        """
        Process a new candle (for order fills, TP/SL checks).

        Args:
            candle: New candle data

        Called at each bar to process pending orders and check stops.
        For backtest, this triggers fills and TP/SL.
        For live, this may be a no-op (exchange handles fills).
        """
        ...

    def submit_close(self, reason: str = "signal", percent: float = 100.0) -> None:
        """
        Submit close order for current position.

        Args:
            reason: Reason for close (e.g., "signal", "stop_loss", "take_profit")
            percent: Percentage of position to close (1-100)

        Called by PlayEngine when exit signal triggers.
        """
        ...


@runtime_checkable
class StateStore(Protocol):
    """
    Protocol for engine state persistence.

    Implementations:
    - InMemoryStateStore: Simple dict for backtest (no persistence)
    - FileStateStore: JSON file for live crash recovery
    - RedisStateStore: Redis for distributed deployments (future)
    """

    def save_state(self, engine_id: str, state: EngineState) -> None:
        """
        Save engine state.

        Args:
            engine_id: Unique engine identifier
            state: Engine state to save

        Should be called periodically and after significant events.
        """
        ...

    def load_state(self, engine_id: str) -> EngineState | None:
        """
        Load engine state.

        Args:
            engine_id: Unique engine identifier

        Returns:
            Saved state if found, None otherwise
        """
        ...

    def delete_state(self, engine_id: str) -> bool:
        """
        Delete saved state.

        Args:
            engine_id: Unique engine identifier

        Returns:
            True if deleted, False if not found
        """
        ...

    def list_states(self) -> list[str]:
        """
        List all saved engine IDs.

        Returns:
            List of engine IDs with saved state
        """
        ...
