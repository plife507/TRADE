# TRADE TODO

Single source of truth for all open work, bugs, and task progress.

---

## Completed Work (archived)

| Item | Status | Date | Reference |
|------|--------|------|-----------|
| Liquidation Parity (Bybit) | DONE | 2026-02 | Liquidation parity review complete |
| Fast Parallel Validation | DONE | 2026-02 | Phases 1-7 complete |
| Health Audit Fixes | DONE | 2026-02-18 | near_pct fixed, legacy cleanup done |
| Backtest Safety Gaps 3-6 | DONE | 2026-02 | GAP-3/4/5/6 all FIXED |
| Full Codebase Review | DONE | 2026-02-17 | `docs/architecture/` (10 files, 253 KB, 120 findings) |
| Codebase Review Gate 1: DSL Critical | DONE | 2026-02-17 | 5 CRIT fixes (setup cache, operators, else_emit, auto-conversion, risk policy) |
| Codebase Review Gate 2: Sim Parity | DONE | 2026-02-17 | 3 HIGH fixes (liquidation fee, bankruptcy price, close reasons) |
| Codebase Review Gate 3: Warmup | DONE | 2026-02-17 | 2 items resolved (ENG-001, BT-007). 2 deferred (see below) |
| Codebase Review Gate 4: Live Safety | DONE | 2026-02-17 | 12 fixes (close ordering, WS reconnect, stale data, pre-live gates) |
| Codebase Review Gate 5: DSL & Engine MED | DONE | 2026-02-17 | 17 fixes + pyright 0 + validate standard 12/12 |
| Codebase Review Gate 6: Sim & Backtest MED | DONE | 2026-02-17 | 13 fixes + validate standard 12/12. 2 future features deferred |
| Codebase Review Gate 7: Data/CLI/Forge MED | DONE | 2026-02-17 | 18 fixes. 1 deferred (DATA-011) |
| Codebase Review Gate 8: LOW Cleanup | DONE | 2026-02-17 | 12 fixed, 18 evaluated OK, 8 not-a-bug. 1 deferred (DATA-017) |
| CLI & Tools Module Splitting (P4.5) | DONE | 2026-02-19 | Phases 1-5 complete. 5 gates passed. Net -113 lines deduplication |
| Debug & Logging Redesign (P6) | DONE | 2026-02-19 | 8 phases: log plumbing, verbosity flags, signal trace, metrics surfacing, JSON consistency, backtest journal |
| Live Dashboard Redesign (P7) | DONE | 2026-02-19 | Modular dashboard package, Rich rendering, tiered refresh, signal proximity |
| Structure Detection Audit | DONE | 2026-02-20 | Audit of swing/trend/MS on real BTC data. See `docs/STRUCTURE_DETECTION_AUDIT.md` |
| Dead Code Audit | DONE | 2026-02-20 | 44 findings, ~800 lines dead code in live path. See `docs/DEAD_CODE_AUDIT.md` |

Full gate details with per-item descriptions: `memory/completed_work.md`

---

## Deferred Items

Items evaluated during codebase review, confirmed low-risk, deferred to appropriate milestones.

### Pre-Deployment (must fix before live trading)

- [ ] **GAP-2** No REST API fallback for warmup data. `_load_tf_bars()` tries buffer -> DuckDB -> fails. Needed for cold-start live scenarios.
- [ ] **DATA-011** `_handle_stale_connection()` does REST refresh but does not force pybit reconnect. `GlobalRiskView._check_ws_health()` blocks trading after 30s unhealthy. Adding active reconnect risky without integration testing.
- [ ] **DATA-017** `panic_close_all()` cancel-before-close ordering is a defensible tradeoff. Reversing to close-first needs integration test to confirm exchange rejects TP-after-close on reduce-only positions.
- [ ] **GATE**: `python trade_cli.py validate pre-live --play X` passes

### Optimization (before sustained live sessions)

- [ ] **ENG-BUG-015** `np.append` O(n) on 500-element arrays, ~3-10 MB/hour GC pressure. Correct behavior, optimize before sustained live sessions.

### Future Features (no correctness impact)

- [ ] **IND-006** Validation that warmup estimates match actual `is_ready()` thresholds. Not a bug (indicators output NaN until ready, which propagates safely).
- [ ] **SIM-MED-3** `ExchangeMetrics` class (217 lines) fully implemented but zero callers. Needs result schema wiring to surface metrics.
- [ ] **SIM-MED-4** `Constraints` class (193 lines) fully implemented but not wired. Needs per-symbol constraint config from exchange instrument info.

---

## Known Issues (non-blocking)

### pandas_ta `'H'` Deprecation Warning

**Status**: Cosmetic warning, no impact on correctness. Will become error in future pandas release.

**Root cause**: `pandas_ta.vwap()` calls `anchor.upper()` internally, passing uppercase `'H'` to `index.to_period()`. Pandas deprecated uppercase `'H'` in favor of lowercase `'h'`.

**Affected**: Only VWAP with hourly anchors (e.g., `anchor: "4h"`). Daily/weekly unaffected. Our `IncrementalVWAP` (live mode) unaffected.

