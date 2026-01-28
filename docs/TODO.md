# TRADE TODO

Active work tracking for the TRADE trading bot. **This is the single source of truth for all open work.**

---

## Current Phase: Audit Remediation

Full codebase audit completed 2026-01-27. Found 5 critical bugs, 19 dead functions, 27 legacy shims, and significant tech debt. All math is correct.

### Gate Dependencies

```
G0 (Critical) ─────────────────────────────► LIVE TRADING ENABLED
     │
     ▼
G1 (Dead Code) ──► G2 (Duplicates) ──► G3 (Legacy) ──► CLEAN CODEBASE
                                            │
                                            ▼
                              G4 (Refactoring) ──► G5 (Infrastructure)
                                                          │
                                                          ▼
                                                   PRODUCTION READY
```

---

## G0: Critical Live Trading Blockers [0/5]

**Status**: COMPLETE ✓ `16891f5` | **Blocks**: Live Trading

These MUST be fixed before any live trading. Each is a potential fund-loss or crash bug.

- [x] **G0.1** Fix deadlock risk in order recording ✓
  - File: `src/core/order_executor.py:374-405`
  - Fix: Moved `self.position.record_trade(...)` outside the lock context

- [x] **G0.2** Fix RiskManager constructor signature mismatch ✓
  - File: `src/engine/adapters/live.py:1041-1045`
  - Fix: Corrected constructor call to match `RiskManager.__init__()` signature

- [x] **G0.3** Fix ExchangeManager instantiation per-call ✓
  - File: `src/core/risk_manager.py:155-165`
  - Fix: Used shared singleton from `_get_exchange_manager()`

- [x] **G0.4** Add position sync on LiveRunner startup ✓
  - File: `src/engine/runners/live_runner.py:164-198`
  - Fix: Added `_sync_positions_on_startup()` called in `start()`

- [x] **G0.5** Make entry + stop loss atomic ✓
  - File: `src/core/exchange_orders_stop.py:343-362`
  - Fix: Added explicit SL order as backup after entry

---

## G1: Dead Code Removal [19/19] ✓

**Status**: COMPLETE ✓ `657d07f` | **Blocks**: None (Quality)

Removed 19 functions that were defined but never called.

- [x] **G1.1-G1.19** All dead functions removed ✓
  - Deleted unused standalone functions, helpers, and entry points

---

## G2: Duplicate Code Removal [5/5] ✓

**Status**: COMPLETE ✓ `59c607d` | **Blocks**: None (Quality) | **After**: G1

- [x] **G2.1-G2.5** All duplicate code removed or consolidated ✓

---

## G3: Legacy Shim Removal [10/10] ✓

**Status**: COMPLETE ✓ `2ad0e44` | **Blocks**: None (Quality) | **After**: G2

- [x] **G3.1-G3.10** All legacy shims and aliases removed ✓

---

## G4: Tech Debt - Function Refactoring [4/4] ✓

**Status**: COMPLETE ✓ | **Blocks**: None (Quality) | **After**: G3

Extracted helper functions from large methods to improve maintainability.

- [x] **G4.1** Refactor `run_backtest_with_gates()` ✓ `df495d3`
  - File: `src/backtest/runner.py`
  - Extracted: 8 helper functions, main function now ~100 lines

- [x] **G4.2** Refactor `Play.from_dict()` ✓ `a67f943`
  - File: `src/backtest/play/play.py`
  - Extracted: `_parse_timeframes()`, `_parse_features()`, `_parse_actions()`, `_parse_risk_model()`, `_parse_structures()`

- [x] **G4.3** Refactor `process_bar()` ✓ `4c496aa`
  - File: `src/backtest/sim/exchange.py`
  - Extracted: 6 helper methods for phases

- [x] **G4.4** Refactor `prepare_backtest_frame_impl()` ✓ `c18617f`
  - File: `src/backtest/engine_data_prep.py`
  - Extracted: 6 helper functions

---

## G5: Infrastructure Improvements [8/8] ✓

**Status**: COMPLETE ✓ | **Blocks**: None (Quality) | **After**: G4

Improvements for production reliability.

### Memory Management

- [x] **G5.1** Add maxsize to event queue ✓ `89beb41`
  - File: `src/data/realtime_state.py:161`
  - Fix: `Queue(maxsize=10000)` or periodic flushing

- [x] **G5.2** Replace list slicing with deque ✓ `89beb41`
  - Files: `src/data/realtime_state.py:491,586`
  - Fix: Use `deque(maxlen=N)` for `_recent_trades` and `_executions`

### Live Trading Robustness

- [x] **G5.3** Add exponential backoff to WS reconnect ✓ `89beb41`
  - File: `src/engine/runners/live_runner.py:525`
  - Fix: Increase delay on consecutive failures

- [x] **G5.4** Add automated position reconciliation ✓ `89beb41`
  - File: `src/engine/runners/live_runner.py`
  - Fix: Periodic reconciliation via `_maybe_reconcile_positions()` every 5 min

- [x] **G5.5** Add retry to panic close ✓ `89beb41`
  - File: `src/core/safety.py:115-139`
  - Fix: Retry failed cancel/close operations 3x

### Missing Features

- [x] **G5.6** Implement ADXR output ✓ `89beb41`
  - File: `src/indicators/incremental.py` (IncrementalADX)
  - Fix: Added `adxr_value` property with historical ADX buffer

