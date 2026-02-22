# Full Codebase Review — 2026-02-21

**Scope**: 319 Python files, ~124K lines across 15 modules in `src/`
**Method**: 6 parallel specialist agents (engine, indicators, safety, backtest, CLI, cross-cutting)
**Overall Assessment**: Production-quality codebase with strong safety architecture. Excellent CLAUDE.md compliance.

---

## Summary

| Severity | Count | Key Areas |
|----------|-------|-----------|
| **Critical** | 5 | Live safety (reduce_only), thread safety (live adapter locks), duplicate logging |
| **High** | 19 | Dual PnL trackers, partial close bypass, FP drift, structure path bug, gate timeout |
| **Medium** | 32 | Silent exceptions, O(n) indicators, timezone inconsistency, dead code, import patterns |
| **Low** | 33 | Clean compliance checks, cosmetic, minor naming |
| **Total** | **89** | |

---

## CRITICAL (5 findings)

### C1. `close_position_tool` missing `reduce_only=True` [CLI]
- **File**: `src/tools/position_tools.py:734`
- `exchange.close_position(symbol=symbol, cancel_conditional_orders=...)` does NOT pass `reduce_only=True`
- CLAUDE.md mandates: "All close/partial-close market orders must pass `reduce_only=True`"
- Without this, a close order could accidentally open a reverse position if TP/SL already closed the original
- **Fix**: Add `reduce_only=True` parameter

### C2. `_check_tf_warmup` reads `_engine_managed_keys` without lock [Engine]
- **File**: `src/engine/adapters/live.py:1494`
- Reads `_engine_managed_keys` outside the `indicator_cache._lock` block, creating a race condition with concurrent WebSocket candle callbacks
- **Fix**: Move the read inside the `with indicator_cache._lock:` block

### C3. `_warmup_structures` iterates `indicator_cache._indicators.keys()` without lock [Engine]
- **File**: `src/engine/adapters/live.py:941`
- During warmup, iterates internal dict keys without holding `_lock` while WebSocket callbacks may modify the dict concurrently
- **Fix**: Capture keys under lock: `with indicator_cache._lock: keys = list(indicator_cache._indicators.keys())`

### C4. `_update_structure_state_for_tf` iterates `indicator_cache._indicators.keys()` without lock [Engine]
- **File**: `src/engine/adapters/live.py:1608`
- Same pattern as C3 but in a hot path called on every candle close — higher risk
- **Fix**: Same as C3

### C5. Duplicate log line in `_load_tf_bars` [Engine]
- **File**: `src/engine/adapters/live.py:894` and `:920`
- Same log message at line 894 (outside `if bars:`) AND line 920 (inside). Causes confusing double-logging and misleading "Loaded 0 bars" messages
- **Fix**: Remove the line-894 version

---

## HIGH (19 findings)

### Engine & Core (7)

| ID | Finding | File | Impact |
|----|---------|------|--------|
| H-E1 | `BacktestExchange.step()` is a no-op but protocol requires candle processing | `engine/adapters/backtest.py` | Architectural confusion |
| H-E2 | `LiveExchange._is_ws_data_fresh` 60s default too stale for position data | `engine/adapters/live.py:1716` | Could show closed positions as open |
| H-E3 | `get_position` near-zero division risk for tiny-price tokens | `core/exchange_positions.py:64` | Possible division error |
| H-E4 | `submit_close` partial close bypasses ExchangeManager safety layers | `engine/adapters/live.py:2344` | Skips trading mode validation, WS tracking |
| H-E5 | `open_position_with_rr` has 500ms `time.sleep` in critical path | `core/exchange_orders_stop.py:384` | Blocks calling thread |
| H-E6 | `DailyLossTracker.check_limit` error message has inverted comparison | `core/safety.py:76` | Misleading error output |
| H-E7 | `limit_buy/sell_with_tpsl` don't call `ws.ensure_symbol_tracked` | `core/exchange_orders_limit.py:130-145` | Missing WS tracking for TP/SL orders |

### Safety & Exchanges (3)

| ID | Finding | File | Impact |
|----|---------|------|--------|
| H-S1 | `BybitClient` stores API key/secret as cleartext instance attributes | `exchanges/bybit_client.py:162` | Credential leak risk in debug/repr |
| H-S2 | `GlobalRiskView` and `DailyLossTracker` maintain separate daily PnL trackers | `risk/global_risk.py:171` vs `core/safety.py:23` | Trackers could diverge |
| H-S3 | `ExchangeManager()` singleton can be bypassed in GlobalRiskView | `risk/global_risk.py:229` | Could init with empty config |

### Indicators & Structures (3)

