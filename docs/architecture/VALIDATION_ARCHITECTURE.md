# Validation Architecture Investigation

> **Date**: 2026-01-11
> **Status**: Investigation Complete - Action Plan Ready

---

## Executive Summary

**Problem**: Validation/audit code bypasses the backtest engine, creating divergent code paths that can have different bugs (e.g., VWAP ts_open issue existed in audit but not engine).

**Solution**: All validation must run through the actual BacktestEngine with synthetic data injection.

---

## Current State Analysis

### Audit Files Inventory

| Audit File | Uses Engine? | Data Source | Direct Calls |
|------------|--------------|-------------|--------------|
| `toolkit_contract_audit.py` | No | Synthetic OHLCV | `compute_indicator()` directly |
| `audit_math_parity.py` | No | Snapshot artifacts | `compute_indicator()` directly |
| `audit_in_memory_parity.py` | Partial | Engine DFs | `compute_indicator()` directly |
| `audit_fibonacci.py` | No | Synthetic BarData | `IncrementalFibonacci.validate_and_create()` |
| `audit_trend_detector.py` | No | Synthetic BarData | `IncrementalTrendDetector()` directly |
| `audit_zone_detector.py` | No | Synthetic BarData | `IncrementalZoneDetector()` directly |
| `audit_rolling_window.py` | No | Synthetic BarData | `IncrementalRollingWindow()` directly |
| `audit_rollup_parity.py` | Partial | Synthetic quotes | `ExecRollupBucket.accumulate()` directly |
| `audit_incremental_state.py` | No | Synthetic BarData | `TFIncrementalState()` directly |
| `audit_incremental_registry.py` | No | Mock data | Registry functions directly |
| `audit_primitives.py` | No | Synthetic floats | Data structure methods |
| `audit_snapshot_plumbing_parity.py` | **YES** | Real DB | Full engine run |
| `artifact_parity_verifier.py` | No | Post-run files | File comparison |
| `stress_test_suite.py` | Partial | Synthetic | Step 7 TODO (not implemented) |

**Only 1 of 14 audits fully uses the engine.**

---

## Indicator Computation Paths (5 Found)

```
PATH 1: ENGINE (Production) ✅
Play → FeatureFrameBuilder → compute_indicator(ts_open=✓)

PATH 2: TOOLKIT AUDIT ✅ (Fixed 2026-01-11)
Synthetic OHLCV → compute_indicator(ts_open=✓)

PATH 3: MATH PARITY AUDIT ❌ BUG
Snapshot artifacts → compute_indicator(ts_open=MISSING)

PATH 4: IN-MEMORY PARITY AUDIT ❌ BUG
Engine DFs → compute_indicator(ts_open=MISSING)

PATH 5: LEGACY indicators.py ✅
DataFrame → compute_indicator(ts_open=✓)
```

**2 additional ts_open bugs found** in `audit_math_parity.py` and `audit_in_memory_parity.py`.

---

## Synthetic Data Generators (6 Found)

| Location | Function | Used By |
|----------|----------|---------|
| `src/forge/validation/synthetic_data.py` | `generate_synthetic_candles()` | Stress test suite |
| `src/forge/audits/toolkit_contract_audit.py` | `generate_synthetic_ohlcv()` | Toolkit audit |
| `src/forge/audits/audit_rollup_parity.py` | `generate_synthetic_quotes()` | Rollup audit |
| `src/viz/api/indicators.py` | `generate_synthetic_ohlcv()` | Viz API |
| `src/cli/smoke_tests/*.py` | Inline generation | Smoke tests |
| `tests/synthetic/harness/snapshot.py` | `SyntheticSnapshot` | DSL tests |

**Should be unified into single canonical source.**

---

## Target Architecture

### Principle: Everything Through The Engine

