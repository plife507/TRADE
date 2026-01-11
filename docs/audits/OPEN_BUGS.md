# Open Bugs

**Last Updated**: 2026-01-10
**Status**: 0 OPEN BUGS (Structure Module Production Validation Complete)

---

## Summary

| Priority | Open | Description |
|----------|------|-------------|
| P0 | 0 | Critical blockers |
| P1 | 0 | High priority |
| P2 | 0 | Medium priority |
| P3 | 0 | Polish |

**Validation Status**: ALL TESTS PASS
- Validation plays relocated to `tests/validation/plays/`
- Indicators: **42/42 pass stress test** (all single + multi-output)
- **Structures: 163/163 stress tests pass** (136 single-TF + 11 HTF/MTF + 16 zone)
- Crossover operators: cross_above, cross_below ENABLED (TradingView semantics)
- Window operators: anchor_tf now properly scales offsets
- Rollup: 11/11 intervals pass
- Metrics: 6/6 tests pass
- Structure smoke: All stages pass
- HTF structures: 5/5 pass (1h/4h swing, trend)
- MTF confluence: 6/6 pass (exec+HTF alignment patterns)
- Zone structures: 16/16 pass (demand/supply zones, state machine, last_price interaction)

**NOTE**: Terminology migration COMPLETE (IdeaCard -> Play, --play -> --play)

---

## P0 Open

*None*

---

## P1 Open

*None*

---

## P2 Open

*None* - All P2 bugs fixed in 2026-01-09 session

---

## P3 Open

*None* - All P3 bugs fixed in 2026-01-09 session

---

## Resolved This Session (2026-01-10) - Structure Module Production

### BUG-016: derived_zone Wrong Dependency Key in Plays - FIXED
- **Location**: 40 stress test plays in `tests/stress/plays/struct_gate_08_*` and `struct_gate_09_*`
- **Issue**: Plays used `depends_on: {swing: swing}` for derived_zone, but code expects `depends_on: {source: swing}`
- **Root Cause**: derived_zone uses `source:` key (not `swing:`) to allow flexible source types
- **Fix**: Changed all derived_zone plays to use `source: swing` in depends_on
- **Verified**: All 40 plays now pass
- **Documentation**: Updated PLAY_DSL_COOKBOOK.md with correct syntax
- **Status**: FIXED

### BUG-017: ENUM Literal Treated as Feature Reference - FIXED
- **Location**: `src/backtest/play/play.py:161-168`
- **Issue**: ENUM literals like `NONE`, `ACTIVE`, `BROKEN` were converted to feature references, causing "Feature 'NONE' referenced but not declared" errors
- **Root Cause**: DSL parser converted ALL string RHS values to feature references without checking for ENUM literals
- **Fix**: Added ENUM literal detection: ALL_CAPS strings with only letters/underscores are preserved as scalar strings
- **Code Change**:
  ```python
  # Before: all strings became feature refs
  rhs = {"feature_id": rhs_raw}

  # After: check for ENUM pattern first
  elif rhs_raw.isupper() and rhs_raw.replace("_", "").isalpha():
      rhs = rhs_raw  # Keep ENUM literals as scalars
  ```
- **Verified**: All 4 affected plays in Gate 08 now pass
- **Status**: FIXED

### BUG-018: Gate 17 Plays Wrong Dependency Keys After Bulk Fix - FIXED
- **Location**: 4 plays in `tests/stress/plays/struct_gate_17_ultimate/`
- **Issue**: Bulk sed fix for BUG-016 incorrectly changed `swing: swing` to `source: swing` for trend/fibonacci structures
- **Root Cause**: Sed replaced ALL occurrences, but trend/fibonacci expect `swing: swing`, only derived_zone expects `source: swing`
- **Fix**: Manually restored correct dependency keys:
  - `trend` and `fibonacci`: `depends_on: {swing: swing}`
  - `derived_zone`: `depends_on: {source: swing}`
- **Verified**: All 4 Gate 17 ultimate plays pass
- **Status**: FIXED

