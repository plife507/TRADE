# Open Bugs

**Last Updated**: 2026-01-04
**Status**: ALL BUGS FIXED or ACCEPTABLE

---

## Summary

| Priority | Open | Description |
|----------|------|-------------|
| P0 | 0 | Critical blockers |
| P1 | 0 | High priority (FIXED) |
| P2 | 0 | Medium priority (1 FIXED, 1 ACCEPTABLE) |
| P3 | 0 | Polish (2 ACCEPTABLE) |

**Validation Status**: ALL TESTS PASS
- IdeaCards: 15/15 normalize (V_100-V_122 blocks format)
- Indicators: **42/42 pass stress test** (all single + multi-output)
- Crossover operators: cross_above, cross_below ENABLED
- Rollup: 11/11 intervals pass
- Metrics: 6/6 tests pass
- Structure smoke: All stages pass
- Stress test Tier 1-2: 7/7 produce trades
- Stress test Tier 3: swing (205), zone (491) verified

---

## P0 Open

*None*

---

## P1 Open

*None* - All P1 bugs fixed in 2026-01-03 session

---

## P2 (All Resolved)

### P2-02: Dynamic Attribute Access
- **Location**: `indicator_vendor.py:193`
- **Issue**: `getattr(ta, indicator_name, None)` relies on external library structure
- **Status**: ACCEPTABLE - Registry validates indicator exists before getattr call
- **Impact**: Minimal - pandas_ta interface is stable
- **Effort**: N/A

### P2-05: Silent Trade Rejection with Tight Stops + Large Sizing - FIXED
- **Location**: `src/core/risk_manager.py:286`
- **Issue**: `percent_equity` sizing with value=10.0 + stop_loss ≤3% produces 0 trades silently
- **Root Cause**: Signals created with `size_usdt=0` (engine computes later) were rejected by
  RiskManager Check 6 (min_viable_size=5.0) because `0 < 5`
- **Fix**: Skip min_viable_size check when `signal.size_usdt == 0` (backtest engine case)
- **Verified**: Test confirms signals with size_usdt=0 now pass risk checks
- **Status**: FIXED in 2026-01-04 session

### P2-06: Multi-Output Indicator Reference Mismatch - FIXED
- **Location**: `compile_idea_card()` in `idea_card_yaml_builder.py`
- **Issue**: `compile_idea_card` used `spec.output_key` instead of `spec.output_keys_list`
- **Fix**: Changed to use `spec.output_keys_list` to include all multi-output expanded keys
- **Verified**: All 16 multi-output indicators now pass (macd, bbands, stoch, etc.)
- **Status**: FIXED in 2026-01-03 stress test session

---

## P3 (All Acceptable)

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

## Resolved This Session (2026-01-04)

### P2-05: Silent Trade Rejection - FIXED
- **Location**: `src/core/risk_manager.py:286`
- **Issue**: Backtest signals with `size_usdt=0` were rejected by min_viable_size check
- **Fix**: Skip min_viable_size check when `signal.size_usdt == 0` (engine computes size later)
- **Verified**: Test confirms signals pass risk checks

---

## Resolved Previous Session (2026-01-03)

### ENHANCEMENT: Crossover Operators Enabled
- **Location**: `src/backtest/rules/registry.py`, `eval.py`, `snapshot_view.py`, `idea_card.py`
- **Feature**: `cross_above` and `cross_below` operators now fully supported
- **Implementation**:
  1. Removed from `BANNED_OPERATORS` in `idea_card.py`
  2. Set `supported=True` in `OPERATOR_REGISTRY`
  3. Added `eval_cross_above()` and `eval_cross_below()` functions
  4. Added `get_with_offset()` to `RuntimeSnapshotView` for prev-bar access
  5. Updated `evaluate_condition()` to handle crossover operators
- **Semantics**:
  - `cross_above`: `prev_lhs < rhs AND curr_lhs >= rhs`
  - `cross_below`: `prev_lhs > rhs AND curr_lhs <= rhs`
- **Verified**: V_80_ema_crossover.yml (16 trades) validates and runs
- **Validation**: `configs/idea_cards/_validation/V_80_ema_crossover.yml`

### P2-07: Structure Paths Fail Validation - FIXED
- **Location**: `execution_validation.py:validate_idea_card_features()` and `idea_card_yaml_builder.py:compile_idea_card()`
- **Issue**: Structure paths like `structure.swing.high_level` failed validation because:
  1. `validate_idea_card_features()` didn't skip structure paths
  2. `compile_idea_card()` only checked `market_structure_blocks` (old format), not `structure_specs_exec` (new format)
- **Fix**:
  1. Added skip for `structure.` prefixed paths in validation
  2. Added `structure_specs_exec` and `structure_specs_htf` to available_structures in compile
- **Verified**: V_70 swing (205 trades), V_72 zone (491 trades) now work

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
| 2026-01-03 | This session | 9 fixes + crossover enhancement |
| 2026-01-03 | [archived/2026-01-03_BUGS_RESOLVED.md](archived/2026-01-03_BUGS_RESOLVED.md) | 72 (P0:7, P1:25, P2:28, P3:12) |
| 2026-01-01 | [2026-01-01/](2026-01-01/) | Original audit reports |
