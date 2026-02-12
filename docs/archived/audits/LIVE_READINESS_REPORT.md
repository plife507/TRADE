# TRADE Live Readiness Report

**Date:** 2026-02-07
**Branch:** feature/unified-engine
**Audit Scope:** 341 files, ~136,000 lines of Python
**Audit Team:** 6 specialist agents reviewing in parallel

> **Update 2026-02-08**: Backtest engine verification is now COMPLETE.
> 170/170 synthetic plays pass, 60/60 real-data Wyckoff verification plays pass
> with 23 math checks each. Equity curve post-close bug fixed ($7 gap to $0.00).
> The findings below regarding live-mode gaps remain valid and are tracked in
> `docs/TODO.md` under "Open Work > P2: Live Engine Rubric".

---

## Executive Summary

**Overall Readiness: ~70% (not 98%)**

The backtest pipeline is production-quality with correct math, comprehensive validation (140+ plays), and sound architecture. However, **live/demo trading is NOT ready** — the unified engine has fundamental gaps where live-mode code paths are stubbed or return None. Signal generation, multi-TF indexing, and the sub-loop evaluator are all non-functional in live mode.

The good news: the architecture is sound. These are implementation gaps, not design flaws. The adapter pattern is correct, the protocols are clean, and the backtest path proves the engine works. The live path needs the same capabilities wired in.

---

## Verdicts

### Order Mechanics (Backtest): PASS
- PnL math correct (gross and net)
- Fee deduction correct (entry + exit)
- TP/SL trigger logic correct with conservative tie-break
- Slippage direction correct for all 4 cases
- Limit order fill with price improvement correct
- Funding rate calculation Bybit-aligned
- Margin model and ledger invariants maintained
- 1 HIGH: Liquidation check uses stale ledger state (edge case)
- 1 MEDIUM: IOC/FOK TIF types broken (behave as GTC)

### Order Mechanics (Live): CONDITIONAL PASS
- Well-engineered safety foundations (strict mode/API mapping, idempotent recording)
- 7-layer risk checks before every order
- Leverage hard cap at 10x
- Demo/live key separation enforced
- 3 CRITICAL: `_recorded_orders` unbounded (OOM), SL cleanup regex misses SL orders (orphans), no panic check in execute()
- 4 HIGH: Stop orders bypass rate limiter/retry, ExchangeManager not singleton, hardcoded leverage=10 in margin mode, silent wait_for_fill timeout
- G0.1-G0.5 fixes verified (G0.3 partial — EM not actually singleton)

### Engine Parity: FAIL
- **Live snapshot building returns None** — rules never evaluate in live
- **TF index management skipped in live** — multi-TF broken
- **Sub-loop never activates in live** — 1m execution broken
- Sizing model is truly shared (PASS)
- State machine transitions correct (PASS)

### DSL & Rules Engine: PASS
- All 12 operators correct
- All 6 window operators correct
- Boolean short-circuit correct
- Feature resolution correct
- Warmup calculation correct
- 3 MEDIUM: Edge cases with low practical risk

### Indicators & Data Layer: PASS
- All 43 indicator formulas mathematically correct
- All 7 structure detectors correct
- Thread-safe realtime state management
- DuckDB locking correct
- 1 MEDIUM: Advisory file locking (verify no concurrent writers)

### Pipeline (Play → Backtest → Demo → Live): PARTIAL FAIL
- Backtest: FULLY WORKING
- Demo: BROKEN (asyncio double-run + missing snapshot)
- Live: BROKEN (confirm_live not forwarded + asyncio + missing snapshot)
- Shadow: PARTIALLY WORKING

---

## All Findings by Severity

### CRITICAL (Must fix — blocks all live/demo trading)

