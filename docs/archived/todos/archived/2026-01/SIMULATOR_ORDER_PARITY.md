# Simulator Order Type Parity

Goal: Implement all Bybit order types in the simulator before demo/live integration.

**Status**: IMPLEMENTATION COMPLETE

---

## Gap Analysis

### Current State (Simulator)

The `SimulatedExchange` (`src/backtest/sim/exchange.py`) currently implements:

| Feature | Status | Location |
|---------|--------|----------|
| Market orders | ✅ Working | `submit_order()` → fills at bar.open with slippage |
| TP/SL on position | ✅ Working | 1m granular checking via `check_tp_sl_1m()` |
| Position tracking | ✅ Working | Single position per symbol (one-way mode) |
| MAE/MFE tracking | ✅ Working | Tracks min/max price during position |
| Funding events | ✅ Working | Applied at 8h intervals |
| Liquidation | ✅ Working | Checked each bar after MTM update |

### Types Defined But Not Implemented

```python
# src/backtest/sim/types.py
class OrderType(str, Enum):
    MARKET = "market"       # ✅ Implemented
    LIMIT = "limit"         # ❌ Type only - no fill logic
    STOP_MARKET = "stop_market"   # ❌ Type only - no trigger logic
    STOP_LIMIT = "stop_limit"     # ❌ Type only - no trigger logic
```

### Live Tools (Complete Reference)

From `src/tools/order_tools.py`:

| Tool | Bybit Feature | Simulator Needs |
|------|---------------|-----------------|
| `market_buy_tool` | Market buy | ✅ Already implemented |
| `market_sell_tool` | Market sell | ✅ Already implemented |
| `market_buy_with_tpsl_tool` | Market + TP/SL | ✅ Already implemented |
| `market_sell_with_tpsl_tool` | Market + TP/SL | ✅ Already implemented |
| `limit_buy_tool` | Limit buy | ❌ Need fill logic |
| `limit_sell_tool` | Limit sell | ❌ Need fill logic |
| `stop_market_buy_tool` | Conditional market | ❌ Need trigger logic |
| `stop_market_sell_tool` | Conditional market | ❌ Need trigger logic |
| `stop_limit_buy_tool` | Conditional limit | ❌ Need trigger + fill logic |
| `stop_limit_sell_tool` | Conditional limit | ❌ Need trigger + fill logic |
| `partial_close_position_tool` | Partial close | ❌ Need reduce-only logic |
| `get_open_orders_tool` | Query orders | ❌ Need order book |
| `cancel_order_tool` | Cancel | ❌ Need order book |
| `amend_order_tool` | Modify | ❌ Need order book |
| `cancel_all_orders_tool` | Bulk cancel | ❌ Need order book |

### Bybit Order Parameters to Support

From `reference/exchanges/bybit/docs/api-explorer/v5/trade/create-order.api.mdx`:

| Parameter | Values | Priority |
|-----------|--------|----------|
| `orderType` | Market, Limit | P1 |
| `triggerPrice` | float | P1 |
| `triggerDirection` | 1=rises to, 2=falls to | P1 |
| `timeInForce` | GTC, IOC, FOK, PostOnly | P2 |
| `reduceOnly` | true/false | P1 |
| `triggerBy` | LastPrice, MarkPrice | P3 (always use close) |
| `tpslMode` | Full, Partial | P3 |

---

## Implementation Progress

### Phase 1: Order Book (Foundation) - COMPLETE

Added enums and OrderBook class to `src/backtest/sim/types.py`:

```python
class TimeInForce(str, Enum):
    GTC = "GTC"           # Good Till Cancel
    IOC = "IOC"           # Immediate or Cancel
    FOK = "FOK"           # Fill or Kill
    POST_ONLY = "PostOnly" # Maker only

class TriggerDirection(int, Enum):
    RISES_TO = 1   # Trigger when bar.high >= trigger_price
    FALLS_TO = 2   # Trigger when bar.low <= trigger_price

@dataclass
class OrderBook:
    """Manages multiple pending orders with O(1) operations."""
    # add_order, get_order, cancel_order, cancel_all, check_triggers
    # get_pending_orders, mark_filled, mark_rejected
```

