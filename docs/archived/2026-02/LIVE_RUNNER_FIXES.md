# Live Runner Fixes: Warmup, Status, Ctrl+C

## Context

When running a play in demo/live mode, three issues exist:
1. **Warmup fails** -- DuckDB demo database has almost no data. No REST API fallback when empty.
2. **No live status** -- after runner starts, terminal is silent until a signal fires.
3. **Ctrl+C freezes** -- signal handler deadlocks the event loop.

---

## Gate 1: REST API Warmup Fallback

**File**: `src/engine/adapters/live.py`

### Problem
`_load_tf_bars()` tries bar buffer then DuckDB. When both are empty (fresh demo account), warmup never completes. The runner sits with 0 bars for med_tf/high_tf forever.

### Fix
Add `_load_bars_from_rest_api()` as third fallback in `_load_tf_bars()`.

**Chain**: bar buffer -> DuckDB -> **REST API** -> give up

New method `_load_bars_from_rest_api(self, tf_str: str) -> list`:
- Uses `get_historical_store(env=self._env)` to get store with configured BybitClient
- Converts TF via `TIMEFRAMES` dict (e.g. `"15m"` -> `"15"`, `"D"` -> `"D"`)
- Computes time range: `now - (tf_minutes * warmup_bars)` to `now` (ms timestamps)
- Calls `store.client.get_klines(symbol, interval, limit=min(warmup_bars, 1000), end=end_ms)`
- Converts DataFrame rows to `BarRecord` objects (same pattern as `_load_bars_from_db_for_tf`)
- Logs: `"Loaded N bars from REST API for TF warm-up"`

### Acceptance
- [x] `_load_tf_bars()` calls REST when DuckDB returns empty
- [ ] Warmup logs show bars loaded from REST for all TFs (15m, 1h, D)
- [ ] Indicators initialize correctly from REST-fetched history

---

## Gate 2: Live Status Line

**File**: `src/engine/runners/live_runner.py`

### Problem
`_process_candle()` only logs at DEBUG level. User sees nothing between startup and signal generation.

### Fix
Add INFO-level status logging in `_process_candle()`:

1. **On each exec TF candle** (not non-exec noise): log bar count, close price, warmup status, signal count
2. **During warmup** (the block that skips signal eval): replace debug-only log with INFO showing warmup progress per TF buffer

### Acceptance
- [x] Each exec TF candle produces an INFO log line
- [x] Warmup phase shows progress (bars loaded per TF)
- [x] Non-exec TF candles do NOT spam the log

---

## Gate 3: Fix Ctrl+C Deadlock

**File**: `src/cli/menus/plays_menu.py`

### Problem
Signal handler calls `loop.create_task(manager.stop())` but never awaits it. The event loop is blocked on `await instance.task` inside `_run()`. The queued stop task never executes. Deadlock.

### Fix
Remove the signal handler entirely. On Windows, Ctrl+C raises `KeyboardInterrupt` directly.

Replace the async/signal handling in `_run_play()` with:
- **Remove** `_signal_handler()` and all `signal.signal()` setup
- **Catch** `KeyboardInterrupt` from `loop.run_until_complete(_run())`
- **Stop** with `asyncio.wait_for(manager.stop(), timeout=15.0)` in the except block
- **Add** timeout to all stop calls to prevent infinite hang

### Acceptance
- [x] Ctrl+C cleanly stops the runner within 15 seconds
- [x] No signal handler code remains
- [x] Stop calls have timeouts
- [x] Final stats print after shutdown

---

## Verification

1. Run `sol_trend_triple_ema` in demo mode (low_tf=15m, med_tf=1h, high_tf=D)
2. Verify warmup logs show REST API fallback loading bars for all 3 TFs
3. Verify periodic status lines appear as candles arrive
4. Press Ctrl+C and verify clean shutdown within 15 seconds
5. `python -m pyright --project pyrightconfig.json` -> 0 errors
