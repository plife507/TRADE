# Archived TODO Phases

This directory contains completed phase tracking documents that have been archived for historical reference.

## Archived Documents

### Core Architecture Phases

1. **SNAPSHOT_HISTORY_MTF_ALIGNMENT_PHASES.md**
   - **Status**: All phases complete (0-9)
   - **Scope**: Snapshot history + MTF alignment roadmap
   - **Key achievements**: RuntimeSnapshot architecture, MTF caching, FeatureSpec pipeline, IdeaCard integration
   - **Completed**: December 2025

2. **SIMULATED_EXCHANGE_MODE_LOCKS_PHASES.md**
   - **Status**: All phases complete
   - **Scope**: SimulatedExchange mode locks (isolated margin + USDT perp only)
   - **Key achievements**: Config validation, currency normalization, test coverage
   - **Completed**: December 2025

3. **BACKTEST_PRODUCTION_FRAMEWORK_SRC_PIPELINE_GATES_A_F.md**
   - **Status**: All gates passed (A-F + Final)
   - **Scope**: Production framework enforcement and verification
   - **Key achievements**: Module ownership locks, IdeaCard → Engine wiring, production-first enforcement
   - **Completed**: December 2025

### Historical Refactor Documentation

4. **BACKTEST_REFACTOR_PHASE_CHECKLIST.md**
   - **Status**: All phases complete (0-5 + cleanup)
   - **Scope**: RuntimeSnapshot + MTF caching + mark unification refactor
   - **Key achievements**: Canonical Bar implementation, RuntimeSnapshot contract, MTF/HTF support
   - **Completed**: December 2025

5. **BACKTEST_REFACTOR_PHASE_NOTES.md**
   - **Status**: Complete implementation notes
   - **Scope**: Detailed notes for BACKTEST_REFACTOR_PHASE_CHECKLIST.md
   - **Contents**: Files created/modified, decisions, test results, code examples
   - **Completed**: December 2025

### Review Documents

6. **PROJECT_REVIEW_DUCKDB_INDICATORS_DEBUG_GUIDE.md**
   - **Status**: Review complete
   - **Scope**: DuckDB data access, indicator declaration, debugging checklist
   - **Purpose**: Reference guide for data pipeline and indicator system

### CLI & Validation System

7. **CLI_FIRST_BACKTEST_DATA_INDICATORS_PHASES.md**
   - **Status**: All phases complete
   - **Scope**: CLI-first validation workflow (no pytest files for backtest validation)
   - **Key achievements**: Preflight diagnostics, indicator key printing, strict failures, CLI wrappers
   - **Completed**: December 2025

8. **CLI_ONLY_VALIDATION_MIGRATION.md**
   - **Status**: All phases complete
   - **Scope**: Migration from pytest to CLI-only validation
   - **Key achievements**: CLI commands, JSON output, pytest file deletion
   - **Completed**: December 2025

### Indicator System

9. **INDICATOR_REGISTRY_YAML_BUILDER_PHASES.md**
   - **Status**: All phases complete
   - **Scope**: Registry-driven indicator system + YAML builder/normalizer
   - **Key achievements**: IndicatorRegistry, validation, multi-output expansion, audit toolkit
   - **Completed**: December 2025

10. **INDICATOR_METADATA_SYSTEM_PHASES.md**
    - **Status**: Phases 1-5, 7 complete
    - **Scope**: Lightweight metadata tracking for indicator provenance
    - **Key achievements**: Metadata capture, FeedStore integration, export utilities, CLI smoke test
    - **Completed**: December 2025

### Validation & Bug Fixes

11. **THREE_YEAR_MTF_TRIO_BACKTESTS.md**
    - **Status**: All phases complete
    - **Scope**: 3-year MTF backtests for BTCUSDT, ETHUSDT, SOLUSDT
    - **Key achievements**: 3 IdeaCards created, validated, and producing trades
    - **Completed**: December 2025

12. **MTF_HISTORY_WARMUP_BUG_FIX.md**
    - **Status**: Bug fixed and verified
    - **Scope**: MTF history warmup not populating during warmup loop
    - **Key achievements**: History update during warmup, MTF backtests generating trades
    - **Completed**: December 2025

### Documentation-Only Reviews

13. **DUCKDB_FUNDING_OI_VOLUME_PIPELINE_REVIEW.md**
    - **Status**: Complete (documentation-only)
    - **Scope**: End-to-end review of DuckDB funding/OI/volume pipeline
    - **Key achievements**: Documented schemas, traced consumption gaps, integration guide
    - **Completed**: December 2025

14. **FUNDING_POLICY_IDEACARD_VALIDATION_IMPACTS.md**
    - **Status**: Complete (documentation-only)
    - **Scope**: Funding policy IdeaCard contract and validation impacts
    - **Key achievements**: Defined sim.funding.enabled contract, validation surface mapping
    - **Completed**: December 2025

## Archive Date

Documents 1-6 archived: December 2025  
Documents 7-12 archived: December 2025 (governance cleanup)
Documents 13-14 archived: December 2025 (docs refactor)

## Purpose

These documents are preserved for:
- Understanding design decisions and trade-offs
- Reference for similar refactors
- Historical context for code changes
- Onboarding new developers

For current project status, see:
- `docs/project/PROJECT_OVERVIEW.md` - Current project overview/roadmap
- `docs/todos/README.md` - Active TODO tracking

