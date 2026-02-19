# Data & Exchange Domain Code Review

**Reviewer:** Code review agent
**Date:** 2026-02-18
**Scope:** Data layer (src/data/) and Exchange layer (src/core/)

> **STATUS (2026-02-18):** All findings resolved. 3 HIGH fixed, 5 MED fixed, 1 MED deferred (DATA-011), 2 known/mitigated, 3 LOW OK/acceptable.
> See `FINDINGS_SUMMARY.md` for current status of each finding.

---

## Files Reviewed

| File | Lines | Role |
|------|-------|------|
| `src/data/historical_data_store.py` | ~600 | DuckDB OHLCV storage, write locking, singleton |
| `src/data/historical_sync.py` | 484 | Sync operations, API fetch, metadata update |
| `src/data/historical_maintenance.py` | ~350 | Gap detection, healing, duplicate removal |
| `src/data/realtime_state.py` | ~993 | Thread-safe in-memory state for all WS data |
| `src/data/realtime_bootstrap.py` | 1273 | WebSocket lifecycle, subscriptions, monitor |
| `src/data/market_data.py` | ~796 | Hybrid WS/REST cache with TTLs |
| `src/core/safety.py` | 455 | DailyLossTracker, PanicState, SafetyChecks |
| `src/core/exchange_manager.py` | ~594 | Singleton facade over all exchange_* modules |
| `src/core/exchange_positions.py` | 964 | Position queries, TP/SL, reconciliation |
| `src/core/exchange_orders_market.py` | 250 | market_buy/sell with and without TP/SL |
| `src/core/order_executor.py` | ~819 | Signal → RiskManager → ExchangeManager pipeline |
| `src/core/risk_manager.py` | ~705 | Deterministic pre-trade risk checks |

---

## Module Overview

The data/exchange domain splits into two layers:

**Data layer** (`src/data/`): DuckDB-backed historical OHLCV storage with environment-aware table naming, file-based write locking for multi-process safety, and a real-time WebSocket state tier. The bootstrap module manages WebSocket lifecycle. The maintenance module handles gap detection and healing.

**Exchange layer** (`src/core/`): A singleton `ExchangeManager` facade over decomposed exchange_* modules. The order executor runs the signal→risk→order pipeline. Safety checks and the DailyLossTracker are shared singletons. The risk manager performs deterministic pre-trade validation.

Overall architecture is sound. Safety-critical paths show genuine attention to fail-closed principles (DCP activation, one-way mode enforcement, reduce_only on closes). Several real bugs exist across both layers, with two HIGH severity issues in the close-order sequence.

---

## File-by-File Findings

---

### src/data/historical_data_store.py

**Summary**: DuckDB OHLCV storage with environment-specific table names, file-based write locking, and a singleton pattern. The `_write_operation()` context manager serialises write access.

#### [DATA-001] MED -- Stale lock file causes 5-minute write outage after double crash

**File:Line**: `historical_data_store.py:491-511`

`_acquire_write_lock()` creates a `.lock` file using `open(path, 'x')` and removes it on release. If the process crashes without running `__del__` (e.g., SIGKILL, power loss), the stale lock blocks all writes for up to 5 minutes before the age-based removal triggers. On Windows, `__del__` is not guaranteed to run on abnormal exit.

**Root cause**: The lock file age threshold (300 seconds) is generous but not applied until the next write attempt, which may be the next bot startup.

**Fix**: On `_acquire_write_lock()`, also check if the PID recorded in the lock file is still running (`os.kill(pid, 0)`). If the owning process is dead, remove the stale lock immediately.

---

#### [DATA-002] LOW -- _store_dataframe in historical_sync.py bypasses write lock

**File:Line**: `historical_sync.py:453-458`

`_store_dataframe()` in `historical_sync.py` calls `store.conn.execute()` directly without wrapping in `store._write_operation()`. Every write path in the store is supposed to go through the context manager.

**Root cause**: The module-level helper function accesses the connection directly rather than routing through the store's write guard.

**Impact**: No deadlock — the threading lock inside `_write_operation` is just for intra-process coordination. The file lock is the multi-process guard and is also not held. If a sync and a WS bar-persist run simultaneously from two threads in the same process, DuckDB's in-process serialisation still prevents corruption. However the intent of the lock is violated and a future multi-process deployment could corrupt the DB.

**Fix**: Replace the direct `store.conn.execute()` calls in `_store_dataframe()` and `_update_metadata()` in `historical_sync.py` with `with store._write_operation():`.

