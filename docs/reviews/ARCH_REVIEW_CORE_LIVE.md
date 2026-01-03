# Architecture Review: Core Module (Live Trading)

**Date**: 2026-01-02
**Reviewer**: Claude Opus 4.5 (Architecture Review)
**Scope**: `src/core/` - Live Trading Domain

---

## Executive Summary

The Core module provides live trading functionality for Bybit futures. The architecture follows a **delegated design pattern** where `ExchangeManager` acts as a facade, delegating to specialized helper modules. The module demonstrates strong safety controls, proper mode validation, and clean separation of concerns.

**Overall Assessment**: Well-structured with mature patterns. Some areas for improvement in error handling consistency and code duplication.

---

## File-by-File Analysis

---

### 1. `application.py`

**Purpose**: Central application lifecycle manager - initialization, startup, shutdown, signal handling.

**Key Functions**:
| Function | Description |
|----------|-------------|
| `initialize()` | Initializes components in dependency order (ExchangeManager -> RiskManager -> PositionManager -> RealtimeState -> RealtimeBootstrap) |
| `start()` | Starts WebSocket if needed by RiskManager or config |
| `stop()` | Graceful shutdown with cleanup |
| `_signal_handler()` | Handles SIGINT/SIGTERM |
| `get_application()` | Singleton accessor |

**Dependencies**:
- `src/config/config.py` (Config)
- `src/utils/logger.py`
- `src/data/realtime_state.py` (lazy)
- `src/data/realtime_bootstrap.py` (lazy)
- `src/core/exchange_manager.py`
- `src/core/risk_manager.py`
- `src/core/position_manager.py`

**Issues Found**:
1. **Thread Safety**: Uses module-level `_app_lock` for singleton, but `Application.__init__` creates new instances without checking - could have race condition if multiple threads call `get_application()` with different configs.
2. **atexit Handler**: Registers `atexit.register(self._atexit_handler)` on every initialization - could stack up if `reset_application()` is called repeatedly.
3. **Suppress Shutdown State**: `_suppress_shutdown` is not thread-safe (no lock around read/write).

**Structural Concerns**:
- Uses module-level singleton pattern with `_application` global variable
- WebSocket startup timeout uses busy-wait polling (`time.sleep(0.1)` in loop)

---

### 2. `exchange_manager.py`

**Purpose**: Unified exchange interface providing facade over Bybit operations. Delegates to specialized helper modules.

**Key Functions**:
| Function | Description |
|----------|-------------|
| `__init__()` | Validates trading mode consistency, initializes BybitClient |
| `_validate_trading_operation()` | Safety guard for mode/API consistency |
| Market data | `get_price()`, `get_bid_ask()` |
| Account | `get_balance()`, `get_account_value()` |
| Orders | Delegates to `exchange_orders_*.py` modules |
| Positions | Delegates to `exchange_positions.py` |
| Instruments | Delegates to `exchange_instruments.py` |

**Dependencies**:
- `src/exchanges/bybit_client.py` (BybitClient)
- `src/config/config.py`
- `src/utils/logger.py`
- `src/utils/helpers.py`
- `src/utils/time_range.py`
- Helper modules: `exchange_instruments`, `exchange_websocket`, `exchange_orders_*`, `exchange_positions`

**Issues Found**:
1. **Lazy Import Pattern**: Every delegated method does `from . import exchange_xxx as xxx` on each call. While avoiding circular imports, this adds overhead on every operation.
2. **Instrument Cache**: `_instruments` cache never expires - stale data possible for symbols with changed specs.
3. **Error Handling**: `get_balance()` silently returns 0 if USDT not found in response.

**Structural Concerns**:
- **Good**: Strict mode/API validation at startup blocks invalid configurations
- **Good**: Clean delegation pattern keeps this file as a thin facade (~520 lines)
- **Concern**: `_previous_positions` dict is used for WebSocket cleanup but never explicitly cleared

---

### 3. `exchange_orders_market.py`

**Purpose**: Market order execution (buy/sell with optional TP/SL).

**Key Functions**:
| Function | Description |
|----------|-------------|
| `market_buy()` | Place market buy order |
| `market_sell()` | Place market sell (short) order |
| `market_buy_with_tpsl()` | Market buy with take-profit/stop-loss |
| `market_sell_with_tpsl()` | Market sell with take-profit/stop-loss |

**Dependencies**:
- `ExchangeManager` (type hint only)
- `exchange_instruments` module
- `exchange_websocket` module
- `BybitAPIError`

