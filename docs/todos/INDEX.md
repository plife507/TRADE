# TRADE Active TODO Documents

**STATUS:** CANONICAL
**PURPOSE:** Index of active TODO phase documents for work tracking
**LAST UPDATED:** January 1, 2026 (Legacy Cleanup, Metrics Enhancement, IdeaCard Value Flow Fix complete; 59-field BacktestMetrics system)

---

## TODO-Driven Execution (Mandatory)

Per project rules:
- **MUST NOT write code before TODO markdown exists** for the work
- Every code change MUST map to a TODO checkbox
- If new work is discovered mid-implementation: STOP → update TODOs → continue
- Work is NOT complete until TODOs are checked
- Completed phases are FROZEN — do not rewrite earlier phases

---

## Active TODOs (Consolidated Next Actions)

### ✅ Recently Completed

| Document | Status | Scope | Effort |
|----------|--------|-------|--------|
| [Price Feed (1m) + Preflight Gate + Packet Injection](archived/2025-12-31/PRICE_FEED_1M_PREFLIGHT_PHASES.md) | ✅ ALL PHASES COMPLETE | 1m quote stream + rollups + mandatory preflight | ~28h |
| [Legacy Cleanup](LEGACY_CLEANUP_PHASES.md) | ✅ Phases 1-2, 9 COMPLETE; 7, 10 pending | Removed dual metrics systems, ExecutionConfig cleanup | ~8h |
| [Metrics Enhancement](METRICS_ENHANCEMENT_PHASES.md) | ✅ COMPLETE (Phases 1-4 + tail risk/leverage/MAE-MFE) | 59 comprehensive metrics for leveraged futures trading | ~12h |
| [IdeaCard Value Flow Fix](IDEACARD_VALUE_FLOW_FIX_PHASES.md) | ✅ ALL PHASES COMPLETE | Fixed slippage_bps, MMR, fail-loud validation | ~6h |

### 📋 Priority 1: Now Ready (Unblocked by Price Feed)

| Document | Status | Scope | Effort |
|----------|--------|-------|--------|
| [Array-Backed Hot Loop (Phase 5)](ARRAY_BACKED_HOT_LOOP_PHASES.md) | Phase 5 📋 READY | Market Structure Features | ~16-24h |
| [Registry Consolidation (Phase 3)](REGISTRY_CONSOLIDATION_PHASES.md) | Phases 0-2 ✅ DONE, Phase 3 📋 READY | Add market structure indicators | ~4h |
| [Market Structure Integration Review](MARKET_STRUCTURE_INTEGRATION_REVIEW.md) | 📋 READY | Code review doc (prerequisite review) | Review |

### 📋 Priority 3: Future Enhancements (Not Blocking)

| Document | Status | Scope | Effort |
|----------|--------|-------|--------|
| [Backtest Analytics](BACKTEST_ANALYTICS_PHASES.md) | Phases 4-6 📋 pending | Time-based analytics, benchmarks, enhanced CLI | TBD |

## Recently Completed TODOs (Last 30 Days)

