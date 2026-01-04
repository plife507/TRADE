# Unified WarmupGate + RuntimeReady Architecture Review

**Date**: 2026-01-01
**Status**: Proposed
**Scope**: Simulator + Live WebSocket warmup unification

---

## Executive Summary

**Recommendation: YES — Implement a unified WarmupGate + RuntimeReady pattern**

This is NOT merely an optimization but a **strategic architectural unification** that achieves:
1. **Live/backtest parity** by using the exact same warming pipeline
2. **Order execution safety** by blocking orders until all dependencies are ready
3. **Clean separation of concerns** with three distinct phases: warmup, ready, trading
4. **WebSocket resilience** via deterministic forward-fill semantics

---

## 1. Current State Analysis

### 1.1 Simulator Warmup (Existing)

The backtest engine has warmup logic scattered across multiple layers:

**Data Level** (`engine_data_prep.py`):
- Computes warmup bars from indicator specs
- Extends query range by warmup span before window_start
- Finds first valid bar where all indicators are non-NaN
- Sets `simulation_start` to max(first_valid_bar, window_start)

**Feed Level** (`feed_store.py`):
- Stores `warmup_bars` metadata
- FeedStore carries first-valid-index awareness

**Runtime Level** (`engine.py` lines 760-792):
```python
if i < sim_start_idx:
    # Extract features but skip strategy evaluation
    warmup_features_exec = FeatureSnapshot(...)
    self._update_history(...)
    prev_bar = bar
    continue
```

**Multi-TF Level** (`engine.py` lines 895-913):
```python
if self._multi_tf_mode and not snapshot.ready:
    # Caches not ready yet - record equity but skip strategy
    ...
    continue

# Mark warmup as complete on first ready snapshot
if self._multi_tf_mode and not self._warmup_complete:
    self._warmup_complete = True
    self._first_ready_bar_index = i
```

**Key Issue**: Warmup is **bar-index driven** (`i < sim_start_idx`), not **feature-driven**.

### 1.2 Live Trading (Current State)

**WebSocket Data Flow**:
1. `RealtimeBootstrap` subscribes to streams
2. WebSocket callbacks fire -> `RealtimeState` updates
3. ExchangeManager queries state via REST/WS

**No Warmup Mechanism**: Orders execute immediately upon signal, with:
- No forced indicator computation period
- No explicit "ready" gate
- Risk of stale indicators on first tick
- WebSocket tick data arrives asynchronously

**Key Issue**: **No unified warmup semantics between live and backtest.**

### 1.3 Runtime Readiness Patterns (Partial)

**TimeframeCache** (`runtime/cache.py` lines 108-120):
```python
@property
def htf_ready(self) -> bool:
    """Check if HTF cache has a valid snapshot."""
    return self._htf_snapshot is not None and self._htf_snapshot.ready

@property
def all_ready(self) -> bool:
    """Check if both HTF and MTF caches are ready."""
    return self.htf_ready and self.mtf_ready
```

**RuntimeSnapshotView** (`snapshot_view.py` lines 237-245):
```python
@property
def ready(self) -> bool:
    """Check if snapshot is ready for strategy evaluation."""
    return (
        self.exec_ctx.ready and
        self.htf_ctx.ready and
        self.mtf_ctx.ready and
        self.history_ready
    )
```

**Issue**: These are **read-only status checks**, not **active warmup orchestrators**.

---

## 2. Proposed Architecture

### 2.1 Three-Phase Model

```
+---------------------------------------------------------------------+
| Unified Runtime Lifecycle (Simulator + Live WebSocket)              |
+---------------------------------------------------------------------+

PHASE 1: WARMUP (orders_disabled=True, orders_blocked=True)
|- Consume closed candles (historical or real-time)
|- Advance feeds through exact same pipeline as trading
|- Update indicators, structure, zones
|- Build snapshots (but do NOT evaluate strategy)
|- Populate history windows
|- Continue until: warmup_bars processed + history_ready
|
PHASE 2: READY (orders_disabled=False, orders_blocked=False)
|- First bar where all gate conditions pass
|- Gate unlocks: can now evaluate strategy + place orders
|- All indicators initialized, history filled, caches populated
|- One-time transition: emit ready_ts event
|
PHASE 3: TRADING (normal operation)
|- Strategy evaluation -> signal generation -> order submission
+- WebSocket ticks forward-fill cached HTF/MTF values
```

### 2.2 Core Classes

#### A. WarmupGate

