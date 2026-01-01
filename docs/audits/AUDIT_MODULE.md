# TRADE Audit Module

**STATUS:** CANONICAL  
**PURPOSE:** Audit module documentation: gates, checks, outcomes, classification  
**LAST UPDATED:** December 18, 2025

---

## Overview

The Audit module provides validation gates and verification tools for the TRADE trading bot. It ensures correctness, determinism, and math parity across the backtesting pipeline.

**Design Principle:** CLI-only validation. No pytest files exist in this codebase.

**Key Locations:**
- `src/backtest/audit_*.py` — Parity audit implementations
- `src/backtest/toolkit_contract_audit.py` — Indicator contract audit
- `src/backtest/gates/*.py` — Validation gates
- `src/backtest/artifacts/` — Artifact verification (validation, determinism, pipeline signature)
- `src/backtest/preflight/` — Preflight gate (data coverage, warmup)

---

## Audit Surfaces

| Surface | What is Audited | Key Files |
|---------|-----------------|-----------|
| Indicator Math | pandas_ta parity for all indicators | `audit_math_parity.py` |
| Snapshot Plumbing | Feature access via get_feature() | `audit_snapshot_plumbing_parity.py` |
| Indicator Contract | Output schema for all indicator types | `toolkit_contract_audit.py` |
| Artifact Integrity | Parquet/JSON output validation | `artifacts/artifact_standards.py` |
| Artifact Validation | Post-run file existence and structure | `artifacts/artifact_standards.py` |
| Pipeline Signature | Production pipeline proof | `artifacts/pipeline_signature.py` |
| Determinism | Re-run hash comparison | `artifacts/determinism.py` |
| Financial Metrics | Math correctness (drawdown, Calmar, etc.) | `metrics.py` (via `metrics-audit` CLI) |
| Data Health | OHLCV quality, gaps, coverage | `runtime/data_health.py`, `preflight/` |
| Production Imports | No forbidden imports in production | `gates/production_first_import_gate.py` |

---

## Validation Gates Overview

The audit system implements gates at multiple stages:

### Pre-Run Gates (Before Backtest Execution)

| Gate | Command | Acceptance Criteria |
|------|---------|---------------------|
| Contract Validation | `validate_idea_card_full()` (automatic) | All schema checks pass |
| Preflight Gate | `backtest preflight --idea-card <ID>` (automatic) | Data coverage + warmup sufficient |
| Auto-Sync | `--fix-gaps` flag (default enabled) | Missing data fetched automatically |

### Post-Run Gates (Automatic After Every Backtest)

| Gate | When | Acceptance Criteria |
|------|------|---------------------|
| Artifact Validation | After every `backtest run` | All required files exist with correct structure |
| Pipeline Signature | After every `backtest run` | `config_source == "IdeaCard"`, `uses_system_config_loader == False` |
| Hash Recording | After every `backtest run` | `trades_hash`, `equity_hash`, `run_hash` stored in `result.json` |

**Behavior:** Missing or invalid artifacts cause **HARD FAIL** (not warning).

### Pre-Merge Gates (MANDATORY)

These gates must pass before any merge to `src/backtest/`:

| Gate | Command | Acceptance Criteria |
|------|---------|---------------------|
| Toolkit Contract | `python trade_cli.py backtest audit-toolkit` | 42/42 indicators pass |
| Math Parity | `python trade_cli.py backtest math-parity --idea-card <ID> --start <date> --end <date>` | 0 failures, max_diff < 1e-8 |
| Snapshot Plumbing | `python trade_cli.py backtest audit-snapshot-plumbing --idea-card <ID> --start <date> --end <date>` | 0 failures |
| Financial Metrics | `python trade_cli.py backtest metrics-audit` | 6/6 test scenarios pass |

**Rule:** Regression = STOP. Fix before proceeding.

### Optional Verification Gates

| Gate | Command | Acceptance Criteria |
|------|---------|---------------------|
| Determinism Verification | `backtest verify-determinism --run <path> --re-run` | Hashes match (identical results) |
| Artifact Parity | `backtest verify-suite --compare-csv-parquet` | CSV ↔ Parquet consistency |

---

## Gate Definitions

### Gate 1: Toolkit Contract Audit

**Purpose:** Validate all registered indicators have correct output contracts

**Trigger Point:** Pre-merge, on-demand

**What it Checks:**
- All 42+ indicator types registered
- Output keys match expected schema
- No missing params or schema drift
- Multi-output indicators produce all expected columns

**Pass Artifact:** JSON report with pass/fail per indicator

**Severity:** BLOCKER — merge blocked if any indicator fails

