# Open Bugs

**Last Updated**: 2026-01-03 (Fresh Audit)
**Status**: Post-Refactor Audit Complete

---

## Summary

| Priority | Open | Description |
|----------|------|-------------|
| P0 | 0 | Critical blockers |
| P1 | 2 | High priority - config patterns |
| P2 | 3 | Medium priority - type safety |
| P3 | 4 | Polish - cleanup |

**Validation Status**: ALL TESTS PASS
- IdeaCards: 9/9 normalize
- Indicators: 42/42 pass audit
- Rollup: 11/11 intervals pass
- Metrics: 6/6 tests pass
- Structure smoke: All stages pass

---

## P0 Open

*None*

---

## P1 Open

### P1-01: Deprecated Config Pattern (hasattr guards)
- **Location**: `engine_data_prep.py` (lines 177, 229, 246, 426, 485, 520, 713)
- **Issue**: Excessive `hasattr(config, 'feature_specs_by_role')` checks
- **Impact**: Indicates mixed old/new config usage, code bloat
- **Fix**: Standardize all config objects to always have `feature_specs_by_role`
- **Effort**: 2h

### P1-02: Hardcoded max_exposure_pct
- **Location**: `runtime/state_tracker.py:244`
- **Issue**: `max_exposure_pct = 100.0` with TODO comment
- **Impact**: Max exposure not configurable for risk management
- **Fix**: Move to `StateTrackerConfig` or gate configuration
- **Effort**: 30m

---

## P2 Open

### P2-01: Loose Type Checking with hasattr()
- **Location**: Multiple files (~20+ locations)
- **Files**: `engine.py`, `engine_data_prep.py`, `engine_feed_builder.py`, `sim/exchange.py`
- **Issue**: Defensive attribute checks for attributes that should be guaranteed
- **Impact**: Unclear which attributes are required vs optional
- **Fix**: Use proper type hints and dataclass validation
- **Effort**: 4h

### P2-02: Dynamic Attribute Access
- **Location**: `indicator_vendor.py:193`
- **Issue**: `getattr(ta, indicator_name, None)` relies on external library structure
- **Impact**: Could break on pandas_ta library updates
- **Fix**: Use registry pattern with explicit function mapping
- **Effort**: 2h

### P2-03: Type Checking Suppression
- **Location**: `audits/audit_incremental_registry.py:56,278`
- **Issue**: `# type: ignore` comments suppress type checking
- **Impact**: Type checker can't validate audit code
- **Fix**: Fix underlying type issues
- **Effort**: 1h

---

## P3 Open

### P3-01: Deprecated market_structure_blocks
- **Location**: `engine_feed_builder.py:170-190`
- **Issue**: Old format still supported with deprecation warning
- **Impact**: Tech debt, dual code paths
- **Fix**: Set deprecation timeline, remove in next major version
- **Effort**: 1h

### P3-02: Dead Code Comments
- **Location**: `runtime/snapshot_view.py:23-25`
- **Issue**: "LEGACY REMOVED:" section listing removed classes
- **Status**: Acceptable (serves as reference)
- **Effort**: 5m

### P3-03: Conditional Default Values
- **Location**: `engine.py:296`
- **Issue**: `hasattr(config.risk_profile, 'max_drawdown_pct')` with default
- **Impact**: Unclear if field is guaranteed
- **Fix**: Make all fields required on dataclasses
- **Effort**: 30m

### P3-04: Type Ignores in Audit Code
- **Location**: `audits/audit_primitives.py:226-238`
- **Issue**: `_ = value` throwaway variables in error tests
- **Status**: Acceptable (intentional test pattern)
- **Effort**: None needed

---

## Audit Checklist (Common Bug Patterns)

When auditing, check for these patterns:

### Determinism
- [x] `json.dump()` with `sort_keys=True` - VERIFIED
- [x] Sequential IDs (no UUID) - VERIFIED
- [x] Dict iteration with sorting - VERIFIED

### Fail-Loud Validation
- [x] Config fields with `__post_init__` checks - VERIFIED
- [ ] Some hasattr guards remain (P1-01)

### NaN/None Handling
- [x] `math.isnan()` for NaN checks - VERIFIED
- [x] Consistent return types - VERIFIED

### Dead Code
- [x] Unused enums removed - VERIFIED
- [x] Duplicate class names resolved - VERIFIED
- [ ] Deprecated code paths remain (P3-01)

### Performance (Hot Loop)
- [x] O(1) operations - VERIFIED (Incremental State)
- [x] No DataFrame in hot path - VERIFIED
- [x] Path caching - VERIFIED

---

## Archive

| Date | Document | Bugs Fixed |
|------|----------|------------|
| 2026-01-03 | [archived/2026-01-03_BUGS_RESOLVED.md](archived/2026-01-03_BUGS_RESOLVED.md) | 72 (P0:7, P1:25, P2:28, P3:12) |
| 2026-01-01 | [2026-01-01/](2026-01-01/) | Original audit reports |