---

#### [DATA-003] LOW -- detect_gaps() loads all timestamps into Python (O(n) memory)

**File:Line**: `historical_maintenance.py:31-36`

```python
rows = store.conn.execute(f"""
    SELECT timestamp
    FROM {store.table_ohlcv}
    WHERE symbol = ? AND timeframe = ?
    ORDER BY timestamp ASC
""", [symbol, timeframe]).fetchall()
```

For a 1-minute table with 2 years of BTCUSDT data this is approximately 1,050,000 rows fetched into Python memory before the gap scan loop.

**Fix**: Compute gaps entirely in DuckDB using a `LAG` window function:

```sql
SELECT
    LAG(timestamp) OVER (ORDER BY timestamp) + INTERVAL (tf_minutes) MINUTE AS gap_start,
    timestamp - INTERVAL (tf_minutes) MINUTE AS gap_end
FROM {table}
WHERE symbol = ? AND timeframe = ?
QUALIFY gap_end > gap_start
```

This returns only the gap rows, keeping memory usage constant.

---

#### [DATA-004] LOW -- 5% gap tolerance silently swallows valid gaps on larger timeframes

**File:Line**: `historical_maintenance.py:49`

```python
if actual_delta > expected_delta * 1.05:
```

For a daily (`D`) timeframe, `expected_delta` is 1440 minutes. The 5% tolerance is 72 minutes — meaning a 70-minute data gap in a daily chart is invisible to `detect_gaps()`.

**Fix**: Use an absolute tolerance (e.g., `expected_delta + timedelta(minutes=1)`) rather than a percentage multiplier, or scale the percentage tightly (1% not 5%).

---

#### [DATA-005] LOW -- heal_comprehensive() deletes ALL rows for a duplicate timestamp

**File:Line**: `historical_maintenance.py:296-300`

```python
for sym, tf, ts, cnt in dupes:
    store.conn.execute(f"""
        DELETE FROM {store.table_ohlcv}
        WHERE symbol = ? AND timeframe = ? AND timestamp = ?
    """, [sym, tf, ts])
```

This deletes every row for a duplicate timestamp. If the GROUP BY found `cnt=2` duplicate rows, both are deleted. The intent is to keep one. There is no subsequent re-insert here — the data is permanently lost.

**Fix**: Use a `DELETE ... WHERE rowid NOT IN (SELECT MIN(rowid) ... GROUP BY symbol, timeframe, timestamp)` to keep exactly one occurrence.

---

### src/data/historical_sync.py

**Summary**: Sync functions operating on `HistoricalDataStore`. Fetches from Bybit API with pagination, stores via module-level `_store_dataframe()`.

#### [DATA-006] MED -- _sync_symbol_timeframe() only fills boundary gaps

**File:Line**: `historical_sync.py:318-332`

The function computes `ranges_to_fetch` to cover data before `first_ts` and after `last_ts`. It does not detect or fill internal gaps (holes in the middle of stored data). A crash mid-sync leaves an internal gap that `sync()` will never repair.

**Fix**: After computing boundary ranges, call `detect_gaps()` and add any internal gap ranges to `ranges_to_fetch`.

---

#### [DATA-007] LOW -- No retry on transient API errors during _fetch_from_api()

**File:Line**: `historical_sync.py:401-403`

```python
except Exception as e:
    store.logger.error(f"API error fetching {symbol}: {e}")
    break
```

Any exception (network timeout, rate limit 429, transient server error) immediately breaks the pagination loop. The partial result is stored and the sync reports success with fewer candles than expected.

**Fix**: Add exponential backoff retry (3 attempts, 1s/2s/4s delays) before breaking. Log at WARNING not ERROR for retried failures.

---

### src/data/historical_maintenance.py

**Summary**: Gap detection and comprehensive healing. See DATA-003, DATA-004, DATA-005 above.

**Positive**: `fill_gaps()` correctly accepts `symbol=None` and `timeframe=None` to scan all combinations. `heal()` runs before/after gap counts for audit visibility.

---

### src/data/realtime_state.py

**Summary**: Thread-safe in-memory state manager for all WebSocket-fed data. Uses `threading.RLock` for state mutations and a separate `threading.Lock` for callback lists.

#### [DATA-008] LOW -- append_bar() auto-init ignores prior buffer size configuration

**File:Line**: `realtime_state.py` (append_bar method)

