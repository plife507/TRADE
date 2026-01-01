# TRADE Project Status

**STATUS:** CANONICAL
**PURPOSE:** What runs today, what is stubbed, top risks, next steps
**LAST UPDATED:** January 1, 2026 (Metrics Consolidation + IdeaCard Value Flow complete)

---

## Current State Summary

| Component | Status | Notes |
|-----------|--------|-------|
| CLI | ✅ Production | All menus functional |
| Data Layer | ✅ Production | DuckDB, sync, heal working |
| Backtest Engine | ✅ Production | Modular architecture (8 modules), single-symbol, MTF, delay_bars support |
| MTF Support | ✅ Production | exec/htf/mtf with delay_bars |
| Simulated Exchange | ✅ Production | Bybit-aligned accounting |
| Preflight + Data-Fix | ✅ Production | Phase 6 CLI smoke tests validated + **mandatory 1m coverage** |
| 1m Price Feed | ✅ Production | QuoteState, ExecRollupBucket, px.rollup.* accessors |
| Artifact Standards | ✅ Production | ts_ms, eval_start_ts_ms, structured exports |
| Backtest Metrics | ✅ Production | **59 unified fields**: equity, drawdown, trade stats, risk-adjusted ratios, tail risk (skewness, kurtosis, VaR, CVaR), leverage metrics, MAE/MFE tracking |
| IdeaCard Value Flow | ✅ Production | Fail-loud validation, explicit declarations, all phases complete |
| Live Trading | ⚠️ Functional | Demo API tested, live not validated |
| Indicator System | ✅ Production | P0 input-source bug fixed (2025-12-17) |
| Strategy Factory | ⚠️ Partial | IdeaCards work, promotion manual |
| Agent Module | ❌ Planned | Not started |

---

## Recent Completions (December 2025 - January 2026)

| Phase | Status | Date | Key Features |
|-------|--------|------|--------------|
| Metrics Consolidation | ✅ Complete | Jan 1 | v1/v2 terminology removed, single unified BacktestMetrics with 59 fields |
| High-Value Quant Metrics | ✅ Complete | Jan 1 | Tail risk (skewness, kurtosis, VaR 95%, CVaR/Expected Shortfall), leverage tracking (avg_leverage_used, max_gross_exposure_pct), MAE/MFE per trade |
| IdeaCard Value Flow | ✅ Complete | Jan 1 | Fail-loud validation, explicit declarations, all phases complete |
| Legacy Cleanup | ✅ Complete | Jan 1 | ExecutionConfig simplified, dead code removed |
| Price Feed (1m) + Preflight | ✅ Complete | Dec 31 | Mandatory 1m coverage, QuoteState, ExecRollupBucket, px.rollup.* accessors, Market Structure unblocked |
| Engine Modular Refactor | ✅ Complete | Dec 30 | Split engine.py into 8 modules (2,236 → 1,154 lines), all tests pass, ready for Phase 5 |
| Backtester Fixes Phase 1 | ✅ Complete | Dec 30 | 6 fixes: HTF O(n)→O(log n), TF defaults raise errors, warmup mandatory, feature metadata required, daily loss explicit |
| Post-Backtest Audit Gates | ✅ Complete | Dec 18 | Auto-sync (--fix-gaps), artifact validation, determinism verification, smoke test integration |
| Backtest Financial Metrics | ✅ Complete | Dec 18 | Fixed Max DD%, proper CAGR/Calmar, TF strictness, funding metrics, metrics-audit CLI |
| Production Pipeline Validation | ✅ Complete | Dec 18 | End-to-end validation with 5 IdeaCards, all 6 gates passed |
| Phase 7: Delay Bars | ✅ Complete | Dec 17 | market_structure.delay_bars, eval_start_ts_role, CLI smoke validated |
| Phase 6: CLI Smoke Tests | ✅ Complete | Dec 17 | PreflightReport JSON, data-fix bounded enforcement, artifact standards |
| Phase 5: Preflight + Backfill | ✅ Complete | Dec 17 | Auto-sync, warmup computation, RunManifest audit trail |
| Indicator Metadata v1 | ✅ Complete | Dec 17 | feature_spec_id, provenance tracking, metadata export |
| MTF Warmup Bug Fix | ✅ Complete | Dec 17 | HTF/MTF warmup synchronization, no silent data insufficiency |

