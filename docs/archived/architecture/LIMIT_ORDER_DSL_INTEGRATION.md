# Limit Order DSL Integration - Full Evaluation

> **Status**: PROPOSAL (2026-01-10)
> **Author**: Claude Code Evaluation

## Executive Summary

The TRADE simulator engine has **complete limit order support** at the execution layer, but the **DSL Actions language cannot express limit orders**. This document evaluates how to bridge this gap with DSL extensions, implementation approach, and use cases.

**Key Finding**: Integration requires changes at 4 layers, but all infrastructure already exists.

---

## 1. Current State Analysis

### 1.1 What Works

| Component | Status | Evidence |
|-----------|--------|----------|
| `OrderType` enum | ✅ Complete | `MARKET`, `LIMIT`, `STOP_MARKET`, `STOP_LIMIT` |
| `Order` dataclass | ✅ Complete | Has `limit_price`, `time_in_force`, `trigger_price` |
| `ExecutionModel.fill_limit_order()` | ✅ Complete | Maker fees, TIF handling, price improvement |
| `SimulatedExchange.submit_limit_order()` | ✅ Complete | Full implementation, never called |
| `SimulatedExchange.submit_stop_order()` | ✅ Complete | Stop-market and stop-limit |

### 1.2 The Gap

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         CURRENT FLOW                                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Play YAML          DSL Parser         Intent              Signal        │
│  ─────────         ──────────         ──────              ──────         │
│  actions:     →    parse_intent() →   action="entry_long" → direction="LONG"
│    emit:                              metadata={sl,tp}       metadata={sl,tp}
│      action:                                                              │
│      entry_long                                                           │
│                                                                          │
│                         ↓                                                │
│                                                                          │
│  Engine._process_signal()                                                │
│  ────────────────────────                                                │
│  exchange.submit_order(     ← HARDCODED TO MARKET                        │
│      side, size_usdt,                                                    │
│      stop_loss, take_profit                                              │
│  )                                                                       │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

**The problem**: `emit:` only supports `action:` and metadata. There's no way to specify:
- Order type (limit vs market)
- Limit price (static or dynamic)
- Time-in-force (GTC, IOC, FOK, POST_ONLY)
- Trigger price for stop orders

---

## 2. DSL Extension Design

### 2.1 Proposed Emit Syntax

**Design Goal**: Backward compatible, explicit, fail-loud.

```yaml
# Current syntax (market order - unchanged)
emit:
  - action: entry_long

# Extended syntax (limit order)
emit:
  - action: entry_long
    order_type: limit                    # NEW: "market" | "limit" | "stop_market" | "stop_limit"
    limit_price: {feature_id: "ema_21"}  # NEW: Dynamic price from feature
    time_in_force: GTC                   # NEW: GTC | IOC | FOK | PostOnly

# Static limit price
emit:
  - action: entry_long
    order_type: limit
    limit_price: 42000.0                 # Static price

# Arithmetic limit price
emit:
  - action: entry_long
    order_type: limit
    limit_price:                         # Arithmetic expression
      op: "-"
      left: {feature_id: "close"}
      right: {feature_id: "atr_14"}

# Stop-limit order
emit:
  - action: entry_long
    order_type: stop_limit
    trigger_price: {feature_id: "swing", field: "high_level"}
    trigger_direction: 1                 # 1=rises_to, 2=falls_to
    limit_price:
      op: "+"
      left: {feature_id: "swing", field: "high_level"}
      right: 10.0
```

### 2.2 Price Expression Types

| Type | Syntax | Example |
|------|--------|---------|
| Static | `limit_price: 42000.0` | Fixed price |
| Feature | `limit_price: {feature_id: "ema_21"}` | Indicator value |
| Structure | `limit_price: {feature_id: "fib", field: "level_0.618"}` | Structure output |
| Arithmetic | `limit_price: {op: "-", left: ..., right: ...}` | Computed price |
| Built-in | `limit_price: {feature_id: "close"}` | Bar OHLCV |

### 2.3 Shorthand Syntax (Convenience)

```yaml
# Full form
emit:
  - action: entry_long
    order_type: limit
    limit_price: {feature_id: "ema_21"}

# Shorthand: limit_at implies order_type: limit
emit:
  - action: entry_long
    limit_at: "ema_21"                   # Shorthand for above

# Shorthand with offset
emit:
  - action: entry_long
    limit_at: "ema_21 - atr_14"          # String parsed as arithmetic
```

