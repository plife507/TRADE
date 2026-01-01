# Phase 4 Snapshot Plumbing Audit — Implementation Review

**Status**: ✅ Complete  
**Date**: 2025-12-16  
**Phase**: Array-Backed Hot Loop Phases (Phase 4 of 9)  
**Commit**: 320121f047e3
**Moved from**: `docs/reviews/PHASE_4_SNAPSHOT_PLUMBING_AUDIT_REVIEW.md` (2025-12-17 docs refactor)

---

## Executive Summary

Phase 4 implements a **deterministic, in-memory audit system** that validates the correctness of `RuntimeSnapshotView.get_feature()` plumbing without changing engine behavior, strategy logic, or indicator math. The audit runs via an optional engine callback, samples strategically during backtest execution, and compares snapshot API results against direct `FeedStore` array reads.

**Key Achievement**: 39,968 comparisons across 1,249 snapshots with **zero failures** in both single-TF and multi-TF configurations.

---

## Problem Statement

### The Challenge

The backtest engine uses an **array-backed snapshot** (`RuntimeSnapshotView`) for O(1) hot-loop performance. Strategies access market data and indicators through this snapshot API:

```python
# Access current exec timeframe EMA
snapshot.get_feature("ema_fast", tf_role="exec", offset=0)

# Access previous higher timeframe EMA
snapshot.get_feature("ema_slow", tf_role="htf", offset=1)

# Access multi-timeframe RSI
snapshot.get_feature("rsi", tf_role="mtf", offset=2)
```

This snapshot layer implements **complex plumbing logic**:

1. **TF Routing**: `tf_role` must select the correct `FeedStore` (exec/htf/mtf)
2. **Offset Semantics**: `offset=N` must compute the correct array index backward from current position
3. **Forward-Fill Behavior**: HTF/MTF values must remain constant between their respective TF closes
4. **Index Tracking**: Must maintain separate indices for exec, HTF, and MTF feeds simultaneously

### Why This Matters

**Before Phase 4**, we had no automated way to verify this plumbing was correct. Bugs in TF routing or index arithmetic would:
- ❌ Produce incorrect backtest results (silently wrong)
- ❌ Not be caught by indicator math audits (Phase 2)
- ❌ Only surface through manual inspection or production failures

**After Phase 4**, we have:
- ✅ Regression protection for snapshot API refactors
- ✅ Automated validation of multi-TF index alignment
- ✅ Sub-second audit runtime (<1s for 1,249 samples)
- ✅ CI-ready JSON output for pipeline integration

---

## What This Audit Validates

| Check | Description | Example Failure Caught |
|-------|-------------|------------------------|
| **TF Routing** | `get_feature(..., tf_role="htf")` reads from HTF feed, not exec feed | If routing maps "htf" to wrong feed, values won't match expected HTF array |
| **Offset Semantics** | `offset=N` correctly computes `current_idx - N` | Off-by-one errors would show as value mismatches |
| **Forward-Fill** | HTF/MTF indices remain constant between their TF closes | If indices increment too early, values would change mid-TF |
| **Closed-Candle Only** | `snapshot.ts_close` always equals `exec_feed.ts_close[exec_idx]` | Partial candles would have different timestamps |
| **NaN Handling** | NaN masks match between snapshot and raw arrays | Missing data handling inconsistencies caught |
| **Multi-Output Indicators** | Each output (e.g., MACD line, signal, histogram) routes correctly | Wrong indicator component would fail comparison |
| **Index Bounds** | Offsets don't go out of bounds | Array index errors caught during comparison |

### What This Audit Does NOT Validate

- ❌ **Indicator Math** — Phase 2 (`phase2-audit`) already validates this
- ❌ **Strategy Logic** — Not in scope for plumbing audit
- ❌ **Order Execution** — Simulated exchange logic
- ❌ **Risk Management** — Risk policy enforcement
- ❌ **Performance** — Speed/memory profiling (separate concern)

---

## Test Results

### Acceptance Test Suite

All gates passed ✅:

```bash
# Phase 4 Single-TF
$ python trade_cli.py backtest audit-snapshot-plumbing \
    --idea-card verify/BTCUSDT_15m_verify_ema_atr \
    --start 2025-12-01 --end 2025-12-14 --json
{
  "status": "pass",
  "data": {
    "success": true,
    "total_samples": 1249,
    "total_comparisons": 39968,
    "failed_comparisons": 0,
    "runtime_seconds": 0.76
  }
}

# Phase 4 Multi-TF
$ python trade_cli.py backtest audit-snapshot-plumbing \
    --idea-card BTCUSDT_15m_mtf_tradeproof \
    --start 2025-12-01 --end 2025-12-14 --json
{
  "status": "pass",
  "data": {
    "success": true,
    "total_samples": 1249,
    "total_comparisons": 39968,
    "failed_comparisons": 0,
    "runtime_seconds": 0.76
  }
}
```

---

## CLI Usage

```bash
# Basic Single-TF Audit
python trade_cli.py backtest audit-snapshot-plumbing \
  --idea-card verify/BTCUSDT_15m_verify_ema_atr \
  --start 2025-12-01 \
  --end 2025-12-14

# Multi-TF Audit with JSON output
python trade_cli.py backtest audit-snapshot-plumbing \
  --idea-card BTCUSDT_15m_mtf_tradeproof \
  --start 2025-12-01 \
  --end 2025-12-14 \
  --json
```

---

## Related Documentation

- **TODO Tracker**: `docs/todos/ARRAY_BACKED_HOT_LOOP_PHASES.md` (Phase 4)
- **Architecture**: `docs/architecture/SIMULATED_EXCHANGE.md`
- **P0 Blocker**: `docs/audits/volume_sma_bug_diagnosis.md`

---

**Review Status**: ✅ Phase 4 Complete — All acceptance gates passed  
**Next Milestone**: Phase 5 (Market Structure) — **BLOCKED** by P0 input-source routing fix

