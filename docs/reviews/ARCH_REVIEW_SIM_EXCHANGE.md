# Architecture Review: Simulated Exchange (`src/backtest/sim/`)

**Reviewer**: Claude Code (Opus 4.5)
**Date**: 2026-01-02
**Scope**: Complete review of the simulated exchange module for backtesting

---

## Executive Summary

The `src/backtest/sim/` module implements a modular, deterministic simulated exchange for backtesting USDT-quoted linear perpetual futures. The architecture follows a tool-calling pattern with a thin orchestrator (`SimulatedExchange`) delegating to specialized modules for pricing, execution, funding, liquidation, and accounting.

**Overall Assessment**: Well-architected with clear separation of concerns. The codebase demonstrates professional-grade design patterns with explicit invariants, consistent currency handling, and deterministic execution semantics. Several areas for improvement identified below.

---

## Module Structure Overview

```
src/backtest/sim/
├── exchange.py           # Main orchestrator (~590 LOC)
├── types.py              # Core types and enums (~566 LOC)
├── ledger.py             # USDT accounting (~324 LOC)
├── bar_compat.py         # Bar timestamp utilities (~41 LOC)
├── adapters/
│   ├── ohlcv_adapter.py  # OHLCV data conversion (~147 LOC)
│   └── funding_adapter.py # Funding rate adaptation (~134 LOC)
├── pricing/
│   ├── price_model.py    # Mark/last/mid derivation (~138 LOC)
│   ├── spread_model.py   # Bid-ask spread estimation (~111 LOC)
│   └── intrabar_path.py  # TP/SL path generation (~215 LOC)
├── execution/
│   ├── execution_model.py # Order execution logic (~282 LOC)
│   ├── slippage_model.py  # Slippage estimation (~164 LOC)
│   ├── impact_model.py    # Market impact (~115 LOC)
│   └── liquidity_model.py # Partial fill constraints (~122 LOC)
├── funding/
│   └── funding_model.py   # Funding rate application (~166 LOC)
├── liquidation/
│   └── liquidation_model.py # Liquidation logic (~189 LOC)
├── constraints/
│   └── constraints.py     # Order validation (~194 LOC)
└── metrics/
    └── metrics.py         # Exchange-side metrics (~219 LOC)
```

---

## File-by-File Analysis

### 1. `sim/exchange.py` - Main Exchange Simulation

**Purpose**: Thin orchestrator coordinating all exchange modules. Manages order lifecycle, position state, and bar-by-bar simulation.

**Key Functions**:
- `__init__()`: Initialize exchange with symbol, capital, execution config, risk profile
- `submit_order()`: Queue entry order for next bar fill
- `submit_close()`: Queue position close for next bar
- `process_bar()`: Main simulation loop - pricing, funding, execution, ledger update
- `_fill_pending_order()`: Fill queued entry orders at bar open
- `_close_position()`: Close position and create trade record
- `force_close_position()`: End-of-data or forced closure

**Dependencies**:
- Internal: `types`, `bar_compat`, `Ledger`, `PriceModel`, `SpreadModel`, `IntrabarPath`, `ExecutionModel`, `FundingModel`, `LiquidationModel`, `ExchangeMetrics`
- External: `system_config.validate_usdt_pair`, `runtime.types.Bar`

**Issues Found**:
1. **LOC Exceeds Target**: At ~590 LOC, exceeds stated target of ~200 LOC (max 250). The orchestrator has grown with Phase 4 additions.
2. **Dual Fee Tracking**: `self.total_fees_paid` tracked separately from `self._ledger.state.total_fees_paid` - potential for drift.
3. **UUID in Order/Fill IDs**: Using `uuid.uuid4()` introduces non-determinism for IDs (though not affecting execution).
4. **Missing Liquidation Flow**: `process_bar()` does not call `_liquidation.check_liquidation()` despite initializing the model.
5. **Trade Import Inside Method**: `from ..types import Trade` imported inside `_close_position()` - should be at module level.

**Structural Concerns**:
- Position closed via `_close_position()` always creates a synthetic exit bar - this works but is unusual
- `last_closed_trades` property returns internal list reference (minor encapsulation leak)
- `set_starvation()` modifies multiple state attributes without transactional guarantee