| Document | Status | Scope | Archive Location |
|----------|--------|-------|-----------------|
| [Price Feed (1m) + Preflight](archived/2025-12-31/PRICE_FEED_1M_PREFLIGHT_PHASES.md) | ✅ COMPLETE (2025-12-31) | 1m quote stream + rollups + mandatory preflight | archived/2025-12-31/ |
| [Legacy Cleanup](LEGACY_CLEANUP_PHASES.md) | ✅ Phases 1-2, 9 COMPLETE (2025-12-31) | Removed dual metrics systems, ExecutionConfig cleanup | active/ |
| [Metrics Enhancement](METRICS_ENHANCEMENT_PHASES.md) | ✅ COMPLETE (2025-12-31) | Benchmark/alpha + tail risk + leverage (59 total fields) | active/ |
| [IdeaCard Value Flow Fix](IDEACARD_VALUE_FLOW_FIX_PHASES.md) | ✅ ALL PHASES COMPLETE (2025-12-31) | Fixed slippage_bps, MMR, fail-loud validation | active/ |
| [Engine Modular Refactor](archived/2025-12-30/ENGINE_MODULAR_REFACTOR_PHASES.md) | ✅ COMPLETE (2025-12-30) | Split engine.py into 8 modules (2,236 → 1,154 lines) | archived/2025-12-30/ |
| [Backtester Fixes — Phase 1](archived/2025-12-30/BACKTESTER_FIXES_PHASE1.md) | ✅ COMPLETE (2025-12-30) | 6 fixes from function evaluation review | archived/2025-12-30/ |
| [Post-Backtest Audit Gates](archived/2025-12-18/POST_BACKTEST_AUDIT_GATES.md) | ✅ COMPLETE (2025-12-18) | Auto-sync, artifact validation, determinism | archived/2025-12-18/ |
| [Backtest Financial Metrics](archived/2025-12-18/BACKTEST_FINANCIAL_METRICS_MTM_EQUITY_PHASES.md) | ✅ COMPLETE (2025-12-18) | Drawdown, Calmar, TF strictness, funding metrics | archived/2025-12-18/ |
| [Production Pipeline Validation](archived/2025-12-18/PRODUCTION_PIPELINE_VALIDATION.md) | ✅ COMPLETE (2025-12-18) | 5 IdeaCards through full workflow validation | archived/2025-12-18/ |
| [Refactor Before Advancing](archived/2025-12-18/REFACTOR_BEFORE_ADVANCING.md) | ✅ COMPLETE (2025-12-18) | Legacy cleanup, adapter deletion, CI wiring | archived/2025-12-18/ |
| [Warmup Sync Fix](archived/2025-12-17/WARMUP_SYNC_FIX.md) | ✅ COMPLETE (2024-12-17) | Preflight/Engine warmup synchronization | archived/2025-12-17/ |
| [P0 Input-Source Fix](archived/2025-12-17/P0_INPUT_SOURCE_ROUTING_FIX.md) | ✅ COMPLETE (2025-12-17) | Fixed volume/open/high/low indicators | archived/2025-12-17/ |
| [Preflight Backfill](archived/2024-12-17/PREFLIGHT_BACKFILL_PHASES.md) | ✅ COMPLETE (2024-12-17) | IdeaCard → Preflight → Engine integration | archived/2024-12-17/ |

---

## BacktestMetrics Enhancement Summary (2025-12-31)

**Total Fields**: 59 comprehensive metrics for leveraged futures backtesting

### Metric Categories

#### Core Performance (6 fields)
- Equity: `initial_equity`, `final_equity`, `net_profit`, `net_return_pct`
- Benchmark: `benchmark_return_pct`, `alpha_pct` (strategy vs buy-and-hold)

#### Trade Statistics (16 fields)
- Summary: `total_trades`, `win_count`, `loss_count`, `win_rate`, `profit_factor`, `profit_factor_mode`
- Size/Quality: `avg_win_usdt`, `avg_loss_usdt`, `largest_win_usdt`, `largest_loss_usdt`, `expectancy_usdt`, `payoff_ratio`
- Duration: `avg_trade_duration_bars`
- Streaks: `max_consecutive_wins`, `max_consecutive_losses`
- Directional: `long_trades`, `short_trades`, `long_win_rate`, `short_win_rate`, `long_pnl`, `short_pnl`

#### Drawdown & Risk (7 fields)
- Drawdown: `max_drawdown_pct`, `max_drawdown_abs`, `max_drawdown_duration_bars`, `ulcer_index` (pain-adjusted)
- Risk-Adjusted: `sharpe`, `sortino`, `calmar`, `recovery_factor`

#### Leveraged Trading Specifics (13 fields)
- **Tail Risk** (critical for leverage): `skewness`, `kurtosis`, `var_95_pct`, `cvar_95_pct`
- **Leverage Metrics**: `avg_leverage_used`, `max_gross_exposure_pct`
- **Entry Friction**: `entry_attempts`, `entry_rejections`, `entry_rejection_rate`
- **Margin Stress**: `min_margin_ratio`, `margin_calls`
- **Liquidation Proximity**: `closest_liquidation_pct`
- **Trade Quality**: `mae_avg_pct`, `mfe_avg_pct` (Maximum Adverse/Favorable Excursion)

#### Time Metrics (3 fields)
- `total_bars`, `bars_in_position`, `time_in_market_pct`