**See**: `docs/session_reviews/` for detailed implementation notes

---

## BacktestMetrics System (59 Unified Fields)

The backtest engine now outputs a comprehensive, production-ready metrics suite with **59 fields** covering all aspects of strategy performance. All v1/v2 terminology has been removed - there is now a single unified `BacktestMetrics` class.

### Metrics Categories

| Category | Fields | Description |
|----------|--------|-------------|
| **Equity Curve** | 6 fields | `final_equity_usdt`, `total_return_pct`, `total_return_ratio`, `cagr_pct`, `trading_days`, `active_duration_hours` |
| **Drawdown** | 3 fields | `max_drawdown_pct`, `max_drawdown_usdt`, `calmar_ratio` |
| **Trade Statistics** | 8 fields | `total_trades`, `winning_trades`, `losing_trades`, `win_rate_pct`, `avg_win_usdt`, `avg_loss_usdt`, `largest_win_usdt`, `largest_loss_usdt` |
| **Risk-Adjusted Returns** | 4 fields | `sharpe_ratio`, `sortino_ratio`, `profit_factor`, `expectancy_usdt` |
| **Tail Risk** | 4 fields | `skewness`, `kurtosis`, `var_95_pct`, `cvar_expected_shortfall_pct` |
| **Leverage & Exposure** | 2 fields | `avg_leverage_used`, `max_gross_exposure_pct` |
| **MAE/MFE Tracking** | 6 fields | `avg_mae_usdt`, `avg_mae_pct`, `avg_mfe_usdt`, `avg_mfe_pct`, `mae_mfe_ratio`, `efficiency_ratio_pct` |
| **Entry Friction** | 3 fields | `total_entry_slippage_usdt`, `total_entry_fees_usdt`, `entry_cost_pct_of_pnl` |
| **Funding & Fees** | 5 fields | `total_funding_paid_usdt`, `total_taker_fees_usdt`, `total_maker_fees_usdt`, `total_fees_usdt`, `funding_as_pct_of_pnl` |
| **Margin Stress** | 5 fields | `min_margin_balance_usdt`, `margin_call_count`, `lowest_margin_ratio_pct`, `avg_margin_utilization_pct`, `margin_stress_hours` |
| **Liquidation Risk** | 4 fields | `closest_liquidation_distance_pct`, `liquidation_alerts_count`, `hours_in_danger_zone`, `liquidation_occurred` |
| **Holding Periods** | 9 fields | `avg_trade_duration_bars`, `avg_win_duration_bars`, `avg_loss_duration_bars`, `median_trade_duration_bars`, `shortest_trade_bars`, `longest_trade_bars`, `avg_bars_between_trades`, `max_bars_between_trades`, `idle_time_pct` |

### Key Features

- **Unified System**: Single `BacktestMetrics` class, no v1/v2 split
- **Fail-Loud Validation**: All required fields must be present, no silent defaults
- **Complete Trade Tracking**: Every trade records MAE/MFE with full position lifecycle
- **Tail Risk Analysis**: Professional quant metrics (VaR, CVaR, skewness, kurtosis)
- **Leverage Monitoring**: Track average leverage and maximum gross exposure
- **Entry Cost Analysis**: Separate tracking of slippage vs fees, cost as % of PnL
- **Margin Safety**: Multi-dimensional margin stress analysis
- **Liquidation Proximity**: Track how close positions came to liquidation

### Validation

All metrics are validated through:
- `backtest metrics-audit` CLI command (6/6 tests pass)
- Artifact validation gates (automatic HARD FAIL)
- Determinism verification (`verify-determinism --re-run`)

