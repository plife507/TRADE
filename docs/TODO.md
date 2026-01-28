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

**Status**: NOT STARTED | **Blocks**: Live Trading

These MUST be fixed before any live trading. Each is a potential fund-loss or crash bug.

- [ ] **G0.1** Fix deadlock risk in order recording
  - File: `src/core/order_executor.py:374-405`
  - Issue: `record_trade()` called inside `_recorded_orders_lock`
  - Fix: Move `self.position.record_trade(...)` outside the lock context
  - Risk: Deadlock during order execution

- [ ] **G0.2** Fix RiskManager constructor signature mismatch
  - File: `src/engine/adapters/live.py:1041-1045`
  - Issue: Passes `position_manager=` but RiskManager expects `config=` and `enable_global_risk=`
  - Fix: Correct the constructor call to match `RiskManager.__init__()` signature
  - Risk: TypeError crash when `LiveExchange.connect()` is called

- [ ] **G0.3** Fix ExchangeManager instantiation per-call
  - File: `src/core/risk_manager.py:155-165`
  - Issue: `ExchangeManager()` created fresh on every `_get_funding_rate()` call
  - Fix: Use dependency injection or pass exchange manager at RiskManager construction
  - Risk: Auth issues, resource waste, potential rate limiting

- [ ] **G0.4** Add position sync on LiveRunner startup
  - File: `src/engine/runners/live_runner.py:164-198`
  - Issue: `start()` does not sync existing positions from exchange
  - Fix: Query exchange for open positions in `start()` before processing loop
  - Risk: Bot unaware of existing positions after restart

- [ ] **G0.5** Make entry + stop loss atomic
  - File: `src/core/exchange_orders_stop.py:343-362`
  - Issue: TPs placed AFTER entry succeeds - crash between leaves position unprotected
  - Fix: Place SL with entry order using `market_buy_with_tpsl`, add TPs after
  - Risk: Position without stop loss protection on crash

---

## G1: Dead Code Removal [0/19]

**Status**: NOT STARTED | **Blocks**: None (Quality)

Remove functions that are defined but never called. Reduces maintenance burden and confusion.

### Priority 1 - Clear Dead Code

- [ ] **G1.1** Delete `run_smoke_test()` - `src/backtest/runner.py:827`
- [ ] **G1.2** Delete `main()` - `src/backtest/runner.py:865`
- [ ] **G1.3** Delete `main()` - `src/backtest/gates/production_first_import_gate.py:356`
- [ ] **G1.4** Delete `adapt_funding_rows()` - `src/backtest/sim/adapters/funding_adapter.py:62`
- [ ] **G1.5** Delete `build_close_ts_map()` - `src/backtest/runtime/cache.py:201`
- [ ] **G1.6** Delete `reset_block_state()` - `src/backtest/runtime/block_state.py:158`
- [ ] **G1.7** Delete `get_available_indicators()` - `src/backtest/indicator_vendor.py:508`

### Priority 2 - Standalone Indicator Functions (Never Called)

- [ ] **G1.8** Delete standalone indicator functions - `src/backtest/indicator_vendor.py:544-755`
  - Functions: `ema()`, `sma()`, `rsi()`, `atr()`, `macd()`, `bbands()`, `stoch()`, `stochrsi()`
  - All computation goes through `compute_indicator()` - these are unused

### Priority 3 - Other Dead Functions

- [ ] **G1.9** Delete `extract_available_keys_from_feature_frames()` - `src/backtest/gates/indicator_requirements_gate.py:241`
- [ ] **G1.10** Delete `run_batch_verification()` - `src/backtest/gates/batch_verification.py:68`
- [ ] **G1.11** Delete `get_system_config_path()` - `src/backtest/system_config.py:1022`
- [ ] **G1.12** Delete `compute_zone_spec_id()` - `src/backtest/market_structure/spec.py:369`
- [ ] **G1.13** Delete `compute_zone_block_id()` - `src/backtest/market_structure/spec.py:411`
- [ ] **G1.14** Delete `build_features_from_preloaded_dfs()` - `src/backtest/features/feature_frame_builder.py:801`
- [ ] **G1.15** Delete `create_engine()` - `src/engine/factory.py:359`
- [ ] **G1.16** Delete `sim_to_engine_position()` - `src/engine/position_adapters.py:21`
- [ ] **G1.17** Delete `exchange_to_engine_position()` - `src/engine/position_adapters.py:71`
- [ ] **G1.18** Delete `normalize_position_side()` - `src/engine/position_adapters.py:132`
- [ ] **G1.19** Delete `run_backtest_isolated()` - `src/engine/runners/parallel.py:233`

---

## G2: Duplicate Code Removal [0/5]

**Status**: NOT STARTED | **Blocks**: None (Quality) | **After**: G1

Remove exact duplicates and consolidate redundant implementations.

- [ ] **G2.1** Delete duplicate metadata file (580+ lines)
  - Delete: `src/backtest/runtime/indicator_metadata.py`
  - Keep: `src/indicators/metadata.py`
  - Update imports in any files that reference the deleted path

- [ ] **G2.2** Consolidate `_parse_timeframe_minutes()` (5 copies!)
  - Files: `live_source.py:274`, `live_runner.py:430`, `live.py:663`, `backtest_source.py:296`, `demo_source.py:244`
  - Fix: Replace all with `from src.backtest.runtime.timeframe import tf_minutes`

- [ ] **G2.3** Consolidate `_datetime_to_epoch_ms()` (2 copies)
  - Files: `backtest_play_tools.py:980`, `preflight.py:117`
  - Fix: Create `src/utils/datetime_utils.py` with canonical implementation