| # | Finding | File:Line | Agent |
|---|---------|-----------|-------|
| 1 | **Live snapshot returns None** — `_build_snapshot_view()` only works for BacktestDataProvider. Signal generation completely broken in live. | play_engine.py:797-875 | Engine Parity |
| 2 | **TF index management skipped** — `_update_high_tf_med_tf_indices()` has `if not self.is_backtest: return`. Multi-TF broken. | play_engine.py:640-641 | Engine Parity |
| 3 | **asyncio.run() called twice** — Two sequential `asyncio.run()` calls orphan runner tasks. Breaks both demo AND live. | subcommands.py:1714-1719 | Pipeline |
| 4 | **confirm_live not forwarded** — `PlayEngineFactory.create(play, mode=mode)` never passes `confirm_live=True`. Live always rejected. | subcommands.py:1638 | Pipeline |
| 5 | **LiveExchange.submit_order() creates duplicate Signal** — Information loss converting Order→Signal for OrderExecutor. | live.py:1285-1329 | Engine Parity |
| 6 | **LiveDataProvider.get_candle() extra tf_role param** — Protocol mismatch; engine never passes tf_role. | live.py:833 | Engine Parity |
| 7 | **_recorded_orders unbounded memory growth** — OOM crash risk over days/weeks of trading. | order_executor.py:121 | Live Orders |
| 8 | **SL cleanup regex misses SL orders** — All 3 cleanup paths only match `TP\d+_` pattern, missing `SL_` prefix. Orphaned SL orders trigger on next position. | exchange_orders_stop.py:364 / exchange_positions.py:381 / exchange_websocket.py:100 | Live Orders |
| 9 | **No panic check in OrderExecutor.execute()** — Orders can execute after panic triggered by another thread. | order_executor.py:237 | Live Orders |
| 10 | **play status/stop are stubs** — No way to monitor or stop running engine from CLI. | subcommands.py:1735,1742 | Pipeline |

### HIGH (Should fix before live)

