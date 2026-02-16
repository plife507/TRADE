# TRADE TODO

Active work tracking for the TRADE trading bot. **This is the single source of truth for all open work.**

---

## Current Phase: Live Trading Ready

Backtest engine fully verified 2026-02-08. **170/170 synthetic plays pass**, **60/60 real-data Wyckoff verification plays pass**. Live readiness gates G14-G17 completed 2026-02-10: crash fixes, MVP live CLI, production hardening, and operational excellence. Full CLI tooling for live trading: `play run/status/stop/watch/logs/pause/resume`, `account balance/exposure`, `position list/close`, `panic`. See `docs/archived/2026-02/plans/LIVE_READINESS_GLOBAL.md` for details.

---

## Completed Gates Summary

| Gate | Items | Status | Date |
|------|-------|--------|------|
| G0: Critical Blockers | 5 fixes (deadlock, risk mgr, exchange mgr, position sync, atomic SL) | COMPLETE | 2026-01-27 |
| G1: Dead Code | 19 functions removed | COMPLETE | 2026-01-27 |
| G2: Duplicates | 5 consolidations | COMPLETE | 2026-01-27 |
| G3: Legacy Shims | 10 shims removed | COMPLETE | 2026-01-27 |
| G4: Refactoring | 4 large functions extracted | COMPLETE | 2026-01-27 |
| G5: Infrastructure | 8 improvements (memory, WS, reconciliation, state machines) | COMPLETE | 2026-01-28 |
| G6: Code Review | 15+ items (fund safety, thread safety, dead code, best practices) | COMPLETE | 2026-01-28 |
| G7: Stress Test | 99 plays across 6 phases, 0 failures | COMPLETE | 2026-01-28 |
| G8: DSL 100% Coverage | 41 plays, 43/43 indicators, 18/18 structures, 4 symbols | COMPLETE | 2026-01-28 |
| G9: QA Swarm Audit | 6 bugs (4 fixed, 1 false positive, 1 verified safe) | COMPLETE | 2026-01-29 |
| G10: Live/Backtest Parity | 10 files reviewed, 6 warmup fixes, 4 stress tests | COMPLETE | 2026-02-05 |
| G11: 170-Play Synthetic Audit | 170/170 pass, 0 fail, 0 zero-trade | COMPLETE | 2026-02-08 |
| G12: 60-Play Real-Data Verification | 60/60 pass, 60/60 math verified (23 checks each) | COMPLETE | 2026-02-08 |
| G13: Unified Validation System | 5 core plays, 4 tiers, dead code removed | COMPLETE | 2026-02-10 |
| G14: Crash Fixes & Safety | 5 fixes (query_ohlcv, end_time, fat finger, DCP, daily loss seed) | COMPLETE | 2026-02-10 |
| G15: MVP Live CLI | 7 items (pre-live gate, banner, status, stop, watch, account/position, signals) | COMPLETE | 2026-02-10 |
| G16: Production Hardening | 4 items (drawdown breaker, state serialization, ring buffer, cross-process) | COMPLETE | 2026-02-10 |
| G17: Operational Excellence | 5 items (journal, logs, pause/resume, notifications, unified backtest) | COMPLETE | 2026-02-10 |
| Pyright Zero + Import Audit | 298 type errors fixed, 13 import warnings fixed, pyrightconfig.json added | COMPLETE | 2026-02-12 |
| Silent Exception Audit | 7 `except Exception: pass` handlers replaced with logging | COMPLETE | 2026-02-12 |
| Demo/Live Production Fixes | 28 bugs fixed across 6 gates (engine, warmup, signal, runner, WS, lifecycle) | COMPLETE | 2026-02-12 |
| Docs & Memory Cleanup | 8 docs + 5 plans archived, MEMORY.md trimmed, TODO condensed | COMPLETE | 2026-02-14 |
| Hash Tracing Audit | 8 fixes: unified hashing, dead code, naming, console output, live hash | COMPLETE | 2026-02-15 |
| Audit: Math Correctness | 6 areas verified | COMPLETE | 2026-01-27 |
| Audit: Warmup Logic | 50 items verified | COMPLETE | 2026-01-27 |
| Audit: State Management | 4 areas verified | COMPLETE | 2026-01-27 |
| Artifact Regeneration | 170/170 synthetic re-run post equity-curve fix, artifacts clean | COMPLETE | 2026-02-15 |
| Price Feature Plays | 6 plays: last_price, mark_price, crossover, arithmetic, short, combined | COMPLETE | 2026-02-15 |

---

## Open Work

### P0: Live Engine Rubric

28 demo/live bugs were fixed (2026-02-12). Remaining items:
- [ ] Define live parity rubric: backtest results as gold standard for live comparison
- [ ] Demo mode 24h validation
- [ ] Verify sub-loop activation in live mode

### P1: Live Trading Integration

- [ ] Test LiveIndicatorProvider with real WebSocket data
- [ ] Paper trading integration
- [ ] Complete live adapter stubs

### P2: Incremental Indicator Expansion