**Issues Found**:
1. **Price Staleness**: Gets price via REST, then places order - price could move. Market orders will still fill but logged price may not match fill.
2. **Duplicate Code**: All 4 functions have nearly identical structure (try/except, validate, calculate qty, create order, return result).

**Structural Concerns**:
- Clean, focused module with single responsibility
- Proper WebSocket symbol tracking via `ws.ensure_symbol_tracked()`

---

### 4. `exchange_orders_limit.py`

**Purpose**: Limit order execution with optional TP/SL.

**Key Functions**:
| Function | Description |
|----------|-------------|
| `limit_buy()` | Place limit buy order |
| `limit_sell()` | Place limit sell order |
| `limit_buy_with_tpsl()` | Limit buy with TP/SL attached |
| `limit_sell_with_tpsl()` | Limit sell with TP/SL attached |

**Dependencies**:
- Same as market orders module

**Issues Found**:
1. **Price Precision**: `round_price()` called correctly, but `_with_tpsl` versions don't round TP/SL prices - could cause API rejection.
2. **Missing WebSocket Tracking**: `limit_buy_with_tpsl()` and `limit_sell_with_tpsl()` don't call `ws.ensure_symbol_tracked()` unlike base limit functions.

**Structural Concerns**:
- Parameter shadowing: `price = inst.round_price(manager, symbol, price)` shadows input parameter - confusing for debugging
- Same code duplication pattern as market orders

---

### 5. `exchange_orders_stop.py`

**Purpose**: Stop/conditional orders and RR-based position opening.

**Key Functions**:
| Function | Description |
|----------|-------------|
| `stop_market_buy/sell()` | Conditional market orders |
| `stop_limit_buy/sell()` | Conditional limit orders |
| `create_conditional_order()` | Generic conditional order creator |
| `open_position_with_rr()` | Opens position with risk-reward based TP/SL levels |

**Dependencies**:
- Same as other order modules
- Uses `Decimal` for precision calculations
- Imports `time` for order_link_id generation

**Issues Found**:
1. **Direct Session Access**: Uses `manager.bybit.session.place_order()` directly instead of wrapper - bypasses any client-level error handling/rate limiting.
2. **Result Parsing Inconsistency**: Lines 50-51, 102-103 check for tuple vs dict response - suggests API inconsistency that should be handled centrally.
3. **open_position_with_rr() Complexity**: 100-line function mixing leverage setting, price calculation, order placement, and TP creation - should be decomposed.

**Structural Concerns**:
- `open_position_with_rr()` catches generic `Exception` for leverage setting and continues - could mask real issues
- Order link IDs use timestamp: `TP{i+1}_{symbol}_{int(time.time())}` - possible collision in fast loops

---

### 6. `exchange_orders_manage.py`

**Purpose**: Order management, history queries, and batch operations.

**Key Functions**:
| Function | Description |
|----------|-------------|
| `get_open_orders()` | Get open orders (normalized to `Order` objects) |
| `cancel_order()` | Cancel single order |
| `cancel_all_orders()` | Cancel all orders (optionally per symbol) |
| `amend_order()` | Modify existing order |
| `close_position()` | Close position with conditional order cleanup |
| `close_all_positions()` | Emergency close all |
| `get_order_history/executions/closed_pnl()` | History queries |
| `batch_*_orders()` | Batch operations (max 10 per batch) |

**Dependencies**:
- `src/utils/helpers.py` (safe_float)
- `src/utils/time_range.py`
- Other exchange modules

**Issues Found**:
1. **Magic Number**: `len(orders) > 10` batch limit is hardcoded - should be config or constant.
2. **Silent Failures**: `get_open_orders()` returns empty list on exception - caller cannot distinguish "no orders" from "API error".
3. **Unused Parameter**: `amend_order()` accepts `trigger_price` but doesn't use it in the kwargs dict.

**Structural Concerns**:
- Batch operations recursively call themselves for >10 orders - could cause deep stack for large batches
- Good pattern: `close_position()` properly cancels conditional orders before closing

---

### 7. `exchange_positions.py`

**Purpose**: Position queries, TP/SL management, leverage/margin settings, unified account operations.

**Key Functions**:
| Function | Description |
|----------|-------------|
| `get_position()` | Get single position (normalized) |
| `get_all_positions()` | Get all open positions |
| `set_position_tpsl()` | Set TP/SL on existing position |
| `set_trailing_stop()` | Set trailing stop |
| `set_leverage()` | Set leverage (with config limit enforcement) |
| `cancel_position_conditional_orders()` | Cleanup conditional orders |
| `reconcile_orphaned_orders()` | Find/cancel orphaned conditional orders |
| `get_transaction_log()` | UTA transaction history |
| Various margin/collateral functions | UTA account management |

