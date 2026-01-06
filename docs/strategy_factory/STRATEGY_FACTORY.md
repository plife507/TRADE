# TRADE Strategy Factory

**STATUS:** CANONICAL
**PURPOSE:** Strategy Factory architecture: Plays, promotion loops, system hashes, playbooks
**LAST UPDATED:** December 18, 2025

---

## Overview

The Strategy Factory is the system for defining, testing, validating, and promoting trading strategies from concept to live trading.

**Current State:** Production-ready core infrastructure. Play system complete with full validation gates; promotion loop automation pending (manual process works).

---

## Definitions

### Play

A **declarative, self-contained strategy specification** that defines:
- What indicators/features the strategy needs (per timeframe)
- Position policy (long_only, short_only, long_short)
- Entry/exit rules (signal logic)
- Risk model (stop loss, take profit, sizing)
- Account configuration (starting equity, leverage, fees)

**Key Properties:**
- Explicit over implicit: No silent defaults
- Fail-fast: Validation at load time
- Machine-readable: YAML format, composable
- Decoupled from execution: Play declares intent, engine executes

**Canonical Location:** `strategies/plays/`

### System (Hash)

A **System** is a Play at a specific version, uniquely identified by a hash.

**Hash Components:**
- Play YAML content (normalized)
- Symbol
- Timeframe configuration
- Feature specifications
- Risk parameters

**Purpose:**
- Track which exact configuration produced which results
- Enable reproducibility
- Support promotion decisions

**Current Status:** Hash generation implemented (`src/backtest/artifacts/hashes.py`). Hashes are now used for:
- Determinism verification (`backtest verify-determinism --re-run`)
- Pipeline signature validation (proves production pipeline used)
- Result tracking in `result.json` (`trades_hash`, `equity_hash`, `run_hash`)
- Input tracking in `run_manifest.json` (`full_hash`, `play_hash`)

### Block / Strategy Instance

A **Block** is a family of related strategies (e.g., "EMA Crossover family").

A **Strategy Instance** is a specific parameterization of a Block (e.g., "EMA 9/21 on BTCUSDT 15m").

**Relationship:**
```
Block (family)
  └── Play (specific parameterization)
        └── System Hash (versioned snapshot)
              └── Backtest Run (execution)
                    └── Artifacts (results)
```

### Playbook

A **Playbook** is a collection of Blocks/Plays intended to run together as a portfolio.

**Current Status:** Not implemented. Future feature.

### Promotion Loop

The **Promotion Loop** is the workflow for advancing strategies through validation stages:

```
Concept
  ↓
Play (YAML definition)
  ↓
Backtest (hygiene window)
  ↓
Backtest (test window)
  ↓
Sim Validation (paper trading)
  ↓
Demo Trading (demo API)
  ↓
Live Trading (real funds)
```

**Current Status:** Manual process. Automated promotion not yet implemented.

---

## Current Implementation

### Implemented (✅)

| Component | Location | Status |
|-----------|----------|--------|
| Play dataclass | `src/backtest/play.py` | ✅ Complete |
| Play YAML builder | `src/backtest/play_yaml_builder.py` | ✅ Complete |
| FeatureSpec | `src/backtest/features/feature_spec.py` | ✅ Complete |
| Indicator Registry | `src/backtest/indicator_registry.py` | ✅ Complete |
| System hash | `src/backtest/artifacts/hashes.py` | ✅ Complete (used for determinism) |
| Backtest engine | `src/backtest/engine.py` | ✅ Complete |
| Artifact generation | `src/backtest/artifacts/` | ✅ Complete |
| Preflight gate | `src/backtest/preflight/` | ✅ Complete (auto-sync, warmup validation) |
| Artifact validation | `src/backtest/artifacts/artifact_standards.py` | ✅ Complete (automatic HARD FAIL) |
| Determinism verification | `src/backtest/artifacts/determinism.py` | ✅ Complete (`verify-determinism` CLI) |
| Pipeline signature | `src/backtest/artifacts/pipeline_signature.py` | ✅ Complete (proves production pipeline) |
| Financial metrics | `src/backtest/metrics.py` | ✅ Complete (audit-grade math) |

### Partially Implemented (⚠️)