---

## 3. Implementation Approach

### 3.1 Integration Points (4 Layers)

```
┌─────────────────────────────────────────────────────────────────────────┐
│ LAYER 1: DSL Parser (src/backtest/rules/dsl_parser.py)                  │
├─────────────────────────────────────────────────────────────────────────┤
│ parse_intent() → extract order_type, limit_price, time_in_force         │
│ parse_price_expr() → NEW: parse limit_price expressions                 │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ LAYER 2: Intent/Signal (src/backtest/rules/strategy_blocks.py)          │
├─────────────────────────────────────────────────────────────────────────┤
│ Intent.metadata now carries:                                            │
│   - order_type: str                                                     │
│   - limit_price_expr: PriceExpr | float | None                          │
│   - trigger_price_expr: PriceExpr | float | None                        │
│   - time_in_force: str                                                  │
│   - trigger_direction: int | None                                       │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ LAYER 3: Signal Evaluation (src/backtest/engine_factory.py)             │
├─────────────────────────────────────────────────────────────────────────┤
│ play_strategy():                                                        │
│   1. Evaluate price expressions against snapshot                        │
│   2. Resolve dynamic prices to float values                             │
│   3. Pass resolved values in Signal.metadata                            │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ LAYER 4: Order Dispatch (src/backtest/engine.py)                        │
├─────────────────────────────────────────────────────────────────────────┤
│ _process_signal():                                                      │
│   order_type = signal.metadata.get("order_type", "market")              │
│   if order_type == "market":                                            │
│       exchange.submit_order(...)                                        │
│   elif order_type == "limit":                                           │
│       exchange.submit_limit_order(limit_price=..., time_in_force=...)   │
│   elif order_type == "stop_market":                                     │
│       exchange.submit_stop_order(trigger_price=..., limit_price=None)   │
│   elif order_type == "stop_limit":                                      │
│       exchange.submit_stop_order(trigger_price=..., limit_price=...)    │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.2 New Types Required

```python
# src/backtest/rules/dsl_nodes/price_expr.py (NEW FILE)

from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class PriceExpr:
    """
    Price expression for limit/trigger prices.

    Resolved at signal time against snapshot.
    """
    pass


@dataclass(frozen=True)
class StaticPrice(PriceExpr):
    """Fixed price value."""
    value: float


@dataclass(frozen=True)
class FeaturePrice(PriceExpr):
    """Price from feature/structure value."""
    feature_id: str
    field: str | None = None


@dataclass(frozen=True)
class ArithmeticPrice(PriceExpr):
    """Computed price: left op right."""
    op: str  # "+", "-", "*", "/"
    left: PriceExpr | float
    right: PriceExpr | float


def resolve_price(expr: PriceExpr, snapshot: "RuntimeSnapshotView") -> float:
    """Resolve price expression to float using snapshot values."""
    if isinstance(expr, StaticPrice):
        return expr.value
    elif isinstance(expr, FeaturePrice):
        return snapshot.get_feature_value(expr.feature_id, expr.field)
    elif isinstance(expr, ArithmeticPrice):
        left = resolve_price(expr.left, snapshot) if isinstance(expr.left, PriceExpr) else expr.left
        right = resolve_price(expr.right, snapshot) if isinstance(expr.right, PriceExpr) else expr.right
        match expr.op:
            case "+": return left + right
            case "-": return left - right
            case "*": return left * right
            case "/": return left / right
            case _: raise ValueError(f"Invalid price op: {expr.op}")
    else:
        raise TypeError(f"Unknown PriceExpr type: {type(expr)}")
```

### 3.3 Parser Changes

```python
# src/backtest/rules/dsl_parser.py

