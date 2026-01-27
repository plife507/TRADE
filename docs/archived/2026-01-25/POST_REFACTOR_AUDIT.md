# Post-Refactor Audit Summary

**Date**: 2026-01-22
**Branch**: feature/unified-engine
**Auditor**: Orchestrator Agent

---

## Executive Summary

The codebase shows significant **code duplication** between `src/indicators/` and `src/backtest/` modules, with approximately **6,000 lines** of near-identical code. Additionally, several files exceed 500 lines and could benefit from splitting. Pattern consistency with CLAUDE.md is good (no deprecated timeframe terminology found).

---

## 1. Bloated Files (>500 lines)

### Critical (>1500 lines) - High priority for split

| File | Lines | Suggested Action |
|------|-------|------------------|
| `src/utils/cli_display.py` | 2507 | Split by action domain (account, order, position, data) |
| `src/data/historical_data_store.py` | 2040 | Extract sync logic, gap detection, emoji helpers |
| `src/forge/validation/synthetic_data.py` | 2010 | Extract pattern generators to separate module |
| `src/backtest/runtime/snapshot_view.py` | 1817 | Extract TFContext, cache helpers, accessor methods |

### Large (1000-1500 lines) - Medium priority

| File | Lines | Suggested Action |
|------|-------|------------------|
| `src/tools/backtest_play_tools.py` | 1412 | Split: validation, execution, display |
| `src/engine/adapters/live.py` | 1291 | Split: order handling, position sync, websocket |
| `src/backtest/artifacts/artifact_standards.py` | 1277 | Extract validators, formatters |
| `src/backtest/execution_validation.py` | 1265 | Consider consolidation with preflight |
| `src/indicators/registry.py` | 1198 | **DELETE (duplicate)** |
| `src/backtest/indicator_registry.py` | 1198 | Keep as canonical |
| `src/backtest/runtime/preflight.py` | 1196 | Extract validation helpers |
| `src/structures/detectors/swing.py` | 1175 | Extract utility functions |
| `src/engine/play_engine.py` | 1166 | Acceptable - core engine |
| `src/tools/position_tools.py` | 1165 | Split: queries, mutations, display |
| `src/data/realtime_bootstrap.py` | 1141 | Extract feed builders |
| `src/backtest/sim/exchange.py` | 1120 | Split: order handling, position tracking |
| `src/tools/order_tools.py` | 1069 | Split: create, cancel, modify |
| `src/config/config.py` | 1060 | Extract validators, loaders |
| `src/backtest/runner.py` | 1031 | Extract gate handlers |
| `src/backtest/metrics.py` | 1030 | Extract formatters |
| `src/backtest/engine_data_prep.py` | 1015 | Extract helpers |
| `src/backtest/system_config.py` | 1009 | Extract validators |

---

## 2. Critical Duplicates (DELETE candidates)

### PRIORITY 1: Exact Duplicates (~4000 lines to remove)

These files are near-identical copies between `src/indicators/` and `src/backtest/`:

| Keep (Canonical) | Delete (Duplicate) | Lines |
|------------------|-------------------|-------|
| `src/backtest/indicator_registry.py` | `src/indicators/registry.py` | 1198 |
| `src/backtest/indicator_vendor.py` | `src/indicators/vendor.py` | 803 |
| `src/backtest/features/feature_spec.py` | `src/indicators/spec.py` | 528 |
| `src/backtest/features/feature_frame_builder.py` | `src/indicators/builder.py` | 979 |

**Total duplicate lines**: ~3500+ lines

**Action**: Keep backtest versions (they import from `..indicator_registry`), delete indicators versions, update `src/indicators/__init__.py` to re-export from backtest.

---

## 3. Dead Code Candidates

### Unused Imports (clean up)

| File | Unused Imports |
|------|---------------|
| `src/backtest/engine.py` | All imports (file is just re-exports) |
| `src/backtest/engine_factory.py` | BacktestResult, FeatureRegistry, Play, RuntimeSnapshot, RuntimeSnapshotView, Signal, SyntheticDataProvider |
| `src/backtest/engine_data_prep.py` | Protocol, SyntheticDataProvider, WindowConfig |
| `src/backtest/runner.py` | Callable, IndicatorRequirementsResult, PipelineSignature, PlaySignalEvaluator, SignalDecision, SyntheticDataProvider, extract_available_keys_from_feature_frames, json, validate_play_full |
| `src/engine/play_engine.py` | CompiledBlock, EvaluationResult, Play, SignalType, SubLoopResult, field |
| `src/engine/factory.py` | DataProvider, ExchangeAdapter, FeedStore, MultiTFIncrementalState, Play, SimulatedExchange, StateStore |

### Empty Pass Statements

| File | Count |
|------|-------|
| `src/backtest/engine_data_prep.py` | 2 |
| `src/engine/manager.py` | 2 |
| `src/engine/play_engine.py` | 1 |
| `src/engine/risk_policy.py` | 2 |
| `src/backtest/runner.py` | 1 |

---

## 4. Pattern Consistency

### Timeframe Terminology (CLAUDE.md compliance)

**GOOD**: No violations found for:
- No `htf`, `ltf`, `mtf` abbreviations in code identifiers
- No `HTF`, `LTF`, `MTF` abbreviations in code identifiers
- No deprecated `Optional[X]` or `Union[X, Y]` patterns

**NOTE**: `exec_tf` is used as a variable name (21 files) - this is acceptable per CLAUDE.md which only prohibits `exec_tf: 15m` YAML pattern (exec should be a pointer).

### LF Line Endings

10 files properly use `newline='\n'` for file writes - good coverage.

---

## 5. Quick Wins (Do First)

### Week 1: Delete Duplicates (-3500 lines)

1. **Delete `src/indicators/registry.py`** - duplicate of backtest version
2. **Delete `src/indicators/vendor.py`** - duplicate of backtest version
3. **Delete `src/indicators/spec.py`** - duplicate of backtest version
4. **Delete `src/indicators/builder.py`** - duplicate of backtest version
5. **Update `src/indicators/__init__.py`** - re-export from backtest modules

### Week 2: Clean Unused Imports

Run through files listed in Section 3 and remove unused imports.

### Week 3: Split Largest Files

1. `src/utils/cli_display.py` (2507 lines) - split into domain-specific modules
2. `src/data/historical_data_store.py` (2040 lines) - extract helpers

---

## 6. Priority Ranking for Next Phase

| Priority | Task | Impact | Effort |
|----------|------|--------|--------|
| **P0** | Delete indicator duplicates | -3500 lines | Low |
| **P1** | Clean unused imports | Clarity | Low |
| **P2** | Split cli_display.py | Maintainability | Medium |
| **P3** | Split historical_data_store.py | Maintainability | Medium |
| **P4** | Consolidate preflight/validation | DRY | High |

---

## 7. Files NOT to Touch

These files are complex but justified:

- `src/engine/play_engine.py` (1166 lines) - Core engine, splitting would hurt cohesion
- `src/backtest/indicator_registry.py` (1198 lines) - Canonical indicator definitions
- `src/structures/detectors/swing.py` (1175 lines) - Complex detection algorithm

---

## Appendix: File Size Distribution

```
>2000 lines:  3 files
1500-2000:    1 file
1000-1500:   18 files
500-1000:    ~30 files
<500 lines:  majority
```

**Total src/ lines estimated**: ~45,000 lines
**Duplicate lines to remove**: ~3,500 lines (8%)
