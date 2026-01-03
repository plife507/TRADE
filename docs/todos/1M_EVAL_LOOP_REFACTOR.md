# 1m Evaluation Loop Refactor

> **Status**: Spec Complete | **Priority**: High
> **Goal**: Mandatory 1m signal evaluation for zone-touch detection
> **Scope**: Simulation only (live prep, no live implementation)

---

## Executive Summary

Refactor the backtest engine to evaluate signals at 1m granularity. This enables zone-touch detection within exec bars and prepares the architecture for future live trading parity.

**Key Findings** (from codebase investigation):
- **80% of infrastructure exists** - FeedStore, QuoteState, ExecRollupBucket ready
- **mark_price already exists** as RuntimeSnapshotView attribute
- **Compiled refs already support** `price.mark.close` resolution
- **Main changes**: Engine loop + TP/SL at 1m granularity

---

## Architecture Overview

```
CURRENT (exec-close only):           TARGET (1m evaluation):

for exec_bar in exec_bars:           for exec_bar in exec_bars:
    process_bar()                        for 1m_bar in 1m_bars:      # NEW
    signal = strategy(snapshot)              update mark_price
    if signal: submit()                      signal = strategy()
                                             if signal: submit; break
                                        process_bar()  # TP/SL at 1m
```

---

## Phase 1: 1m Index Mapping

**Scope**: Map exec bar indices to 1m bar indices

### 1.1 Add Index Helper

**File**: `src/backtest/runtime/feed_store.py`

```python
def get_1m_indices_for_exec(self, exec_idx: int, exec_tf: str) -> tuple[int, int]:
    """Return (start_1m_idx, end_1m_idx) for an exec bar.

    Example: exec_tf="5m", exec_idx=10 → (50, 54)
    """
    ratio = _tf_to_minutes(exec_tf)
    start = exec_idx * ratio
    end = start + ratio - 1
    return (start, end)
```

**Existing code to reuse**:
- `engine_feed_builder.py:539-587` - 1m feed loading
- `runtime/rollup_bucket.py` - ExecRollupBucket (already accumulates 1m)

### Checklist
- [ ] Add `get_1m_indices_for_exec()` to FeedStore
- [ ] Add TF ratio utility if not exists

---

## Phase 2: Snapshot mark_price Resolution

**Scope**: Expose mark_price in get_feature()

### 2.1 Update get_feature()

**File**: `src/backtest/runtime/snapshot_view.py:493-583`

**Current**: mark_price exists as attribute but not accessible via get_feature()

**Change**:
```python
def get_feature(self, key: str, tf_role: str = "exec", offset: int = 0):
    # ADD: Handle mark_price specially
    if key == "mark_price":
        if offset == 0:
            return self.mark_price
        # Historical: access 1m feed (future enhancement)
        raise ValueError("mark_price offset not yet supported")

    # ... existing code unchanged
```

**Existing code to reuse**:
- `snapshot_view.py:796-843` - `_resolve_price_path()` already handles `price.mark.close`
- Compiled refs path already works (agent 5 confirmed)

### Checklist
- [ ] Add mark_price case to get_feature()
- [ ] Verify price.mark.close → mark_price resolution works

---

## Phase 3: Engine 1m Sub-Loop

**Scope**: Add 1m evaluation loop inside main exec loop

### 3.1 Main Loop Changes

**File**: `src/backtest/engine.py:752-1034`

**Current flow** (lines referenced from agent investigation):
```python
# Line 752: for i in range(num_bars):
# Line 789:     process_bar(bar, prev_bar)  # fills + TP/SL
# Line 928:     snapshot = build_snapshot()
# Line 984:     signal = strategy(snapshot)
# Line 1001:    _process_signal(signal, bar, snapshot)
```

