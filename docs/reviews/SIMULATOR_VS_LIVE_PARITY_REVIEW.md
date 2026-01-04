# Simulator vs Live Parity Review

> **Date**: 2026-01-04
> **Goal**: Full simulation parity with Bybit live execution capabilities
> **Status**: Significant gaps identified

---

## Executive Summary

The current simulator (`SimulatedExchange`) implements **~15% of Bybit's live trading capabilities**. While the core backtest loop works well for simple market-order strategies with attached TP/SL, it cannot simulate the full range of order types and position management features available in live trading.

| Category | Live Capabilities | Simulator Support | Gap |
|----------|-------------------|-------------------|-----|
| Order Types | 4 types | 1 type (partial) | 75% missing |
| Order Lifecycle | Full | Minimal | 80% missing |
| Position Management | Full | Basic | 70% missing |
| Risk Controls | Full | Partial | 50% missing |
| Advanced Features | Many | None | 100% missing |

---

## Detailed Capability Matrix

### 1. Order Types

| Order Type | Live | Simulator | Notes |
|------------|------|-----------|-------|
| **Market** | ✅ | ✅ | Works, fills at next bar open |
| **Market + TP/SL** | ✅ | ✅ | TP/SL attached to position |
| **Limit** | ✅ | ❌ | `OrderType.LIMIT` defined but not implemented |
| **Limit + TP/SL** | ✅ | ❌ | - |
| **Stop Market** | ✅ | ❌ | `OrderType.STOP_MARKET` defined but not implemented |
| **Stop Limit** | ✅ | ❌ | `OrderType.STOP_LIMIT` defined but not implemented |

**Live Code** (`order_tools.py`):
```python
# Available in live
market_buy_tool()
market_sell_tool()
market_buy_with_tpsl_tool()
market_sell_with_tpsl_tool()
limit_buy_tool()           # ❌ No simulator equivalent
limit_sell_tool()          # ❌ No simulator equivalent
stop_market_buy_tool()     # ❌ No simulator equivalent
stop_market_sell_tool()    # ❌ No simulator equivalent
stop_limit_buy_tool()      # ❌ No simulator equivalent
stop_limit_sell_tool()     # ❌ No simulator equivalent
```

**Simulator Code** (`exchange.py:232`):
```python
def submit_order(
    self,
    side: str,
    size_usdt: float,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    timestamp: datetime | None = None,
) -> OrderId | None:
    # ONLY creates MARKET orders
    # No limit_price parameter
    # No trigger_price parameter
    # No order_type parameter
```

---

### 2. Time-in-Force Options

| TIF | Live | Simulator | Description |
|-----|------|-----------|-------------|
| **GTC** | ✅ | ❌ | Good Till Cancel |
| **IOC** | ✅ | ❌ | Immediate or Cancel |
| **FOK** | ✅ | ❌ | Fill or Kill |
| **PostOnly** | ✅ | ❌ | Maker only (reject if would take) |

**Impact**: Cannot simulate maker vs taker fee scenarios, cannot test IOC/FOK strategies.

---

### 3. Order Management

| Feature | Live | Simulator | Notes |
|---------|------|-----------|-------|
| **Submit Order** | ✅ | ✅ (market only) | - |
| **Cancel Order** | ✅ | ✅ | `cancel_pending_order()` |
| **Amend Order** | ✅ | ❌ | Cannot change price/qty of pending |
| **Get Open Orders** | ✅ | ⚠️ | Only 1 pending order tracked |
| **Batch Create (10)** | ✅ | ❌ | - |
| **Batch Amend (10)** | ✅ | ❌ | - |
| **Batch Cancel (10)** | ✅ | ❌ | - |
| **Order Link ID** | ✅ | ❌ | Custom order references |

**Live Code** (`order_tools.py`):
```python
amend_order_tool(
    symbol, order_id, order_link_id,
    qty, price, take_profit, stop_loss, trigger_price
)
batch_market_orders_tool(orders)   # Up to 10
batch_limit_orders_tool(orders)    # Up to 10
batch_cancel_orders_tool(orders)   # Up to 10
```

**Simulator Gap**: Only tracks single `pending_order: Order | None`

---

### 4. Position Model