**Current Location:** `src/backtest/toolkit_contract_audit.py`

---

### Gate 2: Math Parity Audit (Phase 2)

**Purpose:** Verify FeatureFrameBuilder output matches fresh pandas_ta computation

**Trigger Point:** Pre-merge, after indicator changes

**What it Checks:**
- Indicator values match reference implementation
- NaN masks identical
- Values within tolerance (1e-8)
- All timeframes and input sources covered

**Pass Artifact:** JSON report with max_diff per indicator

**Severity:** BLOCKER — math divergence is critical

**Current Location:** `src/backtest/audit_math_parity.py`

**Status:** ✅ **FIXED** (December 17, 2025) — Input-source routing bug resolved. All input sources (volume, open, high, low, close) now route correctly.

**See:** `docs/todos/P0_INPUT_SOURCE_ROUTING_FIX.md` for details.

---

### Gate 3: Snapshot Plumbing Audit (Phase 4)

**Purpose:** Verify RuntimeSnapshotView accessor correctness

**Trigger Point:** Pre-merge, after snapshot changes

**What it Checks:**
- `get_feature(key, tf_role, offset)` returns correct values
- TF routing correct (exec/htf/mtf)
- Offset semantics correct
- Forward-fill behavior verified
- 39,968 comparisons in reference test

**Pass Artifact:** JSON report with comparison count, failure count

**Severity:** BLOCKER — snapshot bugs cause silent incorrect results

**Current Location:** `src/backtest/audit_snapshot_plumbing_parity.py`

---

### Gate 4: Production First Import Gate

**Purpose:** Prevent forbidden imports in production code

**Trigger Point:** CI, on-demand

**What it Checks:**
- No `import pdb` in production
- No test-only imports leaked
- No development dependencies in production paths

**Pass Artifact:** Gate result (pass/fail with violations)

**Severity:** WARNING — logged but may not block

**Current Location:** `src/backtest/gates/production_first_import_gate.py`

---

### Gate 5: Data Preflight

**Purpose:** Validate data coverage and warmup before backtest

**Trigger Point:** Pre-backtest (automatic in `backtest run`)

**What it Checks:**
- Sufficient data for date range
- Warmup coverage adequate (computed across all TFs)
- No critical gaps (with auto-sync via `--fix-gaps`)
- All required TFs present (exec, htf, mtf)
- Warmup cap validation (MAX_WARMUP_BARS = 1000)

**Pass Artifact:** Preflight report JSON

**Severity:** BLOCKER for backtest run

**Current Location:** `src/backtest/preflight/`

**Auto-Sync:** `--fix-gaps` flag (default enabled) automatically fetches missing data before validation.

---

### Gate 6: Artifact Validation (Post-Run)

**Purpose:** Verify all required output files exist with correct structure

**Trigger Point:** After successful backtest execution (automatic)

**What it Checks:**
- `equity.parquet` exists with `ts_ms` column
- `trades.parquet` exists with required columns
- `result.json` exists with metrics
- `run_manifest.json` exists with `eval_start_ts_ms`
- `pipeline_signature.json` exists and is valid

**Pass Artifact:** Validation result in ToolResult.data.artifact_validation

**Severity:** **HARD FAIL** if any artifact missing or invalid (not warning)

**Current Location:** `src/backtest/artifacts/artifact_standards.py`

**Integration:** Automatic after every `backtest run` (can disable with `--no-validate`)

---

### Gate 7: Pipeline Signature Validation

**Purpose:** Prove production pipeline was used (no manual overrides or "cheating")

**Trigger Point:** After successful backtest execution (automatic)

**What it Checks:**
- `config_source == "IdeaCard"` (not legacy YAML)
- `uses_system_config_loader == False` (not legacy loader)
- `placeholder_mode == False` (not test mode)
- `feature_keys_match == True` (indicators match declaration)

**Pass Artifact:** Pipeline signature JSON

**Severity:** **HARD FAIL** if missing or invalid

**Current Location:** `src/backtest/artifacts/pipeline_signature.py`

**Integration:** Part of artifact validation gate

---

### Gate 8: Determinism Verification

**Purpose:** Prove re-running same inputs produces identical outputs

**Trigger Point:** Manual verification or CI/CD

**What it Checks:**
- Re-run produces identical results (hash comparison)
- `trades_hash` matches
- `equity_hash` matches
- `run_hash` matches
- `idea_hash` matches

**Pass Artifact:** Comparison report (PASS if identical, FAIL with diff if not)

**Severity:** Report only (does not block backtest)

**Current Location:** `src/backtest/artifacts/determinism.py`

