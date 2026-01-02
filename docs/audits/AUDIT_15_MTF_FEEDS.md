# AUDIT_15: Multi-Timeframe Feed and Alignment Audit

**Auditor**: Agent I (MTF Feed and Alignment Auditor)
**Date**: 2026-01-01
**Status**: COMPLETE

---

## Executive Summary

The MTF feed and alignment system is **well-designed and correctly implements TradingView-style `lookahead_off` semantics**. The forward-fill logic is deterministic and O(1) for the critical path. One minor architectural concern exists regarding the dual close detection mechanism (TimeframeCache + FeedStore indices), but this does not impact correctness.

---

## 1. Scope

### What Was Reviewed

- Multi-timeframe data preparation and loading
- HTF/MTF/LTF alignment logic and forward-fill behavior
- Warmup/delay enforcement across timeframes
- TimeframeCache mechanics and close detection
- RuntimeSnapshotView and TFContext for MTF access
- Hot loop execution order and determinism
- Lookahead prevention mechanisms

### Files Reviewed

| File | Key Functions/Classes |
|------|----------------------|
| `src/backtest/engine_data_prep.py` | `prepare_multi_tf_frames_impl`, `get_tf_features_at_close_impl` |
| `src/backtest/engine_snapshot.py` | `update_htf_mtf_indices_impl`, `refresh_tf_caches_impl`, `build_snapshot_view_impl` |
| `src/backtest/runtime/feed_store.py` | `FeedStore`, `MultiTFFeedStore`, O(1) index lookups |
| `src/backtest/runtime/cache.py` | `TimeframeCache`, `refresh_step`, close timestamp sets |
| `src/backtest/runtime/snapshot_view.py` | `RuntimeSnapshotView`, `TFContext`, staleness properties |
| `src/backtest/runtime/timeframe.py` | `tf_duration`, `tf_minutes`, `ceil_to_tf_close` |
| `src/backtest/engine.py` | Main hot loop implementation |

---

## 2. Contract Checks (6/6 PASS)

### Contract 1: Closed-Candle Only Across TFs - PASS

HTF/MTF indicator values are last-closed only. FeedStore holds precomputed arrays from closed DataFrames.

### Contract 2: Alignment (Forward-Fill) - PASS

HTF/MTF context indices remain at last-closed bar until next HTF/MTF close aligns with exec close. Forward-fill is O(1) via `ts_close_ms_to_idx` dict lookup.

### Contract 3: Warmup/Delay Enforcement - PASS

Fail-loud enforcement: missing warmup config raises explicit ValueError. Multi-TF mode computes `max_eval_start_ts` across all roles.

### Contract 4: Deterministic Step Order - PASS

Each bar follows: advance feeds -> update indices -> build snapshot -> evaluate -> orders.

### Contract 5: No Double-Processing TF Closes - PASS

Set-based close detection guarantees uniqueness.

### Contract 6: Monotonic ts_close - PASS

Data sorted by timestamp + sequential index iteration.

---

## 3. Findings

### P0 (Correctness) - None Found

### P1 (High-Risk)

#### P1-1: TimeframeCache Has Parallel Mechanism to FeedStore Index Updates

**Location**: `cache.py` TimeframeCache vs `engine_snapshot.py` update_htf_mtf_indices_impl

**Issue**: Two mechanisms exist for detecting/handling HTF/MTF closes. The engine primarily uses FeedStore indices. TimeframeCache appears to be legacy.

**Recommendation**: Consolidate to single close detection mechanism or document why both are needed.

### P2 (Maintainability)

- **P2-1**: Warmup handling split across multiple files
- **P2-2**: FeedStore.get_last_closed_idx_at_or_before uses O(log n) binary search (minor impact)

### P3 (Polish)

- **P3-1**: Staleness properties (`htf_is_stale`, `mtf_is_stale`) not used in hot loop
- **P3-2**: History update position comment could reference contract

---

## 4. Performance Notes

### Hot-Loop O(1) Access

| Operation | Complexity |
|-----------|------------|
| Bar OHLCV access | O(1) |
| Indicator access | O(1) |
| HTF/MTF index update | O(1) |
| Close detection | O(1) |
| Snapshot creation | O(1) |

### Specific Verifications

- **HTF EMA Values Remain Constant Until Next HTF Close**: VERIFIED
- **Forward-Fill Logic is Deterministic**: VERIFIED
- **No Lookahead**: VERIFIED (explicit guard at `engine.py:951-964`)

---

## 5. Recommendations

### Immediate (Before Next Phase)

1. **Clarify TimeframeCache vs FeedStore Index Dual Path** - Document which mechanism is authoritative

### Future Phases

2. **Consolidate Warmup Documentation** - Create "Warmup Data Flow" section in architecture docs
3. **Document Staleness Properties for Strategy Authors**

---

**Audit Complete**

Auditor: Agent I (MTF Feed and Alignment Auditor)
