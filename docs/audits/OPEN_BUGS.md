# Open Bugs

**Last Updated**: 2026-01-03 (Bug Fix Session)
**Status**: All P1 fixed, P2/P3 reduced

---

## Summary

| Priority | Open | Description |
|----------|------|-------------|
| P0 | 0 | Critical blockers |
| P1 | 0 | High priority - config patterns (FIXED) |
| P2 | 1 | Medium priority - type safety |
| P3 | 2 | Polish - cleanup |

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

*None* - All P1 bugs fixed in 2026-01-03 session

---

## P2 Open

### P2-02: Dynamic Attribute Access
- **Location**: `indicator_vendor.py:193`
- **Issue**: `getattr(ta, indicator_name, None)` relies on external library structure
- **Status**: ACCEPTABLE - Registry validates indicator exists before getattr call
- **Impact**: Minimal - pandas_ta interface is stable
- **Effort**: N/A

---

## P3 Open

### P3-02: Dead Code Comments
- **Location**: `runtime/snapshot_view.py:23-25`
- **Issue**: "LEGACY REMOVED:" section listing removed classes
- **Status**: ACCEPTABLE - serves as documentation reference for removed code
- **Effort**: N/A

### P3-04: Type Ignores in Audit Code
- **Location**: `audits/audit_incremental_registry.py:56,278`
- **Issue**: `# type: ignore` comments in test code
- **Status**: ACCEPTABLE - intentional test pattern for testing error paths
- **Effort**: N/A

---

## Resolved This Session (2026-01-03)

### P1-01: Deprecated Config Pattern (hasattr guards) - FIXED
- **Fix**: Removed 8 hasattr guards for `feature_specs_by_role` in `engine_data_prep.py`, `engine_feed_builder.py`
- **Rationale**: `SystemConfig.feature_specs_by_role` is always defined (default: empty dict)

### P1-02: Hardcoded max_exposure_pct - FIXED
- **Fix**: Added `max_exposure_pct` field to `StateTrackerConfig` dataclass
- **Location**: `runtime/state_tracker.py`

### P2-01: Loose Type Checking with hasattr() - FIXED
- **Fix**: Part of P1-01 - all hasattr guards for config fields removed

### P2-03: Type Checking Suppression - CLOSED
- **Status**: ACCEPTABLE - `# type: ignore` in audit tests is intentional for testing error paths

### P3-01: Deprecated market_structure_blocks - FIXED
- **Fix**: Added concrete removal date (2026-04-01) and migration guide
- **Location**: `engine_feed_builder.py` header comments and warning messages

### P3-03: Conditional Default Values - FIXED
- **Fix**: Added `max_drawdown_pct` to `RiskProfileConfig` dataclass (default: 100.0)
- **Location**: `system_config.py`, `engine.py`

---

## Audit Checklist (Common Bug Patterns)

When auditing, check for these patterns:

### Determinism
- [x] `json.dump()` with `sort_keys=True` - VERIFIED
- [x] Sequential IDs (no UUID) - VERIFIED
- [x] Dict iteration with sorting - VERIFIED

### Fail-Loud Validation
- [x] Config fields with `__post_init__` checks - VERIFIED
- [x] No hasattr guards for guaranteed fields - VERIFIED (P1-01 fixed)

### NaN/None Handling
- [x] `math.isnan()` for NaN checks - VERIFIED
- [x] Consistent return types - VERIFIED

### Dead Code
- [x] Unused enums removed - VERIFIED
- [x] Duplicate class names resolved - VERIFIED
- [x] Deprecated code paths have removal timeline - VERIFIED (P3-01 fixed)

### Performance (Hot Loop)
- [x] O(1) operations - VERIFIED (Incremental State)
- [x] No DataFrame in hot path - VERIFIED
- [x] Path caching - VERIFIED

---

## Archive

| Date | Document | Bugs Fixed |
|------|----------|------------|
| 2026-01-03 | This session | 7 (P1:2, P2:2, P3:3) |
| 2026-01-03 | [archived/2026-01-03_BUGS_RESOLVED.md](archived/2026-01-03_BUGS_RESOLVED.md) | 72 (P0:7, P1:25, P2:28, P3:12) |
| 2026-01-01 | [2026-01-01/](2026-01-01/) | Original audit reports |