| # | Finding | File:Line | Agent |
|---|---------|-----------|-------|
| 1 | **Liquidation check uses stale ledger state** — `update_for_mark_price` called AFTER liquidation check. Edge-case timing issue. | exchange.py:641-677 | Sim Orders |
| 2 | **PanicState not checked in live loop** — `_process_loop()` doesn't call `check_panic_and_halt()`. | live_runner.py:462 | Pipeline |
| 3 | **SafetyChecks not integrated with LiveRunner** — `SafetyChecks.run_all_checks()` exists but never called. | live_runner.py | Pipeline |
| 4 | **Live snapshot view returns None** — `_build_snapshot_view()` returns None for non-backtest (duplicate of Critical #1). | play_engine.py:873-875 | Pipeline |
| 5 | **Max drawdown halt not in LiveRunner** — Exists in BacktestRunner but not live. | backtest_runner.py:405 | Pipeline |
| 6 | **No SIGTERM handler** — Relies on KeyboardInterrupt only. | subcommands.py | Pipeline |
| 7 | **EngineManager bypassed** — `play run` creates engine directly, no instance limits. | subcommands.py:1636-1649 | Pipeline |
| 8 | **Realized PnL differs** — Backtest: cash-based. Live: fill-based (no fees). | backtest.py:441 / live.py:1438 | Engine Parity |
| 9 | **Position recovery incomplete** — restore_state() restores counters only, not position/structures/TF indices. | play_engine.py:588-604 | Engine Parity |
| 10 | **Stop orders bypass rate limiter AND retry** — Raw pybit session call, no retry on transient failures. SL/TP could silently fail. | exchange_orders_stop.py:41,93 | Live Orders |
| 11 | **ExchangeManager not a singleton** — 4 instantiation points, inconsistent position tracking. | exchange_manager.py | Live Orders |
| 12 | **set_margin_mode() hardcodes leverage=10** — May override user's intended leverage. | exchange_positions.py:264-269 | Live Orders |
| 13 | **wait_for_fill() silently returns None** — No warning, no REST fallback. Untracked positions possible. | order_executor.py:533 | Live Orders |

### MEDIUM (Fix before production)

| # | Finding | File:Line | Agent |
|---|---------|-----------|-------|
| 1 | Pending close before TP/SL — signal close overrides TP/SL on same bar | exchange.py:730-743 | Sim Orders |
| 2 | IOC/FOK limit orders broken — `is_first_bar` never true, behave as GTC | exchange.py:878-881 | Sim Orders |
| 3 | Slippage on TP/SL exits — correct but surprising (should document) | execution_model.py:551-556 | Sim Orders |
| 4 | DuckDB advisory file lock — verify no concurrent writers in live | historical_data_store.py:412-519 | Indicators |
| 5 | AnyExpr failure uses ReasonCode.OK — semantically incorrect | boolean_ops.py:60 | DSL |
| 6 | Legacy evaluate_condition missing between/near/in operators | eval.py:585 | DSL |
| 7 | _is_enum_literal may misclassify feature IDs | dsl_parser.py:385-426 | DSL |
| 8 | Factory config extraction duplicated (3 paths) | factory.py | Engine Parity |
| 9 | LiveExchange.submit_close() PnL wrong units | live.py:1487-1549 | Engine Parity |
| 10 | PLAYS_DIR points to empty directory | play.py:916 | Pipeline |

### LOW (Quality improvements)

| # | Finding | File:Line | Agent |
|---|---------|-----------|-------|
| 1 | Partial closes don't create Trade records | exchange.py:1080-1164 | Sim Orders |
| 2 | Impact model disabled (no volume-adaptive slippage) | impact_model.py:22 | Sim Orders |
| 3 | Simplified liquidation formula differs between components | liquidation_model.py:150-197 | Sim Orders |
| 4 | ALMA is O(n) not O(1) — mathematically unavoidable | adaptive.py | Indicators |
| 5 | Swing pivot detection O(window_size) — documented, negligible | swing.py:607-649 | Indicators |
| 6 | SetupRef not shifted in window operators | shift_ops.py:128-132 | DSL |
| 7 | Warmup max_window over-estimated per feature | dsl_warmup.py:296 | DSL |
| 8 | Unrecognized dict keys silently pass through | play.py:332 | DSL |

---

## What's Solid (No Action Needed)

These components are production-quality and verified correct:

- **43 Indicators**: All formulas match pandas_ta reference, O(1) incremental, correct warmup
- **7 Structure Detectors**: Swing, zone, trend, fibonacci, derived_zone, rolling_window, market_structure — all state machines verified
- **DSL Evaluation Engine**: Type-safe, fail-loud, deterministic, no lookahead bugs
- **Simulated Exchange**: Core order lifecycle, PnL, fees, margin model, funding rates
- **Sizing Model**: Truly shared between backtest/live, mode-agnostic
- **Data Layer**: Thread-safe realtime state, DuckDB with proper locking, staleness detection
- **140+ Validation Plays**: 18+ tiers of comprehensive testing all passing
- **Safety Infrastructure**: PanicState, panic_close_all, position reconciliation (exists but not wired)

---

## Path to Live Trading

### Phase 1: Fix Critical Blockers (est. effort: medium)

These must ALL be fixed before demo or live trading works:

1. **Implement live snapshot building** (`play_engine.py:797-875`)
   - Build `RuntimeSnapshotView` from `LiveDataProvider` indicator/structure caches
   - This is the single biggest blocker

2. **Implement live TF index management** (`play_engine.py:640-641`)
   - Remove `if not self.is_backtest: return` guard
   - Map live candle timestamps to TF indices

3. **Fix asyncio double-run** (`subcommands.py:1714-1719`)
   - Combine into single `asyncio.run(main())` with start + wait

4. **Forward confirm_live** (`subcommands.py:1638`)
   - Pass `confirm_live=args.confirm` to `PlayEngineFactory.create()`

5. **Bound _recorded_orders** (`order_executor.py:121`)
   - Replace `set` with bounded LRU or periodic pruning

6. **Fix SL cleanup regex** (`exchange_orders_stop.py:364`, `exchange_positions.py:381`, `exchange_websocket.py:100`)
   - Change pattern to match both `SL_` and `TP\d+_` prefixes — orphaned SL orders trigger on next position

7. **Add panic check to OrderExecutor.execute()** (`order_executor.py:237`)
   - Check `is_panic_triggered()` before submitting any order

8. **Fix protocol mismatch** (`live.py:833`)
   - Align `get_candle()`, `get_indicator()`, `get_structure()` signatures

9. **Fix Order→Signal conversion** (`live.py:1285-1329`)
   - Ensure no information loss

### Phase 2: Wire Safety Systems (est. effort: small-medium)

10. Add `check_panic_and_halt()` to LiveRunner process loop
11. Integrate `SafetyChecks.run_all_checks()` before order execution
12. Add max drawdown halt to LiveRunner (port from BacktestRunner)
13. Add SIGTERM handler for graceful shutdown
14. Route `play run` through EngineManager for instance limits
15. Route stop orders through BybitClient.create_order() (retry + rate limit)
16. Enforce ExchangeManager singleton (or cached factory)
17. Parameterize leverage in set_margin_mode()
18. Add WARNING log + REST fallback on wait_for_fill timeout
19. Consolidate dual daily loss trackers (risk_manager + safety)
20. Thread-safe Config singleton

### Phase 3: Implement Play Status/Stop (est. effort: small)

21. Implement `play status` CLI command
22. Implement `play stop` CLI command

### Phase 4: Validate Demo (est. effort: small)

15. Run demo mode for 24+ hours with a production play
16. Verify signals fire, orders execute on Bybit demo API
17. Compare demo results with backtest for same period
18. Test panic button, Ctrl+C, crash recovery

### Phase 5: Go Live

19. Run full pre-flight checklist (below)
20. Start with smallest possible position size
21. Monitor first trades closely via Bybit web UI

---

## Pre-Flight Checklist (Before First Live Trade)

### Infrastructure Fixes
- [ ] All 7 Critical blockers fixed
- [ ] All 4 Safety system items wired
- [ ] play status/stop implemented
- [ ] Full smoke test passes: `python trade_cli.py --smoke full`

### Demo Validation
- [ ] Demo mode runs 24+ hours without crash
- [ ] Signals generate and orders execute on Bybit demo
- [ ] Position reconciliation verified (kill + restart)
- [ ] Panic button tested (CLI menu option 10)
- [ ] Ctrl+C graceful shutdown tested

### Configuration
- [ ] `BYBIT_USE_DEMO=false` set
- [ ] `TRADING_MODE=live` set
- [ ] `BYBIT_LIVE_API_KEY` / `BYBIT_LIVE_API_SECRET` set
- [ ] API key permissions: trade + read only (NOT withdraw)
- [ ] Risk limits configured in play (max_leverage, max_drawdown_pct)
- [ ] Position size limits set on Bybit directly (belt + suspenders)

### Monitoring
- [ ] Log monitoring active
- [ ] Bybit web UI open for manual intervention
- [ ] Know how to trigger `panic_close_all_tool()` from CLI
- [ ] Start with minimal position size (e.g., $50-100)

---

## Audit Details

Full audit reports available at:
- `scratchpad/audit_sim_orders.md` — Backtest order mechanics (14 files)
- `scratchpad/audit_live_orders.md` — Live order mechanics (20 files, 7500 lines, 17 findings)
- `scratchpad/audit_engine_parity.md` — Engine parity (14 files)
- `scratchpad/audit_dsl_rules.md` — DSL & rules engine (35+ files)
- `scratchpad/audit_indicators_data.md` — Indicators & data layer (30+ files)
- `scratchpad/audit_pipeline.md` — End-to-end pipeline trace