**Fix options** (when pandas removes `'H'`):
1. Upgrade `pandas_ta` if they fix the `.upper()` call upstream.
2. If no upstream fix: monkey-patch or fork `pandas_ta.vwap()` to use lowercase anchor.

---

## Open Feature Work

### P9: Dead Code Cleanup

See `docs/DEAD_CODE_AUDIT.md` for full findings (44 items, ~800 lines).

#### Phase 1: Delete Obviously Dead Code — DONE (2026-02-20)
- [x] Remove stub methods, dead attributes, SubscriptionConfig factories
- [x] Remove MarketData convenience methods (zero callers) — 10 methods, -205 lines
- [x] Remove RealtimeState unused callbacks and granular clear methods — 16 methods, -127 lines
- [x] Remove PositionManager `set_prefer_websocket()` — -5 lines
- [x] Remove ExchangeManager 4 dead methods + `_trading_mode` attr — -22 lines
- [x] Remove Application `get_websocket_health()`, `on_shutdown()`, `_lock` — -35 lines
- [x] Remove RiskManager `start_websocket_if_needed()` — -31 lines
- [x] Remove `ConnectionStatus.last_message_at` — -5 lines
- [x] Remove SubscriptionConfig factories (3) — -47 lines
- [x] **GATE**: `python trade_cli.py validate quick` passes (5/5 gates)
- **Total: 471 lines deleted across 8 files**

#### Phase 2: P2 Candidates — KEPT (decision: keep for live trading)
- [x] RiskManager RR utilities (`calculate_trade_levels`, SL/TP, `get_max_position_size`) — **KEEP for P2**
- [x] OrderExecutor `wait_for_fill()`, `execute_with_leverage()`, pending order API — **KEEP for P2**
- [x] ExchangeManager `reconcile_orphaned_orders()`, `open_position_with_rr()` — **KEEP for P2**
- [x] PositionManager `get_performance_summary()`, `get_trade_history()` — **KEEP for P2**
- [x] RiskManager `get_global_risk_snapshot()`, `get_global_risk_summary()` — **KEEP for P2**

### P6: Debug & Logging Redesign — DONE (2026-02-19)

All 8 phases complete. `validate quick` passes, all flags (`-q`, `-v`, `--debug`) work.

#### Phase 1: Fix Broken Log Level Plumbing — DONE
- [x] `src/utils/logger.py`: `_resolve_log_level()` reads `TRADE_LOG_LEVEL` > `LOG_LEVEL` > `"INFO"`
- [x] `src/utils/logger.py`: `suppress_for_validation()` sets `trade.*` to WARNING (no `logging.disable()`)
- [x] `src/utils/logger.py`: `get_module_logger(module_name)` maps `src.X` → `trade.X`
- [x] `src/config/config.py`: Reads `TRADE_LOG_LEVEL` env var
- [x] `src/cli/validate.py`: 5x `logging.disable(INFO)` → `suppress_for_validation()`

#### Phase 2: Verbosity Levels — DONE
- [x] `-q`/`--quiet`, `-v`/`--verbose` (mutually exclusive with `--debug`)
- [x] `verbose_log()`, `is_verbose_enabled()`, `enable_verbose()` in `debug.py`
- [x] `trade_cli.py`: `-q` → suppress, `-v` → verbose, `--debug` → both

#### Phase 3: Fix Module-Level Logger Leakage — DONE
- [x] 12 orphan `logging.getLogger(__name__)` → `get_module_logger(__name__)`

#### Phase 4: Signal Trace at Verbose Level — DONE
- [x] `EvaluationTrace`, `BlockTrace`, `CaseTrace` dataclasses in `rules/types.py`
- [x] `execute_with_trace()` in `StrategyBlocksExecutor`
- [x] `evaluate_with_trace()` in `PlaySignalEvaluator`
- [x] Engine wired: verbose → trace path, normal → zero overhead
- [x] Subloop verbose logging (first bars only)

#### Phase 5: Metric Surfacing — DONE
- [x] 21 new fields on `ResultsSummary` (benchmark, tail risk, leverage, MAE/MFE, friction, margin, funding)
- [x] Wired in `compute_results_summary()` via `getattr()` for SimpleNamespace compat
- [x] `print_summary()` expanded with conditional sections
- [x] `to_dict()` includes all new fields

#### Phase 6: JSON Output Consistency — DONE
- [x] `debug determinism` and `debug metrics` JSON wrapped in `{"status","message","data"}` envelope

#### Phase 7: Cross-References and Backtest Journal — DONE
- [x] `BacktestJournal` class in `journal.py` writes `events.jsonl` to artifact folder
- [x] `_write_backtest_journal()` in runner records fill+close per trade
- [x] Artifact path logged at INFO after writing

#### Phase 8: Indicator/Structure Diagnostic Logging — DONE
- [x] NaN-past-warmup warning in `indicators.py` (verbose only)
- [x] Structure version-change detection in `state.py` (verbose only)

### P7: Live Dashboard Redesign — DONE