- [x] **G5.7** Add explicit state machine to LiveRunner ✓ `7814e3a`
  - File: `src/engine/runners/live_runner.py:40-48`
  - Fix: Added VALID_TRANSITIONS, _state_lock, _transition_state()

- [x] **G5.8** Add explicit state machine to PlayEngine ✓ `7814e3a`
  - File: `src/engine/play_engine.py:113-231`
  - Fix: Added EnginePhase enum, VALID_PHASE_TRANSITIONS, _transition_phase()

---

## G6: Codebase Review Remediation [COMPLETE] ✓

**Status**: COMPLETE ✓ `8b8841a` `7c65a13` `38d918c` | **Blocks**: None (Quality) | **After**: G5

Full codebase review completed 2026-01-28 (307 files, 126K LOC). Fixed critical bugs and cleaned up code quality issues.

### Fund Safety Critical (4/4) ✓

- [x] **G6.0.1** Fix missing `max_position_pct` attribute ✓
- [x] **G6.0.2** Fix `tf_minutes` vs `tf_mins` variable bug ✓
- [x] **G6.0.3** Fix Position field name `liq_price` → `liquidation_price` ✓
- [x] **G6.0.4** Add missing Position required fields ✓

### Build/Import Errors (3/3) ✓

- [x] **G6.1.1** Fix missing `print_data_result` import ✓
- [x] **G6.1.2-3** Fix broken relative imports in audit_trend_detector.py ✓

### Thread Safety Critical (2/2) ✓

- [x] **G6.2.1** Add threading.Lock to LiveIndicatorCache ✓
- [x] **G6.2.2** Add threading.Lock to LiveDataProvider buffers ✓

### LF Line Endings (2/2) ✓

- [x] **G6.3.1-2** Add `newline='\n'` to file writers ✓

### Dead Code & Best Practices ✓

- [x] Delete unused files: `src/engine/types.py`, `src/data/historical_queries.py`
- [x] Remove 128 LOC dead code in `system_config.py`
- [x] Remove unused imports across 6 files
- [x] Fix `datetime.utcnow()` → `datetime.now(timezone.utc)`
- [x] Remove legacy `blocks` key support (use `actions` only)
- [x] Fix `is_triggered` semantic bug in sim/types.py
- [x] Bound `_trades` list with deque in position_manager.py
- [x] Fix USDT typos and duplicate docstrings in sim files

---

## Validation After Each Gate

```bash
# After G0 (Critical):
python trade_cli.py --smoke full

# After G1-G3 (Code Removal):
python trade_cli.py --smoke full
# Verify no import errors

# After G4 (Refactoring):
python trade_cli.py --smoke backtest
python trade_cli.py backtest audit-toolkit

# After G5 (Infrastructure):
python trade_cli.py --smoke full
# Manual live testing with demo mode
```

---

## Backlog (Post-Remediation)

### P2: DSL Enhancement

- [ ] Build DSL validator
- [ ] Implement typed block layer
- [ ] Add block composition

### P3: Live Trading Integration

- [ ] Test LiveIndicatorProvider with real WebSocket data
- [ ] Paper trading integration
- [ ] Complete live adapter stubs

### P4: Incremental Indicator Expansion

Expand O(1) incremental indicators from 11 to 43 (full coverage).

---

## Completed Gates

| Gate | Items | Status | Blocking |
|------|-------|--------|----------|
| Audit: Math Correctness | 6 areas | ✓ All Correct | - |
| Audit: Warmup Logic | 50 items | ✓ All Correct | - |
| Audit: State Management | 4 areas | ✓ Sound | - |

---

## Completed Work (2026-01)

### 2026-01-27: Full Codebase Audit

- [x] Audited indicator math (43 indicators) - all correct
- [x] Audited structure detector math (6 detectors) - all correct
- [x] Audited DSL evaluation (20 operators) - all correct
- [x] Audited sizing/risk formulas - all correct
- [x] Audited warmup logic (indicators + structures) - all correct
- [x] Audited incremental state management - sound with minor concerns
- [x] Audited demo/live trading state flow - identified critical issues
- [x] Identified 19 dead functions
- [x] Identified 27 legacy shims
- [x] Identified 580+ line file duplicate
- [x] Identified 4 functions needing refactoring (1400+ lines total)

### 2026-01-25: Unified Indicator System

- [x] Implemented unified indicator system with registry-driven architecture
- [x] Created IndicatorProvider protocol (`src/indicators/provider.py`)
- [x] Expanded incremental indicators from 6 to 11 (O(1) for live trading)
- [x] Removed all hardcoded indicator lists - registry is single source of truth
- [x] Comprehensive DSL cookbook review and fixes

### 2026-01-22: Validation Suite & Synthetic Data

- [x] Created validation plays (consolidated to 19 core plays across 3 tiers)
- [x] Implemented 34 synthetic market condition patterns
- [x] Added SyntheticConfig to Play class for auto-synthetic data
- [x] Fixed synthetic mode TIMEFRAME_NOT_AVAILABLE error

### 2026-01-21: Engine Migration

- [x] PlayEngine migration complete (1,166 lines)
- [x] BacktestEngine deleted (re-exports only remain)
- [x] Position sizing caps added (max_position_equity_pct)