### COOKBOOK-001: derived_zone depends_on Documentation Wrong - FIXED
- **Location**: `docs/specs/PLAY_DSL_COOKBOOK.md` (multiple locations)
- **Issue**: Cookbook showed `depends_on: {swing: swing}` for derived_zone
- **Fix**: Updated to `depends_on: {source: swing}` with NOTE explaining the difference
- **Status**: FIXED

### BUG-019: Zone Detector Used Lowercase States - FIXED
- **Location**: `src/backtest/incremental/detectors/zone.py`
- **Issue**: Zone detector used lowercase states ("none", "active", "broken") while DSL ENUM literal check only preserves uppercase strings
- **Root Cause**: Inconsistency between zone (lowercase) and derived_zone (uppercase) state values
- **Fix**: Changed zone.py to use uppercase states ("NONE", "ACTIVE", "BROKEN") for consistency
- **Code Change**: Updated all state assignments from lowercase to uppercase
- **Verified**: All 10 zone stress tests now pass
- **Status**: FIXED

### ENHANCEMENT: Zone Structure Test Coverage Added
- **Location**: `tests/stress/plays/struct_gate_15_zone/` (16 plays)
- **Feature**: Comprehensive zone structure testing with real market patterns
- **Content**:
  - Demand zone bounce (long), Supply zone rejection (short)
  - Zone state ACTIVE/BROKEN detection
  - Zone boundary field access (upper, lower)
  - Zone + trend confluence patterns
  - Zone version field tracking
  - **last_price + zone interaction** (6 plays for live trading parity)
    - last_price near_pct zone boundaries
    - last_price cross_above/cross_below zone boundaries
    - last_price inside zone detection
- **Status**: COMPLETE (16/16 pass)

### ENHANCEMENT: HTF Structure Documentation Added
- **Location**: `docs/specs/PLAY_DSL_COOKBOOK.md` Section 8 (Multi-Timeframe)
- **Feature**: Added "HTF Structures" and "MTF Confluence Patterns" subsections
- **Content**:
  - HTF structure YAML syntax
  - Pattern 1: Exec Swing + HTF Trend Filter
  - Pattern 2: Dual-Timeframe Trend Alignment
  - Pattern 3: HTF Fib + Exec Swing
- **Status**: COMPLETE

---

## Resolved This Session (2026-01-09)

