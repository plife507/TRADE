# Phase Notes — RuntimeSnapshot + MTF Caching + Mark Unification

Tracking document for the strict refactor implementation.
Each phase appends an entry with files touched, decisions made, open questions, and artifacts.

---

## Phase 0 — Prep / Cutover (Started)

**Date**: 2024-12-13

### Files Created

- `src/backtest/runtime/__init__.py` — Runtime module entry point
- `src/backtest/runtime/types.py` — Canonical Bar, FeatureSnapshot, ExchangeState, RuntimeSnapshot
- `src/backtest/runtime/timeframe.py` — tf_duration, tf_minutes, validate_tf_mapping
- `src/backtest/runtime/windowing.py` — LoadWindow computation, warmup/buffer spans
- `src/backtest/runtime/data_health.py` — DataHealthCheck, GapRange, CoverageInfo
- `src/backtest/runtime/snapshot_builder.py` — SnapshotBuilder (no PriceModel access)
- `src/backtest/runtime/cache.py` — TimeframeCache for HTF/MTF carry-forward
- `src/backtest/artifacts/__init__.py` — Artifacts module entry point
- `src/backtest/artifacts/manifest_writer.py` — run_manifest.json writer
- `src/backtest/artifacts/eventlog_writer.py` — events.jsonl append-only writer
- `src/backtest/artifacts/equity_writer.py` — Optional equity_curve.csv writer

### Tracking Files Created

- `PHASE_NOTES.md` (this file)
- `TODO_PHASES.md` — Phase checklists

### Decisions Made

1. **Canonical Bar location**: `src/backtest/runtime/types.py` is the single source of truth
2. **USDT naming**: ExchangeState uses `*_usdt` suffix for all balance/margin fields
3. **No None defaults**: FeatureSnapshot uses `ready=False` placeholder instead of None
4. **Artifacts isolation**: Core engine/sim/runtime cannot import from artifacts/
5. **Data-driven close detection**: Using close_ts maps, not modulo alignment

### Open Questions

1. ~~Need to verify TF_MINUTES import path works correctly~~ ✅ Verified
2. ~~Need to wire preflight gate in backtest_tools.py (Phase -1)~~ ✅ Done

### Validation Completed

- ✅ Compile/import check passes (all runtime and artifacts modules import successfully)
- ✅ No forbidden imports (artifacts → core) verified
- ✅ TF_MINUTES import works correctly (tf_duration, tf_minutes)

### Artifacts Produced

None yet (module structure only)

---

## Phase -1 — Preflight Data Health Gate (COMPLETED)

**Date**: 2024-12-13 (initial), 2025-12-13 (completed)

### Files Modified

- `src/tools/backtest_tools.py` — Added preflight gate with heal loop via ToolRegistry

### Files Created

- `tests/test_integration_duckdb_preflight_gate.py` — Integration Gate 1 tests (5 tests, opt-in)

### Functions Added

- `backtest_preflight_check_tool(system_id, window_name, heal_if_needed, max_heal_attempts)`
  - Computes load window with warmup/buffers
  - Runs DataHealthCheck on OHLCV and funding data
  - Implements precheck → heal → recheck loop via ToolRegistry tools
  - Hard-fails after MAX_HEAL_ATTEMPTS (3)
  
- Modified `backtest_run_tool` to call preflight gate before engine creation
  - Added `run_preflight` and `heal_if_needed` parameters
  - Blocks simulation if preflight fails

### Corrections Applied (2025-12-13)

**CRITICAL FIX**: Heal loop was using direct store calls instead of ToolRegistry tools.

Before (WRONG):
```python
store.fill_gaps(...)
store.sync_range(...)
store.sync_funding(...)
```

After (CORRECT):
```python
fill_gaps_tool(symbol=..., timeframe=..., env=...)
sync_range_tool(symbols=..., start=..., end=..., timeframes=..., env=...)
sync_funding_tool(symbols=..., period=..., env=...)
```

### Decisions Made

1. **MAX_HEAL_ATTEMPTS = 3**: Three attempts to heal before hard-fail
2. **Heal strategy**: Uses ToolRegistry tools (`fill_gaps_tool`, `sync_range_tool`, `sync_funding_tool`)
3. **Funding period**: Uses 6M period for funding sync during healing (generous buffer)
4. **Preflight is opt-out**: Default is to run preflight (run_preflight=True)
5. **Integration tests opt-in**: Set `BACKTEST_INTEGRATION_TEST=1` to run Integration Gate 1

