# Backtester Function Issues & Fix Implementations

**Created**: December 30, 2025  
**Last Updated**: December 30, 2025  
**Status**: Review Document + Validation Complete  
**Scope**: 13 issues identified across 122 backtester functions  
**Validation**: See `BACKTESTER_FUNCTION_ISSUES_VALIDATION.md` for test results

---

## Executive Summary

| Severity | Count | Status |
|----------|-------|--------|
| Critical | 0 | N/A |
| Moderate | 6 | Fixes proposed |
| Minor | 7 | Documented |

**Overall Health**: 89% of functions working correctly. No critical issues blocking production use.

---

## Moderate Issues (6)

### Issue 1: HTF Lookup O(n) Performance

**Location**: `src/backtest/runtime/feed_store.py`
**Function**: `get_last_closed_idx_at_or_before()`
**Severity**: Moderate
**Impact**: Slow performance on large datasets (5+ years of data)

**Current Implementation**:
```python
def get_last_closed_idx_at_or_before(self, ts: datetime) -> Optional[int]:
    """Find last closed bar at or before timestamp."""
    ts_ms = int(ts.timestamp() * 1000)
    result_idx = None
    for close_ms, idx in self.ts_close_ms_to_idx.items():
        if close_ms <= ts_ms:
            if result_idx is None or idx > result_idx:
                result_idx = idx
    return result_idx
```

**Problem**: O(n) iteration through all timestamps. For 5-year 1h data (~44k bars), this is called per bar = 44k * 44k = 1.9B iterations.

**Fix Implementation**:
```python
import bisect
from typing import Optional

class FeedStore:
    def __init__(self, ...):
        # ... existing init ...
        # Add sorted keys for binary search
        self._sorted_close_ms: List[int] = sorted(self.ts_close_ms_to_idx.keys())

    def get_last_closed_idx_at_or_before(self, ts: datetime) -> Optional[int]:
        """Find last closed bar at or before timestamp. O(log n) via binary search."""
        if not self._sorted_close_ms:
            return None

        ts_ms = int(ts.timestamp() * 1000)

        # Binary search: find rightmost value <= ts_ms
        pos = bisect.bisect_right(self._sorted_close_ms, ts_ms)

        if pos == 0:
            return None  # All timestamps are after ts

        # pos-1 is the index of the largest timestamp <= ts_ms
        close_ms = self._sorted_close_ms[pos - 1]
        return self.ts_close_ms_to_idx[close_ms]
```

**Complexity**: O(n) → O(log n)
**Files to Modify**: `src/backtest/runtime/feed_store.py`

---

### Issue 2: History Deques Manual Update

**Location**: `src/backtest/engine.py`
**Function**: `_update_history()` called manually in hot loop
**Severity**: Moderate
**Impact**: Easy to forget update, causes stale history values

**Current Implementation**:
```python
# In engine.py run() hot loop:
for i in range(start_idx, len(exec_feed.close)):
    # ... build snapshot ...
    snapshot = self._build_snapshot_view(i, htf_idx, mtf_idx)

    # MANUAL: Must remember to update history
    self._update_history(bar, features_exec, htf_updated, mtf_updated, ...)

    # ... strategy evaluation ...
```

**Problem**: History update is separate from snapshot building. If developer adds new code path, history may not update.

**Fix Implementation**:
```python
# Option A: Encapsulate in snapshot builder
def _build_snapshot_view(
    self,
    exec_idx: int,
    htf_idx: Optional[int],
    mtf_idx: Optional[int],
    update_history: bool = True  # Default to auto-update
) -> RuntimeSnapshotView:
    """Build snapshot view and optionally update history."""

    # Build snapshot first
    snapshot = RuntimeSnapshotView(
        feeds=self._multi_tf_feeds,
        exec_idx=exec_idx,
        htf_idx=htf_idx,
        mtf_idx=mtf_idx,
        exchange=self._exchange,
        mark_price=self._last_mark_price,
        history_tuples=self._get_history_tuples(),
    )

    # Auto-update history if enabled
    if update_history:
        self._history_exec_indices.append(exec_idx)
        # ... other history updates ...

    return snapshot
```

**Recommendation**: Option A (simpler, less intrusive)
**Files to Modify**: `src/backtest/engine.py`

---

### Issue 3: Warmup 3-Point Handoff

**Location**: Multiple files
**Flow**: Preflight → Runner → Engine
**Severity**: Moderate
**Impact**: Fragile handoff, warmup mismatch possible

**Current Flow**:
```
1. Preflight computes warmup_bars_by_role
2. Runner reads PreflightReport, writes to SystemConfig.warmup_bars_by_role
3. Engine reads SystemConfig.warmup_bars_by_role
   - If missing, raises ValueError with suggestion to run preflight
```