```python
"""
Unified warmup orchestrator for simulator and live-websocket runtimes.

Enforces identical warming pipeline:
1. Replayed historical bars (exact same pipeline as live ticks)
2. No orders allowed until all gates pass
3. Deterministic forward-fill for HTF/MTF between closes
4. Single source of truth for "ready" status
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Callable, List, Dict, Any
from enum import Enum


class WarmupPhase(str, Enum):
    """Warmup lifecycle phase."""
    PREWARMUP = "prewarmup"      # Before warmup starts
    WARMING = "warming"          # In active warmup period
    READY = "ready"              # Warmup complete, gates open
    TRADING = "trading"          # Full operation
    STOPPED = "stopped"          # Warmup cancelled/stopped


@dataclass
class WarmupGateConfig:
    """
    Configuration for warmup gate.

    Attributes:
        warmup_bars_exec: Number of exec-TF bars to consume before trading
        warmup_bar_indices: Optional pre-computed set of indices to skip
        history_windows: Dict mapping window_name -> required depth in bars
        feed_sources: Dict mapping role -> FeedStore (exec, htf, mtf)
        enable_history: Whether to populate history windows
    """
    warmup_bars_exec: int
    warmup_bar_indices: Optional[set] = None  # [0, sim_start_idx)
    history_windows: Dict[str, int] = field(default_factory=dict)
    feed_sources: Dict[str, Any] = field(default_factory=dict)
    enable_history: bool = True

    # WebSocket-specific (live only)
    websocket_tick_buffer_max: int = 1000  # Max ticks to buffer during warmup


@dataclass
class WarmupStatus:
    """Current warmup state snapshot."""
    phase: WarmupPhase
    bars_consumed: int
    bars_required: int
    ts_warmup_start: Optional[datetime]
    ts_ready: Optional[datetime]
    history_ready: bool
    cache_ready: bool
    not_ready_reasons: List[str] = field(default_factory=list)

    @property
    def is_ready(self) -> bool:
        """Check if warmup is complete and system is ready."""
        return self.phase in (WarmupPhase.READY, WarmupPhase.TRADING)

    @property
    def is_warming(self) -> bool:
        """Check if still in active warmup."""
        return self.phase == WarmupPhase.WARMING


class WarmupGate:
    """
    Unified warmup orchestrator.

    Provides identical warming pipeline for:
    - Simulator: bar-by-bar replay of historical candles
    - Live: WebSocket tick ingestion + closed candle replay

    Usage (Simulator):
        gate = WarmupGate(config)
        gate.start()

        for bar in bars:
            status = gate.process_bar(bar, is_closed=True)
            if status.is_ready:
                signal = strategy(snapshot)
            else:
                # In warmup, caches updating but no strategy eval
                pass

    Usage (Live WebSocket):
        gate = WarmupGate(config)
        gate.start()

        def on_websocket_tick(tick):
            status = gate.process_tick(tick, is_closed=is_1m_closed)
            if status.is_ready:
                signal = strategy(snapshot)
            # Else: buffered or forward-filled

        ws.on_tick(on_websocket_tick)
    """

    def __init__(self, config: WarmupGateConfig):
        self.config = config
        self.phase = WarmupPhase.PREWARMUP
        self.bars_consumed = 0
        self.ts_warmup_start: Optional[datetime] = None
        self.ts_ready: Optional[datetime] = None
        self._history_ready = False
        self._cache_ready = False

        # WebSocket buffering (live only)
        self._tick_buffer: List[Dict[str, Any]] = []

        # Callbacks
        self._on_ready: Optional[Callable] = None
        self._on_phase_change: Optional[Callable] = None

    def start(self, ts: datetime) -> None:
        """Start warmup period."""
        if self.phase != WarmupPhase.PREWARMUP:
            raise RuntimeError(f"Cannot start from phase {self.phase}")
        self.phase = WarmupPhase.WARMING
        self.ts_warmup_start = ts

    def process_bar(
        self,
        bar: "CanonicalBar",
        is_closed: bool = True,
        **context: Any,
    ) -> WarmupStatus:
        """
        Process a bar (closed candle) through the warmup pipeline.

        Exact same pipeline for both simulator and live:
        1. Advance feeds (OHLCV, indicators)
        2. Update TimeframeCache (HTF/MTF)
        3. Populate history windows
        4. Build snapshot (no strategy eval yet)

        Args:
            bar: CanonicalBar to process
            is_closed: Whether this is a closed candle
            **context: Optional context (e.g., step_result for mark_price)

        Returns:
            WarmupStatus with current readiness
        """
        if not is_closed:
            # Forward-fill mode: update mark price, don't advance feeds
            return self._process_tick(bar, context)

        # Closed candle processing
        if self.phase == WarmupPhase.WARMING:
            self.bars_consumed += 1
            self._check_transition_to_ready(bar.ts_close)

        return self.get_status(bar.ts_close)

    def process_tick(
        self,
        tick: Dict[str, Any],
        is_closed: bool = False,
        **context: Any,
    ) -> WarmupStatus:
        """
        Process a WebSocket tick (may be partial or closed).

        Args:
            tick: Tick data dict
            is_closed: Whether this closes a 1m bar
            **context: Optional context

        Returns:
            WarmupStatus
        """
        if not is_closed:
            # Partial tick: buffer or forward-fill HTF/MTF
            if self.phase == WarmupPhase.WARMING:
                self._buffer_tick(tick)
            return self.get_status(tick.get("ts_close"))

        # Closed tick -> treat as bar
        bar = self._tick_to_bar(tick)
        return self.process_bar(bar, is_closed=True, **context)

    def _check_transition_to_ready(self, ts_close: datetime) -> None:
        """Check if all warmup conditions are met."""
        if self.phase != WarmupPhase.WARMING:
            return

        # Gate conditions (all must pass)
        bars_satisfied = self.bars_consumed >= self.config.warmup_bars_exec
        history_satisfied = self._is_history_ready()
        cache_satisfied = self._is_cache_ready()

        if bars_satisfied and history_satisfied and cache_satisfied:
            self.phase = WarmupPhase.READY
            self.ts_ready = ts_close
            self._invoke_ready_callback()

    def get_status(self, ts: datetime) -> WarmupStatus:
        """Get current warmup status."""
        return WarmupStatus(
            phase=self.phase,
            bars_consumed=self.bars_consumed,
            bars_required=self.config.warmup_bars_exec,
            ts_warmup_start=self.ts_warmup_start,
            ts_ready=self.ts_ready,
            history_ready=self._history_ready,
            cache_ready=self._cache_ready,
            not_ready_reasons=self._get_not_ready_reasons(),
        )

    def _get_not_ready_reasons(self) -> List[str]:
        """Get human-readable reasons why system is not ready."""
        reasons = []
        if self.bars_consumed < self.config.warmup_bars_exec:
            reasons.append(
                f"Warmup: {self.bars_consumed}/{self.config.warmup_bars_exec} bars"
            )
        if not self._history_ready:
            reasons.append("History: windows not filled")
        if not self._cache_ready:
            reasons.append("Cache: HTF/MTF snapshots not populated")
        return reasons

    def on_ready(self, callback: Callable) -> None:
        """Register callback to invoke when warmup complete."""
        self._on_ready = callback
```

