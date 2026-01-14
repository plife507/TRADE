# Incremental State Implementation

**Status**: COMPLETE (Validated 2026-01-03)
**Created**: 2026-01-02
**Updated**: 2026-01-03
**Design**: `docs/architecture/INCREMENTAL_STATE_ARCHITECTURE.md`
**Vision**: `docs/architecture/IDEACARD_VISION.md`

## Overview

Implement incremental state architecture for O(1) market structure access in hot loop.

## Validation IdeaCards

| Card | Purpose |
|------|---------|
| V_70_swing_basic.yml | Swing detection with variable resolution |
| V_71_fibonacci.yml | Fibonacci with swing dependency |
| V_72_zone_state.yml | Zone state machine (demand/supply) |
| V_73_trend_direction.yml | Trend classification from HH/HL |
| V_74_rolling_window.yml | O(1) rolling min/max |
| V_75_multi_tf.yml | Multi-timeframe HTF structures |

## Phase 1: Core Primitives

**Gate**: Unit tests pass for MonotonicDeque and RingBuffer

- [x] Create `src/backtest/incremental/__init__.py`
- [x] Create `src/backtest/incremental/primitives.py`
  - [x] Implement `MonotonicDeque` class
  - [x] Implement `RingBuffer` class
- [x] Create `src/backtest/incremental/test_primitives.py` (CLI validation)
  - [x] Test MonotonicDeque min mode
  - [x] Test MonotonicDeque max mode
  - [x] Test MonotonicDeque window eviction
  - [x] Test RingBuffer push/access
  - [x] Test RingBuffer wrap-around
  - [x] Test RingBuffer is_full

**Acceptance**: `python -m src.backtest.incremental.test_primitives` passes

---

## Phase 2: Base Class + Registry

**Gate**: Registry can register and retrieve structure types

- [x] Create `src/backtest/incremental/base.py`
  - [x] Implement `BarData` dataclass
  - [x] Implement `BaseIncrementalDetector` ABC
  - [x] Implement `validate_and_create()` with fail-loud errors
  - [x] Implement `get_value_safe()` with suggestions
- [x] Create `src/backtest/incremental/registry.py`
  - [x] Implement `STRUCTURE_REGISTRY` dict
  - [x] Implement `@register_structure` decorator
  - [x] Implement `get_structure_info()` for discovery
- [x] Add validation tests

**Acceptance**: Can register a dummy structure and retrieve it

---

## Phase 3: Structure Detectors

**Gate**: All 5 detectors pass parity tests against batch implementation

- [x] Create `src/backtest/incremental/detectors/__init__.py`
- [x] Create `src/backtest/incremental/detectors/swing.py`
  - [x] Implement `IncrementalSwingDetector`
  - [x] Add param validation with suggestions
- [x] Create `src/backtest/incremental/detectors/fibonacci.py`
  - [x] Implement `IncrementalFibonacci`
  - [x] Add param validation with suggestions
- [x] Create `src/backtest/incremental/detectors/zone.py`
  - [x] Implement `IncrementalZoneDetector`
  - [x] Add param validation with suggestions
- [x] Create `src/backtest/incremental/detectors/trend.py`
  - [x] Implement `IncrementalTrendDetector`
- [x] Create `src/backtest/incremental/detectors/rolling_window.py`
  - [x] Implement `IncrementalRollingWindow`
  - [x] Add param validation with suggestions
- [x] Parity tests against existing batch swing/zone

**Acceptance**: Incremental outputs match batch outputs for test data

---

## Phase 4: State Containers

**Gate**: MultiTFIncrementalState updates exec and HTF correctly

- [x] Create `src/backtest/incremental/state.py`
  - [x] Implement `TFIncrementalState`
    - [x] Build structures from specs
    - [x] Resolve dependencies in order
    - [x] Update all structures per bar
    - [x] Fail-loud on missing structure
  - [x] Implement `MultiTFIncrementalState`
    - [x] Manage exec + HTF states
    - [x] Route updates correctly
    - [x] Path-based value access
    - [x] Fail-loud on invalid paths
- [x] Integration test with multi-TF scenario

**Acceptance**: Can create state from specs, update, and read values

---

## Phase 5: IdeaCard Schema

**Gate**: Parser extracts structure specs from IdeaCard YAML

- [x] Update `src/backtest/idea_card.py`
  - [x] Add `structures` section to schema
  - [x] Parse exec structure specs
  - [x] Parse HTF structure specs
  - [x] Resolve `{{ variable }}` references in params
  - [x] Validate structure types exist in registry
  - [x] Validate depends_on references
- [x] Create validation IdeaCard with structures
- [x] Test normalization catches errors

**Acceptance**: `backtest normalize` validates structure blocks

---

## Phase 6: Engine Integration

**Gate**: Backtest runs with incremental state, results unchanged

- [x] Update `src/backtest/engine.py`
  - [x] Add `_build_incremental()` method
  - [x] Build `BarData` in hot loop
  - [x] Call `update_exec()` every bar
  - [x] Call `update_htf()` on HTF close
  - [x] Pass incremental to snapshot builder
- [x] Update `src/backtest/runtime/snapshot_view.py`
  - [x] Add `get_structure(path)` method
  - [x] Add `bars_exec_low(n)` using incremental
  - [x] Add `bars_exec_high(n)` using incremental
  - [x] Fail-loud with suggestions on missing
- [x] Run existing IdeaCards, verify metrics unchanged

**Acceptance**: Validation IdeaCards produce identical results

---

## Phase 7: Deprecate Batch Code (Transition Phase)

**Gate**: Batch code deprecated with clear migration path

**Strategy**: Conditional with deprecation warnings (not full removal yet)
- Incremental state is preferred when `structures:` section is present
- Batch system still works for `market_structure_blocks` (deprecated)
- Clear migration path documented

- [x] Add deprecation warning to `build_structures_into_feed()` function
- [x] Skip batch build when IdeaCard uses `structures:` section
- [x] Update `_resolve_structure_path()` with clear documentation
- [x] Keep `FeedStore.structures` field for backward compatibility
- [x] Full smoke test to verify no breaks

**Acceptance**: Both paths work, deprecation warnings shown for legacy path

**Future Phase 7b**: Full removal (when no IdeaCards use market_structure_blocks)
- Delete `build_structures_into_feed()` function
- Delete `FeedStore.structures` and `structure_key_map` fields
- Remove fallback code in `_resolve_structure_path()`

---

## Phase 8: Validation + Docs

**Gate**: Documentation complete, CLI help updated

- [x] Add validation IdeaCards to `strategies/idea_cards/_validation/`
  - [x] `V_70_swing_basic.yml` - swing detection
  - [x] `V_71_fibonacci.yml` - fib levels
  - [x] `V_72_zone_state.yml` - zone state machine
  - [x] `V_73_trend_direction.yml` - trend classification
  - [x] `V_74_rolling_window.yml` - rolling min/max
  - [x] `V_75_multi_tf.yml` - HTF structure updates
- [x] Update `CLAUDE.md` with structure registry info
- [x] Update `docs/architecture/` index
- [ ] Add CLI help for structure-related commands (deferred - not needed for current usage)

**Acceptance**: All validation cards pass, docs updated

---

## Completion Criteria

- [x] All 8 phases complete (Phase 8 finalized 2026-01-03)
- [x] `--smoke full` passes (normalization validated)
- [x] Validation IdeaCards pass (9/9 cards normalized)
- [x] No O(n) operations in hot loop
- [x] Design docs match implementation

**Implementation Complete**: 2026-01-03
