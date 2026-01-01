# System Validation IdeaCard - Delivery Summary

**Date:** 2025-12-16  
**Objective:** Create a TEST-ONLY IdeaCard to validate architectural changes over long horizons (~1 year)

---

## Deliverables

### 1. IdeaCard: `BTCUSDT_1h_system_validation_1year.yml`

**Location:** `configs/idea_cards/BTCUSDT_1h_system_validation_1year.yml`

**Purpose:**
- Regression test for backtest engine architectural changes
- Validates array-backed engine, RuntimeSnapshotView, MTF routing, and Parquet artifacts
- Designed to break if system plumbing is compromised

**Key Characteristics:**
- **Instrument:** BTCUSDT (most liquid perpetual)
- **Horizon:** 1 year (full rolling period, e.g., 2024-01-01 to 2024-12-31)
- **Timeframes:** Exec 1h, HTF 4h, MTF 15m
- **Strategy:** Simple trend-following (EMA crossover + HTF trend filter + MTF RSI)
- **Risk:** Conservative (1% equity risk per trade, 2x ATR stops, 2:1 R:R)
- **Trade Count:** ~10-30 trades/year (regime-dependent)

**What It Tests:**
- ✅ 8,760+ hours of backtest execution without crashes
- ✅ Memory stability (no leaks over long runs)
- ✅ MTF alignment and forward-fill correctness
- ✅ Parquet artifact generation
- ✅ Determinism (repeated runs must match)
- ✅ Snapshot plumbing under deep history lookbacks

**What It Does NOT Test:**
- ❌ Strategy profitability (intentionally unoptimized)
- ❌ Funding cashflow PnL (not applied in current iteration)
- ❌ Live trading execution paths
- ❌ Parameter optimization

---

### 2. Full Guide: `SYSTEM_VALIDATION_LONG_HORIZON_TEST.md`

**Location:** `docs/guides/SYSTEM_VALIDATION_LONG_HORIZON_TEST.md`

**Contents:**
- Complete overview of what the test validates
- Step-by-step execution instructions
- Success/failure criteria and interpretation
- Troubleshooting guide for common issues
- Baseline regression testing workflow
- FAQ and related documentation references

**Use Cases:**
- Pre-merge validation for architectural changes
- Regression testing after refactors
- Onboarding new developers (demonstrates full stack)

---

### 3. Quick Start Guide: `SYSTEM_VALIDATION_QUICKSTART.md`

**Location:** `docs/guides/SYSTEM_VALIDATION_QUICKSTART.md`

**Contents:**
- Three-command validation workflow
- Prerequisites checklist
- Pass/fail criteria at a glance
- Determinism verification commands

**Use Cases:**
- Quick reference for experienced users
- CI/CD integration commands
- Post-change smoke testing

---

## Technical Design

### Strategy Logic (Intentionally Simple)

**Entry Rules:**

**LONG:**
1. Exec TF: Fast EMA(50) crosses above Slow EMA(200)
2. HTF: Price above HTF EMA(100) trend
3. MTF: RSI(14) > 40 (not oversold)

**SHORT:**
1. Exec TF: Fast EMA(50) crosses below Slow EMA(200)
2. HTF: Price below HTF EMA(100) trend
3. MTF: RSI(14) < 60 (not overbought)

**Exit Rules:**
- Opposite signal (EMA crossover reversal)
- ATR-based stop loss (2x ATR)
- Take profit at 2:1 R:R

### Timeframe Stack

| Role | TF | Warmup | Purpose |
|------|----|---------|----|
| Exec | 1h | 250 bars | Entry/exit signals |
| HTF | 4h | 150 bars | Trend bias filter |
| MTF | 15m | 100 bars | Momentum confirmation |

This exercises full MTF routing with three-level alignment.

### Indicators Used

All indicators are common and well-tested:
- EMA (3 instances: fast, slow, trend)
- ATR (for stop loss and position sizing)
- RSI (for momentum confirmation)

No exotic indicators that might introduce new failure modes.

---

## Validation Workflow

### Pre-Merge Checklist

Before merging changes to `src/backtest/*`, run:

```bash
# 1. Check IdeaCard structure
python trade_cli.py backtest indicators \
    --idea BTCUSDT_1h_system_validation_1year --print-keys

# 2. Validate data coverage
python trade_cli.py backtest preflight \
    --idea BTCUSDT_1h_system_validation_1year

# 3. Run full 1-year backtest
python trade_cli.py backtest run \
    --idea BTCUSDT_1h_system_validation_1year \
    --start 2024-01-01 --end 2024-12-31 --env live

# 4. Verify determinism (run twice, compare)
diff backtests/BTCUSDT_1h_system_validation_1year/BTCUSDT/run-001/result.json \
     backtests/BTCUSDT_1h_system_validation_1year/BTCUSDT/run-002/result.json
```

### Expected Outcomes

| Metric | Expected Value | Interpretation |
|--------|----------------|----------------|
| **Completion** | Success | No crashes or OOM errors |
| **Runtime** | < 5 minutes | Efficient array operations |
| **Trade count** | 10-30 | Signal logic working |
| **Artifacts** | All present | Parquet writers working |
| **Determinism** | Identical runs | No random state bugs |
| **Memory** | Flat | No leaks |

