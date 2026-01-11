# Hybrid Engine Design: Backtest → Live Bridge

> **Status**: Design Complete | **Implementation**: Not Started
> **Last Updated**: 2026-01-10
> **Author**: Claude (with user collaboration)

---

## Executive Summary

This document specifies the architecture for bridging TRADE's backtest engine with live trading. The design enables:

1. **Same Play YAML** for backtest AND live (identical strategy evaluation)
2. **Historical warmup** → seamless live transition
3. **Multi-TF from day one** (HTF/MTF/LTF with forward-fill)
4. **Demo → Live** via environment variable

---

## Table of Contents

1. [Current State Analysis](#current-state-analysis)
2. [Design Requirements](#design-requirements)
3. [Latency Analysis](#latency-analysis)
4. [Multi-TF Architecture](#multi-tf-architecture)
5. [Protocol Definitions](#protocol-definitions)
6. [Module Structure](#module-structure)
7. [Hybrid Engine Flow](#hybrid-engine-flow)
8. [Incremental Indicators](#incremental-indicators)
9. [Implementation Roadmap](#implementation-roadmap)
10. [Open Questions](#open-questions)

---

## Current State Analysis

### Two Parallel Stacks (Not Integrated)

```
┌─────────────────────────────────────────────────────────────────┐
│                     CURRENT ARCHITECTURE                        │
│                                                                 │
│   ┌─────────────────────┐       ┌─────────────────────┐        │
│   │   BACKTEST STACK    │       │    LIVE STACK       │        │
│   │   ───────────────   │       │    ──────────       │        │
│   │                     │       │                     │        │
│   │   DuckDB            │       │   WebSocket         │        │
│   │      ↓              │       │      ↓              │        │
│   │   FeedStore         │       │   RealtimeState     │        │
│   │      ↓              │       │      ↓              │        │
│   │   Snapshot          │  ✗    │   ???               │        │
│   │      ↓              │  NO   │      ↓              │        │
│   │   Strategy.on_bar() │ BRIDGE│   ???               │        │
│   │      ↓              │       │      ↓              │        │
│   │   SimExchange       │       │   ExchangeManager   │        │
│   │      ↓              │       │      ↓              │        │
│   │   Ledger            │       │   Bybit API         │        │
│   │                     │       │                     │        │
│   └─────────────────────┘       └─────────────────────┘        │
│                                                                 │
│   Shared: Signal, RiskConfig types                              │
│   NOT shared: Data access, snapshot, strategy evaluation        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Key Divergences

| Aspect | Backtest | Live |
|--------|----------|------|
| **Candle Source** | DuckDB (historical) | WebSocket (realtime) |
| **Indicator Computation** | Vectorized before loop | Must be incremental |
| **Price Source** | Mock (OHLCV) | Real (last_price, mark_price) |
| **Access Pattern** | Arrays (FeedStore) | Dicts/deques (RealtimeState) |
| **Fill Timing** | Next bar open (deterministic) | Immediate (exchange) |
| **Order Types** | Market + attached TP/SL | Full order book |
| **Partial Fills** | No | Yes |

### What's Missing (The Three Bridge Layers)

1. **TradingSnapshot Protocol** - Unified data access interface
2. **ExchangeAPI Protocol** - Unified order execution interface
3. **IndicatorComputer** - Incremental indicator state machine

---

## Design Requirements

```
┌─────────────────────────────────────────────────────────────────┐
│                    DESIGN REQUIREMENTS                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ✓ Same Play YAML for backtest AND live                         │
│  ✓ Demo → Live via env variable (BYBIT_USE_DEMO)                │
│  ✓ Multi-TF from day one (HTF/MTF/LTF)                          │
│  ✓ Historical warmup → seamless live transition                 │
│  ✓ Relaxed latency target (<1s) for 15m+ execution TF           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Latency Analysis

### Latency Breakdown

```
┌─────────────────────────────────────────────────────────────────┐
│                   LATENCY BREAKDOWN                             │
│                                                                 │
│   Bar closes at 10:15:00.000                                    │
│        │                                                        │
│        ▼                                                        │
│   WebSocket delivers bar ────────────────── +50-200ms           │
│        │                                    (network)           │
│        ▼                                                        │
│   Update indicators (all TFs) ───────────── +1-50ms             │
│        │                                    (compute)           │
│        ▼                                                        │
│   Evaluate strategy DSL ─────────────────── +1-10ms             │
│        │                                    (logic)             │
│        ▼                                                        │
│   Submit order to exchange ──────────────── +50-150ms           │
│        │                                    (network)           │
│        ▼                                                        │
│   Order filled ──────────────────────────── +0-500ms            │
│                                             (exchange)          │
│                                                                 │
│   TOTAL: 100-900ms typical                                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Three Latency Approaches

| Approach | Target | Exec TF | Implementation | Use Case |
|----------|--------|---------|----------------|----------|
| **Relaxed** | <1s | 15m+ | Simple Python, sync | Swing trading |
| **Optimized** | <200ms | 5m+ | Incremental, async orders | Intraday |
| **Low-Latency** | <50ms | 1m+ | Rust/C++, co-located | Scalping |

### Recommended Approach: Relaxed

```
┌─────────────────────────────────────────────────────────────────┐
│                   RECOMMENDED: RELAXED                          │
│                                                                 │
│   Target: < 1 second end-to-end                                 │
│   Execution TF: 15m+                                            │
│                                                                 │
│   Rationale:                                                    │
│   - 15m bar = 900,000ms window                                  │
│   - 1 second latency = 0.1% of bar                              │
│   - Slippage from latency: negligible                           │
│   - Matches backtest behavior exactly                           │
│   - Simple, debuggable, maintainable                            │
│                                                                 │
│   Can optimize LATER without architectural changes              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Multi-TF Architecture

### The Challenge

```
┌─────────────────────────────────────────────────────────────────┐
│              MULTI-TF IN LIVE: THE CHALLENGE                    │
│                                                                 │
│   Backtest: All bars pre-exist, just index into arrays          │
│   Live: Bars arrive at DIFFERENT times!                         │
│                                                                 │
│   Example: exec=15m, mtf=1h, htf=4h                             │
│                                                                 │
│   Time        15m bar    1h bar     4h bar                      │
│   ──────────  ───────    ──────     ──────                      │
│   10:15       CLOSE      -          -                           │
│   10:30       CLOSE      -          -                           │
│   10:45       CLOSE      -          -                           │
│   11:00       CLOSE      CLOSE      -        ← MTF updates!     │
│   11:15       CLOSE      -          -                           │
│   ...                                                           │
│   12:00       CLOSE      CLOSE      CLOSE    ← All TFs update!  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Solution: TF-Aware RingBuffers

```
┌─────────────────────────────────────────────────────────────────┐
│            MULTI-TF RINGBUFFER ARCHITECTURE                     │
│                                                                 │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │                   LiveFeedStore                         │   │
│   │                                                         │   │
│   │   exec_buffer (15m):  [═══════════════════════════]    │   │
│   │                        capacity: 500 bars               │   │
│   │                        updates: every 15m               │   │
│   │                                                         │   │
│   │   mtf_buffer (1h):    [═══════════════════════════]    │   │
│   │                        capacity: 200 bars               │   │
│   │                        updates: every 1h                │   │
│   │                        forward-fills between            │   │
│   │                                                         │   │
│   │   htf_buffer (4h):    [═══════════════════════════]    │   │
│   │                        capacity: 100 bars               │   │
│   │                        updates: every 4h                │   │
│   │                        forward-fills between            │   │
│   │                                                         │   │
│   │   quote_buffer (1m):  [═══════════════════════════]    │   │
│   │                        capacity: 100 bars               │   │
│   │                        for intrabar TP/SL               │   │
│   │                                                         │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│   Each buffer contains:                                         │
│   ├── OHLCV arrays                                              │
│   ├── Indicator values (computed incrementally)                 │
│   ├── Structure state (swings, zones)                           │
│   └── Last close timestamp                                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Bar Close Detection Logic

```
on_kline_close(kline_1m):
    │
    ├── Always update quote_buffer (1m)
    │
    ├── Is this a 15m boundary? (minute % 15 == 0)
    │   └── Yes: Aggregate & update exec_buffer
    │            Update exec indicators
    │            Update exec structures
    │
    ├── Is this a 1h boundary? (minute == 0)
    │   └── Yes: Aggregate & update mtf_buffer
    │            Update mtf indicators
    │
    ├── Is this a 4h boundary? (hour % 4 == 0, minute == 0)
    │   └── Yes: Aggregate & update htf_buffer
    │            Update htf indicators
    │
    └── If exec bar closed:
            Build snapshot
            Evaluate strategy
            Submit orders if signal
```

### Forward-Fill Semantics (Matches Backtest)

```
┌─────────────────────────────────────────────────────────────────┐
│              FORWARD-FILL: LIVE MIRRORS BACKTEST                │
│                                                                 │
│   class LiveSnapshot(TradingSnapshot):                          │
│                                                                 │
│       def get_feature(self, tf_role: str, key: str) -> float:   │
│           │                                                     │
│           ├── if tf_role == "ltf":                              │
│           │       return exec_buffer.get(key)                   │
│           │                                                     │
│           ├── if tf_role == "mtf":                              │
│           │       return mtf_buffer.get(key)  # auto forward-fill│
│           │                                                     │
│           └── if tf_role == "htf":                              │
│                   return htf_buffer.get(key)  # auto forward-fill│
│                                                                 │
│   Buffer handles forward-fill automatically:                    │
│   - Only appends on TF close                                    │
│   - get() always returns latest value                           │
│   - Between closes, value unchanged = forward-filled            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Protocol Definitions

### TradingSnapshot Protocol

```python
class TradingSnapshot(Protocol):
    """
    Unified market view - works for BOTH backtest and live.
    Strategy code uses ONLY this interface.
    """

    @property
    def symbol(self) -> str: ...

    @property
    def ts_close(self) -> datetime: ...

    @property
    def close(self) -> float: ...

    @property
    def last_price(self) -> float: ...

    @property
    def mark_price(self) -> float: ...

    def get_feature(
        self,
        tf_role: str,      # "ltf", "mtf", "htf"
        key: str,          # "ema_9", "rsi_14", etc.
        offset: int = 0    # 0=current, -1=prev, etc.
    ) -> float | None:
        """Get indicator value. None if not ready or NaN."""
        ...

    def get_structure_field(
        self,
        block_key: str,    # "swing", "demand_zone", etc.
        field: str         # "high_level", "zone0_state", etc.
    ) -> Any:
        """Get structure field value."""
        ...

    def bars_exec_close(self, count: int) -> list[float]:
        """Get last N exec bar closes for window operators."""
        ...

    def is_feature_ready(self, tf_role: str, key: str) -> bool:
        """Has this indicator completed warmup?"""
        ...
```

### ExchangeAPI Protocol

```python
class ExchangeAPI(Protocol):
    """
    Unified order interface - works for BOTH backtest and live.
    """

    def submit_order(
        self,
        symbol: str,
        side: str,              # "BUY", "SELL"
        size_usdt: float,
        order_type: str = "MARKET",
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> str:  # Returns order_id
        """Submit order. Returns order ID."""
        ...

    def get_position(self, symbol: str) -> Position | None:
        """Get current position, if any."""
        ...

    def close_position(self, symbol: str) -> bool:
        """Close entire position."""
        ...

    def cancel_all_orders(self, symbol: str) -> int:
        """Cancel all pending orders. Returns count."""
        ...
```

### Signal Type (Already Shared)

```python
@dataclass
class Signal:
    """Shared between backtest and live."""
    symbol: str
    direction: str          # "LONG", "SHORT", "FLAT"
    size_usdt: float        # ALWAYS USDT (global standard)
    strategy: str
    stop_loss: float | None = None
    take_profit: float | None = None
    confidence: float = 1.0
```

---

## Module Structure

### Proposed Directory Layout

```
src/
├── trading/                    ← NEW: Unified trading layer
│   ├── __init__.py
│   ├── protocols.py            ← TradingSnapshot, ExchangeAPI
│   ├── snapshot.py             ← Base snapshot logic
│   ├── engine.py               ← Unified engine interface
│   └── signal.py               ← Signal type (move from backtest)
│
├── trading/live/               ← Live-specific implementations
│   ├── __init__.py
│   ├── feed_store.py           ← LiveFeedStore (RingBuffers)
│   ├── snapshot.py             ← LiveSnapshot
│   ├── indicator_computer.py   ← Incremental indicators
│   ├── exchange.py             ← LiveExchange (wraps Bybit)
│   └── engine.py               ← LiveEngine / HybridEngine
│
├── trading/backtest/           ← Backtest-specific (refactored)
│   ├── __init__.py
│   ├── feed_store.py           ← FeedStore (arrays) - EXISTS
│   ├── snapshot.py             ← RuntimeSnapshotView - EXISTS
│   ├── exchange.py             ← SimExchange - EXISTS
│   └── engine.py               ← BacktestEngine - EXISTS
│
├── backtest/                   ← EXISTING (gradually migrate)
├── core/                       ← EXISTING live components
└── exchanges/                  ← EXISTING Bybit client
```

### Demo vs Live Separation

```
┌─────────────────────────────────────────────────────────────────┐
│                 DEMO vs LIVE SEPARATION                         │
│                                                                 │
│   Same code, different endpoints:                               │
│                                                                 │
│   if os.getenv("BYBIT_USE_DEMO") == "true":                     │
│       endpoint = "api-demo.bybit.com"                           │
│       api_key = os.getenv("BYBIT_DEMO_API_KEY")                │
│   else:                                                         │
│       endpoint = "api.bybit.com"                                │
│       api_key = os.getenv("BYBIT_LIVE_API_KEY")                │
│                                                                 │
│   Already implemented in src/exchanges/bybit_client.py!         │
│   NO code changes between demo and live.                        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Hybrid Engine Flow

### Complete Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                   HYBRID ENGINE FLOW                            │
│                                                                 │
│   PHASE 1: HISTORICAL WARMUP                                    │
│   ══════════════════════════                                    │
│                                                                 │
│   ┌─────────────────────────────────────────────┐               │
│   │ 1. Load historical data from DuckDB         │               │
│   │    - Fetch enough for indicator warmup      │               │
│   │    - e.g., 500 bars per TF                  │               │
│   │                                             │               │
│   │ 2. Build FeedStore (like backtest)          │               │
│   │    - Vectorized indicator computation       │               │
│   │    - Structures initialized                 │               │
│   │                                             │               │
│   │ 3. Transfer to LiveFeedStore                │               │
│   │    - Copy last N values to RingBuffers      │               │
│   │    - Copy structure state                   │               │
│   │    - Copy indicator state for incremental   │               │
│   └─────────────────────────────────────────────┘               │
│        │                                                        │
│        ▼                                                        │
│   PHASE 2: CATCH-UP (if needed)                                 │
│   ═════════════════════════════                                 │
│                                                                 │
│   ┌─────────────────────────────────────────────┐               │
│   │ 4. Check: Is DuckDB data current?           │               │
│   │    - Last bar timestamp vs now              │               │
│   │    - If gap > 1 bar: fetch missing via REST │               │
│   │                                             │               │
│   │ 5. Process any missed bars                  │               │
│   │    - Update indicators incrementally        │               │
│   │    - NO trading during catch-up             │               │
│   └─────────────────────────────────────────────┘               │
│        │                                                        │
│        ▼                                                        │
│   PHASE 3: LIVE TRADING                                         │
│   ═════════════════════════                                     │
│                                                                 │
│   ┌─────────────────────────────────────────────┐               │
│   │ 6. Connect WebSocket                        │               │
│   │    - Subscribe to kline stream (1m)         │               │
│   │    - Subscribe to position stream           │               │
│   │                                             │               │
│   │ 7. On each exec bar close:                  │               │
│   │    - Update indicators                      │               │
│   │    - Update structures                      │               │
│   │    - Build LiveSnapshot                     │               │
│   │    - signal = evaluate_strategy(snapshot)   │               │
│   │    - if signal: exchange.submit_order()     │               │
│   │                                             │               │
│   │ 8. Loop forever (or until stopped)          │               │
│   └─────────────────────────────────────────────┘               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Switch Point Detail

```
TIMELINE
════════════════════════════════════════════════════════════════►

    HISTORICAL DATA                    │           LIVE DATA
    (DuckDB)                           │           (WebSocket)
                                       │
    ┌───┬───┬───┬───┬───┬───┬───┬───┐  │  ┌───┬───┬───┬───┐
    │   │   │   │   │   │   │   │ X │  │  │ 1 │ 2 │ 3 │...│
    └───┴───┴───┴───┴───┴───┴───┴───┘  │  └───┴───┴───┴───┘
                                ▲      │      ▲
                                │      │      │
                          Last DuckDB  │  First WebSocket
                          bar close    │  bar close
                                       │
                               SWITCH POINT

    At switch point:
    1. Last DuckDB bar timestamp = T
    2. First WebSocket bar timestamp = T + interval
    3. No gap, no overlap (clean handoff)

    State transferred:
    ├── Indicator state (last N values for lookback)
    ├── Structure state (swing levels, zones)
    ├── Position state (if any from warmup)
    └── History windows (for holds_for, etc.)
```

---

## Incremental Indicators

### Formulas for O(1) Updates

```
┌─────────────────────────────────────────────────────────────────┐
│           INCREMENTAL INDICATOR FORMULAS                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   EMA (Exponential Moving Average)                              │
│   ════════════════════════════════                              │
│   α = 2 / (length + 1)                                          │
│   ema_new = α * close + (1 - α) * ema_prev                      │
│                                                                 │
│   State: ema_prev                                               │
│   Update: O(1)                                                  │
│                                                                 │
│   ───────────────────────────────────────────────────────────   │
│                                                                 │
│   RSI (Relative Strength Index)                                 │
│   ═════════════════════════════                                 │
│   gain = max(0, close - prev_close)                             │
│   loss = max(0, prev_close - close)                             │
│   avg_gain = (avg_gain_prev * (n-1) + gain) / n                 │
│   avg_loss = (avg_loss_prev * (n-1) + loss) / n                 │
│   rs = avg_gain / avg_loss                                      │
│   rsi = 100 - (100 / (1 + rs))                                  │
│                                                                 │
│   State: avg_gain_prev, avg_loss_prev, prev_close               │
│   Update: O(1)                                                  │
│                                                                 │
│   ───────────────────────────────────────────────────────────   │
│                                                                 │
│   ATR (Average True Range)                                      │
│   ═════════════════════════                                     │
│   tr = max(high-low, |high-prev_close|, |low-prev_close|)       │
│   atr = (atr_prev * (n-1) + tr) / n                             │
│                                                                 │
│   State: atr_prev, prev_close                                   │
│   Update: O(1)                                                  │
│                                                                 │
│   ───────────────────────────────────────────────────────────   │
│                                                                 │
│   SMA (Simple Moving Average)                                   │
│   ═══════════════════════════                                   │
│   sma_new = sma_prev + (new_close - oldest_close) / n           │
│                                                                 │
│   State: RingBuffer of last N closes, running_sum               │
│   Update: O(1) with running sum trick                           │
│                                                                 │
│   ───────────────────────────────────────────────────────────   │
│                                                                 │
│   Bollinger Bands                                               │
│   ═══════════════                                               │
│   middle = SMA(n)                                               │
│   std = sqrt(sum((x - mean)^2) / n)                             │
│   upper = middle + k * std                                      │
│   lower = middle - k * std                                      │
│                                                                 │
│   State: RingBuffer, running_sum, running_sum_sq                │
│   Update: O(1) with Welford's algorithm                         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Validation Requirement

All incremental indicators MUST be validated against vectorized versions:

```python
# Validation test pattern
def test_incremental_ema_matches_vectorized():
    prices = generate_random_prices(1000)

    # Vectorized (ground truth)
    ema_vectorized = pandas_ta.ema(prices, length=20)

    # Incremental
    computer = IncrementalEMA(length=20)
    ema_incremental = []
    for price in prices:
        computer.update(price)
        ema_incremental.append(computer.value)

    # Must match within floating point tolerance
    assert np.allclose(ema_vectorized, ema_incremental, rtol=1e-10)
```

---

## Implementation Roadmap

### Phase A: Protocol Foundation

- [ ] Create `src/trading/` directory structure
- [ ] Define `TradingSnapshot` protocol in `protocols.py`
- [ ] Define `ExchangeAPI` protocol in `protocols.py`
- [ ] Refactor `RuntimeSnapshotView` to implement `TradingSnapshot`
- [ ] Refactor `SimExchange` to implement `ExchangeAPI`
- [ ] Verify backtest still works unchanged
- [ ] Add protocol compliance tests

### Phase B: RingBuffer & LiveFeedStore

- [ ] Implement `RingBuffer` data structure with O(1) operations
- [ ] Implement `LiveFeedStore` with multi-TF buffers
- [ ] Implement bar close detection logic (15m/1h/4h boundaries)
- [ ] Implement forward-fill semantics matching backtest
- [ ] Unit tests for buffer operations
- [ ] Unit tests for bar aggregation

### Phase C: Incremental Indicators

- [ ] Implement `IncrementalEMA`
- [ ] Implement `IncrementalRSI`
- [ ] Implement `IncrementalATR`
- [ ] Implement `IncrementalSMA` (with running sum)
- [ ] Implement `IncrementalBBands` (Welford's algorithm)
- [ ] Implement `IncrementalMACD`
- [ ] Add more indicators as needed from registry
- [ ] Validation tests: compare to vectorized versions

### Phase D: LiveSnapshot

- [ ] Implement `LiveSnapshot` conforming to `TradingSnapshot`
- [ ] Multi-TF feature access with forward-fill
- [ ] History window support (`bars_exec_close`)
- [ ] Structure field access
- [ ] `is_feature_ready()` for warmup detection
- [ ] Integration tests with mock data

### Phase E: LiveExchange

- [ ] Implement `LiveExchange` conforming to `ExchangeAPI`
- [ ] Wrap `BybitClient` methods
- [ ] Handle partial fills gracefully
- [ ] Handle order amendments
- [ ] Error handling and retries
- [ ] Rate limiting integration
- [ ] Demo mode testing

### Phase F: HybridEngine

- [ ] Historical warmup loader from DuckDB
- [ ] State transfer: FeedStore → LiveFeedStore
- [ ] Catch-up logic for missed bars
- [ ] WebSocket integration (kline + position streams)
- [ ] Main trading loop
- [ ] Graceful shutdown handling
- [ ] Reconnection logic

### Phase G: Validation & Testing

- [ ] Demo trading on Bybit testnet
- [ ] Signal comparison: backtest vs live (must match!)
- [ ] Stress test: disconnection recovery
- [ ] Stress test: high-frequency bar closes
- [ ] Monitoring and structured logging
- [ ] Alert integration (optional)

### Phase H: Production

- [ ] Live trading with minimal size
- [ ] Performance monitoring
- [ ] Error alerting
- [ ] Gradual size increase
- [ ] Documentation for operations

---

## Open Questions

### To Be Decided Before Implementation

1. **Indicator Coverage**: Which of the 43 registry indicators need incremental versions for Phase 1? Recommend starting with: EMA, RSI, ATR, SMA, MACD, BBands.

2. **Structure Support**: Which structures need live support first? Recommend: Swing detection only (simplest).

3. **Position Sync**: On startup, should we query existing positions from Bybit, or assume clean slate?

4. **Multi-Symbol**: Design is single-symbol. Multi-symbol would need separate engines or multiplexed buffers.

5. **Persistence**: Should live state be persisted for crash recovery? Adds complexity.

6. **Monitoring**: What metrics to expose? Latency histograms, signal counts, PnL tracking?

---

## Related Documents

| Document | Purpose |
|----------|---------|
| `docs/guides/BACKTEST_ENGINE_CONCEPTS.md` | Conceptual guide to current engine |
| `docs/architecture/SIMULATED_EXCHANGE.md` | SimExchange architecture |
| `docs/architecture/PLAY_ENGINE_FLOW.md` | Play → Engine data flow |
| `docs/specs/PLAY_DSL_COOKBOOK.md` | DSL syntax reference |

---

## Changelog

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-10 | Claude | Initial design document |
