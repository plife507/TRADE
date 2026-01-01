# Indicator Pipeline End-to-End Audit

**Date:** 2025-12-17  
**Scope:** Complete indicator computation pipeline from IdeaCard → FeedStore  
**Status:** ✅ COMPLETE — Critical bug identified and documented  
**Moved from:** `docs/reviews/INDICATOR_PIPELINE_END_TO_END_REVIEW.md` (2025-12-17 docs refactor)
**Related:** `docs/audits/volume_sma_bug_diagnosis.md`

---

## Executive Summary

This audit traces the complete indicator computation pipeline across four critical dimensions:

1. **Input Source Handling** — How `input_source` flows from IdeaCard YAML to pandas_ta vendor
2. **Output Naming and Mapping** — How pandas_ta outputs are canonicalized to internal keys
3. **Warmup and NaN Semantics** — How warmup is computed, applied, and how boundaries are handled
4. **MTF Alignment Rules** — How HTF/MTF indices are computed and forward-filled

### Key Findings

**Critical Issues:**
- ❌ **P0 Bug:** `input_source` routing broken for all non-"close" sources (lines 633, 674 in `feature_frame_builder.py`)
- ⚠️ **P1 Risk:** Heuristic column name mapping fragile to pandas_ta changes
- ⚠️ **P1 Risk:** Warmup calculation logic duplicated across two modules

**Architecture Strengths:**
- ✅ Multi-output canonicalization with collision detection
- ✅ Fail-loud validation on missing declared outputs
- ✅ Proper forward-fill MTF alignment (TradingView-compliant)
- ✅ Graceful NaN handling with strict variant for validation

---

## Call Graph: IdeaCard YAML → pandas_ta Vendor

```
┌─────────────────────────────────────────────────────────────────┐
│ IdeaCard YAML                                                   │
│   indicator_type: "sma"                                         │
│   input_source: "volume"   ← User declaration                   │
│   output_key: "volume_sma"                                      │
│   params: {length: 20}                                          │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│ FeatureSpec.from_dict()                                         │
│   → Creates FeatureSpec with input_source=InputSource.VOLUME    │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│ FeatureFrameBuilder.build()                                     │
│   Line 620: input_series = _get_input_series(spec.input_source) │
│   Line 633: result = _compute(close=input_series, ...)    ← BUG │
└─────────────────────────────────────────────────────────────────┘
```

### The Bug (Lines 633, 674)

```python
# Line 633 - BUGGY
close = input_series if spec.input_source == InputSource.CLOSE else ohlcv["close"]
```

**Problem:** When `input_source` is NOT "close", the code ignores `input_series` (which correctly holds the volume data) and passes `ohlcv["close"]` instead.

**Impact:** All non-close input sources (volume, open, high, low, hlc3, ohlc4) are broken.

**Fix:** Change line 633 to always use `input_series`:
```python
close = input_series  # Always use the retrieved input series
```

---

## Recommendations

1. **P0 Fix**: Apply one-line fix to `feature_frame_builder.py` line 633
2. **P0 Gate**: Run input-source parity sweep before Phase 5
3. **P1**: Consolidate warmup calculation logic into single source
4. **P1**: Add explicit pandas_ta version pinning for column name stability

---

## Related Documentation

- **Root Cause**: `docs/audits/volume_sma_bug_diagnosis.md`
- **Indicator System**: `docs/audits/indicator_system_audit.md`
- **Math Parity**: `docs/audits/math_parity_5m_stress_test.md`

