# TRADE Open Bugs

Bug tracking for the TRADE trading bot.

---

## P0: Critical (Blocks Development)

*No critical bugs currently open.*

---

## P1: High (Should Fix Soon)

*No high priority bugs currently open.*

---

## P2: Medium (Fix When Convenient)

*No medium priority bugs currently open.*

---

## P3: Low (Nice to Have)

*No low priority bugs currently open.*

---

## Recently Fixed (2026-01-26)

### BUG-001: Smoke test references deleted plays
**Priority**: P1
**Status**: FIXED
**Location**: `src/cli/smoke_tests/structure.py`, `src/cli/smoke_tests/backtest.py`

**Symptom**: `--smoke full` failed with "Play not found" errors for V_STRUCT_001_swing_detection, T03_multi_indicator, etc.

**Root Cause**: Hardcoded play names in smoke tests were outdated after play consolidation.

**Fix**: Updated play references:
- `structure.py`: V_STRUCT_* -> V_S_* (actual validation play names)
- `backtest.py`: T03_multi_indicator -> V_I_001_ema, T09_multi_tf_three -> V_S_001_swing_basic

### BUG-002: Invalid parameter in preflight call
**Priority**: P1
**Status**: FIXED
**Location**: `src/cli/smoke_tests/backtest.py:439`

**Symptom**: "backtest_preflight_play_tool() got an unexpected keyword argument 'symbol_override'"

**Root Cause**: Smoke test passed `symbol_override` parameter that doesn't exist in function signature.

**Fix**: Removed invalid `symbol_override` parameter from call.

### BUG-003: Outdated Play attribute access
**Priority**: P1
**Status**: FIXED
**Location**: `src/cli/smoke_tests/backtest.py:568`

**Symptom**: "'Play' object has no attribute 'tf_configs'"

**Root Cause**: Code referenced old Play class attributes (tf_configs, exec_tf, med_tf, high_tf).

**Fix**: Updated to use current attributes (tf_mapping, execution_tf).

---

## Bug Template

```markdown
### BUG-XXX: Short Description
**Priority**: P0/P1/P2/P3
**Status**: OPEN / IN_PROGRESS / FIXED
**Location**: file.py:line

**Symptom**: What was observed

**Root Cause**: Why it happened (once known)

**Fix**: What was changed (once fixed)

**Validation**: How we verified the fix
```