```
                    CURRENT (Fragmented)
                    ====================

Validation Plays ──► Engine ──► Results ✅
Toolkit Audit ────► compute_indicator() directly ❌
Math Parity ──────► compute_indicator() directly ❌
Structure Audits ─► detector.update() directly ❌


                    TARGET (Unified)
                    =================

Validation Plays ─┐
Indicator Tests ──┼──► Engine ──► Synthetic Data ──► Results
Structure Tests ──┤               (injected)
Parity Checks ────┘
```

### Implementation Plan

#### Phase 1: Fix Remaining ts_open Bugs (Immediate)

Files to fix:
- `src/forge/audits/audit_math_parity.py:108-120`
- `src/forge/audits/audit_in_memory_parity.py:209-225`

#### Phase 2: Unify Synthetic Data (1-2 hours)

1. Consolidate all generators into `src/forge/validation/synthetic_data.py`
2. Add missing generator types:
   - `generate_synthetic_ohlcv_df()` - Single-TF DataFrame
   - `generate_synthetic_quotes()` - QuoteState list
   - `generate_synthetic_bars()` - BarData list
3. Standardize seed default to 42

#### Phase 3: Add Synthetic Data Injection to Engine (2-3 hours)

Add to `BacktestEngine`:

```python
def inject_synthetic_data(
    self,
    candles: SyntheticCandles,
) -> None:
    """Inject synthetic data, bypassing DuckDB."""
    self._synthetic_data = candles
    self._use_synthetic = True
```

Modify `engine_data_prep.py`:

```python
def prepare_backtest_frame_impl(...):
    if getattr(engine, '_use_synthetic', False):
        df = engine._synthetic_data.get_tf(config.tf)
    else:
        store = get_historical_store(env=config.data_build.env)
        df = store.get_ohlcv(...)
```

#### Phase 4: Migrate Audits to Engine Path (3-4 hours)

For each audit type, create corresponding validation Plays:

| Current Audit | Replacement |
|---------------|-------------|
| toolkit_contract_audit | V_IND_001 through V_IND_043 (one per indicator) |
| structure audits | V_STR_001 through V_STR_006 (one per structure type) |
| rollup parity | V_ROLLUP_001 (1m aggregation validation) |
| math parity | Subsumed by engine run + assertion |

#### Phase 5: Add Assertion-Based Validation (2 hours)

Extend `_test_metadata` in validation Plays:

```yaml
_test_metadata:
  validation_id: "V_IND_001"
  category: "indicator_contract"
  assertions:
    - type: "indicator_produces_output"
      indicator: "ema"
      output_key: "ema_14"
    - type: "no_nan_after_warmup"
      feature: "ema_14"
      warmup_bars: 14
```

---

## Benefits of Unified Architecture

| Aspect | Current | After Unification |
|--------|---------|-------------------|
| Code paths | 5 different | 1 (engine) |
| Bug surface | Multiple places | Single source |
| DB dependency | Audits: No, Plays: Yes | Configurable |
| Test speed | Fast (no engine) | Fast (synthetic data) |
| Divergence risk | High | None |
| Maintenance | 14 audit files | Validation Plays only |

---

## Immediate Actions

1. **Fix ts_open bugs** in 2 remaining audit files
2. **Create this document** as reference
3. **Update OPEN_BUGS.md** with new findings

---

## Files Reference

### To Modify (Phase 1)
- `src/forge/audits/audit_math_parity.py`
- `src/forge/audits/audit_in_memory_parity.py`

### To Unify (Phase 2)
- `src/forge/validation/synthetic_data.py` (canonical)
- `src/forge/audits/toolkit_contract_audit.py` (remove local generator)
- `src/forge/audits/audit_rollup_parity.py` (remove local generator)
- `src/viz/api/indicators.py` (import from canonical)

### To Extend (Phase 3)
- `src/backtest/engine.py` (add inject_synthetic_data)
- `src/backtest/engine_data_prep.py` (check for synthetic mode)

### To Create (Phase 4)
- `tests/validation/plays/indicators/V_IND_*.yml` (43 plays)
- `tests/validation/plays/structures/V_STR_*.yml` (6 plays)