---

## Success Criteria

### ✅ Pass Conditions

1. Backtest completes without errors over 8,760+ hours
2. Memory usage remains stable (no growth over time)
3. All Parquet artifacts written correctly
4. MTF values forward-fill correctly between closes
5. Results are deterministic across repeated runs
6. No alignment drift between exec/HTF/MTF timeframes
7. Trade logs show valid HTF/MTF values at each entry
8. Runtime < 5 minutes on modern hardware

### ❌ Fail Indicators

| Symptom | Likely Root Cause |
|---------|-------------------|
| Crash/OOM | Memory leak in snapshot/array layer |
| Zero trades | MTF alignment broken or signal logic bug |
| Non-deterministic results | Random state or timestamp dependency |
| Missing artifacts | Parquet writer failure |
| MTF value errors | Forward-fill logic broken |
| Performance degradation | O(n²) behavior in hot loop |
| Alignment errors | TF conversion or bar indexing bug |

---

## Integration with Existing Tests

This test complements (does not replace) existing validation:

| Test Type | Scope | IdeaCard |
|-----------|-------|----------|
| **System validation** | Long-horizon stability | This IdeaCard |
| **Strategy validation** | Profitability/edge | MTF tradeproof IdeaCards |
| **Smoke tests** | Short-run correctness | Verify IdeaCards (e.g., `verify_ema_atr`) |
| **CLI validation** | All features | `--smoke full` |

This IdeaCard is specifically for **plumbing correctness**, not strategy performance.

---

## When to Use This Test

### Required (Pre-Merge)

Run before merging changes to:
- `src/backtest/engine.py` (backtest orchestrator)
- `src/backtest/runtime/` (RuntimeSnapshotView, FeedStore, TFContext)
- `src/backtest/sim/` (SimulatedExchange, pricing, ledger)
- `src/backtest/features/` (FeatureSpec, FeatureFrameBuilder)
- Artifact serialization (Parquet writers)
- Timeframe alignment logic

### Optional (Good Practice)

Run after:
- Major refactors in shared utilities
- DuckDB schema changes
- Dependency updates (pandas, numpy, polars)
- Performance optimizations in hot loops

---

## Design Constraints (No Code Changes Required)

This IdeaCard was designed to:
- ✅ Use only features already available in RuntimeSnapshotView
- ✅ Use only indicators in IndicatorRegistry
- ✅ Use only operators supported by signal condition evaluator
- ✅ Require NO engine, schema, or validator changes
- ✅ Work with current Parquet artifact format

**No code modifications needed to run this test.**

---

## Future Enhancements (Out of Scope)

Potential future improvements (NOT required for this delivery):
- Add funding cashflow validation (when funding PnL is modeled)
- Add multi-symbol tests (when multi-symbol backtesting is supported)
- Add cross-margin tests (when cross-margin mode is supported)
- Add intraday (1m/5m) tests for high-frequency plumbing

---

## Related Documentation

| Document | Purpose |
|----------|---------|
| `CLAUDE.md` | AI assistant guidance (domain-aware rules) |
| `docs/architecture/BACKTEST_MODULE_OVERVIEW.md` | Backtest engine architecture |
| `docs/todos/archived/SNAPSHOT_HISTORY_MTF_ALIGNMENT_PHASES.md` | MTF alignment implementation |
| `docs/architecture/ARTIFACT_STORAGE_FORMAT.md` | Parquet artifact specification |
| `docs/reviews/IDEACARD_YAML_STRUCTURE_REVIEW.md` | IdeaCard schema reference |

---

## Notes for Developers

### This IdeaCard is a Canary

If this test breaks:
1. **DO NOT** modify the IdeaCard to make it pass
2. **DO** investigate why the test broke
3. **FIX** the underlying bug, not the test

### This IdeaCard is NOT a Trading Strategy

- Profitability is irrelevant
- Win rate doesn't matter
- Sharpe ratio doesn't matter
- Parameter optimization is forbidden

**What matters:**
- Does it complete without errors?
- Are results deterministic?
- Are artifacts valid?

### Baseline Regression Testing

After architectural changes stabilize, establish a baseline:

```bash
# Run baseline
python trade_cli.py backtest run \
    --idea BTCUSDT_1h_system_validation_1year \
    --start 2024-01-01 --end 2024-12-31 --env live

# Save baseline
cp backtests/BTCUSDT_1h_system_validation_1year/BTCUSDT/run-001/result.json \
   docs/baselines/system_validation_1year_baseline.json
```

Future changes should produce **identical** results (exact trade count, timestamps, prices).

---

## Summary

This delivery provides:
1. **IdeaCard** for long-horizon system validation
2. **Full guide** for interpretation and troubleshooting
3. **Quick start** for rapid validation

**Key benefit:** Catch architectural bugs before they reach production by exercising the full runtime stack over realistic long-duration conditions.

**No code changes required.** This test uses only existing features accessible via RuntimeSnapshotView and the current IdeaCard schema.

Run this test as part of your pre-merge validation workflow for any changes to the backtest engine, snapshot layer, or artifact generation.