#### B. RuntimeReady

```python
"""
Runtime readiness guard: blocks orders until gate passes.

Single responsibility: gate enforcement before order execution.
Works with both simulator and live trading.
"""

from enum import Enum
from typing import Optional


class RuntimeReadyState(str, Enum):
    """State of runtime readiness."""
    NOT_READY = "not_ready"      # Warmup in progress
    READY = "ready"              # Warmup complete
    READY_BLOCKED = "ready_blocked"  # Gate passed but orders blocked (rare)
    DEGRADED = "degraded"        # Partial failure (e.g., data lag)


class RuntimeReady:
    """
    Order execution gate: ONLY allows orders after warmup complete.

    Prevents premature orders with stale indicators.
    Works identically for simulator and live trading.

    Usage:
        gate = WarmupGate(config)
        ready_guard = RuntimeReady(gate)

        def on_signal(signal):
            if not ready_guard.can_execute_order():
                logger.debug(f"Order blocked: {ready_guard.not_ready_reason}")
                return

            exchange.submit_order(signal)
    """

    def __init__(self, warmup_gate: WarmupGate):
        self.gate = warmup_gate

    def can_execute_order(self) -> bool:
        """Check if orders are allowed."""
        status = self.gate.get_status()
        return status.is_ready and status.phase != WarmupPhase.STOPPED

    @property
    def not_ready_reason(self) -> Optional[str]:
        """Get human-readable reason orders are blocked."""
        status = self.gate.get_status()
        if status.is_ready:
            return None
        reasons = status.not_ready_reasons
        return "; ".join(reasons) if reasons else "Unknown reason"

    @property
    def state(self) -> RuntimeReadyState:
        """Get current readiness state."""
        status = self.gate.get_status()
        if status.is_ready:
            return RuntimeReadyState.READY
        return RuntimeReadyState.NOT_READY
```