def parse_intent(data: dict) -> Intent:
    """Parse emit item into Intent."""
    action = data.get("action")
    if not action:
        raise ValueError("Intent requires 'action'")

    metadata = {}

    # Existing fields
    if "metadata" in data:
        metadata.update(data["metadata"])

    # NEW: Order type (default: market)
    order_type = data.get("order_type", "market")
    if order_type not in ("market", "limit", "stop_market", "stop_limit"):
        raise ValueError(f"Invalid order_type: {order_type}")
    metadata["order_type"] = order_type

    # NEW: Limit price
    if "limit_price" in data:
        metadata["limit_price_expr"] = parse_price_expr(data["limit_price"])
    elif order_type == "limit":
        raise ValueError("order_type 'limit' requires 'limit_price'")

    # NEW: Trigger price (for stop orders)
    if "trigger_price" in data:
        metadata["trigger_price_expr"] = parse_price_expr(data["trigger_price"])
    elif order_type in ("stop_market", "stop_limit"):
        raise ValueError(f"order_type '{order_type}' requires 'trigger_price'")

    # NEW: Trigger direction
    if "trigger_direction" in data:
        metadata["trigger_direction"] = data["trigger_direction"]

    # NEW: Time in force
    if "time_in_force" in data:
        metadata["time_in_force"] = data["time_in_force"]

    # NEW: Shorthand - limit_at
    if "limit_at" in data:
        metadata["order_type"] = "limit"
        metadata["limit_price_expr"] = parse_price_shorthand(data["limit_at"])

    percent = data.get("percent", 100.0)

    return Intent(action=action, metadata=metadata, percent=percent)


def parse_price_expr(data) -> PriceExpr:
    """Parse price expression from YAML."""
    if isinstance(data, (int, float)):
        return StaticPrice(value=float(data))
    elif isinstance(data, dict):
        if "feature_id" in data:
            return FeaturePrice(
                feature_id=data["feature_id"],
                field=data.get("field"),
            )
        elif "op" in data:
            return ArithmeticPrice(
                op=data["op"],
                left=parse_price_expr(data["left"]),
                right=parse_price_expr(data["right"]),
            )
        else:
            raise ValueError(f"Invalid price expr: {data}")
    else:
        raise ValueError(f"Invalid price type: {type(data)}")
```

### 3.4 Engine Changes

```python
# src/backtest/engine.py

def _process_signal(self, signal: Signal, bar: CanonicalBar, snapshot, signal_ts=None):
    """Process signal - dispatch to appropriate order type."""
    # ... existing risk checks and sizing ...

    # Extract order parameters from metadata
    metadata = signal.metadata or {}
    order_type = metadata.get("order_type", "market")
    time_in_force = metadata.get("time_in_force", "GTC")

    # Resolve dynamic prices
    limit_price = None
    trigger_price = None
    trigger_direction = metadata.get("trigger_direction", 1)

    if "limit_price_expr" in metadata:
        limit_price = resolve_price(metadata["limit_price_expr"], snapshot)
    if "trigger_price_expr" in metadata:
        trigger_price = resolve_price(metadata["trigger_price_expr"], snapshot)

    # Dispatch to appropriate exchange method
    order_timestamp = signal_ts or bar.ts_close

    match order_type:
        case "market":
            exchange.submit_order(
                side=side,
                size_usdt=size_usdt,
                stop_loss=stop_loss,
                take_profit=take_profit,
                timestamp=order_timestamp,
            )
        case "limit":
            exchange.submit_limit_order(
                side=side,
                size_usdt=size_usdt,
                limit_price=limit_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                time_in_force=time_in_force,
                timestamp=order_timestamp,
            )
        case "stop_market":
            exchange.submit_stop_order(
                side=side,
                size_usdt=size_usdt,
                trigger_price=trigger_price,
                trigger_direction=trigger_direction,
                limit_price=None,
                stop_loss=stop_loss,
                take_profit=take_profit,
                timestamp=order_timestamp,
            )
        case "stop_limit":
            exchange.submit_stop_order(
                side=side,
                size_usdt=size_usdt,
                trigger_price=trigger_price,
                trigger_direction=trigger_direction,
                limit_price=limit_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                timestamp=order_timestamp,
            )
```

---

## 4. Use Cases

### 4.1 Mean Reversion with Limit Entry

**Strategy**: Buy at EMA when price pulls back, not at market.

```yaml
name: "mean_reversion_limit"
tf: "15m"
symbol: "BTCUSDT"

features:
  ema_21:
    indicator: ema
    params: {length: 21}
  rsi_14:
    indicator: rsi
    params: {length: 14}

