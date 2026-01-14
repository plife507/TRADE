# Position vs Order Architecture

This document describes the state management for positions and orders in the TRADE backtest simulator.

---

## Core Concepts

### Order vs Position

| Concept | Definition | State Location | Lifecycle |
|---------|------------|----------------|-----------|
| **Order** | Intent to trade (unfilled instruction) | `exchange._order_book._orders` | Created → Pending → Filled/Cancelled/Rejected |
| **Position** | Active exposure (filled order) | `exchange.position` | None → Open → Closed (None) |

**Key constraint**: ONE active position per symbol (isolated margin mode).

```python
# src/backtest/sim/exchange.py:142
self.position: Position | None = None
```

---

## Order Types

```
src/backtest/sim/types.py

class OrderType(str, Enum):
    MARKET = "market"       # Fill immediately at next bar open
    LIMIT = "limit"         # Fill when price crosses limit_price
    STOP_MARKET = "stop_market"  # Trigger → market fill
    STOP_LIMIT = "stop_limit"    # Trigger → limit fill
```

### Order Lifecycle

```
                    ┌─────────────┐
                    │   PENDING   │
                    └──────┬──────┘
                           │
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
   ┌──────────┐     ┌──────────┐     ┌──────────┐
   │  FILLED  │     │ CANCELLED│     │ REJECTED │
   └──────────┘     └──────────┘     └──────────┘
```

---

## Position Lifecycle

```
                         Signal: entry_long
                                │
                                ▼
                    ┌───────────────────────┐
                    │  submit_market_order  │
                    └───────────┬───────────┘
                                │
                    ┌───────────▼───────────┐
                    │  GUARDRAIL CHECK:     │
                    │  position is None?    │
                    └───────────┬───────────┘
                       NO │           │ YES
                          ▼           ▼
                    ┌─────────┐  ┌─────────────────┐
                    │ BLOCKED │  │ Order → OrderBook│
                    │ (None)  │  └────────┬────────┘
                    └─────────┘           │
                                          ▼
                              ┌───────────────────┐
                              │  Next bar:        │
                              │  process_bar()    │
                              └────────┬──────────┘
                                       │
                                       ▼
                              ┌───────────────────┐
                              │  Fill order       │
                              │  Create Position  │
                              └────────┬──────────┘
                                       │
                    ┌──────────────────┴──────────────────┐
                    │  exchange.position = Position(...)  │
                    │  GUARDRAIL: All entries blocked     │
                    └──────────────────┬──────────────────┘
                                       │
                         ┌─────────────┴─────────────┐
                         ▼                           ▼
                  ┌────────────┐              ┌────────────┐
                  │ Exit Signal│              │  TP/SL Hit │
                  └─────┬──────┘              └─────┬──────┘
                        │                          │
                        └──────────┬───────────────┘
                                   ▼
                    ┌───────────────────────────┐
                    │  exchange.position = None │
                    │  GUARDRAIL: Entries OK    │
                    └───────────────────────────┘
```

---

## Guardrails

### Entry Guardrails

Three guardrails prevent duplicate positions in `src/backtest/sim/exchange.py`:

| Method | Line | Check | Action |
|--------|------|-------|--------|
| `submit_market_order` | 259-260 | `if self.position is not None` | Return None |
| `submit_limit_order` | 315-316 | `if not reduce_only and self.position is not None` | Return None |
| `submit_stop_order` | 375-376 | `if not reduce_only and self.position is not None` | Return None |

### Duplicate Order Guardrail

```python
# exchange.py:261-263
pending_market = self._order_book.get_pending_orders(OrderType.MARKET, self.symbol)
if pending_market:
    return None  # Block duplicate market order
```

### Entries Disabled Guardrail

```python
# exchange.py:253-256
if self.entries_disabled:
    self.entry_rejections_count += 1
    self.last_rejection_code = "ENTRIES_DISABLED"
    return None
```

Used for: starvation protection, end-of-data, manual disable.

