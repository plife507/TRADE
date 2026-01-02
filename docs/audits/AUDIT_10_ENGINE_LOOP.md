# AUDIT_10: Engine Hot Loop and Determinism Audit

**Date**: 2026-01-01
**Auditor**: Agent B (Engine Hot Loop and Determinism Auditor)
**Status**: COMPLETE

---

## Executive Summary

The engine hot loop is well-designed for determinism and correctness. The array-backed architecture successfully eliminates pandas operations from the critical path (with one minor exception). The identified issues are maintenance/polish items, not correctness bugs.

---

## 1. Scope

### What Was Reviewed

- **Engine hot loop** (`src/backtest/engine.py`) - The `run()` method, bar-by-bar simulation
- **Snapshot building** (`src/backtest/engine_snapshot.py`) - RuntimeSnapshotView construction
- **Feed store building** (`src/backtest/engine_feed_builder.py`) - FeedStore creation
- **Feed store runtime** (`src/backtest/runtime/feed_store.py`) - O(1) array access
- **Snapshot view** (`src/backtest/runtime/snapshot_view.py`) - RuntimeSnapshotView implementation
- **Simulated exchange** (`src/backtest/sim/exchange.py`) - Order processing, TP/SL checks
- **Cache layer** (`src/backtest/runtime/cache.py`) - TimeframeCache for HTF/MTF
- **Market structure builder** (`src/backtest/market_structure/builder.py`) - Structure computation
- **Type definitions** (`src/backtest/types.py`) - Data structures and serialization
- **Artifact writer** (`src/backtest/engine_artifacts.py`) - JSON/Parquet output

---

## 2. Contract Checks

### 2.1 Determinism - PASS with P2 recommendations

| Risk | Location | Severity | Analysis |
|------|----------|----------|----------|
| UUID generation | `engine.py:1122`, `exchange.py:252,426,513` | P2 | Cosmetic nondeterminism only - does NOT affect simulation output |
| Dict iteration in warmup | `engine.py:797-798`, `engine.py:830-831` | P1 | Relies on Python 3.7+ dict ordering |
| Set iteration for close_ts | `cache.py:69,73`, `feed_store.py:96` | PASS | Sets used for membership testing only |
| JSON without sort_keys | `engine_artifacts.py:157,178` | P2 | Should add sort_keys for determinism |
| Float equality | Multiple locations | PASS | No `== 0.0` comparisons found |

### 2.2 Closed-Candle Only - PASS

- **Lookahead guard assertions** at `engine.py:951-963`
- **HTF/MTF forward-fill** only updates on exact ts_close match
- **Indicator precomputation** outside hot loop
- **Structure computation** runs before simulation starts

### 2.3 Step Order - PASS

Actual step order in `run()` (lines 744-1019):
1. Create Bar from exec_feed[i]
2. Set bar context on exchange
3. process_bar() - fills pending orders, checks TP/SL
4. Skip if warmup period
5. Update HTF/MTF indices
6. Extract features for history
7. Check stop conditions
8. Accumulate 1m quotes and freeze rollups
9. Build snapshot view
10. Invoke on_snapshot callback
11. Check readiness gate
12. Lookahead guard assertions
13. Call strategy
14. Process signal -> submit order
15. Record equity/account curve
16. Update history
17. prev_bar = bar

### 2.4 Bar Monotonicity - PASS

- Single loop iteration ensures each bar processed exactly once
- FeedStore sorts by timestamp before building arrays

### 2.5 O(1) Hot Loop Access - RISK (P2)

**Found pandas usage**: `pd.isna(val)` at `engine.py:799,832`

Should use `np.isnan()` instead.

---

## 3. Findings

### P0 (Correctness) - None Found

### P1 (High-Risk)

| ID | Finding | Location | Impact |
|----|---------|----------|--------|
| P1.1 | Dict key iteration order | `engine.py:797-798, 830-831` | Relies on Python 3.7+ dict ordering |

### P2 (Maintainability)

| ID | Finding | Location | Impact |
|----|---------|----------|--------|
| P2.1 | UUID cosmetic nondeterminism | `engine.py:1122`, `exchange.py` | Complicates artifact comparison |
| P2.2 | JSON without sort_keys | `engine_artifacts.py:157,178` | Non-deterministic key ordering |
| P2.3 | pd.isna() in hot loop | `engine.py:799,832` | Minor performance overhead |
| P2.4 | builder.py to_dict() | `builder.py:74` | Missing sort_keys=True |

### P3 (Polish)

| ID | Finding | Location | Impact |
|----|---------|----------|--------|
| P3.1 | Redundant snapshot ready update | `engine.py:776,921` | Minor inefficiency |

---

## 4. Recommendations

### Immediate (P2 Fixes)

1. **Add sort_keys to artifact JSON** (`engine_artifacts.py` lines 157, 178)
2. **Replace pd.isna with np.isnan** (`engine.py` lines 799, 832)
3. **Add sort_keys to manifest entry** (`builder.py` line 74)

### Future Consideration (P1)

4. **Explicit dict key sorting for indicator iteration**
5. **Seeded UUID alternative for reproducible IDs** if exact artifact comparison needed

---

## 5. Summary

| Contract | Status | Notes |
|----------|--------|-------|
| Determinism | **PASS** | Cosmetic nondeterminism (UUIDs), recommend sort_keys fixes |
| Closed-candle only | **PASS** | Explicit assertions guard against lookahead |
| Step order | **PASS** | Correct sequence enforced |
| Bar monotonicity | **PASS** | Single iteration, sorted data |
| O(1) hot loop | **RISK (P2)** | Minor pd.isna() usage |

---

**Audit Complete**

Auditor: Agent B (Engine Hot Loop and Determinism Auditor)
