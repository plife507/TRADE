# Backtest Module Legacy Code Audit

**Date**: December 17, 2025  
**Type**: Code Quality Audit  
**Scope**: Legacy remnants, temporary adapters, and technical debt in backtest module  
**Status**: Documentation & Recommendations

---

## Executive Summary

This audit identifies and categorizes legacy code patterns, temporary adapters, and technical debt in the `src/backtest/` module following recent architectural changes. The IdeaCard-native refactor is **mostly complete**, but several temporary adapter layers remain marked for deletion, and two critical paths are **broken** due to incomplete warmup wiring.

**Key Findings**:
- 🔴 **2 broken paths** requiring immediate fixes (YAML loader, audit tool)
- ⚠️ **3 temporary adapters** marked for deletion (SystemConfig bridge layer)
- ✅ **Build-forward discipline** generally followed (defensive warnings, fail-loud approach)
- 📝 **1 outdated comment** contradicting current behavior
- 🔧 **5 design debt items** for future cleanup

**Overall Assessment**: The codebase is transitioning well from SystemConfig to IdeaCard-native architecture, but cleanup phase is incomplete. No critical blockers for current workflow, but legacy paths need attention before they cause confusion.

---

## Table of Contents

1. [Critical Issues (P0)](#critical-issues-p0)
2. [Temporary Adapters (P1)](#temporary-adapters-p1)
3. [Outdated Documentation (P1)](#outdated-documentation-p1)
4. [Design Debt (P2)](#design-debt-p2)
5. [Acceptable Legacy Support](#acceptable-legacy-support)
6. [Recommendations](#recommendations)
7. [File-by-File Analysis](#file-by-file-analysis)

---

## Critical Issues (P0)

### 1. YAML Loader Path — Broken

**File**: `src/backtest/system_config.py:858-869`  
**Function**: `load_system_config()`

**Issue**: Does NOT populate `warmup_bars_by_role` when creating SystemConfig from YAML.

**Code**:
```python
config = SystemConfig(
    system_id=raw.get("system_id", system_id),
    symbol=raw.get("symbol", ""),
    # ... other fields ...
    warmup_multiplier=warmup_multiplier,
    # ❌ warmup_bars_by_role NOT passed - defaults to {}
)
```

**Impact**:
- Any attempt to use legacy YAML-based SystemConfigs will trigger `MISSING_WARMUP_CONFIG` error
- Engine fails at initialization: `ValueError: MISSING_WARMUP_CONFIG: warmup_bars_by_role['exec'] not set`
- Blocks backward compatibility with YAML configs (if that's a goal)

**Root Cause**: P0 warmup fix (Dec 17, 2024) made `warmup_bars_by_role` mandatory, but YAML loader wasn't updated.

**Recommendation**: 
- **Option A**: Wire warmup computation into YAML loader (if YAML support is needed)
- **Option B**: Deprecate YAML loader entirely (if IdeaCard is the only supported path)
- **Decision needed**: Is YAML SystemConfig still a supported path?

**Referenced In**: `docs/session_reviews/2024-12-17_warmup_system_audit.md` (Lines 116-168)

---

### 2. Audit Tool Path — Broken

**File**: `src/backtest/audit_snapshot_plumbing_parity.py:541-556`

**Issue**: Snapshot plumbing parity audit creates SystemConfig without `warmup_bars_by_role`.

**Code**:
```python
system_config = SystemConfig(
    system_id=idea_card.id,
    symbol=symbol,
    # ... other fields ...
    feature_specs_by_role=feature_specs_by_role,
    # ❌ warmup_bars_by_role NOT passed - defaults to {}
)
```

**Impact**:
- Audit tool fails when trying to initialize BacktestEngine
- Cannot validate snapshot plumbing parity (testing workflow broken)

**Recommendation**: Add warmup computation before SystemConfig creation:
```python
from .execution_validation import compute_warmup_requirements

warmup_req = compute_warmup_requirements(idea_card)
system_config = SystemConfig(
    # ... existing fields ...
    warmup_bars_by_role=warmup_req.warmup_by_role,
)
```

**Referenced In**: `docs/session_reviews/2024-12-17_warmup_system_audit.md` (Lines 146-160)

---

## Temporary Adapters (P1)

### 3. IdeaCard → SystemConfig Bridge Layer

**Status**: ⏳ Marked TEMP, planned for deletion

Three interconnected components form the bridge between IdeaCard and engine:

#### 3a. IdeaCardEngineWrapper

**File**: `src/backtest/runner.py:288-323`

**Purpose**: Wraps BacktestEngine to use IdeaCard signal evaluation instead of strategy interface.

**Comment** (line 292):
> TEMP: This wrapper bridges IdeaCard signal rules to the engine's strategy interface.  
> Will be deleted when engine natively supports IdeaCard.

**Code Pattern**:
```python
class IdeaCardEngineWrapper:
    def __init__(self, engine: Any, idea_card: IdeaCard):
        self.engine = engine
        self.idea_card = idea_card
        self.evaluator = IdeaCardSignalEvaluator(idea_card)
    
    def run(self) -> IdeaCardBacktestResult:
        # Bridges to engine.run()
```

**Usage**: Single caller — `run_backtest_with_gates()` in same file.

---

#### 3b. IdeaCardSystemConfig

**File**: `src/backtest/execution_validation.py:620-663`

**Purpose**: Adapter dataclass that converts IdeaCard to SystemConfig-compatible format.

**Comment** (lines 614-618):
> TEMP ADAPTER — DELETE WHEN:
> - Engine natively accepts IdeaCard (no SystemConfig dependency)
> - All callers use IdeaCard directly
> - Deletion criteria met: only runner.py calls this adapter

**Fields**: Minimal subset of SystemConfig fields needed for execution.

**Note**: Currently defined but may not be actively used (check call sites).

---

#### 3c. create_default_engine_factory()

**File**: `src/backtest/runner.py:114-285`

**Purpose**: Factory function that creates BacktestEngine from IdeaCard by building intermediate SystemConfig.

**Comment** (line 121):
> TEMP: This factory exists until engine natively accepts IdeaCard.  
> Single caller: run_backtest_with_gates() in this module.

**Comment** (line 186):
> TEMP: This adapter will be deleted when engine accepts IdeaCard directly

**Key Logic** (lines 247-280):
```python
# Create SystemConfig
system_config = SystemConfig(
    system_id=idea_card.id,
    # ... map IdeaCard fields to SystemConfig ...
    warmup_bars_by_role=warmup_bars_by_role,  # From preflight
    delay_bars_by_role=delay_bars_by_role,    # From preflight
)

# Create engine with SystemConfig
engine = BacktestEngine(
    config=system_config,
    window_name="run",
    tf_mapping=tf_mapping,
)
```

**Design Note**: Properly consumes Preflight output (warmup/delay from gate), doesn't recompute.

---

### Summary: Adapter Layer Deletion Criteria

**Target State**: `BacktestEngine.__init__(idea_card: IdeaCard, ...)` — native IdeaCard acceptance.

**Current Blocker**: Engine still expects SystemConfig in constructor.

**Deletion Checklist**:
- [ ] Refactor `BacktestEngine.__init__()` to accept IdeaCard
- [ ] Extract execution params directly from IdeaCard (no SystemConfig middleman)
- [ ] Delete `IdeaCardEngineWrapper`, `IdeaCardSystemConfig`, `create_default_engine_factory()`
- [ ] Update runner to call `BacktestEngine(idea_card, ...)` directly

**Estimated Scope**: Medium refactor (1-2 sessions), touch points in `engine.py`, `runner.py`, `execution_validation.py`.

---

## Outdated Documentation (P1)

### 4. Misleading Comment About Legacy Fallback

**File**: `src/backtest/system_config.py:498`

**Current Comment**:
```python
# IdeaCard-declared warmup bars per TF role (exec/htf/mtf)
# This is the CANONICAL warmup source - engine MUST use this, not recompute
# If empty, engine will compute from feature specs (legacy path)
warmup_bars_by_role: Dict[str, int] = field(default_factory=dict)
```

**Issue**: Line 498 says *"If empty, engine will compute from feature specs (legacy path)"* — this is **FALSE** as of P0 fix (Dec 17, 2024).

**Reality**: Engine now **fails loud** if `warmup_bars_by_role` is empty:

```python
# src/backtest/engine.py:460-465
if not warmup_bars_by_role or 'exec' not in warmup_bars_by_role:
    raise ValueError(
        "MISSING_WARMUP_CONFIG: warmup_bars_by_role['exec'] not set. "
        "Ensure IdeaCard warmup is wired through compute_warmup_requirements() to SystemConfig."
    )
```

**Correct Comment Should Be**:
```python
# IdeaCard-declared warmup bars per TF role (exec/htf/mtf)
# This is the CANONICAL warmup source - engine MUST use this, not recompute
# MUST NOT be empty - engine will fail loud if missing (no fallback path)
warmup_bars_by_role: Dict[str, int] = field(default_factory=dict)
```

**Impact**: Confuses developers reading the code, suggests a fallback path that doesn't exist.

**Fix**: Update comment to reflect current fail-loud behavior.

---

## Design Debt (P2)

### 5. Duplicated Window Expansion Logic

**Issue**: Range expansion formula (warmup offset calculation) is **duplicated** in 3 locations:

**Location 1: Preflight** (`src/backtest/runtime/preflight.py:255-262`):
```python
def calculate_warmup_start(window_start: datetime, warmup_bars: int, tf_minutes: int) -> datetime:
    warmup_minutes = warmup_bars * tf_minutes
    return window_start - timedelta(minutes=warmup_minutes)
```

**Location 2: Engine Single-TF** (`src/backtest/engine.py:471-474`):
```python
tf_delta = self._timeframe_to_timedelta(self.config.tf)
warmup_span = tf_delta * warmup_bars
extended_start = requested_start - warmup_span
```

**Location 3: Engine Multi-TF** (`src/backtest/engine.py:666-673`):
```python
ltf_delta = tf_duration(ltf_tf)
warmup_span = ltf_delta * warmup_bars

htf_delta = tf_duration(htf_tf)
htf_warmup_span = htf_delta * htf_warmup_bars

data_start = min(extended_start, requested_start - htf_warmup_span)
```

**Risk**: If formula needs adjustment (e.g., safety buffer, calendar-aware expansion), must update 3 places. Easy to diverge.

**Recommendation**: Create centralized utility:
```python
def compute_data_window(
    window_start: datetime,
    window_end: datetime,
    warmup_by_role: Dict[str, int],
    tf_mapping: Dict[str, str],
    safety_buffer_bars: int = 0,
) -> Tuple[datetime, datetime]:
    """
    Compute data fetch window with warmup offset.
    
    Single source of truth for all window expansion logic.
    """
    # Implementation centralizes all 3 duplicated patterns
```

**Impact**: Maintainability improvement, prevents divergence.

**Priority**: P2 (not urgent, but good practice for future).

---

### 6. No Max Warmup Validation

**Issue**: No cap on `warmup_bars` in IdeaCard validation.

**Risk**: Misconfigured IdeaCard with `warmup_bars: 10000` could:
- Request years of historical data (expensive API calls)
- Attempt to fetch data before exchange launch (nonsensical)
- Exceed DuckDB storage capacity

**Current Behavior**: Will attempt to fetch whatever warmup is declared, fail at data layer.

**Recommendation**: Add validation in `validate_idea_card_full()`:
```python
MAX_WARMUP_BARS = 1000  # ~2 weeks on 15m, ~1 month on 1h
EARLIEST_BYBIT_DATE = datetime(2018, 1, 1)  # Exchange launch

for role, tf_config in idea_card.tf_configs.items():
    warmup = tf_config.effective_warmup_bars
    if warmup > MAX_WARMUP_BARS:
        errors.append(f"{role} warmup {warmup} exceeds max {MAX_WARMUP_BARS}")
    
    # Check if extended start would be before exchange launch
    tf_minutes = timeframe_to_minutes(tf_config.tf)
    extended_start = window_start - timedelta(minutes=warmup * tf_minutes)
    if extended_start < EARLIEST_BYBIT_DATE:
        errors.append(f"{role} warmup reaches {extended_start}, before exchange launch")
```

**Priority**: P2 (safety check, not urgent but good practice).

---

### 7. No Exchange Historical Limit Handling

**Issue**: Preflight doesn't check against exchange-specific historical data availability.

**Example**: Bybit may not have data before certain dates for certain symbols.

**Current Behavior**: Generic "No data available" error, not informative.

**Recommendation**: Add exchange-aware validation:
```python
EXCHANGE_EARLIEST_DATES = {
    "bybit": {
        "default": datetime(2018, 1, 1),
        "BTCUSDT": datetime(2019, 10, 1),
        # ... per-symbol overrides
    }
}

def validate_historical_range(symbol: str, start: datetime, exchange: str = "bybit"):
    earliest = get_earliest_date(symbol, exchange)
    if start < earliest:
        raise ValueError(
            f"Requested start {start} is before {symbol} listing on {exchange} ({earliest}). "
            f"Reduce warmup_bars or adjust window_start."
        )
```

**Priority**: P2 (UX improvement, not critical).

---

### 8. Legacy params-based Indicators Check

**File**: `src/backtest/engine.py:522-531`

**Code**:
```python
# No legacy params-based indicators - IdeaCard is the single source of truth
if self.config.strategies:
    for strategy_inst in self.config.strategies:
        if strategy_inst.params and "indicator_params" in strategy_inst.params:
            raise ValueError(
                "Legacy params-based indicators are not supported."
            )
```

**Purpose**: Defensive check to reject old-style indicator configuration.

**Assessment**: ✅ Good fail-loud practice. This is **defensive legacy rejection**, not actual legacy code.

**Status**: Keep as-is (guards against accidental regression).

---

### 9. Legacy RuntimeSnapshot Rejection

**Pattern**: Multiple files contain defensive checks rejecting `RuntimeSnapshot`:

**Examples**:
- `src/backtest/runner.py:313`
- `src/backtest/engine.py:18-21`
- `src/backtest/execution_validation.py:938-942`
- `src/backtest/simulated_risk_manager.py:88-92`

**Assessment**: ✅ Good fail-loud practice. These are **defensive guards**, not legacy code.

**Status**: Keep as-is (prevents silent compatibility issues).

---

## Acceptable Legacy Support

These patterns are **intentional backward compatibility** for reading old data:

### 10. Legacy Artifact CSV Aliases

**File**: `src/backtest/artifacts/artifact_standards.py:60`

**Comment**:
```python
# Legacy CSV aliases (for backward-compat reading of old runs)
```

**Purpose**: Read old backtest results that used CSV format.

**Assessment**: ✅ Read-only backward compatibility (acceptable).

**Current Format**: Parquet for new runs, CSV reading for legacy archives.

---

### 11. Legacy Stop Reason Fields

**File**: `src/backtest/types.py:454, 468, 470, 540, 547`

**Code**:
```python
stop_reason: Optional[str] = None  # Legacy: "account_blown" | "insufficient_free_margin" | "liquidated"
```

**Purpose**: Maintain field compatibility with old BacktestMetrics/BacktestResult structures.

**Assessment**: ✅ Backward-compatible fields (acceptable for historical data).

**Note**: New code uses `stop_classification`, but `stop_reason` preserved for old result loading.

---

### 12. Legacy Fee Fields

**File**: `src/backtest/sim/types.py:574`

**Code**:
```python
@property
def taker_fee_rate(self) -> float:
    """Legacy: taker fee as decimal."""
    return self.taker_bps / 10000.0
```

**Assessment**: ✅ Property alias for backward compatibility (acceptable).

---

### 13. Legacy Manifest Check

**File**: `src/backtest/audit_math_parity.py:79-84`

**Code**:
```python
# FAIL LOUD if not present - no legacy manifest support
if "outputs_written" not in frame_meta:
    raise ValueError(
        f"LEGACY_MANIFEST_UNSUPPORTED: Frame '{role}' missing 'outputs_written' in manifest. "
        "Legacy manifests with only 'feature_columns' are not supported."
    )
```

**Assessment**: ✅ Defensive rejection of old manifests (good fail-loud practice).

---

## Recommendations

### Immediate Actions (P0)

1. **Fix YAML Loader** (`src/backtest/system_config.py:858`)
   - Decision: Deprecate YAML path OR wire warmup computation
   - If deprecating: Add explicit error message directing users to IdeaCard
   - If keeping: Call `compute_warmup_requirements()` before SystemConfig creation

2. **Fix Audit Tool** (`src/backtest/audit_snapshot_plumbing_parity.py:541`)
   - Add warmup computation via `compute_warmup_requirements()`
   - Wire `warmup_bars_by_role` into SystemConfig creation

### Short-term Cleanup (P1)

3. **Update Misleading Comment** (`src/backtest/system_config.py:498`)
   - Remove reference to non-existent "legacy path"
   - Clarify fail-loud behavior

4. **Document Adapter Deletion Plan**
   - Create TODO document: `docs/todos/IDEACARD_NATIVE_ENGINE_MIGRATION.md`
   - Outline steps to refactor engine to accept IdeaCard directly
   - Estimate scope and dependencies

### Medium-term Improvements (P2)

5. **Centralize Window Expansion** (Design Debt #5)
   - Create `compute_data_window()` utility
   - Refactor preflight/engine to use centralized function

6. **Add Warmup Validation** (Design Debt #6)
   - Max warmup bar cap (1000 bars default, override with flag)
   - Earliest date validation (per exchange)

7. **Exchange-aware Historical Limits** (Design Debt #7)
   - Per-symbol earliest date registry
   - Informative error messages when requesting pre-listing data

### Long-term Strategy (P3)

8. **Complete IdeaCard-Native Migration**
   - Refactor `BacktestEngine` to accept IdeaCard in constructor
   - Delete adapter layer (wrapper, factory, IdeaCardSystemConfig)
   - Update all documentation references

9. **Deprecate SystemConfig Path**
   - Once IdeaCard is natively supported, mark SystemConfig as deprecated
   - Add deprecation warnings for YAML-based configs
   - Eventually remove SystemConfig entirely (multi-phase deprecation)

---

## File-by-File Analysis

### High Priority Files (Require Changes)

| File | Issue | Priority | Action |
|------|-------|----------|--------|
| `system_config.py:858` | YAML loader missing warmup | P0 | Fix or deprecate |
| `audit_snapshot_plumbing_parity.py:541` | Audit tool missing warmup | P0 | Add warmup wiring |
| `system_config.py:498` | Outdated comment | P1 | Update comment |
| `runner.py:114-323` | Temp adapter layer | P1 | Document deletion plan |
| `execution_validation.py:620-663` | Temp adapter dataclass | P1 | Part of deletion plan |

### Medium Priority Files (Design Improvements)

| File | Issue | Priority | Action |
|------|-------|----------|--------|
| `runtime/preflight.py:255` | Duplicated expansion logic | P2 | Centralize utility |
| `engine.py:471, 666` | Duplicated expansion logic | P2 | Use centralized utility |
| `execution_validation.py` | No max warmup check | P2 | Add validation |

### Low Priority Files (Acceptable As-Is)

| File | Pattern | Assessment |
|------|---------|------------|
| `artifacts/artifact_standards.py:60` | Legacy CSV read | ✅ Acceptable |
| `types.py:470` | Legacy fields | ✅ Backward compat |
| `sim/types.py:574` | Legacy properties | ✅ Acceptable |
| Multiple | RuntimeSnapshot rejection | ✅ Good defense |

---

## Architecture State Assessment

### IdeaCard-Native Migration Progress

**Phase 1: IdeaCard Design** ✅ Complete
- IdeaCard YAML schema defined
- Validation framework implemented
- FeatureSpec integration complete

**Phase 2: Adapter Layer** ✅ Complete (Temporary)
- `IdeaCardEngineWrapper` working
- `create_default_engine_factory()` working
- Preflight warmup wiring complete
- **Status**: Functional but marked TEMP

**Phase 3: Broken Paths Fix** 🔴 Incomplete
- IdeaCard runner path: ✅ Working
- YAML loader path: ❌ Broken (missing warmup)
- Audit tool path: ❌ Broken (missing warmup)

**Phase 4: Native Engine Support** 📋 Not Started
- Engine still expects SystemConfig
- Adapter deletion blocked by engine dependency

### Compliance with Project Rules

**Build-Forward Discipline**: ✅ Strong
- Clear TEMP markers on adapter code
- No silent backward compatibility fallbacks
- Fail-loud approach on missing config

**TODO-Driven Execution**: ⚠️ Partial
- Recent changes documented in session reviews
- Missing TODO document for adapter deletion plan

**No Implicit Defaults**: ✅ Excellent
- Engine fails loud on missing warmup
- No silent indicator defaults

**Phase Discipline**: ✅ Good
- Clear progression from Phase 1 → 2 → 3
- Phase 4 properly deferred (not started prematurely)

---

## Conclusion

The backtest module is in a **healthy transition state** with clear architectural direction. The IdeaCard-native refactor is 75% complete:

**Strengths**:
- Strong fail-loud discipline (catches misconfigurations early)
- Clear TEMP markers on adapter code (deletion plan visible)
- Defensive guards prevent regression to old patterns
- New code consistently uses IdeaCard (no new SystemConfig dependencies)

**Weaknesses**:
- Two broken legacy paths (YAML, audit) need immediate attention
- Adapter layer lingers (understandable, waiting for engine refactor)
- Duplicated logic in window expansion (minor maintainability issue)

**Critical Path**:
1. Fix broken YAML/audit paths (P0) — unblock legacy compatibility if needed
2. Document adapter deletion plan (P1) — roadmap for Phase 4
3. Refactor engine to accept IdeaCard (P1) — enables adapter deletion
4. Centralize window logic (P2) — cleanup after major refactor

**Overall Risk**: Low. Current implementation is stable and working. Legacy remnants are well-marked and isolated. No silent compatibility issues or hidden assumptions.

---

**Document Version**: 1.0  
**Last Updated**: December 17, 2025  
**Status**: Final Review  
**Next Action**: Address P0 issues (broken paths) or proceed to Phase 4 (engine refactor)