---

### 2. `sim/types.py` - Core Types and Enums

**Purpose**: Single source of truth for all shared types, enums, events, and snapshots.

**Key Types**:
- **Enums**: `OrderType`, `OrderSide`, `OrderStatus`, `FillReason`, `StopReason`
- **Order Lifecycle**: `Order`, `Fill`, `Position`
- **Events**: `FundingEvent`, `LiquidationEvent`
- **Snapshots**: `PriceSnapshot`, `LedgerState`, `StepResult`, `SimulatorExchangeState`
- **Results**: `FillResult`, `FundingResult`, `LiquidationResult`, `LedgerUpdate`
- **Config**: `ExecutionConfig`

**Dependencies**:
- Internal: `..types.StopReason`, `..runtime.types.Bar`

**Issues Found**:
1. **Mixed Freezing**: Some dataclasses are frozen (`Fill`, `FundingEvent`, `PriceSnapshot`) while others are mutable (`Order`, `Position`, `StepResult`). Inconsistent immutability pattern.
2. **`PricePoint` Unused**: Type defined but not used in the codebase (appears in `intrabar_path.py` but never constructed outside of path generation).
3. **Redundant Default**: `ExecutionConfig.slippage_bps = 5.0` but `SlippageConfig.fixed_bps = 5.0` - two places defining same default.

**Structural Concerns**:
- File is well-organized with clear sections
- `to_dict()` methods on all types for serialization - good practice
- `Position.unrealized_pnl()` method is a calculation, not pure data - slightly mixed responsibility

---

### 3. `sim/ledger.py` - USDT Accounting

**Purpose**: Maintains Bybit-aligned margin model with explicit invariants.

**Key Functions**:
- `update_for_mark_price()`: MTM valuation update
- `apply_entry_fee()`, `apply_exit()`, `apply_funding()`: Cash flow operations
- `compute_required_for_entry()`: Entry gate calculation
- `check_invariants()`: Explicit invariant validation (equity = cash + unrealized, etc.)

**Dependencies**:
- Internal: `types` (Fill, Position, etc.)

**Issues Found**:
1. **Invariant Check Not Called**: `check_invariants()` is defined but never called in the main flow - defensive check exists but unused.
2. **No Audit Trail**: Cash balance mutations don't record transaction history.
3. **Fee Comments Inconsistent**: `apply_entry_fee()` docstring says "fee amount in USD" but code is USDT.

**Structural Concerns**:
- Clean separation of concerns
- `_recompute_derived()` ensures consistency after mutations
- `is_liquidatable` property correctly handles edge case of zero maintenance margin

---

### 4. `sim/bar_compat.py` - Bar Timestamp Utilities

**Purpose**: Provides helper functions for extracting timestamps from canonical Bar type.

**Key Functions**:
- `get_bar_ts_open()`: Returns `bar.ts_open`
- `get_bar_ts_close()`: Returns `bar.ts_close`
- `get_bar_timestamp()`: Returns `bar.ts_close` (step time)

**Dependencies**:
- Internal: `runtime.types.Bar`

**Issues Found**:
1. **Trivial Wrapper**: Functions are one-liners that directly access bar attributes - could be eliminated.
2. **Type Alias Unused**: `AnyBar` alias defined but not used elsewhere.

**Structural Concerns**:
- File exists for historical compatibility with legacy Bar type
- Could be removed in future refactor once all code uses canonical Bar directly

---

### 5. `sim/adapters/ohlcv_adapter.py` - OHLCV Data Conversion

**Purpose**: Converts DuckDB/pandas OHLCV rows to canonical Bar objects.

**Key Functions**:
- `adapt_ohlcv_row_canonical()`: Convert single row to Bar with ts_open/ts_close
- `adapt_ohlcv_dataframe_canonical()`: Convert DataFrame to Bar list
- `build_bar_close_ts_map()`: Build ts_close -> Bar mapping for close detection

**Dependencies**:
- Internal: `runtime.types.Bar`, `runtime.timeframe.tf_duration`

**Issues Found**:
1. **DataFrame Iteration**: `adapt_ohlcv_dataframe_canonical()` uses `df.iterrows()` - slow for large DataFrames.
2. **No Batch Validation**: OHLC validation per row without batch error accumulation.
3. **turnover Optional**: `turnover=row.get("turnover")` handles missing field but not documented.

