# TRADE TODO

Single source of truth for all open work, bugs, and task progress.

---

## Completed Work (archived)

| Item | Status | Reference |
|------|--------|-----------|
| Liquidation Parity (Bybit) | DONE | `docs/LIQUIDATION_PARITY_REVIEW.md` |
| Fast Parallel Validation | DONE | Phases 1-7 complete. 1 open gate: `validate real` 61/61 (needs data sync) |
| Health Audit Fixes | DONE | `docs/HEALTH_REPORT_2026_02_18.md` |
| Full Codebase Review | DONE | `docs/architecture/` (10 files, 253 KB, 120 findings) |
| Backtest Safety Gaps 3-6 | DONE | GAP-3/4/5/6 all FIXED |

---

## P0: Codebase Bug Fixes

**Source**: Deep line-by-line review of ~269 Python files (~80,500 lines).
**Full details**: `docs/architecture/FINDINGS_SUMMARY.md` (120 findings: 7 CRIT, 16 HIGH, 53 MED, 44 LOW)
**Per-domain reviews**: `docs/architecture/*_REVIEW.md` (8 files)

### Gate 1: DSL Critical Fixes

These 5 bugs break core Play functionality. Setup references fail, valid operators are rejected, exit detection is broken, and risk config silently misconfigures.

- [x] **DSL-CRIT-1** Added `set_setup_cache()` method to ExprEvaluator, wired in PlaySignalEvaluator constructor. Removed fragile private attr access from engine.
- [x] **DSL-CRIT-2** Added `near_pct`, `near_abs`, `between`, `in` to `OPERATOR_REGISTRY`.
- [x] **DSL-CRIT-3** Fixed `else_clause` → `else_emit` in `_play_has_exit_actions()`.
- [x] **DSL-CFG-001** Removed dead `< 1.0` auto-conversion (defaults.yml already uses 100.0 percentage form).
- [x] **BT-CRIT-1** `create_risk_policy()` now raises `ValueError` when `risk_profile=None` with `risk_mode='rules'`.
- [x] **GATE**: `python trade_cli.py validate quick` passes
- [x] **GATE**: pyright 0 errors

### Gate 2: Sim Parity Fixes

3 bugs that make backtest sim diverge from Bybit. Liquidation understates equity, bankruptcy price is wrong, forced closes are mislabeled.

- [x] **SIM-HIGH-1** Removed duplicate `apply_liquidation_fee()` call and dead method from ledger.
- [x] **SIM-HIGH-2** Added `fee_rate` param to `calculate_bankruptcy_price()`. `fill_exit()` skips fee for liquidation (fee baked into BP).
- [x] **SIM-HIGH-3** Added `end_of_data`, `force_close`, `force` to `reason_map` in `_close_position()`.
- [x] **GATE**: `python trade_cli.py validate standard` ALL 12 GATES PASSED
- [x] **GATE**: `python scripts/verify_trade_math.py` — script doesn't support risk suite (no `risk` in SUITE_DIRS). Sim parity validated via G4b (9 risk plays pass) and `validate standard` (12/12 gates).

### Gate 3: Warmup / GAP-1

~~Warmup hardcoded to 100 bars.~~ Warmup is computed dynamically from `compute_warmup_requirements()`. The `config/defaults.yml` value `engine.warmup_bars: 100` is orphaned dead code.

- [x] **ENG-001** NOT A BUG — engine intentionally delegates warmup to DataProvider.is_ready(). Backtest runner skips warmup bars entirely (never sent to engine). Live adapter checks bar count + NaN + structure readiness. EnginePhase state machine tracks WARMING_UP → READY correctly. Adding a redundant counter would couple engine to warmup computation.
- [x] **BT-007** ALREADY FIXED — `skip_preflight` path now computes warmup via `compute_warmup_requirements()`. Raises ValueError if preflight missing without `skip_preflight=True`. The `config/defaults.yml` `engine.warmup_bars: 100` is dead code (DEFAULTS.engine never accessed anywhere).
- [ ] **IND-006** ENHANCEMENT — validation that warmup estimates match actual `is_ready()` thresholds. Not a bug (indicators output NaN until ready, which propagates safely). Deferred to validation improvements.
- [ ] **GAP-2** LIVE FEATURE GAP — no REST API fallback for warmup data. `_load_tf_bars()` tries buffer → DuckDB → fails. Deferred to pre-deployment (Gate 4).
- [x] **GATE**: `python trade_cli.py validate quick` passes (with --gate-timeout 600)

