# TRADE Documentation

**Start here.** Navigation hub for all project documentation.

---

## Core Docs

| Document | Purpose |
|----------|---------|
| [Architecture](architecture/ARCH_SNAPSHOT.md) | Domains, runtime, invariants, accounting, gates |
| [Market Structure Proposal](architecture/MARKET_STRUCTURE_INTEGRATION_PROPOSAL.md) | Phase 5 design: swings, pivots, trends, regimes |
| [Project Status](PROJECT_STATUS.md) | What runs today, blockers, next steps |
| [Session Handoff](SESSION_HANDOFF.md) | Inter-session context: last work, open streams, priority items |

---

## Domain Docs

| Document | Purpose |
|----------|---------|
| [Data Module](data/DATA_MODULE.md) | DuckDB stores, schemas, quality checks |
| [Strategy Factory](strategy_factory/STRATEGY_FACTORY.md) | IdeaCards, promotion loops |
| [IdeaCard Engine Flow](architecture/IDEACARD_ENGINE_FLOW.md) | IdeaCard -> Engine orchestration |

---

## Active TODOs

| Document | Status |
|----------|--------|
| [TODO Index](todos/INDEX.md) | Canonical index of all active/archived TODOs |
| [Audit Open Bugs](todos/AUDIT_OPEN_BUGS.md) | Bug tracking from agentic audit swarm (P1: 4, P2: 19, P3: 10) |
| [Backtest Analytics](todos/BACKTEST_ANALYTICS_PHASES.md) | Phases 1-4 complete, Phases 5-6 pending |

---

## Architecture

| Document | Purpose |
|----------|---------|
| [ARCH_SNAPSHOT](architecture/ARCH_SNAPSHOT.md) | Main architecture overview |
| [ARCH_DELAY_BARS](architecture/ARCH_DELAY_BARS.md) | Delay bars implementation |
| [ARCH_INDICATOR_WARMUP](architecture/ARCH_INDICATOR_WARMUP.md) | Indicator warmup system |
| [Intraday Adaptive System](architecture/INTRADAY_ADAPTIVE_SYSTEM_REVIEW.md) | Intraday adaptive system design |

---

## Audit Reports

| Document | Purpose |
|----------|---------|
| [Audit Index (2026-01-01)](audits/2026-01-01/AUDIT_INDEX.md) | 10-agent comprehensive audit summary |
| [Audit Module](audits/2026-01-01/AUDIT_MODULE.md) | Gates, tests, bugs, validations |
| [Fix Plan](audits/2026-01-01/FIX_PLAN.md) | Ordered remediation plan with diffs |
| [Risk Register](audits/2026-01-01/RISK_REGISTER.md) | Full risk catalog with mitigation |
| [Indicator Test Matrix](audits/COMPREHENSIVE_INDICATOR_TEST_MATRIX.md) | Test coverage reference (42 indicators) |

### Individual Audit Reports (2026-01-01)

| ID | Title | Key Finding |
|----|-------|-------------|
| [AUDIT_00](audits/2026-01-01/AUDIT_00_ARCHITECTURE.md) | Architecture Lead | _NAMESPACE_RESOLVERS static class var |
| [AUDIT_10](audits/2026-01-01/AUDIT_10_ENGINE_LOOP.md) | Engine Hot Loop | pd.isna() in hot path |
| [AUDIT_15](audits/2026-01-01/AUDIT_15_MTF_FEEDS.md) | MTF Feed & Alignment | Dual close detection mechanism |
| [AUDIT_20](audits/2026-01-01/AUDIT_20_SNAPSHOT_RESOLUTION.md) | Snapshot Resolution | O(n) operations in snapshot |
| [AUDIT_25](audits/2026-01-01/AUDIT_25_MARK_PRICE.md) | Mark Price Simulation | PRICE_FIELDS incomplete |
| [AUDIT_30](audits/2026-01-01/AUDIT_30_RULES_COMPILER.md) | Rules Compiler | Legacy eval path still active |
| [AUDIT_40](audits/2026-01-01/AUDIT_40_MARKET_STRUCTURE.md) | Market Structure | Zone width 1% fallback |
| [AUDIT_50](audits/2026-01-01/AUDIT_50_STATE_TRACKING.md) | State Tracking | Incomplete hook wiring |
| [AUDIT_60](audits/2026-01-01/AUDIT_60_SCHEMA_AND_ARTIFACTS.md) | Schema & Artifacts | Version fields write-only |
| [AUDIT_70](audits/2026-01-01/AUDIT_70_TEST_COVERAGE.md) | Test Coverage | No state on/off comparison test |