### Tests Passed

- Tier 1 (Unit/Smoke): `test_backtest_preflight_data_health_gate.py` — 14/14 ✅
- Integration Gate 1: `test_integration_duckdb_preflight_gate.py` — 7/7 ✅

### Additional Fixes (2025-12-13)

1. **Funding coverage tolerance**: Added `FUNDING_INTERVAL_TOLERANCE = 8 hours` to `data_health.py`
   - Funding only occurs at fixed 8-hour intervals (00:00, 08:00, 16:00 UTC)
   - Coverage check now allows tolerance for funding data edges

2. **End-to-end preflight test**: Added `TestIntegrationPreflightHealLoop` class with:
   - `test_preflight_tool_with_healing_enabled`: Full heal loop verification
   - `test_preflight_without_healing_reports_issues`: Report-only mode

3. **Historical funding backfill**: Manually fetched historical funding data to cover system config window (2024-12-31 to 2025-06-30)

### Open Questions

None — Phase -1 complete

### Determinism Check

N/A (no engine run yet)

---

## Phase 1 — ts_open/ts_close Introduction (COMPLETED)

**Date**: 2024-12-13

### Files Created

- `src/backtest/sim/bar_compat.py` — Bar utility helpers (canonical-only; `AnyBar = Bar`)

### Files Modified

- `src/backtest/sim/adapters/ohlcv_adapter.py` — Added canonical Bar adapter functions
- `src/backtest/sim/types.py` — Added deprecation notice for legacy Bar
- `src/backtest/sim/pricing/price_model.py` — Uses canonical Bar (no legacy)
- `src/backtest/sim/execution/execution_model.py` — Uses ts_open for fill timestamps
- `src/backtest/sim/pricing/intrabar_path.py` — Uses get_bar_ts_open() for path timing
- `src/backtest/sim/exchange.py` — Consumes canonical Bar (AnyBar is an alias), ts_open for fills, ts_close for MTM
- `src/backtest/engine.py` — Creates canonical Bar, uses ts_close for step time

### Functions Added

- `adapt_ohlcv_row_canonical(row, symbol, tf)` — Produces canonical Bar with ts_open/ts_close
- `adapt_ohlcv_dataframe_canonical(df, symbol, tf)` — Batch version
- `build_bar_close_ts_map(df, symbol, tf)` — For data-driven close detection
- `get_bar_ts_open(bar)` — Get ts_open (fills occur at bar open)
- `get_bar_ts_close(bar)` — Get ts_close (step time / MTM)
- `get_bar_timestamp(bar)` — Step time helper (ts_close)

### Changes Made

1. **Canonical Bar in engine**: Engine now creates CanonicalBar with explicit ts_open/ts_close
2. **ts_close for step time**: Equity curve, account curve timestamps use ts_close
3. **ts_open for fills**: All fill timestamps (entry, exit) use ts_open
4. **No legacy bars**: `AnyBar` is now an alias of CanonicalBar only (canonical-only codebase)
5. **Signal submission**: Uses ts_close (decision made at bar close)
6. **PriceModel semantics**: Uses canonical bar timing helpers (`ts_open`/`ts_close`)
7. **Legacy removed**: Legacy Bar + MarketSnapshot support removed post-cutover

### Tests Created

- `tests/test_phase1_ts_open_ts_close.py` — 14 tests for Bar structure and semantics
- `tests/test_phase1_determinism.py` — 5 tests for deterministic replay

### Tests Passed (70 total)

- `test_simulated_exchange_accounting.py` — 25/25 passed
- `test_exchange_indicator_separation.py` — 6/6 passed
- `test_phase1_ts_open_ts_close.py` — 14/14 passed
- `test_phase1_determinism.py` — 5/5 passed
- `test_proof_metrics.py` — 20/20 passed

### Acceptance Criteria Met

1. ✅ **No code assumes DB timestamp == close**: Explicit ts_open/ts_close used
2. ✅ **ts_open/ts_close explicit everywhere**: All modules use bar_compat functions
3. ✅ **Deterministic replay passes**: Two runs produce identical state hash

### Open Questions

None — Phase 1 complete

---

## Phase 2 — RuntimeSnapshot Contract + Single Builder

**Status**: ✅ COMPLETE
**Started**: 2025-12-13
**Completed**: 2025-12-13

