# TODO Directory — Backtest Engine Phase Tracking

This directory contains phase tracking files for backtest engine development. Completed phases are archived in the `archived/` subdirectory.

## Current Active TODOs

### Active Phase Documents

- **BACKTEST_ANALYTICS_PHASES.md** - Analytics implementation (Phases 1-3 complete, Phases 4-6 pending)
- **CLI_FIRST_BACKTEST_DATA_INDICATORS_PHASES.md** - CLI-first validation (Complete)
- **INDICATOR_REGISTRY_YAML_BUILDER_PHASES.md** - Indicator registry and YAML builder (Complete)
- **BACKTEST_MIXED_IDEACARDS_SUITE_10.md** - 10 mixed IdeaCards suite (In progress)
- **THREE_YEAR_MTF_TRIO_BACKTESTS.md** - Three-year MTF trio backtests (Complete)

## Archived Completed Phases

All completed phase tracking documents have been moved to `archived/`:

### Core Architecture Refactors

- **SNAPSHOT_HISTORY_MTF_ALIGNMENT_PHASES.md** - Complete snapshot history + MTF alignment roadmap (Phases 0-9, all complete)
  - RuntimeSnapshot architecture
  - Multi-timeframe caching with closed-candle semantics
  - FeatureSpec + FeatureFrame pipeline
  - IdeaCard schema + ingestion
  - Execution validation gates

- **SIMULATED_EXCHANGE_MODE_LOCKS_PHASES.md** - SimulatedExchange mode locks (isolated margin + USDT perp only)
  - Config schema & validation
  - Currency normalization (USD → USDT)
  - Test coverage

- **BACKTEST_PRODUCTION_FRAMEWORK_SRC_PIPELINE_GATES_A_F.md** - Production framework gates (A-F, all complete)
  - Module ownership locks
  - IdeaCard → Engine wiring
  - Production-first enforcement
  - Pipeline verification

### Historical Refactor Documentation

- **BACKTEST_REFACTOR_PHASE_CHECKLIST.md** - Complete phase-by-phase checklists with implementation tasks and acceptance criteria
  - Phase 0: Prep/Cutover (module layout, validation)
  - Phase -1: Preflight Data Health Gate (data validation, heal loops)
  - Phase 1: ts_open/ts_close Introduction (canonical Bar implementation)
  - Phase 2: RuntimeSnapshot Contract (single builder pattern)
  - Phase 3: TF Close Detection + Caching (MTF/HTF support)
  - Phase 4: Mark Price Unification (single source of truth)
  - Phase 5: Look-Ahead Bias Proof Tests
  - Post-Phase Cleanup: Legacy Bar Removal

- **BACKTEST_REFACTOR_PHASE_NOTES.md** - Detailed implementation notes for each phase
  - Files created/modified per phase
  - Key decisions and architectural choices
  - Test results and validation status
  - Open questions and resolutions
  - Code examples and implementation details

- **PROJECT_REVIEW_DUCKDB_INDICATORS_DEBUG_GUIDE.md** - Review document covering DuckDB data access, indicator declaration, and debugging checklist

## Status

All major backtest engine phases are **COMPLETED** as of December 2025. All tracking documents have been archived.

### Key Achievements

- ✅ Legacy Bar types removed, canonical Bar with `ts_open`/`ts_close` implemented
- ✅ RuntimeSnapshot is the only strategy input
- ✅ MTF/HTF caching with data-driven close detection implemented
- ✅ Mark price unification completed
- ✅ All tests passing (184+ tests)
- ✅ Integration Gate 2 verified with real DuckDB (18 passed, 1 skipped)

### Post-Phase Cleanup

- ✅ All tests updated to use canonical `Bar` format
- ✅ `bar_compat.py` simplified to canonical-only
- ✅ All sim modules use canonical `Bar` type hints
- ✅ Documentation updated across project

## Quick Reference

**What was refactored?**
- Backtest engine core architecture (RuntimeSnapshot, MTF caching, mark price unification)
- Bar type system (canonical Bar with `ts_open`/`ts_close` replacing legacy types)
- Data health preflight gates and heal loops
- Multi-timeframe support with data-driven close detection

**When?** December 2025

**Why archive?** These files document a major architectural refactor that established the foundation for the current backtest engine. Useful for:
- Understanding design decisions and trade-offs
- Reference for similar refactors
- Historical context for code changes
- Onboarding new developers

## Related Documentation

For current project status and roadmap, see:
- `docs/project/PROJECT_OVERVIEW.md` - Current project overview/roadmap
- `docs/project/PROJECT_ROADMAP.md` - Detailed roadmap
- `docs/architecture/SYSTEM_REVIEW.md` - Technical overview
- `docs/architecture/SIMULATED_EXCHANGE.md` - Simulated exchange architecture
