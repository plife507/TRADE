"""
Core types for the simulated exchange.

Provides all shared types, enums, events, and snapshots:
- Order, Fill, Position: Trade lifecycle types
- Bar: Re-exported from runtime.types (canonical Bar with ts_open/ts_close)
- FundingEvent, LiquidationEvent: Exchange events
- PriceSnapshot, SimulatorExchangeState, StepResult: State snapshots

Type design principles:
- Immutable where possible (frozen dataclasses)
- Explicit naming with "_usdt" suffix for all monetary values
- Serializable (to_dict methods)

Currency model (this simulator version):
- All monetary values are in USDT (quote currency)
- This simulator supports USDT-quoted linear perpetuals only
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

# Type alias for order IDs
OrderId = str


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────

class OrderType(str, Enum):
    """Order type."""
    MARKET = "market"
    LIMIT = "limit"
    STOP_MARKET = "stop_market"
    STOP_LIMIT = "stop_limit"


class OrderSide(str, Enum):
    """Order side."""
    LONG = "long"
    SHORT = "short"


class OrderStatus(str, Enum):
    """Order status."""
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class FillReason(str, Enum):
    """Reason for order fill."""
    ENTRY = "entry"
    STOP_LOSS = "sl"
    TAKE_PROFIT = "tp"
    SIGNAL = "signal"
    END_OF_DATA = "end_of_data"
    LIQUIDATION = "liquidation"
    FORCE_CLOSE = "force_close"


class TimeInForce(str, Enum):
    """Time-in-force options for orders.

    Bybit-aligned: https://bybit-exchange.github.io/docs/v5/order/create-order
    """
    GTC = "GTC"           # Good Till Cancel - stays until filled or cancelled
    IOC = "IOC"           # Immediate or Cancel - fill what you can, cancel rest
    FOK = "FOK"           # Fill or Kill - fill entirely or cancel entirely
    POST_ONLY = "PostOnly" # Maker only - reject if would take liquidity


class TriggerDirection(int, Enum):
    """Trigger direction for conditional orders.

    Bybit semantics:
    - 1 = trigger when price RISES TO trigger_price (breakout)
    - 2 = trigger when price FALLS TO trigger_price (breakdown)
    """
    RISES_TO = 1   # Trigger when bar.high >= trigger_price
    FALLS_TO = 2   # Trigger when bar.low <= trigger_price


# StopReason imported from canonical location (no duplication)
from ..types import StopReason


# ─────────────────────────────────────────────────────────────────────────────
# Bar type alias (canonical Bar from runtime.types)
# ─────────────────────────────────────────────────────────────────────────────

# Re-export canonical Bar from runtime.types for convenience
from ..runtime.types import Bar


# ─────────────────────────────────────────────────────────────────────────────
# Order
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Order:
    """
    Order waiting to be filled.

    Unified order type supporting all Bybit order types:
    - MARKET: Fill immediately at market price
    - LIMIT: Fill when price crosses limit_price
    - STOP_MARKET: Trigger at trigger_price, then fill as market
    - STOP_LIMIT: Trigger at trigger_price, then fill at limit_price

    Attributes:
        order_id: Unique order identifier
        symbol: Trading symbol (e.g., "BTCUSDT")
        side: LONG or SHORT
        size_usdt: Position size in USDT
        order_type: MARKET, LIMIT, STOP_MARKET, or STOP_LIMIT
        limit_price: Price for limit orders (required for LIMIT, STOP_LIMIT)
        trigger_price: Trigger price for stop orders (required for STOP_*)
        trigger_direction: RISES_TO (1) or FALLS_TO (2) for stop orders
        time_in_force: GTC, IOC, FOK, or POST_ONLY
        reduce_only: If True, only reduces position (cannot increase)
        stop_loss: Attached SL price for the position
        take_profit: Attached TP price for the position
        created_at: Order creation timestamp
        status: PENDING, FILLED, CANCELLED, or REJECTED
        submission_bar_index: Bar index when order was submitted (for IOC/FOK first-bar tracking)
    """
    order_id: OrderId
    symbol: str
    side: OrderSide
    size_usdt: float
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None
    trigger_price: float | None = None
    trigger_direction: TriggerDirection | None = None
    time_in_force: TimeInForce = TimeInForce.GTC
    reduce_only: bool = False
    stop_loss: float | None = None
    take_profit: float | None = None
    created_at: datetime | None = None
    status: OrderStatus = OrderStatus.PENDING
    submission_bar_index: int | None = None
    tp_order_type: str = "Market"
    sl_order_type: str = "Market"
    # Reference price used for SL/TP computation (signal bar close).
    # Used at fill time to adjust SL/TP for the actual fill price.
    sl_tp_ref_price: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "size_usdt": self.size_usdt,
            "order_type": self.order_type.value,
            "limit_price": self.limit_price,
            "trigger_price": self.trigger_price,
            "trigger_direction": self.trigger_direction.value if self.trigger_direction else None,
            "time_in_force": self.time_in_force.value,
            "reduce_only": self.reduce_only,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "status": self.status.value,
        }

    @property
    def is_conditional(self) -> bool:
        """Check if this is a conditional (stop) order."""
        return self.order_type in (OrderType.STOP_MARKET, OrderType.STOP_LIMIT)

    @property
    def is_triggered(self) -> bool:
        """Check if stop order has been triggered (filled after trigger condition met)."""
        # G6.6.1: Fix semantic bug - triggered means FILLED, not PENDING
        # Stop orders go: PENDING -> FILLED (when triggered) or CANCELLED
        return self.is_conditional and self.status == OrderStatus.FILLED


# ─────────────────────────────────────────────────────────────────────────────
# Position
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Position:
    """
    Currently open position.

    Unified position type (replaces OpenPosition).

    Phase 4 additions:
    - entry_bar_index: Bar index at entry (for trade duration tracking)
    - entry_ready: Snapshot readiness state at entry

    Dynamic stop tracking:
    - initial_stop: Original stop loss before trailing/BE adjustments
    - trailing_active: Whether trailing stop is activated
    - be_activated: Whether break-even stop has been triggered
    """
    position_id: str
    symbol: str
    side: OrderSide
    entry_price: float
    entry_time: datetime
    size: float  # Base currency units
    size_usdt: float
    stop_loss: float | None = None
    take_profit: float | None = None
    fees_paid: float = 0.0
    # Original entry fee (for partial close pro-rating)
    entry_fee: float = 0.0
    # Phase 4: Bar tracking and readiness
    entry_bar_index: int | None = None
    entry_ready: bool = True
    # MAE/MFE tracking: min/max price during position lifetime
    min_price: float | None = None
    max_price: float | None = None
    # Phase 12: Cumulative funding PnL (applied at 8h settlements)
    funding_pnl_cumulative: float = 0.0
    # Dynamic stop tracking
    initial_stop: float | None = None  # Original SL before trailing/BE
    trailing_active: bool = False  # Whether trailing has been activated
    be_activated: bool = False  # Whether break-even has been triggered
    peak_favorable_price: float | None = None  # Best price for trailing stop calc
    # TP/SL order types (Bybit convention: "Market" or "Limit")
    tp_order_type: str = "Market"
    sl_order_type: str = "Market"

    def unrealized_pnl(self, mark_price: float) -> float:
        """Calculate unrealized PnL at given mark price."""
        if self.side == OrderSide.LONG:
            return (mark_price - self.entry_price) * self.size
        else:
            return (self.entry_price - mark_price) * self.size
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "position_id": self.position_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "entry_price": self.entry_price,
            "entry_time": self.entry_time.isoformat(),
            "size": self.size,
            "size_usdt": self.size_usdt,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "fees_paid": self.fees_paid,
            "entry_fee": self.entry_fee,
            # Phase 4
            "entry_bar_index": self.entry_bar_index,
            "entry_ready": self.entry_ready,
            # MAE/MFE tracking
            "min_price": self.min_price,
            "max_price": self.max_price,
            # Phase 12: Funding
            "funding_pnl_cumulative": self.funding_pnl_cumulative,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Fill
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Fill:
    """
    Record of an order fill.
    
    Represents a single fill event (entry or exit).
    """
    fill_id: str
    order_id: OrderId
    symbol: str
    side: OrderSide
    price: float
    size: float
    size_usdt: float
    timestamp: datetime
    reason: FillReason
    fee: float = 0.0
    slippage: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "fill_id": self.fill_id,
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "price": self.price,
            "size": self.size,
            "size_usdt": self.size_usdt,
            "timestamp": self.timestamp.isoformat(),
            "reason": self.reason.value,
            "fee": self.fee,
            "slippage": self.slippage,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Events
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FundingEvent:
    """
    Funding rate event.
    
    Applied to open positions at funding timestamp.
    """
    timestamp: datetime
    symbol: str
    funding_rate: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "funding_rate": self.funding_rate,
        }


@dataclass(frozen=True)
class LiquidationEvent:
    """
    Liquidation event.

    Records when a position was liquidated.
    Bybit: mark price triggers liquidation, settlement at bankruptcy price.
    """
    timestamp: datetime
    symbol: str
    side: OrderSide
    mark_price: float
    bankruptcy_price: float
    equity_usdt: float
    maintenance_margin_usdt: float
    liquidation_fee: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "side": self.side.value,
            "mark_price": self.mark_price,
            "bankruptcy_price": self.bankruptcy_price,
            "equity_usdt": self.equity_usdt,
            "maintenance_margin_usdt": self.maintenance_margin_usdt,
            "liquidation_fee": self.liquidation_fee,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Price Snapshot
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PriceSnapshot:
    """
    Point-in-time price state.
    
    Contains all price references for a given bar.
    """
    timestamp: datetime
    mark_price: float
    last_price: float
    mid_price: float
    bid_price: float
    ask_price: float
    spread: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "mark_price": self.mark_price,
            "last_price": self.last_price,
            "mid_price": self.mid_price,
            "bid_price": self.bid_price,
            "ask_price": self.ask_price,
            "spread": self.spread,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Intrabar Path
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PricePoint:
    """
    Single point in intrabar price path.
    
    Used for deterministic TP/SL checking within a bar.
    """
    timestamp: datetime
    price: float
    sequence: int  # Order within the bar (0 = first)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "price": self.price,
            "sequence": self.sequence,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Result Types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Rejection:
    """Order rejection record."""
    order_id: OrderId
    reason: str
    code: str
    timestamp: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "reason": self.reason,
            "code": self.code,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class FillResult:
    """Result of order execution within a bar."""
    fills: list[Fill] = field(default_factory=list)
    rejections: list[Rejection] = field(default_factory=list)
    orders_remaining: list[Order] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fills": [f.to_dict() for f in self.fills],
            "rejections": [r.to_dict() for r in self.rejections],
            "orders_remaining": [o.to_dict() for o in self.orders_remaining],
        }


@dataclass
class FundingResult:
    """Result of funding application."""
    funding_pnl: float = 0.0
    events_applied: list[FundingEvent] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "funding_pnl": self.funding_pnl,
            "events_applied": [e.to_dict() for e in self.events_applied],
        }


@dataclass
class LiquidationResult:
    """Result of liquidation check."""
    liquidated: bool = False
    event: LiquidationEvent | None = None
    fill: Fill | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "liquidated": self.liquidated,
            "event": self.event.to_dict() if self.event else None,
            "fill": self.fill.to_dict() if self.fill else None,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Ledger State
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class LedgerState:
    """
    Complete ledger state at a point in time.
    
    Bybit-aligned margin model:
    - cash_balance_usdt: realized cash
    - unrealized_pnl_usdt: mark-to-market PnL
    - equity_usdt = cash_balance_usdt + unrealized_pnl_usdt
    - used_margin_usdt: position IM
    - free_margin_usdt = equity_usdt - used_margin_usdt
    - available_balance_usdt = max(0, free_margin_usdt)
    """
    cash_balance_usdt: float
    unrealized_pnl_usdt: float
    equity_usdt: float
    used_margin_usdt: float
    free_margin_usdt: float
    available_balance_usdt: float
    maintenance_margin_usdt: float
    total_fees_paid: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "cash_balance_usdt": self.cash_balance_usdt,
            "unrealized_pnl_usdt": self.unrealized_pnl_usdt,
            "equity_usdt": self.equity_usdt,
            "used_margin_usdt": self.used_margin_usdt,
            "free_margin_usdt": self.free_margin_usdt,
            "available_balance_usdt": self.available_balance_usdt,
            "maintenance_margin_usdt": self.maintenance_margin_usdt,
            "total_fees_paid": self.total_fees_paid,
        }


@dataclass
class LedgerUpdate:
    """Result of ledger update after fills/funding."""
    state: LedgerState
    realized_pnl: float = 0.0
    fees_paid: float = 0.0
    funding_paid: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.to_dict(),
            "realized_pnl": self.realized_pnl,
            "fees_paid": self.fees_paid,
            "funding_paid": self.funding_paid,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Step Result
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class StepResult:
    """
    Result of processing a single bar.
    
    Aggregates all events and state changes from process_bar().
    
    Phase 4: Unified mark price handling:
    - ts_close: Canonical step time (bar close timestamp)
    - mark_price: Computed once by exchange, used for all MTM/liquidation
    - mark_price_source: How mark was derived (close|hlc3|ohlc4)
    """
    timestamp: datetime
    # Phase 4: Canonical mark price fields
    ts_close: datetime | None = None
    mark_price: float | None = None
    mark_price_source: str = "close"
    # Event aggregates
    fills: list[Fill] = field(default_factory=list)
    rejections: list[Rejection] = field(default_factory=list)
    funding_result: FundingResult = field(default_factory=FundingResult)
    liquidation_result: LiquidationResult = field(default_factory=LiquidationResult)
    ledger_update: LedgerUpdate | None = None
    prices: PriceSnapshot | None = None
    debug_audit: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "ts_close": self.ts_close.isoformat() if self.ts_close else None,
            "mark_price": self.mark_price,
            "mark_price_source": self.mark_price_source,
            "fills": [f.to_dict() for f in self.fills],
            "rejections": [r.to_dict() for r in self.rejections],
            "funding_result": self.funding_result.to_dict(),
            "liquidation_result": self.liquidation_result.to_dict(),
            "ledger_update": self.ledger_update.to_dict() if self.ledger_update else None,
            "prices": self.prices.to_dict() if self.prices else None,
            "debug_audit": self.debug_audit,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Exchange State
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SimulatorExchangeState:
    """
    Complete simulator exchange state snapshot.
    
    Used for debugging and reproducibility.
    This is the internal state of SimulatedExchange - for strategy-facing
    state, use runtime.types.ExchangeState instead.
    """
    symbol: str
    timestamp: datetime | None
    ledger: LedgerState
    position: Position | None
    pending_orders: list[Order]

    # Starvation tracking
    entries_disabled: bool = False
    entries_disabled_reason: StopReason | None = None
    first_starved_ts: datetime | None = None
    first_starved_bar_index: int | None = None
    entry_attempts_count: int = 0
    entry_rejections_count: int = 0
    last_rejection_code: str | None = None
    last_rejection_reason: str | None = None
    
    # Config echo
    leverage: float = 1.0
    initial_margin_rate: float = 1.0
    maintenance_margin_rate: float = 0.005
    taker_fee_rate: float | None = None  # Loaded from DEFAULTS if None

    def __post_init__(self) -> None:
        """Load defaults from config/defaults.yml if not specified."""
        if self.taker_fee_rate is None:
            from src.config.constants import DEFAULTS
            self.taker_fee_rate = DEFAULTS.fees.taker_rate

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "ledger": self.ledger.to_dict(),
            "position": self.position.to_dict() if self.position else None,
            "pending_orders": [o.to_dict() for o in self.pending_orders],
            "entries_disabled": self.entries_disabled,
            "entries_disabled_reason": self.entries_disabled_reason.value if self.entries_disabled_reason else None,
            "first_starved_ts": self.first_starved_ts.isoformat() if self.first_starved_ts else None,
            "first_starved_bar_index": self.first_starved_bar_index,
            "entry_attempts_count": self.entry_attempts_count,
            "entry_rejections_count": self.entry_rejections_count,
            "last_rejection_code": self.last_rejection_code,
            "last_rejection_reason": self.last_rejection_reason,
            "leverage": self.leverage,
            "initial_margin_rate": self.initial_margin_rate,
            "maintenance_margin_rate": self.maintenance_margin_rate,
            "taker_fee_rate": self.taker_fee_rate,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Config Types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ExecutionConfig:
    """
    Execution parameters for simulation.

    Controls slippage application only. Fee rates come from RiskProfileConfig.

    Fee Model:
    - taker_fee_rate: Sourced from RiskProfileConfig.taker_fee_rate
    - maker_fee_bps: Available in engine.config.params (future limit order support)
    - All fills use RiskProfileConfig for fee calculation
    """
    slippage_bps: float = 5.0  # 0.05% default

    @property
    def slippage_rate(self) -> float:
        """Slippage as decimal (e.g., 0.0005 for 5 bps)."""
        return self.slippage_bps / 10000.0


# ─────────────────────────────────────────────────────────────────────────────
# Order Book
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class OrderBook:
    """
    Manages multiple pending orders for the simulated exchange.

    Replaces the single `pending_order` pattern with a proper order book
    that supports multiple concurrent orders of all types.

    Design:
    - O(1) order lookup by order_id
    - O(n) order iteration for fill checking (n = active orders)
    - Bounded size (max_orders) to prevent unbounded memory growth

    Usage:
        book = OrderBook()
        book.add_order(order)
        triggered = book.check_triggers(bar)
        for order in triggered:
            book.cancel_order(order.order_id)
    """
    max_orders: int = 100  # Safety limit

    # Private fields initialized in __post_init__
    _orders: dict[str, Order] = field(default_factory=dict, repr=False)
    _order_counter: int = field(default=0, repr=False)

    def add_order(self, order: Order) -> str:
        """
        Add an order to the book.

        Args:
            order: Order to add (order_id will be set if empty)

        Returns:
            The order_id

        Raises:
            ValueError: If order book is full
        """
        if len(self._orders) >= self.max_orders:
            raise ValueError(f"Order book full (max {self.max_orders} orders)")

        if not order.order_id:
            self._order_counter += 1
            order.order_id = f"order_{self._order_counter:04d}"

        self._orders[order.order_id] = order
        return order.order_id

    def get_order(self, order_id: str) -> Order | None:
        """Get order by ID."""
        return self._orders.get(order_id)

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order by ID.

        Returns:
            True if order was cancelled, False if not found
        """
        if order_id in self._orders:
            order = self._orders.pop(order_id)
            order.status = OrderStatus.CANCELLED
            return True
        return False

    def cancel_all(self, symbol: str | None = None) -> int:
        """
        Cancel all orders, optionally filtered by symbol.

        Args:
            symbol: Filter by symbol (None = all symbols)

        Returns:
            Number of orders cancelled
        """
        to_cancel = []
        for order_id, order in self._orders.items():
            if symbol is None or order.symbol == symbol:
                to_cancel.append(order_id)

        for order_id in to_cancel:
            self.cancel_order(order_id)

        return len(to_cancel)

    def check_triggers(self, bar: Bar) -> list[Order]:
        """
        Check which stop orders should trigger based on bar OHLC.

        Stop order trigger logic (Bybit semantics):
        - RISES_TO (1): Trigger if bar.high >= trigger_price
        - FALLS_TO (2): Trigger if bar.low <= trigger_price

        Args:
            bar: Current bar to check against

        Returns:
            List of orders that triggered (still in book, caller handles)
        """
        triggered = []

        for order in self._orders.values():
            if not order.is_conditional:
                continue

            if order.trigger_price is None:
                continue

            direction = order.trigger_direction or TriggerDirection.RISES_TO

            if direction == TriggerDirection.RISES_TO:
                if bar.high >= order.trigger_price:
                    triggered.append(order)
            elif direction == TriggerDirection.FALLS_TO:
                if bar.low <= order.trigger_price:
                    triggered.append(order)

        return triggered

    def get_pending_orders(
        self,
        order_type: OrderType | None = None,
        symbol: str | None = None,
    ) -> list[Order]:
        """
        Get all pending orders, optionally filtered.

        Args:
            order_type: Filter by order type
            symbol: Filter by symbol

        Returns:
            List of matching pending orders
        """
        result = []
        for order in self._orders.values():
            if order.status != OrderStatus.PENDING:
                continue
            if order_type is not None and order.order_type != order_type:
                continue
            if symbol is not None and order.symbol != symbol:
                continue
            result.append(order)
        return result

    def mark_filled(self, order_id: str) -> None:
        """Mark an order as filled and remove from book."""
        if order_id in self._orders:
            order = self._orders.pop(order_id)
            order.status = OrderStatus.FILLED

    def mark_rejected(self, order_id: str, reason: str = "") -> None:
        """Mark an order as rejected and remove from book."""
        if order_id in self._orders:
            order = self._orders.pop(order_id)
            order.status = OrderStatus.REJECTED

    @property
    def count(self) -> int:
        """Number of orders in book."""
        return len(self._orders)

    @property
    def is_empty(self) -> bool:
        """Check if book is empty."""
        return len(self._orders) == 0

    def amend_order(
        self,
        order_id: str,
        limit_price: float | None = None,
        trigger_price: float | None = None,
        size_usdt: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> bool:
        """
        Amend an existing order's parameters.

        Only pending orders can be amended. Supports modifying:
        - limit_price: For LIMIT and STOP_LIMIT orders
        - trigger_price: For STOP_MARKET and STOP_LIMIT orders
        - size_usdt: Order size
        - stop_loss: Attached SL price
        - take_profit: Attached TP price

        Args:
            order_id: ID of order to amend
            limit_price: New limit price (optional)
            trigger_price: New trigger price (optional)
            size_usdt: New size in USDT (optional)
            stop_loss: New stop loss price (optional, pass 0 to remove)
            take_profit: New take profit price (optional, pass 0 to remove)

        Returns:
            True if order was amended, False if order not found or not amendable
        """
        order = self._orders.get(order_id)
        if order is None:
            return False

        if order.status != OrderStatus.PENDING:
            return False

        # Amend limit price (only for LIMIT/STOP_LIMIT)
        if limit_price is not None:
            if order.order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT):
                order.limit_price = limit_price

        # Amend trigger price (only for STOP_MARKET/STOP_LIMIT)
        if trigger_price is not None:
            if order.order_type in (OrderType.STOP_MARKET, OrderType.STOP_LIMIT):
                order.trigger_price = trigger_price

        # Amend size
        if size_usdt is not None and size_usdt > 0:
            order.size_usdt = size_usdt

        # Amend TP/SL (0 = remove)
        if stop_loss is not None:
            order.stop_loss = stop_loss if stop_loss > 0 else None

        if take_profit is not None:
            order.take_profit = take_profit if take_profit > 0 else None

        return True

    def reset(self) -> None:
        """Clear all orders. Call when starting a new backtest."""
        self._orders.clear()
        self._order_counter = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_count": self.count,
            "max_orders": self.max_orders,
            "orders": [o.to_dict() for o in self._orders.values()],
        }