**Dependencies**:
- `src/utils/helpers.py`
- `src/utils/time_range.py`
- `BybitAPIError`
- `re` (regex for order pattern matching)

**Issues Found**:
1. **Code Duplication**: `get_position()` and `get_all_positions()` have nearly identical position normalization logic (~30 lines each).
2. **Unused Parameter**: `set_trailing_stop()` accepts `active_price` but doesn't pass it to API.
3. **PnL Calculation Risk**: Line 64: `unrealized_pnl / (size * entry_price) * 100` - could divide by zero if `entry_price` is 0.

**Structural Concerns**:
- Large file (957 lines) - could split UTA operations into separate module
- Good pattern: `reconcile_orphaned_orders()` uses regex to only cleanup bot-generated orders
- TimeRange is properly required for all history queries (enforces no implicit defaults)

---

### 8. `exchange_instruments.py`

**Purpose**: Instrument specifications, price/quantity calculations.

**Key Functions**:
| Function | Description |
|----------|-------------|
| `get_instrument_info()` | Get and cache instrument specs |
| `round_price()` | Round to valid tick size |
| `get_tick_size()` | Get min price increment |
| `get_min_qty()` | Get min order quantity |
| `calculate_qty()` | Convert USD amount to quantity |
| `get_price_precision()` | Get decimal places for price |

**Dependencies**:
- `Decimal` (for precision)
- Type hints for ExchangeManager

**Issues Found**:
1. **Cache Never Expires**: `manager._instruments[symbol]` cached forever - no TTL.
2. **Default Fallbacks**: Returns `"0.01"` and `"0.001"` as defaults - could cause incorrect rounding for some instruments.
3. **get_price_precision() Bug**: `rstrip("0")` could return incorrect precision for tick sizes like `"1.0"` -> `"1."` -> precision 0.

**Structural Concerns**:
- Clean, focused module
- Good use of `Decimal` for precision-sensitive calculations

---

### 9. `exchange_websocket.py`

**Purpose**: WebSocket integration for position cleanup callbacks.

**Key Functions**:
| Function | Description |
|----------|-------------|
| `setup_websocket_cleanup()` | Register position update callback |
| `on_position_update_cleanup()` | Handle position close -> cancel conditional orders |
| `cancel_conditional_orders_for_symbol()` | Cancel all bot-generated conditional orders |
| `ensure_symbol_tracked()` | Subscribe symbol to WebSocket |
| `remove_symbol_from_websocket()` | Stop tracking symbol |

**Dependencies**:
- `src/data/realtime_state.py` (lazy)
- `src/data/realtime_bootstrap.py` (lazy)
- `re` (regex)

**Issues Found**:
1. **Race Condition**: Position close detection relies on `manager._previous_positions` dict which could be stale if WebSocket callback is delayed.
2. **Silent Failures**: `ensure_symbol_tracked()` catches all exceptions and does nothing - caller has no way to know subscription failed.

**Structural Concerns**:
- Good separation of WebSocket-specific logic from ExchangeManager
- Properly filters to only cancel bot-generated orders via regex pattern

---

### 10. `order_executor.py`

**Purpose**: Trade execution flow through risk checks with WebSocket feedback support.

**Key Functions**:
| Function | Description |
|----------|-------------|
| `execute()` | Main execution flow: Signal -> Risk Check -> Exchange -> Record |
| `_validate_trading_mode()` | Safety check before any execution |
| `close_position()` | Convenience method to close |
| `execute_with_leverage()` | Execute with specific leverage |
| `wait_for_fill()` | Wait for WebSocket fill confirmation |
| `cleanup_old_pending_orders()` | Remove stale pending orders |

**Dependencies**:
- `ExchangeManager`, `RiskManager`, `PositionManager`
- `src/config/config.py`
- `src/utils/logger.py`
- `src/data/realtime_state.py` (lazy)

**Issues Found**:
1. **Pending Order Memory Leak**: `_pending_orders` dict only cleaned by explicit `cleanup_old_pending_orders()` call - could grow unbounded.
2. **Type Mismatch**: `_pending_orders: dict[str, PendingOrder]` uses built-in dict generic (Python 3.9+) - inconsistent with other files using `Dict[str, ...]`.
3. **WebSocket Callback Order**: `_on_execution()` could be called before `execute()` returns if WS is very fast - pending order might not be in dict yet.