---

## Deterministic State Management

### Sequential Counters

The simulator uses monotonic counters for deterministic ID generation:

| Counter | Location | Format | Purpose |
|---------|----------|--------|---------|
| `_order_counter` | exchange.py:146 | `order_0001` | Unique order IDs |
| `_position_counter` | exchange.py:147 | `pos_0001` | Unique position IDs |
| `_trade_counter` | exchange.py:145 | `trade_0001` | Unique trade records |

### Why This Ensures Determinism

1. **Counters never reset mid-run** - Monotonic increment only
2. **IDs are globally unique** - No collision possible within a run
3. **Same inputs = Same sequence** - Play + Data → Identical ID sequence

### Hash Verification

`src/backtest/artifacts/determinism.py` compares runs via:

```python
@dataclass
class HashComparison:
    field_name: str      # e.g., "trades_hash", "metrics_hash"
    run_a_value: str     # Hash from run A
    run_b_value: str     # Hash from run B
    matches: bool        # run_a == run_b
```

**Verified hashes**:
- Trade sequence hash (entry/exit order)
- Metrics hash (final PnL, win rate, etc.)
- Equity curve hash (bar-by-bar equity)

**Determinism guarantee**: Same Play + Same Data = Same Hashes

---

## OrderBook Architecture

```python
# src/backtest/sim/types.py:634
@dataclass
class OrderBook:
    """Manages multiple pending orders."""
    max_orders: int = 100  # Safety limit
    _orders: dict[str, Order]  # O(1) lookup by order_id
    _order_counter: int  # Backup counter if order has no ID
```

### Key Operations

| Method | Complexity | Purpose |
|--------|------------|---------|
| `add_order(order)` | O(1) | Add order to book |
| `get_order(order_id)` | O(1) | Lookup by ID |
| `cancel_order(order_id)` | O(1) | Remove from book |
| `get_pending_orders(type, symbol)` | O(n) | Filter by type/symbol |
| `check_triggers(bar)` | O(n) | Find triggered stops |

### Memory Safety

```python
if len(self._orders) >= self.max_orders:
    raise ValueError(f"Order book full (max {self.max_orders} orders)")
```

---

## State Snapshot

At any point in time, exchange state consists of:

```python
@dataclass
class SimulatorExchangeState:
    # Account
    cash_balance_usdt: float
    equity_usdt: float
    unrealized_pnl_usdt: float
    used_margin_usdt: float
    free_margin_usdt: float

    # Position (0 or 1)
    position: Position | None

    # Pending orders (0 to max_orders)
    pending_orders: list[Order]

    # Counters (for determinism)
    order_counter: int
    position_counter: int
    trade_counter: int
```

---

## Implications for 1m Evaluation Model

If we switch to 1m hot loop evaluation:

| Aspect | Impact | Reason |
|--------|--------|--------|
| Position guardrails | No change | Check `self.position`, not timeframe |
| Order book | No change | Handles any evaluation frequency |
| Determinism | Maintained | Sequential counters work at any TF |
| Memory | Same | State size unchanged, more evaluations |

**Key insight**: Guardrails are timeframe-agnostic. The 1m model changes *when* we check conditions, not *how* positions are managed.

---

## Related Files

| File | Purpose |
|------|---------|
| `src/backtest/sim/exchange.py` | SimulatedExchange (state + guardrails) |
| `src/backtest/sim/types.py` | Order, Position, OrderBook types |
| `src/backtest/artifacts/determinism.py` | Hash comparison for verification |
| `src/backtest/engine.py` | Orchestrates signal → order flow |

---

## Summary

1. **One position per symbol** - Enforced by guardrails at order submission
2. **Orders queue in OrderBook** - Multiple pending orders allowed
3. **Sequential counters** - Guarantee deterministic IDs
4. **Hash verification** - Confirms identical runs produce identical output
5. **Timeframe-agnostic** - Guardrails work at any evaluation frequency