### BUG-014: Index Out of Bounds in 1m Subloop - FIXED
- **Location**: `src/backtest/engine.py:1390-1420`
- **Issue**: `_evaluate_with_1m_subloop` crashed with `IndexError: index 133859 is out of bounds for axis 0 with size 133852` when quote feed didn't fully cover simulation range
- **Root Cause**: `start_1m` was not bounds-checked, only `end_1m` was clamped
- **Fix**:
  1. Clamp both `start_1m` and `end_1m` to valid range
  2. Add fallback to exec close when `start_1m > end_1m` (quote feed doesn't cover exec bar)
  3. Add bounds check for `start_1m - 1` access
- **Verified**: All 4 affected XRPUSDT plays now pass (S_L_151, S_S_151, S_L_165, S_S_165)
- **Status**: FIXED

### BUG-015: HTF Data Coverage Check Too Strict for Bar Alignment - FIXED
- **Location**: `src/data/historical_data_store.py`, `src/backtest/runtime/preflight.py`
- **Issue**: Gate 20 plays with 4h HTF features failed with `INSUFFICIENT_COVERAGE` even when data existed
- **Root Causes**:
  1. Data query used `timestamp >= start` which missed bars containing but not starting at requested time
  2. Coverage check compared `max_ts >= required_end` but max_ts is bar START, not END
- **Fix**:
  1. Added `floor_to_bar_boundary()` to round query start times down to bar boundaries
  2. Updated coverage check to use `max_ts + bar_duration` for effective end coverage
- **Verified**: All 12 Gate 20 plays pass, all Gate 21 HTF plays pass
- **Status**: FIXED

### P2-AUDIT-01: Hard-coded min_viable_size Constant - FIXED
- **Location**: `src/core/risk_manager.py:285`
- **Issue**: `min_viable_size = 5.0` was hard-coded instead of configurable
- **Fix**: Added `min_viable_size_usdt` to `RiskConfig` dataclass, updated risk_manager to use config value
- **Status**: FIXED

### P2-AUDIT-02: Incomplete Partial Close Trade Tracking - DOCUMENTED
- **Location**: `src/backtest/sim/exchange.py:946-965`
- **Issue**: Partial closes do not create intermediate Trade records
- **Resolution**: Behavior is intentional and already documented in docstring. Partial closes realize PnL but only create Trade record on final close.
- **Status**: DOCUMENTED (intentional behavior)

### P2-AUDIT-03: Quote Feed Fallback is Silent - FIXED
- **Location**: `src/backtest/engine.py:1364-1374`
- **Issue**: When 1m data unavailable, engine silently fell back to exec close
- **Fix**: Added warning log (once per run) when fallback is used, with instructions to sync 1m data
- **Status**: FIXED

### P2-AUDIT-04: Clock Drift Warning Only, No Block - FIXED
- **Location**: `src/exchanges/bybit_client.py:186-194`
- **Issue**: Clock drift >1s ahead only logged error, didn't block
- **Fix**: Now raises `RuntimeError` with instructions to sync clock when drift >1000ms ahead
- **Status**: FIXED

### P2-AUDIT-05: ExchangeMetrics Initialized but Unused - FIXED
- **Location**: `src/backtest/sim/exchange.py:139`
- **Issue**: `self._metrics = ExchangeMetrics()` was created but never used
- **Fix**: Removed unused import and initialization
- **Status**: FIXED

### P3-AUDIT-01: Legacy Property Aliases - FIXED
- **Location**: `src/backtest/sim/exchange.py:208-223`
- **Issue**: Legacy aliases duplicated `*_usdt` properties
- **Fix**: Removed legacy aliases (`equity`, `cash_balance`, `available_balance`, `free_margin`). Updated callers in engine.py and bar_processor.py to use `*_usdt` versions.
- **Status**: FIXED

### P3-AUDIT-02: Outdated Docstring References - FIXED
- **Location**: `src/backtest/runtime/snapshot_view.py`
- **Issue**: Docstrings referenced "Idea Card" instead of "Play"
- **Fix**: Replaced all 3 occurrences of "Idea Card" with "Play"
- **Status**: FIXED

### P3-AUDIT-03: Unbounded Path Cache Growth - FIXED
- **Location**: `src/backtest/runtime/snapshot_view.py:56`
- **Issue**: `_PATH_CACHE` dict grew unbounded
- **Fix**: Replaced with `@lru_cache(maxsize=1024)` function `_tokenize_path()`
- **Status**: FIXED

---

## Resolved Previous Session (2026-01-07)

### P2-SIM-02: Frozen Fill Dataclass Crash - FIXED
- **Location**: `src/backtest/sim/execution_model.py:fill_exit()`
- **Issue**: `fill_exit()` was missing `close_ratio` parameter, causing crash with frozen dataclass
- **Fix**: Added `close_ratio` param to `fill_exit()` function signature
- **Status**: FIXED in 2026-01-07 session

### P2-005: last_price Offset Support for Crossover - FIXED
- **Location**: `src/backtest/rules/eval.py`
- **Issue**: `last_price` could not be used with crossover operators (needed offset=1 for prev value)
- **Fix**: Added `prev_last_price` tracking to enable crossover evaluation
- **Status**: FIXED in 2026-01-07 session

### P1-001: Crossover Semantics Misaligned with TradingView - FIXED
- **Location**: `src/backtest/rules/eval.py:eval_cross_above(), eval_cross_below()`
- **Issue**: Crossover used `prev < rhs AND curr >= rhs` instead of TradingView standard
- **Fix**: Aligned to TradingView: `cross_above` = `prev <= rhs AND curr > rhs`
- **Semantics**:
  - `cross_above`: `prev_lhs <= rhs AND curr_lhs > rhs`
  - `cross_below`: `prev_lhs >= rhs AND curr_lhs < rhs`
- **Status**: FIXED in 2026-01-07 session

### P1-002: anchor_tf Ignored in Window Operators - FIXED
- **Location**: `src/backtest/rules/eval.py`
- **Issue**: `anchor_tf` parameter was declared but not used - window operators always used bars=N literally
- **Fix**: Offsets now scale by anchor_tf minutes (e.g., `bars: 3, anchor_tf: "1h"` = 180 minutes lookback)
- **Status**: FIXED in 2026-01-07 session

### P2-004: Duration Bar Ceiling Missing - FIXED
- **Location**: `src/backtest/rules/duration.py:duration_to_bars()`
- **Issue**: Duration to bar conversion did not handle ceiling properly
- **Fix**: Added proper ceiling check in `duration_to_bars()`
- **Status**: FIXED in 2026-01-07 session

---

## P2 Resolved (Previous Sessions)

### P2-09: Backtest Run Requires --smoke or Explicit --start/--end - FIXED
- **Location**: `src/backtest/runner.py:223-250`
- **Issue**: Running `backtest run --play X` without `--smoke` or explicit dates failed
- **Fix**: Auto-infer window from DB coverage using `store.status(symbol)`
- **Details**: Gets first_timestamp and last_timestamp from sync metadata
- **Verified**: `backtest run --play I_001_ema` now runs with full DB coverage
- **Status**: FIXED in 2026-01-05 session

### P2-10: Structure-Only Plays Rejected - FIXED
- **Location**: `src/backtest/play.py:570`
- **Issue**: Plays with `structures:` but empty `features:` failed validation
- **Fix**: Added `has_structures` flag, allow empty features if structures exist
- **Details**: Validation now checks `if not self.features and not self.has_structures`
- **Verified**: `S_007_structure_only.yml` with `features: []` runs successfully
- **Status**: FIXED in 2026-01-05 session

### P2-11: Structure References Require `structure.` Prefix - FIXED
- **Location**: `src/backtest/rules/compile.py:388-391`, `src/backtest/execution_validation.py:398-410`
- **Issue**: Users had to write `feature_id: "structure.swing"` instead of `feature_id: "swing"`
- **Fix**: Auto-resolve structure keys without prefix to `structure.*` paths
- **Details**:
  1. Added `structure_keys` field to Play class (extracted from structures: section)
  2. compile.py: Check if key is in available_structures before adding indicator namespace
  3. execution_validation.py: Skip validation for known structure keys
- **Result**: Both `feature_id: "swing"` and `feature_id: "structure.swing"` now work
- **Status**: FIXED in 2026-01-05 session

### P2-08: Windows Emoji Encoding Breaks Data Sync - FIXED
- **Location**: `src/data/historical_data_store.py:46-80`
- **Issue**: Spinner animation with emoji caused `UnicodeEncodeError` on Windows
- **Root Cause**: Detection logic tested if Python could encode emoji, but didn't account for
  console display capability on legacy terminals (cmd.exe, PowerShell 5.x with cp1252)
- **Fix**: Rewrote `_detect_ascii_mode()` with conservative approach:
  - Default to ASCII on Windows unless explicitly known UTF-8 terminal
  - Check for Windows Terminal (`WT_SESSION`)
  - Check for VS Code terminal (`TERM_PROGRAM`)
  - Check for ConEmu/Cmder (`ConEmuANSI`)
  - Check for explicit `PYTHONIOENCODING=utf-8`
  - Only then check stdout encoding
- **Investigation**: See `docs/audits/WINDOWS_ENCODING_INVESTIGATION.md`
- **Status**: FIXED in 2026-01-05 session

### P2-02: Dynamic Attribute Access
- **Location**: `indicator_vendor.py:193`
- **Issue**: `getattr(ta, indicator_name, None)` relies on external library structure
- **Status**: ACCEPTABLE - Registry validates indicator exists before getattr call
- **Impact**: Minimal - pandas_ta interface is stable
- **Effort**: N/A

### P2-05: Silent Trade Rejection with Tight Stops + Large Sizing - FIXED
- **Location**: `src/core/risk_manager.py:286`
- **Issue**: `percent_equity` sizing with value=10.0 + stop_loss <=3% produces 0 trades silently
- **Root Cause**: Signals created with `size_usdt=0` (engine computes later) were rejected by
  RiskManager Check 6 (min_viable_size=5.0) because `0 < 5`
- **Fix**: Skip min_viable_size check when `signal.size_usdt == 0` (backtest engine case)
- **Verified**: Test confirms signals with size_usdt=0 now pass risk checks
- **Status**: FIXED in 2026-01-04 session

### P2-06: Multi-Output Indicator Reference Mismatch - FIXED
- **Location**: `compile_play()` in `play_yaml_builder.py`
- **Issue**: `compile_play` used `spec.output_key` instead of `spec.output_keys_list`
- **Fix**: Changed to use `spec.output_keys_list` to include all multi-output expanded keys
- **Verified**: All 16 multi-output indicators now pass (macd, bbands, stoch, etc.)
- **Status**: FIXED in 2026-01-03 stress test session

---

## P3 Resolved

### P3-05: PLAY_SYNTAX.md Documentation Mismatch - FIXED
- **Location**: `docs/specs/PLAY_SYNTAX.md`
- **Issue**: Docs showed `feature_id: "swing"` for structures but code required `feature_id: "structure.swing"`
- **Fix**: Fixed the code (P2-11) to accept both formats. Will update docs to document both.
- **Result**: Both `swing` and `structure.swing` now work - no doc mismatch
- **Status**: FIXED in 2026-01-05 session

---

## P3 (All Acceptable)

### P3-02: Dead Code Comments
- **Location**: `runtime/snapshot_view.py:23-25`
- **Issue**: "LEGACY REMOVED:" section listing removed classes
- **Status**: ACCEPTABLE - serves as documentation reference for removed code
- **Effort**: N/A

### P3-04: Type Ignores in Audit Code
- **Location**: `src/forge/audits/audit_incremental_registry.py:56,278` (planned location after migration)
- **Issue**: `# type: ignore` comments in test code
- **Status**: ACCEPTABLE - intentional test pattern for testing error paths
- **Effort**: N/A

---

## Resolved Previous Session (2026-01-03)

### ENHANCEMENT: Crossover Operators Enabled
- **Location**: `src/backtest/rules/registry.py`, `eval.py`, `snapshot_view.py`, `play.py` (after migration)
- **Feature**: `cross_above` and `cross_below` operators now fully supported
- **Implementation**:
  1. Removed from `BANNED_OPERATORS` in `play.py`
  2. Set `supported=True` in `OPERATOR_REGISTRY`
  3. Added `eval_cross_above()` and `eval_cross_below()` functions
  4. Added `get_with_offset()` to `RuntimeSnapshotView` for prev-bar access
  5. Updated `evaluate_condition()` to handle crossover operators
- **Semantics** (updated 2026-01-07 to TradingView standard):
  - `cross_above`: `prev_lhs <= rhs AND curr_lhs > rhs`
  - `cross_below`: `prev_lhs >= rhs AND curr_lhs < rhs`
- **Verified**: V_80_ema_crossover.yml (16 trades) validates and runs
- **Validation**: `tests/validation/plays/V_80_ema_crossover.yml`

### P2-07: Structure Paths Fail Validation - FIXED
- **Location**: `execution_validation.py:validate_play_features()` and `play_yaml_builder.py:compile_play()` (after migration)
- **Issue**: Structure paths like `structure.swing.high_level` failed validation because:
  1. `validate_play_features()` didn't skip structure paths
  2. `compile_play()` only checked `market_structure_blocks` (old format), not `structure_specs_exec` (new format)
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

| Date | Document | Bugs Found/Fixed |
|------|----------|------------------|
| 2026-01-10 | Structure Module Production | 4 FIXED (BUG-016,017,018,019) + 2 doc fixes + zone tests |
| 2026-01-09 | Senior Dev Audit | 8 FIXED (P2:5, P3:3) |
| 2026-01-07 | Previous session | 5 fixes (P1-001, P1-002, P2-004, P2-005, P2-SIM-02) |
| 2026-01-05 | Previous session | 4 fixes (P2-08, P2-09, P2-10, P2-11, P3-05) |
| 2026-01-03 | Previous session | 9 fixes + crossover enhancement |
| 2026-01-03 | [archived/2026-01-03_BUGS_RESOLVED.md](archived/2026-01-03_BUGS_RESOLVED.md) | 72 (P0:7, P1:25, P2:28, P3:12) |
| 2026-01-01 | [2026-01-01/](2026-01-01/) | Original audit reports |