| Feature | Live | Simulator | Notes |
|---------|------|-----------|-------|
| **Single Position** | ✅ | ✅ | Current model |
| **Position Scaling (Add)** | ✅ | ❌ | Cannot add to position |
| **Partial Close (%)** | ✅ | ❌ | Must close 100% |
| **Partial Close (qty)** | ✅ | ❌ | - |
| **Position Layers** | ✅ | ❌ | No layer tracking |
| **Avg Entry Price** | ✅ | ⚠️ | Only for single entry |
| **Reduce Only Orders** | ✅ | ❌ | - |

**Live Code** (`order_tools.py`):
```python
partial_close_position_tool(
    symbol,
    close_percent,    # 0-100%
    price=None,       # Optional limit price
)
```

**Simulator Position** (`types.py:122`):
```python
@dataclass
class Position:
    # Single entry - no layers
    entry_price: float
    size: float
    size_usdt: float
    # No partial close support
    # No add-to-position support
```

---

### 5. TP/SL Features

| Feature | Live | Simulator | Notes |
|---------|------|-----------|-------|
| **Basic TP/SL** | ✅ | ✅ | Attached to position |
| **TP/SL Mode: Full** | ✅ | ✅ | Close entire position |
| **TP/SL Mode: Partial** | ✅ | ❌ | Close portion at level |
| **TP/SL Order Type: Market** | ✅ | ✅ | - |
| **TP/SL Order Type: Limit** | ✅ | ❌ | `tp_limit_price`, `sl_limit_price` |
| **Trigger By: LastPrice** | ✅ | ✅ | Default |
| **Trigger By: MarkPrice** | ✅ | ⚠️ | Uses mark for liquidation |
| **Trigger By: IndexPrice** | ✅ | ❌ | - |
| **Modify TP/SL** | ✅ | ❌ | Cannot amend after entry |
| **Trailing Stop** | ✅ | ❌ | - |
| **Active Price (Trailing)** | ✅ | ❌ | - |

**Live Code** (`bybit_trading.py:302`):
```python
def set_trading_stop(
    symbol,
    take_profit=None,
    stop_loss=None,
    trailing_stop=None,      # ❌ Not in simulator
    active_price=None,       # ❌ Not in simulator
    tpsl_mode="Full",        # ❌ Partial not supported
    tp_size=None,            # ❌ Partial TP size
    sl_size=None,            # ❌ Partial SL size
    tp_limit_price=None,     # ❌ Limit TP
    sl_limit_price=None,     # ❌ Limit SL
    tp_order_type="Market",
    sl_order_type="Market",
)
```

---

### 6. Conditional Orders (Triggers)

| Feature | Live | Simulator | Notes |
|---------|------|-----------|-------|
| **Trigger Direction: Rise** | ✅ | ❌ | Buy when price rises to X |
| **Trigger Direction: Fall** | ✅ | ❌ | Sell when price falls to X |
| **Trigger By: LastPrice** | ✅ | ❌ | - |
| **Trigger By: MarkPrice** | ✅ | ❌ | - |
| **Trigger By: IndexPrice** | ✅ | ❌ | - |
| **Stop → Market** | ✅ | ❌ | - |
| **Stop → Limit** | ✅ | ❌ | - |

**Live Code** (`bybit_trading.py:262`):
```python
def create_conditional_order(
    symbol, side, qty,
    trigger_price,
    trigger_direction,    # 1=rise, 2=fall
    order_type="Market",  # or "Limit"
    price=None,           # Limit price if order_type=Limit
    trigger_by="LastPrice",
)
```

---

### 7. Margin & Leverage

| Feature | Live | Simulator | Notes |
|---------|------|-----------|-------|
| **Set Leverage** | ✅ | ✅ | Via config |
| **Isolated Margin** | ✅ | ✅ | Only mode supported |
| **Cross Margin** | ✅ | ❌ | Explicitly rejected |
| **Switch Margin Mode** | ✅ | ❌ | - |
| **Add Position Margin** | ✅ | ❌ | - |
| **Reduce Position Margin** | ✅ | ❌ | - |
| **Auto Add Margin** | ✅ | ❌ | - |
| **Risk Limit Tiers** | ✅ | ❌ | - |

---

### 8. Position Modes

| Feature | Live | Simulator | Notes |
|---------|------|-----------|-------|
| **One-Way Mode** | ✅ | ✅ | Current behavior |
| **Hedge Mode** | ✅ | ❌ | Long + Short simultaneously |
| **Switch Position Mode** | ✅ | ❌ | - |