- [ ] **G2.4** Consolidate timeframe constants (5 definitions)
  - Files: `constants.py:310`, `historical_data_store.py`, `timeframe.py`, `engine_data_prep.py:118`, `synthetic_data.py:41`
  - Fix: Use `TIMEFRAME_MINUTES` from `src/config/constants.py` everywhere

- [ ] **G2.5** Review duplicate type definitions
  - `ValidationResult` (4 definitions) - rename to context-specific names
  - `OrderResult` (2 definitions) - rename to `EngineOrderResult` vs `ExchangeOrderResult`
  - Document why each exists or consolidate

---

## G3: Legacy Shim Removal [0/10]

**Status**: NOT STARTED | **Blocks**: None (Quality) | **After**: G2

Per CLAUDE.md "ALL FORWARD, NO LEGACY" - delete shims, don't wrap.

### Priority 1 - Delete Re-export Wrapper Modules

- [ ] **G3.1** Delete `src/backtest/engine.py` (re-export shim)
  - Update callers to import from `src/backtest/engine_factory.py` directly

- [ ] **G3.2** Delete `src/tools/backtest_cli_wrapper.py` (re-export shim)
  - Update callers to import from specific tool modules

- [ ] **G3.3** Delete `src/backtest/market_structure/types.py` (re-export shim)
  - Update callers to import from `src/backtest/structure_types.py`

- [ ] **G3.4** Delete `src/backtest/play/__init__.py` if only re-exports
  - Or reduce to minimal exports

### Priority 2 - Delete Deprecated Stubs

- [ ] **G3.5** Delete `run_backtest()` stub - `src/backtest/engine_factory.py:36-54`
  - Already raises RuntimeError, safe to delete

- [ ] **G3.6** Evaluate `src/backtest/features/__init__.py` deprecation
  - If only internal usage, migrate internal code and delete

### Priority 3 - Remove Backward Compat Code

- [ ] **G3.7** Remove legacy "data" key - `src/config/config.py:254-264`
- [ ] **G3.8** Remove `GATE_CODE_DESCRIPTIONS` alias - `src/backtest/runtime/state_types.py:113`
- [ ] **G3.9** Remove `format_action_result` alias - `src/utils/cli_display.py:764`
- [ ] **G3.10** Remove legacy pattern names - `src/forge/validation/synthetic_data.py:63-65,1307`

---

## G4: Tech Debt - Function Refactoring [0/4]

**Status**: NOT STARTED | **Blocks**: None (Quality) | **After**: G3

Large functions that are hard to maintain and test.

- [ ] **G4.1** Refactor `run_backtest_with_gates()` (638 lines)
  - File: `src/backtest/runner.py:187-824`
  - Extract: `_setup_synthetic_data()`, `_run_preflight()`, `_create_manifest()`, `_run_engine()`, `_write_artifacts()`, `_build_result()`
  - Target: Main function < 100 lines, extracted functions < 80 lines each

- [ ] **G4.2** Refactor `Play.from_dict()` (335 lines)
  - File: `src/backtest/play/play.py:528-863`
  - Extract: `_parse_account_config()`, `_parse_features()`, `_parse_timeframes()`, `_parse_actions()`, `_parse_risk_model()`, `_parse_structures()`
  - Target: Main method < 50 lines

- [ ] **G4.3** Refactor `process_bar()` (206 lines)
  - File: `src/backtest/sim/exchange.py:488-693`
  - Extract: `_process_funding()`, `_process_orders()`, `_update_dynamic_stops()`, `_check_exits()`, `_track_mae_mfe()`, `_check_liquidation()`
  - Target: Main method < 50 lines

- [ ] **G4.4** Refactor `prepare_backtest_frame_impl()` (252 lines)
  - File: `src/backtest/engine_data_prep.py:123-374`
  - Extract: `_validate_inputs()`, `_compute_windows()`, `_load_data()`, `_apply_indicators()`, `_compute_sim_start()`
  - Target: Main function < 60 lines

---

## G5: Infrastructure Improvements [0/8]

**Status**: NOT STARTED | **Blocks**: None (Quality) | **After**: G4

Improvements for production reliability.

### Memory Management

- [ ] **G5.1** Add maxsize to event queue
  - File: `src/data/realtime_state.py:161`
  - Fix: `Queue(maxsize=10000)` or periodic flushing

- [ ] **G5.2** Replace list slicing with deque
  - Files: `src/data/realtime_state.py:491,586`
  - Fix: Use `deque(maxlen=N)` for `_recent_trades` and `_executions`

### Live Trading Robustness

- [ ] **G5.3** Add exponential backoff to WS reconnect
  - File: `src/engine/runners/live_runner.py:525`
  - Fix: Increase delay on consecutive failures

- [ ] **G5.4** Add automated position reconciliation
  - File: `src/core/position_manager.py:159`
  - Fix: Background task calling `reconcile_with_rest()` every 30-60s

- [ ] **G5.5** Add retry to panic close
  - File: `src/core/safety.py:115-139`
  - Fix: Retry failed cancel/close operations 3x

### Missing Features

- [ ] **G5.6** Implement ADXR output
  - File: `src/indicators/incremental.py` (IncrementalADX)
  - Issue: Registry declares `adxr` output but not implemented
  - Fix: Add `adxr_value` property with historical ADX buffer

- [ ] **G5.7** Add explicit state machine to LiveRunner
  - File: `src/engine/runners/live_runner.py:40-48`
  - Fix: Add lock around state transitions, document valid transitions

- [ ] **G5.8** Add explicit state machine to PlayEngine
  - File: `src/engine/play_engine.py:113-231`
  - Fix: Create formal EngineState enum with transition validation

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
