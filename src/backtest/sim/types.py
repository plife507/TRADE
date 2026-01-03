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


# StopReason imported from canonical location (no duplication)
from ..types import StopReason


# ─────────────────────────────────────────────────────────────────────────────
# Bar type alias (canonical Bar from runtime.types)
# ─────────────────────────────────────────────────────────────────────────────

# Re-export canonical Bar from runtime.types for backward compatibility
from ..runtime.types import Bar


# ─────────────────────────────────────────────────────────────────────────────
# Order
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Order:
    """
    Order waiting to be filled.
    
    Unified order type (replaces PendingOrder).
    """
    order_id: OrderId
    symbol: str
    side: OrderSide
    size_usdt: float
    order_type: OrderType = OrderType.MARKET
    stop_loss: float | None = None
    take_profit: float | None = None
    limit_price: float | None = None
    trigger_price: float | None = None
    created_at: datetime | None = None
    status: OrderStatus = OrderStatus.PENDING

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "size_usdt": self.size_usdt,
            "order_type": self.order_type.value,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "limit_price": self.limit_price,
            "trigger_price": self.trigger_price,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "status": self.status.value,
        }


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
    # Phase 4: Bar tracking and readiness
    entry_bar_index: int | None = None
    entry_ready: bool = True
    # MAE/MFE tracking: min/max price during position lifetime
    min_price: float | None = None
    max_price: float | None = None

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
            # Phase 4
            "entry_bar_index": self.entry_bar_index,
            "entry_ready": self.entry_ready,
            # MAE/MFE tracking
            "min_price": self.min_price,
            "max_price": self.max_price,
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
    """
    timestamp: datetime
    symbol: str
    side: OrderSide
    mark_price: float
    equity_usdt: float
    maintenance_margin_usdt: float
    liquidation_fee: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "side": self.side.value,
            "mark_price": self.mark_price,
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
    taker_fee_rate: float = 0.0006

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