---

### 9. Advanced Features

| Feature | Live | Simulator | Notes |
|---------|------|-----------|-------|
| **Disconnect Cancel All (DCP)** | ✅ | ❌ | Safety feature |
| **Close On Trigger** | ✅ | ❌ | - |
| **Order Link ID** | ✅ | ❌ | Custom references |
| **Position Idx** | ✅ | ❌ | For hedge mode |

---

## Current Simulator Architecture

### What Works Well

```
┌─────────────────────────────────────────────────────────────────┐
│                    SimulatedExchange                            │
├─────────────────────────────────────────────────────────────────┤
│  ✅ Market order entry at next bar open                        │
│  ✅ Slippage model (configurable BPS)                          │
│  ✅ TP/SL checking against bar OHLC                            │
│  ✅ 1m granular TP/SL checking (optional)                      │
│  ✅ Funding rate application                                    │
│  ✅ Liquidation checking                                        │
│  ✅ Bybit-aligned margin model (IMR, MMR)                      │
│  ✅ Fee calculation (taker)                                     │
│  ✅ MAE/MFE tracking                                            │
│  ✅ Trade artifact recording                                    │
└─────────────────────────────────────────────────────────────────┘
```

### What's Missing

```
┌─────────────────────────────────────────────────────────────────┐
│                    GAPS                                         │
├─────────────────────────────────────────────────────────────────┤
│  ❌ Limit order book (pending orders by price)                 │
│  ❌ Stop order tracking (trigger conditions)                   │
│  ❌ Multiple pending orders                                     │
│  ❌ Order amendment                                             │
│  ❌ Partial position closes                                     │
│  ❌ Position scaling (add to position)                         │
│  ❌ Trailing stops                                              │
│  ❌ Time-in-force simulation                                    │
│  ❌ Maker fee model                                             │
│  ❌ Partial fills                                               │
│  ❌ Order expiry (TTL)                                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## Gap Analysis by Strategy Type

| Strategy Type | Can Simulate? | Gaps |
|---------------|---------------|------|
| Simple trend following (market orders) | ✅ Yes | None |
| Mean reversion with limit entries | ❌ No | Limit orders |
| Breakout with stop entries | ❌ No | Stop orders |
| Scale-in strategies | ❌ No | Position layers |
| Partial TP strategies | ❌ No | Partial close |
| Grid trading | ❌ No | Multiple limits |
| DCA strategies | ❌ No | Position scaling |
| Trailing stop strategies | ❌ No | Trailing stops |

---

## Implementation Roadmap

### Phase 1: Limit Orders (High Priority)

**Scope**: Basic limit order support

```python
# New submit_order signature
def submit_order(
    self,
    side: str,
    size_usdt: float,
    order_type: OrderType = OrderType.MARKET,  # NEW
    limit_price: float | None = None,           # NEW
    stop_loss: float | None = None,
    take_profit: float | None = None,
    timestamp: datetime | None = None,
) -> OrderId | None:
```

**Changes Required**:
- [ ] `PendingOrderBook` class for multiple orders
- [ ] `LimitFillSimulator` for fill logic
- [ ] Fill model configuration (touch/through/volume)
- [ ] Order aging and TTL

**Effort**: Medium (2-3 days)

---

### Phase 2: Stop Orders (High Priority)

**Scope**: Conditional order triggers

```python
# New submit_stop_order method
def submit_stop_order(
    self,
    side: str,
    size_usdt: float,
    trigger_price: float,
    trigger_direction: int,  # 1=rise, 2=fall
    order_type: OrderType = OrderType.MARKET,
    limit_price: float | None = None,
) -> OrderId | None:
```

**Changes Required**:
- [ ] Stop order tracking in `PendingOrderBook`
- [ ] Trigger condition checking per bar
- [ ] Conversion to market/limit on trigger

**Effort**: Medium (1-2 days)

---

### Phase 3: Position Scaling (High Priority)

**Scope**: Add to and partially close positions

```python
# New ScaledPosition class
@dataclass
class ScaledPosition:
    layers: list[PositionLayer]

    def add_layer(self, entry_price, size_usdt): ...
    def remove_pct(self, pct, method="fifo"): ...

    @property
    def avg_entry_price(self) -> float: ...
    @property
    def total_size_usdt(self) -> float: ...
