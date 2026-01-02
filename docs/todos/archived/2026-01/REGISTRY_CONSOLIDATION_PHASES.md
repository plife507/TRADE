# Registry Consolidation: String-Based Indicator Types

**Status**: Phases 0-2 ✅ COMPLETE | Phase 3 ✅ SUPERSEDED (market_structure module)
**Created**: 2025-12-30
**Updated**: 2025-12-31
**Goal**: Consolidate dual indicator type systems into a single registry-driven architecture to enable extensible market structure features without hardcoding

---

## Context

**Prerequisite for**: Phase 5 (Market Structure Features) in `ARRAY_BACKED_HOT_LOOP_PHASES.md`

**Triggered by**: Code review finding that adding new indicator types requires editing 4+ files

**Related Documents**:
- `docs/todos/ARRAY_BACKED_HOT_LOOP_PHASES.md` — Phase 5 blocked until this is resolved
- `docs/todos/MARKET_STRUCTURE_INTEGRATION_REVIEW.md` — Original review prompt
- `docs/reviews/MARKET_STRUCTURE_INTEGRATION_REVIEW_FINDINGS.md` — Detailed findings

---

## Problem Statement

### Current State: Dual System with Duplication

The codebase has **two parallel systems** for defining indicator types:

| System | Location | Type | Maintenance |
|--------|----------|------|-------------|
| `IndicatorType` enum | `feature_spec.py:25-230` | Hardcoded 150+ entries | Edit Python file |
| `MULTI_OUTPUT_KEYS` dict | `feature_spec.py:235-293` | Hardcoded 50+ entries | Edit Python file |
| `SUPPORTED_INDICATORS` dict | `indicator_registry.py:54-304` | Data-driven | Edit dict only |
| Warmup switch statement | `feature_spec.py:477-510` | Hardcoded if/elif | Edit Python file |

### Adding a New Indicator Type Requires

1. Add to `IndicatorType` enum (hardcoded)
2. Add to `MULTI_OUTPUT_KEYS` dict (hardcoded)
3. Add to `SUPPORTED_INDICATORS` dict (data-driven)
4. Add warmup case to `FeatureSpec.warmup_bars` (hardcoded switch)
5. Potentially add to `indicator_vendor.py` compute function

**Total: 4-5 files to edit for a single new indicator type**

### Why This Blocks Phase 5 (Market Structure)

Market structure features (swing detection, pivot identification, trend classification) need:
- New indicator types that don't exist in pandas_ta
- Custom warmup formulas
- Sparse output handling (forward-fill)
- Custom compute functions

With the current architecture, this requires modifying hardcoded enums and switch statements, violating the "build-forward only" principle.

---

## Proposed Solution: Registry as Single Source of Truth

### Target State

```python
# indicator_registry.py — ONLY place to add new indicators

SUPPORTED_INDICATORS = {
    # Existing indicators (unchanged)
    "ema": {
        "inputs": {"close"},
        "params": {"length"},
        "multi_output": False,
        "warmup_formula": lambda p: p.get("length", 20) * 3,
    },
    "macd": {
        "inputs": {"close"},
        "params": {"fast", "slow", "signal"},
        "multi_output": True,
        "output_keys": ("macd", "signal", "histogram"),
        "warmup_formula": lambda p: p.get("slow", 26) * 3 + p.get("signal", 9),
    },

    # NEW: Market structure — just add to dict!
    "swing": {
        "inputs": {"high", "low", "close"},
        "params": {"lookback", "confirmation"},
        "multi_output": True,
        "output_keys": ("high", "high_idx", "low", "low_idx"),
        "warmup_formula": lambda p: p.get("lookback", 20) + p.get("confirmation", 3),
        "sparse": True,                    # NEW: Forward-fill required
        "compute_fn": "compute_swing",     # NEW: Custom compute function
    },
}
```

### Benefits