---

## 3. WebSocket Tick Handling Strategies

### 3.1 Strategy Comparison

| Strategy | Pros | Cons | Best For |
|----------|------|------|----------|
| **Buffer** | Deterministic: replay exact ticks after warmup | Memory overhead; complexity | Production (integrity > performance) |
| **Ignore** | Minimal overhead; simple logic | Lost data; potential gaps | Demo / testing only |
| **Mark-Only** | Balance: tick updates mark price, no feed advance | HTF forward-fill partial; stale indicators | Less critical symbols |

### 3.2 Recommended: Buffer (Hybrid with Early-Exit)

```python
class WebSocketWarmupHandler:
    """
    Buffer incoming ticks during warmup, replay after ready.

    Guarantees: exact same order/timing as live, zero lookahead.
    """

    def __init__(self, gate: WarmupGate, max_buffer_size: int = 1000):
        self.gate = gate
        self.tick_buffer: Deque[Dict] = deque(maxlen=max_buffer_size)
        self.pending_replay = False

    def on_websocket_tick(self, tick: Dict[str, Any]) -> None:
        """Receive tick from WebSocket."""
        is_closed = tick.get("kline", {}).get("confirm") == "1"
        status = self.gate.get_status()

        if status.phase == WarmupPhase.WARMING:
            # Warmup: buffer tick
            if is_closed:
                self.tick_buffer.append(tick)
                # Process as closed bar through gate
                self.gate.process_bar(
                    self._tick_to_bar(tick),
                    is_closed=True,
                )
            else:
                # Partial: buffer but don't process
                self.tick_buffer.append(tick)

        elif status.phase == WarmupPhase.READY and not self.pending_replay:
            # Ready: replay buffered ticks, then live
            self.pending_replay = True
            self._replay_buffer()
            # Then process current tick normally
            self._process_live_tick(tick)

        else:
            # Trading: process live tick
            self._process_live_tick(tick)

    def _replay_buffer(self) -> None:
        """Replay buffered ticks after warmup complete."""
        for buffered_tick in self.tick_buffer:
            self._process_live_tick(buffered_tick)
        self.tick_buffer.clear()
```

---

## 4. Integration Points

### 4.1 Simulator Integration

**Integration in `BacktestEngine.run()`:**

```python
def run(self, strategy):
    # ... setup ...

    # Create and configure WarmupGate
    gate_config = WarmupGateConfig(
        warmup_bars_exec=prepared.warmup_bars,
        history_windows={"bars_exec": history_depth},
        feed_sources={
            "exec": self._exec_feed,
            "htf": self._htf_feed,
            "mtf": self._mtf_feed,
        },
        enable_history=True,
    )
    warmup_gate = WarmupGate(gate_config)
    ready_guard = RuntimeReady(warmup_gate)
    warmup_gate.start(df.iloc[0]["timestamp"])

    for i in range(num_bars):
        bar = CanonicalBar(...)

        # Process through warmup gate
        warmup_status = warmup_gate.process_bar(
            bar,
            is_closed=True,
            step_result=step_result,
        )

        # Build snapshot (always)
        snapshot = self._build_snapshot_view(i, step_result)

        # Evaluate strategy (only if ready)
        signal = None
        if warmup_status.is_ready and not self._exchange.entries_disabled:
            signal = strategy(snapshot, self.config.params)

        # Submit order (guarded by RuntimeReady)
        if signal is not None and ready_guard.can_execute_order():
            self._process_signal(signal, bar, snapshot)
```

### 4.2 Live WebSocket Integration

**Integration in `ExchangeManager`:**

