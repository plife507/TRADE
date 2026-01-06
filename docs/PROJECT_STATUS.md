# TRADE Project Status

**STATUS:** CANONICAL
**PURPOSE:** What runs today, what is stubbed, top risks, next steps
**LAST UPDATED:** January 4, 2026 (Legacy Plays removed, all blocks format)

---

## Current State Summary

| Component | Status | Notes |
|-----------|--------|-------|
| CLI | ✅ Production | All menus functional |
| Data Layer | ✅ Production | DuckDB, sync, heal working |
| Backtest Engine | ✅ Production | Modular architecture (8 modules), Stages 0-7 complete |
| Market Structure | ✅ Production | Swing, Trend, Zones, Zone Interaction, State Tracking |
| Incremental State | ✅ Production | O(1) hot loop access, 6 structures in registry |
| Derived Zones | ✅ Production | K slots + aggregates pattern (Phase 12) |
| MTF Support | ✅ Production | exec/htf/mtf with delay_bars |
| Simulated Exchange | ✅ Production | Bybit-aligned accounting |
| Preflight + Data-Fix | ✅ Production | Phase 6 CLI smoke tests validated + **mandatory 1m coverage** |
| 1m Price Feed | ✅ Production | QuoteState, ExecRollupBucket, px.rollup.* accessors |
| Artifact Standards | ✅ Production | ts_ms, eval_start_ts_ms, structured exports |
| Backtest Metrics | ✅ Production | **62 unified fields**: equity, drawdown, trade stats, risk-adjusted ratios, tail risk (skewness, kurtosis, VaR, CVaR), leverage metrics, MAE/MFE, benchmark alpha |
| Play Value Flow | ✅ Production | Fail-loud validation, explicit declarations, all phases complete |
| Blocks DSL | ✅ Production | v3.0.0 - nested all/any/not, 11 operators, window operators |
| Live Trading | ⚠️ Functional | Demo API tested, live not validated |
| Indicator System | ✅ Production | 42 indicators in registry, string-based types |
| Validation Suite | ✅ Production | 11 validation Plays (V_100+ blocks format only) |
| Strategy Factory | ⚠️ Partial | Plays work, promotion manual |
| Agent Module | ❌ Planned | Not started |

---

## Recent Completions (January 2026)

| Phase | Status | Date | Key Features |
|-------|--------|------|--------------|
| Legacy Cleanup | ✅ Complete | Jan 4 | All signal_rules Plays removed, blocks-only format |
| Derived Zones (Phase 12) | ✅ Complete | Jan 4 | K slots + aggregates, derived_zone detector |
| Mega-file Refactor | ✅ Complete | Jan 3 | data_tools, tool_registry, datetime_utils splits |
| Incremental State Architecture | ✅ Complete | Jan 3 | O(1) hot loop, Structure Registry, agent-composable blocks |
| 1m Evaluation Loop Refactor | ✅ Complete | Jan 2 | mark_price resolution, 1m TP/SL checking, validation cards |
| Market Structure Stages 0-7 | ✅ Complete | Jan 1 | Swing, Trend, Zones, Zone Interaction, State Tracking |
| State Tracking (Stage 7) | ✅ Complete | Jan 1 | SignalState, ActionState, GateState, BlockState machines |
| Zone Interaction (Stage 6) | ✅ Complete | Jan 1 | touched, inside, time_in_zone metrics |
| Zone Hardening (Stage 5.1) | ✅ Complete | Jan 1 | instance_id, duplicate key validation |
| Zones (Stage 5) | ✅ Complete | Jan 1 | Parent-scoped zones, demand/supply, state machine |
| Rule Evaluation (Stage 4) | ✅ Complete | Jan 1 | Compiled refs, 6 operators, ReasonCode enum |
| Play Integration (Stage 3) | ✅ Complete | Jan 1 | market_structure_blocks, enum tokens, preflight |
| Structure MVP (Stage 2) | ✅ Complete | Jan 1 | SwingDetector, TrendClassifier |
| MarkPriceEngine (Stage 1) | ✅ Complete | Jan 1 | price.mark.* implicit, SimMarkProvider |
| Schema Lock (Stage 0) | ✅ Complete | Jan 1 | StructureType, ZoneType enums, registry |
| Audit Swarm | ✅ Complete | Jan 1 | 12/16 P1 fixes applied, 33 open bugs tracked |
| Metrics Consolidation | ✅ Complete | Jan 1 | 62 unified BacktestMetrics fields |
| Play Value Flow | ✅ Complete | Jan 1 | Fail-loud validation, explicit declarations |
| Legacy Cleanup | ✅ Complete | Jan 1 | ExecutionConfig simplified, dead code removed |