| Aspect | Before (Enum) | After (String + Registry) |
|--------|---------------|---------------------------|
| Adding new indicator | Edit 4-5 files | Edit 1 dict entry |
| Type safety | Compile-time enum | Runtime validation (fail-fast) |
| YAML parsing | Enum conversion needed | Direct string use |
| Warmup calculation | Hardcoded switch | Registry formula lookup |
| Multi-output keys | Hardcoded dict | Registry `output_keys` |
| Custom compute | Not supported | Registry `compute_fn` |
| Sparse features | Not supported | Registry `sparse` flag |

---

## Hard Constraints

| ID | Constraint |
|----|------------|
| **A** | **No public API changes** — `FeatureSpec` creation from YAML must work identically |
| **B** | **No behavior changes** — All existing audits must pass (42/42 toolkit, math-parity, smoke tests) |
| **C** | **Fail-fast validation** — Invalid indicator types raise `ValueError` immediately |
| **D** | **TODO-driven** — All work must map to checkboxes below |
| **E** | **Registry owns all metadata** — No duplicate definitions in multiple files |

---

## Phase 0: Registry Extension (Foundation) ✅ COMPLETE

**Goal**: Extend `IndicatorRegistry` with warmup formulas and new fields without breaking existing code

**Estimated Changes**: ~150 lines in `indicator_registry.py`
**Completed**: 2025-12-31

### Checklist

- [x] 0.1 Add `warmup_formula` field to `SUPPORTED_INDICATORS` entries
  - Lambda that takes params dict, returns warmup bars
  - Default formula: `lambda p: p.get("length", 0)`
  - Specific formulas for EMA (3x length), MACD (slow*3 + signal), etc.
  - File: `indicator_registry.py`

- [x] 0.2 Add `sparse` and `compute_fn` fields to `SUPPORTED_INDICATORS`
  - `sparse: bool = False` — Whether feature needs forward-fill
  - `compute_fn: Optional[str] = None` — Custom compute function name (for non-pandas_ta indicators)
  - File: `indicator_registry.py`

- [x] 0.3 Update `IndicatorInfo` dataclass with new fields
  ```python
  @dataclass(frozen=True)
  class IndicatorInfo:
      name: str
      input_series: FrozenSet[str]
      accepted_params: FrozenSet[str]
      is_multi_output: bool
      output_keys: Tuple[str, ...]
      primary_output: Optional[str]
      # NEW fields:
      warmup_formula: Optional[Callable[[Dict], int]] = None
      sparse: bool = False
      compute_fn: Optional[str] = None
  ```
  - File: `indicator_registry.py`

- [x] 0.4 Add registry method `get_warmup_bars(indicator_type, params)`
  ```python
  def get_warmup_bars(self, indicator_type: str, params: Dict[str, Any]) -> int:
      info = self.get_indicator_info(indicator_type)
      if info.warmup_formula:
          return info.warmup_formula(params)
      return params.get("length", 0)
  ```
  - File: `indicator_registry.py`

- [x] 0.5 Validate Phase 0
  - Run: `python trade_cli.py backtest audit-toolkit` → 42/42 PASS ✅
  - Run: `python trade_cli.py --smoke backtest` → PASS ✅
  - Verify: No behavior changes (registry extension only) ✅

**Acceptance**: Registry extended with new fields, all tests pass, no API changes ✅

---

## Phase 1: String-Based Indicator Types ✅ COMPLETE

**Goal**: Change `FeatureSpec.indicator_type` from enum to string with registry validation

**Estimated Changes**: ~200 lines across `feature_spec.py`, `feature_frame_builder.py`
**Completed**: 2025-12-31

### Checklist

- [x] 1.1 Change `FeatureSpec.indicator_type` type annotation
  - Changed to `indicator_type: str`
  - Updated `__post_init__` to validate against registry
  - File: `feature_spec.py`

- [x] 1.2 Update `FeatureSpec.warmup_bars` property
  - Now uses `registry.get_warmup_bars(self.indicator_type.lower(), self.params)`
  - File: `feature_spec.py`