**Structural Concerns**:
- Good validation of OHLC consistency (high >= open/close, etc.)
- Clean timestamp parsing with multiple input format support

---

### 6. `sim/adapters/funding_adapter.py` - Funding Rate Adaptation

**Purpose**: Converts funding rate data to FundingEvent objects with time window filtering.

**Key Functions**:
- `adapt_funding_row()`: Convert single row to FundingEvent
- `adapt_funding_rows()`: Convert with time window filter (prev_ts, ts]
- `adapt_funding_dataframe()`: DataFrame conversion

**Dependencies**:
- Internal: `types.FundingEvent`

**Issues Found**:
1. **Duplicate Filtering**: Time window filtering duplicated between adapter and `FundingModel.apply_events()`.
2. **Empty Symbol**: `symbol = row.get("symbol", "")` defaults to empty string - should fail or warn.

**Structural Concerns**:
- Half-open interval (prev_ts, ts] is correct for funding semantics
- Sort by timestamp ensures deterministic ordering

---

### 7. `sim/pricing/price_model.py` - Mark Price Derivation

**Purpose**: Derives mark/last/mid prices from OHLC bar data with configurable mark source.

**Key Functions**:
- `get_mark_price()`: Compute mark from close/hlc3/ohlc4
- `get_prices()`: Return complete PriceSnapshot

**Dependencies**:
- Internal: `types.Bar`, `types.PriceSnapshot`, `bar_compat`

**Issues Found**:
1. **Mid Price Ignores Spread**: `get_mid_price()` returns `bar.close` regardless of spread parameter.
2. **No Mark Price Validation**: Unsupported sources raise ValueError but no validation at config time.

**Structural Concerns**:
- Simple, focused module
- Single responsibility principle well applied

---

### 8. `sim/pricing/spread_model.py` - Bid-Ask Spread Estimation

**Purpose**: Estimates bid-ask spread from bar data (fixed or volume-based).

**Key Functions**:
- `get_spread()`: Calculate spread in price units
- `get_bid_ask()`: Derive bid/ask from mid and spread

**Dependencies**:
- Internal: `types.Bar`

**Issues Found**:
1. **Dynamic Mode Unimplemented**: `_dynamic_spread()` returns fixed spread despite "dynamic" mode.
2. **Unused Config Fields**: `volume_multiplier`, `min_spread_bps`, `max_spread_bps` defined but not used.

**Structural Concerns**:
- Clean interface for future volume-based implementation
- Spread in price units is correct approach

---

### 9. `sim/pricing/intrabar_path.py` - TP/SL Path Generation

**Purpose**: Generates deterministic price paths within a bar for TP/SL checking.

**Key Functions**:
- `generate_path()`: Create O->L->H->C price path
- `generate_path_for_side()`: Side-specific conservative path
- `check_tp_sl()`: Check if TP/SL hit within bar
- `get_exit_price()`: Return TP/SL level as exit price

**Dependencies**:
- Internal: `types.Bar`, `types.PricePoint`, `types.OrderSide`, `types.FillReason`, `bar_compat`

**Issues Found**:
1. **Unused Path Generation**: `generate_path()` and `generate_path_for_side()` return `PricePoint` lists but aren't used by `check_tp_sl()`.
2. **Hardcoded Timedelta**: `delta = timedelta(seconds=15)` is arbitrary and not based on actual bar duration.
3. **entry_price Parameter Unused**: `check_tp_sl()` accepts `entry_price` but doesn't use it.

**Structural Concerns**:
- Conservative tie-break (SL before TP) is correct design choice
- Logic correctly handles both long and short positions

---

### 10. `sim/execution/execution_model.py` - Order Execution Logic

**Purpose**: Handles market order execution with slippage, margin checks, and TP/SL evaluation.

**Key Functions**:
- `fill_entry_order()`: Fill pending entry at bar open with slippage
- `check_tp_sl()`: Delegate to intrabar path
- `fill_exit()`: Fill position exit with slippage
- `calculate_realized_pnl()`: Compute PnL for position closure