**Structural Concerns**:
- Good separation: Execution logic doesn't know about API details
- Clean event emission for observability
- Safety validation happens first in `execute()`

---

### 11. `position_manager.py`

**Purpose**: Position tracking with hybrid WebSocket/REST support.

**Key Functions**:
| Function | Description |
|----------|-------------|
| `get_snapshot()` | Get portfolio snapshot (WS or REST) |
| `get_position()` | Get single position |
| `record_trade()` | Record completed trade |
| `record_execution_from_ws()` | Record from WebSocket event |
| `get_daily_stats()` | Daily trading statistics |
| `get_performance_summary()` | Win rate, PnL metrics |
| `reconcile_with_rest()` | Verify WS data against REST |

**Dependencies**:
- `ExchangeManager`, `Position`
- `src/utils/logger.py`
- `src/data/realtime_state.py` (lazy)

**Issues Found**:
1. **Unbounded Trade History**: `_trades` list grows forever - no limit or rotation.
2. **Inconsistent Position Creation**: `get_position()` WS path creates `Position` with wrong field names (e.g., `liq_price` instead of `liquidation_price`).
3. **Missing Fields**: WS path in `get_position()` creates Position with fewer fields than REST path (missing `exchange`, `position_type`, `margin_mode`, etc.).

**Structural Concerns**:
- Good fallback pattern: WS first, REST fallback
- Daily reset logic duplicated with RiskManager
- Reconciliation feature is valuable for production reliability

---

### 12. `risk_manager.py`

**Purpose**: Rule-based risk controls - pure deterministic checks, no AI/ML.

**Key Functions**:
| Function | Description |
|----------|-------------|
| `check()` | Main risk check: daily loss, balance, position size, exposure, per-trade % |
| `check_leverage()` | Validate and cap leverage |
| `record_pnl()` | Track realized PnL |
| `get_remaining_exposure()` | Calculate available exposure |
| `get_max_position_size()` | Calculate max allowed size |
| `calculate_trade_levels()` | RR-based TP/SL calculation helper |

**Dependencies**:
- `src/config/config.py` (RiskConfig)
- `src/utils/logger.py`
- `src/risk/global_risk.py` (lazy)
- `PositionManager.PortfolioSnapshot`

**Issues Found**:
1. **Magic Numbers**: `min_viable_size = 5.0` hardcoded - should be config.
2. **Circular Import Risk**: `start_websocket_if_needed()` imports from `src/core/application.py` - circular with application importing risk_manager.
3. **Daily Reset Race**: `_reset_daily_if_needed()` not thread-safe for `_daily_pnl` and `_daily_trades`.

**Structural Concerns**:
- Clear, sequential risk check pipeline
- Good integration with GlobalRiskView for account-level checks
- Static methods for RR calculations are useful utilities

---

### 13. `safety.py`

**Purpose**: Emergency panic button and safety checks.

**Key Functions**:
| Function | Description |
|----------|-------------|
| `panic_close_all()` | EMERGENCY: Cancel all orders, close all positions, trigger halt |
| `is_panic_triggered()` | Check if panic active |
| `check_panic_and_halt()` | Check panic at loop start |
| `reset_panic()` | Reset panic (requires confirmation) |
| `SafetyChecks.run_all_checks()` | Pre-trade safety validation |

**Dependencies**:
- `src/utils/logger.py`
- `threading`
- `datetime`

**Issues Found**:
1. **Callback Exception Handling**: `PanicState.trigger()` catches all callback exceptions but doesn't log them.
2. **Duplicate Daily Loss Tracking**: `SafetyChecks` tracks `_daily_loss` separately from `RiskManager._daily_pnl` - could get out of sync.

**Structural Concerns**:
- Thread-safe panic state with lock
- Good confirmation pattern for reset (`confirm="RESET"`)
- Proper separation of panic state from safety checks

---

### 14. `__init__.py`

**Purpose**: Module exports and public API definition.

**Key Functions**: None (exports only)

**Dependencies**: All core module files

**Issues Found**: None

**Structural Concerns**:
- Clean, explicit `__all__` list
- Proper re-exports for public API

---

## Cross-Cutting Concerns

### Order Execution Flow

```
Signal -> OrderExecutor.execute()
            |
            v
      _validate_trading_mode() -- Safety Guard
            |
            v
      RiskManager.check() -- Risk Validation
            |
            v
      ExchangeManager.market_buy/sell() -- Execution
            |
            v
      PositionManager.record_trade() -- Recording
```