```python
class ExchangeManager:
    def __init__(self):
        # ... existing setup ...

        # Initialize warmup gate for live trading
        self.warmup_gate = self._create_warmup_gate()
        self.ready_guard = RuntimeReady(self.warmup_gate)

        # Register WebSocket handler
        realtime_state.on_websocket_tick(self._on_tick)

    def _create_warmup_gate(self) -> WarmupGate:
        """Create gate configured for live trading."""
        warmup_bars = 20  # From config

        config = WarmupGateConfig(
            warmup_bars_exec=warmup_bars,
            history_windows={"bars_exec": warmup_bars + 5},
            feed_sources={"exec": self._exec_feed},
            enable_history=True,
            websocket_tick_buffer_max=500,
        )
        gate = WarmupGate(config)
        gate.on_ready(self._on_warmup_ready)
        gate.start(datetime.now(timezone.utc))
        return gate

    def _on_tick(self, tick: Dict[str, Any]) -> None:
        """Handle incoming 1m kline from WebSocket."""
        is_closed = tick.get("kline", {}).get("confirm") == "1"
        bar = self._tick_to_bar(tick)

        # Process through gate
        status = self.warmup_gate.process_bar(bar, is_closed=is_closed)

        # Build snapshot
        snapshot = self._build_snapshot_for_live(bar)

        # Evaluate strategy (always)
        signal = strategy(snapshot, self.config.params)

        # Submit order (guarded)
        if signal and self.ready_guard.can_execute_order():
            self.submit_order(signal, bar)
        elif signal:
            self.logger.debug(
                f"Order blocked during warmup: {self.ready_guard.not_ready_reason}"
            )
```

---

## 5. Live/Backtest Parity Guarantees

### 5.1 Indicator Computation

**Simulator**:
```python
# Phase: WARMING
for i in range(sim_start_idx):
    bar = bars[i]
    # Feeds advanced, indicators computed (during data prep)
    # Strategy NOT evaluated
    snapshot = build_snapshot(...)

# Phase: READY
signal = strategy(snapshot)  # First real eval
```

**Live**:
```python
# Phase: WARMING
for tick in websocket:
    bar = tick_to_bar(tick)
    # Same feed advance, same indicator pipeline
    # Strategy NOT evaluated
    snapshot = build_snapshot(...)

# Phase: READY
signal = strategy(snapshot)  # First real eval
```

**Guarantee**: Indicators computed in same order, same math

### 5.2 History Windows

Both use `HistoryManager`:
- Simulator: populated during warmup
- Live: populated during warmup

**Guarantee**: History available at first trade

### 5.3 MTF Forward-Fill

Both use `TimeframeCache` with identical logic:
- Update HTF/MTF on close
- Return cached value between closes

**Guarantee**: HTF/MTF values identical

---

## 6. Implementation Roadmap

### Phase 1: Core Interfaces (Foundational)
- [ ] Define `WarmupGate` and `RuntimeReady` classes
- [ ] Create `WarmupGateConfig` and `WarmupStatus` dataclasses
- [ ] Implement base `process_bar()` and `process_tick()` methods
- [ ] Add status properties: `is_ready`, `not_ready_reasons`

### Phase 2: Simulator Integration
- [ ] Refactor `BacktestEngine.run()` to use `WarmupGate`
- [ ] Replace manual `i < sim_start_idx` checks with gate status
- [ ] Wire `snapshot.ready` through gate state
- [ ] Add unit tests with synthetic data

### Phase 3: Live WebSocket Integration
- [ ] Create `WebSocketWarmupHandler` with buffer mode
- [ ] Integrate with `ExchangeManager` initialization
- [ ] Add position-specific warmup configuration
- [ ] Test with demo mode + live data

### Phase 4: Validation & Hardening
- [ ] Add parity tests: simulate warmup = live warmup
- [ ] Test WebSocket disconnection/reconnection
- [ ] Add metrics: bars_consumed, ready_latency, buffer_overflow_count
- [ ] CLI diagnostics: `backtest warmup-status`

### Phase 5: Cleanup
- [ ] Remove legacy `_warmup_complete` flags
- [ ] Delete manual `sim_start_idx` gates
- [ ] Archive old warmup patterns

---

## 7. Key Design Decisions & Rationale

### 7.1 Single WarmupGate for Both Domains

**Why**: Achieves **live/backtest parity** through code reuse.

**How**: WarmupGate accepts:
- Closed bars (simulator) -> deterministic replay
- WebSocket ticks (live) -> buffer + replay

**Trade-off**: Slightly more complex than domain-specific versions, but eliminates bugs from duplicate logic.

### 7.2 RuntimeReady as Separate Guard (Not in WarmupGate)

**Why**: Single Responsibility Principle.

- `WarmupGate` = *track readiness*
- `RuntimeReady` = *enforce readiness*

**Benefit**: Easy to mock in tests; can inject different strategies (permissive in dev, strict in prod).

### 7.3 Buffer Mode for WebSocket (Default)

**Why**: Determinism > Performance for trading.

**Cost**: ~1KB per tick x 1000 ticks = 1MB memory (negligible).

**Benefit**:
- Replayed ticks execute in exact order
- No skipped candles
- State machine logic unchanged between warmup/ready
- Easy to add metrics/debugging

### 7.4 Forward-Fill Semantics for HTF/MTF

