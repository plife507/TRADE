# Active Work Tracking

**Date:** 2026-01-15
**Branch:** feature/unified-engine
**Status:** Unified Engine Complete - Legacy Code Removed

---

## Completed This Session

### Schema Rename [COMPLETE]

Renamed timeframe role keys in tf_mapping for clarity:

| Old Key | New Key | Meaning |
|---------|---------|---------|
| `htf` | `high_tf` | high_tf - Higher Timeframe (6h, 12h, D) |
| `mtf` | `med_tf` | med_tf - Medium Timeframe (30m, 1h, 2h, 4h) |
| `ltf` | `low_tf` | low_tf - Low Timeframe (1m, 3m, 5m, 15m) |

**Files Updated:**
- [x] `src/backtest/play/play.py` - Play YAML schema
- [x] `src/backtest/runtime_config.py` - RuntimeConfig fields
- [x] `src/backtest/rules/compile.py` - DSL compile valid_roles
- [x] `src/backtest/runtime/feed_store.py` - FeedStore role access
- [x] `src/config/constants.py` - TF_ROLE_GROUPS mapping

---

### BUG-001: ltf_frame Reference [FIXED]

- **Location:** `src/backtest/engine.py:649`
- **Issue:** Missed rename from `ltf_frame` to `low_tf_frame`
- **Fix:** Updated variable name to match schema rename

---

### BUG-002: data_env Plumbing [FIXED]

- **Issue:** CLI `--data-env` flag not flowing through to engine
- **Root cause:** Missing plumbing through RunnerConfig -> create_engine_from_play -> SystemConfig.DataBuildConfig

**Fix path:**
- [x] CLI `--data-env` argument captured
- [x] Passed to `RunnerConfig.data_env`
- [x] Flowed to `create_engine_from_play()`
- [x] Set in `SystemConfig.DataBuildConfig.data_env`
- [x] Used by FeedStore data loading

---

### BUG-003: Time in Market (bars_in_position) [FIXED]

- **Issue:** Time in Market metrics showing 0.0 in results
- **Root cause:** `bars_in_position` not being incremented in BacktestRunner
- **Location:** `src/engine/runners/backtest_runner.py`
- **Fix:** Added position duration tracking, now shows correct bars-in-position values

---

## Unified Engine Status

### Gates Completed

| Gate | Description | Status |
|------|-------------|--------|
| GATE 0 | Baseline validation | PASSED |
| GATE 1 | Extract Signal Evaluation | COMPLETED |
| GATE 2 | Extract Multi-TF Logic | COMPLETED |
| GATE 3 | Unify Position Sizing | COMPLETED |
| GATE 4 | Wire BacktestRunner | COMPLETED |
| GATE 5 | Delete Duplicate Code | COMPLETED |
| GATE 6 | Full Stress Test Validation | COMPLETED |

### Validation Status

```
audit-toolkit:     42/42 indicators PASS
normalize-batch:   9/9 plays PASS
smoke:             PASS
```

---

## Pending Work (P0 - Critical)

None currently.

---

## Pending Work (P1 - High)

### Live Trading Integration

- [ ] Wire LiveDataProvider to WebSocket feed
- [ ] Wire LiveExchange to Bybit API
- [ ] Implement LiveRunner event loop
- [ ] Add warm-up data loading from market_data_live.duckdb

### Demo Trading Integration

- [ ] Wire DemoDataProvider to demo WebSocket
- [ ] Wire DemoExchange to demo API
- [ ] Test end-to-end paper trading flow

---

## Pending Work (P2 - Medium)

### Documentation

- [x] Update CLAUDE.md with tf_mapping schema
- [x] Update SESSION_HANDOFF.md
- [x] Create UNIFIED_ENGINE_SPEC.md
- [ ] Update PLAY_DSL_COOKBOOK.md with new role names

### Validation Coverage

- [ ] Add MultiTF validation plays with new role names
- [ ] Record new baseline hashes after schema rename
- [ ] Add data_env switching tests

---

## Pending Work (P3 - Low) ✅ COMPLETE

### Code Cleanup [DONE]

- [x] ~~Remove deprecated BacktestEngine code~~ **COMPLETED**
  - `BacktestEngine._evaluate_with_1m_subloop()` - REMOVED
  - `BarProcessor` class - DELETED (bar_processor.py)
  - `BacktestEngine.run()` - Now raises deprecation error
  - `run_backtest()` - Now raises deprecation error
  - Audits migrated to unified path (`run_engine_with_play()`)
- [x] Clean up unused imports in engine modules (verified: none found by ruff)
- [ ] Add type stubs for adapter protocols (deferred)

---

## Architecture Notes

### 3-Database Architecture

| Database | API Source | Purpose |
|----------|------------|---------|
| `market_data_backtest.duckdb` | api.bybit.com | Backtests (default) |
| `market_data_live.duckdb` | api.bybit.com | Live trading warm-up |
| `market_data_demo.duckdb` | api-demo.bybit.com | Paper trading |

### Position Modes

| Config | Meaning |
|--------|---------|
| `position_policy.mode: long_short` | Trade both directions sequentially (one-way) |
| `position_mode: oneway` (exchange) | No simultaneous long+short (hedge disabled) |

---

## References

- Unified Engine Plan: `docs/todos/UNIFIED_ENGINE_PLAN.md`
- Baseline Hashes: `docs/todos/UNIFIED_ENGINE_BASELINE.md`
- Engine Naming: `docs/specs/ENGINE_NAMING_CONVENTION.md`