All 44 O(1) incremental indicators implemented. Expand coverage testing and edge-case validation.

### P3: Market Sentiment Tracker

Design document: `docs/brainstorm/MARKET_SENTIMENT_TRACKER.md`

- [ ] Phase 1: Price-derived sentiment (Tier 0) -- use existing indicators + structures for regime classification + composite score (zero new dependencies)
- [ ] Phase 2: Bybit exchange sentiment (Tier 1) -- funding rate, OI, L/S ratio, liquidations, OBI via WS/REST
- [ ] Phase 3: External data (Tier 2) -- Fear & Greed Index, DeFiLlama stablecoin supply
- [ ] Phase 4: Historical sentiment for backtesting -- compute + store sentiment during backtest runs
- [ ] Phase 5: Statistical regime detection -- HMM-based classifier (optional, requires hmmlearn)
- [ ] Future: Agent-based play selector that consumes sentiment tracker output

### P4: DSL Enhancement (Complete)

- [x] Build DSL validator (`src/backtest/rules/dsl_validator.py` -- validates all FeatureRef/SetupRef at parse time)
- [x] Implement typed block layer (fail-loud in `dsl_nodes/utils.py` and `play.py`)
- [x] Add block composition (`setups:` YAML section with nested refs + circular detection)

---

## Known Gaps

- **DuckDB file locking on Windows** -- platform limitation; all scripts run sequentially, `run_full_suite.py` has retry logic (5 attempts, 3-15s backoff)

---

## Validation After Each Gate

```bash
# Unified validation (preferred)
python trade_cli.py validate quick              # Pre-commit (~10s)
python trade_cli.py validate standard           # Pre-merge (~2min)
python trade_cli.py validate full               # Pre-release (~10min)
python trade_cli.py validate pre-live --play X  # Deployment gate
python trade_cli.py validate exchange            # Exchange integration (~30s)

# Individual tools
python trade_cli.py backtest run --play X --fix-gaps  # Single backtest
python scripts/run_full_suite.py                      # 170-play synthetic suite
python scripts/run_real_verification.py               # 60-play real verification
python scripts/verify_trade_math.py --play X          # Math verification for a play
```

---

## Completed Work (2026-02-15)

- [x] 170/170 synthetic suite re-run with post-equity-curve-fix engine -- artifacts regenerated, SL_TP stale artifact issue resolved
- [x] 6 price feature plays (PF_001-006): `last_price` gt/cross/short/arithmetic, `mark_price` near_pct, combined usage -- closes 1m signal pipeline gap
- [x] Known Gaps cleaned: last_price, mark_price, SL_TP stale artifacts all resolved

---

## Completed Work (2026-02-14)

- [x] Docs cleanup: archived 8 completed reports/plans + 5 gate plans to `docs/archived/2026-02/`
- [x] Removed empty `docs/plans/` directory
- [x] MEMORY.md trimmed from ~200 to 107 lines (collapsed old bug entries, removed duplication)
- [x] TODO.md condensed (collapsed old completed work sections, added missing gate table rows)

---

## Completed Work (2026-02-12/13)

- [x] Pyright zero: 298 type errors resolved across 75+ files, 13 import warnings fixed, `pyrightconfig.json` added
- [x] Silent exception audit: 7 `except Exception: pass` handlers replaced with logging in engine
- [x] Demo/Live production fixes: 28 bugs fixed across 6 gates. See `docs/archived/2026-02/DEMO_PRODUCTION_PLAN.md`
- [x] `eval_not()` fix in `boolean_ops.py`: NOT operator now correctly inverts all non-error results

---

## Completed Work (2026-02-10)

- [x] G13: Unified Validation System -- 5 core plays, 4 tiers (`quick`/`standard`/`full`/`pre-live`), dead code removed
- [x] G14-G17: Live readiness gates (crash fixes, MVP live CLI, production hardening, operational excellence)
- [x] G5 Structure Parity: vectorized reference fixes for market_structure and derived_zone (9/9 detectors PASS)

---

## Completed Work (2026-02-07/08)

- [x] DSL parser fixes: dotted refs, bracket syntax, arithmetic dict format, NOT operator unwrapping
- [x] 170-play synthetic audit: 170/170 pass, all 44 indicators, 7 structures, all DSL operators
- [x] 60-play real-data verification: 60/60 pass, 60/60 math verified (23 checks each)
- [x] Equity curve post-close fix: final equity point appended AFTER `_close_remaining_position()`

---

## Completed Work (2026-02-05)

- [x] G10: Live/Backtest Parity -- 10 files reviewed, 6 warmup fixes, 4 stress tests

---

## Completed Work (2026-01)

- [x] G0-G6: Full codebase audit (307 files, 126K LOC), 5 critical blockers, 34 cleanups, 8 infrastructure improvements
- [x] G7-G8: 99 stress test plays, 41 DSL coverage plays, 43/43 indicators, 18/18 structures
- [x] G9: QA Swarm (8 agents, 2029 files, 6 bugs found and resolved)
- [x] Unified indicator system, validation suite, engine migration (Jan 21-25)