**Assessment**: Flow is clean and follows single-responsibility. Safety validation happens first.

### Position Tracking

- **Primary Source**: WebSocket via `RealtimeState` when connected
- **Fallback**: REST API via `ExchangeManager`
- **Reconciliation**: `PositionManager.reconcile_with_rest()` for verification

**Assessment**: Good hybrid approach. Some data inconsistency risks between WS and REST paths.

### Risk Management

1. **GlobalRiskView** (optional): Account-level margin/liquidation checks
2. **RiskManager**: Per-trade rules (size, exposure, daily loss)
3. **SafetyChecks**: Pre-trade validation
4. **PanicState**: Emergency halt

**Assessment**: Multiple layers provide defense in depth. Some duplication between layers.

### Safety Controls

| Control | Location | Description |
|---------|----------|-------------|
| Mode Validation | `ExchangeManager.__init__`, `OrderExecutor._validate_trading_mode()` | Blocks invalid PAPER/LIVE+DEMO combinations |
| Daily Loss Limit | `RiskManager.check()`, `SafetyChecks.check_daily_loss_limit()` | Stops trading when limit hit |
| Panic Button | `safety.py` | Emergency flatten all |
| Leverage Cap | `exchange_positions.set_leverage()` | Enforces config max |

### WebSocket Handling

- **Purpose**: Real-time position/order updates for faster feedback
- **Integration Points**:
  - `exchange_websocket.py` for cleanup callbacks
  - `order_executor.py` for execution feedback
  - `position_manager.py` for position data
- **Fallback**: All paths fall back to REST if WebSocket unavailable

**Assessment**: Well-designed fallback pattern. Some edge cases around WS/REST data inconsistency.

### API Patterns

- **Delegation Pattern**: ExchangeManager delegates to helper modules
- **Lazy Import**: Used throughout to avoid circular dependencies
- **Result Objects**: Consistent use of `OrderResult`, `RiskCheckResult`, `ExecutionResult`
- **Safe Float Conversion**: `safe_float()` helper used consistently

---

## Summary of Issues

### High Priority

| Issue | Location | Impact |
|-------|----------|--------|
| Pending order memory leak | `order_executor.py` | Could grow unbounded in long-running process |
| Daily loss tracking duplication | `RiskManager` vs `SafetyChecks` | Values could diverge |
| Position data inconsistency | `position_manager.py:get_position()` | WS path creates Position with wrong/missing fields |
| Thread safety | Multiple files | `_daily_pnl`, `_suppress_shutdown` not protected |

### Medium Priority

| Issue | Location | Impact |
|-------|----------|--------|
| Instrument cache never expires | `exchange_instruments.py` | Stale data for changed symbols |
| Direct session access | `exchange_orders_stop.py` | Bypasses client error handling |
| Code duplication in order modules | `exchange_orders_*.py` | Maintenance burden |
| Unused `trigger_price` parameter | `exchange_orders_manage.amend_order()` | Confusing API |
| Unused `active_price` parameter | `exchange_positions.set_trailing_stop()` | Feature not working |

### Low Priority

| Issue | Location | Impact |
|-------|----------|--------|
| Lazy import overhead | `exchange_manager.py` | Minor performance |
| Magic numbers | Multiple files | Hardcoded values should be config |
| Inconsistent type hints | `order_executor.py` | `dict[str, ...]` vs `Dict[str, ...]` |

---

## Recommendations

1. **Extract Position Normalization**: Create shared helper for WS and REST position data normalization.

2. **Add Instrument Cache TTL**: Implement expiry for `_instruments` cache (e.g., 1 hour).

3. **Unify Daily Tracking**: Single source of truth for daily PnL/trades between RiskManager and SafetyChecks.

4. **Add Thread Locks**: Protect mutable state that's accessed from callbacks (`_daily_pnl`, pending orders, etc.).

5. **Pending Order Cleanup**: Add automatic periodic cleanup or max size limit.

6. **Extract Common Order Logic**: Create base function for order execution pattern used across all order modules.

7. **Fix Unused Parameters**: Either implement `active_price` and `trigger_price` or remove from signature.

8. **Add Integration Tests**: WebSocket + REST fallback paths need coverage.

---

## Conclusion

The Core module is well-architected with strong safety controls and clean separation of concerns. The delegation pattern keeps individual files focused, and the hybrid WebSocket/REST approach provides reliability. The main areas for improvement are around data consistency between WS/REST paths, thread safety for shared state, and reducing code duplication in order execution modules.

**Stability Rating**: Production-ready with monitoring recommended for the identified issues.