**Dependencies**:
- Internal: `types`, `bar_compat`, `SlippageModel`, `ImpactModel`, `LiquidityModel`, `IntrabarPath`

**Issues Found**:
1. **Impact Model Unused**: `ImpactModel` initialized but never called in execution flow.
2. **Liquidity Partial Fill Commented**: Code acknowledges partial fills not supported but doesn't reject or warn.
3. **Fee Calculation Inconsistency**: Entry fee uses `order.size_usdt`, exit fee uses `position.size * fill_price` (notional at exit).

**Structural Concerns**:
- Clean separation of entry vs exit execution
- Slippage applied consistently in correct direction

---

### 11. `sim/execution/slippage_model.py` - Slippage Estimation

**Purpose**: Applies fixed or volume-based slippage to execution prices.

**Key Functions**:
- `apply_slippage()`: Apply slippage to entry (buys pay more, sells receive less)
- `apply_exit_slippage()`: Apply slippage to exit (opposite direction)

**Dependencies**:
- Internal: `types.Bar`, `types.OrderSide`

**Issues Found**:
1. **Docstring Typo**: Comments mention "USDTT" which doesn't exist - should be "USDT".
2. **Volume-Based Unimplemented**: Mode exists but returns fixed slippage.

**Structural Concerns**:
- Correct slippage direction for entries and exits
- Clean interface for future volume-based implementation

---

### 12. `sim/execution/impact_model.py` - Market Impact

**Purpose**: Estimates price impact from order size relative to volume.

**Key Functions**:
- `get_impact_multiplier()`: Calculate impact multiplier (>= 1.0)
- `get_impact_bps()`: Total slippage including impact

**Dependencies**:
- Internal: `types.Bar`

**Issues Found**:
1. **Never Called**: Impact model initialized but never used in execution flow.
2. **Docstring Typo**: "USDTT" mentioned in comments.

**Structural Concerns**:
- Good design with linear and sqrt impact models
- Correctly uses volume only for liquidity, not direction

---

### 13. `sim/execution/liquidity_model.py` - Partial Fill Constraints

**Purpose**: Caps order fills based on available liquidity.

**Key Functions**:
- `get_max_fillable()`: Calculate max fillable size
- `would_be_partial_fill()`: Check if order would be partially filled

**Dependencies**:
- Internal: `types.Bar`

**Issues Found**:
1. **Disabled by Default**: `mode: str = "disabled"` means no liquidity constraints applied.
2. **Partial Fill Unhandled**: Model calculates constraint but execution doesn't act on it.
3. **Docstring Typo**: "USDTT" mentioned.

**Structural Concerns**:
- Clean interface ready for activation
- Correct volume-fraction approach

---

### 14. `sim/funding/funding_model.py` - Funding Rate Application

**Purpose**: Applies funding rate events to open positions.

**Key Functions**:
- `apply_events()`: Apply funding events in time window to position
- `_calculate_funding()`: Calculate single funding payment
- `filter_events_for_window()`: Pre-filter events to window

**Dependencies**:
- Internal: `types.Position`, `types.FundingEvent`, `types.FundingResult`, `types.OrderSide`

**Issues Found**:
1. **Position Value at Entry**: Uses `position.size * position.entry_price` but Bybit uses mark price at funding time.
2. **Duplicate Filtering**: Events filtered both in adapter and in `apply_events()`.
3. **No ADL**: Explicitly excluded (documented, not a bug).

**Structural Concerns**:
- Correct funding direction (longs pay positive rates)
- Half-open interval filtering is correct

---

### 15. `sim/liquidation/liquidation_model.py` - Liquidation Logic

**Purpose**: Checks liquidation conditions and handles forced closure.

**Key Functions**:
- `check_liquidation()`: Check if equity <= maintenance margin
- `is_liquidatable()`: Simple liquidation check
- `calculate_liquidation_price()`: Estimate liquidation price

**Dependencies**:
- Internal: `types.Position`, `types.PriceSnapshot`, `types.LedgerState`, `types.LiquidationEvent`, `types.LiquidationResult`, `types.Fill`, `types.FillReason`