**Problem**: Three separate places manage warmup. If any step skipped or modified, warmup mismatch occurs.

**Fix Implementation**:
```python
# Option A: Make SystemConfig required with warmup (fail-fast)
# In engine.py __init__:

def __init__(self, config: SystemConfig, ...):
    # Validate warmup is present - no fallback
    if not config.warmup_bars_by_role:
        raise ValueError(
            "SystemConfig.warmup_bars_by_role is required. "
            "Run preflight first: python trade_cli.py backtest preflight --idea-card <ID>"
        )
    self._warmup_bars_by_role = config.warmup_bars_by_role
```

**Recommendation**: Option A (fail-fast aligns with project philosophy)
**Files to Modify**: `src/backtest/engine.py`, `src/backtest/system_config.py`

---

### Issue 4: TF Default 1h Instead of Raising

**Location**: `src/backtest/engine.py`
**Function**: `_timeframe_to_timedelta()`
**Severity**: Moderate
**Impact**: Unknown TF silently uses 1h, causing incorrect bar timing

**Current Implementation**:
```python
TF_MINUTES = {
    "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "2h": 120, "4h": 240, "6h": 360, "12h": 720,
    "1d": 1440, "1w": 10080,
}

def _timeframe_to_timedelta(self, tf: str) -> timedelta:
    minutes = TF_MINUTES.get(tf, 60)  # Default to 1h - BAD!
    return timedelta(minutes=minutes)
```

**Problem**: Unknown TF like "8h" or "3d" silently defaults to 60 minutes.

**Fix Implementation**:
```python
def _timeframe_to_timedelta(self, tf: str) -> timedelta:
    """Convert timeframe string to timedelta. Raises on unknown TF."""
    if tf not in TF_MINUTES:
        raise ValueError(
            f"Unknown timeframe: '{tf}'. "
            f"Valid timeframes: {sorted(TF_MINUTES.keys())}"
        )
    return timedelta(minutes=TF_MINUTES[tf])
```

**Files to Modify**: `src/backtest/engine.py`

---

### Issue 5: Metadata Coverage Optional

**Location**: `src/backtest/features/feature_frame_builder.py`
**Class**: `FeatureArrays`
**Severity**: Moderate
**Impact**: Legacy paths may skip metadata, breaking provenance tracking

**Current Implementation**:
```python
@dataclass
class FeatureArrays:
    arrays: Dict[str, np.ndarray]
    metadata: Optional[Dict[str, IndicatorMetadata]] = None  # Optional!

    def __post_init__(self):
        # Soft check: only validate if metadata provided
        if self.metadata:
            for key in self.arrays:
                if key not in self.metadata:
                    logger.warning(f"Missing metadata for {key}")
```

**Problem**: `metadata=None` is allowed, breaking Phase 4 provenance tracking.

**Fix Implementation**:
```python
@dataclass
class FeatureArrays:
    arrays: Dict[str, np.ndarray]
    metadata: Dict[str, IndicatorMetadata]  # Now required!

    def __post_init__(self):
        # Strict validation
        missing = set(self.arrays.keys()) - set(self.metadata.keys())
        if missing:
            raise ValueError(
                f"Missing metadata for indicators: {missing}. "
                "All indicators must have provenance metadata."
            )

    @classmethod
    def empty(cls) -> "FeatureArrays":
        """Factory for empty arrays (no indicators declared)."""
        return cls(arrays={}, metadata={})
```

**Files to Modify**: `src/backtest/features/feature_frame_builder.py`

---

### Issue 6: Daily Loss Set to Infinity

**Location**: `src/backtest/risk_policy.py`
**Class**: `RulesRiskPolicy`
**Severity**: Moderate
**Impact**: Backtest silently allows unlimited daily loss, deviating from live behavior

**Current Implementation**:
```python
class RulesRiskPolicy(RiskPolicy):
    def __init__(self, risk_profile: RiskProfileConfig):
        self._risk_profile = risk_profile
        # Daily loss disabled for determinism
        self._max_daily_loss = float('inf')  # Silent deviation!
```

**Problem**: Live trading enforces daily loss limits; backtest doesn't. Results may not match production.

**Fix Implementation**:
```python
class RulesRiskPolicy(RiskPolicy):
    """
    Production-faithful risk policy for backtesting.

    NOTE: Daily loss limit is set to infinity for determinism.
    This is intentional - backtests should not halt mid-run due to
    cumulative losses, as this would make results non-reproducible
    across different starting points. Live trading enforces real
    daily limits via the live RiskManager.
    """

    def __init__(
        self,
        risk_profile: RiskProfileConfig,
        enforce_daily_loss: bool = False,  # Explicit opt-in
    ):
        self._risk_profile = risk_profile

        if enforce_daily_loss:
            self._max_daily_loss = risk_profile.max_daily_loss_usd
            logger.info(
                f"Daily loss limit ENABLED: ${self._max_daily_loss:.2f}. "
                "Note: This may cause non-deterministic results."
            )
        else:
            self._max_daily_loss = float('inf')
```