### Gate 4: Live Safety (pre-deployment blockers)

12 bugs that must be fixed before any live trading. Close ordering, WS reconnect, stale data, broken pre-live gates.

- [x] **DATA-018** Fixed: close market order placed FIRST, conditional orders cancelled AFTER success. If close fails, TP/SL remain active to protect position.
- [x] **DATA-010** Fixed: added `_resubscribe_all_symbols()` method, called on reconnect detection in `_on_ticker`. All tracked symbols re-subscribed idempotently.
- [x] **ENG-009** Fixed: stale candles drained from `_candle_queue` before reconnect. Prevents processing outdated data against stale indicator state.
- [x] **ENG-013** Fixed: warmup candles now compute `ts_close = ts_open + tf_duration` instead of `ts_close = ts_open`.
- [x] **ENG-006** Fixed: `_last_reconcile_ts` no longer set on sync failure. Allows immediate retry on next candle instead of 5-min wait.
- [x] **ENG-008** NOT A BUG — both close paths (full via `close_position()` and partial via `submit_close()`) already set `reduce_only=True`. Audited all call sites; no bypass possible.
- [x] **DATA-005** Fixed: `seed_from_exchange()` now retries 3x with exponential backoff (2s, 4s, 8s). `_seed_failed` only set after all retries exhausted. Successful seed clears previous failure.
- [x] **DATA-007** Fixed: added `market_close()` function with enforced `reduce_only=True`. Wraps `market_buy/sell` with no override possible.
- [x] **CLI-011** Fixed conflict detection: `raw_data.get("positions", [])` for dict return type.
- [x] **CLI-010** Fixed balance key: `available_balance` → `available`.
- [x] **IND-004** Fixed: added `_VALID_PARAMS` registry to indicator factory. Unknown params (e.g., `af_start` instead of `af0`) now raise `ValueError`.
- [x] **DSL-006** DEFERRED — OI/funding data availability is a preflight enhancement. Runtime fails loudly if tables missing. Not a safety bug.
- [ ] **GATE**: `python trade_cli.py validate pre-live --play X` passes with correct balance/conflict checks
- [ ] **GATE**: pyright 0 errors

### Gate 5: DSL & Engine MED Fixes

18 medium-severity bugs in DSL evaluation, engine adapters, and play parsing.

