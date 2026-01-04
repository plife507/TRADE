# Market Structure Integration - Code Review Findings

**Review Date**: 2025-12-30
**Reviewer**: Claude Code
**Status**: COMPLETE
**Files Reviewed**: 15+ core modules across backtest engine

---

## Executive Summary

This review examined the backtest engine codebase for edge cases and issues that could prevent clean integration of market structure features (swings, pivots, trends, regimes) following the same architectural pattern as indicators.

**Overall Assessment**: ⚠️ **PROCEED WITH CAUTION**

The architecture is well-designed for indicator-like features, but market structure features have unique characteristics (sparse values, multi-value outputs, different update semantics) that require careful extension of existing patterns rather than drop-in replacement.

### Key Findings Summary

| Area | Status | Critical Issues | Recommendations |
|------|--------|-----------------|-----------------|
| 1. FeatureSpec/FeatureFrame | ⚠️ | Warmup assumptions indicator-only | Extend warmup calculation |
| 2. FeedStore Array Storage | ⚠️ | No sparse feature support | Add forward-fill arrays |
| 3. RuntimeSnapshotView | ✅ | Minor: needs "last N" API | Add structure-specific accessors |
| 4. MTF Integration | ⚠️ | Cross-TF validation not possible | Document limitation |
| 5. Warmup/Delay | ⚠️ | Structure warmup differs | New warmup formulas needed |
| 6. History Management | ⚠️ | Stores full snapshots, not sparse | Consider structure history |
| 7. Artifacts/Validation | ⚠️ | No reference implementation | Custom validators needed |
| 8. Hot Loop Performance | ✅ | O(1) maintained if precomputed | Ensure precomputation |
| 9. IdeaCard Config | ⚠️ | Needs new indicator types | Extend IndicatorType enum |
| 10. Error Handling | ✅ | Good patterns exist | Apply to structure features |

---

## Review Area 1: FeatureSpec/FeatureFrame Integration

### Status: ⚠️ Needs Attention

### Findings

