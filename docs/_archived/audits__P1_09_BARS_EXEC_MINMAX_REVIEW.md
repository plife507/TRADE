# P1-09: O(n) Operations in `bars_exec_high/low` - Technical Review

**Reviewer**: Senior Python Developer Perspective
**File**: `src/backtest/runtime/snapshot_view.py` (lines 379-403)
**Severity**: P1 (High-Risk) - Performance in hot loop
**Date**: 2026-01-01
**Status**: ARCHIVED - FIXED by Incremental State Architecture (2026-01-03)

---

## 1. Current Implementation

```python
def bars_exec_low(self, n: int) -> Optional[float]:
    """Get lowest low of last n exec bars (for structure SL)."""
    if n < 1:
        raise ValueError("n must be >= 1")

    start_idx = max(0, self.exec_idx - n + 1)
    end_idx = self.exec_idx + 1

    if start_idx >= end_idx:
        return None

    return float(np.min(self._feeds.exec_feed.low[start_idx:end_idx]))

def bars_exec_high(self, n: int) -> Optional[float]:
    """Get highest high of last n exec bars (for structure SL)."""
    if n < 1:
        raise ValueError("n must be >= 1")

    start_idx = max(0, self.exec_idx - n + 1)
    end_idx = self.exec_idx + 1

    if start_idx >= end_idx:
        return None

    return float(np.max(self._feeds.exec_feed.high[start_idx:end_idx]))
```

---

## 2. Problem Analysis

### 2.1 Time Complexity

| Operation | Complexity | Notes |
|-----------|------------|-------|
| Slice creation `low[start:end]` | O(1) | NumPy views are cheap |
| `np.min()` / `np.max()` | **O(n)** | Must scan all elements |
| Total per call | **O(n)** | Where n = window size |

### 2.2 Hot Loop Impact

If called in the backtest hot loop with a fixed window (e.g., `n=20`):

```
Bars: 100,000
Calls per bar: 2 (high + low)
Window size: 20
Total operations: 100,000 x 2 x 20 = 4,000,000 comparisons
```

For larger windows (`n=200` for daily structure):
```
Total operations: 100,000 x 2 x 200 = 40,000,000 comparisons
```

### 2.3 Current Mitigating Factors

1. **Not currently used**: Grep shows no callers in the codebase
2. **NumPy is fast**: C-level loop, not Python iteration
3. **Cache-friendly**: Contiguous memory access

---

## 3. Why This Is Still a P1

### 3.1 Future Risk
These methods are clearly designed for stop-loss placement (`"for structure SL"` in docstring). Once strategies start using them, performance degrades.

### 3.2 Incorrect Mental Model
The `RuntimeSnapshotView` is documented as providing **O(1) access**. These methods violate that contract.

### 3.3 Accumulating Window Problem
If a strategy uses multiple window sizes:
```python
swing_low_5 = snapshot.bars_exec_low(5)
swing_low_20 = snapshot.bars_exec_low(20)
swing_low_50 = snapshot.bars_exec_low(50)
```
Each call rescans overlapping data.

---

## 4. Solution Options

### Option A: Rolling Min/Max (Precomputed)

**Approach**: Precompute rolling min/max during data preparation.

```python
# In FeedStore or data prep:
rolling_high_20 = pd.Series(high).rolling(20).max().values
rolling_low_20 = pd.Series(low).rolling(20).min().values
```

**Pros**:
- O(1) access in hot loop
- Simple implementation

**Cons**:
- Fixed window size (must precompute each needed window)
- Memory overhead: 8 bytes x bars x windows

**Best for**: Known, fixed window sizes (e.g., 20-bar structure SL)

---

### Option B: Monotonic Deque (Sliding Window)

**Approach**: Maintain a deque tracking the min/max as the window slides.

```python
from collections import deque

class SlidingMinMax:
    def __init__(self, window: int):
        self.window = window
        self.min_deque = deque()  # (index, value)
        self.max_deque = deque()

    def push(self, idx: int, value: float):
        # Remove elements outside window
        while self.min_deque and self.min_deque[0][0] <= idx - self.window:
            self.min_deque.popleft()
        while self.max_deque and self.max_deque[0][0] <= idx - self.window:
            self.max_deque.popleft()

        # Maintain monotonicity
        while self.min_deque and self.min_deque[-1][1] >= value:
            self.min_deque.pop()
        while self.max_deque and self.max_deque[-1][1] <= value:
            self.max_deque.pop()

        self.min_deque.append((idx, value))
        self.max_deque.append((idx, value))

    def get_min(self) -> float:
        return self.min_deque[0][1]

    def get_max(self) -> float:
        return self.max_deque[0][1]
```

**Complexity**: Amortized O(1) per bar