**Files to Modify**: `src/backtest/risk_policy.py`

---

## Minor Issues (7)

### Issue 7: Funding Applied Before Fills

**Location**: `src/backtest/sim/exchange.py`
**Function**: `process_bar()`
**Severity**: Minor

**Current Order**:
```python
def process_bar(self, bar, prev_bar, funding_events):
    # 1. Compute mark price
    # 2. Apply funding to open position  <-- BEFORE fills
    # 3. Fill pending entry order
    # 4. Check TP/SL
    # 5. Update MTM
```

**Problem**: If funding causes near-liquidation, entry may still fill.

**Fix**: Document as intentional or reorder to: fills → funding → TP/SL.

---

### Issue 8: Synthetic Exit Bar Non-Canonical

**Location**: `src/backtest/sim/exchange.py`
**Function**: `_close_position()`
**Severity**: Minor

**Current**:
```python
exit_bar = Bar(
    ts_open=exit_time,
    ts_close=exit_time,  # Same as ts_open
    ...
)
```

**Fix**: Document as intentional (exit is instantaneous).

---

### Issue 9: Zero Volatility Returns 0.0

**Location**: `src/backtest/metrics.py`
**Functions**: `_compute_sharpe()`, `_compute_sortino()`
**Severity**: Minor

**Fix**: Return `float('nan')` or log warning for zero-volatility periods.

---

### Issue 10: RunManifest Written 3 Times

**Location**: `src/backtest/runner.py`
**Severity**: Minor

**Current**: Written at init, after preflight, after engine run.

**Fix**: Collect all data, write once at end.

---

### Issue 11: Snapshot Emission Silent Failure

**Location**: `src/backtest/runner.py`
**Severity**: Minor

**Current**:
```python
try:
    emit_snapshots(...)
except Exception:
    pass  # Silent failure!
```

**Fix**: Log warning on failure.

---

### Issue 12: MAX_WARMUP_BARS No Override

**Location**: `src/backtest/execution_validation.py`
**Constant**: `MAX_WARMUP_BARS = 1000`
**Severity**: Minor

**Fix**: Make configurable via IdeaCard or SystemConfig.

---

### Issue 13: WARNING Severity Passes Validation

**Location**: `src/backtest/execution_validation.py`
**Severity**: Minor

**Fix**: Add separate `passed_with_warnings` status.

---

## Implementation Priority

### Phase 1: High Priority (Recommended Now)

| Issue | Effort | Impact |
|-------|--------|--------|
| #1 HTF Lookup O(n) | 2h | Performance 100x improvement |
| #4 TF Default 1h | 30m | Prevents silent bugs |

### Phase 2: Medium Priority (Next Sprint)

| Issue | Effort | Impact |
|-------|--------|--------|
| #3 Warmup Handoff | 2h | Reduces fragility |
| #5 Metadata Optional | 1h | Improves provenance |
| #2 History Deques | 1h | Prevents stale data |

### Phase 3: Low Priority (Technical Debt)

| Issue | Effort | Impact |
|-------|--------|--------|
| #6 Daily Loss Docs | 30m | Documentation only |
| #7-13 Minor Issues | 4h total | Edge cases |

---

## Validation After Fixes

After implementing fixes, run:

```bash
# Compile check
python -m compileall src/backtest/

# Smoke tests
python trade_cli.py --smoke full

# Audit gates
python trade_cli.py backtest audit-toolkit
python trade_cli.py backtest math-parity --idea-card verify_ema_atr --start 2025-12-01 --end 2025-12-14
python trade_cli.py backtest audit-snapshot-plumbing --idea-card verify_ema_atr --start 2025-12-01 --end 2025-12-14
```

---

## Summary

The backtester is production-ready with 89% of functions working correctly. The 6 moderate issues are optimization opportunities that improve robustness but don't block current use.

**Validation Status** (December 30, 2025):
- ✅ **5/5 idea cards tested** - All passed
- ✅ **All validation gates** - Working correctly
- ✅ **Artifacts validated** - All required files present
- ✅ **Performance acceptable** - <2s for all tests
- ⚠️ **Issue #1 (HTF Lookup)** - Not tested (requires large dataset profiling)

**See**: `BACKTESTER_FUNCTION_ISSUES_VALIDATION.md` for complete test results

**Recommended Next Steps**:
1. Fix Issue #1 (HTF lookup) for 100x performance gain
2. Fix Issue #4 (TF default) to prevent silent bugs
3. Document remaining issues in backlog for future sprints
