# AUDIT_00: Architecture Lead Audit

**Audit Date**: 2026-01-01
**Auditor Role**: Architecture Lead Auditor (Agent A)
**Status**: COMPLETE

---

## Executive Summary

The TRADE backtesting engine demonstrates **strong architectural discipline** with clear module boundaries, explicit dependency contracts, and a well-designed "variable structure" extension pattern. The array-backed FeedStore architecture achieves O(1) data access in the hot loop as designed. Key contracts around determinism, closed-candle-only semantics, and stable snapshot paths are enforced through explicit checks and fail-loud patterns.

**Top 3 Risks Identified:**

1. **P1 (High Risk)**: `RuntimeSnapshotView._NAMESPACE_RESOLVERS` dispatch table is a static class variable, not instance-based, which could cause issues if extended in subclasses or during concurrent testing.

2. **P1 (High Risk)**: `MultiTFPreparedFrames.warmup_multiplier` is hardcoded to 1 and marked as "legacy" but the field remains in the dataclass, creating potential confusion for future maintenance.

3. **P2 (Maintainability)**: The `build_structures_into_feed()` function in `engine_feed_builder.py` modifies FeedStore in-place (mutations), violating the otherwise immutable design pattern of FeedStore.

---

## 1. Scope

### What Was Reviewed

| Module Path | Focus Area |
|-------------|------------|
| `src/backtest/engine.py` | Main orchestrator, hot loop, multi-TF dispatch |
| `src/backtest/engine_data_prep.py` | Data loading, warmup computation, delay bars |
| `src/backtest/engine_feed_builder.py` | FeedStore construction, structure wiring |
| `src/backtest/engine_snapshot.py` | Snapshot view construction, HTF/MTF index updates |
| `src/backtest/runtime/feed_store.py` | FeedStore/MultiTFFeedStore immutable store design |
| `src/backtest/runtime/snapshot_view.py` | RuntimeSnapshotView path resolver, TFContext |
| `src/backtest/market_structure/builder.py` | StructureBuilder extension pattern |
| `src/backtest/market_structure/registry.py` | Structure type registry |

### What Was NOT Reviewed (Out of Scope)

- `src/backtest/sim/` exchange internals (simulated order execution, ledger)
- `src/backtest/rules/` rule evaluation (compile, eval)
- `src/backtest/artifacts/` artifact writing
- `src/backtest/indicators.py` indicator computation
- Play parsing and validation
- CLI command implementations
- Test/validation Plays

---

## 2. Contract Checks

### 2.1 Determinism Contract - PASS

| Enforcement Point | Status | Notes |
|-------------------|--------|-------|
| FeedStore is immutable after construction | **PASS** | No mutators exposed; `from_dataframe()` returns new instance |
| No Python `random` in hot loop | **PASS** | Not observed in reviewed modules |
| Sorted data in `from_dataframe()` | **PASS** | `df.sort_values("timestamp")` called |
| HTF/MTF update order | **PASS** | `refresh_tf_caches_impl()` updates HTF first, then MTF (deterministic) |
| Structure computation is pure | **PASS** | `StructureBuilder.build()` takes OHLCV arrays, returns stores |

### 2.2 Closed-Candle Only Contract - PASS

| Enforcement Point | Status | Notes |
|-------------------|--------|-------|
| Indicator computation on full DF before loop | **PASS** | `apply_feature_spec_indicators(df, specs)` in prep phase |
| HTF/MTF forward-fill semantics | **PASS** | `update_htf_mtf_indices_impl()` uses `get_idx_at_ts_close()` |
| `get_last_closed_idx_at_or_before()` logic | **PASS** | Binary search on sorted close timestamps |
| No partial bar access in TFContext | **PASS** | `current_idx` always points to closed bar |
| Structure arrays computed offline | **PASS** | `StructureBuilder.build()` runs before hot loop |

### 2.3 Stable Public Snapshot Contract - PASS (with P1 risk)

| Enforcement Point | Status | Notes |
|-------------------|--------|-------|
| `RuntimeSnapshotView.get(path)` dispatcher | **PASS** | Namespace-based dispatch table |
| `_NAMESPACE_RESOLVERS` registry | **RISK** | Static class variable, not protected against modification |
| `_resolve_structure_path()` validation | **PASS** | Validates block_key exists, field in allowlist |
| `_resolve_indicator_path()` graceful None | **PASS** | Returns None for missing, no silent defaults |
| `_resolve_price_path()` explicit fields | **PASS** | Only mark.close/high/low supported, others raise ValueError |

