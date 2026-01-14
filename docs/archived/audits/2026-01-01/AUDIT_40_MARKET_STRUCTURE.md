# AUDIT_40: Market Structure Core Audit

**Date**: 2026-01-01
**Auditor**: Agent E (Market Structure Core Auditor)
**Status**: COMPLETE
**Scope**: Market Structure Builder, Detectors, and Zone Interaction (Stages 0-6)

---

## Executive Summary

The market structure subsystem is **well-designed and correctly implemented** for Stages 0-6. The architecture supports variable structure types with minimal engine changes. Zone interaction logic correctly implements closed-candle-only semantics with proper reset rules.

---

## 1. Scope

### What Was Reviewed

- **Structure Builder Orchestration**: StructureBuilder, StructureStore, ZoneStore
- **Detectors**: SwingDetector, TrendClassifier, ZoneDetector
- **Zone Interaction Logic**: ZoneInteractionComputer (touched/inside/time_in_zone)
- **Slot Semantics and Array Storage**: FeedStore structure/zone integration
- **Instance ID Determinism**: compute_zone_instance_id, compute_zone_spec_id
- **Override Ordering**: Dependency resolution and zone metric computation order
- **Registry and Type System**: STRUCTURE_REGISTRY, StructureType, ZoneType, ZoneState, TrendState

---

## 2. Contract Checks

### 2.1 Closed-Candle Only - PASS

| Invariant | Status |
|-----------|--------|
| All structure updates occur only on candle close | **PASS** |
| Zone state transitions on close only | **PASS** |
| Zone interaction uses closed bar OHLC | **PASS** |

### 2.2 Determinism - PASS

- `instance_id` uses SHA256 of canonical string
- `spec_id/block_id` uses sorted JSON with separators
- All detectors use no randomness

### 2.3 Slot Semantics - PASS

Storage hierarchy:
```
FeedStore.structures[block_id] -> StructureStore
  |-- fields: Dict[field_name, np.ndarray]
  +-- zones[zone_key] -> ZoneStore
       +-- fields: Dict[field_name, np.ndarray]
```

### 2.4 Variable Structure Architecture - PASS

Adding new structure type requires only:
1. Register in types.py
2. Define outputs in types.py
3. Create detector
4. Register detector
5. Add validation Play

**No engine changes required**.

### 2.5 Override Ordering - PASS

- SWING before TREND via `_resolve_dependency_order()`
- Zone state before interaction (locked ordering)
- BROKEN bar zeroes all metrics

---

## 3. Findings

### P0 (Correctness) - None Found

### P1 (High-Risk)

#### P1.1: TREND Dependency Assumes Single SWING Block

**Location**: `builder.py:382-389`

If multiple SWING blocks exist, TREND uses arbitrary first one.

**Mitigation**: Python 3.7+ guarantees dict insertion order.

#### P1.2: Zone Width Fallback to 1%

**Location**: `zone_detector.py:248-252`

Silent fallback if ATR not available. Not fail-loud per project rules.

**Recommendation**: Fail loudly or document warmup behavior.

### P2 (Maintainability)

- **P2.1**: Legacy aliases `SWING_OUTPUTS`, `TREND_OUTPUTS` in types.py
- **P2.2**: Mixed NaN handling in `StructureStore.get_field()`
- **P2.3**: ATR TODO not resolved in `builder.py:315`

### P3 (Polish)

- Docstring misalignment between "bullish" and UP/DOWN naming
- Missing TYPE_CHECKING import guard

---

## 4. Zone Interaction Verification (Stage 6)

### Metric Formulas - CORRECT

| Metric | Formula | Status |
|--------|---------|--------|
| touched | `(bar_low <= upper) AND (bar_high >= lower)` | CORRECT |
| inside | `(bar_close >= lower) AND (bar_close <= upper)` | CORRECT |
| time_in_zone | Increment if inside AND same instance, else 0 | CORRECT |

### Reset Rules - PASS

| Rule | Status |
|------|--------|
| Reset when state != ACTIVE | PASS |
| Reset when instance_id changes | PASS |
| BROKEN bar override (all metrics to 0) | PASS |

---

## 5. Performance Notes

### O(1) Access - PASS

| Access Pattern | Status |
|----------------|--------|
| `FeedStore.get_structure_field()` | O(1) |
| `FeedStore.get_zone_field()` | O(1) |
| `RuntimeSnapshotView.get("structure.*")` | O(1) |

### Loop Complexity

| Detector | Complexity |
|----------|------------|
| SwingDetector | O(n * window) - bottleneck |
| TrendClassifier | O(n) |
| ZoneDetector | O(n) |
| ZoneInteractionComputer | O(n) |

---

## 6. Recommendations

### Immediate (P1 Fixes)

1. **P1.2**: Wire ATR through to ZoneDetector or fail loudly

### Short-Term (P2 Fixes)

1. Remove legacy aliases from types.py
2. Resolve ATR TODO in builder.py

### Medium-Term

1. Add explicit SWING-TREND linkage
2. Consider SwingDetector optimization with numpy rolling max/min

---

**Audit Complete**

Auditor: Agent E (Market Structure Core Auditor)