When `append_bar()` is called for an `(env, symbol, tf)` triple that has no buffer, it auto-initialises with a default `maxlen`. If `init_bar_buffer()` was previously called with a custom `maxlen` for that key but data then came in on a different env, the buffer is silently created with the default size.

**Impact**: Low. The auto-init includes a warning log. The wrong size is cosmetic — it does not corrupt data.

---

#### [DATA-009] LOW -- is_websocket_healthy() accepts a max_stale_seconds parameter but ignores it

The signature accepts `max_stale_seconds` but the implementation does not use it — it checks only `_private_ws_connected` and whether wallet data has been received. Callers passing a stale threshold receive no benefit.

**Fix**: Either implement the stale check (compare last update timestamp to `datetime.now()`) or remove the parameter from the signature.

---

### src/data/realtime_bootstrap.py

**Summary**: WebSocket lifecycle management with monitor thread. Manages public + private connections, dynamic subscription, bar persistence, and 60-second health polling.

#### [DATA-010] HIGH -- Dynamic symbol subscriptions are lost after WebSocket reconnect

**File:Line**: `realtime_bootstrap.py:559-564` (reconnect detection), `realtime_bootstrap.py:351-412` (`subscribe_symbol_dynamic`)

Reconnect detection happens in `_on_kline()` and `_on_ticker()`: when `_public_connected` is `False` and data arrives, it is set back to `True`. This relies entirely on pybit's internal reconnect behaviour restoring the original subscriptions.

However, symbols added via `subscribe_symbol_dynamic()` after startup are tracked in `self._symbols` and subscribed via the client — but pybit does not persist dynamically added subscriptions across reconnects. After a reconnect, only the initial `_start_public_streams()` subscriptions are active. Any dynamically added symbols silently stop receiving data.

**Root cause**: `_handle_stale_connection()` clears `_public_connected` but never re-subscribes. The reconnect detection path also does not re-subscribe.

**Impact**: A position opened on SOLUSDT (dynamically added) will have no WS price/kline data after any WS reconnect. Trades execute blind until a REST fallback kicks in.

**Fix**: Add a `_resubscribe_all()` method that iterates `self._symbols` and re-calls the full subscription sequence (`subscribe_ticker`, `subscribe_klines`, etc.). Call this in the reconnect detection branch in `_on_ticker()` and `_on_kline()`.

---

#### [DATA-011] MED -- _handle_stale_connection() marks disconnected but never triggers reconnect

**File:Line**: `realtime_bootstrap.py:1079-1117`

When the monitor detects 60 seconds of no data:
1. REST wallet/position refresh is attempted.
2. `_public_connected` and `_private_connected` are set to `False`.
3. `set_public_ws_reconnecting()` / `set_private_ws_reconnecting()` are called on state.

Nothing actively reconnects the WebSocket. The code relies on pybit's internal reconnect thread waking up on its own schedule. If pybit's connection is in a half-open TCP state (not triggering its own reconnect), the bootstrap will poll REST forever but never re-establish WebSocket streams.

**Fix**: Add an explicit `self.client.reconnect_public_ws()` call (or equivalent) in `_handle_stale_connection()` if `_public_connected` is being cleared.

---

#### [DATA-012] MED -- get_health() returns healthy=True when both WS and data are absent at startup

**File:Line**: `realtime_bootstrap.py:1139-1140`

```python
"healthy": has_data or using_rest_fallback,
```

At startup, before any data arrives, `has_data` is `False`. `using_rest_fallback` is `not (self._public_connected or self._private_connected)`. If pybit is still connecting (not yet connected), both flags are `False`, making `using_rest_fallback = True`, so `healthy = True`.

A caller checking health before any data is available gets `healthy=True` when the system is not actually ready.

**Fix**: Require at minimum that `_fetch_initial_wallet()` succeeded (wallet data seeded) before reporting healthy, regardless of WS connection state.

---

#### [DATA-013] MED -- subscribe_kline_intervals() updates sub_config but not the subscription set

**File:Line**: `realtime_bootstrap.py:474`

```python
self.sub_config.kline_intervals.extend(new_intervals)
```

`subscribe_kline_intervals()` subscribes new intervals for one symbol and extends `sub_config.kline_intervals`. But this means any symbol subscribed after this call (via `subscribe_symbol_dynamic()`) will also try to subscribe the new intervals, even if those intervals were only needed for one specific symbol.

**Impact**: Excess subscriptions sent to Bybit for subsequent symbols. Low risk but wastes bandwidth.

---

#### [DATA-014] LOW -- _persist_bar_to_db() uses lazy singleton store, not the existing connection