### December 2025 Completions

| Phase | Status | Date | Key Features |
|-------|--------|------|--------------|
| Price Feed (1m) + Preflight | ✅ Complete | Dec 31 | Mandatory 1m coverage, QuoteState, ExecRollupBucket |
| Engine Modular Refactor | ✅ Complete | Dec 30 | Split engine.py into 8 modules (2,236 → 1,154 lines) |
| Backtester Fixes Phase 1 | ✅ Complete | Dec 30 | 6 fixes: HTF O(n)→O(log n), TF defaults raise errors |
| Post-Backtest Audit Gates | ✅ Complete | Dec 18 | Auto-sync (--fix-gaps), artifact validation |
| Backtest Financial Metrics | ✅ Complete | Dec 18 | Fixed Max DD%, proper CAGR/Calmar |

**See**: `docs/session_reviews/` for detailed implementation notes

---

## Structure Registry (6 Detectors)

| Type | Description | Outputs |
|------|-------------|---------|
| `swing` | Swing high/low detection | high_level, high_idx, low_level, low_idx, version |
| `fibonacci` | Fib retracement/extension | level_0.382, level_0.5, level_0.618, etc. |
| `zone` | Demand/supply zones | state, upper, lower, anchor_idx |
| `trend` | Trend classification | direction, strength, bars_in_trend |
| `rolling_window` | O(1) rolling min/max | value |
| `derived_zone` | Fib zones from pivots | K slots + aggregates (zone0_*, any_touched, etc.) |

---

## BacktestMetrics System (62 Unified Fields)

The backtest engine now outputs a comprehensive, production-ready metrics suite with **62 fields** covering all aspects of strategy performance. All v1/v2 terminology has been removed - there is now a single unified `BacktestMetrics` class.

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
python trade_cli.py backtest run --play <ID> --start <date> --end <date>
python trade_cli.py backtest preflight --play <ID> --fix-gaps
python trade_cli.py backtest indicators --play <ID> --print-keys

# Validation & Audits
python trade_cli.py backtest verify-determinism --run <path> --re-run
python trade_cli.py backtest metrics-audit
python trade_cli.py backtest audit-toolkit
python trade_cli.py backtest math-parity --play <ID> --start <date> --end <date>
python trade_cli.py backtest audit-snapshot-plumbing --play <ID> --start <date> --end <date>
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
| Streaming (Stage 8) | Future | Demo/Live websocket, real-time tick aggregation |
| Promotion automation | Stubbed | Manual process only |
| Drift detection (Phase 5 Audit) | Future | Baseline storage system |
| Live trading validation | Incomplete | Demo tested, live untested |
| Agent module | Not started | Future phase |

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

## Open Bugs (Post-Refactor Audit 2026-01-03)

| Priority | Open | Description |
|----------|------|-------------|
| P0 | 0 | No critical blockers |
| P1 | 2 | Config patterns (hasattr guards, hardcoded values) |
| P2 | 3 | Type safety (hasattr, dynamic access, type ignores) |
| P3 | 4 | Polish (deprecated code, comments, defaults) |

**Total Open**: 9 bugs (down from 72 fixed in previous audit)

**Previous Audit**: 72 bugs fixed (P0:7, P1:25, P2:28, P3:12) - archived

**P1 Open**:
- P1-01: Deprecated config pattern (hasattr guards) - 2h to fix
- P1-02: Hardcoded max_exposure_pct - 30m to fix

**See**: `docs/audits/OPEN_BUGS.md` for full catalog

---

## Recently Resolved Issues

