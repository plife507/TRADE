# TRADE — Project Roadmap

**Last Updated:** December 14, 2025  
**Project Status:** Backtest engine operational with IdeaCard system; analytics complete (Phases 1-3)  
**Overall Grade:** A (9/10) — Exceptional for a first project

---

## Executive Summary

The TRADE bot is a **well-architected, safety-first** Bybit futures trading bot with a complete backtesting engine. The codebase is **production-ready for demo trading and backtesting**.

**Completed:**
- ✅ Complete Bybit UTA trading support
- ✅ Bybit-aligned backtest engine refactor (Phases 0–5: RuntimeSnapshot + MTF caching + mark unification)
- ✅ DuckDB historical data store
- ✅ Tool Registry for orchestrators
- ✅ Risk controls and safety features

**Current Focus:**
- ✅ Backtest analytics (Phases 1-3 complete)
- ✅ IdeaCard system fully operational
- ✅ Indicator registry with 150+ pandas_ta indicators
- 🔨 Additional backtest suites and validation

---

## Phase Status

### ✅ Phase 1 — Core Backtest Engine (COMPLETE)

**Goal:** Boring, reliable backtest engine for single system.

**Delivered:**
- Deterministic results (same inputs → same outputs)
- No look-ahead (indicators computed correctly)
- Bybit-aligned accounting (isolated margin, IMR/MMR, fees)
- Config-only window switching (hygiene/test)
- Canonical timing (`Bar.ts_open/ts_close`) + `RuntimeSnapshot` strategy input
- MTF/HTF caching with readiness gate
- Mark price unification (single mark per step)
- Preflight data health gate + bounded heal loop (tools)
- Artifact output (`result.json`, `trades.csv`, `equity.csv`, `account_curve.csv`, `run_manifest.json`, `events.jsonl`)

**SimulatedExchange Features:**
- **Modular architecture**: Thin orchestrator (~200 LOC) with specialized modules
- Explicit USD-named state variables
- Entry gate with Active Order IM concept
- Configurable fees (taker_fee_rate)
- Stop conditions (account_blown, insufficient_free_margin)
- RiskProfileConfig with all tunables
- **Specialized modules**: Pricing, execution (slippage/liquidity/impact), funding, liquidation, ledger, metrics, constraints

### ✅ Phase 2 — Tools & CLI Integration (COMPLETE)

**Goal:** Make backtesting usable via tools and CLI.

**Status:**
- ✅ `backtest_run_tool` — Run backtest by system_id + window_name
- ✅ `backtest_list_systems_tool` — List available system configs
- ✅ CLI Backtest menu — Interactive selection
- ✅ Epoch tracking — Artifacts + lineage metadata
- ✅ Smoke tests + integration gates (DuckDB + replay determinism)
- 🔨 Ongoing polish (UX/error messages)

### 📋 Phase 3 — Logging & Data for Learning (FUTURE)

**Goal:** Log enough for future forecasting/ML.

**Planned:**
- Per-bar dataset export (features + labels)
- Reproducible feature snapshots

### 📋 Phase 4 — Strategy Factory (FUTURE)

**Goal:** Light orchestrator on top of tools.

**Planned:**
- Strategy registry with status tracking
- Batch backtest orchestration
- Pass/fail tracking and promotion

### 📋 Phase 5 — Forecast Experiments (FUTURE)

**Goal:** Offline forecast + policy experiments.

**Planned:**
- Simple forecaster on per-bar dataset
- Rule-based policy selection
- Composite backtest mode

### 📋 Phase 6 — Demo & Live (FUTURE)

**Goal:** Promote stable systems to demo/live.

**Planned:**
- Demo window tracking
- Performance-based promotion
- Live deployment guardrails

---

## Current Architecture Scores

| Area | Score | Notes |
|------|-------|-------|
| **Architecture** | 9.5/10 | Clean layering, proper abstractions |
| **Safety & Risk** | 10/10 | Strict mode mapping, circuit breakers |
| **API Correctness** | 9/10 | Official SDK, rate limiting, TimeRange |
| **Code Quality** | 9/10 | Type hints, dataclasses, consistent style |
| **Backtest Engine** | 9/10 | Bybit-aligned, deterministic, configurable |
| **Test Coverage** | 8/10 | Critical paths covered, needs more edge cases |

