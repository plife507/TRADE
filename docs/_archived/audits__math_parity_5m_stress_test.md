# Math Parity Audit Results - 5m Stress Test

**Date:** 2025-12-16  
**Run:** `backtests/BTCUSDT_5m_stress_test_indicator_dense/BTCUSDT/run-003`  
**Purpose:** Verify indicator calculations match pandas_ta exactly

---

## ⚠️ Audit Status: FAILED (1 of 9 columns)

The math parity audit compared our computed indicators against fresh pandas_ta computation and found a **discrepancy in volume_sma**.

---

## Summary

| Metric | Value |
|--------|-------|
| **Total Columns** | 9 |
| **Passed** | 8 |
| **Failed** | 1 |
| **Overall Status** | ❌ FAILED |

---

## Detailed Results

### ✅ PASSED Indicators (8/9)

All these indicators match pandas_ta **EXACTLY** (0.0 difference):

| Indicator | Max Diff | Mean Diff | Values | Status |
|-----------|----------|-----------|--------|--------|
| **ema_fast** (exec) | 0.0 | 0.0 | 12,665 | ✅ PERFECT |
| **ema_slow** (exec) | 0.0 | 0.0 | 12,648 | ✅ PERFECT |
| **rsi** (exec) | 0.0 | 0.0 | 12,659 | ✅ PERFECT |
| **atr** (exec) | 0.0 | 0.0 | 12,659 | ✅ PERFECT |
| **macd_macd** (exec) | 0.0 | 0.0 | 12,640 | ✅ PERFECT |
| **macd_signal** (exec) | 0.0 | 0.0 | 12,640 | ✅ PERFECT |
| **macd_histogram** (exec) | 0.0 | 0.0 | 12,640 | ✅ PERFECT |
| **ema_trend** (htf) | 0.0 | 0.0 | 1,734 | ✅ PERFECT |

---

### ❌ FAILED Indicator (1/9)

| Indicator | Max Diff | Mean Diff | Values | Status |
|-----------|----------|-----------|--------|--------|
| **volume_sma** (exec) | **102,652** | **89,078** | 12,654 | ❌ **LARGE DISCREPANCY** |

**Details:**
- Input source: `volume`
- Indicator type: `sma`
- Params: `length=20`
- Max absolute difference: **102,652.20**
- Mean absolute difference: **89,078.11**
- NaN mask: ✅ Identical

---

## Analysis

### What This Means

1. **✅ Price-based indicators are perfect:**
   - All EMAs, RSI, ATR, and MACD match pandas_ta exactly
   - No floating-point drift
   - No implementation bugs

2. **❌ Volume-based SMA has issues:**
   - Large discrepancy between our computation and pandas_ta
   - The difference is ~100K on volume values (which can be in millions)
   - This suggests either:
     - Wrong input data being used
     - Incorrect SMA implementation for volume
     - Data type mismatch (int64 vs float64)

### Why Didn't We Catch This Earlier?

**The validation tests DID work correctly** because:
- The strategy logic doesn't rely heavily on volume_sma accuracy
- The volume filter condition (`volume > volume_sma`) still works directionally
- Trades were generated and determinism was preserved

**But the math is WRONG**, and the audit caught it!

---

## Root Cause Investigation Needed

The volume_sma discrepancy needs investigation:

### Hypothesis 1: Input Data Issue
- Are we passing the correct volume column?
- Is there a data type mismatch?

### Hypothesis 2: SMA Implementation
- Is the SMA implementation correct for integer inputs?
- Does it handle volume data differently than price data?

### Hypothesis 3: NaN Handling
- The NaN masks match, so warmup is correct
- But the computed values differ significantly

---

## Validation Test Impact

### What This Audit Revealed

The validation tests validated:
- ✅ **Structural correctness** (no crashes, artifacts generated)
- ✅ **Determinism** (same results across runs)
- ✅ **Performance** (runtime acceptable)
- ✅ **Signal evaluation** (trades generated)

But they did NOT validate:
- ❌ **Mathematical correctness** of volume-based indicators
- ❌ **Parity with pandas_ta** for all indicator types

**This is why the audit module exists!**

---

## Recommendations

### Immediate Actions

1. **✅ Run audit on all validation tests** (not just determinism checks)
2. **❌ Block merging code** that uses volume-based indicators until fixed
3. **🔍 Investigate volume_sma implementation:**
   ```python
   # Check indicator_vendor.py SMA implementation
   # Compare with pandas_ta.sma(volume, length=20)
   ```
4. **🧪 Add volume-based indicator test** to verification suite

### Updated Validation Workflow

**Before:** 
```bash
1. Run backtest
2. Check determinism
3. ✅ Merge
```

**After (CORRECT):**
```bash
1. Run backtest with --emit-snapshots
2. Check determinism
3. Run math parity audit  # ← WE WERE MISSING THIS!
4. ✅ Merge only if audit passes
```

---

## Commands to Reproduce

```bash
# 1. Run backtest with snapshots
python trade_cli.py backtest run \
    --idea-card BTCUSDT_5m_stress_test_indicator_dense \
    --start 2024-11-01 --end 2024-12-14 \
    --data-env live \
    --emit-snapshots

# 2. Run math parity audit
python -c "
from src.backtest.audit_math_parity import audit_math_parity_from_snapshots
from pathlib import Path
result = audit_math_parity_from_snapshots(Path('backtests/BTCUSDT_5m_stress_test_indicator_dense/BTCUSDT/run-003'))
print(result.data)
"
```

---

## Conclusion

**Good catch!** The audit module revealed a **bug in volume_sma computation** that the determinism tests alone would never find.

### Key Takeaways

1. ✅ **8 of 9 indicators are mathematically perfect** (match pandas_ta exactly)
2. ❌ **volume_sma has a significant discrepancy** (~100K difference)
3. ✅ **Audit module is working correctly** (detected the issue)
4. 📝 **Validation workflow needs update** (always run audit after determinism check)

### Next Steps

1. Fix volume_sma implementation
2. Re-run audit to verify fix
3. Update validation IdeaCards to include math parity audit step
4. Consider adding audit to CI/CD pipeline

---

**Audit Completed:** 2025-12-16  
**Status:** ⚠️ **FAILED** (volume_sma discrepancy)  
**Action Required:** Investigate and fix volume_sma computation

