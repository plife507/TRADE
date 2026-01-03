# TRADE Backtest Engine Architecture Review

> **Review Date**: January 2026
> **Scope**: Entry logic, signal evaluation, position management, and comparison to industry standards
> **Status**: Complete

---

## Executive Summary

The TRADE backtest engine implements a **hybrid event-driven architecture** that combines:

- **Vectorized indicator computation** (pre-loop, O(n) once)
- **Sequential bar-by-bar evaluation** (in-loop, O(1) per bar)
- **Declarative IdeaCard strategies** (YAML, not Python callbacks)

This design achieves both **performance** (no pandas in hot loop) and **correctness** (structural lookahead prevention), while offering a unique declarative approach that separates strategy logic from execution mechanics.

### Key Strengths

1. **Structural lookahead prevention** - Signals evaluate at bar close, fills execute at next bar open
2. **O(1) hot loop** - Array-backed indicator access, no DataFrame operations
3. **Declarative strategies** - IdeaCards are data, not code
4. **Clean separation of concerns** - Evaluator (conditions) → RiskManager (sizing) → Exchange (execution)

### Comparison to Industry

| Engine | Architecture | Strategy Definition | Order Management |
|--------|-------------|---------------------|------------------|
| **TRADE** | Hybrid (vectorized + event-driven) | Declarative YAML | PendingOrder → Fill |
| VectorBT | Fully vectorized | Array operations | Immediate execution |
| Backtrader | Event-driven | Python `next()` callback | Full broker simulation |
| Zipline | Event-driven | Python `handle_data()` | Order objects |

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Entry Flow Deep Dive](#2-entry-flow-deep-dive)
3. [Signal Evaluation System](#3-signal-evaluation-system)
4. [Position Management](#4-position-management)
5. [Comparison to Industry Engines](#5-comparison-to-industry-engines)
6. [Architectural Paradigms](#6-architectural-paradigms)
7. [Best Practices Adopted](#7-best-practices-adopted)
8. [Unique Differentiators](#8-unique-differentiators)
9. [Recommendations](#9-recommendations)
10. [References](#10-references)

---

## 1. Architecture Overview

### 1.1 System Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           TRADE BACKTEST ENGINE                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐  │
│  │  IdeaCard   │    │  FeedStore  │    │   Engine    │    │  Exchange   │  │
│  │  (YAML)     │    │  (Arrays)   │    │  (Loop)     │    │  (Sim)      │  │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘    └──────┬──────┘  │
│         │                  │                  │                  │         │
│         ▼                  ▼                  ▼                  ▼         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐  │
│  │  Evaluator  │◄───│  Snapshot   │◄───│  Strategy   │───►│  Position   │  │
│  │  (Rules)    │    │  (View)     │    │  (Wrapper)  │    │  (State)    │  │
│  └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Component Responsibilities

| Component | File | Responsibility |
|-----------|------|----------------|
| **IdeaCard** | `src/backtest/idea_card.py` | Declarative strategy definition (rules, risk, sizing) |
| **FeedStore** | `src/backtest/runtime/feed_store.py` | Pre-computed indicator arrays |
| **Engine** | `src/backtest/engine.py` | Main loop orchestration |
| **Evaluator** | `src/backtest/execution_validation.py` | Condition evaluation, SL/TP computation |
| **Snapshot** | `src/backtest/runtime/snapshot_view.py` | O(1) read-only view of current state |
| **Exchange** | `src/backtest/sim/exchange.py` | Order lifecycle, position management |
| **RiskManager** | `src/backtest/engine.py` | Position sizing based on risk profile |

### 1.3 Data Flow

```
[Historical Data] → [FeedStore] → [Indicators Computed]
                                         │
                                         ▼
                    ┌────────────────────────────────────┐
                    │         MAIN LOOP (per bar)        │
                    │                                    │
                    │  1. Get bar (O(1) array access)    │
                    │  2. Process pending orders         │
                    │  3. Check TP/SL stops              │
                    │  4. Build RuntimeSnapshotView      │
                    │  5. Call strategy(snapshot)        │
                    │  6. Process signal (if any)        │
                    │  7. Record equity                  │
                    │                                    │
                    └────────────────────────────────────┘
```

---

## 2. Entry Flow Deep Dive

### 2.1 Complete Entry Pipeline

```
IdeaCard.entry_rules
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ CONDITION EXTRACTION                                            │
│   ├─ indicator_key: "ema_20", "close", "rsi"                   │
│   ├─ tf_role: "exec", "htf", "mtf"                             │
│   ├─ operator: GT, LT, GTE, LTE, EQ, CROSS_ABOVE, CROSS_BELOW  │
│   └─ value: threshold (50) or indicator key ("ema_slow")       │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ SNAPSHOT FEATURE ACCESS (O(1))                                  │
│   snapshot.get_feature(indicator_key, tf_role, offset)         │
│   └─ Returns: float value from pre-computed array              │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ EVALUATOR.EVALUATE()                                            │
│   ├─ IF NOT has_position:                                      │
│   │     FOR rule IN entry_rules:                               │
│   │       IF position_policy.allows(rule.direction):           │
│   │         IF _evaluate_conditions(rule.conditions):          │
│   │           → Compute SL/TP from risk_model                  │
│   │           → RETURN EvaluationResult(ENTRY_LONG/SHORT)      │
│   └─ ELSE: evaluate exit_rules                                 │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ SIGNAL CREATION (engine_factory.py:343-388)                    │
│   Signal(                                                       │
│     direction="LONG",                                          │
│     symbol=idea_card.symbol_universe[0],                       │
│     metadata={"stop_loss": sl_price, "take_profit": tp_price}  │
│   )                                                             │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ ENGINE._PROCESS_SIGNAL() (engine.py:1340-1410)                 │
│   1. Guard: Skip if has_position or has_pending_order          │
│   2. Apply risk policy filter (optional)                       │
│   3. Compute size: risk_manager.size_order(snapshot, signal)   │
│   4. Check minimum size threshold                              │
│   5. Extract SL/TP from signal.metadata                        │
│   6. Call exchange.submit_order(side, size_usdt, sl, tp)       │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ EXCHANGE.SUBMIT_ORDER() (sim/exchange.py:236-270)              │
│   1. Check entries_disabled flag                               │
│   2. Check no existing position or pending order               │
│   3. Create PendingOrder with deterministic ID (order_0001)    │
│   4. Store as self.pending_order                               │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼ [NEXT BAR]
┌─────────────────────────────────────────────────────────────────┐
│ EXCHANGE._FILL_PENDING_ORDER() (sim/exchange.py:419-462)       │
│   1. Execute fill via execution model (apply slippage)         │
│   2. Create Fill object (price=bar.open ± slippage)            │
│   3. Apply entry fee via ledger                                │
│   4. Create Position object with:                              │
│      ├─ position_id: "pos_0001" (deterministic)                │
│      ├─ entry_price: fill.price                                │
│      ├─ entry_time: ts_open (next bar)                         │
│      ├─ stop_loss: from order                                  │
│      ├─ take_profit: from order                                │
│      └─ entry_bar_index: current bar index                     │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Timing Semantics

| Event | Timing | Description |
|-------|--------|-------------|
| **Signal evaluation** | `bar.ts_close` | Closed-candle data only |
| **Order submission** | `bar.ts_close` | Same bar as signal |
| **Order fill** | `next_bar.ts_open` | One bar delay (no lookahead) |
| **Position active** | `next_bar.ts_open` | TP/SL monitoring begins |

### 2.3 Lookahead Prevention

**File**: `src/backtest/engine.py` (lines 966-979)

```python
# ========== LOOKAHEAD GUARD (Phase 3) ==========
# Assert strategy is invoked only at bar close with closed-candle data.
assert snapshot.ts_close == bar.ts_close, (
    f"Lookahead violation: snapshot.ts_close ({snapshot.ts_close}) != "
    f"bar.ts_close ({bar.ts_close})"
)
```

This assertion makes lookahead bias a **structural impossibility** rather than a discipline requirement.

---

## 3. Signal Evaluation System

### 3.1 IdeaCardSignalEvaluator

**File**: `src/backtest/execution_validation.py` (lines 742-842)

The evaluator is the brain of signal generation, converting declarative rules into actionable decisions.

#### Entry vs Exit Decision

```python
def evaluate(
    self,
    snapshot: RuntimeSnapshotView,
    has_position: bool,
    position_side: str | None = None,
) -> EvaluationResult:

    # ENTRY PATH: No position → evaluate entry rules
    if not has_position:
        for rule in signal_rules.entry_rules:
            if position_policy.allows(rule.direction):
                if self._evaluate_conditions(rule.conditions, snapshot):
                    return EvaluationResult(
                        decision=ENTRY_LONG or ENTRY_SHORT,
                        stop_loss_price=computed_sl,
                        take_profit_price=computed_tp,
                    )

    # EXIT PATH: Has position → evaluate exit rules
    else:
        for rule in signal_rules.exit_rules:
            if rule.direction == position_side:
                if self._evaluate_conditions(rule.conditions, snapshot):
                    return EvaluationResult(decision=EXIT)

    return EvaluationResult(decision=NO_ACTION)
```

### 3.2 Condition Logic

#### AND Logic (Within a Rule)

All conditions in a single rule must be true:

```python
def _evaluate_conditions(conditions, snapshot) -> bool:
    for cond in conditions:
        if not evaluate_single_condition(cond, snapshot):
            return False  # ANY failure = rule fails
    return True  # ALL passed
```

#### OR Logic (Between Rules)

First matching rule wins (short-circuit):

```python
for rule in entry_rules:
    if _evaluate_conditions(rule.conditions, snapshot):
        return ENTRY  # First match wins, stop evaluation
```

### 3.3 Supported Operators

| Operator | Symbol | Description | Example |
|----------|--------|-------------|---------|
| `GT` | `>` | Greater than | `close > ema_20` |
| `GTE` | `>=` | Greater than or equal | `rsi >= 50` |
| `LT` | `<` | Less than | `close < ema_20` |
| `LTE` | `<=` | Less than or equal | `rsi <= 30` |
| `EQ` | `==` | Equal (within epsilon) | `direction == 1` |
| `CROSS_ABOVE` | `×↑` | Crosses above | `ema_fast cross_above ema_slow` |
| `CROSS_BELOW` | `×↓` | Crosses below | `ema_fast cross_below ema_slow` |

### 3.4 Stop Loss / Take Profit Computation

**File**: `src/backtest/execution_validation.py` (lines 1031-1113)

| SL Type | Formula | Example |
|---------|---------|---------|
| `percent` | `entry ± (entry × value/100)` | 2% SL |
| `atr_multiple` | `entry ± (atr × value) ± buffer` | 1.5× ATR SL |
| `fixed_points` | `entry ± value` | 50 points SL |

| TP Type | Formula | Example |
|---------|---------|---------|
| `rr_ratio` | `entry ± (sl_distance × value)` | 2:1 RR |
| `percent` | `entry ± (entry × value/100)` | 4% TP |
| `atr_multiple` | `entry ± (atr × value)` | 3× ATR TP |

---

## 4. Position Management

### 4.1 Position State Machine

```
[NO POSITION]
     │
     │ Signal(ENTRY_LONG/SHORT)
     ▼
[PENDING ORDER] ─────────────────────────────┐
     │                                       │
     │ Next bar open (fill)                  │ Rejected
     ▼                                       ▼
[POSITION OPEN] ◄────────────────────── [NO POSITION]
     │
     ├─── TP hit ───────┐
     ├─── SL hit ───────┤
     ├─── Signal(FLAT) ─┤
     └─── Liquidation ──┤
                        ▼
                  [TRADE RECORDED]
                        │
                        ▼
                  [NO POSITION]
```

### 4.2 Position Object

**File**: `src/backtest/sim/types.py` (lines 121-174)

```python
@dataclass
class Position:
    position_id: str          # "pos_0001" (deterministic)
    symbol: str               # "BTCUSDT"
    side: OrderSide           # LONG or SHORT
    entry_price: float        # Fill price (with slippage)
    entry_time: datetime      # ts_open of fill bar
    size: float               # Base currency units
    size_usdt: float          # Notional in USDT
    stop_loss: float | None   # SL price
    take_profit: float | None # TP price
    fees_paid: float          # Entry fee
    entry_bar_index: int      # For duration analysis
    min_price: float | None   # MAE tracking
    max_price: float | None   # MFE tracking
```

### 4.3 `has_position` Flow

```
SimulatedExchange.position (source of truth)
           │
           │ self.exchange.position is not None
           ▼
RuntimeSnapshotView.has_position (read-only property)
           │
           │ snapshot.has_position
           ▼
idea_card_strategy() wrapper (extracts state)
           │
           │ has_position, position_side
           ▼
IdeaCardSignalEvaluator.evaluate(snapshot, has_position, position_side)
           │
           ▼
Entry rules (if NOT has_position) OR Exit rules (if has_position)
```

### 4.4 Guards Against Duplicate Entries

**File**: `src/backtest/engine.py` (lines 1358-1364)

```python
# Guard 1: Already have a position
if exchange.position is not None:
    return

# Guard 2: Already have a pending order
if exchange.pending_order is not None:
    return
```

---

## 5. Comparison to Industry Engines

### 5.1 Feature Matrix

| Feature | TRADE | VectorBT | Backtrader | Zipline | NautilusTrader |
|---------|-------|----------|------------|---------|----------------|
| **Architecture** | Hybrid | Vectorized | Event-driven | Event-driven | Event-driven |
| **Language** | Python | Python/Numba | Python | Python | Rust/Python |
| **Strategy definition** | YAML IdeaCard | Array ops | `next()` callback | `handle_data()` | `on_bar()` |
| **Order types** | Market | Market | Market/Limit/Stop | Market/Limit | Full simulation |
| **Multi-asset** | Single symbol | Multi-asset | Multi-asset | Multi-asset | Multi-asset |
| **Live trading** | Separate | Limited | Broker plugins | Zipline-live | Native |
| **Lookahead prevention** | Structural | Manual | Structural | Structural | Structural |
| **Speed** | Fast (O(1) loop) | Fastest | Medium | Slow | Fast |

### 5.2 Strategy Definition Comparison

#### TRADE (Declarative YAML)

```yaml
entry_rules:
  - direction: "long"
    conditions:
      - tf: "exec"
        indicator_key: "ema_fast"
        operator: "cross_above"
        value: "ema_slow"
        is_indicator_comparison: true
      - tf: "htf"
        indicator_key: "close"
        operator: "gt"
        value: "ema_trend"
        is_indicator_comparison: true
```

#### Backtrader (Python Callback)

```python
class MyStrategy(bt.Strategy):
    def __init__(self):
        self.ema_fast = bt.indicators.EMA(period=20)
        self.ema_slow = bt.indicators.EMA(period=50)
        self.crossover = bt.indicators.CrossOver(self.ema_fast, self.ema_slow)

    def next(self):
        if self.crossover > 0:
            self.buy()
        elif self.crossover < 0:
            self.sell()
```

#### VectorBT (Array Operations)

```python
fast_ema = vbt.MA.run(close, 20, short_name='fast')
slow_ema = vbt.MA.run(close, 50, short_name='slow')

entries = fast_ema.ma_crossed_above(slow_ema)
exits = fast_ema.ma_crossed_below(slow_ema)

pf = vbt.Portfolio.from_signals(close, entries, exits)
```

#### Zipline (Event Handler)

```python
def initialize(context):
    context.asset = symbol('AAPL')

def handle_data(context, data):
    fast = data.history(context.asset, 'price', 20, '1d').mean()
    slow = data.history(context.asset, 'price', 50, '1d').mean()

    if fast > slow:
        order_target_percent(context.asset, 1.0)
    else:
        order_target_percent(context.asset, 0.0)
```

### 5.3 Order Management Comparison

| Engine | Order Lifecycle | Fill Model |
|--------|----------------|------------|
| **TRADE** | Signal → PendingOrder → Fill → Position | Next bar open + slippage |
| **VectorBT** | Signal array → Immediate execution | Same bar or next bar open |
| **Backtrader** | Order object → Broker simulation | Configurable fill models |
| **Zipline** | Order → Transaction | Commission model |

### 5.4 Performance Characteristics

| Engine | Indicator Computation | Loop Execution | Memory Model |
|--------|----------------------|----------------|--------------|
| **TRADE** | Vectorized (pre-loop) | O(1) per bar | Array-backed |
| **VectorBT** | Vectorized (NumPy) | Vectorized | Full dataset in memory |
| **Backtrader** | Per-bar (cached) | Python iteration | Lines/buffers |
| **Zipline** | Per-bar | Python iteration | Panel data |

---

## 6. Architectural Paradigms

### 6.1 Vectorized Backtesting

**Representative**: VectorBT

**Characteristics**:
- Processes entire dataset at once using NumPy/pandas
- Signal generation as array operations
- Fast for simple strategies
- Limited order management

**Pros**:
- Extremely fast (10-100x faster)
- Simple to write
- Great for parameter optimization

**Cons**:
- No proper order lifecycle
- Difficult to model complex logic
- Lookahead bias requires discipline

### 6.2 Event-Driven Backtesting

**Representative**: Backtrader, Zipline, QuantStart

**Characteristics**:
- Sequential bar-by-bar processing
- Event queue: MARKET → SIGNAL → ORDER → FILL
- Realistic broker simulation

**Pros**:
- Code reuse for live trading
- No lookahead by design
- Complex order types supported

**Cons**:
- Slower execution
- More complex to implement
- Callback spaghetti risk

### 6.3 TRADE Hybrid Approach

**Innovation**: Combines vectorized indicators with event-driven evaluation

```
┌───────────────────────────────────────────────────────────────┐
│                    PRE-LOOP (Vectorized)                      │
│                                                               │
│  indicators = compute_all_indicators(ohlcv_data)  # O(n) once │
│  feed_store = FeedStore(indicators)                           │
└───────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────┐
│                    IN-LOOP (Event-Driven)                     │
│                                                               │
│  for bar_idx in range(num_bars):                              │
│      # O(1) array access - no pandas!                         │
│      snapshot = RuntimeSnapshotView(feed_store, bar_idx)      │
│      signal = strategy(snapshot)  # Evaluate conditions       │
│      process_signal(signal)       # Submit order              │
└───────────────────────────────────────────────────────────────┘
```

**Result**: Performance of vectorized + correctness of event-driven

---

## 7. Best Practices Adopted

### 7.1 From QuantStart Event-Driven Architecture

| Practice | QuantStart | TRADE Implementation |
|----------|------------|---------------------|
| Event types | MARKET, SIGNAL, ORDER, FILL | Signal → Engine → Exchange flow |
| Portfolio converts signals to orders | SignalEvent → OrderEvent | `_process_signal()` computes size |
| Execution handler simulates broker | Slippage, commissions | ExecutionModel in exchange |

### 7.2 From VectorBT Performance Model

| Practice | VectorBT | TRADE Implementation |
|----------|----------|---------------------|
| Pre-compute indicators | Full vectorization | FeedStore with indicator arrays |
| Avoid pandas in loop | NumPy arrays | O(1) array access via snapshot |
| Batch operations | Portfolio vectors | Vectorized indicator computation |

### 7.3 From Industry Standards

| Practice | Source | TRADE Implementation |
|----------|--------|---------------------|
| Hybrid approach | IBKR Campus | Vectorized indicators + sequential loop |
| Structural lookahead prevention | MarketCalls | Closed-candle assertion |
| Deterministic IDs | Best practice | `order_0001`, `pos_0001` |
| Split sizing from signals | QuantStart | Evaluator (SL/TP) vs RiskManager (size) |

---

## 8. Unique Differentiators

### 8.1 Declarative IdeaCards

**What makes it unique**: Strategies are YAML data, not Python code.

**Benefits**:
- No callback spaghetti
- Version-controlled strategy definitions
- Easy to validate and audit
- Can be generated/modified by AI agents

**Trade-off**: Less flexibility than arbitrary Python code

### 8.2 Timeframes Header

**What makes it unique**: Explicit declaration of timeframe roles

```yaml
timeframes:
  exec: "5m"   # Execution timeframe
  htf: "4h"    # Higher timeframe (trend bias)
  mtf: "15m"   # Medium timeframe (momentum)
```

**Benefits**:
- Clear multi-timeframe semantics
- Validation against allowed TF groups
- Forward-fill behavior explicit

### 8.3 Closed-Candle-Only Semantics

**What makes it unique**: Enforced at architecture level, not convention

```python
assert snapshot.ts_close == bar.ts_close  # Structural guard
```

**Benefits**:
- Lookahead bias is impossible
- Matches TradingView `lookahead_off` semantics
- No need for manual discipline

### 8.4 Split Responsibility Model

| Concern | Component | Responsibility |
|---------|-----------|----------------|
| **What** | Evaluator | Conditions that trigger entry/exit |
| **How much** | RiskManager | Position sizing based on risk profile |
| **How** | Exchange | Fill execution with slippage/fees |

**Benefits**:
- Clean separation of domain logic
- Easy to test each component
- Risk model independent of signal logic

---

## 9. Recommendations

### 9.1 Current Strengths to Preserve

1. **Structural lookahead prevention** - Keep the assertion
2. **O(1) hot loop** - Never add pandas operations in bar loop
3. **Declarative IdeaCards** - Resist pressure to add Python callbacks
4. **Deterministic IDs** - Essential for reproducibility

### 9.2 Potential Enhancements

| Enhancement | Priority | Rationale |
|-------------|----------|-----------|
| Limit/stop order types | Medium | More realistic simulation |
| Multi-symbol backtesting | Medium | Portfolio strategies |
| Partial fill simulation | Low | Liquidity modeling |
| Order book simulation | Low | HFT strategies |

### 9.3 Architectural Risks to Monitor

| Risk | Mitigation |
|------|------------|
| Callback creep | Keep IdeaCards declarative |
| Hot loop degradation | Profile regularly, no pandas in loop |
| Lookahead leaks | Maintain structural assertions |
| Complexity growth | Keep component responsibilities clear |

---

## 10. References

### 10.1 External Sources

- [Battle-Tested Backtesters: VectorBT, Zipline, Backtrader](https://medium.com/@trading.dude/battle-tested-backtesters-comparing-vectorbt-zipline-and-backtrader-for-financial-strategy-dee33d33a9e0)
- [Backtrader vs NautilusTrader vs VectorBT vs Zipline-reloaded](https://autotradelab.com/blog/backtrader-vs-nautilusttrader-vs-vectorbt-vs-zipline-reloaded)
- [Event-Driven Backtesting with Python - QuantStart](https://www.quantstart.com/articles/Event-Driven-Backtesting-with-Python-Part-I/)
- [Vector-Based vs Event-Based Backtesting - IBKR Campus](https://www.interactivebrokers.com/campus/ibkr-quant-news/a-practical-breakdown-of-vector-based-vs-event-based-backtesting/)
- [VectorBT Documentation](https://vectorbt.dev/)
- [Backtrader Documentation](https://www.backtrader.com/)

### 10.2 Internal Code References

| Component | File | Key Lines |
|-----------|------|-----------|
| IdeaCard parsing | `src/backtest/idea_card.py` | Entry/exit rules dataclasses |
| Signal evaluation | `src/backtest/execution_validation.py` | 742-842 (evaluate), 904-987 (conditions) |
| Strategy wrapper | `src/backtest/engine_factory.py` | 343-388 |
| Engine loop | `src/backtest/engine.py` | 752-1034 (main loop), 1340-1410 (_process_signal) |
| Order submission | `src/backtest/sim/exchange.py` | 236-270 (submit_order) |
| Order fill | `src/backtest/sim/exchange.py` | 419-462 (_fill_pending_order) |
| Snapshot view | `src/backtest/runtime/snapshot_view.py` | 493-552 (get_feature), 623-649 (position state) |

---

## Appendix A: Entry Flow Sequence Diagram

```
┌─────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐  ┌──────────┐  ┌──────────┐
│ IdeaCard│  │ Snapshot │  │ Evaluator│  │ Engine │  │ Exchange │  │ Position │
└────┬────┘  └────┬─────┘  └────┬─────┘  └───┬────┘  └────┬─────┘  └────┬─────┘
     │            │             │            │            │             │
     │            │  get_feature│            │            │             │
     │            │◄────────────│            │            │             │
     │            │             │            │            │             │
     │            │   value     │            │            │             │
     │            │────────────►│            │            │             │
     │            │             │            │            │             │
     │            │             │ ENTRY_LONG │            │             │
     │            │             │───────────►│            │             │
     │            │             │            │            │             │
     │            │             │            │size_order()│             │
     │            │             │            │───────────►│             │
     │            │             │            │            │             │
     │            │             │            │submit_order│             │
     │            │             │            │───────────►│             │
     │            │             │            │            │             │
     │            │             │            │ [NEXT BAR] │             │
     │            │             │            │            │             │
     │            │             │            │            │fill_pending │
     │            │             │            │            │────────────►│
     │            │             │            │            │             │
     │            │             │            │            │  Position   │
     │            │             │            │            │◄────────────│
     │            │             │            │            │             │
```

---

## Appendix B: Glossary

| Term | Definition |
|------|------------|
| **IdeaCard** | YAML file declaring a trading strategy (rules, risk, sizing) |
| **Evaluator** | Component that evaluates IdeaCard rules against snapshot data |
| **Snapshot** | Read-only view of current bar's indicators and exchange state |
| **FeedStore** | Pre-computed indicator arrays for O(1) access |
| **PendingOrder** | Order submitted but not yet filled (waits for next bar) |
| **Fill** | Execution of an order with price, size, and fees |
| **Position** | Open trade with entry price, SL, TP, and tracking data |
| **has_position** | Boolean indicating whether exchange has open position |
| **Closed-candle** | Data from fully completed bars only (no partial candles) |
| **Lookahead bias** | Using future data to make past decisions (must be prevented) |

---

*Document generated: January 2026*
*Engine version: TRADE Backtest v3.0*