| Component | Location | Status |
|-----------|----------|--------|
| Strategy registry | `src/strategies/registry.py` | Basic |
| Window presets | `src/backtest/window_presets.py` | Hygiene/test defined |

### Not Implemented (❌)

| Component | Notes |
|-----------|-------|
| Playbook | Future feature |
| Promotion automation | Manual process (works, automation pending) |
| Baseline storage | Hash comparison works, baseline storage for drift detection pending |
| Performance comparison | Manual (tools ready) |
| Agent integration | Future feature |

---

## Play Schema

```yaml
# Minimal Play structure
id: "BTCUSDT_15m_ema_crossover"
version: "1.0"

symbol: "BTCUSDT"
position_policy: "long_short"  # long_only, short_only, long_short

tf_configs:
  exec:
    timeframe: "15m"
    feature_specs:
      - indicator_type: ema
        output_key: ema_fast
        params:
          length: 9
      - indicator_type: ema
        output_key: ema_slow
        params:
          length: 21
  htf:  # Optional higher timeframe
    timeframe: "4h"
    feature_specs:
      - indicator_type: ema
        output_key: htf_ema_trend
        params:
          length: 50

account:
  starting_equity_usdt: 1000.0
  max_leverage: 10.0
  fee_model:
    taker_bps: 6.0
    maker_bps: 2.0

risk_model:
  stop_loss_atr_mult: 2.0
  take_profit_atr_mult: 3.0
  position_size_pct: 0.02

signal_rules:
  long_entry: "ema_fast > ema_slow and htf_ema_trend > prev_htf_ema_trend"
  long_exit: "ema_fast < ema_slow"
  short_entry: "ema_fast < ema_slow and htf_ema_trend < prev_htf_ema_trend"
  short_exit: "ema_fast > ema_slow"
```

---

## Validation Gates

The Strategy Factory implements a **multi-gate validation system** that ensures strategies meet quality standards before promotion. All gates are automated and integrated into the backtest workflow.

### Gate 1: Contract Validation (Syntax & Schema)

**When**: Before any backtest execution
**Command**: `validate_play_full()` (automatic in `backtest run`)

**Checks**:
- ✅ YAML parses correctly
- ✅ Required fields present (`id`, `symbol`, `tf_configs`, `account`, `risk_model`)
- ✅ Types match schema (timeframes, numeric ranges)
- ✅ FeatureSpec declarations valid (`output_key`, `indicator_type`, `params`)
- ✅ Risk model structure correct (`stop_loss.type`, `take_profit.type`, `sizing.model`)
- ✅ Signal rules format valid (`is_indicator_comparison` flag, operator types)
- ✅ Warmup caps enforced (MAX_WARMUP_BARS = 1000)

**Failure**: Hard fail with specific error messages

### Gate 2: Preflight Gate (Data Coverage & Warmup)

**When**: Before engine execution
**Command**: `backtest preflight --play <path>` (automatic in `backtest run`)

**Checks**:
- ✅ Historical data available for date range
- ✅ All timeframes have data (exec, htf, mtf)
- ✅ Warmup coverage sufficient (computed across all TFs)
- ✅ Gap detection (missing bars identified)
- ✅ Auto-sync available (`--fix-gaps` flag, default enabled)

**Output**: `PreflightReport` JSON with coverage details

**Failure**: Hard fail if data insufficient (unless `--fix-gaps` can resolve)

### Gate 3: Backtest Execution

**When**: During engine run
**Command**: `backtest run --play <path>`

**Checks**:
- ✅ Backtest completes without errors
- ✅ No NaN in critical paths (indicators, equity, trades)
- ✅ Accounting invariants maintained (equity = cash + unrealized PnL)
- ✅ Order execution valid (fills, fees, slippage)
- ✅ Risk limits enforced (leverage, position size)

**Failure**: Hard fail with error traceback

### Gate 4: Artifact Validation (Post-Run)

**When**: After successful backtest execution
**Command**: Automatic (can disable with `--no-validate`)

**Checks**:
- ✅ `equity.parquet` exists with `ts_ms` column
- ✅ `trades.parquet` exists with required columns
- ✅ `result.json` exists with metrics
- ✅ `run_manifest.json` exists with `eval_start_ts_ms`
- ✅ `pipeline_signature.json` exists and is valid