**Pros**:
- True O(1) per-bar access
- Memory efficient: O(window) not O(bars)

**Cons**:
- More complex implementation
- Must be updated every bar (stateful)
- Requires integration into engine loop

**Best for**: Single window size with strict O(1) requirement

---

### Option C: Segment Tree (Multiple Windows)

**Approach**: Build a segment tree for range min/max queries.

```python
class SegmentTree:
    def __init__(self, arr: np.ndarray, op=min):
        self.n = len(arr)
        self.op = op
        self.tree = [0] * (2 * self.n)
        # Build tree
        for i in range(self.n):
            self.tree[self.n + i] = arr[i]
        for i in range(self.n - 1, 0, -1):
            self.tree[i] = self.op(self.tree[2*i], self.tree[2*i+1])

    def query(self, left: int, right: int):
        """Range query [left, right)"""
        result = float('inf') if self.op == min else float('-inf')
        left += self.n
        right += self.n
        while left < right:
            if left & 1:
                result = self.op(result, self.tree[left])
                left += 1
            if right & 1:
                right -= 1
                result = self.op(result, self.tree[right])
            left //= 2
            right //= 2
        return result
```

**Complexity**: O(log n) per query, O(n) build

**Pros**:
- Supports arbitrary window sizes
- Single data structure for all queries

**Cons**:
- O(log n) not O(1)
- Memory: 2x array size
- Complex implementation

**Best for**: Variable window sizes with many queries

---

### Option D: Hybrid (Recommended)

**Approach**: Precompute common windows, fall back to segment tree for others.

```python
class OptimizedMinMax:
    PRECOMPUTED_WINDOWS = [5, 10, 20, 50, 100, 200]

    def __init__(self, high: np.ndarray, low: np.ndarray):
        # Precompute common windows
        self.rolling_high = {}
        self.rolling_low = {}
        for w in self.PRECOMPUTED_WINDOWS:
            self.rolling_high[w] = self._rolling_max(high, w)
            self.rolling_low[w] = self._rolling_min(low, w)

        # Segment trees for arbitrary queries
        self.seg_high = SegmentTree(high, max)
        self.seg_low = SegmentTree(low, min)

    def get_high(self, idx: int, window: int) -> float:
        if window in self.rolling_high:
            return self.rolling_high[window][idx]  # O(1)
        return self.seg_high.query(max(0, idx-window+1), idx+1)  # O(log n)

    def get_low(self, idx: int, window: int) -> float:
        if window in self.rolling_low:
            return self.rolling_low[window][idx]  # O(1)
        return self.seg_low.query(max(0, idx-window+1), idx+1)  # O(log n)
```

---

## 5. Recommendation

### Short-Term (Minimal Change)
**Do nothing** - methods are unused. Document the O(n) behavior.

```python
def bars_exec_low(self, n: int) -> Optional[float]:
    """
    Get lowest low of last n exec bars.

    WARNING: O(n) complexity. For hot-loop usage with fixed windows,
    consider precomputing rolling min in FeedStore.
    """
```

### Medium-Term (When Used)
**Option A** - Precompute rolling min/max for known windows during data prep.

Add to `FeedStore`:
```python
rolling_low_20: Optional[np.ndarray] = None
rolling_high_20: Optional[np.ndarray] = None
```

Update `bars_exec_low()`:
```python
def bars_exec_low(self, n: int) -> Optional[float]:
    # Fast path for precomputed window
    if n == 20 and self._feeds.exec_feed.rolling_low_20 is not None:
        return float(self._feeds.exec_feed.rolling_low_20[self.exec_idx])

    # Fallback to O(n) scan
    ...
```

### Long-Term (If Variable Windows Needed)
**Option D** - Hybrid with segment tree fallback.

---

## 6. Impact Assessment

| Factor | Current | After Fix |
|--------|---------|-----------|
| Complexity | O(n) | O(1) or O(log n) |
| Memory | 0 | +8 bytes x bars x windows |
| Code Complexity | Simple | Medium |
| Breaking Change | No | No (same API) |

---

## 7. Summary

| Aspect | Assessment |
|--------|------------|
| **Severity** | P1 - Correct but violates O(1) contract |
| **Urgency** | Low - Not currently used |
| **Fix Effort** | Low (Option A) to Medium (Option D) |
| **Recommendation** | Document now, fix when first used |

The issue is real but **not urgent**. The methods exist for future use (structure-based stop-loss). When a strategy needs them, implement **Option A** (precomputed rolling windows) for the specific window sizes used.

---

## References

- **Location**: `src/backtest/runtime/snapshot_view.py:379-403`
- **Risk Register**: `docs/audits/2026-01-01/RISK_REGISTER.md` (P1-09)
- **Related**: FeedStore at `src/backtest/runtime/feed_store.py`