| Issue | Status | Date | Document |
|-------|--------|------|----------|
| Legacy Plays removed | ✅ COMPLETE | 2026-01-04 | All signal_rules cards deleted, blocks-only |
| Derived Zones (Phase 12) | ✅ COMPLETE | 2026-01-04 | K slots + aggregates pattern |
| Mega-file Refactor | ✅ COMPLETE | 2026-01-03 | Phases 1-3 done |
| Market Structure Stages 0-7 | ✅ COMPLETE | 2026-01-01 | docs/todos/archived/2026-01-01/MARKET_STRUCTURE_PHASES.md |
| Audit Swarm P1 fixes (12/16) | ✅ COMPLETE | 2026-01-01 | docs/audits/2026-01-01/FIX_PLAN.md |
| Metrics v1/v2 consolidation | ✅ COMPLETE | 2026-01-01 | Single unified BacktestMetrics with 62 fields |
| High-value quant metrics missing | ✅ FIXED | 2026-01-01 | Added tail risk, leverage, MAE/MFE tracking |
| Play value flow validation | ✅ COMPLETE | 2026-01-01 | docs/todos/archived/2026-01-01/PLAY_VALUE_FLOW_FIX_PHASES.md |
| Legacy execution config remnants | ✅ CLEANED | 2026-01-01 | ExecutionConfig simplified, dead code removed |
| Price Feed (1m) + Preflight | ✅ COMPLETE | 2025-12-31 | docs/todos/archived/2025-12-31/PRICE_FEED_1M_PREFLIGHT_PHASES.md |
| Engine modular refactor | ✅ COMPLETE | 2025-12-30 | docs/todos/archived/2025-12-30/ENGINE_MODULAR_REFACTOR_PHASES.md |
| Backtester fixes (6 issues) | ✅ COMPLETE | 2025-12-30 | docs/todos/archived/2025-12-30/BACKTESTER_FIXES_PHASE1.md |

**No Current P0 Blockers** - All critical issues resolved

---

## Next Steps (Canonical Roadmap)

**Current Status:** Backtest Engine and Market Structure complete ✅
**Play Format:** All blocks DSL (v3.0.0), signal_rules deprecated and removed

### NEXT: Choose One

| Feature | Priority | Effort | Description |
|---------|----------|--------|-------------|
| **Phase 4 Refactor** | Next | 2h | Split play.py into focused modules |
| **Streaming (Stage 8)** | High | 16h+ | Demo/Live websocket integration |
| **BOS/CHoCH Detection** | Medium | 8h | Break of Structure / Change of Character |
| **Advanced Operators** | Medium | 4h | crosses_up, crosses_down, within_bps |
| **Agent Module** | Future | 40h+ | Automated strategy generation |

### Active Tracking Documents

| Document | Purpose |
|----------|---------|
| `docs/todos/TODO.md` | Active work tracking |
| `docs/todos/MEGA_FILE_REFACTOR.md` | Phase 4 refactor plan |
| `docs/audits/OPEN_BUGS.md` | Bug tracker |

---

## Validation Checklist (Production Ready)

- [x] All smoke tests pass (`--smoke full`)
- [x] Phase 6 backtest smoke tests pass (6/6 tests with determinism)
- [x] Toolkit contract audit passes (42/42 indicators)
- [x] Math parity audit passes (P0 input-source fixed 2025-12-17)
- [x] Financial metrics audit passes (`backtest metrics-audit` 6/6)
- [x] Snapshot plumbing audit passes
- [x] Artifact validation gates active (automatic HARD FAIL)
- [x] Determinism verification available (`verify-determinism --re-run`)
- [x] Production pipeline validated (5 Plays, all gates passed)
- [x] No linter errors
- [x] Documentation updated (January 4, 2026)
- [x] Refactor cleanup complete ✅
- [x] Engine modular refactor complete ✅ (2025-12-30)
- [x] Backtester fixes Phase 1 complete ✅ (2025-12-30)
- [x] Price Feed (1m) + Preflight complete ✅ (2025-12-31)
- [x] Metrics consolidation complete ✅ (2026-01-01)
- [x] Play value flow complete ✅ (2026-01-01)
- [x] Market Structure Stages 0-7 complete ✅ (2026-01-01)
- [x] Audit Swarm P1 fixes (12/16) complete ✅ (2026-01-01)
- [x] 11 validation Plays pass normalization ✅ (V_100+ blocks format only)
- [x] Incremental State Architecture complete ✅ (2026-01-03)
- [x] Derived Zones (Phase 12) complete ✅ (2026-01-04)
- [x] Legacy Plays removed ✅ (2026-01-04)

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
| AI Guidance | `CLAUDE.md` |
| Active TODOs | `docs/todos/TODO.md` |
| Architecture | `docs/architecture/` |
| Play Syntax | `docs/guides/PLAY_SYNTAX.md` |
| Bugs | `docs/audits/OPEN_BUGS.md` |

---