### Files Touched

1. `src/backtest/runtime/snapshot_builder.py` — Added `build_exchange_state_from_exchange()` helper
2. `src/backtest/engine.py` — Added SnapshotBuilder, updated `_build_snapshot()` to return RuntimeSnapshot, removed `_build_legacy_snapshot()`
3. `src/backtest/simulated_risk_manager.py` — Updated to accept `RuntimeSnapshot` only (removed MarketSnapshot support)
4. `src/backtest/__init__.py` — Removed MarketSnapshot from exports
5. `src/strategies/base.py` — Updated BaseStrategy to accept `RuntimeSnapshot` only (removed AnySnapshot Union)
6. `src/strategies/ema_rsi_atr.py` — Updated to extract features from RuntimeSnapshot only
7. `src/strategies/registry.py` — Updated StrategyFunction type alias to use RuntimeSnapshot only
8. `tests/test_phase2_runtime_snapshot_contract.py` — 13 new tests, updated to verify RuntimeSnapshot-only contract

### Key Decisions

1. **RuntimeSnapshot Only**: Removed MarketSnapshot support completely - RuntimeSnapshot is the only supported snapshot type
2. **Single-TF Mode**: In Phase 2, all TF roles (htf, mtf, ltf) point to the same timeframe; proper MTF caching comes in Phase 3
3. **Feature Extraction**: Strategy extracts indicators from `snapshot.features_ltf.features` dict
4. **No Legacy Support**: Removed `_build_legacy_snapshot()` and all MarketSnapshot references - clean break from old API

### Acceptance Criteria Met

1. ✅ **Strategy input is RuntimeSnapshot only**: `ema_rsi_atr_strategy` accepts and processes RuntimeSnapshot
2. ✅ **Snapshot building centralized in SnapshotBuilder**: Engine uses `_snapshot_builder.build_with_defaults()`
3. ✅ **Tests pass**: 13 Phase 2 tests + all prior tests (Phase 0: 20, Phase -1: 14+7, Phase 1: 19)

### Open Questions

None — Phase 2 complete

---

## Phase 3 — TF Close Detection + Caching (MTF/HTF)

**Status**: ✅ COMPLETE
**Started**: 2025-12-13
**Completed**: 2025-12-13

### Files Touched

1. `src/backtest/engine.py` — Added multi-TF data loading, TimeframeCache integration, readiness gate
2. `src/backtest/runtime/cache.py` — Used existing TimeframeCache with close_ts maps
3. `tests/test_phase3_mtf_cache.py` — 20 new tests for cache behavior

### Key Changes

1. **Multi-TF Engine Configuration**:
   - Engine accepts optional `tf_mapping` parameter (htf, mtf, ltf → tf strings)
   - Defaults to single-TF mode (all roles = LTF) for backward compatibility
   - Added `_multi_tf_mode` flag to control behavior

2. **Multi-TF Data Loading**:
   - Added `prepare_multi_tf_frames()` method
   - Loads data for each unique TF in tf_mapping
   - Applies indicators to each TF DataFrame
   - Builds close_ts maps for data-driven close detection

3. **TimeframeCache Integration**:
   - Engine creates TimeframeCache instance at init
   - Sets close_ts maps during data loading
   - Added `_refresh_tf_caches()` method called at each bar close
   - Uses factory functions to build FeatureSnapshots from TF DataFrames

4. **Readiness Gate**:
   - Checks `snapshot.ready` before strategy evaluation
   - Skips trading (but records equity) until all caches ready
   - Logs when caches become ready

5. **MultiTFPreparedFrames Dataclass**:
   - Holds all TF DataFrames with indicators
   - Stores close_ts maps for each TF
   - Provides helpers for getting HTF/MTF/LTF close timestamps

### Key Decisions

1. **Data-Driven Close Detection**: Uses close_ts sets built from actual bar data, not modulo-based alignment
2. **HTF-First Update Order**: At coincident closes, HTF updates before MTF (deterministic)
3. **Cache Carry-Forward**: Between closes, cached values are returned unchanged
4. **Warmup Spans**: HTF warmup span calculated separately (may need more history)

### Acceptance Criteria Met

