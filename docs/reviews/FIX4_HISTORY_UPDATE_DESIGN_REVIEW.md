# Fix 4: History Update Atomicity — Senior Developer Design Review

**Date**: 2025-12-30
**Reviewer**: Senior Developer Analysis
**Status**: Fix REJECTED — Current Design is Correct
**Severity**: Moderate (original assessment) → None (after analysis)

---

## Executive Summary

The proposed fix to make history updates atomic with snapshot builds was **correctly rejected**. The current two-phase design (build snapshot → evaluate strategy → update history) is an intentional architectural decision required for correct strategy semantics. Implementing the proposed fix would introduce subtle but critical bugs in all strategies that compare current values to historical values.

---

## 1. Original Issue Statement

### What Was Flagged

From the backtester function evaluation:

> **Issue**: History deques manual — Engine must remember to append
> **Severity**: Moderate
> **Impact**: Easy to forget update, causes stale history values

### Proposed Fix

```
- Add `update_history: bool = True` parameter to `_build_snapshot_view()`
- Move history mutations into `_build_snapshot_view()`
- Remove separate `_update_history()` calls from hot loop
```

### Rationale for Proposal

The concern was **developer ergonomics** — if someone adds a new code path in the hot loop, they might forget to call `_update_history()`, leading to stale data bugs.

---

## 2. Architectural Analysis

### Current Hot Loop Execution Order

```python
# engine.py run() — simplified for clarity
for i in range(start_idx, len(exec_feed.close)):
    bar = exec_feed.get_bar(i)  # Bar N

    # Phase 1: Build snapshot (history contains bars 0..N-1)
    snapshot = self._build_snapshot_view(i, step_result)

    # Phase 2: Strategy evaluation
    # Strategy can access:
    #   - snapshot.close         → Bar N close price
    #   - snapshot.prev_close(1) → Bar N-1 close price (from history)
    #   - snapshot.ema_fast      → EMA computed at bar N
    #   - snapshot.prev_ema_fast(1) → EMA at bar N-1 (from history)
    signal = strategy(snapshot, params)

    # Phase 3: Process signal
    if signal:
        self._process_signal(signal, bar, snapshot)

    # Phase 4: Update history (NOW append bar N)
    self._update_history(bar, features_exec, ...)

    # Next iteration: history contains bars 0..N
```

### Why This Order Matters

The key invariant is:

> **When evaluating bar N, `history[-1]` must contain bar N-1.**

This is required for any strategy logic that compares current state to previous state.

### What the Fix Would Break

If history update happens atomically with snapshot build:

```python
for i in range(start_idx, len(exec_feed.close)):
    bar = exec_feed.get_bar(i)  # Bar N

    # BROKEN: History now contains bar N before strategy runs
    snapshot = self._build_snapshot_view(i, step_result, update_history=True)

    # Strategy evaluation — WRONG semantics!
    #   - snapshot.close         → Bar N close price (correct)
    #   - snapshot.prev_close(1) → Bar N close price (WRONG! same as current)
    signal = strategy(snapshot, params)
```

---

## 3. Impact Analysis

### Affected Strategy Patterns

| Pattern | Example Code | Current Behavior | With Fix (Broken) |
|---------|--------------|------------------|-------------------|
| **Crossover** | `ema > level and prev_ema(1) < level` | Detects level cross | Never triggers (ema == prev_ema) |
| **Breakout** | `close > bars_exec_high(20)` | Detects new high | Always false (current in range) |
| **Momentum** | `rsi < 70 and prev_rsi(1) > 70` | Detects reversal | Never triggers |
| **Divergence** | `close > prev_close(1) and rsi < prev_rsi(1)` | Detects divergence | Never triggers |
| **Swing** | `low < prev_low(1) and low < prev_low(2)` | Detects swing low | Incorrect comparison |

### Specific Code Examples

**1. Golden Cross Detection**