---

## Key Principles (NEVER COMPROMISE)

### Safety First

**Always:**
- ✅ Validate trading mode before every order
- ✅ Enforce risk limits strictly
- ✅ Use demo API for testing
- ✅ Log all trading decisions
- ✅ Test through real interfaces

**Never:**
- ❌ Bypass risk manager
- ❌ Hardcode values that should be configurable
- ❌ Skip validation for "quick" fixes
- ❌ Trade on live API without explicit confirmation

### Code Quality Standards

**Maintain:**
- Type hints on all functions
- Docstrings for public APIs
- Consistent error handling
- No files over 1500 lines
- Tests for critical paths

**Avoid:**
- Direct API calls from tools/CLI
- Hardcoded symbols, sizes, or paths
- Silent error swallowing
- Magic numbers without constants

### Architecture Discipline

**Follow:**
- Tools layer is the ONLY public API
- ExchangeManager for all trading operations
- Rate limiter for ALL API calls
- TimeRange for ALL history queries
- Config for ALL settings

---

## Development Workflow

### Adding New Features

1. Check if existing code already does what you need
2. Prefer reusing existing abstractions
3. Keep the call chain shallow
4. Ensure wrapper adds clear value (validation, transformation)

### Testing Strategy

1. Test through real interfaces (CLI, tools)
2. Unit tests are supplementary, not primary
3. Real API calls (demo mode) for integration tests
4. If it works in tests but fails in CLI, tests are incomplete

### Refactoring Guidelines

**Refactor when:**
- File exceeds 1500 lines
- Pattern repeats 3+ times
- Code is hard to test
- Performance is measurably poor

**Don't refactor:**
- "Just because"
- Without tests in place
- During critical bug fixes
- Without understanding impact

---

## Immediate Tasks

### High Priority

- [ ] Add more backtest smoke test scenarios
- [ ] Polish error messages in CLI
- [ ] Add risk_profile override examples to docs

### Medium Priority

- [ ] Stress tests for rate limiter
- [ ] Edge case tests (partial fills, etc.)
- [ ] Concurrent execution tests

### Low Priority

- [ ] API documentation (OpenAPI/Swagger)
- [ ] Architecture diagrams
- [ ] Deployment guides

---

## Success Metrics

### Code Quality

- **Test Coverage:** 80%+ for critical paths
- **Type Coverage:** 100%
- **Linter Score:** 0 errors
- **File Size:** All files <1500 lines

### Operational

- **Uptime:** 99.9%+
- **API Error Rate:** <0.1%
- **Order Execution Time:** <500ms p95
- **Rate Limit Utilization:** <80% average

### Backtest Accuracy

- **Determinism:** 100% reproducible
- **Accounting Invariants:** Always pass
- **Fee Accuracy:** Within 0.01% of Bybit

---

## Risk Management Checklist

Before deploying any change to live trading:

- [ ] All tests pass (unit + integration)
- [ ] Tested on demo API first
- [ ] Code review completed
- [ ] Safety validations verified
- [ ] Error handling tested
- [ ] Rate limiting verified
- [ ] Logging verified (no secrets)
- [ ] Documentation updated
- [ ] Rollback plan prepared

---

## Reference Documentation

| Topic | File |
|-------|------|
| Technical Overview | `docs/architecture/SYSTEM_REVIEW.md` |
| Backtest Accounting | `docs/architecture/SIMULATED_EXCHANGE.md` |
| Data Architecture | `docs/architecture/DATA_ARCHITECTURE.md` |
| Project Rules | `docs/project/PROJECT_RULES.md` |
| Code Examples | `docs/guides/CODE_EXAMPLES.md` |
| Bybit API Reference | `reference/exchanges/bybit/docs/v5/` |

---

## Changelog

- **2025-12-13:** Backtest refactor complete (Phases 0–5)
  - Refactored exchange into modular architecture (pricing, execution, funding, liquidation, ledger, metrics, constraints)
  - Added proof-grade metrics system (V2)
  - Thin orchestrator pattern (~200 LOC main class)
- **2025-12-12:** Backtest engine operational
- **2025-12-06:** Initial roadmap created
