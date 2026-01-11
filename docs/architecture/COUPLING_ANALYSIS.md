# Backtest Simulator Coupling Analysis

> Generated: 2026-01-11
> Purpose: Identify coupling patterns, circular dependencies, and cohesion issues

## Overview

This document analyzes coupling between modules in `src/backtest/` to identify:
- Circular dependencies
- High coupling (modules with many dependencies)
- Low cohesion (modules doing unrelated things)
- Inappropriate intimacy (modules reaching into each other's internals)

---

## Coupling Metrics

### Module Dependency Counts

| Module | Afferent (Used By) | Efferent (Uses) | Instability |
|--------|-------------------|-----------------|-------------|
| runtime/types.py | 25+ | 0 | 0.00 |
| sim/types.py | 20+ | 2 | 0.09 |
| rules/dsl_nodes/constants.py | 15+ | 0 | 0.00 |
| runtime/feed_store.py | 15+ | 2 | 0.12 |
| incremental/primitives.py | 8+ | 0 | 0.00 |
| runtime/snapshot_view.py | 10+ | 5 | 0.33 |
| sim/exchange.py | 5+ | 10 | 0.67 |
| engine.py | 3 | 17 | 0.85 |
| bar_processor.py | 1 | 9 | 0.90 |
| runner.py | 1 | 10 | 0.91 |

*Instability = Efferent / (Afferent + Efferent)*
- 0.0 = Maximally stable (many depend on it)
- 1.0 = Maximally unstable (depends on many)

### Interpretation

**Stable modules (low instability)**: Foundation types that should rarely change
- runtime/types.py, sim/types.py, incremental/primitives.py

**Unstable modules (high instability)**: Entry points that change frequently
- engine.py, runner.py, bar_processor.py (expected - they orchestrate)

---

## Circular Dependencies

### Identified Circular Dependencies

| Cycle | Severity | Resolution | Status |
|-------|----------|------------|--------|
| engine.py ↔ engine_factory.py | Medium | Dynamic imports in factory | Resolved |
| compile.py → market_structure → ??? | Low | Lazy import in compile.py | Resolved |
| feature_spec.py → indicator_registry | Low | Deferred import in __post_init__ | Resolved |

### Potential Future Cycles

| Risk | Description | Mitigation |
|------|-------------|------------|
| snapshot_view ↔ feature_registry | snapshot_view TYPE_CHECKING imports feature_registry | Keep TYPE_CHECKING |
| engine ↔ execution_validation | Both reference Play evaluation | Interface extraction |

---

## High Coupling Modules

### engine.py (17 internal imports)
**Severity**: High (but acceptable for orchestrator)

**Imports from**:
- engine_data_prep, engine_feed_builder, engine_snapshot
- engine_history, engine_stops, engine_artifacts
- bar_processor, types, runtime/*, sim/*
- rules/, incremental/, rationalization/
- core/risk_manager, data/historical_data_store

**Assessment**: As the main orchestrator, engine.py naturally has many dependencies. The extraction of helpers (engine_data_prep, engine_feed_builder, etc.) is good but could go further.

**Recommendation**: Consider breaking into smaller orchestrators (DataOrchestrator, SimOrchestrator).

---

### runtime/snapshot_view.py (1750 lines)
**Severity**: High

**Responsibilities**:
1. Price accessors (mark_price, last_price, close)
2. Indicator accessors
3. Feature lookup (Feature Registry integration)
4. Structure lookup (both incremental and FeedStore)
5. Namespace dispatch (price.*, indicator.*, structure.*, feature.*)
6. TFContext management

**Assessment**: This module does too much. The dispatch table pattern is good but the file is too large.

**Recommendation**: Split into:
- `snapshot_view.py` - Core view class
- `snapshot_accessors.py` - Price/indicator accessors
- `snapshot_resolver.py` - Namespace dispatch logic

---

### sim/exchange.py (1067 lines)
**Severity**: Medium

**Responsibilities**:
1. Order management (submit, cancel, amend)
2. Position tracking
3. Bar processing
4. PnL calculation
5. Liquidation coordination
6. Model orchestration (pricing, execution, funding, liquidation)

**Assessment**: Well-structured as thin orchestrator over modular components. Size is acceptable.

---

## God Objects / Classes

### RuntimeSnapshotView
**Lines**: 1750
**Methods**: 40+
**Issue**: Does too much - accessors, resolvers, context management

**Recommendation**: Extract resolver logic to separate module.

### BacktestEngine
**Lines**: 1618
**Methods**: 30+
**Issue**: Orchestration + data prep + result building

**Assessment**: Acceptable after helper extraction. Further splitting may fragment logic.

---

## Cross-Layer Dependencies

### Expected Layers (top to bottom)
```
Layer 1: Entry Points      [runner.py]
Layer 2: Orchestration     [engine.py, engine_factory.py, bar_processor.py]
Layer 3: Rules             [rules/]
Layer 4: Runtime           [runtime/, features/, incremental/]
Layer 5: Simulation        [sim/]
Layer 6: Foundation        [types.py, primitives]
Layer 7: External          [artifacts/, gates/] (isolated)
```

### Violations Found

| Violation | Type | Severity | Status |
|-----------|------|----------|--------|
| engine.py → core/risk_manager | Cross-domain import | Low | Acceptable (Signal type) |
| engine.py → data/historical_store | Cross-domain import | Low | Acceptable (data loading) |
| bar_processor → TF_MINUTES | Reaches into data module | Low | Could use runtime wrapper |

### Layer Integrity Score

| Layer | Dependencies Down | Dependencies Up | Score |
|-------|------------------|-----------------|-------|
| Entry Points | 5 | 0 | A (correct) |
| Orchestration | 15 | 2 | B (minor issues) |
| Rules | 5 | 0 | A (correct) |
| Runtime | 8 | 0 | A (correct) |
| Simulation | 5 | 0 | A (correct) |
| Foundation | 0 | 0 | A (correct) |
| External | 3 | 0 | A (correct) |

---

## Cohesion Analysis

### High Cohesion (Good)

| Module | Cohesion | Notes |
|--------|----------|-------|
| sim/ledger.py | High | Single responsibility: USDT accounting |
| sim/types.py | High | Type definitions only |
| runtime/types.py | High | Type definitions only |
| incremental/primitives.py | High | Data structure implementations |
| rules/dsl_nodes/*.py | High | Each file handles one node type |

### Low Cohesion (Concerns)

| Module | Cohesion | Issue | Recommendation |
|--------|----------|-------|----------------|
| runtime/snapshot_view.py | Low | Multiple responsibilities | Split into focused modules |
| engine.py | Medium | Orchestration + prep | Already extracted helpers |

---

## Inappropriate Intimacy

### Identified Cases

| Module A | Module B | Issue | Severity |
|----------|----------|-------|----------|
| compile.py | market_structure | Lazy imports structure fields | Low |
| snapshot_view.py | feature_registry | TYPE_CHECKING import | Low |

### Assessment

The codebase handles intimacy well through:
1. TYPE_CHECKING imports for type hints
2. Lazy imports for runtime resolution
3. Interface-based access (snapshot.get() instead of direct field access)

---

## Recommendations

### Priority 1: Split RuntimeSnapshotView

**Why**: 1750 lines with multiple responsibilities
**How**: Extract resolver logic to `snapshot_resolver.py`
**Impact**: Improved testability, clearer responsibility

### Priority 2: Reduce engine.py Import Count

**Why**: 17 imports creates maintenance burden
**How**: Create internal `_engine_imports.py` that bundles related imports
**Impact**: Cleaner import section, easier to track dependencies

### Priority 3: Formalize Layer Boundaries

**Why**: Prevent future cross-layer violations
**How**: Add CLAUDE.md sections defining layer boundaries
**Impact**: Clear guidance for future development

### Priority 4: Document Circular Dependency Patterns

**Why**: Ensure consistency in resolution approach
**How**: Create `docs/architecture/CIRCULAR_DEP_PATTERNS.md`
**Impact**: Prevent ad-hoc solutions

---

## Summary

### Strengths

1. **Clean foundation layer**: runtime/types.py, sim/types.py have 0 internal deps
2. **Good modularization**: sim/ split into focused submodules
3. **Proper isolation**: artifacts/, gates/ correctly isolated from engine
4. **Registry pattern**: Single source of truth for indicators/features

### Weaknesses

1. **snapshot_view.py too large**: 1750 lines, multiple responsibilities
2. **engine.py import count**: 17 internal imports (acceptable for orchestrator)
3. **Minor cross-domain imports**: Signal type from core/, data loading from data/

### Overall Assessment

The codebase has **good architecture** with clear layering and minimal circular dependencies. The main concern is the size of snapshot_view.py which should be split for maintainability.

**Coupling Score**: B+ (Good, minor improvements possible)