**New flow**:
```python
for i in range(num_bars):
    bar = get_exec_bar(i)

    # ========== 1m SUB-LOOP ==========
    if i >= sim_start_idx:
        signal_triggered = False
        start_1m, end_1m = feed.get_1m_indices_for_exec(i, exec_tf)

        for sub_idx in range(start_1m, end_1m + 1):
            if signal_triggered:
                break

            # Update snapshot with 1m mark price
            mark_price = quote_feed.close[sub_idx]
            snapshot = _build_snapshot_with_mark(exec_idx=i, mark_price=mark_price)

            # Evaluate
            signal = strategy(snapshot, self.config.params)

            if signal is not None:
                _process_signal_1m(signal, sub_idx, snapshot)
                signal_triggered = True
    # ========== END 1m SUB-LOOP ==========

    # Process bar (fills, TP/SL) - timing changes in Phase 4
    process_bar(bar, prev_bar)

    prev_bar = bar
```

### 3.2 Signal Processing at 1m

**File**: `src/backtest/engine.py:1340-1410`

```python
def _process_signal_1m(self, signal: Signal, eval_idx: int, snapshot):
    """Submit order at 1m close timestamp."""
    ts_close = self._quote_feed.get_ts_close_datetime(eval_idx)

    self._exchange.submit_order(
        side=side,
        size_usdt=size_usdt,
        stop_loss=stop_loss,
        take_profit=take_profit,
        timestamp=ts_close,  # 1m close, not exec close
    )
```

### Checklist
- [ ] Add 1m sub-loop after line 752
- [ ] Add `_build_snapshot_with_mark()` method
- [ ] Add `_process_signal_1m()` method
- [ ] Implement one-entry-per-exec-bar limit

---

## Phase 4: Exchange 1m Fill Timing

**Scope**: Fill orders and check TP/SL at 1m granularity

### 4.1 Entry Fill at 1m

**File**: `src/backtest/sim/execution/execution_model.py:99-108`

**Current**:
```python
fill_ts = get_bar_ts_open(bar)  # exec bar open
fill_price = bar.open + slippage
```

**Change**: Accept 1m bar for fill timing
```python
def fill_entry_order(self, order, bar_1m, ...):
    fill_ts = get_bar_ts_open(bar_1m)  # 1m bar open
    fill_price = bar_1m.open + slippage
```

### 4.2 TP/SL at 1m Granularity

**File**: `src/backtest/sim/pricing/intrabar_path.py:133-185`

**Current**: Checks TP/SL using exec bar OHLC only

**Change**: Iterate 1m bars instead of intrabar path
```python
def check_tp_sl_1m(position, 1m_bars: list[Bar]) -> tuple[FillReason, int, float] | None:
    """Check TP/SL against each 1m bar in order.

    Returns: (reason, hit_1m_idx, hit_price) or None
    """
    for idx, bar in enumerate(1m_bars):
        if position.side == "LONG":
            if bar.low <= position.stop_loss:
                return (FillReason.STOP_LOSS, idx, position.stop_loss)
            if bar.high >= position.take_profit:
                return (FillReason.TAKE_PROFIT, idx, position.take_profit)
        # ... SHORT side
    return None
```

### 4.3 Exchange process_bar Changes

**File**: `src/backtest/sim/exchange.py:311-417`

**Change**: Add quote_feed parameter, use 1m for TP/SL
```python
def process_bar(self, bar, prev_bar, quote_feed=None, exec_1m_range=None):
    if quote_feed is not None and exec_1m_range is not None:
        # Use 1m granularity for TP/SL
        start_1m, end_1m = exec_1m_range
        result = check_tp_sl_1m(self.position, quote_feed[start_1m:end_1m+1])
        if result:
            reason, hit_idx, price = result
            hit_ts = quote_feed.get_ts_open(hit_idx)
            self._close_position(price, hit_ts, reason.value)
    else:
        # Fallback to current behavior
        ...
```

### Checklist
- [ ] Update execution_model.py to accept 1m bar
- [ ] Add check_tp_sl_1m() function
- [ ] Add quote_feed parameter to process_bar()
- [ ] Update engine.py to pass 1m range to exchange

---

## Phase 5: Data Loading

**Scope**: Ensure 1m data always loaded for backtests