actions:
  entry_long:
    all:
      - ["rsi_14", "<", 35]              # Oversold condition
      - ["close", ">", "ema_21"]         # Price above EMA (uptrend)
    emit:
      - action: entry_long
        order_type: limit
        limit_price: {feature_id: "ema_21"}  # Limit at EMA
        time_in_force: GTC

  exit_long:
    - ["rsi_14", ">", 70]
```

**Behavior**:
1. When RSI < 35 and close > EMA21, submit limit buy at EMA21 price
2. Order stays in book (GTC) until price dips to EMA21
3. If price never reaches EMA, order remains unfilled
4. Exit on RSI > 70 (market order)

### 4.2 Breakout with Stop Entry

**Strategy**: Enter long when price breaks above swing high.

```yaml
name: "breakout_stop_entry"
tf: "15m"
symbol: "BTCUSDT"

structures:
  swing:
    detector: swing
    params: {left: 5, right: 5}

features:
  atr_14:
    indicator: atr
    params: {length: 14}

actions:
  entry_long:
    all:
      - ["swing", "high_level", ">", 0]  # Valid swing high exists
    emit:
      - action: entry_long
        order_type: stop_market
        trigger_price: {feature_id: "swing", field: "high_level"}
        trigger_direction: 1              # Trigger when price rises to level

  exit_long:
    - ["close", "<", "swing", "low_level"]
```

**Behavior**:
1. Submit stop order above swing high
2. When price rises to swing high, trigger converts to market order
3. Entry happens on breakout (not before)

### 4.3 Fibonacci Zone Entry with Limit

**Strategy**: Enter at Fib retracement level with tight limit.

```yaml
name: "fib_zone_limit"
tf: "1h"
symbol: "ETHUSDT"

structures:
  swing:
    detector: swing
    params: {left: 10, right: 10}
  fib:
    detector: fibonacci
    depends_on: {swing: swing}
    params:
      levels: [0.618, 0.786]
      mode: retracement

features:
  rsi_14:
    indicator: rsi
    params: {length: 14}

actions:
  entry_long:
    all:
      - ["close", "near_pct", "fib.level_0.618", 0.01]  # Within 1% of fib
      - ["rsi_14", "<", 40]
    emit:
      - action: entry_long
        order_type: limit
        limit_price: {feature_id: "fib", field: "level_0.618"}
        time_in_force: IOC               # Fill immediately or cancel
```

**Behavior**:
1. When price is near 0.618 fib and RSI < 40, submit IOC limit at fib level
2. If not filled immediately (price moved), order cancelled
3. Prevents chasing - only enters at desired level

### 4.4 Scaled Entry (Multiple Limits)

**Strategy**: Scale into position with multiple limit orders.

```yaml
name: "scaled_entry"
tf: "4h"
symbol: "BTCUSDT"

features:
  ema_50:
    indicator: ema
    params: {length: 50}
  atr_14:
    indicator: atr
    params: {length: 14}

actions:
  entry_long:
    all:
      - ["close", ">", "ema_50"]
    emit:
      # Order 1: 40% at EMA
      - action: entry_long
        order_type: limit
        limit_price: {feature_id: "ema_50"}
        percent: 40
      # Order 2: 30% at EMA - 0.5*ATR
      - action: entry_long
        order_type: limit
        limit_price:
          op: "-"
          left: {feature_id: "ema_50"}
          right:
            op: "*"
            left: {feature_id: "atr_14"}
            right: 0.5
        percent: 30
      # Order 3: 30% at EMA - 1*ATR
      - action: entry_long
        order_type: limit
        limit_price:
          op: "-"
          left: {feature_id: "ema_50"}
          right: {feature_id: "atr_14"}
        percent: 30
```

**Behavior**:
1. Submit 3 limit orders at different levels
2. 40% at EMA, 30% at EMA-0.5ATR, 30% at EMA-1ATR
3. Builds position gradually on pullback

### 4.5 Limit Take Profit (Exit)

**Strategy**: Exit at specific price level, not market.

```yaml
name: "limit_take_profit"
tf: "15m"
symbol: "BTCUSDT"

structures:
  swing:
    detector: swing
    params: {left: 5, right: 5}

