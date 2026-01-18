# Live Trading Readiness - Gated Checklist

**Date:** 2026-01-15
**Branch:** feature/unified-engine
**Goal:** Complete all gates before enabling live trading

---

## Gate 0: Code Audit Baseline (COMPLETE)

**Status:** PASSED

- [x] Unified engine migration complete
- [x] Legacy `BacktestEngine.run()` deprecated with RuntimeError
- [x] Legacy `run_backtest()` deprecated with RuntimeError
- [x] Parallel backtest infrastructure verified
- [x] Async patterns reviewed and verified safe
- [x] Type hints using modern Python 3.12+ syntax

---

## Gate 1: Deprecated Code Cleanup

**Status:** PASSED ✓

### 1.1 Hard Deprecations (RuntimeError) - DONE
- [x] `BacktestEngine.run()` - Raises RuntimeError
- [x] `run_backtest()` - Raises RuntimeError
- [x] `bar_processor.py` - DELETED

### 1.2 Soft Deprecations - NOW HARD DEPRECATED ✓
- [x] `load_system_config()` in `system_config.py` - Now raises RuntimeError
- [x] `backtest_list_systems_tool()` - Returns deprecation error
- [x] `backtest_get_system_tool()` - Returns deprecation error
- [x] `backtest_preflight_check_tool()` - Returns deprecation error
- [x] `backtest_prepare_data_tool()` - Returns deprecation error
- [x] `backtest_verify_data_tool()` - Returns deprecation error

### 1.3 Delegation Modules - DEFERRED
| Module | Delegates To | Action |
|--------|--------------|--------|
| `src/backtest/incremental/` | `src/structures/` | Keep until all imports migrated |
| `src/backtest/features/` | `src/indicators/` | Keep until all imports migrated |

---

## Gate 2: Stub Implementations

**Status:** PASSED ✓

### 2.1 LivePriceSource (P1 - Required for Live Trading)

**File:** `src/core/prices/live_source.py`

| Method | Status | Description |
|--------|--------|-------------|
| `get_mark_price()` | [x] DONE | Get mark price from HistoricalDataStore(env="live") |
| `get_ohlcv()` | [x] DONE | Get OHLCV from market_data_live.duckdb |
| `get_1m_marks()` | [x] DONE | Get historical 1m mark prices |
| `healthcheck()` | [x] DONE | Check DuckDB connection status |
| `connect()` | [x] DONE | Stub (WebSocket future) |
| `disconnect()` | [x] DONE | Clear cache |

### 2.2 DemoPriceSource (P1 - Required for Demo Trading)

**File:** `src/backtest/prices/demo_source.py`

| Method | Status | Description |
|--------|--------|-------------|
| `get_mark_price()` | [x] DONE | Get mark price from HistoricalDataStore(env="demo") |
| `get_ohlcv()` | [x] DONE | Get OHLCV from market_data_demo.duckdb |
| `get_1m_marks()` | [x] DONE | Get historical 1m mark prices |
| `healthcheck()` | [x] DONE | Check DuckDB connection status |

### Architecture Note
Both sources wrap HistoricalDataStore with appropriate env for warm-up data.
WebSocket real-time updates can be added later without changing the interface.

---

## Gate 3: Technical Debt Resolution

**Status:** PASSED ✓ (Critical TODOs resolved)

### 3.1 Critical TODOs

| File | Line | TODO | Status |
|------|------|------|--------|
| `adapters/backtest.py` | 400 | Liquidation price calculation | [x] DONE - Uses LiquidationModel |
| `play_engine.py` | 466 | Realized PnL tracking | [x] DONE - Uses exchange.get_realized_pnl() |

### 3.2 Performance TODOs

| File | Line | TODO | Priority |
|------|------|------|----------|
| `adapters/live.py` | 137 | Incremental indicator computation | P2 |
| `adapters/live.py` | 465 | Structure history for lookback | P3 |

### 3.3 Feature TODOs

| File | Line | TODO | Priority |
|------|------|------|----------|
| `forge/functional/generator.py` | 349 | Add structure and operator plays | P3 |
| `forge/functional/generator.py` | 423 | Add --structures and --operators handling | P3 |
| `rationalization/conflicts.py` | 311 | Check transition history | P3 |

---

## Gate 4: Parallel Backtest Verification

**Status:** DEFERRED - Needs separate database architecture

### Implementation Status
- [x] `src/engine/runners/parallel.py` - Code complete
- [x] `run_backtests_parallel()` - Implemented
- [x] `run_backtest_isolated()` - Implemented
- [ ] Database isolation - NEEDS NEW APPROACH

### Issue
DuckDB single-writer limitation means parallel backtests need a dedicated database strategy:
- Option A: Separate database file per parallel worker
- Option B: In-memory database copies for parallel runs
- Option C: Pre-load all data then run parallel (no DB access during run)

### Current Workaround
Read-only mode implemented but not production-ready. For now, run backtests sequentially.

### Future Work
Implement proper parallel database architecture when needed for batch optimization runs.

---

## Gate 5: Live Integration Testing

**Status:** PARTIAL (Prerequisites met, requires manual exchange testing)

### Prerequisites
- [x] Gate 2.1 (LivePriceSource) complete
- [x] Gate 2.2 (DemoPriceSource) complete

### Tasks (Automated - from CLI smoke test)
- [x] Demo account connection verified
- [x] Order placement (limit buy) tested
- [x] Order cancellation tested
- [x] Balance/equity queries working
- [x] Market data (price, OHLCV, funding) working

### Tasks (Manual Testing Required)
- [ ] Test LiveDataProvider with real WebSocket streaming
- [ ] Test full order execution flow (fill confirmation)
- [ ] Test position tracking (open/close cycle)
- [ ] Test stop-loss/take-profit execution

---

## Gate 6: Final Validation

**Status:** PASSED ✓

### Smoke Tests
- [x] Full CLI smoke test passes (0 failures)
- [x] Play normalization: 119/119 Plays validated
- [x] Metadata smoke test passes
- [x] Demo trading smoke test passes

### Audit Verification
- [x] `audit_rollup_parity.py` passes (11 intervals, 80 comparisons)
- [x] `audit_metrics.py` passes (6/6 calculations)
- [x] `toolkit_contract_audit.py` passes (43/43 indicators)
- [x] Indicator registry: All 43 indicators validated

---

## Summary

| Gate | Name | Status | Blocker |
|------|------|--------|---------|
| 0 | Code Audit Baseline | COMPLETE | - |
| 1 | Deprecated Code Cleanup | PASSED ✓ | - |
| 2 | Stub Implementations | PASSED ✓ | - |
| 3 | Technical Debt Resolution | PASSED ✓ | - |
| 4 | Parallel Backtest Verification | DEFERRED | Needs new DB |
| 5 | Live Integration Testing | PARTIAL | Manual testing |
| 6 | Final Validation | PASSED ✓ | - |

**Live Trading Readiness: 85% complete. Gates 0-3, 6 PASSED. Gate 5 PARTIAL (basic demo tests pass, manual position lifecycle testing needed).**

---

## Execution Order

1. **Gate 1.2** - Remove `load_system_config()` soft deprecation
2. **Gate 4** - Verify parallel backtests work
3. **Gate 2** - Implement price source stubs
4. **Gate 3** - Address technical debt
5. **Gate 5** - Live integration testing
6. **Gate 6** - Final validation

**Estimated Completion:** Gate 1-4 can be done immediately. Gate 5-6 require exchange integration testing.
