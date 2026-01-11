# Backtest Simulator Refactor Targets

> Generated: 2026-01-11
> Purpose: Identify refactoring opportunities based on dependency analysis

## Overview

This document lists refactoring opportunities identified during the dependency review. The backtest simulator codebase is well-structured overall, with clear layering and minimal circular dependencies. The refactoring targets identified are improvements rather than critical fixes.

---

## Priority 1: Critical (Blocking Issues)

**No critical issues identified.**

The codebase has no blocking architectural problems. All circular dependencies are resolved through appropriate patterns (dynamic imports, TYPE_CHECKING, lazy loading).

---

## Priority 2: High (Significant Improvement)

### R2.1: Split RuntimeSnapshotView

**Location**: `src/backtest/runtime/snapshot_view.py`
**Lines**: 1750
**Issue**: Multiple responsibilities in single file

**Current State**:
- Price accessors (mark_price, last_price, close)
- Indicator accessors
- Feature lookup (Feature Registry integration)
- Structure lookup (both incremental and FeedStore)
- Namespace dispatch (price.*, indicator.*, structure.*, feature.*)
- TFContext management

**Proposed Split**:
```
runtime/
├── snapshot_view.py          # Core RuntimeSnapshotView class (~500 lines)
├── snapshot_accessors.py     # Price/indicator accessor methods (~400 lines)
├── snapshot_resolver.py      # Namespace dispatch logic (~600 lines)
└── tf_context.py             # TFContext class (~250 lines)
```

**Benefits**:
- Improved testability (can test resolver logic independently)
- Clearer responsibility boundaries
- Easier to understand and maintain

**Estimated Effort**: 2-3 days
**Risk**: Medium (changes affect many modules that use snapshot)

---

### R2.2: Consolidate Engine Helper Imports

**Location**: `src/backtest/engine.py`
**Issue**: 17 internal imports spread across file header

**Current State**:
```python
from .engine_data_prep import ...  # 6 imports
from .engine_feed_builder import ...  # 6 imports
from .runtime.funding_scheduler import ...
from .engine_snapshot import ...  # 3 imports
from .engine_history import ...  # 3 imports
from .engine_stops import ...  # 3 imports
from .engine_artifacts import ...  # 2 imports
from .bar_processor import ...
from .engine_factory import ...  # 3 imports
# ... many more
```

**Proposed Solution**:
Create `_engine_deps.py` that bundles related imports:
```python
# engine.py
from ._engine_deps import (
    # Data prep
    PreparedFrame, MultiTFPreparedFrames, prepare_backtest_frame_impl,
    # Feed building
    build_feed_stores_impl, build_quote_feed_impl,
    # ... etc
)
```

**Benefits**:
- Cleaner import section
- Easier to track dependencies
- Single place to update if helper APIs change

**Estimated Effort**: 0.5 days
**Risk**: Low (purely organizational)

---

## Priority 3: Medium (Code Quality)

### R3.1: Extract TF_MINUTES to runtime/

**Location**: `src/data/historical_data_store.py` -> `src/backtest/runtime/timeframe.py`
**Issue**: bar_processor.py imports TF_MINUTES from data module

**Current State**:
```python
# bar_processor.py
from ..data.historical_data_store import TF_MINUTES
```

**Proposed Solution**:
Move TF_MINUTES constant to `runtime/timeframe.py` where other TF utilities live.
Update data module to import from runtime (or duplicate if needed for isolation).

**Benefits**:
- Removes cross-domain dependency
- Keeps timeframe logic in one place

**Estimated Effort**: 0.5 days
**Risk**: Low

---

### R3.2: Standardize Circular Dependency Resolution

**Issue**: Three different patterns used for circular dependencies

**Current Patterns**:
1. Dynamic imports in engine_factory.py
2. TYPE_CHECKING imports in snapshot_view.py
3. Lazy imports with global caching in compile.py

**Proposed Standard**:
Document and standardize on TYPE_CHECKING for type hints, lazy imports for runtime resolution.
Create `docs/architecture/CIRCULAR_DEP_PATTERNS.md` with guidelines.

**Benefits**:
- Consistent approach across codebase
- Easier for new contributors to follow patterns

**Estimated Effort**: 0.5 days
**Risk**: Low

---

### R3.3: Add Layer Boundary Documentation

**Issue**: Layer boundaries are implicit, not documented