**File:Line**: `realtime_bootstrap.py:660-666`

```python
def _get_db_store(self) -> "HistoricalDataStore":
    if self._db_store is None:
        from .historical_data_store import get_historical_store
        self._db_store = get_historical_store(env=self.env)
    return self._db_store
```

`get_historical_store()` returns the global singleton. This is correct. However, the singleton's `_write_operation()` context manager acquires a threading lock and a file lock. The WS callback thread calling `_persist_bar_to_db()` will block here for up to 30 seconds if a sync operation holds the lock.

**Impact**: WS message processing is blocked, causing dropped messages and stale kline state during sync.

**Fix**: Offload DB persistence to a dedicated writer thread (bounded queue, single consumer). The WS callback enqueues the bar and returns immediately.

---

### src/data/market_data.py

**Summary**: Hybrid WS/REST cache provider with per-source TTLs. Correct REST fallback when WS data is absent or expired.

#### [DATA-015] LOW -- get_funding_rate() treats funding_rate == 0 as missing WS data

**File:Line**: `market_data.py` (get_funding_rate method)

A typical check pattern: `if ticker and ticker.funding_rate:` incorrectly skips WS data when `funding_rate` is exactly `0.0` (a valid value). This causes a REST fallback on every call during periods of zero funding, adding unnecessary REST overhead.

**Fix**: Use `if ticker and ticker.funding_rate is not None:`.

---

**Positive**: TTL-based expiry, WS-primary REST-fallback design, and per-source cache isolation are all correct patterns. The implementation is clean.

---

### src/core/safety.py

**Summary**: Shared `DailyLossTracker` singleton, `PanicState` with callback chain, `SafetyChecks` pre-trade guard.

#### [DATA-016] MED -- RiskManager reads _daily_pnl directly without checking _seed_failed

`DailyLossTracker._seed_failed` blocks trading when `seed_from_exchange()` fails. `SafetyChecks.check_daily_loss_limit()` correctly calls `check_limit()` which checks `_seed_failed`. However, `RiskManager.check()` accesses the tracker's `daily_pnl` property directly for its own loss calculations and does not go through `check_limit()`. If the seed failed, `_daily_pnl` is 0.0, making the loss check trivially pass.

**Fix**: `RiskManager.check()` should call `get_daily_loss_tracker().check_limit(max_daily_loss)` rather than reading `daily_pnl` directly, or add an explicit `if tracker.seed_failed: return blocked` guard.

---

#### [DATA-017] LOW -- panic_close_all() cancel-then-close race leaves position unprotected

**File:Line**: `safety.py:265-311`

In `panic_close_all()`, the flow is:
1. Cancel all open orders (including SL/TP conditionals).
2. Close all positions.

If step 2 fails for a position (exchange error, network timeout), the position is open with no SL/TP protection. This can happen transiently since the retry count is only 3.

**Fix**: Reverse the order within `panic_close_all()` to match the safer pattern described below under DATA-019: attempt close first, then cancel conditionals. Or, submit close orders in the same REST call as cancellations using Bybit's batch endpoint.

---

**Positive**: `DailyLossTracker._reset_if_needed()` correctly uses `datetime.now(timezone.utc)` — timezone-aware reset. `seed_from_exchange()` sets `_seed_failed=True` on exception, blocking trading until the seed succeeds. `PanicState.trigger()` correctly copies the callback list under lock before dispatching, preventing deadlock.

---

### src/core/exchange_manager.py

**Summary**: Singleton facade. Enforces mode/API mapping, activates DCP at startup, verifies one-way mode, delegates to decomposed exchange_* modules.

**Positive**: DCP (Disconnect Cancel All) activated at 10s window on startup for live mode. One-way mode verification raises `ValueError` on failure — correct fail-closed. Double-init guard via `_initialized` flag.

**No significant bugs found.** The singleton initialisation, API mapping enforcement, and delegation pattern are all correct.

---

### src/core/exchange_positions.py

**Summary**: Position queries, TP/SL setters, leverage/margin management, orphaned order reconciliation.

#### [DATA-018] HIGH -- close_position()-flow: cancel conditional orders BEFORE placing close market order

**File:Line**: `exchange_positions.py:cancel_position_conditional_orders` (called from `exchange_orders_manage.py:close_position`)

The close flow (verified by grepping `exchange_orders_manage.py`) cancels TP/SL conditional orders before placing the market close order. If the market close order placement fails (exchange error, insufficient liquidity, network timeout), the position is left open with no protective stop loss or take profit.

