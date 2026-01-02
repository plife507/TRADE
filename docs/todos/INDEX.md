# TRADE Active TODO Documents

**STATUS:** CANONICAL
**PURPOSE:** Index of active TODO phase documents for work tracking
**LAST UPDATED:** January 1, 2026 (Market Structure Stages 0-5.1 complete)

---

## TODO-Driven Execution (Mandatory)

Per project rules:
- **MUST NOT write code before TODO markdown exists** for the work
- Every code change MUST map to a TODO checkbox
- If new work is discovered mid-implementation: STOP → update TODOs → continue
- Work is NOT complete until TODOs are checked
- Completed phases are FROZEN — do not rewrite earlier phases

---

## Current State Summary

**BacktestMetrics System**: 62 comprehensive fields for leveraged futures trading
**Indicator Registry**: 42 indicators, string-based types, single source of truth
**CLI**: IdeaCard-first workflow with full menu coverage
**Validation**: All IdeaCards in `configs/idea_cards/_validation/` (21 cards)

---

## Active TODOs

### Priority 1: Ready to Execute

| Document | Status | Scope | Next Step |
|----------|--------|-------|-----------|
| [Market Structure Phases](MARKET_STRUCTURE_PHASES.md) | Stages 0-5.1 ✅, Stage 6 📋 READY | Market structure engine | Zone interaction OR unified state tracking |

### Priority 2: Completed / Superseded

| Document | Status | Scope |
|----------|--------|-------|
| [Array-Backed Hot Loop](ARRAY_BACKED_HOT_LOOP_PHASES.md) | Phases 1-4 ✅, Phase 5 ✅ SUPERSEDED | Hot loop refactor + market structure (now in MARKET_STRUCTURE_PHASES.md) |
| [Registry Consolidation](REGISTRY_CONSOLIDATION_PHASES.md) | Phases 0-2 ✅, Phase 3 ✅ SUPERSEDED | Indicator registry (structures use separate module) |

### Priority 3: Future Enhancements (Not Blocking)

| Document | Status | Scope |
|----------|--------|-------|
| [Backtest Analytics](BACKTEST_ANALYTICS_PHASES.md) | Phases 1-4 ✅, Phases 5-6 📋 pending | Benchmark comparison, enhanced CLI |

### Reference Documents (Not TODOs)

| Document | Purpose |
|----------|---------|
| [Market Structure Integration Review](MARKET_STRUCTURE_INTEGRATION_REVIEW.md) | Code review prompts for Phase 5 prep |
| [Comprehensive Indicator Test Matrix](COMPREHENSIVE_INDICATOR_TEST_MATRIX.md) | Test coverage reference (42 indicators) |

---

## Recently Archived (January 2026)

| Document | Completed | Scope |
|----------|-----------|-------|
| [Legacy Cleanup](archived/2026-01-01/LEGACY_CLEANUP_PHASES.md) | 2026-01-01 | Removed dual metrics, warmup_multiplier, dead methods |
| [Metrics Enhancement](archived/2026-01-01/METRICS_ENHANCEMENT_PHASES.md) | 2026-01-01 | 62-field BacktestMetrics (tail risk, leverage, MAE/MFE) |
| [IdeaCard Value Flow Fix](archived/2026-01-01/IDEACARD_VALUE_FLOW_FIX_PHASES.md) | 2026-01-01 | Fixed slippage_bps, MMR, fail-loud validation |
| [CLI Menu Tools Alignment](archived/2026-01-01/CLI_MENU_TOOLS_ALIGNMENT_PHASES.md) | 2026-01-01 | IdeaCard menus, audits submenu, tools refactor |

## Previously Archived (December 2025)

| Document | Completed | Scope |
|----------|-----------|-------|
| [Price Feed (1m) + Preflight](archived/2025-12-31/PRICE_FEED_1M_PREFLIGHT_PHASES.md) | 2025-12-31 | 1m quote stream + rollups + mandatory preflight |
| [Engine Modular Refactor](archived/2025-12-30/ENGINE_MODULAR_REFACTOR_PHASES.md) | 2025-12-30 | Split engine.py into 8 modules (2,236 → 1,154 lines) |
| [Backtester Fixes — Phase 1](archived/2025-12-30/BACKTESTER_FIXES_PHASE1.md) | 2025-12-30 | 6 fixes from function evaluation review |
| [Post-Backtest Audit Gates](archived/2025-12-18/POST_BACKTEST_AUDIT_GATES.md) | 2025-12-18 | Auto-sync, artifact validation, determinism |
| [Backtest Financial Metrics](archived/2025-12-18/BACKTEST_FINANCIAL_METRICS_MTM_EQUITY_PHASES.md) | 2025-12-18 | Drawdown, Calmar, TF strictness, funding metrics |
| [Production Pipeline Validation](archived/2025-12-18/PRODUCTION_PIPELINE_VALIDATION.md) | 2025-12-18 | 5 IdeaCards through full workflow validation |

---

## Key Metrics Reference

### BacktestMetrics (62 Fields)

**Core Performance (6)**: initial_equity, final_equity, net_profit, net_return_pct, benchmark_return_pct, alpha_pct

**Trade Statistics (16)**: total_trades, win_count, loss_count, win_rate, profit_factor, profit_factor_mode, avg_win_usdt, avg_loss_usdt, largest_win_usdt, largest_loss_usdt, expectancy_usdt, payoff_ratio, avg_trade_duration_bars, max_consecutive_wins, max_consecutive_losses, avg_trade_return_pct

**Long/Short (6)**: long_trades, short_trades, long_win_rate, short_win_rate, long_pnl, short_pnl

**Drawdown & Risk (8)**: max_drawdown_pct, max_drawdown_abs, max_drawdown_duration_bars, ulcer_index, sharpe, sortino, calmar, recovery_factor, omega_ratio

**Tail Risk (4)**: skewness, kurtosis, var_95_pct, cvar_95_pct

**Leverage (2)**: avg_leverage_used, max_gross_exposure_pct

**Trade Quality (4)**: mae_avg_pct, mfe_avg_pct, avg_winning_trade_duration_bars, avg_losing_trade_duration_bars

**Entry Friction (3)**: entry_attempts, entry_rejections, entry_rejection_rate

**Margin Stress (3)**: min_margin_ratio, margin_calls, closest_liquidation_pct

**Time (3)**: total_bars, bars_in_position, time_in_market_pct

**Fees & Funding (4)**: total_fees, total_funding_paid_usdt, total_funding_received_usdt, net_funding_usdt

**Costs (2)**: gross_profit, gross_loss

---

## Validation Commands

```bash
# Quick validation (no DB required)
python trade_cli.py backtest audit-toolkit       # 42/42 indicators
python trade_cli.py backtest metadata-smoke      # Indicator metadata

# IdeaCard workflow
python trade_cli.py backtest idea-card-normalize-batch --dir configs/idea_cards/_validation

# Full smoke (DB required)
$env:TRADE_SMOKE_INCLUDE_BACKTEST="1"; python trade_cli.py --smoke full
```

---

## Creating New TODOs

1. Create `docs/todos/NEW_FEATURE_PHASES.md`
2. Define phases with checkboxes
3. Include acceptance criteria per phase
4. Reference in this INDEX.md
5. Begin implementation only after TODO exists

**Template:**

```markdown
# Feature Name

**Status**: Phase 1 🔄 IN PROGRESS
**Created**: YYYY-MM-DD
**Goal**: One-line description

---

## Phase 1: First Phase

**Goal**: What this phase accomplishes

- [ ] 1.1 First task
- [ ] 1.2 Second task

**Acceptance**: How to verify phase is complete
```