actions:
  entry_long:
    - ["ema_9", "cross_above", "ema_21"]
    emit:
      - action: entry_long
        order_type: market                # Market entry

  exit_long:
    - ["close", "near_pct", "swing.high_level", 0.005]
    emit:
      - action: exit_long
        order_type: limit
        limit_price: {feature_id: "swing", field: "high_level"}
        time_in_force: GTC
```

### 4.6 Maker-Only Strategy (Fee Optimization)

**Strategy**: Only enter as maker (lower fees).

```yaml
name: "maker_only_entry"
tf: "5m"
symbol: "BTCUSDT"

features:
  vwap:
    indicator: vwap
  atr_14:
    indicator: atr
    params: {length: 14}

actions:
  entry_long:
    all:
      - ["close", "<", "vwap"]           # Price below VWAP
      - ["rsi_14", "<", 40]
    emit:
      - action: entry_long
        order_type: limit
        limit_price:                      # Bid slightly below current
          op: "-"
          left: {feature_id: "close"}
          right:
            op: "*"
            left: {feature_id: "atr_14"}
            right: 0.1
        time_in_force: PostOnly           # Reject if would take liquidity
```

**Behavior**:
1. Submit limit order below current price (maker)
2. PostOnly ensures order is rejected if it would fill immediately
3. Only fills if market comes to your price (0.01% maker fee vs 0.06% taker)

---

## 5. Order Lifecycle & Metrics

### 5.1 Order States to Track

```
PENDING → FILLED (success)
        → CANCELLED (GTC timeout, manual, IOC/FOK)
        → REJECTED (PostOnly, margin, liquidity)
        → EXPIRED (time-based)
```

### 5.2 New Metrics for Limit Orders

| Metric | Description |
|--------|-------------|
| `limit_orders_submitted` | Total limit orders submitted |
| `limit_orders_filled` | Limit orders that filled |
| `limit_fill_rate` | Ratio of filled to submitted |
| `avg_time_to_fill` | Average bars from submit to fill |
| `limit_price_improvement` | Avg better price vs market |
| `maker_fee_savings` | Fee reduction from limit orders |
| `limit_orders_cancelled` | Orders cancelled before fill |
| `limit_orders_expired` | Orders expired without fill |

### 5.3 Trade Record Enhancements

```python
@dataclass
class Trade:
    # Existing fields...

    # NEW: Order execution details
    order_type: str = "market"
    limit_price: float | None = None
    time_in_force: str | None = None
    bars_to_fill: int = 0              # 0 = immediate (market)
    price_improvement: float = 0.0     # Fill price vs market
```

---

## 6. Edge Cases & Considerations

### 6.1 Unfilled Orders

**Problem**: Limit orders may never fill if price doesn't reach limit.

**Solutions**:
1. **GTC with timeout**: Add `expire_after_bars: N` to auto-cancel
2. **Fallback to market**: If unfilled after N bars, convert to market
3. **Trailing limit**: Adjust limit price each bar (advanced)

```yaml
emit:
  - action: entry_long
    order_type: limit
    limit_price: {feature_id: "ema_21"}
    time_in_force: GTC
    expire_after_bars: 10              # Cancel if not filled in 10 bars
    fallback_to_market: true           # Convert to market on expiry
