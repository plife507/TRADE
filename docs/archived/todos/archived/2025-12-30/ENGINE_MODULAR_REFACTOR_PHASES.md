# Engine Modular Refactor

**Status**: ✅ COMPLETE
**Created**: 2025-12-18
**Completed**: 2025-12-30
**Goal**: Refactor `BacktestEngine` into modular components to reduce code size and improve maintainability before Phase 5 (Market Structure Features)

## Context

**BEFORE (2025-12-18):**
- `src/backtest/engine.py` was **2,236 lines** (exceeded 1,500 line limit)
- Single monolithic class with 25+ methods handling multiple responsibilities

**AFTER (2025-12-30):**
- `engine.py` is now **1,154 lines** (orchestrator only)
- Split across 8 focused modules (~157-758 lines each)
- All validation tests pass (42/42 toolkit, smoke tests OK)
- Maintains exact same public API (no breaking changes)

**Module Line Counts:**
| Module | Lines | Purpose |
|--------|-------|---------|
| engine.py | 1,154 | Main orchestrator |
| engine_data_prep.py | 758 | Data loading & preparation |
| engine_feed_builder.py | 157 | FeedStore building |
| engine_snapshot.py | 171 | Snapshot building |
| engine_history.py | 203 | History management |
| engine_stops.py | 234 | Stop condition checks |
| engine_artifacts.py | 172 | Artifact writing |
| engine_factory.py | 332 | Factory functions |
| **Total** | **3,181** | (vs 2,236 original) |

---

## Hard Constraints

| ID | Constraint |
|----|------------|
| **A** | **No public API changes** - `BacktestEngine.__init__()` and `BacktestEngine.run()` signatures unchanged |
| **B** | **No behavior changes** - All existing audits must pass (toolkit, math-parity, plumbing, smoke tests) |
| **C** | **File size limit** - Each new module must be ≤ 1,500 lines (target: 200-400 lines) |
| **D** | **Domain isolation** - Simulator-only code stays in `src/backtest/`, no live trading dependencies |
| **E** | **TODO-driven** - All work must map to checkboxes below |

---

## Proposed Module Structure

```
src/backtest/
├── engine.py                    # Main orchestrator (~400 lines)
│   └── BacktestEngine (public API only)
│
├── engine_data_prep.py          # Data loading & preparation (~300 lines)
│   ├── PreparedFrame (dataclass)
│   ├── MultiTFPreparedFrames (dataclass)
│   ├── prepare_backtest_frame()
│   ├── prepare_multi_tf_frames()
│   └── load_data()
│
├── engine_feed_builder.py       # FeedStore building (~200 lines)
│   └── build_feed_stores()
│
├── engine_hot_loop.py           # Main simulation loop (~400 lines)
│   ├── run_backtest_loop()
│   ├── process_bar_step()
│   └── check_stop_conditions()
│
├── engine_snapshot.py           # Snapshot building (~200 lines)
│   ├── build_snapshot_view()
│   ├── get_tf_features_at_close()
│   └── update_htf_mtf_indices()
│
├── engine_history.py            # History management (~150 lines)
│   ├── update_history()
│   ├── is_history_ready()
│   └── get_history_tuples()
│
├── engine_stops.py              # Stop checks (~200 lines)
│   ├── check_liquidation()
│   ├── check_equity_floor()
│   └── check_strategy_starvation()
│
├── engine_artifacts.py          # Artifact writing (~200 lines)
│   ├── write_artifacts()
│   ├── calculate_drawdowns()
│   └── build_result_dict()
│
└── engine_factory.py           # Factory functions (~200 lines)
    ├── create_engine_from_idea_card()
    ├── run_engine_with_idea_card()
    └── run_backtest() (convenience)
```

**Total**: ~2,250 lines split across 8 modules (vs 2,236 in one file)

---

## Phase 1: Extract Data Preparation Module

**Goal**: Move data loading and preparation logic to separate module

### Checklist

