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
| **Market** | Yes | Yes | Works, fills at next bar open |
| **Market + TP/SL** | Yes | Yes | TP/SL attached to position |
| **Limit** | Yes | No | `OrderType.LIMIT` defined but not implemented |
| **Limit + TP/SL** | Yes | No | - |
| **Stop Market** | Yes | No | `OrderType.STOP_MARKET` defined but not implemented |
| **Stop Limit** | Yes | No | `OrderType.STOP_LIMIT` defined but not implemented |

**Live Code** (`order_tools.py`):
```python
# Available in live
market_buy_tool()
market_sell_tool()
market_buy_with_tpsl_tool()
market_sell_with_tpsl_tool()
limit_buy_tool()           # No simulator equivalent
limit_sell_tool()          # No simulator equivalent
stop_market_buy_tool()     # No simulator equivalent
stop_market_sell_tool()    # No simulator equivalent
stop_limit_buy_tool()      # No simulator equivalent
stop_limit_sell_tool()     # No simulator equivalent
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
| **GTC** | Yes | No | Good Till Cancel |
| **IOC** | Yes | No | Immediate or Cancel |
| **FOK** | Yes | No | Fill or Kill |
| **PostOnly** | Yes | No | Maker only (reject if would take) |

**Impact**: Cannot simulate maker vs taker fee scenarios, cannot test IOC/FOK strategies.

---

### 3. Order Management

| Feature | Live | Simulator | Notes |
|---------|------|-----------|-------|
| **Submit Order** | Yes | Yes (market only) | - |
| **Cancel Order** | Yes | Yes | `cancel_pending_order()` |
| **Amend Order** | Yes | No | Cannot change price/qty of pending |
| **Get Open Orders** | Yes | Partial | Only 1 pending order tracked |
| **Batch Create (10)** | Yes | No | - |
| **Batch Amend (10)** | Yes | No | - |
| **Batch Cancel (10)** | Yes | No | - |
| **Order Link ID** | Yes | No | Custom order references |

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
| **Single Position** | Yes | Yes | Current model |
| **Position Scaling (Add)** | Yes | No | Cannot add to position |
| **Partial Close (%)** | Yes | No | Must close 100% |
| **Partial Close (qty)** | Yes | No | - |
| **Position Layers** | Yes | No | No layer tracking |
| **Avg Entry Price** | Yes | Partial | Only for single entry |
| **Reduce Only Orders** | Yes | No | - |

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
| **Basic TP/SL** | Yes | Yes | Attached to position |
| **TP/SL Mode: Full** | Yes | Yes | Close entire position |
| **TP/SL Mode: Partial** | Yes | No | Close portion at level |
| **TP/SL Order Type: Market** | Yes | Yes | - |
| **TP/SL Order Type: Limit** | Yes | No | `tp_limit_price`, `sl_limit_price` |
| **Trigger By: LastPrice** | Yes | Yes | Default |
| **Trigger By: MarkPrice** | Yes | Partial | Uses mark for liquidation |
| **Trigger By: IndexPrice** | Yes | No | - |
| **Modify TP/SL** | Yes | No | Cannot amend after entry |
| **Trailing Stop** | Yes | No | - |
| **Active Price (Trailing)** | Yes | No | - |

**Live Code** (`bybit_trading.py:302`):
```python
def set_trading_stop(
    symbol,
    take_profit=None,
    stop_loss=None,
    trailing_stop=None,      # Not in simulator
    active_price=None,       # Not in simulator
    tpsl_mode="Full",        # Partial not supported
    tp_size=None,            # Partial TP size
    sl_size=None,            # Partial SL size
    tp_limit_price=None,     # Limit TP
    sl_limit_price=None,     # Limit SL
    tp_order_type="Market",
    sl_order_type="Market",
)
```

---

### 6. Conditional Orders (Triggers)

| Feature | Live | Simulator | Notes |
|---------|------|-----------|-------|
| **Trigger Direction: Rise** | Yes | No | Buy when price rises to X |
| **Trigger Direction: Fall** | Yes | No | Sell when price falls to X |
| **Trigger By: LastPrice** | Yes | No | - |
| **Trigger By: MarkPrice** | Yes | No | - |
| **Trigger By: IndexPrice** | Yes | No | - |
| **Stop → Market** | Yes | No | - |
| **Stop → Limit** | Yes | No | - |

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
| **Set Leverage** | Yes | Yes | Via config |
| **Isolated Margin** | Yes | Yes | Only mode supported |
| **Cross Margin** | Yes | No | Explicitly rejected |
| **Switch Margin Mode** | Yes | No | - |
| **Add Position Margin** | Yes | No | - |
| **Reduce Position Margin** | Yes | No | - |
| **Auto Add Margin** | Yes | No | - |
| **Risk Limit Tiers** | Yes | No | - |

---

### 8. Position Modes

| Feature | Live | Simulator | Notes |
|---------|------|-----------|-------|
| **One-Way Mode** | Yes | Yes | Current behavior |
| **Hedge Mode** | Yes | No | Long + Short simultaneously |
| **Switch Position Mode** | Yes | No | - |

---

### 9. Advanced Features

| Feature | Live | Simulator | Notes |
|---------|------|-----------|-------|
| **Disconnect Cancel All (DCP)** | Yes | No | Safety feature |
| **Close On Trigger** | Yes | No | - |
| **Order Link ID** | Yes | No | Custom references |
| **Position Idx** | Yes | No | For hedge mode |

---

## Current Simulator Architecture

### What Works Well

```
┌─────────────────────────────────────────────────────────────────┐
│                    SimulatedExchange                            │
├─────────────────────────────────────────────────────────────────┤
│  Yes Market order entry at next bar open                        │
│  Yes Slippage model (configurable BPS)                          │
│  Yes TP/SL checking against bar OHLC                            │
│  Yes 1m granular TP/SL checking (optional)                      │
│  Yes Funding rate application                                    │
│  Yes Liquidation checking                                        │
│  Yes Bybit-aligned margin model (IMR, MMR)                      │
│  Yes Fee calculation (taker)                                     │
│  Yes MAE/MFE tracking                                            │
│  Yes Trade artifact recording                                    │
└─────────────────────────────────────────────────────────────────┘
```

### What's Missing

```
┌─────────────────────────────────────────────────────────────────┐
│                    GAPS                                         │
├─────────────────────────────────────────────────────────────────┤
│  No Limit order book (pending orders by price)                 │
│  No Stop order tracking (trigger conditions)                   │
│  No Multiple pending orders                                     │
│  No Order amendment                                             │
│  No Partial position closes                                     │
│  No Position scaling (add to position)                         │
│  No Trailing stops                                              │
│  No Time-in-force simulation                                    │
│  No Maker fee model                                             │
│  No Partial fills                                               │
│  No Order expiry (TTL)                                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## Gap Analysis by Strategy Type

| Strategy Type | Can Simulate? | Gaps |
|---------------|---------------|------|
| Simple trend following (market orders) | Yes | None |
| Mean reversion with limit entries | No | Limit orders |
| Breakout with stop entries | No | Stop orders |
| Scale-in strategies | No | Position layers |
| Partial TP strategies | No | Partial close |
| Grid trading | No | Multiple limits |
| DCA strategies | No | Position scaling |
| Trailing stop strategies | No | Trailing stops |

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

1. **Validation Play** in `tests/validation/plays/`
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
