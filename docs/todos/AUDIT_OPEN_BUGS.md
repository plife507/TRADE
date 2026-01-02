# Audit Open Bugs

**Source**: Agentic Audit Swarm (2026-01-01)
**Status**: ACTIVE

---

## Summary

| Priority | Total | Fixed | Open |
|----------|-------|-------|------|
| P0 | 0 | 0 | 0 |
| P1 | 16 | 12 | 4 |
| P2 | 20 | 1 | 19 |
| P3 | 10 | 0 | 10 |

---

## P1 Open (Deferred)

### P1-09: O(n) Operations in Snapshot Methods
- [ ] **Location**: `snapshot_view.py` - `bars_exec_high()`, `bars_exec_low()`
- [ ] **Issue**: List comprehensions iterate over slices per access
- [ ] **Impact**: Hot loop performance with large windows
- [ ] **Fix**: Pre-compute or use rolling numpy operations

### P1-12: TREND Assumes Single SWING Block
- [ ] **Location**: `builder.py:382-389`
- [ ] **Issue**: Multiple SWING blocks use arbitrary first one
- [ ] **Impact**: Low - dict insertion order mitigates
- [ ] **Fix**: Add explicit SWING-TREND linkage parameter

### P1-13: Dual Close Detection Mechanism
- [ ] **Location**: `TimeframeCache` vs `FeedStore`
- [ ] **Issue**: Two mechanisms for detecting candle close
- [ ] **Impact**: Low - tested extensively
- [ ] **Fix**: Consolidate to single close detection path

### P1-15: Schema Drift Detection Missing
- [ ] **Location**: `snapshot_view.py`
- [ ] **Issue**: No detection when new namespaces added without resolver updates
- [ ] **Impact**: Silent failures on new path patterns
- [ ] **Fix**: Add schema version assertion or resolver registry

---

## P2 Open

| ID | Location | Issue | Fix |
|----|----------|-------|-----|
| P2-02 | `engine.py` | UUID in trade ID (cosmetic nondeterminism) | Use sequential IDs |
| P2-03 | Various | JSON without sort_keys=True | Add sort_keys consistently |
| P2-04 | `types.py` | Legacy aliases SWING_OUTPUTS, TREND_OUTPUTS | Remove aliases |
| P2-05 | `StructureStore` | Mixed NaN handling in get_field() | Standardize approach |
| P2-06 | `builder.py:315` | ATR TODO not resolved | Wire ATR through |
| P2-07 | `snapshot_view.py:741` | String split in hot path | Accept pre-parsed tokens |
| P2-08 | Multiple | Duplicate operator aliases | Single source of truth |
| P2-09 | `types.py` | RULE_EVAL_SCHEMA_VERSION unused | Remove or implement |
| P2-10 | `state_tracker.py` | History manager internal access (_bars_exec) | Add public API |
| P2-11 | Validation | V_65 not wired to comparison test | Wire to test suite |
| P2-12 | `engine.py` | StateTracker.reset() not called on init | Add reset call |
| P2-13 | Engine hooks | Missing type hints | Add type annotations |
| P2-14 | `snapshot_view.py` | PRICE_FIELDS incomplete for high/low | Add missing fields |
| P2-15 | Various | mark_price_source soft-fail validation | Make fail-loud |
| P2-16 | Hash functions | Truncation to 8-16 chars | Consider full hash |
| P2-17 | `artifact_standards.py` | Renamed fields via silent fallbacks | Document or remove |
| P2-18 | `TimeframeCache` | No persistence or versioning | Add cache versioning |
| P2-19 | `structure.py` | Zone interaction smoke embedded | Extract to own file |
| P2-20 | `__init__.py` | run_state_tracking_smoke not in __all__ | Add to exports |

---

## P3 Open (Polish)

| ID | Location | Issue |
|----|----------|-------|
| P3-01 | ReasonCode | Redundant R_ prefix |
| P3-02 | Registry | Logical operators defined not implemented |
| P3-03 | Types | Docstring "bullish" vs UP/DOWN naming |
| P3-04 | Various | Missing TYPE_CHECKING import guard |
| P3-05 | Smoke tests | Inconsistent naming convention |
| P3-06 | Structure smoke | Magic numbers |
| P3-07 | Versioning | Inconsistent formats (semver vs "0.1-dev") |
| P3-08 | Parquet | Version hardcoded |
| P3-09 | StateTracker | ActionState unused signal_id field |
| P3-10 | GateContext | GATE_CODE_DESCRIPTIONS could be enum attr |

---

## Archive

Full audit reports archived at: `docs/audits/2026-01-01/`

| File | Description |
|------|-------------|
| AUDIT_00_ARCHITECTURE.md | Architecture Lead |
| AUDIT_10_ENGINE_LOOP.md | Engine Hot Loop |
| AUDIT_15_MTF_FEEDS.md | MTF Feed & Alignment |
| AUDIT_20_SNAPSHOT_RESOLUTION.md | Snapshot Resolution |
| AUDIT_25_MARK_PRICE.md | Mark Price Simulation |
| AUDIT_30_RULES_COMPILER.md | Rules Compiler |
| AUDIT_40_MARKET_STRUCTURE.md | Market Structure |
| AUDIT_50_STATE_TRACKING.md | State Tracking |
| AUDIT_60_SCHEMA_AND_ARTIFACTS.md | Schema & Artifacts |
| AUDIT_70_TEST_COVERAGE.md | Test Coverage |
| AUDIT_INDEX.md | Executive Summary |
| RISK_REGISTER.md | Full Risk Catalog |
| FIX_PLAN.md | Remediation Plan (completed) |