**Command:** `backtest verify-determinism --run <path> --re-run`

---

### Gate 9: Financial Metrics Audit

**Purpose:** Validate financial math correctness (drawdown, Calmar, CAGR, etc.)

**Trigger Point:** Manual validation or CI/CD

**What it Checks:**
- Max Drawdown % correctness (independent maxima tracking)
- Calmar ratio consistency (geometric CAGR, not arithmetic)
- Timeframe annualization strictness (no silent defaults)
- Edge case handling (zero volatility, zero drawdown)

**Pass Artifact:** 6/6 test scenarios pass

**Severity:** Report only (does not block backtest)

**Current Location:** `src/backtest/metrics.py` (via CLI command)

**Command:** `backtest metrics-audit`

---

## Smoke Tests

| Mode | Command | Scope |
|------|---------|-------|
| Full | `python trade_cli.py --smoke full` | Data + trading + diagnostics |
| Data | `python trade_cli.py --smoke data` | Data builder only |
| Data Extensive | `python trade_cli.py --smoke data_extensive` | Clean DB, gaps, sync, heal |
| Orders | `python trade_cli.py --smoke orders` | All order types (DEMO) |
| Live Check | `python trade_cli.py --smoke live_check` | Connectivity (LIVE keys required) |
| Backtest | `python trade_cli.py --smoke backtest` | Backtest pipeline |
| Metadata | `python trade_cli.py backtest metadata-smoke` | Indicator metadata system |

---

## Audit Outcomes

### Current Status

| Gate | Status | Last Run | Notes |
|------|--------|----------|-------|
| Contract Validation | ✅ PASS | Dec 18, 2025 | All schema checks pass |
| Preflight Gate | ✅ PASS | Dec 18, 2025 | Auto-sync integrated, warmup validated |
| Toolkit Contract | ✅ PASS | Dec 18, 2025 | 42/42 indicators |
| Math Parity | ✅ PASS | Dec 18, 2025 | P0 input-source bug fixed |
| Snapshot Plumbing | ✅ PASS | Dec 18, 2025 | 39,968 comparisons, 0 failures |
| Artifact Validation | ✅ PASS | Dec 18, 2025 | Automatic HARD FAIL active |
| Pipeline Signature | ✅ PASS | Dec 18, 2025 | Production pipeline proven |
| Determinism Verification | ✅ PASS | Dec 18, 2025 | Re-run hash comparison works |
| Financial Metrics | ✅ PASS | Dec 18, 2025 | 6/6 test scenarios pass |
| Data Preflight | ✅ PASS | Dec 18, 2025 | All checks pass |

### Recently Resolved (December 17-18, 2025)

**P0 Input-Source Routing Bug** ✅ FIXED
- **Location:** `src/backtest/features/feature_frame_builder.py` lines 633, 674
- **Symptom:** `volume_sma` showed 102K discrepancy vs pandas_ta
- **Root Cause:** Non-"close" input sources routed to wrong data column
- **Fix:** Input-source routing logic corrected
- **Status:** All input sources (volume, open, high, low, close) now route correctly
- **Documentation:** `docs/todos/P0_INPUT_SOURCE_ROUTING_FIX.md`

**Max Drawdown % Bug** ✅ FIXED (December 18, 2025)
- **Issue:** Max DD% was tied to event that maximized DD absolute
- **Fix:** Independent maxima tracking (max_dd_abs and max_dd_pct tracked separately)
- **Documentation:** `docs/todos/archived/2025-12-18/BACKTEST_FINANCIAL_METRICS_MTM_EQUITY_PHASES.md`

**Calmar Ratio Bug** ✅ FIXED (December 18, 2025)
- **Issue:** Used arithmetic annualized return instead of geometric CAGR
- **Fix:** Proper CAGR formula: `(E_final / E_initial) ** (1/years) - 1`
- **Documentation:** `docs/todos/archived/2025-12-18/BACKTEST_FINANCIAL_METRICS_MTM_EQUITY_PHASES.md`

**No Current Blockers** — All critical issues resolved ✅

---

## Failure Classification

| Classification | Meaning | Action |
|----------------|---------|--------|
| BLOCKER | Critical correctness issue | Stop all work, fix immediately |
| ERROR | Functional issue | Fix before next release |
| WARNING | Non-critical issue | Track, fix when convenient |
| INFO | Observation only | Document, no action required |

---

## Audit Artifacts