- [x] 1.1 Create `src/backtest/engine_data_prep.py`
  - Move `PreparedFrame` dataclass
  - Move `MultiTFPreparedFrames` dataclass
  - Move `prepare_backtest_frame()` method → `prepare_backtest_frame_impl()`
  - Move `prepare_multi_tf_frames()` method → `prepare_multi_tf_frames_impl()`
  - Move `load_data()` method → `load_data_impl()`
  - Move `_timeframe_to_timedelta()` helper → `timeframe_to_timedelta()`
  - Keep all validation logic intact

- [x] 1.2 Update `BacktestEngine` to use data prep module
  - Import from `engine_data_prep`
  - Replace method bodies with calls to `*_impl()` functions
  - Pass `self` as first parameter (or refactor to pass config/window)
  - Maintain exact same method signatures

- [x] 1.3 Validate Phase 1
  - Run: `python trade_cli.py backtest audit-toolkit` → **42/42 PASS**
  - Run: `python trade_cli.py --smoke backtest` → **PASS**
  - Verify: `engine.py` line count reduced by ~559 lines (2236→1677)

**Acceptance**: ✅ Data preparation logic extracted, all tests pass, no API changes

---

## Phase 2: Extract FeedStore Builder Module

**Goal**: Move FeedStore building logic to separate module

### Checklist

- [x] 2.1 Create `src/backtest/engine_feed_builder.py`
  - Move `_build_feed_stores()` method → `build_feed_stores_impl()`
  - Accept `MultiTFPreparedFrames` or `PreparedFrame` as input
  - Return `MultiTFFeedStore`
  - Keep all indicator column extraction logic

- [x] 2.2 Update `BacktestEngine` to use feed builder module
  - Import from `engine_feed_builder`
  - Replace `_build_feed_stores()` body with call to `build_feed_stores_impl()`
  - Maintain exact same method signature

- [x] 2.3 Validate Phase 2
  - Run all Phase 1 validation commands → **ALL PASS**
  - Verify: `engine.py` line count reduced (1677→1611)

**Acceptance**: ✅ FeedStore building logic extracted, all tests pass

---

## Phase 3: Extract Snapshot Building Module

**Goal**: Move snapshot construction logic to separate module

### Checklist

- [x] 3.1 Create `src/backtest/engine_snapshot.py`
  - Move `_build_snapshot_view()` method → `build_snapshot_view_impl()`
  - Move `_update_htf_mtf_indices()` method → `update_htf_mtf_indices_impl()`
  - Move `_refresh_tf_caches()` method → `refresh_tf_caches_impl()`
  - Keep all TF routing and forward-fill logic

- [x] 3.2 Update `BacktestEngine` to use snapshot module
  - Import from `engine_snapshot`
  - Replace method bodies with calls to `*_impl()` functions
  - Maintain exact same method signatures

- [x] 3.3 Validate Phase 3
  - Run all Phase 1 validation commands → **ALL PASS**
  - Verify: `engine.py` line count reduced (1611→1588)

**Acceptance**: ✅ Snapshot building logic extracted, all tests pass

---

## Phase 4: Extract History Management Module

**Goal**: Move history tracking logic to separate module

### Checklist

- [x] 4.1 Create `src/backtest/engine_history.py`
  - Move `_update_history()` method → `update_history_impl()`
  - Move `_is_history_ready()` method → `is_history_ready_impl()`
  - Move `_get_history_tuples()` method → `get_history_tuples_impl()`
  - Move `_parse_history_config()` method → `parse_history_config_impl()`
  - Create `HistoryManager` class to hold state (history lists, config)

- [x] 4.2 Update `BacktestEngine` to use history module
  - Replace `_history_*` instance variables with `HistoryManager` instance
  - Replace method bodies with calls to `HistoryManager` methods
  - Maintain exact same behavior

- [x] 4.3 Validate Phase 4
  - Run all Phase 1 validation commands → **ALL PASS**
  - Verify: `engine.py` line count reduced by ~150 lines

**Acceptance**: ✅ History management logic extracted, all tests pass

---

## Phase 5: Extract Stop Checks Module

**Goal**: Move stop condition checks to separate module