#### Fees & Funding (4 fields)
- Fees: `total_fees`
- Funding: `total_funding_paid_usdt`, `total_funding_received_usdt`, `net_funding_usdt`

### Key Features

1. **Proof-Grade Metrics**: Entry friction, margin stress, liquidation proximity validate strategy viability
2. **Tail Risk Analysis**: Skewness, kurtosis, VaR, CVaR critical for leverage risk management
3. **Benchmark Comparison**: Alpha calculation shows strategy outperformance vs buy-and-hold
4. **Trade Quality**: MAE/MFE show how trades behave before close (stop placement quality)
5. **Complete Export**: All 59 fields in `BacktestMetrics.to_dict()` for JSON/Parquet artifacts

**Source**: `src/backtest/types.py` (BacktestMetrics dataclass)
**Computation**: `src/backtest/metrics.py` (compute_backtest_metrics)

---

## Active TODO Details

### ✅ COMPLETE: Price Feed (1m) + Preflight Gate + Packet Injection

**Canonical Document**: `docs/todos/archived/2025-12-31/PRICE_FEED_1M_PREFLIGHT_PHASES.md`
**Status**: ✅ ALL PHASES COMPLETE (2025-12-31)
**Goal**: Add a 1m-driven "quote/ticker proxy" + rollups for simulator/backtest, and make 1m coverage a mandatory preflight requirement **before Market Structure work begins**.

**Completed Phases**:
- **Phase 1**: Preflight Gate — Mandatory 1m coverage + exec→1m mapping check
- **Phase 2**: Simulator Quote Stream — QuoteState dataclass + quote feed builder
- **Phase 3**: ExecRollupBucket + Packet Injection — Rollup accumulation in hot loop
- **Phase 4**: Validation + Documentation Lock — All gates passed

**Key Deliverables**:
- `QuoteState` dataclass with provenance tracking (`px.last.*`, `px.mark.*`)
- `ExecRollupBucket` with accumulate/freeze/reset (`px.rollup.*`)
- Snapshot accessors: `rollup_min_1m`, `rollup_max_1m`, `rollup_bars_1m`, etc.
- Data-fix now includes mandatory 1m sync
- Preflight fails fast when 1m coverage is missing

**Validation Gates (all passed)**:
1. ✅ **Preflight** hard-fails if 1m coverage/mapping is missing
2. ✅ **Quote feed functions** work with synthetic data
3. ✅ **Backtest smoke** passes with price-feed path enabled
4. ✅ **Full smoke** passes end-to-end

**Unblocks**: Market Structure features (Array-Backed Hot Loop Phase 5, Registry Consolidation Phase 3)

### Array-Backed Hot Loop Phases

**Current:** Phase 5 📋 READY (unblocked — Price Feed complete)

| Phase | Status | Scope |
|-------|--------|-------|
| Phase 1 | ✅ Complete | Array-backed snapshot prep |
| Phase 2 | ✅ Complete | Audit lock-in (contract + parity) |
| Phase 3 | ✅ Complete | Parquet migration (CSV → Parquet) |
| Phase 4 | ✅ Complete | Snapshot plumbing audit (39,968 comparisons) |
| Phase 5 | 📋 READY | Market Structure — P0 blocker resolved |

**Unblocked:** P0 Input-Source fix completed 2025-12-17

### Backtest Analytics Phases

**Current:** Phases 4-6 pending (future enhancement, not blocking)

| Phase | Status | Scope |
|-------|--------|-------|
| Phase 1 | ✅ Complete | Wire existing metrics to output |
| Phase 2 | ✅ Complete | Additional risk-adjusted metrics |
| Phase 3 | ✅ Complete | Detailed trade statistics |
| Phase 4 | 📋 Pending | Time-based analytics |
| Phase 5 | 📋 Pending | Benchmark comparison |
| Phase 6 | 📋 Pending | Enhanced CLI display |

---

## Archived TODOs

Completed TODO documents are archived in `docs/todos/archived/`.

For historical reference, see also `docs/_archived/todos__*.md` (legacy location).

---

## Creating New TODOs

When starting new work:

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

---

## Phase 2: Second Phase

...
```

---