Extended Order dataclass with new fields:
- `trigger_direction`, `time_in_force`, `reduce_only`
- Properties: `is_conditional`, `is_triggered`

### Phase 2: Limit Order Fill Logic - COMPLETE

Added to `src/backtest/sim/execution/execution_model.py`:

```python
def check_limit_fill(order, bar) -> tuple[bool, float | None]:
    # Limit BUY: Fill if bar.low <= limit_price
    # Limit SELL: Fill if bar.high >= limit_price
    # Price improvement if bar opens better than limit

def fill_limit_order(order, bar, ..., is_first_bar) -> FillResult:
    # Handles time-in-force: GTC, IOC, FOK, POST_ONLY
    # Returns FillResult with fill or rejection
```

### Phase 3: Stop Order Trigger Logic - COMPLETE

Trigger logic in `OrderBook.check_triggers()`:
- RISES_TO (1): Trigger if bar.high >= trigger_price
- FALLS_TO (2): Trigger if bar.low <= trigger_price

Fill logic in `ExecutionModel.fill_triggered_stop()`:
- STOP_MARKET: Delegates to `fill_entry_order()` (market fill)
- STOP_LIMIT: Delegates to `fill_limit_order()` (limit fill)

### Phase 4: Reduce-Only Support - COMPLETE

Added `ExecutionModel.check_reduce_only()`:
```python
def check_reduce_only(order, position) -> tuple[bool, float | None, str | None]:
    # 1. Must have an open position
    # 2. Order side must be opposite to position side
    # 3. Order size clamped to position size (no flip)
    # Returns (is_valid, clamped_size_usdt, error_reason)
```

### Phase 5: Order Management - COMPLETE

SimulatedExchange now has full order management:

**New Submission Methods:**
- `submit_limit_order(side, size_usdt, limit_price, ...)` - Submit limit order
- `submit_stop_order(side, size_usdt, trigger_price, trigger_direction, ...)` - Submit stop order

**Order Management Methods:**
- `get_open_orders()` - Query all pending orders
- `cancel_order_by_id(order_id)` - Cancel single order
- `cancel_all_orders()` - Cancel all orders

**Internal Processing:**
- `_process_order_book(bar)` - Process all order book orders each bar
- `_handle_entry_fill(fill, order)` - Handle position creation
- `_handle_reduce_only_fill(fill, order)` - Handle position reduction (partial + full)

**Order Amendment:**
- `amend_order(order_id, ...)` - Modify pending order price, qty, TP/SL

### Phase 6: Partial Position Closes - COMPLETE

Added support for partial position closes:

- `reduce_only=True` orders can close less than full position
- Partial close uses `Ledger.apply_partial_exit()` (preserves margin state)
- Full close uses `Ledger.apply_exit()` (clears margin state)
- Position size reduced proportionally on partial close
- Margin recalculated on next `update_for_mark_price` call

---

## Type Extensions

### New Enums (types.py)

```python
class TimeInForce(str, Enum):
    GTC = "GTC"           # Good Till Cancel
    IOC = "IOC"           # Immediate or Cancel
    FOK = "FOK"           # Fill or Kill
    POST_ONLY = "PostOnly" # Maker only

class TriggerDirection(int, Enum):
    RISES_TO = 1   # Trigger when price >= trigger_price
    FALLS_TO = 2   # Trigger when price <= trigger_price
```

### Extended Order Dataclass

```python
@dataclass
class Order:
    order_id: OrderId
    symbol: str
    side: OrderSide
    size_usdt: float
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None      # For LIMIT, STOP_LIMIT
    trigger_price: float | None = None    # For STOP_*
    trigger_direction: TriggerDirection | None = None
    time_in_force: TimeInForce = TimeInForce.GTC
    reduce_only: bool = False
    stop_loss: float | None = None
    take_profit: float | None = None
    created_at: datetime | None = None
    status: OrderStatus = OrderStatus.PENDING
```

