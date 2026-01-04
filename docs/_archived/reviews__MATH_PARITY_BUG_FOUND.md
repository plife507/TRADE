# Math Parity Audit Bug: Single-TF Strategies Show 0 Columns

**Date**: December 30, 2025
**Status**: ✅ **FIXED**
**Severity**: Moderate (affects audit only, not backtest execution)
**Fixed**: December 30, 2025

---

## Bug Summary

**Math-parity audit shows 0/0 columns for single-TF strategies** even with 3-month data windows. Multi-TF strategies work correctly (4/4 columns).

**Root Cause**: `prepare_multi_tf_frames()` requires `warmup_bars_by_role['htf']` to be set, but single-TF strategies only have `warmup_bars_by_role['exec']`.

---

## Bug Details

### Location

**File**: `src/backtest/engine.py`
**Function**: `prepare_multi_tf_frames()`
**Line**: 706-712 (before fix)

```python
# BEFORE FIX (broken)
# HTF warmup - required for multi-TF mode
if 'htf' not in warmup_bars_by_role:
    raise ValueError(
        "MISSING_WARMUP_CONFIG: warmup_bars_by_role['htf'] not set for multi-TF mode. "
        "Preflight gate must compute warmup for HTF role. "
        "Check IdeaCard has htf TF config with warmup declared."
    )
```

### Problem

1. **Single-TF strategies** only have `exec` role configured:
   - `warmup_bars_by_role = {'exec': 60}` (example)
   - No `htf` or `mtf` roles

2. **`prepare_multi_tf_frames()` always requires `htf` warmup**, even for single-TF strategies where all roles map to the same TF:
   - `tf_mapping = {'ltf': '15m', 'mtf': '15m', 'htf': '15m'}` (all same TF)

3. **The audit calls `prepare_multi_tf_frames()`** which fails for single-TF strategies

4. **Exception is caught** and audit returns 0/0 columns instead of showing the actual error

### Code Flow (Before Fix)

```
audit_in_memory_parity.py:485
  → engine.prepare_multi_tf_frames()
    → engine.py:706
      → if 'htf' not in warmup_bars_by_role:
          → raise ValueError(...)  # ❌ Fails for single-TF
```

**Exception handling** (line 508-514):
```python
except Exception as e:
    return InMemoryParityResult(
        success=False,
        error_message=f"Failed to run in-memory parity: {str(e)}",
        summary={"traceback": traceback.format_exc()},
    )
```

But the error message isn't shown in the CLI output - it just shows "0/0 columns".

---

## Evidence

### Test Results (3-Month Windows) — Before Fix

| IdeaCard | Type | Window | Result | Status |
|----------|------|--------|--------|--------|
| `test02__AVAXUSDT_cci_adx` | Single-TF | 3 months | **0/0 columns** | ❌ Bug |
| `test__phase6_warmup_matrix__BTCUSDT_5m` | Single-TF | 3 months | **0/0 columns** | ❌ Bug |
| `test__delay_bars_mtf__LTCUSDT_5m_1h_4h` | Multi-TF | 3 months | **4/4 columns** | ✅ Works |
| `test__phase6_mtf_alignment__BTCUSDT_5m_1h_4h` | Multi-TF | 14 days | **4/4 columns** | ✅ Works |

**Pattern**: All single-TF strategies show 0/0, all multi-TF strategies work.

### Direct Test

```python
from src.backtest.engine import create_engine_from_idea_card
from src.backtest.idea_card import load_idea_card
from src.backtest.execution_validation import compute_warmup_requirements
from datetime import datetime

ic = load_idea_card('test02__AVAXUSDT_cci_adx')
warmup = compute_warmup_requirements(ic)
print(warmup.warmup_by_role)  # {'exec': 60} - no 'htf'!

engine = create_engine_from_idea_card(
    ic, datetime(2024,9,1), datetime(2024,12,1),
    warmup.warmup_by_role, warmup.delay_by_role
)
engine.prepare_multi_tf_frames()  # ❌ Raises ValueError: MISSING_WARMUP_CONFIG
```

---

## Fix Applied

### Option Selected: Option 1 — Make HTF Warmup Optional for Single-TF

**File**: `src/backtest/engine.py`
**Lines**: 705-729 (after fix)