```python
def strategy(snapshot, params):
    ema_fast = snapshot.ema_fast
    ema_slow = snapshot.ema_slow
    prev_ema_fast = snapshot.prev_ema_fast(1)
    prev_ema_slow = snapshot.prev_ema_slow(1)

    # Golden cross: fast crosses above slow
    if ema_fast > ema_slow and prev_ema_fast <= prev_ema_slow:
        return Signal(side="long", ...)
```

With atomic update: `prev_ema_fast == ema_fast`, so the crossover condition `prev_ema_fast <= prev_ema_slow` would use current values, not previous.

**2. Breakout Strategy**

```python
def strategy(snapshot, params):
    current_close = snapshot.close
    highest_20 = snapshot.bars_exec_high(20)  # Highest high in last 20 bars

    # Breakout above 20-bar high
    if current_close > highest_20:
        return Signal(side="long", ...)
```

With atomic update: The current bar's high would be included in `bars_exec_high(20)`, making the breakout detection incorrect.

**3. RSI Overbought Exit**

```python
def strategy(snapshot, params):
    rsi = snapshot.rsi
    prev_rsi = snapshot.prev_rsi(1)

    # Exit when RSI drops below 70 from overbought
    if rsi < 70 and prev_rsi > 70:
        return Signal(action="close", ...)
```

With atomic update: `prev_rsi == rsi`, so the condition `prev_rsi > 70` would never differ from `rsi < 70`.

---

## 4. Code Evidence

### Explicit Documentation in Codebase

The engine contains this comment at lines 1297-1299:

```python
# NOTE: _update_history is called AFTER strategy evaluation (at end of loop)
# to ensure crossover detection can access PREVIOUS bar's features correctly.
# See: history_features_exec[-1] should be bar N-1 when evaluating bar N.
```

This documents the intentional design decision.

### History Data Structures

```python
# engine.py __init__
self._history_bars_exec: List[CanonicalBar] = []
self._history_features_exec: List[FeatureSnapshot] = []
self._history_features_htf: List[FeatureSnapshot] = []
self._history_features_mtf: List[FeatureSnapshot] = []
```

### RuntimeSnapshotView History Access

```python
# snapshot_view.py
def prev_close(self, n: int = 1) -> Optional[float]:
    """Get close price n bars ago from history."""
    if n <= 0 or n > len(self._history_bars_exec):
        return None
    return self._history_bars_exec[-n].close

def prev_ema_fast(self, n: int = 1) -> Optional[float]:
    """Get EMA fast value n bars ago from history."""
    if n <= 0 or n > len(self._history_features_exec):
        return None
    return self._history_features_exec[-n].features.get("ema_fast")
```

---

## 5. Alternative Solutions Considered

### Option A: Atomic Update (Rejected)

**Pros:**
- Single call site, can't forget

**Cons:**
- Breaks all prev_* semantics
- Would require redesigning snapshot API
- Significant regression risk

**Verdict**: ❌ Rejected — breaks core functionality

### Option B: Context Manager Pattern

```python
with self._snapshot_context(i, step_result) as snapshot:
    signal = strategy(snapshot, params)
# __exit__ automatically calls _update_history()
```

**Pros:**
- Guarantees history update
- Clean syntax

**Cons:**
- Adds complexity
- Exception handling in __exit__ can be tricky
- Marginal benefit for established codebase

**Verdict**: ⚠️ Over-engineering for the problem

### Option C: Post-Loop Assertion (Considered)

```python
# At end of each iteration
assert len(self._history_bars_exec) == expected_length, "History not updated"
```

**Pros:**
- Catches bugs in development
- No semantic changes

**Cons:**
- Runtime overhead (though minimal)
- Only catches bugs, doesn't prevent them

**Verdict**: ✅ Viable but not implemented

### Option D: Documentation (Current)

The existing comment at line 1297 documents the design. Combined with code review practices, this is sufficient.

**Verdict**: ✅ Adequate for production codebase

---

## 6. Comparison to Industry Patterns