---

## Execution Model Updates

### Updated Fill Logic (execution_model.py)

```python
def fill_orders(self, order_book: OrderBook, bar: Bar, ...) -> FillResult:
    """Process all pending orders against current bar."""
    fills = []

    # 1. Check stop order triggers
    triggered = order_book.get_triggered(bar)
    for order in triggered:
        if order.order_type == OrderType.STOP_MARKET:
            # Convert to market order, fill at bar open
            fill = self._fill_market_order(order, bar)
            fills.append(fill)
        elif order.order_type == OrderType.STOP_LIMIT:
            # Convert to limit order, add to book
            limit_order = self._stop_to_limit(order)
            order_book.add_order(limit_order)

    # 2. Check limit order fills
    for order_id, order in order_book.active_orders.items():
        if order.order_type == OrderType.LIMIT:
            fill = self._try_fill_limit(order, bar)
            if fill:
                fills.append(fill)
                order_book.remove(order_id)
        elif order.order_type == OrderType.MARKET:
            fill = self._fill_market_order(order, bar)
            fills.append(fill)
            order_book.remove(order_id)

    return FillResult(fills=fills)
```

---

## Validation Tests - COMPLETE

Order type validation is done via the simulator orders smoke test:

**Location:** `src/cli/smoke_tests/sim_orders.py`

**Run with:** `python -c "from src.cli.smoke_tests import run_sim_orders_smoke; run_sim_orders_smoke()"`

### Test Coverage

| Section | Tests |
|---------|-------|
| Section 1: Limit Order Fills | Limit buy fills at limit price, Limit sell fills at limit price |
| Section 2: Stop Order Triggers | Stop market buy/sell trigger and fill |
| Section 3: Time-in-Force | GTC order persistence |
| Section 4: Reduce-Only Orders | Position creation, reduce-only validation |
| Section 5: Order Book Management | Cancel single, cancel all, order queries |
| Section 6: Order Book Processing | Full process_bar integration |
| Section 7: Partial Position Close | 50% close, position reduced, position remains open |
| Section 8: Order Amendment | Price amend, size amend, TP/SL add/remove, invalid order |

All tests pass (exit code 0).

---

## Priority Order

1. **Phase 1: Order Book** - Foundation for everything else
2. **Phase 2: Limit Orders** - Most commonly used after market
3. **Phase 3: Stop Orders** - Needed for stop-loss entries
4. **Phase 4: Reduce-Only** - Needed for partial closes
5. **Phase 5: Order Management** - Nice to have, not critical

---

## Not Implementing (Out of Scope)

| Feature | Reason |
|---------|--------|
| Batch orders | Can be simulated by multiple submits |
| Partial fills | Complexity outweighs benefit for backtesting |
| triggerBy options | Always use bar close as price reference |
| tpslMode Partial | Full mode sufficient |
| positionIdx (hedge mode) | One-way mode only |

---

## Future Features (Not Yet Implemented)

These Bybit features are documented for future implementation when needed:

### Trailing Stop (P2 Priority)

Bybit supports trailing stops via the `/v5/position/trading-stop` endpoint:

```yaml
# Bybit API parameters
trailingStop: "50"        # Distance in price points (e.g., $50 callback)
activePrice: "45000"      # Activation price (trailing starts when reached)
```

**Behavior**:
1. Position opened at 40000
2. Price rises to 45000 (activePrice) → trailing stop activates
3. Initial stop set at 44950 (45000 - 50)
4. Price rises to 46000 → stop follows to 45950
5. Price drops to 45950 → STOP TRIGGERED

**Implementation Requirements**:
- `trailing_distance: float` on Position dataclass
- `trailing_active_price: float` (optional activation threshold)
- `_highest_price` / `_lowest_price` tracking (already have MAE/MFE)
- Update trailing stop level in `process_bar()` after price moves favorably