- [x] 1.3 Update `FeatureSpec.output_keys_list` property
  - Now uses `is_multi_output()` and `get_output_names()` which delegate to registry
  - File: `feature_spec.py`

- [x] 1.4 YAML parsing already works (string passthrough)
  - FeatureSpec always accepted strings, now validates via registry
  - File: `idea_card_yaml_builder.py`

- [x] 1.5 Update `FeatureFrameBuilder` to use string type
  - Removed `_normalize_type()` method
  - All methods now take `str` directly
  - File: `feature_frame_builder.py`

- [x] 1.6 Update all test/example code
  - Updated `smoke_tests.py` to use strings
  - File: `smoke_tests.py`

- [x] 1.7 Validate Phase 1
  - Run: `python trade_cli.py backtest audit-toolkit` → 42/42 PASS ✅
  - Run: `python trade_cli.py --smoke backtest` → PASS ✅

**Acceptance**: `FeatureSpec.indicator_type` is string, registry owns all metadata, all tests pass ✅

---

## Phase 2: Delete Deprecated Code ✅ COMPLETE

**Goal**: Remove hardcoded `IndicatorType` enum and `MULTI_OUTPUT_KEYS` dict

**Estimated Changes**: -250 lines (deletion)
**Actual Changes**: -349 lines (468 lines now vs 817 before)
**Completed**: 2025-12-31

### Checklist

- [x] 2.1 Delete `IndicatorType` enum from `feature_spec.py`
  - Deleted 205+ lines of enum definitions
  - File: `feature_spec.py`

- [x] 2.2 Delete `MULTI_OUTPUT_KEYS` dict from `feature_spec.py`
  - Deleted 58+ lines of dict definitions
  - `is_multi_output()` and `get_output_names()` now delegate to registry
  - File: `feature_spec.py`

- [x] 2.3 Warmup now handled by registry
  - No switch statement to delete (was already handled in Phase 1)
  - `warmup_bars` property uses `registry.get_warmup_bars()`
  - File: `feature_spec.py`

- [x] 2.4 Update imports across codebase
  - `indicators.py`: Now imports `get_registry` instead of `MULTI_OUTPUT_KEYS, IndicatorType`
  - `feature_frame_builder.py`: Removed `IndicatorType` from imports
  - `execution_validation.py`: Removed unused import
  - `smoke_tests.py`: Removed `IndicatorType` import
  - `features/__init__.py`: Removed `IndicatorType` and `MULTI_OUTPUT_KEYS` exports
  - `README.md`: Updated documentation
  - Files: Multiple

- [x] 2.5 Validate Phase 2
  - Run: `python trade_cli.py backtest audit-toolkit` → 42/42 PASS ✅
  - Run: `python trade_cli.py --smoke backtest` → PASS (4 trades, +$873.90) ✅
  - `feature_spec.py` reduced from 817 to 468 lines (-349 lines) ✅

**Acceptance**: Deprecated code deleted, single source of truth in registry ✅

---

## Phase 3: Add Market Structure Indicators (SUPERSEDED)

**Status**: ✅ **SUPERSEDED** — Different architecture chosen

**Original Goal**: Add swing, pivot, trend indicators to indicator_registry.py

**Architectural Decision (2026-01-01)**:
Market structure is implemented as a **separate module** (`src/backtest/market_structure/`)
with its own registry (`STRUCTURE_REGISTRY`), rather than adding to the indicator registry.

**Rationale:**
- Complex state machines (zones: NONE → ACTIVE → BROKEN)
- Confirmation gates (pending → confirmed/failed)
- Parent-child relationships (zones are children of swing blocks)
- Different warmup semantics than indicators
- Separate namespace in IdeaCard (`market_structure_blocks:` vs `features:`)

**See**: `docs/todos/MARKET_STRUCTURE_PHASES.md` for detailed implementation.