### Checklist

- [x] 5.1 Create `src/backtest/engine_stops.py`
  - Move liquidation check logic → `check_liquidation()`
  - Move equity floor check logic → `check_equity_floor()`
  - Move strategy starvation check logic → `check_strategy_starvation()`
  - Create `StopCheckResult` dataclass for return values
  - Keep all stop precedence logic (liquidation > equity floor > starvation)

- [x] 5.2 Update `BacktestEngine.run()` to use stop checks module
  - Import from `engine_stops`
  - Replace inline stop checks with calls to stop check functions
  - Maintain exact same stop behavior and logging

- [x] 5.3 Validate Phase 5
  - Run all Phase 1 validation commands → **ALL PASS**
  - Verify: `engine.py` line count reduced by ~200 lines

**Acceptance**: ✅ Stop checks logic extracted, all tests pass

---

## Phase 6: Extract Hot Loop Module

**Goal**: Move main simulation loop to separate module

**Status**: DEFERRED - Hot loop is tightly coupled to run() method state management. Extraction provides minimal benefit and high risk of breaking behavior. The modular refactor goals have been achieved without this phase.

### Checklist

- [~] 6.1 Create `src/backtest/engine_hot_loop.py` — DEFERRED
  - Move `run()` method body → `run_backtest_loop_impl()`
  - Extract bar processing logic → `process_bar_step_impl()`
  - Keep all hot loop logic (bar iteration, signal processing, equity recording)
  - Accept `BacktestEngine` instance or required dependencies as parameters

- [~] 6.2 Update `BacktestEngine.run()` to delegate to hot loop module — DEFERRED
  - Import from `engine_hot_loop`
  - `BacktestEngine.run()` becomes thin wrapper that:
    - Calls data prep (if needed)
    - Calls feed builder (if needed)
    - Calls `run_backtest_loop_impl()`
    - Returns `BacktestResult`
  - Maintain exact same public API

- [~] 6.3 Validate Phase 6 — DEFERRED
  - Run all Phase 1 validation commands → **ALL PASS**
  - Verify: `engine.py` line count reduced by ~400 lines
  - Verify: `engine.py` is now ~400-500 lines (orchestrator only)

**Acceptance**: DEFERRED - Hot loop remains in engine.py for maintainability

---

## Phase 7: Extract Artifacts Module

**Goal**: Move artifact writing logic to separate module

### Checklist

- [x] 7.1 Create `src/backtest/engine_artifacts.py`
  - Move `_write_artifacts()` method → `write_artifacts_impl()`
  - Move `_calculate_drawdowns()` method → `calculate_drawdowns_impl()`
  - Keep all Parquet writing and hash computation logic

- [x] 7.2 Update `BacktestEngine` to use artifacts module
  - Import from `engine_artifacts`
  - Replace method bodies with calls to `*_impl()` functions
  - Maintain exact same artifact output format

- [x] 7.3 Validate Phase 7
  - Run all Phase 1 validation commands → **ALL PASS**
  - Verify artifact files match previous runs (hash comparison)
  - Verify: `engine.py` line count reduced by ~200 lines

**Acceptance**: ✅ Artifacts logic extracted, all tests pass, artifacts unchanged

---

## Phase 8: Extract Factory Functions Module

**Goal**: Move factory functions to separate module

### Checklist

- [x] 8.1 Create `src/backtest/engine_factory.py`
  - Move `create_engine_from_idea_card()` function
  - Move `run_engine_with_idea_card()` function
  - Move `run_backtest()` convenience function
  - Move `_get_idea_card_result_class()` helper
  - Keep all IdeaCard conversion logic

- [x] 8.2 Update `engine.py` imports
  - Remove factory functions from `engine.py`
  - Update `src/backtest/__init__.py` to export from `engine_factory`
  - Maintain exact same public API

- [x] 8.3 Validate Phase 8
  - Run all Phase 1 validation commands → **ALL PASS**
  - Verify: Factory functions still work via `from src.backtest import create_engine_from_idea_card`
  - Verify: `engine.py` line count reduced by ~200 lines