```

### 6.2 Order Management in Position

**Problem**: What happens to unfilled limit orders when position opens via another signal?

**Proposed Behavior**:
1. Entry orders auto-cancelled when position opens
2. Exit orders remain active
3. Configurable via `cancel_on_position: true|false`

### 6.3 Multiple Pending Orders

**Current**: Only one pending order allowed per symbol.

**Proposed**: Allow multiple limit orders (for scaled entries):
- Track array of pending orders
- Fill in price order (best first)
- Aggregate into single position

### 6.4 Partial Fills

**Current**: All-or-nothing fills.

**Proposed** (v2):
- Liquidity-aware partial fills
- Position updates per fill
- Complex for backtesting (needs orderbook data)

**Recommendation**: Skip partial fills in v1, document as future enhancement.

---

## 7. Implementation Phases

### Phase 1: Core Limit Orders (MVP)

**Scope**:
- `order_type: limit` in DSL
- Static and feature-based limit prices
- GTC time-in-force only
- Single limit order per signal

**Files Changed**:
1. `src/backtest/rules/dsl_nodes/price_expr.py` (NEW)
2. `src/backtest/rules/dsl_parser.py` (extend `parse_intent`)
3. `src/backtest/engine.py` (`_process_signal`)
4. `tests/validation/plays/V_140_limit_orders.yml` (NEW)

**Estimated LOC**: ~200

### Phase 2: Stop Orders

**Scope**:
- `order_type: stop_market` and `stop_limit`
- `trigger_price` and `trigger_direction`
- Integration with existing stop trigger logic

**Files Changed**:
1. `src/backtest/rules/dsl_parser.py` (extend)
2. `src/backtest/engine.py` (extend)
3. `tests/validation/plays/V_141_stop_orders.yml` (NEW)

**Estimated LOC**: ~100

### Phase 3: Advanced TIF & Expiry

**Scope**:
- IOC, FOK, PostOnly time-in-force
- `expire_after_bars` option
- Order cancellation metrics

**Files Changed**:
1. Parser and engine extensions
2. Metrics additions

**Estimated LOC**: ~150

### Phase 4: Arithmetic Price Expressions

**Scope**:
- `limit_price: {op: "-", left: ..., right: ...}`
- Full arithmetic DSL support in prices
- Shorthand syntax (`limit_at: "ema_21 - atr_14"`)

**Files Changed**:
1. `parse_price_expr()` extension
2. `resolve_price()` arithmetic support

**Estimated LOC**: ~100

### Phase 5: Scaled Entries (Multiple Orders)

**Scope**:
- Multiple `emit` items with different limit prices
- Order book with multiple pending entries
- Aggregated position from multiple fills

**Complexity**: High - requires order book redesign

---

## 8. Validation Plays

### V_140: Basic Limit Order

```yaml
version: "3.0.0"
name: "V_140_limit_basic"
description: "Validate limit order fills at limit price"
symbol: "BTCUSDT"
tf: "15m"

features:
  ema_20:
    indicator: ema
    params: {length: 20}

actions:
  entry_long:
    - ["close", ">", "ema_20"]
    emit:
      - action: entry_long
        order_type: limit
        limit_price: {feature_id: "ema_20"}

# Expected: Order fills when bar.low <= ema_20
# Expected: Fill price = ema_20 (not bar.open)
```

### V_141: Stop Order Trigger

```yaml
version: "3.0.0"
name: "V_141_stop_trigger"
description: "Validate stop order triggers at trigger price"
symbol: "BTCUSDT"
tf: "15m"

structures:
  swing:
    detector: swing
    params: {left: 3, right: 3}

actions:
  entry_long:
    - ["swing.high_level", ">", 0]
    emit:
      - action: entry_long
        order_type: stop_market
        trigger_price: {feature_id: "swing", field: "high_level"}
        trigger_direction: 1

# Expected: Order triggers when bar.high >= swing.high_level
# Expected: Fill at bar.open of trigger bar
```

---

## 9. Summary

### Feasibility: HIGH

All infrastructure exists. The gap is purely at the DSL/parser layer.

### Effort Estimate

| Phase | Scope | LOC | Complexity |
|-------|-------|-----|------------|
| 1 | Core limit orders | ~200 | Low |
| 2 | Stop orders | ~100 | Low |
| 3 | TIF & expiry | ~150 | Medium |
| 4 | Arithmetic prices | ~100 | Low |
| 5 | Scaled entries | ~300 | High |

**Total**: ~850 LOC for full implementation

### Benefits

1. **Better fills**: Enter at desired prices, not market
2. **Fee savings**: Maker fees 6x lower than taker
3. **Breakout strategies**: Enter on price confirmation
4. **Scaled entries**: Build positions gradually
5. **Live parity**: DSL maps directly to exchange APIs

### Risks

1. **Unfilled orders**: Need clear expiry/cancellation rules
2. **Complexity**: More order states to track
3. **Backtesting realism**: Limit fills assume liquidity exists

---

## 10. Recommendation

**Start with Phase 1** (Core Limit Orders) as MVP:
- Covers 80% of use cases
- Low complexity, high value
- Enables mean reversion and zone strategies
- Foundation for phases 2-5

**Defer scaled entries** (Phase 5) until demand is clear - significant complexity for niche use case.