**See**: `src/backtest/metrics.py` for implementation details

---

## What Runs Today

### CLI Commands

```bash
# Start CLI
python trade_cli.py

# Smoke tests
python trade_cli.py --smoke full           # Full validation (includes Phase 6 if enabled)
python trade_cli.py --smoke data           # Data only
python trade_cli.py --smoke data_extensive # Clean DB, full sync
python trade_cli.py --smoke orders         # Order types (DEMO)
python trade_cli.py --smoke backtest       # Backtest engine validation

# Phase 6 backtest smoke tests (opt-in)
$env:TRADE_SMOKE_INCLUDE_BACKTEST="1"; python trade_cli.py --smoke full

# Backtest
python trade_cli.py backtest run --idea-card <ID> --start <date> --end <date>
python trade_cli.py backtest preflight --idea-card <ID> --fix-gaps
python trade_cli.py backtest indicators --idea-card <ID> --print-keys

# Validation & Audits
python trade_cli.py backtest verify-determinism --run <path> --re-run
python trade_cli.py backtest metrics-audit
python trade_cli.py backtest audit-toolkit
python trade_cli.py backtest math-parity --idea-card <ID> --start <date> --end <date>
python trade_cli.py backtest audit-snapshot-plumbing --idea-card <ID> --start <date> --end <date>
python trade_cli.py backtest audit-rollup
python trade_cli.py backtest metadata-smoke
```

### Expected Outputs

| Command | Success Output |
|---------|----------------|
| `--smoke full` | All checks pass, no errors |
| `backtest run` | `BacktestResult` with metrics, artifacts written to `backtests/` |
| `backtest preflight` | Data coverage report, warmup validation |
| `audit-toolkit` | 42/42 indicators pass |
| `audit-rollup` | 11/11 intervals pass, bucket + accessors pass |

---

## What is Stubbed / Incomplete

| Component | Status | What's Missing |
|-----------|--------|----------------|
| Phase 5 (Market Structure) | 📋 Ready | **UNBLOCKED** - Price Feed complete, ready to implement |
| Registry Consolidation (Phase 3) | 📋 Ready | Remove hardcoded indicator enums (prereq for MS) |
| Promotion automation | 📋 Stubbed | Manual process only |
| Drift detection (Phase 5 Audit) | 📋 Future | Baseline storage system |
| Live trading validation | 📋 Incomplete | Demo tested, live untested |
| Agent module | ❌ Not started | Future phase |

---

## Top 10 Risks / Unknowns

| # | Risk | Severity | Mitigation |
|---|------|----------|------------|
| 1 | Live trading untested | HIGH | Validate on DEMO extensively first |
| 2 | Slippage model accuracy | MEDIUM | Default is conservative, validated in backtests |
| 3 | Funding rate timing | MEDIUM | Aligned with Bybit 8h intervals |
| 4 | Liquidation model accuracy | MEDIUM | Uses Bybit MMR formula |
| 5 | Rate limiting in production | MEDIUM | Current limits conservative |
| 6 | Strategy overfitting | MEDIUM | Use validation periods, multiple symbols |
| 7 | Market regime changes | MEDIUM | Monitor performance, adjust strategies |
| 8 | MTF alignment edge cases | LOW | Extensively tested, determinism verified |
| 9 | Indicator registry completeness | LOW | 42 indicators covered |
| 10 | DuckDB concurrency | LOW | Single-writer pattern |

---

## Recently Resolved Issues