#### 1.1 Warmup Calculation is Indicator-Specific
**File**: [feature_spec.py:450-513](src/backtest/features/feature_spec.py#L450-L513)

The `warmup_bars` property has hardcoded logic for specific indicator types:

```python
@property
def warmup_bars(self) -> int:
    ind_type = self.indicator_type

    if ind_type == IndicatorType.EMA:
        return get_ema_warmup(self.length)
    elif ind_type == IndicatorType.RSI:
        return get_rsi_warmup(self.length)
    # ... more indicator-specific cases
    else:
        # Fallback for unknown types
        return self.length
```

**Issue**: Market structure features (swing detection, pivot identification) have different warmup semantics:
- Swing detection: Needs N bars lookback + confirmation bars
- Pivot detection: May need variable lookback based on swing depth
- Trend identification: May depend on multiple indicator warmups

**Recommendation**:
1. Add explicit `warmup_bars` parameter to FeatureSpec (already exists as computed property, but allow override)
2. Create new `get_structure_warmup()` helpers with structure-specific formulas
3. Update fallback to use `params.get('warmup', self.length)` instead of just `self.length`

#### 1.2 Multi-Output Handling Works but Needs Extension
**File**: [feature_spec.py:232-306](src/backtest/features/feature_spec.py#L232-L306)

Current `MULTI_OUTPUT_KEYS` dict handles indicator multi-outputs well. Structure features would need new entries:

```python
# Proposed additions (not in code yet):
IndicatorType.SWING: ("high", "high_idx", "low", "low_idx"),
IndicatorType.PIVOT: ("high", "low", "pivot_type"),
IndicatorType.TREND: ("direction", "strength", "regime"),
```

**Recommendation**: Extend `MULTI_OUTPUT_KEYS` when adding structure indicator types.

#### 1.3 Dependency Validation Works
**File**: [feature_spec.py:573-589](src/backtest/features/feature_spec.py#L573-L589)

The `_validate_dependencies()` method correctly ensures chained features are computed in order. This supports structure features that depend on indicators (e.g., trend depending on EMA values).

**Status**: ✅ Safe

---

## Review Area 2: FeedStore Array Storage

### Status: ⚠️ Needs Attention

### Findings

#### 2.1 All Arrays Must Have Same Length
**File**: [feed_store.py:104-118](src/backtest/runtime/feed_store.py#L104-L118)

```python
def __post_init__(self):
    for name, arr in self.indicators.items():
        assert len(arr) == self.length, f"indicator {name} length mismatch"
```

**Issue**: Sparse structure features (swings only occur every N bars) must still have length-matching arrays. This is fine, but requires:
- Forward-fill for "last swing" semantics
- NaN or sentinel values where no swing exists

**Recommendation**:
- Structure features should use **forward-fill precomputation** during `FeatureFrameBuilder.build()`
- Document that sparse features must store last-known value at each bar index
- Add helper `forward_fill_structure_array()` to builder

#### 2.2 No Special Handling for Sparse Features
**File**: [feed_store.py](src/backtest/runtime/feed_store.py)

Current implementation stores indicators as dense arrays with NaN for invalid periods. This works for structure features if:
- Forward-fill is applied during computation
- Snapshot access handles NaN correctly

**Issue**: Current NaN handling returns `None` in accessors:
```python
def get_indicator(self, name: str) -> Optional[float]:
    val = self.feed.indicators[name][self.current_idx]
    if np.isnan(val):
        return None
    return float(val)
```

**Problem for Structure**: Returning `None` for "no swing at this bar" is different from "swing hasn't been computed yet". Need to distinguish:
- `NaN` = warmup period (not ready)
- Valid float = last known swing value (forward-filled)

**Recommendation**:
- Precompute structure features with forward-fill semantics
- First valid index marks where feature becomes available
- All subsequent bars have forward-filled values (never NaN after first valid)

#### 2.3 `indicator_columns` Parameter Name
**File**: [feed_store.py:228](src/backtest/runtime/feed_store.py#L228)

Parameter is named `indicator_columns` but is semantically "feature_columns". This is a naming convention issue only.

**Recommendation**: Consider renaming to `feature_columns` for clarity, but low priority.

---

## Review Area 3: RuntimeSnapshotView API

### Status: ✅ Safe (Minor Enhancements Needed)

### Findings

#### 3.1 `get_feature()` API Supports Any Key
**File**: [snapshot_view.py:500-559](src/backtest/runtime/snapshot_view.py#L500-L559)

The unified `get_feature()` API already supports:
- OHLCV keys (open, high, low, close, volume)
- Any indicator key in `feed.indicators`
- Offset for previous bar access
- TF role routing (exec, htf, mtf)

**Conclusion**: Structure features will work if stored in `feed.indicators` dict.

#### 3.2 Offset Semantics Work but Limited
**File**: [snapshot_view.py:537-538](src/backtest/runtime/snapshot_view.py#L537-L538)

```python
target_idx = ctx.current_idx - offset
if target_idx < 0 or target_idx >= feed.length:
    return None
```

**Issue**: Offset is "bars back" not "swings back". For structure features, strategies may want "previous swing" (not "value N bars ago").

**Recommendation**: Add structure-specific accessor:
```python
def get_last_n_structure_values(self, key: str, n: int, tf_role: str = "exec") -> List[float]:
    """Get last N non-NaN values for sparse structure feature."""
    # Implementation: scan backward to find N valid values
```

#### 3.3 Staleness Tracking Works
**File**: [snapshot_view.py:595-613](src/backtest/runtime/snapshot_view.py#L595-L613)

HTF/MTF staleness is properly tracked via `htf_is_stale` and `mtf_is_stale` properties.

**Conclusion**: Structure features at HTF/MTF will correctly forward-fill and report staleness.

---

## Review Area 4: Multi-Timeframe (MTF) Integration

### Status: ⚠️ Needs Attention

### Findings

#### 4.1 Structure Features Compute Independently per TF
**File**: [engine_data_prep.py:498-508](src/backtest/engine_data_prep.py#L498-L508)

Each TF gets its own feature computation:
```python
specs = config.feature_specs_by_role.get(tf_role) or \
        config.feature_specs_by_role.get('exec', [])
if specs:
    df = apply_feature_spec_indicators(df, specs)
```

**Conclusion**: Structure features can be computed independently per TF, same as indicators.

#### 4.2 Cross-TF Validation Not Currently Supported
**Issue**: Review question asked "Do structure features need cross-TF validation (e.g., HTF swing must contain LTF swings)?"

**Answer**: The current architecture does NOT support cross-TF validation during computation. Each TF's features are computed in isolation.

**Recommendation**:
- Document this as a known limitation
- If cross-TF validation is needed, it must be done:
  - Post-computation (after all TFs computed)
  - Or at runtime during strategy evaluation
- Consider adding optional cross-TF validator hook

#### 4.3 Forward-Fill Semantics Work Correctly
**File**: [snapshot_view.py:210-230](src/backtest/runtime/snapshot_view.py#L210-L230)

HTF/MTF contexts use last-closed index, which is correct for forward-fill semantics.

---

## Review Area 5: Warmup and Delay Bars

### Status: ⚠️ Needs Attention

### Findings

#### 5.1 Warmup Computed via Preflight (Good)
**File**: [engine_data_prep.py:178-191](src/backtest/engine_data_prep.py#L178-L191)

```python
warmup_bars_by_role = getattr(config, 'warmup_bars_by_role', {})
if not warmup_bars_by_role or 'exec' not in warmup_bars_by_role:
    raise ValueError("MISSING_WARMUP_CONFIG: warmup_bars_by_role['exec'] not set...")
```

**Conclusion**: Engine correctly reads warmup from Preflight, doesn't compute itself.

#### 5.2 Structure Warmup Needs New Formulas
**File**: [indicator_vendor.py:716-770](src/backtest/indicator_vendor.py#L716-L770)

Current warmup helpers are indicator-specific:
- `get_ema_warmup()`, `get_rsi_warmup()`, etc.

**Missing**: No helpers for structure features:
- `get_swing_warmup(lookback, confirmation)`: lookback + confirmation bars
- `get_pivot_warmup(depth, levels)`: depth * levels + buffer
- `get_trend_warmup(ema_length, confirmation)`: max(ema_warmup, confirmation)

**Recommendation**: Add structure warmup helpers to `indicator_vendor.py` or new `structure_vendor.py`.

#### 5.3 Delay Bars Work Correctly
**File**: [engine_data_prep.py:293-323](src/backtest/engine_data_prep.py#L293-L323)

Delay bars are applied AFTER warmup satisfaction, which is correct for structure features that need closed candles.

**Conclusion**: Structure features can use same delay_bars mechanism.

---

## Review Area 6: History Management

### Status: ⚠️ Needs Attention

### Findings

#### 6.1 History Stores FeatureSnapshots, Not Sparse Values
**File**: [engine_history.py:72-75](src/backtest/engine_history.py#L72-L75)

```python
self._history_bars_exec: List[CanonicalBar] = []
self._history_features_exec: List[FeatureSnapshot] = []
```

**Issue**: History stores full snapshots. For structure features that are sparse, this means:
- Many consecutive snapshots have same "last swing" value
- No efficient "get last N swings" query

**Recommendation**: Consider adding structure-specific history:
```python
self._history_swings_exec: Deque[SwingEvent] = deque(maxlen=50)
```

#### 6.2 Crossover Detection via Offset Works
**File**: [execution_validation.py:865-888](src/backtest/execution_validation.py#L865-L888)

Crossover operators (`CROSS_ABOVE`, `CROSS_BELOW`) use offset to get previous values:
```python
prev_val = self._get_feature_value(cond.indicator_key, cond.tf, snapshot, offset=cond.prev_offset)
```

**Conclusion**: Crossover with structure features works IF structure values are forward-filled.

#### 6.3 `bars_exec_low()` / `bars_exec_high()` Exist
**File**: [snapshot_view.py:393-417](src/backtest/runtime/snapshot_view.py#L393-L417)

These methods provide structure-like functionality (min/max over N bars):
```python
def bars_exec_low(self, n: int) -> Optional[float]:
    return float(np.min(self._feeds.exec_feed.low[start_idx:end_idx]))
```

**Conclusion**: Similar patterns can be used for structure features.

---

## Review Area 7: Artifact and Validation

### Status: ⚠️ Needs Attention

### Findings

#### 7.1 No Reference Implementation for Structure Features
**File**: [indicator_vendor.py](src/backtest/indicator_vendor.py)

Indicators use pandas_ta as reference implementation for math-parity validation. Structure features have no equivalent reference:
- No "pandas_ta swing detector"
- No standard library for pivot detection
- Trend/regime logic is strategy-specific

**Recommendation**:
- Create in-house reference implementation for structure features
- OR skip math-parity validation for structure (different validation approach)
- Consider golden-file validation instead (known inputs → expected outputs)

#### 7.2 FeatureArrays Metadata Supports Structure Features
**File**: [feature_frame_builder.py:74-90](src/backtest/features/feature_frame_builder.py#L74-L90)

Metadata validation ensures every array has provenance:
```python
if array_keys != metadata_keys:
    raise ValueError(f"Missing metadata for indicators: {missing}...")
```

**Conclusion**: Structure features will get same metadata tracking.

#### 7.3 Artifact Schema May Need Extension
Structure features may want to export additional artifacts:
- Swing event list (timestamps + prices)
- Pivot point coordinates
- Regime transitions

**Recommendation**: Plan for structure-specific artifact writers.

---

## Review Area 8: Hot Loop Performance

### Status: ✅ Safe (If Precomputed)

### Findings

#### 8.1 O(1) Access Contract Maintained
**File**: [snapshot_view.py](src/backtest/runtime/snapshot_view.py)

All data access is via array indexing:
```python
val = self.feed.indicators[name][self.current_idx]
```

**Conclusion**: Structure features will have O(1) access IF precomputed.

#### 8.2 No On-Demand Computation
**File**: [feed_store.py](src/backtest/runtime/feed_store.py)

FeedStore is immutable once built. No computation in hot loop.

**Critical Requirement**: Structure features MUST be precomputed by `FeatureFrameBuilder`, not computed on-demand.

#### 8.3 Binary Search for HTF Lookup
**File**: [feed_store.py:183-213](src/backtest/runtime/feed_store.py#L183-L213)

`get_last_closed_idx_at_or_before()` uses O(log n) binary search:
```python
pos = bisect.bisect_right(self._sorted_close_ms, ts_ms)
```

**Note**: If structure features need "find last swing index", a similar O(log n) lookup could be added. But prefer precomputed forward-fill for O(1) access.

---

## Review Area 9: IdeaCard Configuration

### Status: ⚠️ Needs Attention

### Findings

#### 9.1 IndicatorType Enum Needs Extension
**File**: [feature_spec.py:25-230](src/backtest/features/feature_spec.py#L25-L230)

Current enum has 150+ indicators from pandas_ta. Structure features need new entries:
```python
# Proposed (not in code):
SWING = "swing"
PIVOT = "pivot"
TREND = "trend"
REGIME = "regime"
```

**Recommendation**: Add structure indicator types to `IndicatorType` enum.

#### 9.2 Signal Rules Support Structure Features
**File**: [execution_validation.py:681-782](src/backtest/execution_validation.py#L681-L782)

`IdeaCardSignalEvaluator` evaluates conditions via `get_feature()`:
```python
current_val = self._get_feature_value(cond.indicator_key, cond.tf, snapshot, offset=0)
```

**Conclusion**: Structure features work in signal rules if declared in FeatureSpecs.

#### 9.3 Risk Model ATR Keys Work
**File**: [execution_validation.py:315-327](src/backtest/execution_validation.py#L315-L327)

Risk model can reference any feature key for SL/TP:
```python
if idea_card.risk_model.stop_loss.atr_key:
    refs.append(FeatureReference(
        key=idea_card.risk_model.stop_loss.atr_key,
        tf_role="exec",
        ...
    ))
```

**Conclusion**: Structure-based SL (e.g., "last swing low") can be implemented.

---

## Review Area 10: Error Handling and Edge Cases

### Status: ✅ Safe (Good Patterns Exist)

### Findings

#### 10.1 Fail-Loud Design
**File**: [feature_frame_builder.py:424-429](src/backtest/features/feature_frame_builder.py#L424-L429)

Missing features raise errors:
```python
if missing:
    raise ValueError(f"Missing required feature keys: {missing}")
```

**Conclusion**: Apply same pattern to structure features.

#### 10.2 KeyError for Undeclared Features
**File**: [snapshot_view.py:81-102](src/backtest/runtime/snapshot_view.py#L81-L102)

`get_indicator_strict()` raises KeyError with helpful message:
```python
raise KeyError(
    f"Indicator '{name}' not declared. "
    f"Available indicators: {available}. "
    f"Ensure indicator is specified in FeatureSpec/Idea Card."
)
```

**Conclusion**: Good error messages exist, apply to structure features.

#### 10.3 NaN Handling Returns None
**File**: [snapshot_view.py:77-79](src/backtest/runtime/snapshot_view.py#L77-L79)

```python
if np.isnan(val):
    return None
```

**Note**: For structure features, ensure forward-fill means NaN only during warmup.

---

## Specific Edge Cases Analysis

### Edge Case 1: Sparse Structure Features

**Scenario**: Swing detection produces value only every ~10-20 bars.

**Analysis**:
- Arrays must be full length (validation enforces this)
- Forward-fill during computation ensures continuous values
- NaN only during initial warmup period
- `get_feature()` returns last-known value correctly

**Recommendation**: Add `forward_fill_array()` utility to builder, apply to structure outputs.

### Edge Case 2: Multi-Value Structure Features

**Scenario**: Swing has price, index, strength, direction.

**Analysis**:
- Use `MULTI_OUTPUT_KEYS` pattern (already exists)
- Each output stored as separate array
- Access via `swing_high`, `swing_high_idx`, `swing_strength` keys

**Recommendation**: Define output keys in `MULTI_OUTPUT_KEYS` for structure types.

### Edge Case 3: Cross-TF Structure Validation

**Scenario**: HTF swing high must align with LTF data.

**Analysis**:
- Current architecture computes TFs independently
- No cross-TF validation during computation
- Must be done post-computation or at runtime

**Recommendation**:
- Document as limitation
- Add optional cross-TF validator hook in Preflight
- OR accept that cross-TF alignment is strategy responsibility

### Edge Case 4: Structure Features Depending on Indicators

**Scenario**: Trend detection uses EMA slope.

**Analysis**:
- Dependency validation already works ([feature_spec.py:573-589](src/backtest/features/feature_spec.py#L573-L589))
- Structure feature can declare `input_source=INDICATOR` with `input_indicator_key`
- Computation order respected

**Recommendation**: No changes needed, existing pattern works.

### Edge Case 5: Delay Bars with Structure Features

**Scenario**: Structure feature needs closed candle semantics.

**Analysis**:
- Delay bars apply to evaluation start, not computation
- Structure features computed on closed data (same as indicators)
- Delay ensures evaluation sees fully-formed structure values

**Recommendation**: No changes needed, existing pattern works.

### Edge Case 6: History Windows with Structure Features

**Scenario**: "Previous 3 swings" for analysis.

**Analysis**:
- Current history stores full FeatureSnapshots
- No efficient "find last N distinct values" query
- Offset-based access returns same forward-filled value

**Recommendation**: Add structure-specific history tracking:
```python
# New in HistoryManager
self._swing_events: Deque[SwingEvent] = deque(maxlen=20)
```

### Edge Case 7: Warmup Calculation for Structure Features

**Scenario**: Swing needs 50 bars lookback, indicators need 20.

**Analysis**:
- `max_warmup_bars` property uses max across all specs
- Structure with larger warmup will correctly extend data load

**Recommendation**: Ensure structure warmup formulas are added to `FeatureSpec.warmup_bars` property.

### Edge Case 8: Performance with Sparse Structure Features

**Scenario**: O(1) access to "last swing".

**Analysis**:
- Forward-fill during computation ensures O(1) access
- No runtime search needed if properly precomputed
- Same performance as indicators

**Critical**: Must precompute, not on-demand compute.

---

## Critical Architecture Issue: Hardcoded IndicatorType Enum

### Current State: Dual System with Duplication

The codebase has **two parallel systems** for defining indicator types:

1. **`IndicatorType` enum** ([feature_spec.py:25-230](src/backtest/features/feature_spec.py#L25-L230))
   - Hardcoded 150+ enum values
   - Used by `FeatureSpec.indicator_type` field
   - Has duplicate `MULTI_OUTPUT_KEYS` dict

2. **`SUPPORTED_INDICATORS` dict** ([indicator_registry.py:54-304](src/backtest/indicator_registry.py#L54-L304))
   - Data-driven, extensible
   - Defines inputs, params, outputs per indicator
   - Already used by `IndicatorRegistry`

**Problem**: Adding a new indicator type (like market structure features) requires:
- Adding to `IndicatorType` enum (hardcoded)
- Adding to `MULTI_OUTPUT_KEYS` dict (hardcoded)
- Adding to `SUPPORTED_INDICATORS` dict (data-driven)
- Adding warmup logic to `FeatureSpec.warmup_bars` (hardcoded switch)

### Proposed Solution: Registry-Driven Indicator Types

Replace the hardcoded `IndicatorType` enum with a **string-based, registry-validated approach**:

#### Option A: Use String Type with Registry Validation

```python
# feature_spec.py - PROPOSED CHANGE

@dataclass(frozen=True)
class FeatureSpec:
    """
    Specification for a single indicator/feature.

    indicator_type is now a STRING validated against IndicatorRegistry.
    """
    indicator_type: str  # Changed from IndicatorType enum to str
    output_key: str
    params: Dict[str, Any] = field(default_factory=dict)
    # ... rest unchanged

    def __post_init__(self):
        # Validate indicator_type against registry
        from ..indicator_registry import get_registry
        registry = get_registry()
        if not registry.is_supported(self.indicator_type):
            raise ValueError(
                f"Unsupported indicator type: '{self.indicator_type}'. "
                f"Supported: {registry.list_indicators()}"
            )
        # ... rest of validation
```

#### Option B: Dynamic Enum from Registry (Python 3.11+ Feature)

```python
# indicator_registry.py - Create enum dynamically from registry

def get_indicator_type_enum():
    """Create IndicatorType enum dynamically from SUPPORTED_INDICATORS."""
    from enum import Enum
    return Enum('IndicatorType', {
        name.upper(): name for name in SUPPORTED_INDICATORS.keys()
    })

# Usage: still get enum type-safety but from registry data
IndicatorType = get_indicator_type_enum()
```

### Recommended: Option A (String-Based)

**Rationale**:
1. **Simpler**: No enum gymnastics, just strings
2. **YAML-friendly**: IdeaCard YAML already uses strings
3. **Extensible**: Add new types by updating registry dict only
4. **Registry as Single Source of Truth**: All indicator metadata in one place

### Required Changes for String-Based Approach

#### 1. Update `FeatureSpec.indicator_type` to `str`

```python
# OLD
indicator_type: IndicatorType

# NEW
indicator_type: str  # Validated against IndicatorRegistry
```

#### 2. Move `MULTI_OUTPUT_KEYS` to Registry

The registry already has `output_keys` per indicator. Delete `MULTI_OUTPUT_KEYS` dict and use:

```python
# OLD (feature_spec.py)
MULTI_OUTPUT_KEYS: Dict[IndicatorType, Tuple[str, ...]] = {
    IndicatorType.MACD: ("macd", "signal", "histogram"),
    # ... 50+ entries
}

# NEW (use registry)
def is_multi_output(indicator_type: str) -> bool:
    return get_registry().is_multi_output(indicator_type)

def get_output_names(indicator_type: str) -> Tuple[str, ...]:
    return get_registry().get_output_suffixes(indicator_type)
```

#### 3. Move Warmup Logic to Registry

Add warmup formulas to `SUPPORTED_INDICATORS`:

```python
# indicator_registry.py - PROPOSED EXTENSION
SUPPORTED_INDICATORS = {
    "ema": {
        "inputs": {"close"},
        "params": {"length"},
        "multi_output": False,
        "warmup_formula": lambda p: p.get("length", 20) * 3,  # 3x length for EMA
    },
    "macd": {
        "inputs": {"close"},
        "params": {"fast", "slow", "signal"},
        "multi_output": True,
        "output_keys": ("macd", "signal", "histogram"),
        "warmup_formula": lambda p: p.get("slow", 26) * 3 + p.get("signal", 9),
    },
    # Market structure - just add to dict!
    "swing": {
        "inputs": {"high", "low", "close"},
        "params": {"lookback", "confirmation"},
        "multi_output": True,
        "output_keys": ("high", "high_idx", "low", "low_idx"),
        "warmup_formula": lambda p: p.get("lookback", 20) + p.get("confirmation", 3),
        "sparse": True,  # New flag for forward-fill requirement
        "compute_fn": "compute_swing_detection",  # Custom compute function
    },
}
```

#### 4. Update FeatureSpec.warmup_bars Property

```python
# feature_spec.py - PROPOSED CHANGE

@property
def warmup_bars(self) -> int:
    """Get warmup bars from registry formula."""
    from ..indicator_registry import get_registry
    registry = get_registry()
    info = registry.get_indicator_info(self.indicator_type)

    # Use registry-defined formula if available
    warmup_fn = info.warmup_formula
    if warmup_fn:
        return warmup_fn(self.params)

    # Fallback to length param
    return self.params.get("length", 0)
```

### Benefits of String-Based Approach

| Aspect | Enum-Based (Current) | String-Based (Proposed) |
|--------|---------------------|------------------------|
| Adding new indicator | Edit 4 files | Edit 1 dict |
| Type safety | Compile-time enum | Runtime validation |
| YAML parsing | Needs enum conversion | Direct string use |
| Registry sync | Manual, error-prone | Automatic |
| Market structure | Requires enum extension | Just add to dict |

### Migration Path

1. **Phase 1**: Add `indicator_type_str` field alongside enum (backward compat)
2. **Phase 2**: Update all code to use string-based validation
3. **Phase 3**: Deprecate `IndicatorType` enum
4. **Phase 4**: Remove enum, use strings only

---

## Recommended Implementation Order

### Phase 5.0: Registry Consolidation (Prerequisite)
1. Extend `SUPPORTED_INDICATORS` with `warmup_formula` field
2. Add `sparse` flag for structure features
3. Add `compute_fn` field for custom compute functions
4. Update `IndicatorInfo` dataclass with new fields

### Phase 5.1: String-Based Indicator Types
1. Change `FeatureSpec.indicator_type` from enum to string
2. Move `MULTI_OUTPUT_KEYS` lookups to registry
3. Move warmup calculation to registry formulas
4. Update YAML parsing to use strings directly

### Phase 5.2: Structure Feature Registration
1. Add structure entries to `SUPPORTED_INDICATORS` dict
2. Implement `compute_swing_detection()` function
3. Add `forward_fill_array()` utility to builder
4. Implement structure warmup formulas

### Phase 5.3: Runtime Enhancement (Optional)
1. Add structure-specific snapshot accessors
2. Add structure history tracking
3. Add cross-TF validation hook

### Phase 5.4: Validation & Testing
1. Create golden-file tests for structure algorithms
2. Add structure feature smoke tests to CLI
3. Document structure feature usage in IdeaCard

---

## Validation Checklist

- [x] All edge cases documented
- [x] Integration points identified
- [x] No blocking issues found (all addressable)
- [x] Recommendations provided for each finding
- [ ] Test cases suggested (see Phase 5.4)
- [x] Architecture assumptions validated

---

## Conclusion

The backtest engine architecture is well-suited for market structure integration with targeted extensions:

1. **Precomputation Pattern**: Structure features fit naturally if computed during `FeatureFrameBuilder.build()` and stored as forward-filled arrays.

2. **No Blocking Issues**: All identified issues have clear resolution paths. None require architectural rewrites.

3. **Key Extension Points**:
   - `IndicatorType` enum (add structure types)
   - `MULTI_OUTPUT_KEYS` dict (add structure outputs)
   - `FeatureSpec.warmup_bars` property (add structure formulas)
   - `forward_fill_array()` utility (new helper)

4. **Known Limitations**:
   - Cross-TF validation not supported during computation
   - No efficient "last N distinct values" query (workaround: dedicated structure history)

The existing O(1) hot loop performance can be maintained by ensuring all structure features are precomputed with forward-fill semantics.

---

## Next Steps

1. Update `docs/architecture/MARKET_STRUCTURE_INTEGRATION_PROPOSAL.md` with findings
2. Create `docs/todos/MARKET_STRUCTURE_PHASE5_CHECKLIST.md` with implementation tasks
3. Begin Phase 5.1: Foundation work (no breaking changes)