| ID | Finding | File | Impact |
|----|---------|------|--------|
| H-I1 | MFI first-bar buffer/sum desync for `length=1` edge case | `indicators/incremental/buffer_based.py:337-347` | Incorrect MFI values |
| H-I2 | SMA/BBands floating-point drift in running sums over 100k+ bars | `indicators/incremental/core.py:91-107` | Determinism issues on long runs |
| H-I3 | PSAR initial direction based on single bar, differs from pandas_ta | `indicators/incremental/stateful.py:42-43,73-79` | Wrong first few PSAR values |

### Backtest & Data (3)

| ID | Finding | File | Impact |
|----|---------|------|--------|
| H-B1 | `get_structure` strips wrong prefix length (`[4:]` should be `[8:]`) | `backtest/runtime/snapshot_view.py:1189` | Structure lookups via dotted path fail |
| H-B2 | Sharpe ratio uses population variance (N) not sample (N-1) | `backtest/metrics.py` | Inflated Sharpe for small samples |
| H-B3 | `_get_exec_result` returns first dict entry, not actual exec TF | `backtest/runtime/preflight.py:263-267` | Wrong TF in preflight output |

### CLI & Tools (3)

| ID | Finding | File | Impact |
|----|---------|------|--------|
| H-C1 | Logging violations — 3 files use `import logging` + `logging.getLogger("trade")` | `cli/subcommands/backtest.py:140`, `play.py:186`, `menus/plays_menu.py:392` | Bypasses `get_module_logger()` |
| H-C2 | Gate timeout default inconsistency: argparser=300s vs constant=600s | `cli/argparser.py:276` vs `cli/validate.py:57` | G10 times out on WSL2 |
| H-C3 | Timeframe validation bug: `"D".lower()` → `"d"` not in CANONICAL_TIMEFRAMES | `utils/timeframes.py` | Fragile validation for daily TF |

### Cross-Cutting (3 — counted under their respective domains above for dedup)

| ID | Finding | File | Impact |
|----|---------|------|--------|
| H-X1 | Duplicate `short_hash()` in `debug.py` and `run_logger.py` | `utils/debug.py:106`, `backtest/logging/run_logger.py:53` | Code duplication |
| H-X2 | Bare `import logging` in non-infrastructure code (4 files) | See H-C1 + `backtest/runner.py:1025` | Convention violation |
| H-X3 | Inconsistent `~/.trade/` path: `os.path.expanduser` vs `Path.home()` | 4 files vs 9 files | Pattern inconsistency |

---

## MEDIUM (32 findings)

### Engine & Core (7)

| ID | Finding | File |
|----|---------|------|
| M-E1 | `execute_signal` mutates `signal.metadata` in place | `engine/play_engine.py:618-621` |
| M-E2 | `ExchangeManager.__init__` sets `_initialized = True` before all init work | `core/exchange_manager.py:220-228` |
| M-E3 | `EngineManager` creates own asyncio loop, fragile with LiveRunner | `engine/manager.py` |
| M-E4 | Signal handler calls `self.stop()` which does thread ops | `core/application.py:547` |
| M-E5 | Position side strings: lowercase in core vs UPPERCASE in engine | Multiple |
| M-E6 | `cancel_all_orders` returns True when no orders exist (masks API errors) | `core/exchange_orders_manage.py:94-96` |
| M-E7 | `get_candle_for_tf` positive/negative index handling is identical in both branches | `engine/adapters/live.py:1252-1258` |

### Safety & Exchanges (8)

| ID | Finding | File |
|----|---------|------|
| M-S1 | `close_position` lacks `order_link_id` for idempotent retry | `core/exchange_orders_manage.py:195` |
| M-S2 | `market_close()` OrderResult doesn't reflect `reduce_only=True` | `core/exchange_orders_market.py:147-171` |
| M-S3 | Race window in `_on_order_update` between status check and deletion | `core/order_executor.py:161-181` |
| M-S4 | `PanicState._triggered` is bool, not Event — no immediate notification | `core/safety.py:181-245` |
| M-S5 | `batch_market_orders` lacks `order_link_id` for idempotent retries | `core/exchange_orders_manage.py:345` |
| M-S6 | `_check_price_deviation` reference_price never set on Signal | `core/order_executor.py:745` |
| M-S7 | WebSocket health grace period (30s) allows stale-data trades | `risk/global_risk.py:273-281` |
| M-S8 | API key/secret passed to WS in plaintext (surface area concern) | `exchanges/bybit_websocket.py:85-95` |

### Indicators & Structures (7)