| Issue | Status | Date | Document |
|-------|--------|------|----------|
| Metrics v1/v2 consolidation | ✅ COMPLETE | 2026-01-01 | Single unified BacktestMetrics with 59 fields |
| High-value quant metrics missing | ✅ FIXED | 2026-01-01 | Added tail risk, leverage, MAE/MFE tracking |
| IdeaCard value flow validation | ✅ COMPLETE | 2026-01-01 | docs/todos/IDEACARD_VALUE_FLOW_FIX_PHASES.md |
| Legacy execution config remnants | ✅ CLEANED | 2026-01-01 | ExecutionConfig simplified, dead code removed |
| Price Feed (1m) + Preflight | ✅ COMPLETE | 2025-12-31 | docs/todos/archived/2025-12-31/PRICE_FEED_1M_PREFLIGHT_PHASES.md |
| Engine modular refactor | ✅ COMPLETE | 2025-12-30 | docs/todos/archived/2025-12-30/ENGINE_MODULAR_REFACTOR_PHASES.md |
| Backtester fixes (6 issues) | ✅ COMPLETE | 2025-12-30 | docs/todos/archived/2025-12-30/BACKTESTER_FIXES_PHASE1.md |
| Max Drawdown % bug (tied maxima) | ✅ FIXED | 2025-12-18 | archived/2025-12-18/BACKTEST_FINANCIAL_METRICS_MTM_EQUITY_PHASES.md |
| Calmar ratio (arithmetic vs geometric) | ✅ FIXED | 2025-12-18 | archived/2025-12-18/BACKTEST_FINANCIAL_METRICS_MTM_EQUITY_PHASES.md |
| TF annualization silent defaults | ✅ FIXED | 2025-12-18 | archived/2025-12-18/BACKTEST_FINANCIAL_METRICS_MTM_EQUITY_PHASES.md |
| Refactor cleanup (legacy paths) | ✅ COMPLETE | 2025-12-18 | docs/todos/REFACTOR_BEFORE_ADVANCING.md |
| Backtest smoke test function conflict | ✅ FIXED | 2025-12-18 | Function name conflict resolved, Unicode encoding fixed |
| Input-source routing (volume/open/high/low) | ✅ FIXED | 2025-12-17 | docs/todos/P0_INPUT_SOURCE_ROUTING_FIX.md |
| Preflight/Engine warmup mismatch | ✅ FIXED | 2025-12-17 | docs/todos/WARMUP_SYNC_FIX.md |

**No Current P0 Blockers** - All critical issues resolved

---

## Next Steps (Canonical Roadmap)

**Current Status:** Backtest pipeline validated and production-ready ✅
**Price Feed (1m) + Preflight:** ✅ Complete (2025-12-31) - 1m quote stream, rollups, mandatory preflight
**Engine Modular Refactor:** ✅ Complete (2025-12-30) - engine.py reduced from 2,236 to 1,154 lines across 8 modules
**Backtester Fixes Phase 1:** ✅ Complete (2025-12-30) - 6 critical fixes applied, all tests passing

### 🔜 NEXT: Market Structure Features (Phase 5)

**Canonical Document:** `docs/todos/ARRAY_BACKED_HOT_LOOP_PHASES.md`
**Status:** Phases 1-4 ✅ Complete, Phase 5 📋 **UNBLOCKED AND READY**
**Prerequisites (all complete):**
- ✅ Price Feed (1m) + Preflight phase complete (2025-12-31)
- ✅ Engine Modular Refactor complete (2025-12-30)
- ✅ Backtester Fixes complete (2025-12-30)

**Available Resources:**
- `px.rollup.*` accessors: `rollup_min_1m`, `rollup_max_1m`, `rollup_bars_1m`, etc.
- `QuoteState`: Last trade proxy (`px.last.*`)
- Mandatory 1m coverage enforced by preflight

**Recommended Prerequisite:** Registry Consolidation (`docs/todos/REGISTRY_CONSOLIDATION_PHASES.md`) - Remove hardcoded indicator enums before adding market structure indicators.

| Task | Effort | Status |
|------|--------|--------|
| Registry Consolidation (Phase 3) | 4h | 📋 Ready (recommended first) |
| Market Structure enhancements | 16h | 📋 Ready |
| Additional performance optimizations | 8h | Pending |

---

## Consolidated Next Actions (All Active TODOs)

### Immediate Next (Priority 1) - ALL UNBLOCKED