This is a direct violation of the live safety principle: safety guards must block trading when data is unavailable, not allow it.

**Fix**: Reverse the order — place the market close order first, verify it is accepted (not just submitted), then cancel conditional orders. If the close fails, leave the SL/TP in place.

---

#### [DATA-019] MED -- reconcile_orphaned_orders() silently proceeds on get_all_positions() failure

**File:Line**: `exchange_positions.py:468-572`

```python
try:
    positions = get_all_positions(manager)
    open_symbols = {pos.symbol for pos in positions if pos.is_open}
    ...
except Exception as e:
    manager.logger.error(f"Error reconciling orphaned orders: {e}")
```

The outer `except` catches `get_all_positions()` failures and logs, but the inner loop has already built `open_symbols` from a partial or empty result. The code inside the `try` block that iterates `orders_by_symbol` will see `open_symbols` as empty, cancelling all bot-generated conditional orders for every symbol.

Looking at the actual code flow: if `get_all_positions()` raises, the entire function body catches it at the outer except, so no orders are actually cancelled on a full exception. However, partial failures (a REST timeout that returns empty list instead of raising) would leave `open_symbols = set()` and trigger mass cancellation.

**Fix**: Explicitly validate that `positions` is not empty before proceeding with reconciliation. Add: `if not positions: return cancelled_by_symbol` after the `get_all_positions()` call if the exchange normally has positions.

---

#### [DATA-020] LOW -- unrealized_pnl_percent calculated against notional, not margin

**File:Line**: `exchange_positions.py:64` and `exchange_positions.py:117`

```python
unrealized_pnl_percent=unrealized_pnl / (size * entry_price) * 100 if size and entry_price else 0,
```

`size * entry_price` is the position notional. PnL percent is conventionally expressed against the margin deployed (notional / leverage). At 10x leverage, a 1% notional move = 10% margin move, but this formula reports 1%.

**Impact**: Display only. No trading logic uses this field directly.

**Fix**: `unrealized_pnl_percent = unrealized_pnl / (size * entry_price / leverage) * 100`.

---

### src/core/exchange_orders_market.py

**Summary**: Market buy/sell with and without TP/SL. `_extract_fill_price()` falls back to pre-order quote if `avgPrice` is absent or zero.

#### [DATA-021] LOW -- _extract_fill_price() stores wrong entry price when avgPrice=0

**File:Line**: `exchange_orders_market.py:18-45`

Bybit returns `avgPrice=0` for a market order that is submitted but not yet fully acknowledged (rare race condition in async processing). The function correctly falls back to the pre-order quote price. However, this quote price was fetched before the order was placed; slippage, market impact, and the time between quote and fill mean the stored `fill_price` can materially differ from the actual fill.

**Impact**: `OrderResult.price` may be wrong by the slippage amount. TP/SL calculations based on this price will be off by the same amount.

**Fix**: If `avgPrice=0`, poll `get_order(order_id)` once with a short delay (0.5s) to retrieve the actual fill price before falling back to the quote.

---

#### [DATA-022] LOW -- reduce_only not propagated to OrderResult

**File:Line**: `exchange_orders_market.py:74-78`, `exchange_orders_market.py:117-121`

`market_buy()` and `market_sell()` accept `reduce_only: bool` and pass it to the exchange, but the returned `OrderResult` is constructed without `reduce_only=reduce_only`. Callers reading `result.reduce_only` see the default value.

**Fix**: Add `reduce_only=reduce_only` to all `OrderResult(...)` constructors in this module.

---

**Positive**: The `reduce_only=True` parameter is correctly threaded through to `BybitClient.create_order()`. The fail-fast `if usd_amount <= 0` guard at the top of each function is correct. TP/SL fields are correctly propagated in `market_buy_with_tpsl()` and `market_sell_with_tpsl()`.

---

### src/core/order_executor.py

**Summary**: Signal → RiskManager → pre-trade safety → ExchangeManager pipeline with WS-based fill confirmation and idempotency cache.

#### [DATA-023] MED -- Price deviation check calls bybit.get_ticker() directly, bypassing WS/REST cache

**File:Line**: `order_executor.py` (`_check_price_deviation` method, ~line 700)

The price deviation guard (G14.3) fetches a fresh ticker via direct `bybit.get_ticker()` REST call rather than using `MarketData.get_latest_price()` or `RealtimeState.get_ticker()`. This adds a synchronous REST round-trip to every order execution path, increasing latency and consuming rate limit budget.