| ID | Finding | File |
|----|---------|------|
| M-I1 | 8 indicators have O(length) ops, could use MonotonicDeque for O(1) | `core.py`, `trivial.py`, `stateful.py`, `adaptive.py` |
| M-I2 | Mutable class-level attrs on BaseIncrementalDetector (latent footgun) | `structures/base.py:60-62` |
| M-I3 | `TFIncrementalState.update()` imports debug utilities inside method body | `structures/state.py:125-126` |
| M-I4 | `batch_wrapper.py` bypasses `validate_and_create()` factory | `structures/batch_wrapper.py:42` |
| M-I5 | Swing detector is O(left+right+1) per check, not O(1) | `structures/detectors/swing.py` |
| M-I6 | DerivedZone `_regen()` rebuilds all K slots on each source change | `structures/detectors/derived_zone.py` |
| M-I7 | MarketStructure `_swing_highs/_swing_lows` grow unbounded | `structures/detectors/market_structure.py` |

### Backtest & Data (5)

| ID | Finding | File |
|----|---------|------|
| M-B1 | `near_pct` tolerance: no guard against double/no normalization | `backtest/rules/dsl_parser.py:568-569` |
| M-B2 | `_normalize_rhs_for_operator` hardcoded enum values need manual updates | `backtest/rules/dsl_parser.py:500-521` |
| M-B3 | `state_tracker.py` block_history pruning creates new list every excess bar | `backtest/runtime/state_tracker.py:335-343` |
| M-B4 | `RuntimeSnapshotView.get_feature_value` O(n) structure path resolution | `backtest/runtime/snapshot_view.py:803-968` |
| M-B5 | `sync_forward` uses naive `datetime.now()` mixed with tz-aware DB timestamps | `data/historical_sync.py:269` |

### CLI & Tools (5)

| ID | Finding | File |
|----|---------|------|
| M-C1 | Missing `@functools.wraps` on `safe_menu_action` decorator | `cli/utils.py` |
| M-C2 | `"size"` key alongside `"size_usdt"` in position tool dicts | `tools/position_tools.py:52` |
| M-C3 | Missing `newline='\n'` in 8 file open calls | `cli/validate.py`, `cli/menus/backtest_analytics_menu.py` |
| M-C4 | ~60 bare `assert isinstance(...)` in production menu code (stripped in -O) | `cli/menus/*.py` |
| M-C5 | Private attribute access patterns (6 files reach into `._instances`, `._lock`, etc.) | `cli/menus/plays_menu.py`, `cli/subcommands/play.py`, etc. |

### Cross-Cutting (4 — counted under domains above for dedup)

| ID | Finding | File |
|----|---------|------|
| M-X1 | 44 `except Exception: pass` occurrences, some in engine hot path | `engine/play_engine.py:491,1821,2136` |
| M-X2 | `from __future__ import annotations` used in 71/165 files (inconsistent) | Across `src/` |
| M-X3 | 47 `type: ignore` comments clustered in structure detectors | `structures/detectors/*.py` |
| M-X4 | `asyncio.TimeoutError, Exception` redundant catch | `cli/subcommands/play.py:261` |

---

## LOW (33 findings)

### Cross-Cutting — All Clean (12 checks passed)

| Check | Result |
|-------|--------|
| No `Optional[X]` / `Union[X, Y]` in type annotations | CLEAN |
| No banned timeframe names (htf/ltf/mtf/HTF/LTF/MTF) | CLEAN |
| No `execution_tf` (banned) | CLEAN |
| No `idea_hash` (deprecated) | CLEAN |
| No `size_usd` (banned) | CLEAN |
| No wildcard imports | CLEAN |
| No `logging.disable()` calls | CLEAN |
| No deprecated `blocks:` DSL keyword | CLEAN |
| No `Optional`/`Union` imports from typing | CLEAN |
| All `type: ignore` comments are specific (have error codes) | CLEAN |
| No DataFrame operations in engine hot loop | CLEAN |
| File writes use `newline='\n'` | MOSTLY CLEAN (see M-C3) |

### Other Low Findings (21)

<details>
<summary>Click to expand all low findings</summary>

| ID | Finding | Source |
|----|---------|--------|
| L-E1 | Unused `Decimal` import in exchange_orders_stop.py | Engine |
| L-E2 | Absolute import `from src.utils.logger` instead of relative | Engine |
| L-E3 | `add_margin` reaches through two abstraction levels | Engine |
| L-E4 | Lazy import of logger inside function | Engine |
| L-E5 | `TFIndexManager` uses O(log N) bisect, not O(1) as docs claim | Engine |
| L-S1 | DailyLossTracker midnight reset may be delayed | Safety |
| L-S2 | BybitClient._sync_server_time silently handles unexpected data | Safety |
| L-S3 | ExchangeManager singleton could theoretically create multiple instances | Safety |
| L-S4 | Global `threading.excepthook` replacement for WS cleanup | Safety |
| L-S5 | PositionManager uses local time, DailyLossTracker uses UTC | Safety |
| L-S6 | `open_position_with_rr` skips OrderExecutor safety checks | Safety |
| L-I1 | Factory if/elif chain could be dict lookup (O(44) → O(1)) | Indicators |
| L-I2 | EMA warmup SMA-to-exponential "jump" (standard but noted) | Indicators |
| L-I3 | _ChainedEMA seeds from first value, not SMA (pandas_ta parity) | Indicators |
| L-I4 | VWAP session boundary silently skips reset on missing timestamp | Indicators |
| L-I5 | `type: ignore` clustering in zone.py and fibonacci.py | Indicators |
| L-I6 | RingBuffer `to_array()` copies on every call | Indicators |
| L-I7 | BBands param `std` vs constructor `std_dev` naming mismatch | Indicators |
| L-B1 | `_tokenize_path` LRU cache fixed at 1024, no monitoring | Backtest |
| L-B2 | Indicator registry validates at import time (adds latency) | Backtest |
| L-B3 | `compute_warmup_bars` is now a passthrough (dead code) | Backtest |
| L-B4 | `PlayInfo.direction` detection fails for DSL 3.0 list-format actions | Backtest |
| L-C1 | Legacy compatibility comment violates ALL FORWARD NO LEGACY | CLI |
| L-C2 | `sync_forward_tool` uses bare assert on ToolResult.data | CLI |