**Why**: Matches TradingView lookahead_off semantics.

**How**: Between TF closes, snapshot returns cached value unchanged:
```python
# 5m bar, HTF = 1h
# If 1h bar closed 3 bars ago:
snapshot.htf_ema_fast  # <- returns value from 3 bars ago, unchanged
snapshot.ts_htf_close  # <- timestamp of last HTF close (stale marker)

# Strategy can detect staleness:
if snapshot.ts_close > snapshot.htf_ctx_ts_close:
    # HTF is forward-filled
    use_conservative_signal()
```

---

## 8. Anti-Patterns to Avoid

### 8.1 DO NOT: Compute Indicators During Trading

```python
# WRONG
if strategy_needs(indicator):
    indicator = compute_indicator(close[-20:])  # In hot loop!

# CORRECT
indicator = snapshot.indicator("ema_20")  # Pre-computed during warmup
```

### 8.2 DO NOT: Silently Default Missing Warmup

```python
# WRONG
warmup_bars = config.get("warmup_bars", 20)  # Implicit default!

# CORRECT
if "warmup_bars" not in config:
    raise ValueError("warmup_bars REQUIRED in config")
```

### 8.3 DO NOT: Block Strategy Evaluation Itself During Warmup

```python
# WRONG - misleading
if status.is_warming:
    signal = strategy(snapshot)  # Evaluate but don't execute?
    # Later: decide not to submit

# CORRECT
if status.is_warming:
    signal = None  # Don't call strategy at all
```

---

## 9. Testing Strategy

### 9.1 Unit Tests

```python
def test_warmup_gate_basic():
    config = WarmupGateConfig(warmup_bars_exec=5)
    gate = WarmupGate(config)
    gate.start(dt_now())

    for i in range(4):
        status = gate.process_bar(bar, is_closed=True)
        assert status.phase == WarmupPhase.WARMING

    # 5th bar -> READY
    status = gate.process_bar(bar, is_closed=True)
    assert status.phase == WarmupPhase.READY
    assert status.is_ready
```

### 9.2 Integration Tests

```python
def test_simulator_parity():
    # Run same 20 bars through:
    # 1. BacktestEngine (old warmup logic)
    # 2. BacktestEngine (new WarmupGate)

    # Assert: same trades, same equity curve
```

### 9.3 Live WebSocket Tests (Demo Mode)

```python
def test_websocket_warmup_buffer():
    # Subscribe to demo 1m BTCUSDT
    # Simulate 10 ticks during first hour

    # Assert: gate.phase == WARMING until 20+ bars
    # Assert: no orders submitted until ready
    # Assert: orders submitted after ready
```

---

## 10. File Placement

Recommended file structure:

```
src/backtest/runtime/
    warmup_gate.py          # WarmupGate, WarmupGateConfig, WarmupStatus, WarmupPhase
    runtime_ready.py        # RuntimeReady, RuntimeReadyState

src/core/
    websocket_warmup.py     # WebSocketWarmupHandler (live-specific)
```

---

## 11. Conclusion

### Direct Answer

**Q**: Do you recommend a single shared "WarmupGate" + "RuntimeReady" mechanism?

**A**: **YES, strongly recommended.** This is not optimization—it's **architectural correctness**.

### Why This Approach Wins

| Aspect | Unified Gate | Separate Logic |
|--------|--------------|-----------------|
| Code duplication | None | Moderate |
| Live/backtest parity | Guaranteed | Manual verification |
| Bug risk | Lower (one path) | Higher (two paths) |
| Maintenance | Single source | Two sources |
| Testing effort | Lower | Higher |
| Strategy parity | Certain | Uncertain |

### Key Architectural Benefits

1. **No Implicit Defaults**: All warmup bars, history windows, feed sources MUST be explicit
2. **Closed-Candle Only**: Indicators computed once per bar, forward-filled between closes
3. **Fail-Loud**: If any dependency not ready, error message is specific (not silent skip)
4. **Time-Travel Safe**: WebSocket buffer ensures no lookahead bias
5. **Debuggable**: Single gate exposes `not_ready_reasons` for diagnostics

---

## References

- `src/backtest/engine.py` - Current simulator warmup logic
- `src/backtest/runtime/snapshot_view.py` - RuntimeSnapshotView.ready property
- `src/backtest/runtime/cache.py` - TimeframeCache.all_ready
- `src/core/exchange_manager.py` - Live WebSocket integration point
- `CLAUDE.md` - Domain rules for simulator vs live