**Fix**: Use the existing `MarketData` cache (which already has WS/REST fallback) for the reference price.

---

**Positive**: Idempotency via `_recorded_orders` (bounded `OrderedDict`, 10,000-entry LRU) is well designed. Panic check before every execution is correct. `wait_for_fill()` has a REST fallback for WS timeout. `_validate_trading_mode()` PAPER=DEMO / REAL=LIVE consistency check is robust.

---

### src/core/risk_manager.py

**Summary**: Deterministic pre-trade risk checks: drawdown circuit breaker, position size limits, daily loss, exposure cap, funding rate cost, leverage limits.

#### [DATA-024] LOW -- check() returns allowed=True for FLAT signals without checking panic state

RiskManager.check() is called with a signal. For FLAT (close) signals the function may return `allowed=True` early without verifying `is_panic_triggered()`. If panic was triggered between the executor's panic check and the risk check, the close order proceeds, which is actually safe (closing is desirable during panic). However, the inconsistency is worth documenting.

**Impact**: None in practice — closing positions during panic is correct.

---

**Positive**: Drawdown circuit breaker, maximum open positions, minimum balance enforcement, and global risk view (position count, gross exposure) are all implemented correctly. The `PortfolioSnapshot` dataclass correctly pre-computes all inputs so the check is O(1) without any exchange calls.

---

## Cross-Module Dependencies

```
LiveRunner / PlayEngine
  └── OrderExecutor.execute(signal)
        ├── is_panic_triggered()             [safety.py global]
        ├── RiskManager.check(signal, portfolio)
        │     └── DailyLossTracker.check_limit()  [safety.py singleton]
        ├── _check_price_deviation()          [uses bybit.get_ticker() directly -- DATA-023]
        └── ExchangeManager.market_*_with_tpsl()
              ├── exchange_instruments.calculate_qty()
              ├── BybitClient.create_order()
              └── exchange_positions.cancel_position_conditional_orders()  [DATA-018]

RealtimeBootstrap
  ├── BybitClient (WS subscribe)
  ├── RealtimeState (write WS data)
  └── HistoricalDataStore.upsert_candle()   [blocks WS thread -- DATA-014]

SafetyChecks
  ├── DailyLossTracker [shared singleton with RiskManager]
  ├── ExchangeManager.get_balance()
  └── is_panic_triggered()

panic_close_all()
  ├── PanicState.trigger()
  ├── BybitClient.set_disconnect_cancel_all(1s)  [DCP tightened]
  ├── ExchangeManager.cancel_all_orders()
  └── ExchangeManager.close_all_positions()
        └── create_order(reduce_only=True)        [correct]
```

---

## Architecture Diagram

```
LIVE DATA FLOW
==============

Bybit Exchange
  |
  |-- WebSocket streams
  v
RealtimeBootstrap
  |-- _on_ticker()     --> RealtimeState._tickers
  |-- _on_kline()      --> RealtimeState._klines
  |    |-- _on_bar_closed()
  |         |-- _persist_bar_to_memory() --> RealtimeState._bar_buffers
  |         |-- _persist_bar_to_db()     --> HistoricalDataStore.upsert_candle()
  |                                          [blocks WS thread -- DATA-014]
  |-- _on_position()   --> RealtimeState._positions
  |-- _on_order()      --> RealtimeState._orders
  |-- _on_execution()  --> RealtimeState._executions
  |-- _on_wallet()     --> RealtimeState._wallet
  |
  +-- _monitor_loop() (every 30s)
       |-- no data for 60s? --> _handle_stale_connection()
            |-- _fetch_initial_wallet() via REST
            |-- _fetch_initial_positions() via REST
            |-- _public_connected = False  [reconnect NOT triggered -- DATA-011]
            |-- dynamic symbol subscriptions NOT restored on reconnect -- DATA-010


TRADE EXECUTION FLOW
====================

OrderExecutor.execute(signal)
  |
  |-- 1. is_panic_triggered()                    [BLOCK if True]
  |-- 2. _validate_trading_mode()
  |-- 3. SafetyChecks.run_all_checks()
  |       |-- panic state
  |       |-- DailyLossTracker.check_limit()
  |       |-- ExchangeManager.get_balance()  [REST call every time]
  |       |-- ExchangeManager.get_total_exposure()
  |-- 4. RiskManager.check(signal, portfolio)
  |-- 5. _check_price_deviation()               [direct REST call -- DATA-023]
  |-- 6. ExchangeManager.market_*_with_tpsl()
  |       |-- _validate_trading_operation()
  |       |-- BybitClient.create_order(reduce_only=False for entries)
  |       |-- _extract_fill_price()             [may use stale quote -- DATA-021]
  |-- 7. PositionManager.record_trade()         [idempotency guard]


CLOSE FLOW (unsafe ordering)
=============================

close_position(symbol)
  |-- 1. cancel_position_conditional_orders()   [SL/TP cancelled FIRST -- DATA-018]
  |-- 2. create_order(reduce_only=True)
  |       |
  |       +-- IF THIS FAILS: position is open with NO SL/TP protection

SAFE CLOSE FLOW (recommended fix)
==================================

close_position(symbol)
  |-- 1. create_order(reduce_only=True)         [close first]
  |       |-- IF FAILS: return error, SL/TP still active
  |-- 2. cancel_position_conditional_orders()   [then cancel conditionals]


SAFETY LAYER
============

ExchangeManager.__init__()
  |-- assert mode/API mapping valid  [ValueError on mismatch]
  |-- switch_to_one_way_mode()       [ValueError on failure]
  |-- set_disconnect_cancel_all(10s) [DCP activated at startup]

panic_close_all()
  |-- PanicState.trigger()
  |-- set_disconnect_cancel_all(1s)  [DCP tightened to 1s]
  |-- cancel_all_orders() x3 retry
  |-- close_all_positions() x3 retry per position
       |-- create_order(reduce_only=True)
```