1. ✅ **Between closes, cached snapshots don't change**: Verified in `test_cached_value_unchanged_between_closes`
2. ✅ **At close timestamps, caches update exactly once**: Verified in `test_cache_updates_at_close_only`
3. ✅ **Coincident closes update deterministically (HTF then MTF)**: Verified in `test_htf_updates_before_mtf`
4. ✅ **Trading disabled until HTF/MTF caches ready**: Verified in `test_not_ready_until_first_close`, `test_ready_after_both_updated`

### Tests Passed (102 total Phase 0-3)

- Phase 0: `test_phase0_module_structure.py` — 20/20
- Phase -1: `test_backtest_preflight_data_health_gate.py` — 14/14
- Phase 1: `test_phase1_ts_open_ts_close.py` — 14/14, `test_phase1_determinism.py` — 5/5
- Phase 2: `test_phase2_runtime_snapshot_contract.py` — 13/13
- Phase 3: `test_phase3_mtf_cache.py` — 20/20
- Core: `test_simulated_exchange_accounting.py` — 25/25, `test_proof_metrics.py` — 20/20, `test_exchange_indicator_separation.py` — 6/6

### Open Questions

None — Phase 3 complete

---

## Phase 4 — Mark Price Proxy Unification (Completed)

**Date**: 2024-12-13

### Goal

Unify mark price computation so:
1. SimulatedExchange computes mark_price exactly once per step
2. StepResult returns mark_price to caller
3. SnapshotBuilder receives mark_price from exchange (never calls PriceModel)
4. All MTM/liquidation uses the same mark_price

### Files Modified

1. `src/backtest/sim/types.py`:
   - Added `ts_close`, `mark_price`, `mark_price_source` fields to StepResult
   - Updated `to_dict()` to include new fields

2. `src/backtest/sim/exchange.py`:
   - Changed `process_bar()` return type from `List` to `StepResult`
   - Compute mark_price once via PriceModel at start of step
   - Pass mark_price to `ledger.update_for_mark_price()`
   - Return StepResult with mark_price, ts_close, mark_price_source
   - Added `_last_closed_trades` attribute and `last_closed_trades` property

3. `src/backtest/engine.py`:
   - Updated to capture StepResult from `process_bar()`
   - Get closed trades via `exchange.last_closed_trades`
   - Pass `step_result` to `_build_snapshot()`
   - Updated `_build_snapshot()` to use `step_result.mark_price`
   - Added `StepResult` import
   - Updated module docstring with Phase 4 notes

4. Tests updated for new API:
   - `tests/test_phase1_determinism.py` — use `last_closed_trades`
   - `tests/test_simulated_exchange_accounting.py` — use `last_closed_trades`

### Files Created

- `tests/test_backtest_mark_price_unification.py` — 18 tests

### Key Implementation Details

1. **Single Source of Truth**:
   ```python
   # In process_bar():
   prices = self._price_model.get_prices(bar, spread)
   mark_price = prices.mark_price  # Computed once
   
   # Used for MTM update
   self._ledger.update_for_mark_price(self.position, mark_price)
   
   # Returned in StepResult
   return StepResult(
       ts_close=step_time,
       mark_price=mark_price,
       mark_price_source=self._mark_source,
       ...
   )
   ```

2. **Backward Compatibility**:
   - Added `last_closed_trades` property to get trades closed in last step
   - Tests updated to use this property instead of return value

3. **SnapshotBuilder**:
   - Already required `mark_price` as parameter (by design)
   - Engine now passes `step_result.mark_price` instead of computing from `bar.close`

### Acceptance Criteria Met

1. ✅ **RuntimeSnapshot.mark_price == exchange mark price**: Verified in `test_runtime_snapshot_mark_equals_exchange_mark`
2. ✅ **SnapshotBuilder never calls PriceModel**: Verified in `test_snapshot_never_calls_price_model` (requires mark_price parameter)
3. ✅ **Mark price computed once per step**: Verified in `test_mark_price_single_source_of_truth`
4. ✅ **MTM uses exchange mark_price**: Verified in `test_mark_price_used_for_mtm`

### Tests Passed (89 total tests run)

- Phase 1: `test_phase1_determinism.py` — 5/5
- Phase 2: `test_phase2_runtime_snapshot_contract.py` — 13/13
- Phase 3: `test_phase3_mtf_cache.py` — 20/20
- Phase 4: `test_backtest_mark_price_unification.py` — 18/18
- Core: `test_simulated_exchange_accounting.py` — 25/25
- Core: `test_stop_semantics.py` — 12/12

### Open Questions

None — Phase 4 complete

---