**Pipeline Signature Validation**:
- ✅ `config_source == "Play"` (not legacy YAML)
- ✅ `uses_system_config_loader == False` (not legacy loader)
- ✅ `placeholder_mode == False` (not test mode)
- ✅ `feature_keys_match == True` (indicators match declaration)

**Failure**: **HARD FAIL** if any artifact missing or invalid (not warning)

### Gate 5: Determinism Verification (Optional)

**When**: Manual verification or CI/CD
**Command**: `backtest verify-determinism --run <path> --re-run`

**Checks**:
- ✅ Re-run produces identical results (hash comparison)
- ✅ `trades_hash` matches
- ✅ `equity_hash` matches
- ✅ `run_hash` matches
- ✅ `play_hash` matches

**Output**: PASS if identical, FAIL with diff if not

**Purpose**: Proves reproducibility (no hidden state or randomness)

### Gate 6: Financial Metrics Audit (Optional)

**When**: Manual validation or CI/CD
**Command**: `backtest metrics-audit`

**Checks**:
- ✅ Max Drawdown % correctness (independent maxima)
- ✅ Calmar ratio consistency (geometric CAGR)
- ✅ Timeframe annualization strictness (no silent defaults)
- ✅ Edge case handling (zero volatility, zero drawdown)

**Output**: 6/6 test scenarios pass

### Gate 7: Performance Threshold (Future)

**When**: Before promotion to next stage
**Status**: Not yet automated (manual evaluation)

**Proposed Checks**:
- ⏳ Meets minimum Sharpe ratio (configurable)
- ⏳ Drawdown within limits (configurable)
- ⏳ Sufficient trade count for statistical significance
- ⏳ Win rate above threshold
- ⏳ Profit factor above threshold

**Future**: Automated promotion criteria based on these thresholds

---

## Artifact Output

Each backtest run produces a versioned folder with complete audit trail:

```
backtests/<play_id>/<symbol>/<hash>/
├── result.json              # Summary metrics (with trades_hash, equity_hash, run_hash)
├── trades.parquet           # Trade records (structured columns)
├── equity.parquet           # Equity curve (with ts_ms column)
├── run_manifest.json        # Run metadata (eval_start_ts_ms, full_hash, play_hash)
├── pipeline_signature.json  # Provenance (proves production pipeline used)
└── logs/                    # Execution logs (optional)
```

### Artifact Standards (Enforced)

**Equity Parquet**:
- Required column: `ts_ms` (millisecond timestamp)
- Columns: `ts_ms`, `equity_usdt`, `cash_balance_usdt`, `unrealized_pnl_usdt`, `realized_pnl_usdt`

**Trades Parquet**:
- Required columns: `entry_ts_ms`, `exit_ts_ms`, `entry_price`, `exit_price`, `size_usdt`, `net_pnl_usdt`
- Structured trade data for analysis

**Result JSON**:
- Financial metrics: `net_profit`, `net_return_pct`, `sharpe_ratio`, `max_dd_pct`, `calmar_ratio`
- Hash values: `trades_hash`, `equity_hash`, `run_hash` (for determinism)
- Trade statistics: `total_trades`, `win_rate`, `profit_factor`, `expectancy_usdt`

**Pipeline Signature JSON**:
- Proves production pipeline was used (not legacy paths)
- Validates: `config_source`, `uses_system_config_loader`, `placeholder_mode`, `feature_keys_match`
- **HARD FAIL** if missing or invalid

**Run Manifest JSON**:
- Input tracking: `full_hash` (input hash), `play_hash` (Play hash)
- Timing: `eval_start_ts_ms` (evaluation start timestamp)
- Configuration: `symbol`, `timeframe`, `window_start`, `window_end`

---

## Promotion Criteria (Proposed)

| Stage | Criteria | Gate |
|-------|----------|------|
| Concept → Play | YAML valid, features declared | Syntax |
| Play → Hygiene Backtest | Backtest completes, no errors | Execution |
| Hygiene → Test Backtest | Positive expectancy, reasonable drawdown | Performance |
| Test → Sim Validation | Consistent with backtest | Parity |
| Sim → Demo | No execution issues | Live test |
| Demo → Live | Confident in edge, risk acceptable | Manual |

---

## Play Locations