```

**Changes Required**:
- [ ] Replace `Position` with `ScaledPosition`
- [ ] Layer-based PnL calculation
- [ ] Partial close via percentage
- [ ] FIFO/LIFO/proportional exit methods

**Effort**: Medium (2-3 days)

---

### Phase 4: Order Amendment (Medium Priority)

**Scope**: Modify pending orders

```python
def amend_order(
    self,
    order_id: str,
    new_price: float | None = None,
    new_size: float | None = None,
) -> bool:
```

**Changes Required**:
- [ ] Order lookup by ID
- [ ] Price/size modification
- [ ] Re-sorting in order book

**Effort**: Low (1 day)

---

### Phase 5: Trailing Stops (Medium Priority)

**Scope**: Dynamic stop loss adjustment

```python
@dataclass
class TrailingStop:
    distance: float        # Distance from peak
    active_price: float    # Price at which trailing activates
    current_stop: float    # Current stop level

    def update(self, current_price: float) -> float:
        """Update stop level based on price movement."""
```

**Changes Required**:
- [ ] Trailing stop state per position
- [ ] Per-bar trailing update logic
- [ ] Activation price logic

**Effort**: Medium (1-2 days)

---

### Phase 6: Time-in-Force (Low Priority)

**Scope**: Order lifecycle options

| TIF | Simulation Logic |
|-----|------------------|
| GTC | Keep in book until filled/cancelled |
| IOC | Fill what's possible on submission bar, cancel rest |
| FOK | Fill entire order or reject |
| PostOnly | Reject if would cross spread |

**Effort**: Low (1 day)

---

### Phase 7: Partial Fills (Low Priority)

**Scope**: Volume-based fill simulation

```python
@dataclass
class FillResult:
    filled: bool
    fill_price: float
    filled_size: float
    remaining_size: float  # For partial fills
    partial: bool
```

**Effort**: Medium (1-2 days)

---

## Priority Matrix

| Feature | Strategy Impact | Implementation Effort | Priority |
|---------|-----------------|----------------------|----------|
| Limit orders | High | Medium | **P1** |
| Stop orders | High | Medium | **P1** |
| Position scaling | High | Medium | **P1** |
| Partial close | High | Low | **P1** |
| Order amendment | Medium | Low | P2 |
| Trailing stops | Medium | Medium | P2 |
| Time-in-force | Low | Low | P3 |
| Partial fills | Low | Medium | P3 |
| Hedge mode | Low | High | P4 |
| Cross margin | Low | High | P4 |

---

## Recommended Next Steps

### Immediate (This Week)

1. **Create `PendingOrderBook`** class to replace single `pending_order`
2. **Extend `submit_order()`** to accept `order_type` and `limit_price`
3. **Implement basic limit fill logic** (touch model)

### Short Term (This Month)

4. **Add stop order support** with trigger conditions
5. **Implement `ScaledPosition`** for position layering
6. **Add partial close** capability

### Medium Term (Next Quarter)

7. **Trailing stop simulation**
8. **Order amendment**
9. **Volume-weighted fill model**

---

## Test Coverage Requirements

Each new feature needs:

1. **Validation IdeaCard** in `configs/idea_cards/_validation/`
2. **Unit test scenarios** via CLI smoke tests
3. **Parity check** vs live behavior documentation

### Proposed Validation Cards

| Card | Feature |
|------|---------|
| V_200_limit_basic.yml | Basic limit order fill |
| V_201_limit_no_fill.yml | Limit order that doesn't fill |
| V_202_stop_market.yml | Stop market trigger |
| V_203_stop_limit.yml | Stop limit trigger and fill |
| V_210_scale_in.yml | Position scaling entry |
| V_211_partial_exit.yml | Partial position close |
| V_220_trailing_stop.yml | Trailing stop activation |

---

## References

- Live order tools: `src/tools/order_tools.py`
- Bybit trading methods: `src/exchanges/bybit_trading.py`
- Simulator exchange: `src/backtest/sim/exchange.py`
- Simulator types: `src/backtest/sim/types.py`
- Limit orders spec: `docs/specs/LIMIT_ORDERS_AND_SCALING.md`
