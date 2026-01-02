# AUDIT_25: price.mark.* Contract Audit

**Agent**: J - Price/Mark Simulation & Contract Auditor
**Date**: 2026-01-01
**Status**: COMPLETE

---

## Executive Summary

The `price.mark.*` contract is **well-designed and consistently enforced** across the codebase. Single producer pattern ensures all consumers use the same mark price. O(1) deterministic lookup via integer timestamps.

---

## 1. Scope

### What Was Reviewed

- **price.mark.* contract definition** and documented semantics
- **All consumers** of mark price across the codebase
- **Providers/engines** for mark price computation
- **Alias contract** for price.mark.high/low
- **Semantic drift risks** between "true mark" vs "exec OHLC"
- **O(1) lookup determinism** and float handling

---

## 2. Contract Verification

### 2.1 Stable price.mark.* Semantics - PASS

| Invariant | Status |
|-----------|--------|
| `price.mark.close` returns scalar float at exec bar | **PASS** |
| Mark price computed exactly once per step | **PASS** |
| Mark price source is configurable (close/hlc3/ohlc4) | **PASS** |
| Engine validates mark_price_source at startup | **PASS** |

### 2.2 Alias Contract - PASS

| Path | Status | Notes |
|------|--------|-------|
| `price.mark.close` | PASS | Primary mark price |
| `price.mark.high` | PASS | Stage 6: exec-bar high (alias) |
| `price.mark.low` | PASS | Stage 6: exec-bar low (alias) |

### 2.3 Deterministic O(1) Lookup - PASS

- `SimMarkProvider._ts_to_idx` uses integer milliseconds as dict keys
- No float equality comparisons
- Arrays immutable after init

### 2.4 All Consumers Use Same Semantics - PASS

| Consumer | Status |
|----------|--------|
| Snapshot resolution | PASS |
| Ledger MTM | PASS |
| Liquidation check | PASS |
| Unrealized PnL | PASS |
| Exit price source | PASS |
| Rules evaluation | PASS |
| EventLog | PASS |

---

## 3. Findings

### P0 (Correctness) - None

### P1 (High-Risk) - None

### P2 (Maintainability)

#### P2-1: mark_price_source validation is soft-fail

**Location**: `engine.py` L849-852

Logs warning but doesn't fail-fast. PriceModel will raise on unknown sources.

#### P2-2: Execution model bar.close vs mark.close distinction unclear

**Location**: `execution_model.py` L255-259

Exit price fallback to `bar.close` is correct but could benefit from comment.

#### P2-3: PRICE_FIELDS registry incomplete for Stage 6

**Location**: `compile.py` L34-36

Comment says Stage 6 adds high/low, but registry only has `close`.

**Recommendation**: Update to `{"close", "high", "low"}`

### P3 (Polish)

- SimMarkProvider.SOURCE_NAME hardcoded
- Multiple places track mark_price_source (not a bug, serves different purposes)

---

## 4. Performance Notes

| Operation | Complexity | Status |
|-----------|------------|--------|
| `snapshot.get("price.mark.close")` | O(1) | PASS |
| Mark price lookup | O(1) dict | PASS |
| Snapshot creation | O(1) | PASS |

---

## 5. Recommendations

### Immediate

1. **Update PRICE_FIELDS registry** to include `high` and `low`

### Short-Term

2. **Add inline documentation** in `execution_model.py` clarifying bar.close vs mark.close
3. **Consider fail-fast validation** for unsupported mark_price_source

---

**Audit Complete**

Auditor: Agent J (Price/Mark Simulation Auditor)