### Why Option 1?

| Option | Approach | Pros | Cons |
|--------|----------|------|------|
| **1 (chosen)** | Engine detects single-TF via `_multi_tf_mode` | Correct semantics, uses existing flag | 6 more lines |
| 2 | Always populate htf/mtf warmup | Fewer lines | Semantic confusion |
| 3 | Audit uses different path | Explicit handling | Code duplication |

**Option 1 is best** because:
- Uses the existing `_multi_tf_mode` flag (already set in `__init__`)
- Maintains correct semantics (single-TF strategies don't have htf warmup)
- Localized change (only validation logic, not data flow)
- Clear intent via comments

### Code Change

```python
# AFTER FIX (working)
# HTF warmup - required for multi-TF mode, optional for single-TF
#
# FIX: Single-TF strategies only define warmup_bars_by_role['exec'].
# They don't have separate HTF/MTF roles, so 'htf' key won't exist.
# However, _multi_tf_mode is False for single-TF, and all TF mappings
# point to the same timeframe (e.g., {'htf': '15m', 'mtf': '15m', 'ltf': '15m'}).
#
# Solution: Only require 'htf' warmup when actually in multi-TF mode.
# For single-TF, fall back to exec warmup (which covers all roles since
# they're all the same timeframe).
#
# See: docs/reviews/MATH_PARITY_BUG_FOUND.md for full analysis.
if 'htf' not in warmup_bars_by_role:
    if self._multi_tf_mode:
        # True multi-TF mode: htf warmup is required
        raise ValueError(
            "MISSING_WARMUP_CONFIG: warmup_bars_by_role['htf'] not set for multi-TF mode. "
            "Preflight gate must compute warmup for HTF role. "
            "Check IdeaCard has htf TF config with warmup declared."
        )
    else:
        # Single-TF mode: all roles map to same TF, use exec warmup
        htf_warmup_bars = warmup_bars_by_role.get('exec', 0)
else:
    htf_warmup_bars = warmup_bars_by_role['htf']
```

### Key Design Decisions

1. **Use `_multi_tf_mode` flag** — Already computed in `__init__` based on TF mapping:
   ```python
   # From __init__ (lines 244-249)
   if tf_mapping is None:
       self._multi_tf_mode = False
   else:
       self._multi_tf_mode = tf_mapping["htf"] != tf_mapping["ltf"] or \
                             tf_mapping["mtf"] != tf_mapping["ltf"]
   ```

2. **Fall back to exec warmup** — For single-TF, all roles are the same TF, so exec warmup covers everything.

3. **Preserve error for multi-TF** — If someone creates a multi-TF strategy without htf warmup, the error still fires.

---

## Rejected Alternatives

### Option 2: Compute HTF/MTF Warmup for Single-TF

**File**: `src/backtest/execution_validation.py`
**Function**: `compute_warmup_requirements()`

**Rejected because**: Creates semantic confusion. A single-TF strategy would have `warmup_bars_by_role['htf'] = 60` even though there's no HTF. This could cause bugs if code later checks for htf existence.

### Option 3: Use Different Path for Single-TF Audit

**File**: `src/backtest/audits/audit_in_memory_parity.py`

**Rejected because**: Code duplication. Would need to maintain two separate paths for frame preparation.

---

## Impact

- **Severity**: Moderate
- **Affects**: Math-parity audit only (not backtest execution)
- **User Impact**: Cannot validate indicator math for single-TF strategies
- **Workaround**: Use multi-TF strategies for math validation, or manually verify indicators

---

## Test Plan

After fix:

1. ✅ Run math-parity on single-TF strategies with 3-month windows
2. ✅ Verify columns are found (should show N/N for single-TF)
3. ✅ Verify multi-TF strategies still work (4/4 columns)
4. ✅ Verify backtest execution still works for both types

---

## Timeline

| Date | Event |
|------|-------|
| 2025-12-30 | Bug discovered during math-parity audit testing |
| 2025-12-30 | Root cause identified |
| 2025-12-30 | Fix options analyzed |
| 2025-12-30 | **Option 1 implemented** |

---

**Bug Confirmed**: December 30, 2025
**Fix Applied**: December 30, 2025
**Fix Location**: `src/backtest/engine.py` lines 705-729