### 2.4 Variable Structure Architecture Contract - PASS

| Requirement | Status | Implementation |
|-------------|--------|----------------|
| Registry-based type registration | **PASS** | `STRUCTURE_REGISTRY` in `market_structure/registry.py` |
| Array storage via StructureStore | **PASS** | `StructureStore.fields: Dict[str, np.ndarray]` |
| Snapshot path resolution | **PASS** | `get()` -> `_resolve_structure_path()` -> `FeedStore.get_structure_field()` |
| No engine.py modification needed | **PASS** | `build_structures_into_feed()` handles wiring generically |
| Zone sub-namespace support | **PASS** | `structure.<block_key>.zones.<zone_key>.<field>` path pattern |

---

## 3. Findings

### P0 (Correctness Breach) - None Found

### P1 (High-Risk Debt)

#### P1.1: Static Namespace Resolver Dispatch Table

**Location**: `runtime/snapshot_view.py:712-718`

```python
_NAMESPACE_RESOLVERS = {
    "price": "_resolve_price_path",
    "indicator": "_resolve_indicator_path",
    "structure": "_resolve_structure_path",
}
```

**Risk**: Class variable can be accidentally modified, especially in test fixtures or subclasses.

**Recommendation**: Convert to `types.MappingProxyType` or validate in `__init__`.

#### P1.2: Legacy warmup_multiplier Field

**Location**: `engine_data_prep.py:83` in `MultiTFPreparedFrames`

**Risk**: Confusing for maintainers. Field exists but is never used with any value other than 1.

**Recommendation**: Remove field from dataclass or add deprecation comment.

#### P1.3: FeedStore Mutation in build_structures_into_feed()

**Location**: `engine_feed_builder.py:226-227`

**Risk**: FeedStore is documented as immutable, but structures are mutated after construction.

**Recommendation**: Document mutation window explicitly or use builder pattern.

### P2 (Maintainability)

- Duplicate ts_close conversion logic across multiple files
- Long method: `prepare_multi_tf_frames_impl()` at 261 lines

### P3 (Polish)

- Dead comment reference to undefined `warmup_multiplier` in error message
- Missing type hints in factory methods (should use `Sequence[str]` for read-only list parameters)

---

## 4. Performance Notes

### Hot Loop Allocations - OK

| Location | Allocation | Status |
|----------|------------|--------|
| `RuntimeSnapshotView.__init__()` | TFContext creation | **OK** - 3 small dataclass objects per bar |
| `build_snapshot_view_impl()` | RuntimeSnapshotView | **OK** - O(1) object creation |
| `get_structure_field()` | None | **OK** - Direct array access |
| `get_feature()` | None | **OK** - Direct array access |

### O(1) Access Verification - PASS

| Access Pattern | Method | Complexity |
|----------------|--------|------------|
| Indicator at index | `feed.indicators[name][idx]` | O(1) |
| OHLCV at index | `feed.close[idx]` | O(1) |
| Structure field at index | `store.fields[name][idx]` | O(1) |
| Zone field at index | `store.zones[key].fields[name][idx]` | O(1) |
| HTF/MTF index lookup | `ts_close_ms_to_idx[ts_ms]` | O(1) dict |
| Binary search for forward-fill | `bisect.bisect_right()` | O(log n) - acceptable |

---

## 5. Recommendations

### Immediate (Before Next Phase)

1. **[P1.3]** Document or refactor FeedStore structure mutation pattern
2. **[P3.1]** Fix undefined `warmup_multiplier` in error message

### Short-Term (Phase 5.2+)

3. **[P1.1]** Freeze `_NAMESPACE_RESOLVERS` with MappingProxyType
4. **[P1.2]** Remove or deprecate `warmup_multiplier` field
5. **[P2.1]** Extract `datetime_to_epoch_ms()` utility

### Medium-Term (Refactor Window)

6. **[P2.3]** Decompose `prepare_multi_tf_frames_impl()` into smaller functions

---

**Audit Complete**

Auditor: Agent A (Architecture Lead)