---

## Finding Summary

| ID | Severity | File | Lines | Summary |
|----|----------|------|-------|---------|
| DATA-010 | **HIGH** | realtime_bootstrap.py | 559-564, 351-412 | Dynamic symbol subscriptions lost after WS reconnect |
| DATA-018 | **HIGH** | exchange_orders_manage.py (close_position) | close flow | Cancel TP/SL before close market order -- position unprotected on failure |
| DATA-011 | MED | realtime_bootstrap.py | 1079-1117 | _handle_stale_connection() marks disconnected but never triggers reconnect |
| DATA-012 | MED | realtime_bootstrap.py | 1139-1140 | get_health() returns healthy=True before any data at startup |
| DATA-013 | MED | realtime_bootstrap.py | 466-474 | subscribe_kline_intervals() adds to all future symbols, not just the caller |
| DATA-016 | MED | safety.py | ~206 | RiskManager reads daily_pnl directly, bypassing _seed_failed block |
| DATA-017 | MED | safety.py | 265-311 | panic_close_all() cancel-before-close leaves position unprotected on partial failure |
| DATA-019 | MED | exchange_positions.py | 468-572 | reconcile_orphaned_orders() cancels all orders if positions list unexpectedly empty |
| DATA-023 | MED | order_executor.py | ~700 | Price deviation check calls REST directly, bypassing WS/REST cache |
| DATA-001 | LOW | historical_data_store.py | 491-511 | Stale lock file blocks writes for 5 minutes after crash |
| DATA-002 | LOW | historical_sync.py | 453-458 | _store_dataframe bypasses _write_operation context manager |
| DATA-003 | LOW | historical_maintenance.py | 31-36 | detect_gaps() loads all timestamps into Python (O(n) memory) |
| DATA-004 | LOW | historical_maintenance.py | 49 | 5% gap tolerance swallows valid gaps on large timeframes |
| DATA-005 | LOW | historical_maintenance.py | 296-300 | heal_comprehensive() deletes ALL rows for duplicate timestamp |
| DATA-006 | LOW | historical_sync.py | 318-332 | _sync_symbol_timeframe() fills only boundary gaps, not internal gaps |
| DATA-007 | LOW | historical_sync.py | 401-403 | No retry on transient API errors in _fetch_from_api() |
| DATA-008 | LOW | realtime_state.py | append_bar | append_bar() auto-init ignores prior custom buffer size |
| DATA-009 | LOW | realtime_state.py | is_websocket_healthy | max_stale_seconds parameter accepted but ignored |
| DATA-014 | LOW | realtime_bootstrap.py | 660-666 | _persist_bar_to_db() write lock blocks WS callback thread |
| DATA-015 | LOW | market_data.py | get_funding_rate | funding_rate == 0 treated as missing, triggers unnecessary REST call |
| DATA-020 | LOW | exchange_positions.py | 64, 117 | unrealized_pnl_percent uses notional not margin (display only) |
| DATA-021 | LOW | exchange_orders_market.py | 18-45 | avgPrice=0 falls back to pre-order quote without polling for actual fill |
| DATA-022 | LOW | exchange_orders_market.py | 74-78, 117-121 | reduce_only not propagated to returned OrderResult |
| DATA-024 | LOW | risk_manager.py | check() | FLAT signals bypass panic check in risk layer (safe in practice) |

