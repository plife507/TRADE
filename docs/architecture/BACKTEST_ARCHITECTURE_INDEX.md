# Backtest Simulator Architecture Review

> **Review Date**: 2026-01-11
> **Scope**: `src/backtest/` - 155 Python files across 29 subdirectories
> **Architecture Grade**: B+ (Good)

---

## Quick Navigation

| Document | Purpose | Key Content |
|----------|---------|-------------|
| [DEPENDENCY_MAP.md](./DEPENDENCY_MAP.md) | File-by-file imports | All imports, public APIs, module relationships |
| [CALL_GRAPHS.md](./CALL_GRAPHS.md) | Function call chains | Execution flows, component diagrams |
| [COUPLING_ANALYSIS.md](./COUPLING_ANALYSIS.md) | Coupling patterns | Circular deps, tight coupling, hidden deps |
| [REFACTOR_TARGETS.md](./REFACTOR_TARGETS.md) | Refactor opportunities | Prioritized improvements, effort estimates |
| [LEGACY_AUDIT.md](./LEGACY_AUDIT.md) | Legacy code findings | **27+ shims, 2 deprecated modules still present** |

---

## Executive Summary

### Architecture Strengths

- **Clean layer separation**: Entry → Orchestration → Rules → Runtime → Sim → Foundation
- **Minimal circular dependencies**: Only 3 found (resolved via dynamic imports)
- **Well-isolated foundation**: `types.py`, `play/`, `artifacts/` have 0 internal deps
- **O(1) hot loop**: Performance contracts enforced via precomputed arrays

### Areas for Improvement

| File | Issue | Priority |
|------|-------|----------|
| `runtime/snapshot_view.py` | 1750 lines, multiple responsibilities | P2 |
| `engine.py` | 17 internal imports (acceptable for orchestrator) | P2 |
| Various | Missing docstrings, cleanup | P3 |

---

## Module Overview

```
src/backtest/
├── Entry Points (4 files)
│   ├── engine.py              ← Main orchestrator (17 imports)
│   ├── runner.py              ← Play-native runner with gates
│   ├── engine_factory.py      ← Factory functions
│   └── bar_processor.py       ← Per-bar processing
│
├── sim/ (25+ files)           ← Simulated Exchange [WELL MODULARIZED]
│   ├── exchange.py            ← Thin orchestrator
│   ├── types.py               ← Foundation types (0 internal deps)
│   ├── ledger.py              ← Accounting state machine
│   ├── pricing/               ← Pure function models
│   ├── execution/             ← Order fill pipeline
│   ├── funding/               ← Funding rate events
│   └── liquidation/           ← Liquidation checks
│
├── runtime/ (18 files)        ← Runtime Views & State
│   ├── types.py               ← Core types (0 internal deps)
│   ├── feed_store.py          ← O(1) array storage
│   ├── snapshot_view.py       ← Hot loop view [NEEDS SPLIT]
│   └── state_*.py             ← Stage 7 state tracking
│
├── rules/ (25+ files)         ← DSL & Evaluation
│   ├── dsl_nodes/             ← Node type hierarchy
│   ├── evaluation/            ← Expression evaluator
│   └── compile.py             ← YAML → DSL compilation
│
├── features/ (3 files)        ← Indicator Specifications
├── incremental/ (12 files)    ← O(1) Structure Detection
├── play/ (4 files)            ← Config Models [0 INTERNAL DEPS]
├── artifacts/ (9 files)       ← Result Writing [0 INTERNAL DEPS]
├── prices/ (8 files)          ← Mark Price Providers
└── gates/ (4 files)           ← Validation Gates
```

---

## Dependency Statistics

| Directory | Files | Avg Internal Deps | Avg External Deps |
|-----------|-------|-------------------|-------------------|
| Entry points | 4 | 13 | 4 |
| sim/ | 25 | 5 | 3 |
| runtime/ | 18 | 3 | 4 |
| rules/ | 25 | 4 | 2 |
| incremental/ | 12 | 2 | 3 |
| play/ | 4 | 0 | 3 |
| artifacts/ | 9 | 0 | 5 |

---

## Refactor Roadmap

### Phase 1: Quick Wins (1 day)
- [ ] Consolidate engine helper imports → See [REFACTOR_TARGETS.md](./REFACTOR_TARGETS.md#p2-medium-priority)
- [ ] Add missing docstrings to public APIs

### Phase 2: Structural (3 days)
- [ ] Split `snapshot_view.py` into focused modules
- [ ] Extract state tracking to dedicated package

### Phase 3: Polish (2 days)
- [ ] Standardize import ordering
- [ ] Remove deprecated shims
- [ ] Update module-level documentation

---

## Key Call Flows

### Backtest Execution
```
BacktestRunner.run()
  → engine_factory.run_backtest()
    → BacktestEngine.__init__()
    → BacktestEngine.run()
      → _run_loop()
        → BarProcessor.process_bar()
          → SimulatedExchange.process_bar()
```

### Order Fill Pipeline
```
SimulatedExchange.submit_order()
  → OrderBook.add_order()
  → [on next bar]
  → ExecutionModel.fill_entry_order()
    → SlippageModel.apply_slippage()
    → Ledger.apply_entry_fee()
```

> **Full diagrams**: See [CALL_GRAPHS.md](./CALL_GRAPHS.md)

---

## Circular Dependencies

| Cycle | Resolution | Status |
|-------|------------|--------|
| engine ↔ bar_processor | Lazy import in bar_processor | Resolved |
| snapshot_view ↔ cache | TYPE_CHECKING guard | Resolved |
| rules/compile ↔ dsl_parser | Shared types module | Resolved |

> **Full analysis**: See [COUPLING_ANALYSIS.md](./COUPLING_ANALYSIS.md)

---

## Next Steps

1. **Review detailed findings** in linked documents
2. **Prioritize refactors** based on current workstream
3. **Execute Phase 1** quick wins if bandwidth allows
4. **Plan Phase 2** structural changes for next sprint

---

## Related Documentation

| Document | Location |
|----------|----------|
| Project Overview | `docs/project/PROJECT_OVERVIEW.md` |
| Backtest Engine Concepts | `docs/guides/BACKTEST_ENGINE_CONCEPTS.md` |
| Play DSL Cookbook | `docs/specs/PLAY_DSL_COOKBOOK.md` |
| Simulated Exchange | `docs/architecture/SIMULATED_EXCHANGE.md` |