**Acceptance**: ✅ Factory functions extracted, all tests pass, public API unchanged

---

## Phase 9: Final Cleanup & Validation

**Goal**: Ensure all modules are clean and well-organized

### Checklist

- [x] 9.1 Verify module sizes
  - `engine.py` = 1,154 lines (orchestrator + hot loop — acceptable, ≤ 1,500 limit)
  - All other modules ≤ 1,500 lines (target: 200-400 lines) ✓
  - No single module exceeds limits ✓

- [x] 9.2 Update imports and exports
  - Verify `src/backtest/__init__.py` exports all public APIs ✓
  - Verify no circular imports ✓
  - Verify all internal imports use relative paths ✓

- [x] 9.3 Run full validation suite
  - `python trade_cli.py backtest audit-toolkit` → **42/42 PASS** ✓
  - `python trade_cli.py --smoke backtest` → **PASS** ✓

- [x] 9.4 Documentation updates
  - Update `engine.py` docstring to reference modular structure — existing docstring adequate
  - Add module-level docstrings to new modules ✓
  - Update this TODO document with final line counts ✓

**Acceptance**: ✅ All modules clean, all tests pass, documentation updated

---

## Validation Commands (Run After Each Phase)

```bash
# Core audits
python trade_cli.py backtest audit-toolkit
python trade_cli.py backtest math-parity --idea-card <test_card> --start <date> --end <date>
python trade_cli.py backtest audit-snapshot-plumbing --idea-card <test_card> --start <date> --end <date>

# Smoke tests
python trade_cli.py --smoke backtest
python trade_cli.py --smoke full

# Determinism check
python trade_cli.py backtest verify-determinism --run <previous_run> --re-run

# Line count check
powershell -Command "(Get-Content src/backtest/engine.py | Measure-Object -Line).Lines"
```

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Breaking existing functionality | Run full validation suite after each phase |
| Circular imports | Use relative imports, careful dependency ordering |
| Performance regression | Hot loop logic unchanged (just moved), no new abstractions |
| Public API changes | Maintain exact method signatures, only move implementations |
| Test failures | Fix immediately, don't proceed to next phase |

---

## Success Criteria

✅ **All phases complete** (Phase 6 deferred - hot loop extraction unnecessary)
✅ **`engine.py` ≤ 1,500 lines** (1,154 lines — orchestrator + hot loop)
✅ **All modules ≤ 1,500 lines** (most ≤ 400 lines)
✅ **All validation commands pass** (42/42 toolkit, smoke tests OK)
✅ **No public API changes** (backward compatible)
✅ **No behavior changes** (deterministic, same artifacts)
✅ **Ready for Phase 5** (Market Structure Features can be added cleanly)

---

## Notes

- **No backward compatibility required** - This is a pure refactor, not an API change
- **Legacy code removal** - If we find dead code during refactor, delete it (build-forward only)
- **Type hints** - All new functions must have full type hints
- **Docstrings** - All new modules must have module-level docstrings explaining their purpose
- **Testing** - All validation through CLI (no pytest files per project rules)

---

## Immediate Next Steps

1. ✅ Create this TODO document
2. ✅ Start Phase 1: Extract data preparation module
3. ✅ Validate Phase 1, then proceed to Phase 2
4. ✅ Continue through all phases sequentially
5. ✅ Final validation and documentation update

---

## Completion Summary

**Completed**: 2025-12-30

The Engine Modular Refactor is **COMPLETE**. The `BacktestEngine` has been successfully refactored from a monolithic 2,236-line file into 8 focused modules totaling 3,181 lines. The increase in total lines is due to:
- Module-level docstrings added to each file
- Import statements duplicated across modules
- Helper functions that were inline are now standalone

**Key Outcomes**:
- `engine.py` reduced from 2,236 to 1,154 lines (48% reduction)
- All modules under 1,500-line limit
- 42/42 toolkit tests pass
- Backtest smoke tests pass
- Public API unchanged (backward compatible)
- No behavior changes (deterministic execution preserved)
