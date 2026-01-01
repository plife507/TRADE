# TRADE Documentation

**Start here.** Navigation hub for all project documentation.

---

## Core Docs

| Document | Purpose |
|----------|---------|
| [Architecture](architecture/ARCH_SNAPSHOT.md) | Domains, runtime, invariants, accounting, gates |
| [Market Structure Proposal](architecture/MARKET_STRUCTURE_INTEGRATION_PROPOSAL.md) | Phase 5 design: swings, pivots, trends, regimes |
| [Project Status](PROJECT_STATUS.md) | What runs today, blockers, next steps |

---

## Domain Docs

| Document | Purpose |
|----------|---------|
| [Data Module](data/DATA_MODULE.md) | DuckDB stores, schemas, quality checks |
| [Strategy Factory](strategy_factory/STRATEGY_FACTORY.md) | IdeaCards, promotion loops |
| [Audit Module](audits/AUDIT_MODULE.md) | Gates, tests, bugs, validations |

---

## Active TODOs

| Document | Status |
|----------|--------|
| [Price Feed (1m) + Preflight Gate](todos/PRICE_FEED_1M_PREFLIGHT_PHASES.md) | 🔜 NEXT (Blocking Market Structure) |
| [Array-Backed Hot Loop](todos/ARRAY_BACKED_HOT_LOOP_PHASES.md) | Phase 5 📋 READY (After Price Feed) |
| [Backtest Analytics](todos/BACKTEST_ANALYTICS_PHASES.md) | Phases 4-6 📋 pending |
| [Registry Consolidation](todos/REGISTRY_CONSOLIDATION_PHASES.md) | 📋 READY (Prereq for Market Structure) |

---

## Quick Start

```bash
python trade_cli.py                     # Run CLI
python trade_cli.py --smoke full        # Full smoke test
python trade_cli.py backtest run --idea-card <ID> --start <date> --end <date>
```

---

## Recently Completed (December 2025)

| Document | Status | Archive Location |
|----------|--------|-----------------|
| [Engine Modular Refactor](todos/archived/2025-12-30/ENGINE_MODULAR_REFACTOR_PHASES.md) | ✅ Complete (2025-12-30) | archived/2025-12-30/ |
| [Backtester Fixes Phase 1](todos/archived/2025-12-30/BACKTESTER_FIXES_PHASE1.md) | ✅ Complete (2025-12-30) | archived/2025-12-30/ |
| [Preflight + Backfill](todos/PREFLIGHT_BACKFILL_PHASES.md) | ✅ Phases 1-7 Complete (2024-12-17) | - |
| [Refactor Before Advancing](todos/archived/2025-12-18/REFACTOR_BEFORE_ADVANCING.md) | ✅ Complete (2025-12-18) | archived/2025-12-18/ |
| [Post-Backtest Audit Gates](todos/archived/2025-12-18/POST_BACKTEST_AUDIT_GATES.md) | ✅ Phases 1-4 Complete | archived/2025-12-18/ |
| [Backtest Financial Metrics](todos/archived/2025-12-18/BACKTEST_FINANCIAL_METRICS_MTM_EQUITY_PHASES.md) | ✅ All Phases Complete | archived/2025-12-18/ |
| [Production Pipeline Validation](todos/archived/2025-12-18/PRODUCTION_PIPELINE_VALIDATION.md) | ✅ All Gates Passed | archived/2025-12-18/ |

## Previously Completed (December 18, 2025)

| Document | Status | Archive Location |
|----------|--------|-----------------|
| [Post-Backtest Audit Gates](todos/archived/2025-12-18/POST_BACKTEST_AUDIT_GATES.md) | ✅ Phases 1-4 Complete | todos/archived/2025-12-18/ |
| [Backtest Financial Metrics](todos/archived/2025-12-18/BACKTEST_FINANCIAL_METRICS_MTM_EQUITY_PHASES.md) | ✅ All Phases Complete | todos/archived/2025-12-18/ |
| [Production Pipeline Validation](todos/archived/2025-12-18/PRODUCTION_PIPELINE_VALIDATION.md) | ✅ All Gates Passed | todos/archived/2025-12-18/ |

---

## Session Reviews (Recent)

| Date | Topic | Key Changes |
|------|-------|-------------|
| 2025-12-18 | [Cleanup Summary](session_reviews/2025-12-18_cleanup_summary.md) | Workspace cleanup, TODO archival, clean starting point |
| 2025-12-18 | [Production Pipeline Validation](session_reviews/2025-12-18_production_pipeline_validation.md) | End-to-end backtest pipeline validation (5 IdeaCards, all gates passed) |
| 2025-12-18 | [Financial Metrics Audit](session_reviews/2025-12-18_backtest_financial_metrics_audit.md) | Math formulas for all performance metrics |
| 2024-12-17 | [Phase 6 CLI Smoke Tests](session_reviews/2024-12-17_phase6_cli_smoke_tests.md) | PreflightReport JSON, data-fix bounded enforcement, artifact standards |
| 2024-12-17 | [Delay Bars Implementation](session_reviews/2024-12-17_delay_bars_implementation_and_validation.md) | market_structure.delay_bars, eval_start_ts_role, 410 trades validated |
| 2024-12-17 | [Warmup System Audit](session_reviews/2024-12-17_warmup_system_audit.md) | MTF warmup bug fix, synchronization logic |

---

## External References

| Topic | Location |
|-------|----------|
| AI Guidance | `CLAUDE.md` |
| IdeaCards | `configs/idea_cards/` |
| Source | `src/` |

---