**Total: 24 findings -- 2 HIGH, 7 MED, 15 LOW**

---

## Priority Action Items

### 1. DATA-018 (HIGH) -- Fix close-position ordering

**File**: `src/core/exchange_orders_manage.py` (close_position function)

Reverse the order: place the market close order first, then cancel conditional orders. This is the most critical live safety fix — a failed close currently leaves the position with no SL/TP.

```python
# Current (UNSAFE):
cancel_position_conditional_orders(...)
create_order(reduce_only=True)

# Fix (SAFE):
result = create_order(reduce_only=True)
if result.success:
    cancel_position_conditional_orders(...)
```

---

### 2. DATA-010 (HIGH) -- Re-subscribe dynamic symbols after WS reconnect

**File**: `src/data/realtime_bootstrap.py`

Add a `_resubscribe_dynamic_symbols()` method. Call it in both reconnect detection branches (`_on_kline` and `_on_ticker`) when `_public_connected` transitions from `False` to `True`.

```python
def _resubscribe_dynamic_symbols(self):
    """Re-subscribe symbols added after initial startup."""
    initial_symbols = set(self.app_config.trading.default_symbols)
    dynamic_symbols = self._symbols - initial_symbols
    for symbol in dynamic_symbols:
        self.subscribe_symbol_dynamic(symbol)
```

---

### 3. DATA-011 (MED) -- Trigger active reconnect when stale

**File**: `src/data/realtime_bootstrap.py:_handle_stale_connection()`

After marking connections as reconnecting, add an explicit reconnect attempt:

```python
try:
    self.client.reconnect_public_ws()
except Exception as e:
    self.logger.warning(f"Reconnect attempt failed: {e}")
```

---

### 4. DATA-016 (MED) -- Thread _seed_failed through RiskManager

**File**: `src/core/risk_manager.py`

```python
tracker = get_daily_loss_tracker()
ok, reason = tracker.check_limit(self.config.risk.max_daily_loss_usd)
if not ok:
    return RiskDecision(allowed=False, reason=reason)
```

Use `check_limit()` instead of reading `daily_pnl` directly so the `_seed_failed` block is respected.

---

### 5. DATA-005 (LOW) -- Fix duplicate deduplication data loss

**File**: `src/data/historical_maintenance.py:296-300`

```python
# Replace DELETE-all with keep-one:
store.conn.execute(f"""
    DELETE FROM {store.table_ohlcv}
    WHERE symbol = ? AND timeframe = ? AND timestamp = ?
    AND rowid NOT IN (
        SELECT MIN(rowid) FROM {store.table_ohlcv}
        WHERE symbol = ? AND timeframe = ? AND timestamp = ?
    )
""", [sym, tf, ts, sym, tf, ts])
```

---

## Answers to Key Review Questions

| Question | Answer |
|----------|--------|
| DuckDB locking correct? | File lock + threading lock pattern is correct. `historical_sync.py` bypasses it (DATA-002). |
| Gap detection robust? | O(n) memory (DATA-003), 5% tolerance too wide (DATA-004), internal gaps not filled (DATA-006). |
| Sync consistency? | Boundary-only sync leaves internal gaps unfilled (DATA-006). No retry on API errors (DATA-007). |
| Thread safety? | RLock on state, separate Lock on callbacks. Correct. WS callback blocks on DB write (DATA-014). |
| WS reconnection? | Dynamic symbols not re-subscribed after reconnect (DATA-010, HIGH). No active reconnect trigger (DATA-011). |
| Rate limiting? | No API 429 retry in sync (DATA-007). Price deviation check adds extra REST call per trade (DATA-023). |
| reduce_only correct? | Close orders correctly pass `reduce_only=True`. Not propagated to OrderResult (DATA-022, cosmetic). |
| Fail-closed safety? | Close-before-cancel violated in close_position flow (DATA-018, HIGH). get_health() misleading at startup (DATA-012). |
| Panic close partial fills? | Cancel-before-close leaves position unprotected on close failure (DATA-017). |
| DailyLossTracker timezone? | Correctly uses `datetime.now(timezone.utc)` for midnight reset. |