**Issues Found**:
1. **Never Called**: `check_liquidation()` not invoked from `exchange.py` despite being initialized.
2. **Fill Generates UUID**: Creates non-deterministic fill ID.
3. **Liquidation Price Simplified**: Formula doesn't account for fees or funding in buffer calculation.

**Structural Concerns**:
- Model is complete but integration missing
- Good separation of check vs calculation

---

### 16. `sim/constraints/constraints.py` - Order Validation

**Purpose**: Validates and adjusts orders to exchange constraints (tick/lot size, min notional).

**Key Functions**:
- `round_price()`: Round to tick size (truncation)
- `round_qty()`: Round to lot size (truncation)
- `validate_order()`: Check min notional and price bounds

**Dependencies**:
- Internal: `types.Order`

**Issues Found**:
1. **Never Called**: Constraints module not used in execution flow.
2. **Docstring Typo**: "USDTT" mentioned.
3. **No Symbol-Specific Constraints**: All constraints are global, not per-symbol.

**Structural Concerns**:
- Complete implementation ready for integration
- Correct truncation semantics for exchange compatibility

---

### 17. `sim/metrics/metrics.py` - Exchange-Side Metrics

**Purpose**: Tracks execution quality metrics (slippage, fees, funding, liquidations).

**Key Functions**:
- `record_step()`: Process StepResult and update metrics
- `_record_fill()`: Track individual fill metrics
- `get_metrics()`: Return aggregated snapshot

**Dependencies**:
- Internal: `types.StepResult`, `types.Fill`, `types.FillReason`

**Issues Found**:
1. **Never Called**: `record_step()` not invoked from exchange processing loop.
2. **Slippage BPS Calculation**: `(fill.slippage / fill.price) * 10000` - slippage is already in price units.
3. **Docstring Typo**: "USDTT" mentioned multiple times.

**Structural Concerns**:
- Complete metrics collection ready for integration
- Good separation of entry vs exit fee tracking

---

## Cross-Cutting Issues

### 1. Unused Modules
Several modules are initialized but never called in the main execution flow:
- `LiquidationModel.check_liquidation()` - liquidation checks not performed
- `ExchangeMetrics.record_step()` - metrics not collected
- `Constraints` - order validation not applied
- `ImpactModel` - market impact not factored into slippage

### 2. Currency Typos
"USDTT" appears in several docstrings and comments. Should be "USDT" consistently:
- `slippage_model.py` (line 13, 14)
- `impact_model.py` (line 11, 12)
- `liquidity_model.py` (line 12, 13)
- `constraints.py` (line 13, 14)
- `metrics.py` (line 27, 28)

### 3. Non-Deterministic IDs
Several places use `uuid.uuid4()` for IDs:
- Order IDs in `submit_order()`
- Position IDs in `_fill_pending_order()`
- Fill IDs in `ExecutionModel.fill_entry_order()`, `fill_exit()`
- Liquidation fill IDs in `LiquidationModel.check_liquidation()`

For fully deterministic replay, consider sequential counters or hash-based IDs.

### 4. Duplicate Default Values
Same defaults defined in multiple places:
- Slippage BPS: `ExecutionConfig.slippage_bps = 5.0` and `SlippageConfig.fixed_bps = 5.0`
- Fee rates: Multiple modules define `0.0006` as default

### 5. Missing Integration Tests
Given the modular architecture, integration between modules isn't explicitly tested:
- Slippage + Impact + Liquidity in execution
- Funding + Ledger update
- Liquidation + Position close

---

## Order Lifecycle Flow

```
1. Strategy calls submit_order(side, size_usdt, sl, tp)
   └── Creates Order object, stores in self.pending_order

2. Engine calls process_bar(bar, prev_bar, funding_events)
   ├── 2a. PriceModel.get_prices(bar) -> mark_price computed ONCE
   ├── 2b. FundingModel.apply_events() -> funding PnL to ledger
   ├── 2c. _fill_pending_order(bar) if pending_order exists
   │   └── ExecutionModel.fill_entry_order() -> Fill created at ts_open
   │       └── Ledger.apply_entry_fee() -> cash reduced
   │       └── Position created with entry details
   ├── 2d. Handle pending_close if requested
   │   └── _close_position(bar.open, ts_open, reason)
   ├── 2e. ExecutionModel.check_tp_sl(position, bar) if position exists
   │   └── If triggered: _close_position(exit_price, ts_open, reason)
   ├── 2f. Track MAE/MFE min/max prices
   └── 2g. Ledger.update_for_mark_price(position, mark_price)
       └── Returns StepResult with all events

3. Position Exit (via _close_position):
   ├── ExecutionModel.fill_exit() -> Fill with slippage
   ├── ExecutionModel.calculate_realized_pnl() -> gross PnL
   ├── Ledger.apply_exit(realized_pnl, exit_fee)
   └── Trade record created and added to trades list
```