**DSL Extension Needed**:
```yaml
risk_model:
  trailing_stop:
    type: "price_distance"  # or "percent"
    value: 50.0
    active_price: 45000.0   # Optional
```

### Partial TP/SL (P3 Priority)

Bybit supports partial take-profit/stop-loss via `tpslMode=Partial`:

```yaml
# Bybit API parameters
tpslMode: "Partial"
takeProfit: "42000"
tpLimitPrice: "42000"     # Optional limit for TP execution
tpSize: "0.5"             # Close 50% at TP
stopLoss: "38000"
slLimitPrice: "37900"     # Optional limit for SL execution
slSize: "0.5"             # Close 50% at SL
```

**Behavior**:
- Only close specified size at TP/SL, not full position
- Remaining position continues with original entry price
- Multiple TP/SL levels can be set (pyramid exits)

**Implementation Requirements**:
- `tp_size_usdt: float | None` on Position
- `sl_size_usdt: float | None` on Position
- Partial close logic in `_check_tp_sl_exit()`
- Multiple TP levels support (list instead of single value)

**DSL Extension Needed**:
```yaml
risk_model:
  take_profit:
    - level: 1
      type: "percent"
      value: 2.0
      size_pct: 50.0    # Close 50% at first TP
    - level: 2
      type: "percent"
      value: 4.0
      size_pct: 50.0    # Close remaining at second TP
```

### Limit TP/SL Execution (P3 Priority)

Bybit allows TP/SL to execute as limit orders instead of market:

```yaml
takeProfit: "42000"
tpLimitPrice: "42050"     # Execute as limit at 42050, not market
tpOrderType: "Limit"      # vs "Market" (default)
```

**Benefit**: Avoids slippage but risks non-fill if price moves away.

**Implementation Requirements**:
- `tp_order_type: OrderType` (default MARKET)
- `sl_order_type: OrderType` (default MARKET)
- Create limit orders instead of immediate fills

---

## Order Mechanics Smoke Test

A comprehensive smoke test validates all implemented order mechanics:

**Location:** `src/cli/smoke_tests/order_mechanics.py`

**Run:** `python -c "from src.cli.smoke_tests.order_mechanics import run_order_mechanics_smoke; run_order_mechanics_smoke(verbose=True)"`

### Test Coverage (10 Sections)

| Section | Feature | Status |
|---------|---------|--------|
| 1 | Market Order with SL/TP | PASS |
| 2 | Stop Loss Triggered | PASS |
| 3 | Take Profit Triggered | PASS |
| 4 | Conservative Tie-Break (SL wins) | PASS |
| 5 | SL Not Triggered (price above) | PASS |
| 6 | Short Position SL/TP | PASS |
| 7 | Position Close at End of Data | PASS |
| 8 | Multi-Bar SL Hit | PASS |
| 9 | Margin Check on Entry | PASS |
| 10 | Leveraged Position | PASS |

### Key Behaviors Verified

- **SL Trigger**: `bar.low <= stop_loss` (long) or `bar.high >= stop_loss` (short)
- **TP Trigger**: `bar.high >= take_profit` (long) or `bar.low <= take_profit` (short)
- **Conservative Tie-Break**: When both SL and TP would trigger in same bar, SL wins
- **Fill Price**: SL fills at `stop_loss × (1 - slippage)`, TP fills at `take_profit × (1 - slippage)`
- **Margin Check**: Orders rejected if `size_usdt > capital × leverage`

---

## Testing Strategy

After each phase:
1. Create validation Play with synthetic data
2. Run backtest with real DuckDB data (BTCUSDT)
3. Verify fills match expected behavior
4. Add to forge smoke tests

**Success Criteria:**
- All validation Plays pass normalization
- Backtests complete without errors
- Fill prices match expected logic
- Order state transitions are correct