- [x] **DSL-PLAY-001** Fixed `tf: exec` resolution in `play.py` — resolves pointer → role → concrete TF.
- [x] **DSL-PLAY-002** Unrecognized condition keys now raise `ValueError` (was warning).
- [x] **DSL-RISK-001** Removed legacy `atr_key` fallback in `StopLossRule.from_dict()`.
- [x] **DSL-RISK-002** Removed legacy `atr_key` fallback in `TakeProfitRule.from_dict()`.
- [x] **DSL-FREG-001** Silent 50-bar warmup default now raises `ValueError` on lookup failure.
- [x] **ENG-004** Replaced duplicated `TF_MINUTES` in subloop.py with import from `historical_data_store`.
- [x] **ENG-BUG-006** Added debug log when `end_1m` is clamped (partial 1m coverage).
- [x] **DSL-HIGH-1** NOT A BUG — `has_position` naturally prevents entry+exit conflict on same bar.
- [x] **DSL-002** NOT A BUG — operator sets (VALID_OPERATORS, ARITHMETIC_OPERATORS) are disjoint by construction.
- [x] **DSL-004** NOT A BUG — cross_above uses `<=` (TradingView standard touch-and-cross semantics).
- [x] **ENG-002** NOT A BUG — `EnginePhase.WARMING_UP` IS used on line 800 (`_is_ready()` check).
- [x] **ENG-007** NOT A BUG — unbounded queue is intentional (candles are precious, can't be recovered).
- [x] **ENG-BUG-002** NOT A BUG — `exchange.step()` is a no-op in both backtest and live modes.
- [x] **ENG-BUG-004** NOT A BUG — already handled with try/catch + error log, uses last known equity.
- [x] **ENG-BUG-014** NOT A BUG — when TFs equal, sharing cache is correct optimization.
- [x] **DSL-EXEC-002** Fixed: added `HoldsForDuration`, `OccurredWithinDuration`, `CountTrueDuration` to import and isinstance check in `extract_rule_feature_refs()`. Duration window nodes no longer invisible to warmup walker.
- [x] **ENG-BUG-010** Fixed: `_seen_candles.clear()` called after successful reconnect. Catch-up candles no longer silently dropped. Independent of ENG-009 (both fixed).
- [ ] **ENG-BUG-015** Real but low impact — np.append O(n) on 500-element arrays, ~3-10 MB/hour GC pressure. Correct behavior, optimize before sustained live sessions. Deferred.
- [x] **GATE**: `python trade_cli.py validate standard` ALL 12 GATES PASSED
- [x] **GATE**: pyright 0 errors

### Gate 6: Sim & Backtest MED Fixes

15 medium-severity bugs in simulation, metrics, risk sizing, and backtest infrastructure.

- [x] **SIM-MED-2** Skip slippage for Limit TP exits and liquidation exits.
- [x] **BT-002** Logger cleanup now logs `debug` instead of silently `pass`.
- [x] **BT-005** Fixed deprecated `utcfromtimestamp` → `fromtimestamp(tz=timezone.utc)`.
- [x] **BT-WARN-2** Fixed missing `* max_lev` in `_size_risk_based()` equity cap. Matches `SizingModel`.
- [x] **BT-WARN-5** `freeze()` returns NaN instead of inf/−inf when empty. Rollup audit updated.
- [x] **IND-FISHER-001** Fisher `is_ready` now requires `_count > self.length` (length+1 bars).
- [x] **IND-REG-003** Fisher warmup estimate: `length` → `length + 1`.
- [x] **SIM-006** NOT A BUG — `estimate_liquidation_price()` documents why mm_deduction requires qty (not available pre-trade).
- [x] **IND-FACTORY-001** NOT A BUG — `None` return is intended for vectorized fallback path.
- [x] **IND-001** NOT A BUG — RSI needs length+1 bars, ATR/SMA need length bars, each for valid mathematical reasons.
- [x] **BT-WARN-4** NOT A BUG — `calculate_warmup_start()` is a thin wrapper delegating to canonical function, actively used.
- [x] **SIM-001** COSMETIC — exit timestamp uses exec bar ts_open instead of 1m trigger time. Fixing requires SubLoop to return trigger bar timestamp. Deferred.
- [x] **SIM-MED-1** NOT A BUG — engine processes one signal per exec bar, so stale margin from partial exit can't cause incorrect rejection in same bar.
- [ ] **SIM-MED-3** FUTURE FEATURE — `ExchangeMetrics` class (217 lines) fully implemented but zero callers. Missing analytics, not a correctness bug. Needs result schema wiring to surface metrics.
- [ ] **SIM-MED-4** FUTURE FEATURE — `Constraints` class (193 lines) fully implemented but not wired. Parity risk only on altcoins/small accounts. Needs per-symbol constraint config from exchange instrument info.
- [x] **GATE**: `python trade_cli.py validate standard` ALL 12 GATES PASSED

### Gate 7: Data, CLI & Forge MED Fixes

20 medium-severity bugs in data layer, CLI tools, and forge validation.

- [x] **CLI-006** Removed double-timeout in `_run_staged_gates()` — `future.result()` no longer duplicates gate timeout.
- [x] **CLI-032** Fixed key mismatch: `total_exposure_usdt` → `exposure_usd`.
- [x] **FORGE-032** NOT A BUG — `"1m"` means "1 month" in time range context, `"30d"` already exists as alternative.
- [x] **FORGE-035** NOT A BUG — retry correctly scoped to file lock errors. Other DuckDB errors should fail, not retry.
- [x] **IND-007** BY DESIGN — Anchored VWAP excluded from parity audit (live-computed, NaN placeholders in batch).
- [x] **FORGE-001** KNOWN — Multi-TF bar dilation documented. Use `near_pct` for structure comparisons.
- [x] **DATA-001** MITIGATED — DuckDB file locking on Windows, sequential access + retry logic in place.
- [x] **DATA-003** Fixed: `_is_websocket_connected()` now checks `is_wallet_stale(60s)` in addition to connection flag. Connected-but-silent WS treated as disconnected at tool layer.
- [x] **DATA-006** Fixed: verification `get_all_positions()` call in `panic_close_all()` now retries 3x with delay.
- [x] **DATA-016** Fixed: `RiskManager.check()` now calls `_daily_tracker.check_limit()` instead of reading `_daily_pnl` directly. `_seed_failed` guard properly enforced on all code paths.
- [ ] **DATA-011** `_handle_stale_connection()` does REST refresh + marks state as unhealthy but does not force pybit reconnect. `GlobalRiskView._check_ws_health()` blocks trading after 30s unhealthy. Adding active reconnect is risky without integration testing. Deferred.
- [x] **CLI-004** NOT A BUG — `close_position()` in `exchange_orders_manage.py` hardcodes `reduce_only=True`. No caller can bypass it. Additionally, `market_close()` function added in `exchange_orders_market.py`.
- [x] **CLI-008** LOW IMPACT — gate-level timeout (300s) catches hangs. Per-play timeout improves error message only. Deferred.
- [x] **CLI-020** Fixed: `_get_exchange_manager()` now uses double-checked locking with `threading.Lock()` to prevent race condition on concurrent construction.
- [x] **CLI-027** Fixed batch tools (market, limit, cancel) — `success=(failed_count == 0)`.
- [x] **FORGE-007** Fixed error code: `MISSING_REQUIRED_FIELD` → `DSL_PARSE_ERROR` for YAML parse errors in `validate_play_file()`.
- [x] **FORGE-010** Fixed `validate_no_lookahead()` — now checks ALL pivots.
- [x] **FORGE-011** Fixed `validate_determinism()` — now generates all play TFs + 1m, uses `align_multi_tf=True`.
- [x] **FORGE-019** Added warning when both `.env` and `api_keys.env` exist.
- [x] **FORGE-008** Fixed PSAR parity — `mean_abs_diff` now computed from actual diffs, not approximated.
- [ ] **GATE**: `python trade_cli.py validate full` passes

### Gate 8: LOW Priority Cleanup

44 low-severity findings. Code hygiene, dead code removal, minor edge cases.
Full list in `docs/architecture/FINDINGS_SUMMARY.md` under "LOW (44)".

**Fixed:**
- [x] **ENG-BUG-001** Removed hardcoded `bar_index == 100` debug sentinel.
- [x] **SIM-004** Added `initial_capital > 0` validation in `Ledger.__init__()`.
- [x] **SIM-007** Added `fee_rate` to `calculate_bankruptcy_price()` (fixed in Gate 2 SIM-HIGH-2).
- [x] **BT-WARN-1** Hash function fallbacks now raise `TypeError` instead of silent degradation.
- [x] **BT-WARN-3** Removed legacy `compute_results_summary` path — raises `ValueError` if no metrics.
- [x] **IND-003** ADX `_adx_history`: `list` → `deque`, `pop(0)` → `popleft()`, `= []` → `.clear()`.
- [x] **IND-CMO-001** CMO `_pos_buf`/`_neg_buf`: `list` → `deque`, same pattern.
- [x] **DSL-SB-002** `Intent.action` now validated against `VALID_ACTIONS` in `__post_init__()`.
- [x] **CLI-014** `_run_play_backtest` now passes through CLI flags (data_env, smoke, sync, emit_snapshots, no_artifacts).
- [x] **CLI-027** Batch tools (market, limit, cancel) return `success=False` on partial failure.
- [x] **FORGE-019** Warning logged when both `.env` and `api_keys.env` exist (shadow risk).
- [x] **FORGE-010** `validate_no_lookahead()` now checks ALL pivots, not just the first.

**Evaluated OK (no fix needed):**
- [x] **ENG-003** Threading import used minimally (OK)
- [x] **ENG-BUG-003** Duplicate drawdown check is defense-in-depth (OK)
- [x] **ENG-005** Fallback evaluation warns once (OK)
- [x] **BT-001** GateFailure catch relies on `success=False` default (OK)
- [x] **BT-004** Drawdown decimal/percent convention documented (OK)
- [x] **DSL-005** `dispatch_operator` — between/in handled elsewhere (OK)
- [x] **IND-002** BBands float drift is standard numerical behavior (OK)
- [x] **IND-005** PairState `(str, Enum)` mixin unusual but correct (OK)
- [x] **DATA-002** `_detect_ascii_mode` emoji test on import (OK)
- [x] **DATA-004** Bar buffer sizes hardcoded (OK)
- [x] **CLI-002** Gate timeout 300s generous for quick tier (OK)
- [x] **CLI-005** `trading_env` validated before order params (OK)
- [x] **CLI-006b** Backtest tool double-catches exceptions (OK)
- [x] **CLI-007** Exit codes properly propagated (OK)
- [x] **FORGE-002** Seed determinism depends on numpy RNG version (OK)
- [x] **FORGE-004** DEFAULTS loaded at import time (OK)
- [x] **FORGE-005** TABLE_SUFFIXES maps backtest to _live (documented, OK)
- [x] **FORGE-006** Redaction over-matches on substring (safety-positive, OK)
- [x] **SIM-002** Liquidation equity projection duplication is defense-in-depth (OK)
- [x] **SIM-005** `debug_check_invariants` defaults to False (OK — perf)

**Remaining LOW items (evaluated):**
- [x] **ENG-BUG-005** NOT A BUG — factory injection pattern, attrs set before engine.run(), no guards bypassed.
- [x] **SIM-003** NOT A BUG — after TP/SL exit, position is closed; post-close price action is irrelevant to trade MAE/MFE.
- [x] **BT-003** NOT A BUG — unknown classification defaulting to non-terminal is the safer fallback.
- [x] **BT-006** NOT A BUG — convention-based immutability is standard; `frozen=True` would break factory injection.
- [x] **CLI-003** NOT A BUG — hardcoded test expectations are standard for validation suites.
- [x] **FORGE-003** NOT A BUG — `_prices_to_ohlcv()` construction guarantees `high >= max(open,close)`, `low <= min(open,close)`.
- [x] **FORGE-013b** NOT A BUG — `generate_synthetic_bars()` is dead code (never called); production uses `generate_synthetic_candles()` with all 34 patterns.
- [x] **FORGE-027** Fixed: added `bearer`, `jwt`, `x-api-key`, `x-api-secret` to `REDACT_KEY_PATTERNS`.

**Deferred / Resolved:**
- [x] **DATA-008** ACCEPTABLE — `_extract_fill_price` falls back to quote price with warning. Best available estimate given Bybit's `avgPrice=0` on pending fills. Actual fill arrives via WS execution callback.
- [x] **DATA-012** Fixed: `get_health()` now returns `healthy: has_data` (must have received actual data). Previous `using_rest_fallback` proxy gave false-positive at startup before any data arrived.
- [ ] **DATA-017** `panic_close_all()` cancel-before-close ordering is a defensible tradeoff. Reversing to close-first is safe only if exchange reliably rejects TP-after-close on reduce-only positions. DCP provides partial mitigation. Deferred pending integration test.
- [x] **FORGE-007b** Fixed: JSONL logger now rotates at midnight. `_write_jsonl()` checks date on every write, `_rotate_jsonl()` closes old file and opens new date-stamped file.
- [ ] **GATE**: `python trade_cli.py validate full` passes
- [ ] **GATE**: pyright 0 errors

---

## Known Issues (non-blocking)

### pandas_ta `'H'` Deprecation Warning

**Status**: Cosmetic warning, no impact on correctness. Will become error in future pandas release.

**Root cause**: `pandas_ta.vwap()` calls `anchor.upper()` internally (line 54 of `pandas_ta/overlap/vwap.py`), then passes the uppercased anchor to `index.to_period(anchor)`. Any hourly-based anchor (`"4h"` → `"4H"`, or even `"h"` → `"H"`) triggers the pandas `FutureWarning` because pandas deprecated uppercase `'H'` in favor of lowercase `'h'` for frequency aliases.

**Affected plays**: Any play using VWAP with an hourly anchor (e.g., `IND_044_vwap_session_boundary` uses `anchor: "4h"`). Daily (`"D"`) and weekly (`"W"`) anchors are not affected.

**Scope of investigation**:
- Searched all `src/` for deprecated pandas frequency aliases (`'H'`, `'T'`, `'S'`, `'M'` as freq params) — **none found** in our code.
- Our `"D"`, `"W"`, `"M"` strings are Bybit API / timeframe identifiers, NOT pandas frequency aliases. They are never passed to `pd.date_range()`, `df.resample()`, etc.
- All `pd.date_range()` calls use `freq="1min"` or `freq="15min"` (lowercase, not deprecated).
- All `pd.Timedelta()` calls use `minutes=` kwarg (not frequency strings).
- Tested all 9 `pandas_ta` functions we call (`ema`, `sma`, `rsi`, `atr`, `macd`, `bbands`, `stoch`, `stochrsi`, `vwap`) — only `vwap` with hourly anchors triggers warnings.
- Our `IncrementalVWAP` (live mode) does NOT use pandas frequency aliases — it uses integer timestamp division for session boundary detection. **Not affected.**

**Fix options** (when pandas removes `'H'`):
1. Upgrade `pandas_ta` if they fix the `.upper()` call upstream.
2. If no upstream fix: monkey-patch or fork `pandas_ta.vwap()` to use lowercase anchor.

---

## Open Feature Work

### P1: Live Engine Rubric

- [ ] Define live parity rubric: backtest results as gold standard for live comparison
- [ ] Demo mode 24h validation
- [ ] Verify sub-loop activation in live mode

### P2: Live Trading Integration

- [ ] Test LiveIndicatorProvider with real WebSocket data
- [ ] Paper trading integration
- [ ] Complete live adapter stubs

### P4: CLI Redesign (Gates 4, 5, 8 open)

See `docs/CLI_REDESIGN.md` for full details.

- [ ] **Gate 4**: Unified `_place_order()` flow (type selector, side, symbol, amount, preview, confirm)
- [ ] **Gate 5**: Data menu top-level rewrite (delegate to sub-menu files already created)
- [ ] **Gate 8**: Final manual validation (offline menu, connect flow, quick-picks, cross-links)

### P5: Market Sentiment Tracker

Design document: `docs/brainstorm/MARKET_SENTIMENT_TRACKER.md`

- [ ] Phase 1: Price-derived sentiment (Tier 0) -- existing indicators + structures, zero new deps
- [ ] Phase 2: Bybit exchange sentiment (Tier 1) -- funding rate, OI, L/S ratio, liquidations, OBI
- [ ] Phase 3: External data (Tier 2) -- Fear & Greed Index, DeFiLlama stablecoin supply
- [ ] Phase 4: Historical sentiment for backtesting
- [ ] Phase 5: Statistical regime detection -- HMM-based (optional, requires hmmlearn)
- [ ] Future: Agent-based play selector that consumes sentiment tracker output

---

## Accepted Behavior

| ID | File | Note |
|----|------|------|
| GAP-BD2 | `trade_cli.py` | `os._exit(0)` is correct -- pybit WS threads are non-daemon, `sys.exit()` would hang |

## Platform Issues

- **DuckDB file locking on Windows** -- all scripts run sequentially, `run_full_suite.py` has retry logic (5 attempts, 3-15s backoff)

---

## Validation Commands

```bash
# Unified tiers (parallel staged execution, with timeouts + incremental reporting)
python trade_cli.py validate quick              # Pre-commit (~2min)
python trade_cli.py validate standard           # Pre-merge (~4min)
python trade_cli.py validate full               # Pre-release (~6min)
python trade_cli.py validate real               # Real-data verification (~2min)
python trade_cli.py validate module --module X --json  # Single module (PREFERRED for agents)
python trade_cli.py validate pre-live --play X  # Deployment gate
python trade_cli.py validate exchange           # Exchange integration (~30s)

# Options
python trade_cli.py validate full --workers 4         # Control parallelism
python trade_cli.py validate full --timeout 60        # Per-play timeout (default 120s)
python trade_cli.py validate full --gate-timeout 300  # Per-gate timeout (default 600s)

# Backtest / verification
python trade_cli.py backtest run --play X --sync      # Single backtest
python scripts/run_full_suite.py                      # 170-play synthetic suite
python scripts/verify_trade_math.py --play X          # Math verification
```