</details>

---

## Positive Findings (Strong Patterns)

The review identified many well-implemented patterns worth preserving:

1. **Fail-closed safety architecture**: LiveRunner blocks signals on position sync failure, WS unhealthy, safety check failure, or panic state
2. **DCP (Disconnect Cancel All)**: Exchange-side safety net — Bybit cancels all orders after 10s if process crashes
3. **`reduce_only=True` enforced on closes** (except C1 above)
4. **Idempotent order retries** via `order_link_id` with Bybit's 3-minute dedup window
5. **API keys from environment only**: No hardcoded credentials, `.env` in `.gitignore`
6. **Thread safety**: Proper locking with `RLock`, `_callback_lock`, copy-under-lock iteration
7. **Daily loss seed from exchange**: On restart, queries Bybit's closed PnL to prevent reset-to-zero exploit
8. **Panic verification**: Verifies positions actually closed after panic close attempt, with retries
9. **Position reconciliation**: Periodic 5-minute reconciliation catches missed WS fills
10. **Deterministic hashing pipeline**: Canonical JSON serialization, consistent hash lengths, clear flow
11. **DSL type system**: Float equality rejection, compile-time validation, case-insensitive enums
12. **Zero CLAUDE.md naming violations**: No htf/ltf/mtf, no Optional/Union, no idea_hash, no size_usd

---

## Recommended Fix Priority

### Phase 1: Live Safety (immediate)
- [ ] **C1**: Add `reduce_only=True` to `close_position_tool`
- [ ] **C2-C4**: Add proper locking in live adapter indicator cache access
- [ ] **H-S2**: Unify daily PnL tracking (GlobalRiskView → DailyLossTracker)
- [ ] **M-S6**: Wire `reference_price` on Signal for price deviation guard
- [ ] **GATE**: `python trade_cli.py validate quick` passes

### Phase 2: Correctness Bugs
- [ ] **C5**: Remove duplicate log line in `_load_tf_bars`
- [ ] **H-B1**: Fix `get_structure` prefix stripping (`[4:]` → `[8:]` or `.removeprefix()`)
- [ ] **H-C2**: Fix gate timeout default (argparser 300 → 600)
- [ ] **H-C3**: Fix timeframe validation for "D" (case-sensitive check)
- [ ] **H-E6**: Fix DailyLossTracker error message comparison direction
- [ ] **H-E7**: Add `ws.ensure_symbol_tracked` to `limit_buy/sell_with_tpsl`
- [ ] **GATE**: `python trade_cli.py validate standard` passes

### Phase 3: Architecture & Quality
- [ ] **H-E4**: Route partial closes through ExchangeManager
- [ ] **H-X1**: Remove duplicate `short_hash()` in run_logger.py
- [ ] **H-X3**: Standardize `Path.home()` over `os.path.expanduser`
- [ ] **M-I7**: Cap MarketStructure swing history (deque with maxlen)
- [ ] **M-B3**: Use deque for block_history instead of list pruning
- [ ] **M-C3**: Add `newline='\n'` to 8 file open calls
- [ ] **M-C4**: Replace bare asserts with explicit checks in menus
- [ ] **GATE**: `python trade_cli.py validate standard` passes

### Phase 4: Performance & Polish
- [ ] **M-I1**: Use MonotonicDeque for O(1) min/max in 8 indicators
- [ ] **H-I2**: Add periodic sum recomputation for SMA/BBands FP drift
- [ ] **M-I3**: Move debug import to module level in state.py
- [ ] **L-I1**: Replace factory if/elif with dict lookup
- [ ] **L-B3**: Remove dead `compute_warmup_bars` passthrough
- [ ] **GATE**: `python scripts/run_full_suite.py` — 170/170 pass