### 5.1 Mandatory 1m Feed

**File**: `src/backtest/engine_data_prep.py`

**Current**: 1m data loaded for quote feed (already exists - agent 1 confirmed)

**Verify**: `load_1m_data_impl()` is called for all backtests

### 5.2 Preflight Validation

**File**: `src/backtest/runtime/preflight.py`

**Add**: Validate 1m data coverage matches exec TF coverage
```python
def validate_1m_coverage(exec_start, exec_end, quote_feed):
    expected_1m_bars = (exec_end - exec_start).total_seconds() / 60
    if len(quote_feed) < expected_1m_bars * 0.95:  # 95% coverage
        raise PreflightError("Insufficient 1m data coverage")
```

### Checklist
- [ ] Verify 1m data loaded for all backtests
- [ ] Add 1m coverage validation to preflight

---

## Phase 6: Validation IdeaCards

**Scope**: Create validation cards for 1m evaluation

### 6.1 New Validation Cards

| Card | Purpose |
|------|---------|
| `V_60_mark_price_basic.yml` | Verify mark_price accessible |
| `V_61_zone_touch.yml` | Verify zone touch at 1m |
| `V_62_entry_timing.yml` | Verify entry at 1m ts_close |

### V_60_mark_price_basic.yml
```yaml
id: V_60_mark_price_basic
timeframes:
  exec: "5m"
signal_rules:
  entry_rules:
    - direction: "long"
      conditions:
        - indicator_key: "mark_price"
          operator: "lt"
          value: 100000
```

### Checklist
- [ ] Create V_60_mark_price_basic.yml
- [ ] Create V_61_zone_touch.yml
- [ ] Create V_62_entry_timing.yml
- [ ] Run validation with normalize-batch

---

## Implementation Order

```
Phase 1: Index Mapping (1 file, ~20 lines)
    ↓
Phase 2: Snapshot Resolution (1 file, ~10 lines)
    ↓
Phase 3: Engine Loop (1 file, ~80 lines)
    ↓
Phase 4: Exchange Fill (3 files, ~100 lines)
    ↓
Phase 5: Data Loading (verify existing, ~10 lines)
    ↓
Phase 6: Validation Cards (3 files)
```

**Total estimated changes**: ~220 lines of code

---

## What's Already Built (Agent Investigation)

| Component | Status | Location |
|-----------|--------|----------|
| 1m data loading | **EXISTS** | `engine_feed_builder.py:539-587` |
| QuoteState dataclass | **EXISTS** | `runtime/types.py` |
| ExecRollupBucket | **EXISTS** | `runtime/rollup_bucket.py` |
| FeedStore | **EXISTS** | `runtime/feed_store.py` |
| mark_price attribute | **EXISTS** | `snapshot_view.py:150-233` |
| price.mark.close resolution | **EXISTS** | `snapshot_view.py:796-843` |
| Compiled refs path | **EXISTS** | `rules/compile.py`, `rules/eval.py` |

---

## What's NOT In Scope

| Item | Reason |
|------|--------|
| Live trading engine | Prep only - no implementation |
| WebSocket integration | Future phase |
| Historical mark_price offsets | Phase 2 enhancement |
| Multi-symbol 1m | Single symbol first |

---

## Design Decisions

1. **TP/SL at 1m**: Yes - consistent with 1m evaluation
2. **Max 1 entry per exec bar**: Prevents rapid-fire entries
3. **Warmup uses exec bars**: 1m data loaded but not evaluated
4. **Fallback path**: process_bar() works without quote_feed (backward compat)

---

## Performance Notes

| Exec TF | 1m Evals/Bar | Slowdown | Acceptable |
|---------|--------------|----------|------------|
| 1m | 1 | None | Yes |
| 5m | 5 | 5x | Yes |
| 15m | 15 | 15x | Yes |
| 1h | 60 | 60x | Yes |

**Mitigation**: Early exit on signal (one entry per exec bar)

---

*Last updated: January 2026*