---

## Reviews

| Document | Purpose |
|----------|---------|
| [Architecture Design Review](reviews/ARCHITECTURE_DESIGN_REVIEW.md) | Architecture design decisions |
| [Backtest System Review](reviews/BACKTEST_SYSTEM_REVIEW.md) | Backtest system analysis |
| [Backtest Engine Code Review](reviews/BACKTEST_ENGINE_CODE_REVIEW.md) | Engine code quality review |
| [Market Structure Integration Findings](reviews/MARKET_STRUCTURE_INTEGRATION_REVIEW_FINDINGS.md) | Integration findings |
| [Exception Hierarchy Review](reviews/EXCEPTION_HIERARCHY_REVIEW.md) | Exception handling patterns |
| [Unified Warmup Architecture](reviews/UNIFIED_WARMUP_ARCHITECTURE_REVIEW.md) | Warmup architecture review |

---

## Quick Start

```bash
python trade_cli.py                     # Run CLI
python trade_cli.py --smoke full        # Full smoke test
python trade_cli.py backtest run --idea-card <ID> --start <date> --end <date>
```

---

## Recently Completed (January 2026)

| Document | Status | Archive Location |
|----------|--------|-----------------|
| [Market Structure Phases](todos/archived/2026-01-01/MARKET_STRUCTURE_PHASES.md) | Stages 0-7 Complete | todos/archived/2026-01-01/ |
| [Legacy Cleanup](todos/archived/2026-01-01/LEGACY_CLEANUP_PHASES.md) | Complete | todos/archived/2026-01-01/ |
| [Metrics Enhancement](todos/archived/2026-01-01/METRICS_ENHANCEMENT_PHASES.md) | Complete | todos/archived/2026-01-01/ |
| [IdeaCard Value Flow Fix](todos/archived/2026-01-01/IDEACARD_VALUE_FLOW_FIX_PHASES.md) | Complete | todos/archived/2026-01-01/ |
| [CLI Menu Tools Alignment](todos/archived/2026-01-01/CLI_MENU_TOOLS_ALIGNMENT_PHASES.md) | Complete | todos/archived/2026-01-01/ |
| [Registry Consolidation](todos/archived/2026-01/REGISTRY_CONSOLIDATION_PHASES.md) | Complete | todos/archived/2026-01/ |
| [Array-Backed Hot Loop](todos/archived/2026-01/ARRAY_BACKED_HOT_LOOP_PHASES.md) | Complete | todos/archived/2026-01/ |

## Previously Completed (December 2025)

| Document | Status | Archive Location |
|----------|--------|-----------------|
| [Price Feed (1m) + Preflight](todos/archived/2025-12-31/PRICE_FEED_1M_PREFLIGHT_PHASES.md) | Complete | todos/archived/2025-12-31/ |
| [Engine Modular Refactor](todos/archived/2025-12-30/ENGINE_MODULAR_REFACTOR_PHASES.md) | Complete | todos/archived/2025-12-30/ |
| [Backtester Fixes Phase 1](todos/archived/2025-12-30/BACKTESTER_FIXES_PHASE1.md) | Complete | todos/archived/2025-12-30/ |
| [Post-Backtest Audit Gates](todos/archived/2025-12-18/POST_BACKTEST_AUDIT_GATES.md) | Complete | todos/archived/2025-12-18/ |
| [Backtest Financial Metrics](todos/archived/2025-12-18/BACKTEST_FINANCIAL_METRICS_MTM_EQUITY_PHASES.md) | Complete | todos/archived/2025-12-18/ |
| [Production Pipeline Validation](todos/archived/2025-12-18/PRODUCTION_PIPELINE_VALIDATION.md) | Complete | todos/archived/2025-12-18/ |

---

## Session Reviews (Archived)

Session reviews have been archived to `docs/session_reviews/archived/`.

| Archive Location | Content |
|------------------|---------|
| [session_reviews/archived/](session_reviews/archived/) | Historical session summaries (2024-12 to 2025-12) |
| [session_reviews/README.md](session_reviews/README.md) | Session review format and purpose |

---

## External References

| Topic | Location |
|-------|----------|
| AI Guidance | `CLAUDE.md` |
| IdeaCards | `configs/idea_cards/` |
| Validation IdeaCards | `configs/idea_cards/_validation/` (21+ cards) |
| Source | `src/` |
| Archived Docs | `docs/_archived/` |

---