Redesigned the demo/live trading dashboard from monolithic `src/cli/live_dashboard.py` (1,388 lines) into modular `src/cli/dashboard/` package with Rich Group/Panel/Table rendering, tiered refresh, signal proximity, sparklines, and graceful lifecycle.

#### Phase 1: Module Split — DONE
- [x] Split into `src/cli/dashboard/` package (13 modules)
- [x] `__init__.py` — re-exports `run_dashboard`, `DashboardState`, `OrderTracker`, etc.
- [x] `state.py` — `DashboardState`, `refresh_ticker()`, `refresh_account()`, `refresh_engine_data()`
- [x] `widgets.py` — formatting helpers, status badge, tab bar, sparkline
- [x] `tabs/` — 6 tab builders in separate files (overview, indicators, structures, log, play_yaml, orders)
- [x] `input.py` — `TabState`, key listener with quit confirmation, `f` filter key
- [x] `runner.py` — entry point with Group/Panel composition
- [x] `log_handler.py` — `DashboardLogHandler`
- [x] `order_tracker.py` — `OrderEvent`, `OrderTracker` with W/L stats
- [x] `play_meta.py` — `populate_play_meta()`
- [x] `signal_proximity.py` — condition evaluator reusing P6 trace system
- [x] Updated callers: `play.py`, `plays_menu.py`
- [x] Deleted `src/cli/live_dashboard.py`
- [x] **GATE**: `validate quick` passes, zero `live_dashboard` imports remain

#### Phase 2: Rich Group Rendering — DONE
- [x] `_build()` returns `Group` instead of `Text`
- [x] Status header in `Panel(border_style="cyan")`
- [x] Tab content in `Panel(border_style="dim")`
- [x] Indicators/structures/orders tabs use `rich.table.Table` with auto-sizing

#### Phase 3: Tiered Refresh Intervals — DONE
- [x] Ticker: 250ms cadence (`refresh_ticker()`)
- [x] Account/runner stats: 2s cadence (`refresh_account()`)
- [x] Indicators/structures: on bar close (bars_processed change)
- [x] 50ms base poller loop
- [x] Staleness indicator on indicators + structures tabs
- [x] Warmup ETA: bars_remaining * tf_seconds

#### Phase 4: Enhanced Tabs — DONE
- [x] Sparklines (Unicode `▁▂▃▅▇`) from indicator history ring buffer (depth=20)
- [x] Log severity filter (`f` key cycles all/warn+/error)
- [x] Session P&L summary on overview tab
- [x] W/L stats method on OrderTracker

#### Phase 5: Signal Proximity Display — DONE
- [x] `signal_proximity.py` with `evaluate_proximity()` using `evaluate_with_trace()`
- [x] `ConditionStatus`, `BlockStatus`, `SignalProximity` dataclasses
- [x] Overview tab renders condition checklist (green=pass, red=fail, % ratio)
- [x] Evaluates at account refresh cadence (2s)

#### Phase 6: Graceful Enter/Exit — DONE
- [x] Quit with position: first `q` shows yellow warning, second `q` confirms
- [x] Shutdown messaging: "Shutting down engine..." on exit
- [x] Pause file cleanup in `finally` block
- [x] R-multiple display (`(+1.3R)`) when SL is set
- [x] Time-in-trade display since position opened
- [x] `position_opened_at` and `risk_per_trade` tracked in state

### P8: Structure Detection Fixes

See `docs/STRUCTURE_DETECTION_AUDIT.md` for full audit report.
Audit script: `scripts/analysis/structure_audit.py`

#### Phase 1: Fix Config Defaults
- [ ] Change `confirmation_close` default to `True` in `market_structure.py` (or document that ICT/SMC plays MUST set it)
- [ ] Add recommended defaults to play templates: `min_atr_move: 0.5` or `strict_alternation: true`
- [ ] Document trend/MS timing mismatch in `docs/PLAY_DSL_REFERENCE.md` — plays must not expect both to agree on same bar
- [ ] **GATE**: `python trade_cli.py validate quick` passes

#### Phase 2: Trend Detector Review
- [ ] Investigate why `strength=2` never fires on real BTC data (4h/12h/D, 6 months)
- [ ] Consider reducing consecutive-pair requirement or increasing wave history size
- [ ] Re-run `scripts/analysis/structure_audit.py` to verify improvement
- [ ] **GATE**: Trend reaches `strength=2` at least once on 6-month BTC 4h data

#### Phase 3: Trend/MS Synchronization (Design Decision)
- [ ] Decide approach: (a) accept mismatch as intentional, (b) make MS depend on trend, (c) add pending CHoCH, (d) speed up trend, (e) slow down MS
- [ ] Implement chosen approach
- [ ] Re-run audit — trend/MS agreement should exceed 50%
- [ ] **GATE**: `python trade_cli.py validate standard` passes

#### Phase 4: CHoCH Correctness
- [ ] Track which swing produced the last BOS (not just most recent swing)
- [ ] CHoCH only valid when breaking the BOS-producing swing level
- [ ] **GATE**: `python trade_cli.py validate quick` passes

---

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
