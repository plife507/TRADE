# AUDIT_20: Snapshot Resolution Path Contracts

**Audit Date**: 2026-01-01
**Auditor**: Agent C - Snapshot/Resolver & Path Contract Auditor
**Scope**: RuntimeSnapshotView path resolution for price/structure/indicator access
**Status**: COMPLETE

---

## Executive Summary

The snapshot resolution system is **well-designed** with dispatch table pattern for scalable namespace handling, registry-driven structure resolution, explicit fail-fast on unknown paths, and schema versioning for drift tracking.

---

## 1. Scope

### What Was Reviewed

1. **RuntimeSnapshotView** - Path resolution via `get()` method, namespace dispatch
2. **FeedStore** - Structure storage and field access methods
3. **Market Structure Registry** - Detector registration, type validation
4. **Market Structure Builder** - StructureStore creation and wiring
5. **Market Structure Types** - Output schemas, public field mappings
6. **MarkPriceEngine** - Mark price resolution
7. **IdeaCard** - Feature spec parsing and path construction
8. **Rules Compilation** - CompiledRef path validation
9. **Rules Evaluation** - Condition evaluation against snapshot
10. **Engine Snapshot** - Snapshot construction

---

## 2. Contract Checks

### Contract 1: Stable Public Snapshot Contract - PASS

Dispatch table pattern ensures deterministic resolution. Code explicitly raises `ValueError` for unknown namespaces.

### Contract 2: Fields Additive-Only - RISK (P2)

Policy documented but not code-enforced. No automated schema drift detection.

### Contract 3: Registry-Driven Resolution - PASS

Resolution uses dictionary dispatch throughout. No if/else chains on structure type.

### Contract 4: O(1) Access Guarantees - RISK (P1)

Primary paths are O(1). However:
- `bars_exec_low()` / `bars_exec_high()` are O(n) reduction operations
- Datetime conversion allocates Python objects

---

## 3. Findings

### P0 (Correctness) - None Found

### P1 (High-Risk)

#### P1-1: O(n) Operations in Snapshot Methods

**Location**: `snapshot_view.py` lines 375-399

**Issue**: `bars_exec_low()` and `bars_exec_high()` use `np.min()` / `np.max()` over slices

**Recommendation**: Document as O(n) with recommended max values.

### P2 (Maintainability)

#### P2-1: No Automated Schema Drift Detection

**Location**: `types.py` STRUCTURE_SCHEMA_VERSION

**Recommendation**: Add baseline file and validation test.

#### P2-2: PRICE_FIELDS Registry Incomplete

**Location**: `compile.py` lines 33-37

**Issue**: Registry shows `mark.close` but runtime also supports `mark.high` and `mark.low`

**Recommendation**: Update to `{"close", "high", "low"}`

#### P2-3: Zone Field Validation Deferred to Runtime

IdeaCard typos in zone paths won't be caught until backtest execution.

### P3 (Polish)

- Inconsistent naming: `ltf` vs `exec` aliases
- `price.last.*` placeholder exists but not implemented

---

## 4. O(1) Access Paths (Verified)

1. **Indicator lookup**: `feed.indicators[key][idx]` - dict lookup + array index
2. **OHLCV lookup**: `feed.close[idx]` - direct array index
3. **Structure field lookup**: `structure_key_map[key]` -> `structures[block_id]` -> `fields[field][idx]`
4. **Zone field lookup**: Extends structure path with one more dict lookup
5. **Mark price**: Stored as scalar in snapshot - O(1) property access

---

## 5. Recommendations

### Immediate (Before Next Release)

1. **Update PRICE_FIELDS** in `compile.py` to include `high` and `low` for mark prices
2. **Document O(n) methods** in `bars_exec_low/high` docstrings

### Near-Term (Next Sprint)

3. **Add schema drift validation** - Create baseline file and validate against it
4. **Add zone compile-time validation** - Pass available zones to path validation

---

**Audit Complete**

Auditor: Agent C (Snapshot/Resolver Auditor)
