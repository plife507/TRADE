# Limit Orders and Position Scaling Architecture

> **Status**: Future Phase (Design Spec)
> **Created**: 2026-01-04
> **Prerequisites**: Blocks DSL v3.0.0, Incremental State, Derived Zones

This document specifies the architecture for limit order support and position scaling in both backtest and live trading contexts.

---

## Table of Contents

1. [Motivation](#motivation)
2. [Current State Analysis](#current-state-analysis)
3. [Design Goals](#design-goals)
4. [DSL Extensions](#dsl-extensions)
5. [Order Model](#order-model)
6. [Position Scaling Model](#position-scaling-model)
7. [Limit Order Fill Simulation](#limit-order-fill-simulation)
8. [Live Trading Parity](#live-trading-parity)
9. [Implementation Phases](#implementation-phases)
10. [Open Questions](#open-questions)

---

## Motivation

Institutional-style trading requires:

1. **Anticipatory entries**: Place limit orders at structure levels before price arrives
2. **Scaled position building**: Enter 10-25% tranches instead of all-or-nothing
3. **Partial exits**: Take profits at multiple levels, trail remainder
4. **Risk distribution**: Spread entries across multiple order blocks/zones

**Example Flow**:
```
Squeeze breakout detected
    → Anticipate pullback to demand zone
    → Place limit buy at zone upper (10% size)
    → If filled, place limit buy at zone lower (15% size)
    → Set stop below zone, TP at prior swing high
```

This cannot be expressed with current market-order-only semantics.

---

## Current State Analysis

### What Exists

| Component | Status | Location |
|-----------|--------|----------|
| `OrderType` enum | ✅ Defined | `src/backtest/sim/types.py:33` |
| `Order.limit_price` | ✅ Field exists | `src/backtest/sim/types.py:96` |
| `Order.trigger_price` | ✅ Field exists | `src/backtest/sim/types.py:97` |
| `Intent.metadata` | ✅ Extensible dict | `src/backtest/rules/strategy_blocks.py:65` |
| Volume data | ✅ Tracked | FeedStore, Snapshot, Rollups |
| Order book data | ❌ Not tracked | Would need L2 snapshots |

### Current Limitations

```python
# SimulatedExchange.submit_order() - current signature
def submit_order(
    self,
    side: str,
    size_usdt: float,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    timestamp: datetime | None = None,
) -> OrderId | None:
    # Always creates MARKET order
    # Rejects if position exists (single-position only)
    # No limit_price parameter
```

### Current VALID_ACTIONS

```python
VALID_ACTIONS = frozenset({
    "entry_long", "entry_short",
    "exit_long", "exit_short", "exit_all",
    "adjust_stop", "adjust_target", "adjust_size",
    "no_action",
})
```

---

## Design Goals

1. **DSL-first**: All order semantics expressible in IdeaCard YAML
2. **Backend-agnostic**: Same YAML runs in backtest and live
3. **Incremental adoption**: Existing market-order strategies unchanged
4. **Realistic simulation**: Fill logic accounts for liquidity constraints
5. **No lookahead**: Order placement uses only closed-bar data

---

## DSL Extensions

### New Action Types

```python
VALID_ACTIONS = frozenset({
    # Existing
    "entry_long", "entry_short",
    "exit_long", "exit_short", "exit_all",
    "adjust_stop", "adjust_target", "adjust_size",
    "no_action",

    # New: Limit orders
    "place_limit_long",      # Place limit buy
    "place_limit_short",     # Place limit sell (short entry)
    "place_limit_exit_long", # Place limit sell (close long)
    "place_limit_exit_short",# Place limit buy (close short)

    # New: Stop orders
    "place_stop_long",       # Stop buy (breakout entry)
    "place_stop_short",      # Stop sell (breakdown entry)

    # New: Order management
    "cancel_order",          # Cancel specific order by ref
    "cancel_all_orders",     # Cancel all pending orders
    "amend_order",           # Modify price/size of pending order
})
```

### Intent Metadata Schema

```yaml
emit:
  - action: place_limit_long
    metadata:
      # === Price Specification ===
      # Static price
      price: 50000.0

      # OR dynamic price reference
      price_ref:
        feature_id: "demand_zone"
        field: "closest_active_upper"
        offset: -10  # Optional: subtract 10 from value

      # OR price relative to current
      price_offset_pct: -0.5  # 0.5% below current price

      # === Size Specification ===
      # Absolute size
      size_usdt: 1000.0

      # OR percentage of equity
      size_pct: 0.10  # 10% of portfolio equity

      # OR percentage of max position
      size_of_max_pct: 0.25  # 25% of max allowed position

      # === Attached Orders (optional) ===
      stop_loss: 49000.0
      stop_loss_ref:
        feature_id: "demand_zone"
        field: "closest_active_lower"

      take_profit: 52000.0
      take_profit_ref:
        feature_id: "swing"
        field: "high_level"

      # === Order Lifecycle ===
      ttl_bars: 20          # Cancel if not filled in 20 bars
      ttl_type: "gtc"       # gtc | gtd | ioc | fok

      # === Order Identification ===
      order_ref: "zone_entry_1"  # For cancel/amend reference
      order_group: "entries"     # For group operations
```

### Complete IdeaCard Example

```yaml
name: "zone_scalper_v1"
symbol: "BTCUSDT"
tf: "15m"
htf: "4h"

features:
  - type: squeeze
    id: sqz
    params: { bb_length: 20, kc_length: 20, kc_mult: 1.5 }
  - type: supertrend
    id: st
    params: { length: 10, multiplier: 3.0 }

structures:
  exec:
    - type: swing
      key: swing
      params: { left: 5, right: 5 }
    - type: derived_zone
      key: demand
      depends_on: { swing: swing }
      params:
        levels: [0.618, 0.786]
        mode: retracement
        zone_type: demand
        max_active: 3

variables:
  has_squeeze_fire: { lhs: { feature_id: sqz, field: fired }, op: eq, rhs: true }
  has_swing_low: { lhs: { feature_id: swing, field: low_level }, op: gt, rhs: 0 }
  zone_active: { lhs: { feature_id: demand, field: any_active }, op: eq, rhs: true }
  is_flat: { lhs: { builtin: position_side }, op: eq, rhs: "flat" }
  has_pending: { lhs: { builtin: pending_order_count }, op: gt, rhs: 0 }

blocks:
  # Block 1: Place limit order after squeeze breakout
  - id: post_breakout_entry
    cases:
      - when:
          all:
            - var: has_squeeze_fire
            - var: has_swing_low
            - var: zone_active
            - var: is_flat
            - not: { var: has_pending }
        emit:
          - action: place_limit_long
            metadata:
              price_ref: { feature_id: demand, field: closest_active_upper }
              size_pct: 0.10
              ttl_bars: 30
              order_ref: "zone_entry"
              stop_loss_ref: { feature_id: demand, field: closest_active_lower }
              take_profit_ref: { feature_id: swing, field: high_level }

  # Block 2: Scale in if first entry filled and price continues down
  - id: scale_in
    cases:
      - when:
          all:
            - lhs: { builtin: position_side }
              op: eq
              rhs: "long"
            - lhs: { builtin: position_layers }
              op: lt
              rhs: 3  # Max 3 scale-ins
            - lhs: { builtin: close }
              op: lt
              rhs: { builtin: position_avg_entry, multiplier: 0.98 }  # 2% below avg
            - var: zone_active
        emit:
          - action: place_limit_long
            metadata:
              price_ref: { feature_id: demand, field: zone1_upper }  # Next zone
              size_pct: 0.15  # Larger size on scale-in
              ttl_bars: 20
              order_ref: "scale_2"

  # Block 3: Partial exit at target
  - id: partial_exit
    cases:
      - when:
          all:
            - lhs: { builtin: position_side }
              op: eq
              rhs: "long"
            - lhs: { builtin: close }
              op: near_pct
              rhs: { feature_id: swing, field: high_level }
              tolerance: 0.5  # Within 0.5% of target
        emit:
          - action: exit_long
            metadata:
              size_pct: 0.5  # Close 50% of position
              reason: "partial_tp"

  # Block 4: Cancel stale orders
  - id: order_management
    cases:
      - when:
          all:
            - lhs: { builtin: oldest_pending_age_bars }
              op: gt
              rhs: 50
        emit:
          - action: cancel_all_orders
            metadata:
              reason: "stale"
```

---

## Order Model

### Extended Order Dataclass

```python
@dataclass
class Order:
    """Extended order with limit/stop support."""

    # Identity
    order_id: str
    order_ref: str | None = None      # User-defined reference
    order_group: str | None = None    # For group operations

    # Core fields
    symbol: str
    side: OrderSide
    size_usdt: float
    order_type: OrderType = OrderType.MARKET

    # Price fields
    limit_price: float | None = None
    trigger_price: float | None = None  # For stop orders

    # Attached orders
    stop_loss: float | None = None
    take_profit: float | None = None

    # Lifecycle
    created_at: datetime | None = None
    expires_at: datetime | None = None
    ttl_bars: int | None = None
    bars_pending: int = 0

    # Status
    status: OrderStatus = OrderStatus.PENDING

    # Fill tracking
    filled_size_usdt: float = 0.0
    avg_fill_price: float | None = None
    fill_events: list[FillEvent] = field(default_factory=list)
```

### Order Book State

```python
@dataclass
class PendingOrderBook:
    """Tracks all pending orders for the exchange."""

    limit_buys: list[Order] = field(default_factory=list)   # Sorted by price desc
    limit_sells: list[Order] = field(default_factory=list)  # Sorted by price asc
    stop_buys: list[Order] = field(default_factory=list)    # Sorted by trigger asc
    stop_sells: list[Order] = field(default_factory=list)   # Sorted by trigger desc

    def add_order(self, order: Order) -> None:
        """Add order to appropriate book, maintain sort."""
        ...

    def cancel_by_ref(self, order_ref: str) -> Order | None:
        """Cancel order by user reference."""
        ...

    def cancel_by_group(self, group: str) -> list[Order]:
        """Cancel all orders in group."""
        ...

    def get_fillable_orders(self, bar: Bar) -> list[Order]:
        """
        Get orders that would fill on this bar.

        For limit buys: bar.low <= limit_price
        For limit sells: bar.high >= limit_price
        For stop buys: bar.high >= trigger_price
        For stop sells: bar.low <= trigger_price
        """
        ...

    def age_all(self) -> list[Order]:
        """Increment bars_pending, return expired orders."""
        ...
```

---

## Position Scaling Model

### Layer-Based Position

```python
@dataclass
class PositionLayer:
    """Single entry layer within a scaled position."""

    layer_id: str
    entry_price: float
    size_usdt: float
    entry_bar_idx: int
    entry_timestamp: datetime
    order_ref: str | None = None  # Which order created this layer

    # Per-layer stops (optional, can differ from position-level)
    layer_stop: float | None = None
    layer_target: float | None = None


@dataclass
class ScaledPosition:
    """Position composed of multiple entry layers."""

    symbol: str
    side: PositionSide
    layers: list[PositionLayer] = field(default_factory=list)

    # Position-level stops (apply to entire position)
    stop_loss: float | None = None
    take_profit: float | None = None

    @property
    def total_size_usdt(self) -> float:
        return sum(layer.size_usdt for layer in self.layers)

    @property
    def avg_entry_price(self) -> float:
        """Size-weighted average entry."""
        if not self.layers:
            return 0.0
        total_value = sum(l.size_usdt * l.entry_price for l in self.layers)
        return total_value / self.total_size_usdt

    @property
    def layer_count(self) -> int:
        return len(self.layers)

    def add_layer(self, layer: PositionLayer) -> None:
        """Add a new entry layer."""
        self.layers.append(layer)

    def remove_size(self, size_usdt: float, method: str = "fifo") -> list[PositionLayer]:
        """
        Remove size from position, return affected layers.

        Methods:
        - fifo: Remove from oldest layers first
        - lifo: Remove from newest layers first
        - proportional: Remove proportionally from all layers
        """
        ...

    def remove_pct(self, pct: float, method: str = "fifo") -> list[PositionLayer]:
        """Remove percentage of position."""
        return self.remove_size(self.total_size_usdt * pct, method)
```

### Builtin Variables for Scaling

```python
SCALING_BUILTINS = {
    # Position state
    "position_side": "flat | long | short",
    "position_size_usdt": "Total position size",
    "position_avg_entry": "Size-weighted average entry price",
    "position_layers": "Number of entry layers",
    "position_unrealized_pnl": "Current unrealized PnL",
    "position_unrealized_pct": "Unrealized PnL as % of entry",

    # Per-layer access (for advanced strategies)
    "position_layer_0_entry": "First layer entry price",
    "position_layer_0_size": "First layer size",
    # ... etc

    # Order state
    "pending_order_count": "Number of pending orders",
    "pending_limit_buy_count": "Number of pending limit buys",
    "pending_limit_sell_count": "Number of pending limit sells",
    "oldest_pending_age_bars": "Age of oldest pending order in bars",

    # Capacity
    "remaining_position_capacity": "Max position - current position",
    "remaining_equity_pct": "Equity not in positions",
}
```

---

## Limit Order Fill Simulation

### Fill Models (Configurable)

```python
class FillModel(str, Enum):
    """Available fill simulation models."""

    TOUCH = "touch"           # Fill if price touches limit
    THROUGH = "through"       # Fill only if price goes through
    VOLUME_WEIGHTED = "volume_weighted"  # Probability based on volume
    CONSERVATIVE = "conservative"  # Through + back-of-queue assumption


@dataclass
class FillModelConfig:
    """Configuration for fill simulation."""

    model: FillModel = FillModel.VOLUME_WEIGHTED

    # TOUCH model params
    # (none - simple touch = fill)

    # THROUGH model params
    through_threshold_pct: float = 0.01  # Must go 0.01% through level

    # VOLUME_WEIGHTED model params
    volume_participation_max: float = 0.10  # Max 10% of bar volume
    assume_queue_position: float = 0.5     # Assume middle of queue

    # CONSERVATIVE model params
    require_close_through: bool = True     # Close must be through level
```

### Fill Simulation Implementation

```python
class LimitFillSimulator:
    """
    Simulates limit order fills using bar data.

    Since we don't have order book data, we use bar OHLCV as proxy:
    - Price action tells us if level was reached
    - Volume tells us approximate liquidity
    - Range tells us price distribution
    """

    def __init__(self, config: FillModelConfig):
        self.config = config

    def check_fill(
        self,
        order: Order,
        bar: Bar,
        prev_bar: Bar | None = None,
    ) -> FillResult:
        """
        Check if order would fill on this bar.

        Returns:
            FillResult with fill status, price, and size
        """
        if order.order_type == OrderType.LIMIT:
            return self._check_limit_fill(order, bar, prev_bar)
        elif order.order_type == OrderType.STOP_MARKET:
            return self._check_stop_fill(order, bar, prev_bar)
        elif order.order_type == OrderType.STOP_LIMIT:
            return self._check_stop_limit_fill(order, bar, prev_bar)
        else:
            raise ValueError(f"Unknown order type: {order.order_type}")

    def _check_limit_fill(
        self,
        order: Order,
        bar: Bar,
        prev_bar: Bar | None,
    ) -> FillResult:
        """Check limit order fill."""

        is_buy = order.side == OrderSide.LONG
        limit_price = order.limit_price

        # Step 1: Did price reach our level?
        if is_buy:
            price_reached = bar.low <= limit_price
            price_through = bar.low < limit_price
        else:
            price_reached = bar.high >= limit_price
            price_through = bar.high > limit_price

        if not price_reached:
            return FillResult(filled=False)

        # Step 2: Apply fill model
        match self.config.model:
            case FillModel.TOUCH:
                return FillResult(
                    filled=True,
                    fill_price=limit_price,
                    filled_size=order.size_usdt,
                )

            case FillModel.THROUGH:
                if not price_through:
                    return FillResult(filled=False)
                return FillResult(
                    filled=True,
                    fill_price=limit_price,
                    filled_size=order.size_usdt,
                )

            case FillModel.VOLUME_WEIGHTED:
                return self._volume_weighted_fill(order, bar, is_buy)

            case FillModel.CONSERVATIVE:
                return self._conservative_fill(order, bar, is_buy)

    def _volume_weighted_fill(
        self,
        order: Order,
        bar: Bar,
        is_buy: bool,
    ) -> FillResult:
        """
        Estimate fill using volume as liquidity proxy.

        Assumptions:
        - Volume is distributed uniformly across bar range
        - We can participate in at most X% of volume at our level
        - Queue position affects our fill priority
        """
        limit_price = order.limit_price
        bar_range = bar.high - bar.low

        if bar_range == 0:
            # Flat bar - full fill if at our price
            if (is_buy and bar.low <= limit_price) or \
               (not is_buy and bar.high >= limit_price):
                return FillResult(
                    filled=True,
                    fill_price=limit_price,
                    filled_size=order.size_usdt,
                )
            return FillResult(filled=False)

        # Estimate USDT volume at our price level
        # Assume uniform distribution across range
        bar_turnover = bar.volume * bar.close  # Approximate USDT volume
        usdt_per_unit_range = bar_turnover / bar_range

        # How much of the bar range is at or better than our price?
        if is_buy:
            favorable_range = limit_price - bar.low
        else:
            favorable_range = bar.high - limit_price

        available_volume = usdt_per_unit_range * favorable_range

        # Apply participation limit
        max_fill = available_volume * self.config.volume_participation_max

        # Apply queue position penalty
        effective_fill = max_fill * (1 - self.config.assume_queue_position)

        if effective_fill >= order.size_usdt:
            # Full fill
            return FillResult(
                filled=True,
                fill_price=limit_price,
                filled_size=order.size_usdt,
            )
        elif effective_fill > 0:
            # Partial fill
            return FillResult(
                filled=True,
                fill_price=limit_price,
                filled_size=effective_fill,
                remaining_size=order.size_usdt - effective_fill,
                partial=True,
            )
        else:
            return FillResult(filled=False)

    def _conservative_fill(
        self,
        order: Order,
        bar: Bar,
        is_buy: bool,
    ) -> FillResult:
        """
        Conservative fill model.

        Requires:
        - Price to go THROUGH the level (not just touch)
        - Close to be through the level (confirming liquidity was taken)
        """
        limit_price = order.limit_price

        if is_buy:
            price_through = bar.low < limit_price
            close_through = bar.close < limit_price
        else:
            price_through = bar.high > limit_price
            close_through = bar.close > limit_price

        if not price_through:
            return FillResult(filled=False)

        if self.config.require_close_through and not close_through:
            # Price wicked through but didn't close through
            # Assume we might not have been filled
            return FillResult(filled=False)

        return FillResult(
            filled=True,
            fill_price=limit_price,
            filled_size=order.size_usdt,
        )


@dataclass
class FillResult:
    """Result of fill simulation."""

    filled: bool
    fill_price: float | None = None
    filled_size: float | None = None
    remaining_size: float | None = None
    partial: bool = False
    fill_bar_idx: int | None = None
    slippage: float = 0.0
```

### Fill Model Selection Guidelines

| Model | Use Case | Bias |
|-------|----------|------|
| `TOUCH` | Quick backtests, optimistic estimate | Optimistic |
| `THROUGH` | Standard backtests | Slightly optimistic |
| `VOLUME_WEIGHTED` | Realistic simulations | Neutral |
| `CONSERVATIVE` | Stress testing, worst-case | Pessimistic |

**Recommendation**: Default to `VOLUME_WEIGHTED` for strategy development, validate with `CONSERVATIVE` before live deployment.

---

## Live Trading Parity

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        IdeaCard YAML                            │
│            (Same file for backtest and live)                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    BlocksExecutor.execute()                     │
│            Evaluates conditions, emits Intent objects           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    IntentProcessor                              │
│         Resolves dynamic refs, validates, routes                │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────┐
│   BACKTEST BACKEND      │     │     LIVE BACKEND        │
├─────────────────────────┤     ├─────────────────────────┤
│ SimulatedExchange       │     │ LiveOrderRouter         │
│  - PendingOrderBook     │     │  - BybitClient          │
│  - LimitFillSimulator   │     │  - WebSocket feeds      │
│  - ScaledPosition       │     │  - Order state sync     │
└─────────────────────────┘     └─────────────────────────┘
```

### Intent Processing

```python
class IntentProcessor:
    """
    Processes Intents into concrete orders.

    Resolves dynamic references and validates before
    routing to appropriate backend.
    """

    def __init__(
        self,
        snapshot: RuntimeSnapshotView,
        position: ScaledPosition | None,
        pending_orders: PendingOrderBook,
        equity: float,
        max_position_usdt: float,
    ):
        self.snapshot = snapshot
        self.position = position
        self.pending_orders = pending_orders
        self.equity = equity
        self.max_position_usdt = max_position_usdt

    def process(self, intent: Intent) -> Order | None:
        """
        Convert Intent to Order.

        Returns None if intent is invalid or would be rejected.
        """
        meta = intent.metadata

        # Resolve price
        price = self._resolve_price(meta)

        # Resolve size
        size_usdt = self._resolve_size(meta)

        # Validate
        if not self._validate_order(intent, price, size_usdt):
            return None

        # Build order
        return self._build_order(intent, price, size_usdt)

    def _resolve_price(self, meta: dict) -> float | None:
        """Resolve price from metadata."""

        # Static price
        if "price" in meta:
            return float(meta["price"])

        # Dynamic reference
        if "price_ref" in meta:
            ref = meta["price_ref"]
            feature_id = ref["feature_id"]
            field = ref["field"]

            value = self.snapshot.get_structure_value(feature_id, field)

            # Apply offset
            if "offset" in ref:
                value += ref["offset"]
            if "offset_pct" in ref:
                value *= (1 + ref["offset_pct"] / 100)

            return value

        # Relative to current price
        if "price_offset_pct" in meta:
            return self.snapshot.close * (1 + meta["price_offset_pct"] / 100)

        # Market order - no price needed
        return None

    def _resolve_size(self, meta: dict) -> float:
        """Resolve size from metadata."""

        # Absolute size
        if "size_usdt" in meta:
            return float(meta["size_usdt"])

        # Percentage of equity
        if "size_pct" in meta:
            return self.equity * meta["size_pct"]

        # Percentage of max position
        if "size_of_max_pct" in meta:
            return self.max_position_usdt * meta["size_of_max_pct"]

        # Default (shouldn't happen with validation)
        raise ValueError("No size specified in intent metadata")
```

### Live Order Router

```python
class LiveOrderRouter:
    """
    Routes processed intents to live exchange.

    Maintains sync between local state and exchange state
    via WebSocket order updates.
    """

    def __init__(self, client: BybitClient, symbol: str):
        self.client = client
        self.symbol = symbol
        self._local_orders: dict[str, Order] = {}

    async def submit_order(self, order: Order) -> str:
        """Submit order to exchange, return exchange order ID."""

        match order.order_type:
            case OrderType.MARKET:
                if order.side == OrderSide.LONG:
                    result = await self.client.market_buy(
                        symbol=self.symbol,
                        size_usdt=order.size_usdt,
                    )
                else:
                    result = await self.client.market_sell(
                        symbol=self.symbol,
                        size_usdt=order.size_usdt,
                    )

            case OrderType.LIMIT:
                if order.side == OrderSide.LONG:
                    result = await self.client.limit_buy(
                        symbol=self.symbol,
                        price=order.limit_price,
                        size_usdt=order.size_usdt,
                    )
                else:
                    result = await self.client.limit_sell(
                        symbol=self.symbol,
                        price=order.limit_price,
                        size_usdt=order.size_usdt,
                    )

            case OrderType.STOP_MARKET:
                # ... similar pattern
                pass

        # Track locally
        exchange_order_id = result["orderId"]
        order.exchange_order_id = exchange_order_id
        self._local_orders[exchange_order_id] = order

        # Handle attached SL/TP
        if order.stop_loss or order.take_profit:
            await self._attach_sl_tp(exchange_order_id, order)

        return exchange_order_id

    async def cancel_order(self, order_ref: str) -> bool:
        """Cancel order by user reference."""
        for oid, order in self._local_orders.items():
            if order.order_ref == order_ref:
                await self.client.cancel_order(
                    symbol=self.symbol,
                    order_id=oid,
                )
                return True
        return False
```

### State Synchronization

```python
class OrderStateSynchronizer:
    """
    Keeps local order/position state in sync with exchange.

    Uses WebSocket for real-time updates, REST for reconciliation.
    """

    def __init__(self, client: BybitClient, symbol: str):
        self.client = client
        self.symbol = symbol
        self.position: ScaledPosition | None = None
        self.pending_orders: PendingOrderBook = PendingOrderBook()

        # Event handlers
        self._on_fill: list[Callable] = []
        self._on_cancel: list[Callable] = []

    async def start(self):
        """Start WebSocket subscription."""
        await self.client.subscribe_order_updates(
            symbol=self.symbol,
            callback=self._handle_order_update,
        )
        await self.client.subscribe_position_updates(
            symbol=self.symbol,
            callback=self._handle_position_update,
        )

        # Initial reconciliation
        await self._reconcile()

    async def _handle_order_update(self, update: dict):
        """Process order update from WebSocket."""

        status = update["orderStatus"]
        order_id = update["orderId"]

        if status == "Filled":
            order = self._find_order(order_id)
            if order:
                # Create position layer from fill
                layer = PositionLayer(
                    layer_id=f"layer_{order_id}",
                    entry_price=float(update["avgPrice"]),
                    size_usdt=float(update["cumExecValue"]),
                    entry_bar_idx=-1,  # Unknown in live
                    entry_timestamp=datetime.now(UTC),
                    order_ref=order.order_ref,
                )

                # Update position
                if self.position is None:
                    self.position = ScaledPosition(
                        symbol=self.symbol,
                        side=order.side,
                    )
                self.position.add_layer(layer)

                # Remove from pending
                self.pending_orders.remove(order_id)

                # Notify handlers
                for handler in self._on_fill:
                    await handler(order, layer)

        elif status == "Cancelled":
            self.pending_orders.remove(order_id)
            for handler in self._on_cancel:
                await handler(order_id)
```

---

## Implementation Phases

### Phase 1: Core Order Model (Foundation)

**Scope**: Extended Order/Position dataclasses, no execution changes

- [ ] `Order` dataclass with limit/stop fields
- [ ] `PositionLayer` and `ScaledPosition` dataclasses
- [ ] `PendingOrderBook` with add/cancel/query
- [ ] `FillResult` dataclass
- [ ] Unit tests for all dataclasses

**Acceptance**: All dataclasses instantiate correctly, order book operations work

### Phase 2: DSL Extensions

**Scope**: New actions and metadata schema

- [ ] Add new actions to `VALID_ACTIONS`
- [ ] Extend `Intent` validation for metadata schema
- [ ] Add price/size reference resolution
- [ ] Add scaling builtins to snapshot
- [ ] Parser tests for new YAML syntax

**Acceptance**: Can parse and validate IdeaCards with limit order syntax

### Phase 3: Fill Simulation

**Scope**: Backtest fill logic

- [ ] `LimitFillSimulator` with all models
- [ ] `FillModelConfig` for tuning
- [ ] Integration with bar processing loop
- [ ] Partial fill handling
- [ ] Order expiry (TTL) handling

**Acceptance**: Limit orders fill correctly in backtest with configurable model

### Phase 4: Scaled Position Integration

**Scope**: Multi-layer position in SimulatedExchange

- [ ] Replace `Position` with `ScaledPosition`
- [ ] Layer-based PnL calculation
- [ ] Partial exit logic (FIFO/LIFO/proportional)
- [ ] Update metrics for scaled positions
- [ ] Artifacts track layer history

**Acceptance**: Can run backtest with scaled entries/exits, metrics correct

### Phase 5: Live Backend

**Scope**: Live order routing and state sync

- [ ] `IntentProcessor` for live context
- [ ] `LiveOrderRouter` with Bybit integration
- [ ] `OrderStateSynchronizer` with WebSocket
- [ ] Reconciliation logic
- [ ] Error handling and retry

**Acceptance**: Can run live with limit orders, state syncs correctly

### Phase 6: Validation and Hardening

**Scope**: Edge cases, stress testing

- [ ] Validation IdeaCards (V_200+) for limit orders
- [ ] Conservative fill model stress tests
- [ ] Live paper trading validation
- [ ] Documentation and examples

**Acceptance**: Full test coverage, paper trading stable

---

## Open Questions

### Q1: Partial Fill Continuation

When a limit order partially fills, what happens to the remainder?

**Options**:
- A) Remainder stays as pending order (continue trying to fill)
- B) Remainder is cancelled (one-shot attempt per bar)
- C) Configurable per-order via metadata

**Recommendation**: Option C with default A

### Q2: Multiple Orders at Same Level

Can we have multiple limit orders at the same price?

**Options**:
- A) Yes, track independently
- B) No, merge into single order
- C) Configurable

**Recommendation**: Option A (more flexible for strategies)

### Q3: Stop-Limit Trigger Behavior

When a stop-limit triggers, does the limit order:

**Options**:
- A) Use trigger price as limit (exact)
- B) Use separate limit_price field
- C) Use offset from trigger

**Recommendation**: Option B (matches exchange semantics)

### Q4: Order Book Data Acquisition

Should we add real order book tracking for more realistic simulation?

**Options**:
- A) No, volume-weighted model is sufficient
- B) Yes, record L2 snapshots live for replay
- C) Yes, use tick data if available

**Recommendation**: Start with A, add B as optional enhancement

### Q5: Cross-Margin Position Scaling

Current design assumes isolated margin. How does scaling work with cross-margin?

**Answer**: Deferred. Isolated-only for initial implementation per existing constraints.

---

## References

- [Bybit Order Types](reference/exchanges/bybit/docs/v5/order/)
- [Blocks DSL v3.0.0](docs/specs/IDEACARD_SYNTAX.md)
- [Incremental State Architecture](docs/specs/INCREMENTAL_STATE_ARCHITECTURE.md)
- [Simulated Exchange](docs/architecture/SIMULATED_EXCHANGE.md)