**Completed Implementation:**
- ✅ `src/backtest/market_structure/` module with:
  - `STRUCTURE_REGISTRY` for detector registration
  - `SwingDetector`, `TrendDetector` batch computation
  - `ZoneDetector` for demand/supply zones
  - `StructureBuilder` orchestrating computation
- ✅ Exposed via `snapshot.get("structure.<key>.<field>")`
- ✅ Rule evaluation with compiled refs

**Note**: Indicators (42 types) and structures (swing, trend, zones) remain separate
registries with different semantics. This is intentional, not technical debt

---

## Validation Commands (Run After Each Phase)

```bash
# Core audits
python trade_cli.py backtest audit-toolkit
python trade_cli.py backtest math-parity --idea-card verify_ema_atr --start "2025-12-01" --end "2025-12-14"
python trade_cli.py backtest audit-snapshot-plumbing --idea-card verify_ema_atr --start "2025-12-01" --end "2025-12-14"

# Smoke tests
python trade_cli.py --smoke backtest
python trade_cli.py --smoke full

# Line count check (feature_spec.py should shrink by ~300 lines after Phase 2)
powershell -Command "(Get-Content src/backtest/features/feature_spec.py | Measure-Object -Line).Lines"
```

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Breaking YAML parsing | Phase 1.4 ensures string passthrough works |
| Breaking existing backtests | All audits run after each phase |
| Circular import issues | Registry imports are deferred (inside functions) |
| Performance regression | No new abstractions in hot loop |
| Missing warmup formulas | Default formula returns `length` param |

---

## Success Criteria

- [ ] `feature_spec.py` reduced by ~300 lines (enum + dict + switch deleted)
- [ ] All indicator metadata in single `SUPPORTED_INDICATORS` dict
- [ ] Adding new indicator = 1 dict entry (no enum/switch edits)
- [ ] All existing audits pass (42/42 toolkit, math-parity, smoke)
- [ ] Market structure indicators registerable without hardcoding
- [ ] Phase 5 (Market Structure) unblocked

---

## Connection to Existing TODOs

### Relationship to Array-Backed Hot Loop Phases

| Hot Loop Phase | Status | Dependency on Registry Consolidation |
|----------------|--------|--------------------------------------|
| Phase 1-4 | ✅ Complete | None (already done) |
| **Phase 5** | 🔴 BLOCKED | **Requires this TODO to complete first** |

**Unblock Path**:
1. Complete Registry Consolidation Phases 0-2
2. Phase 5 (Market Structure) becomes READY
3. Complete Registry Consolidation Phase 3 (adds structure indicators)

### Relationship to Engine Modular Refactor

The Engine Modular Refactor (✅ COMPLETE) prepared the codebase for this work:
- `engine_data_prep.py` already uses `apply_feature_spec_indicators()`
- `engine_feed_builder.py` already uses `FeatureFrameBuilder`
- No changes needed to engine modules

### Relationship to Preflight Backfill Phases

The Preflight system (✅ COMPLETE) correctly computes warmup from `FeatureSpec.warmup_bars`. After this refactor:
- `FeatureSpec.warmup_bars` uses `registry.get_warmup_bars()` internally
- Preflight continues to work unchanged (same public API)

---

## Notes

- **No backward compatibility required** — Build-forward only per project rules
- **Legacy code removal** — Delete enum/dict after string-based approach works
- **Type hints** — All new functions must have full type hints
- **Docstrings** — All new modules must have module-level docstrings
- **Testing** — All validation through CLI (no pytest files per project rules)

---

## Immediate Next Steps

1. [ ] Create this TODO document ✅
2. [ ] Review and approve approach
3. [ ] Start Phase 0: Registry Extension
4. [ ] Validate Phase 0, then proceed to Phase 1
5. [ ] Continue through all phases sequentially
6. [ ] Update `ARRAY_BACKED_HOT_LOOP_PHASES.md` Phase 5 status to UNBLOCKED