### TradingView Pine Script

```pine
// Pine Script semantics
ema_current = ta.ema(close, 20)
ema_previous = ema_current[1]  // Previous bar's value

// Crossover detection
if ta.crossover(ema_current, some_level)
    strategy.entry("Long", strategy.long)
```

Pine Script's `[1]` operator explicitly accesses the **previous bar's value**, not the current bar. This matches our `prev_ema_fast(1)` semantics.

### Backtrader (Python)

```python
# Backtrader semantics
class MyStrategy(bt.Strategy):
    def next(self):
        current_close = self.data.close[0]
        previous_close = self.data.close[-1]  # Previous bar

        if current_close > previous_close:
            self.buy()
```

Backtrader uses negative indexing where `[0]` is current and `[-1]` is previous. Same semantic pattern.

### QuantConnect (LEAN)

```csharp
// LEAN semantics
public override void OnData(Slice data) {
    var current = Securities["SPY"].Close;
    var history = History<TradeBar>("SPY", 2, Resolution.Daily);
    var previous = history.First().Close;

    if (current > previous) {
        SetHoldings("SPY", 1);
    }
}
```

LEAN explicitly separates current data from historical data.

### Conclusion

All major backtesting frameworks maintain the semantic distinction between "current bar" and "historical bars." Our design aligns with industry standards.

---

## 7. Risk Assessment

### If Fix Were Implemented

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Silent strategy bugs | **Certain** | **Critical** | None — fundamental semantic break |
| Incorrect backtest results | **Certain** | **Critical** | None |
| Production strategy mismatch | **Certain** | **High** | None |
| User confusion | **High** | **Medium** | Documentation |

### With Current Design

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Developer forgets history update | **Low** | **Medium** | Code review, documentation |
| New code path misses update | **Low** | **Medium** | Established patterns, tests |

---

## 8. Final Recommendation

### Decision: REJECT the fix

The current two-phase design is **correct and intentional**. The proposed fix would introduce critical semantic bugs affecting all strategies that use historical comparisons.

### Rationale

1. **Semantic Correctness**: The current design correctly implements the standard backtesting pattern where `prev_*(n)` returns the value from n bars ago, not the current bar.

2. **Industry Alignment**: This pattern matches TradingView, Backtrader, QuantConnect, and other major platforms.

3. **Explicit Documentation**: The design is documented in code comments.

4. **Low Risk**: The "forgot to update" risk is mitigated by:
   - Established code patterns
   - Code review processes
   - The hot loop is well-defined and rarely modified

5. **High Regression Risk**: Changing this would require auditing and potentially rewriting all strategies.

### Action Items

- [x] Document decision in code review
- [x] Update TODO document to mark as "SKIPPED — Design is correct"
- [ ] Consider adding assertion in debug mode (future enhancement)

---

## 9. Appendix: Test Case for Verification

If someone wants to verify the current behavior is correct:

```python
def test_history_timing():
    """Verify prev_* returns previous bar, not current."""
    # Setup: bars with known values
    # Bar 0: close=100, ema=100
    # Bar 1: close=110, ema=105
    # Bar 2: close=120, ema=112

    # When evaluating bar 2:
    snapshot = engine._build_snapshot_view(2, step_result)

    # Current values
    assert snapshot.close == 120
    assert snapshot.ema_fast == 112

    # Previous values (should be bar 1, not bar 2)
    assert snapshot.prev_close(1) == 110  # NOT 120
    assert snapshot.prev_ema_fast(1) == 105  # NOT 112

    # Two bars ago (should be bar 0)
    assert snapshot.prev_close(2) == 100
    assert snapshot.prev_ema_fast(2) == 100
```

---

## 10. Document History

| Date | Author | Change |
|------|--------|--------|
| 2025-12-30 | Claude Code | Initial review and rejection decision |

---

*This review documents why Fix 4 from BACKTESTER_FIXES_PHASE1.md was intentionally skipped. The current implementation is correct.*