| Location | Purpose | Status |
|----------|---------|--------|
| `strategies/plays/` | Canonical production cards | ✅ Active |
| `strategies/plays/verify/` | Verification test cards | ✅ Active |
| `strategies/plays/_TEMPLATE.yml` | Template for new cards | ✅ Active |
| `src/strategies/plays/` | Examples/templates only | ⚠️ Misplaced |
| `src/strategies/strategies/` | Legacy configs | ⚠️ Misplaced |

**Recommendation:** Move or delete `src/strategies/plays/` and `src/strategies/strategies/`.

---

## Agent Integration Points (Future)

When the Agent module is implemented:

| Integration Point | Purpose |
|-------------------|---------|
| Play generation | AI generates Play from research |
| Backtest execution | Agent triggers backtest via ToolRegistry |
| Result interpretation | AI analyzes BacktestResult |
| Promotion decision | AI recommends promotion |
| Parameter optimization | AI suggests parameter changes |

**API Surface:** `src/tools/backtest_tools.py` via ToolRegistry

---

## Recent Completions (December 18, 2025)

✅ **Post-Backtest Audit Gates** (Phases 1-4 complete)
- Auto-sync integration (`--fix-gaps` flag, default enabled)
- Artifact validation (automatic HARD FAIL after every run)
- Determinism verification (`verify-determinism --re-run` CLI)
- Pipeline signature validation (proves production pipeline used)
- Smoke test integration (TEST 5 & TEST 6)

✅ **Backtest Financial Metrics** (All phases complete)
- Fixed Max Drawdown % bug (independent maxima tracking)
- Implemented proper CAGR/Calmar ratio (geometric, not arithmetic)
- Added TF strictness (no silent defaults, unknown TF raises error)
- Added funding metrics infrastructure
- Created `backtest metrics-audit` CLI command (6/6 tests pass)

✅ **Production Pipeline Validation** (All gates passed)
- 5 Plays created and validated (4 valid, 1 intentionally invalid)
- All 6 validation gates tested and verified
- End-to-end pipeline validated
- Schema issues discovered and documented

**See**: `docs/todos/archived/2025-12-18/` for complete documentation

---

## Next Steps

### Immediate (Ready to Start)

1. **Phase 5: Hot Loop Optimization** — Array-backed market structure for higher throughput
   - Document: `docs/todos/ARRAY_BACKED_HOT_LOOP_PHASES.md`
   - Status: Ready (P0 blocker resolved December 17, 2025)

### Short-Term (1-2 Weeks)

2. **Clean up Play locations** — Consolidate to `strategies/plays/`
   - Move or delete `src/strategies/plays/` and `src/strategies/strategies/`

3. **Define performance thresholds** — Minimum criteria for promotion
   - Sharpe ratio minimum
   - Drawdown limits
   - Trade count requirements
   - Win rate thresholds

### Medium-Term (Future)

4. **Baseline storage for drift detection** — Store canonical results for key Plays
   - Document: `docs/todos/archived/2025-12-18/POST_BACKTEST_AUDIT_GATES.md` (Phase 5)
   - Compare new runs to stored baselines
   - Integrate with CI (GitHub Actions)

5. **Build promotion automation** — Scripted stage transitions
   - Automated promotion based on performance thresholds
   - Integration with validation gates

6. **Add agent integration** — Play generation from research
   - AI generates Play from research notes
   - Automated backtest execution via ToolRegistry
   - Result interpretation and promotion recommendations

---

## Quick Reference

### Key Commands

```bash
# Preflight (data coverage, warmup)
python trade_cli.py backtest preflight --play <path> --fix-gaps

# Run backtest (with automatic validation)
python trade_cli.py backtest run --play <path> --start <date> --end <date>

# Verify determinism
python trade_cli.py backtest verify-determinism --run <path> --re-run

# Metrics audit
python trade_cli.py backtest metrics-audit

# Full smoke test
python trade_cli.py --smoke full
```

### Key Documents

| Document | Purpose |
|----------|---------|
| `docs/reviews/BACKTEST_SYSTEM_REVIEW.md` | Complete system review |
| `docs/todos/INDEX.md` | Active TODO tracking |
| `docs/PROJECT_STATUS.md` | Current state, blockers, next steps |
| `docs/todos/archived/2025-12-18/` | Today's completed work |

---