**📋 Registry Consolidation (Recommended First)**
- **Document**: `docs/todos/REGISTRY_CONSOLIDATION_PHASES.md`
- **Status**: Phases 0-2 ✅, Phase 3 📋 READY
- **Effort**: ~4 hours
- **Purpose**: Remove hardcoded indicator enums before adding market structure indicators

**📋 Market Structure Features (Phase 5)**
- **Document**: `docs/todos/ARRAY_BACKED_HOT_LOOP_PHASES.md`
- **Status**: Phases 1-4 ✅, Phase 5 📋 **UNBLOCKED**
- **Effort**: ~16-24 hours
- **Prerequisites**: ✅ All complete (Price Feed, Engine Refactor, Backtester Fixes)

**📋 Market Structure Integration Review**
- **Document**: `docs/todos/MARKET_STRUCTURE_INTEGRATION_REVIEW.md`
- **Status**: 📋 READY FOR REVIEW
- **Purpose**: Code review to identify edge cases before Phase 5 implementation

### Future Enhancements (Priority 2 - Not Blocking)

**📋 Backtest Analytics (Phases 4-6)**
- **Document**: `docs/todos/BACKTEST_ANALYTICS_PHASES.md`
- **Status**: Phases 1-3 ✅ Complete, Phases 4-6 📋 PENDING
- **Scope**: Time-based analytics, benchmark comparison, enhanced CLI display
- **Note**: Future enhancement, not blocking any other work

### Ongoing Work (Priority 3)

**Strategy Development**
- Create production strategies
- Backtest validation runs
- Performance analysis

**Live Trading Preparation**
- Extended demo mode testing (8h)
- Risk manager validation (4h)
- Live data feed integration (4h)

---

## Validation Checklist (Production Ready)

- [x] All smoke tests pass (`--smoke full`)
- [x] Phase 6 backtest smoke tests pass (6/6 tests with determinism)
- [x] Toolkit contract audit passes (42/42)
- [x] Math parity audit passes (P0 input-source fixed 2025-12-17)
- [x] Financial metrics audit passes (`backtest metrics-audit` 6/6)
- [x] Snapshot plumbing audit passes
- [x] Artifact validation gates active (automatic HARD FAIL)
- [x] Determinism verification available (`verify-determinism --re-run`)
- [x] Production pipeline validated (5 IdeaCards, all gates passed)
- [x] No linter errors
- [x] Documentation updated (January 1, 2026)
- [x] Refactor cleanup complete ✅
- [x] Engine modular refactor complete ✅ (2025-12-30)
- [x] Backtester fixes Phase 1 complete ✅ (2025-12-30)
- [x] Price Feed (1m) + Preflight complete ✅ (2025-12-31)
- [x] Metrics consolidation complete ✅ (2026-01-01)
- [x] IdeaCard value flow complete ✅ (2026-01-01)

---

## Environment Setup

```bash
# Clone and install
git clone <repo>
cd TRADE
pip install -r requirements.txt

# Configure
cp env.example api_keys.env
# Edit api_keys.env with your Bybit keys

# Verify
python trade_cli.py --smoke data
```

**Required Keys:**
- `BYBIT_LIVE_DATA_API_KEY` — Data operations
- `BYBIT_DEMO_API_KEY` — Demo trading (recommended for testing)
- `BYBIT_LIVE_API_KEY` — Live trading (use with caution)

---

## Quick Reference

| Topic | Document |
|-------|----------|
| Start here | `docs/DOCS_INDEX.md` |
| Current state | `docs/contracts/state_of_the_union.md` |
| Architecture | `docs/architecture/ARCH_SNAPSHOT.md` |
| Domains | `docs/domains/DOMAIN_MAP.md` |
| Modules | `docs/modules/MODULE_NOTES.md` |
| Data | `docs/data/DATA_MODULE.md` |
| Audit | `docs/audits/AUDIT_MODULE.md` |
| Strategy Factory | `docs/strategy_factory/STRATEGY_FACTORY.md` |
| AI Guidance | `CLAUDE.md` |

---