| Artifact | Location | Purpose |
|----------|----------|---------|
| Toolkit audit report | CLI output / JSON | Contract validation results |
| Math parity report | CLI output / JSON | Parity check results |
| Plumbing audit report | CLI output / JSON | Snapshot access results |
| Preflight report | `run-NNN/preflight_report.json` | Pre-run validation (optional, CLI runs own) |
| Pipeline signature | `run-NNN/pipeline_signature.json` | Provenance tracking (required) |
| Artifact validation | ToolResult.data.artifact_validation | Post-run validation results |
| Determinism report | CLI output / JSON | Re-run comparison results |
| Metrics audit report | CLI output / JSON | Financial math validation (6/6 tests) |
| Indicator metadata | `artifacts/indicator_metadata.json` | Indicator provenance |
| Result hashes | `result.json` (trades_hash, equity_hash, run_hash) | Determinism tracking |
| Run manifest | `run_manifest.json` (full_hash, idea_hash) | Input tracking |

---

## Determinism Verification

**Rule:** Same config + same data → identical output

**Verification Method:**
1. Run backtest with IdeaCard and window
2. Store hashes: `trades_hash`, `equity_hash`, `run_hash`, `idea_hash`
3. Re-run with `backtest verify-determinism --run <path> --re-run`
4. Compare hashes (must match exactly)
5. Report PASS if identical, FAIL with diff if not

**Hash Storage:**
- Input hash: `full_hash` in `run_manifest.json`
- Output hashes: `trades_hash`, `equity_hash`, `run_hash` in `result.json`

**Current Status:** ✅ Determinism verified for all tested configurations

**Command:** `backtest verify-determinism --run <path> --re-run`

**Integration:** Optional determinism check in smoke tests (`TRADE_SMOKE_INCLUDE_DETERMINISM=1`)

---

## Invariant Checks (Per-Bar)

These invariants are verified every bar in simulation:

```python
# Accounting invariants (simulator uses USDT, not USD)
assert equity_usdt == cash_balance_usdt + unrealized_pnl_usdt
assert free_margin_usdt == equity_usdt - used_margin_usdt
assert available_balance_usdt == max(0.0, free_margin_usdt)

# Timing invariants
assert snapshot.ts_close == bar.ts_close
assert snapshot.ts_close <= current_time  # No look-ahead

# OHLC invariants
assert bar.high >= bar.low
assert bar.high >= bar.open
assert bar.high >= bar.close
assert bar.low <= bar.open
assert bar.low <= bar.close

# Closed-candle only (no partial bar computation)
assert indicator_values_computed_on_closed_candles_only
assert htf_mtf_values_forward_fill_until_next_tf_close
```

---

## Recommended Consolidation

**Current State:** Audit code scattered in `src/backtest/` root

**Proposed Structure:**
```
src/backtest/audits/
├── __init__.py
├── math_parity.py           # was audit_math_parity.py
├── snapshot_plumbing.py     # was audit_snapshot_plumbing_parity.py
├── in_memory_parity.py      # was audit_in_memory_parity.py
├── artifact_verifier.py     # was artifact_parity_verifier.py
└── contract_audit.py        # was toolkit_contract_audit.py
```

**Benefits:**
1. Clear domain boundary
2. Easier discovery
3. Consistent with gates/ pattern

---

## CI Integration

All audit commands support `--json` flag for structured output:

```bash
python trade_cli.py backtest audit-toolkit --json
python trade_cli.py backtest math-parity --idea-card <ID> --start <date> --end <date> --json
```

**CI Pipeline (Recommended):**
1. Run toolkit contract audit
2. Run math parity audit (when unblocked)
3. Run snapshot plumbing audit
4. Fail pipeline if any gate fails

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
- End-to-end pipeline validated with 5 IdeaCards
- All 6 validation gates tested and verified
- Schema issues discovered and documented

**See**: `docs/todos/archived/2025-12-18/` for complete documentation

---

## Next Steps

### Immediate (Ready)

1. **Phase 5: Hot Loop Optimization** — Array-backed market structure for higher throughput
   - Document: `docs/todos/ARRAY_BACKED_HOT_LOOP_PHASES.md`
   - Status: Ready (P0 blocker resolved December 17, 2025)

### Short-Term (1-2 Weeks)

2. **Consolidate audit code** — Move to `src/backtest/audits/` (recommended structure)
3. **Add CI integration** — Automated gate checks on PR (GitHub Actions)
4. **Baseline storage for drift detection** — Store canonical results for key IdeaCards
   - Document: `docs/todos/archived/2025-12-18/POST_BACKTEST_AUDIT_GATES.md` (Phase 5)

### Medium-Term (Future)

5. **Expand parity coverage** — All input sources, all indicators (comprehensive validation)
6. **Automated promotion criteria** — Performance thresholds for strategy promotion

---