**Proposed Solution**:
Add to `src/backtest/CLAUDE.md`:
```markdown
## Layer Boundaries

| Layer | Modules | May Import From |
|-------|---------|-----------------|
| Entry | runner.py | All |
| Orchestration | engine.py, bar_processor.py | Rules, Runtime, Sim |
| Rules | rules/* | Runtime, Foundation |
| Runtime | runtime/*, features/* | Foundation |
| Simulation | sim/* | Foundation |
| Foundation | types.py, primitives | None |
| External | artifacts/, gates/ | All (isolated consumers) |
```

**Benefits**:
- Clear guidance for future development
- Prevents accidental layer violations

**Estimated Effort**: 0.5 days
**Risk**: None

---

## Priority 4: Low (Nice to Have)

### R4.1: Extract Engine Data Orchestration

**Location**: `src/backtest/engine.py`
**Issue**: Data preparation logic mixed with main orchestration

**Proposed Solution**:
Create `engine_orchestration.py` that separates:
- Data loading and preparation
- Frame building
- Feed store construction

Keep `engine.py` focused on the main run() loop.

**Benefits**:
- Clearer separation of concerns
- Easier testing of data preparation

**Estimated Effort**: 1-2 days
**Risk**: Medium

---

### R4.2: Consolidate Type Re-exports

**Issue**: Multiple modules re-export Bar type

**Current State**:
- `backtest/types.py` re-exports Bar from `runtime/types.py`
- `sim/types.py` re-exports Bar from `runtime/types.py`

**Proposed Solution**:
Keep single re-export location. Document canonical import path.

**Benefits**:
- Clearer import paths
- Reduced confusion

**Estimated Effort**: 0.25 days
**Risk**: Low

---

## Proposed Module Boundaries

Based on dependency analysis, the following module boundaries are confirmed as correct:

### Domain Boundaries (Correct)

```
src/backtest/
├── Entry Layer        [runner.py]
├── Orchestration      [engine.py, engine_factory.py, bar_processor.py]
│                      [engine_*.py helpers]
├── Rules              [rules/]
├── Runtime            [runtime/, features/]
├── Incremental        [incremental/]
├── Simulation         [sim/]
├── Play Config        [play/]
├── Foundation         [types.py, system_config.py]
└── External (isolated)[artifacts/, gates/]
```

### Cross-Domain Dependencies (Acceptable)

| Dependency | Reason | Status |
|------------|--------|--------|
| engine.py -> core/risk_manager | Signal type for strategy | OK |
| engine.py -> data/historical_store | Data loading | OK |
| runner.py -> data/historical_store | Data loader callback | OK |

---

## Breaking Changes Required

**None required for identified refactors.**

All proposed changes maintain backward compatibility:
- R2.1 (Split snapshot_view): Re-export from original module
- R2.2 (Consolidate imports): Internal organization only
- R3.* : Documentation and minor moves

---

## Migration Strategy

### For R2.1 (Split RuntimeSnapshotView)

1. Create new files with extracted code
2. Import and re-export from original snapshot_view.py
3. Update internal imports gradually
4. Run validation suite after each step

### For R2.2 (Consolidate Imports)

1. Create _engine_deps.py with all imports
2. Update engine.py to import from bundle
3. Verify no functional changes
4. Commit as single atomic change

### General Guidelines

- **Run validation after each refactor**: `python trade_cli.py --smoke full`
- **One refactor at a time**: Don't combine multiple changes
- **Keep backward compatibility**: Re-export from original locations

---

## Summary

| Priority | ID | Title | Effort | Risk |
|----------|-----|-------|--------|------|
| P1 | - | No critical issues | - | - |
| P2 | R2.1 | Split RuntimeSnapshotView | 2-3 days | Medium |
| P2 | R2.2 | Consolidate Engine Imports | 0.5 days | Low |
| P3 | R3.1 | Extract TF_MINUTES | 0.5 days | Low |
| P3 | R3.2 | Standardize Circular Deps | 0.5 days | Low |
| P3 | R3.3 | Layer Boundary Docs | 0.5 days | None |
| P4 | R4.1 | Extract Engine Data Orch | 1-2 days | Medium |
| P4 | R4.2 | Consolidate Type Re-exports | 0.25 days | Low |

**Total Estimated Effort**: 5-8 days
**Recommended First Action**: R2.2 (low risk, high visibility improvement)