---

## Position Accounting Model

```
Entry:
  cash_balance -= entry_fee
  position.size = size_usdt / fill_price
  position.entry_price = fill_price (with slippage)
  used_margin = position_value * IMR

MTM (each bar):
  unrealized_pnl = (mark_price - entry_price) * size * direction
  equity = cash_balance + unrealized_pnl
  maintenance_margin = position_value * MMR

Exit:
  realized_pnl = price_diff * size
  cash_balance += realized_pnl - exit_fee
  position = None
  unrealized_pnl = 0
```

---

## Fee Calculation

```python
# Entry Fee
entry_fee = order.size_usdt * taker_fee_rate

# Exit Fee
exit_notional = position.size * fill_price  # Value at exit
exit_fee = exit_notional * taker_fee_rate

# Net PnL (on Trade record)
net_pnl = realized_pnl - (entry_fee + exit_fee)
```

**Issue**: Entry fee based on requested notional, exit fee based on actual notional at exit price - asymmetric but correct for leveraged positions where value changes.

---

## Funding Rate Handling

```python
# Funding payment calculation
position_value = size * entry_price  # BUG: Should use mark price
direction = -1 if LONG else +1       # Longs pay positive rates
funding_pnl = position_value * funding_rate * direction

# Applied to ledger
cash_balance += funding_pnl
```

**Issue**: Bybit calculates funding on position value at mark price, not entry price.

---

## Liquidation Logic

```python
# Liquidation condition
is_liquidatable = equity <= maintenance_margin

# Liquidation price estimate (simplified)
if LONG:
    liq_price = entry - (cash - size * entry * MMR) / size
if SHORT:
    liq_price = entry + (cash - size * entry * MMR) / size
```

**Note**: Liquidation model is complete but not integrated into `process_bar()`.

---

## Recommendations

### High Priority

1. **Integrate Liquidation Checks**: Add `_liquidation.check_liquidation()` call in `process_bar()` after ledger update.

2. **Fix Funding Calculation**: Use mark price at funding time, not entry price.

3. **Enable Metrics Collection**: Call `_metrics.record_step(step_result)` at end of `process_bar()`.

4. **Fix "USDTT" Typos**: Search and replace across all files.

### Medium Priority

5. **Integrate Constraints**: Apply tick/lot rounding and min notional validation in `fill_entry_order()`.

6. **Enable Impact Model**: Wire `ImpactModel.get_impact_multiplier()` into slippage calculation.

7. **Deterministic IDs**: Replace `uuid.uuid4()` with sequential counters for full replay determinism.

8. **Consolidate Defaults**: Single source for slippage BPS, fee rates, etc.

### Low Priority

9. **Remove `bar_compat.py`**: Inline the trivial functions or access Bar attributes directly.

10. **Implement Dynamic Spread**: Complete volume-based spread model or remove the mode.

11. **Add Invariant Checks**: Call `ledger.check_invariants()` in debug mode.

12. **Refactor `exchange.py`**: Extract trade creation logic to reduce LOC.

---

## Conclusion

The simulated exchange architecture is well-designed with clear modularity and separation of concerns. The main gaps are:

1. **Incomplete Integration**: Several modules (liquidation, metrics, constraints, impact) are implemented but not wired into the main loop.
2. **Minor Bugs**: Funding uses entry price instead of mark price; various typos.
3. **Non-determinism**: UUID-based IDs prevent exact replay.

The codebase follows good practices: explicit invariants in the ledger, consistent currency naming (USDT suffix), conservative TP/SL tie-breaking, and clean type hierarchies. With the recommended integrations, this would be a robust backtesting engine.
