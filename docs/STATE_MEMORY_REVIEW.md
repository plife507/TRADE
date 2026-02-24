# State & Memory Architecture Review

> **Date**: 2026-02-24
> **Scope**: Full evaluation of state management, memory growth, long-run stability, runtime performance, and language fitness for the TRADE system.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current State Architecture](#2-current-state-architecture)
3. [Memory Growth Analysis](#3-memory-growth-analysis)
4. [Long-Run Stability (Hours → Days → Weeks)](#4-long-run-stability)
5. [Runtime Performance Profile](#5-runtime-performance-profile)
6. [Is Python Still the Right Language?](#6-is-python-still-the-right-language)
7. [Improvements Before Advancing](#7-improvements-before-advancing)
8. [Recommendations](#8-recommendations)

---

## 1. Executive Summary

The TRADE system's state management is **well-designed for correctness** but has **operational gaps for long-running sessions**. Most data structures are properly bounded (deques with maxlen, ring buffers, rolling windows). However, several unbounded growth patterns would cause problems after 2-4 weeks of continuous live trading.

### Headline Findings

| Area | Verdict | Details |
|------|---------|---------|
| **Indicator state** | Excellent | O(1) incremental, ~50 KB total for all 44 indicators |
| **Structure state** | Good | Ring buffers, bounded. One exception: RollingWindow |
| **Live indicator cache** | Needs fix | `np.append()` creates ~50 MB/day GC pressure |
| **Log files** | Needs fix | No rotation — grows to GBs over weeks |
| **Bar buffers** | Needs fix | Unbounded deques in RealtimeState |
| **Journals** | Safe | Streaming to disk, no memory accumulation |
| **DuckDB** | Safe | No writes during live trading; WAL managed |
| **Position/order tracking** | Safe | Bounded deques (maxlen=10000) |
| **Crash recovery** | Partial | State files exist but no automatic restart |
| **Python fitness** | Correct choice | Ecosystem + dev velocity outweigh theoretical perf gains |
| **Backtest speed** | 2,000-10,000 bars/sec | Compute-efficient; I/O-bound (DuckDB), not CPU-bound |
| **Live latency** | 60-200 ms signal-to-order | Network-bound (exchange API), not system-bound |

### Critical Path: What Must Be Fixed Before Long-Run Live

1. **Log rotation** — unbounded disk growth
2. **Bar buffer bounds** — unbounded memory growth
3. **np.append → pre-allocated arrays** — unnecessary GC pressure
4. **Callback unregistration** — theoretical leak on reconnect

---

## 2. Current State Architecture

### 2.1 State Storage Map

```
┌─────────────────────────────────────────────────────────────────┐
│  PlayEngine State                                               │
│  ├── Position (side, size, entry_price, TP/SL)     ~1 KB       │
│  ├── Pending Orders (list)                          ~500 B     │
│  ├── Equity / Realized PnL (floats)                 ~100 B     │
│  ├── Incremental Indicators (44 scalars)            ~50 KB     │
│  └── Incremental Structures (ring buffers)          ~200 KB    │
│                                                                 │
│  TOTAL ENGINE STATE: ~250 KB                                    │
├─────────────────────────────────────────────────────────────────┤
│  Live Indicator Cache (per TF, rolling window)                  │
│  ├── OHLCV arrays (500 bars × 5 × 8 bytes)         ~20 KB     │
│  ├── Indicator arrays (500 bars × 20 × 4 bytes)    ~40 KB     │
│  └── Structure state (scalar + ring buffers)        ~5 KB      │
│                                                                 │
│  TOTAL LIVE CACHE: ~65 KB per TF × 3 TFs = ~195 KB            │
├─────────────────────────────────────────────────────────────────┤
│  FeedStore (Backtest only — immutable after load)               │
│  ├── OHLCV (25K bars × 7 × 8 bytes)                ~1.4 MB    │
│  ├── Indicators (25K bars × 20 × 4 bytes)          ~2.0 MB    │
│  ├── Timestamp maps (sets, dicts)                   ~3.0 MB    │
│  └── Metadata + structures                          ~0.6 MB    │
│                                                                 │
│  TOTAL FEEDSTORE: ~7 MB per TF × 3 TFs = ~21 MB               │
├─────────────────────────────────────────────────────────────────┤
│  Persistence Layer                                              │
│  ├── FileStateStore: data/runtime/state/{id}.json   ~5-100 KB  │
│  ├── TradeJournal: data/journal/{id}.jsonl          append-only │
│  ├── Instance Registry: data/runtime/instances/     ~1 KB/file │
│  └── DuckDB: market_data_{mode}.duckdb              read-only*  │
│                                                                 │
│  * No writes during live trading — only reads for warmup        │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Indicator State (44 Indicators, All O(1))

Every indicator maintains only scalar state — no historical arrays:

| Indicator | State Fields | Memory | Growth |
|-----------|-------------|--------|--------|
| EMA | `_ema`, `_count`, `_warmup_sum` | ~48 B | Zero |
| SMA | `_buffer` (deque, maxlen=length) | ~100-500 B | Zero (ring) |
| RSI | `_prev_close`, `_avg_gain`, `_avg_loss` | ~80 B | Zero |
| ATR | `_prev_close`, `_atr`, `_warmup_tr` (bounded) | ~200 B | Zero |
| MACD | 3× IncrementalEMA (nested) | ~200 B | Zero |
| BBands | `_buffer` (deque), `_running_sum`, `_running_sq_sum` | ~500 B | Zero |
| Stochastic | `_fast_k_buffer`, `_k_buffer` + MonotonicDeques | ~1-2 KB | Zero |
| ADX | IncrementalATR + `_adx_history` (deque, maxlen) | ~500 B | Zero |
| SuperTrend | IncrementalATR + scalar state | ~500 B | Zero |

**Total for all 44 indicators: ~50 KB** — this is outstanding. The incremental design means memory is constant regardless of how many bars are processed.

### 2.3 Structure State (7 Types)

| Structure | Core State | Memory | Bounded? |
|-----------|-----------|--------|----------|
| Swing (fractal) | 2× RingBuffer(left+right+1) | ~500 B | Yes (fixed numpy array) |
| Swing (atr_zigzag) | Direction flag, extreme price | ~50 B | Yes (scalars only) |
| Trend | direction, high/low levels | ~100 B | Yes (scalars only) |
| Zone | Peak history, zone levels | ~1-2 KB | Mostly (depends on zone count) |
| Fibonacci | Fib level outputs | ~200 B | Yes (fixed output set) |
| MarketStructure | Break history, pivot tracking | ~1-2 KB | Mostly |
| **RollingWindow** | `_data_buffer` (deque, **no maxlen**) | **Unbounded** | **NO** |
| DerivedZone | Parent zone references | ~100-200 B | Yes |

**Key concern**: `RollingWindow` uses `deque(maxlen=None)` — it grows by one entry per bar indefinitely. On a 7-day live run at 1m resolution: 10,080 entries × ~200 bytes = 2 MB. Not catastrophic, but a design flaw.

### 2.4 State Serialization

The engine serializes state to JSON for crash recovery:

```python
# EngineState → JSON
{
    "engine_id": "abc123",
    "play_id": "EMA_cross_BTC",
    "position": { "side": "LONG", "size_usdt": 500.0, ... },
    "equity_usdt": 10234.56,
    "incremental_state_json": "<serialized structures + indicator state>"
}
```

- **Format**: JSON (human-readable, not pickle)
- **Writes**: Atomic (tempfile → `os.replace()`)
- **Frequency**: Every `state_save_interval` bars (default: 100)
- **Typical size**: 5-100 KB depending on structure complexity
- **Location**: `data/runtime/state/{engine_id}.json`

---

## 3. Memory Growth Analysis

### 3.1 Bounded Components (Safe)

| Component | Bounding Mechanism | Max Size | Location |
|-----------|-------------------|----------|----------|
| Trade history | `deque(maxlen=10000)` | ~2 MB | `position_manager.py:147` |
| Recent trades (WS) | `deque(maxlen=100)` per symbol | ~20 KB/sym | `realtime_state.py:140` |
| Execution history | `deque(maxlen=500)` | ~100 KB | `realtime_state.py:145` |
| Open positions | dict, auto-cleanup on close | ~1 KB/pos | `realtime_state.py:143` |
| Open orders | dict, auto-cleanup on fill | ~1 KB/ord | `realtime_state.py:144` |
| Candle dedup set | Trimmed at 100 per TF | ~15 KB | `live_runner.py:201` |
| Indicator cache | Rolling window, max 500 bars | ~60 KB/TF | `live.py:64` |

### 3.2 Unbounded Components (Concerns)

#### A. `np.append()` in LiveIndicatorCache — GC Pressure

**File**: `src/engine/adapters/live.py`, lines 266-330

```python
# Every new candle triggers this:
self._open = np.append(self._open, candle.open)    # O(n) copy!
self._indicators[name] = np.append(self._indicators[name], inc_ind.value)

# Then trim:
if len(self._close) > self._buffer_size:
    self._open = self._open[trim_count:]             # Another O(n) copy!
```

**Problem**: `np.append()` creates a brand-new array and copies all elements. With a 500-element buffer and 10 indicators:
- Per candle: ~5,000 float copies + array allocations
- Per day (1m bars): 1,440 candles × 5,000 copies = 7.2M copies
- **GC pressure**: ~50 MB/day of temporary arrays created and destroyed
- Tracked as `ENG-BUG-015` in TODO.md

**Fix**: Replace with pre-allocated circular buffer (numpy array + head pointer), identical to the RingBuffer pattern already used by swing detectors.

#### B. Bar Buffers in RealtimeState — No maxlen

**File**: `src/data/realtime_state.py`, lines 177-180

```python
self._bar_buffers: dict[str, dict[str, dict[str, deque[BarRecord]]]] = {
    "live": defaultdict(lambda: defaultdict(deque)),   # No maxlen!
    "demo": defaultdict(lambda: defaultdict(deque)),   # No maxlen!
}
```

**Problem**: These deques grow by one entry per bar, per symbol, per TF, forever.
- 7 days × 1,440 bars/day × 3 TFs × 1 symbol × ~200 B/record = **~6 MB**
- 30 days: **~24 MB** per symbol
- Multiple symbols compound the growth

**Fix**: Add `maxlen` parameter matching the bar buffer size config (already defined in `get_bar_buffer_size()` — 500 for 1m, 200 for 15m, etc.).

#### C. Log Files — No Rotation

**File**: `src/utils/logger.py`

Log files are created daily (`bot_YYYYMMDD.log`) but never deleted or rotated:
- Observed: `bot_20260219.log` at **209 MB**
- 30 days: ~3 GB of logs
- 90 days: ~9 GB of logs
- Also: `errors_*.log`, `trades_*.log`, `events_*.jsonl` — all unbounded

**Fix**: Use `RotatingFileHandler` with 100 MB max per file, keep 7 files (700 MB cap total).

#### D. Callback Lists — Append-Only

**File**: `src/data/realtime_state.py`, lines 154-162, 283-311

```python
def on_kline_update(self, callback):
    with self._callback_lock:
        self._kline_callbacks.append(callback)  # Never removed
```

No `unregister_callback()` method exists. If callbacks are registered on each reconnect without cleanup, the list grows. **Low risk** if registration happens only at startup, but a design gap.

### 3.3 Memory Timeline (Single Live Instance)

```
Hour 0 (Startup):
  Engine state:           ~250 KB
  Live indicator cache:   ~195 KB (3 TFs × 65 KB)
  WebSocket state:        ~50 KB
  DuckDB (warmup read):   ~21 MB (freed after warmup)
  ──────────────────────────────
  TOTAL:                  ~22 MB (drops to ~500 KB after warmup)

Hour 1:
  + 60 candles processed
  + ~2 MB GC pressure from np.append
  + ~72 KB bar buffer growth
  Steady state:           ~600 KB resident

Day 1:
  + 1,440 candles processed
  + ~50 MB cumulative GC pressure (freed, but fragments heap)
  + ~1.7 MB bar buffer growth
  + ~100 MB log file growth
  Resident:               ~3 MB  |  Disk: ~100 MB logs

Day 7:
  + 10,080 candles processed
  + ~350 MB cumulative GC pressure
  + ~12 MB bar buffer growth (UNBOUNDED)
  + ~700 MB log growth
  Resident:               ~15 MB  |  Disk: ~700 MB logs

Day 30:
  + 43,200 candles processed
  + ~1.5 GB cumulative GC pressure
  + ~50 MB bar buffer growth (UNBOUNDED)
  + ~3 GB log growth
  Resident:               ~55 MB  |  Disk: ~3 GB logs

  ⚠️ Heap fragmentation likely; consider process restart
```

### 3.4 Backtest Memory (For Comparison)

Backtests have **zero growth concerns** — all data is pre-allocated:

```
FeedStore (3 TFs):        ~21 MB (fixed, immutable)
Engine state:             ~250 KB (bounded)
Indicator pre-compute:    ~2 MB (fixed arrays)
───────────────────────────
TOTAL:                    ~23 MB per backtest
```

Multiple backtests via ProcessPoolExecutor: each worker gets its own ~23 MB. With 4 workers: ~92 MB total. This is well within normal bounds.

---

## 4. Long-Run Stability

### 4.1 What Works for 24h+ Runs

| Feature | Mechanism | Status |
|---------|-----------|--------|
| Atomic state writes | tempfile → `os.replace()` | Solid |
| Bounded trade history | `deque(maxlen=10000)` | Solid |
| Position cleanup | dict.pop() on close | Solid |
| Daily loss reset | UTC midnight comparison | Solid (fixed in P16) |
| Position reconciliation | Every 5 minutes via REST | Solid |
| Cooldown system | 15s post-stop grace period | Solid |
| Instance cleanup on startup | Remove dead PIDs, expired cooldowns | Solid |

### 4.2 What Breaks on 7+ Day Runs

| Issue | Growth Rate | Impact at 30 Days | Severity |
|-------|------------|-------------------|----------|
| Log files (no rotation) | ~100 MB/day | 3 GB disk | Medium |
| Bar buffers (no maxlen) | ~1.7 MB/day | 50 MB RAM | Medium |
| np.append GC pressure | ~50 MB/day churned | Heap fragmentation | Low-Medium |
| Instance file accumulation | ~1 KB/restart | Hundreds of stale files | Low |
| RollingWindow deque | ~300 KB/day | 9 MB RAM | Low |

### 4.3 WebSocket Reconnection

The reconnection parameters are defined but not fully implemented:

```python
# Defined in LiveRunner config:
base_reconnect_delay: float = 1.0
max_reconnect_delay: float = 60.0
max_reconnect_attempts: int = 10
```

**Current behavior**: Only passive position reconciliation at 5-minute intervals. No active WebSocket reconnection with exponential backoff. If the WebSocket drops, the system relies on RealtimeBootstrap's internal reconnect (which does work), but the LiveRunner doesn't have its own backoff layer.

**Potential issue**: If WebSocket stays disconnected for >100 candle periods, the dedup set can't prevent duplicate processing on reconnect (set trimmed to 100 entries).

### 4.4 Crash Recovery Flow

```
Process Crash
  │
  ├── State file exists: data/runtime/state/{id}.json
  │     Contains: position, equity, pending orders, structure state
  │
  ├── Instance file exists: data/runtime/instances/{id}.json
  │     Contains: PID, play_id, symbol, mode
  │
  └── Journal file exists: data/journal/{id}.jsonl
        Contains: all trade events up to crash

Manual Restart
  │
  ├── EngineManager._read_disk_instances(clean_stale=True)
  │     Removes dead PIDs, expired cooldowns
  │
  ├── LiveRunner._sync_positions_on_startup()
  │     Queries exchange for current positions
  │     Compares with persisted state
  │
  └── Indicators/structures rebuilt from warmup data
        (Does NOT restore from state file — recomputes from candles)
```

**Gap**: No automatic restart. Requires manual process restart or external supervisor (systemd, supervisor, Docker restart policy).

### 4.5 Time-Based Edge Cases

| Scenario | Status | Notes |
|----------|--------|-------|
| Midnight UTC rollover | Fixed (P16) | All datetime.now() uses UTC |
| DST transitions | N/A | UTC-naive datetimes, no TZ awareness |
| Funding rate payments (8h) | Not simulated | Exchange handles live; backtest gap (H22) |
| Weekend gaps (crypto = 24/7) | N/A | No market closures for crypto |
| New Year / holidays | N/A | Crypto trades continuously |

---

## 5. Runtime Performance Profile

### 5.1 Backtest Performance

**Per-bar cost breakdown**:

| Operation | Complexity | Time | Notes |
|-----------|-----------|------|-------|
| Array access (FeedStore) | O(1) | ~0.01 ms | Numpy indexing, cache-friendly |
| Indicator updates (44) | O(1) each | ~0.5-2 µs total | Incremental, no recompute |
| Structure updates | O(1) each | ~1-5 µs total | Ring buffers, incremental |
| Fill processing (TP/SL) | O(1) | ~0.1 ms | Position lookup + price comparison |
| Signal evaluation | O(r), r=5-10 | ~10-50 µs | Compiled DSL, no string parsing |
| **Per-bar total** | | **~0.1-0.5 ms** | |

**Throughput**: **2,000-10,000 bars/second** on WSL2 (varies by indicator count and structure complexity).

**Bottleneck**: DuckDB data loading (I/O), not computation. Once data is in FeedStore arrays, the engine flies.

### 5.2 Live Latency

**Signal-to-order timeline**:

```
Candle closes on exchange
  │ (~100-500ms WebSocket delivery)
  ▼
WebSocket callback → Queue.put_nowait()          ~0.1 ms
  │
  ▼
Dequeue + route to correct TF buffer             ~1-5 ms
  │
  ▼
Snapshot build (indicator array copies)           5-50 ms  ⚠️ BOTTLENECK
  │
  ▼
Rule evaluation (compiled DSL tree)               ~0.05 ms
  │
  ▼
Safety checks (risk, margin, drawdown)            ~1 ms
  │
  ▼
Order submission (Bybit REST API)                 50-100 ms (network)
  │
  ▼
TOTAL: ~60-200 ms signal-to-order
```

**The live latency bottleneck is snapshot building** (5-50 ms), not indicator computation or rule evaluation. This is because `_build_live_feed_store()` copies indicator arrays from the cache into a new FeedStore on every signal evaluation.

### 5.3 Validation Suite Performance

| Command | Time | Bottleneck |
|---------|------|------------|
| `validate quick` | ~2 min | G10 complexity ladder |
| `validate standard` | ~390s | G10 alone: ~317s |
| `validate full` | ~6 min | Parallel gates + timeouts |
| `validate real` | ~2 min | DuckDB real data loading |

### 5.4 Key Performance Insight

The system is **not CPU-bound for live trading**. At 1 candle per minute (1m exec TF), the engine uses <0.1% CPU. Even at 1-second candles, processing would take <10 ms per candle — well within budget. The constraint is exchange API latency and WebSocket delivery, not Python computation speed.

---

## 6. Is Python Still the Right Language?

### 6.1 The Short Answer

**Yes.** Python 3.12+ is the correct choice for TRADE. The reasoning:

### 6.2 Why Python Works

| Factor | Evidence | Weight |
|--------|----------|--------|
| **Ecosystem** | pybit (official Bybit SDK), DuckDB bindings, pandas, numpy, Rich, asyncio | Critical |
| **Development velocity** | 56K lines of well-typed Python; rapid iteration on strategies | Critical |
| **Live latency budget** | 60-200 ms signal-to-order; Python adds <10 ms | Sufficient |
| **Backtest speed** | 2K-10K bars/sec; validation suite runs in minutes | Sufficient |
| **Maintainability** | Single language, type hints throughout, clear architecture | High |
| **O(1) indicator design** | Eliminates the "Python is slow for loops" problem | Excellent |
| **GIL avoidance** | ProcessPoolExecutor for backtests, asyncio for live | Correct |

### 6.3 Why Alternatives Don't Justify a Rewrite

| Alternative | Gain | Cost | Verdict |
|-------------|------|------|---------|
| **Rust engine core** | 2-5x backtest speed | Months of rewrite; maintain two codebases; no pybit SDK | Not justified |
| **Go for WebSocket** | Lower connection overhead | Lose pybit SDK; no DuckDB bindings; new language for team | Not justified |
| **C++ with Python bindings** | Maximum per-bar speed | Extreme complexity; debugging difficulty; C++ type-safety tax | Not justified |
| **Julia** | Faster numeric computation | No exchange SDKs; immature ecosystem; startup overhead | Not justified |
| **Mojo** | Python syntax + native speed | Immature (2024 release); no ecosystem; production risk | Too early |

### 6.4 The Architecture Makes the Language Choice Work

The reason Python isn't a bottleneck is **architectural, not accidental**:

1. **O(1) incremental indicators** — No Python loops over 25K bars. Each indicator update is 2-5 float operations.
2. **Compiled DSL rules** — Rules are parsed at Play load time, not per-bar. Evaluation is method calls, not string parsing.
3. **Numpy for arrays** — FeedStore data is contiguous numpy arrays (C-level access). Python never iterates element-by-element.
4. **ProcessPoolExecutor** — Backtests run in separate processes, completely avoiding the GIL.
5. **Async for I/O** — Live trading is I/O-bound (waiting for candles, submitting orders). Python's asyncio handles this correctly.

### 6.5 When Python WOULD Become a Problem

| Scenario | Threshold | Current State | Distance |
|----------|-----------|---------------|----------|
| Sub-second trading (HFT) | <10 ms end-to-end | 60-200 ms | Far (not a goal) |
| 1000+ concurrent live plays | Memory per process | Single-digit plays | Far |
| Tick-by-tick processing | Millions of ticks/day | 1,440 bars/day (1m) | Not applicable |
| ML model inference per bar | GPU/CPU intensive | No ML in signal path | Not applicable |

**None of these scenarios are relevant to TRADE's architecture or roadmap.**

### 6.6 Hybrid Architecture: When to Consider

If performance becomes an issue in the future, the correct approach is **selective native extensions**, not a full rewrite:

```
Candidate for native extension:
  └── LiveIndicatorCache (np.append → Rust circular buffer)
      Cost: ~1 week
      Gain: Eliminate 50 MB/day GC pressure
      ROI: High (targeted fix for known issue)

NOT candidates for native extension:
  ├── PlayEngine (too complex, too much domain logic)
  ├── Signal evaluation (already fast enough)
  ├── Structure detection (already incremental)
  └── Exchange adapters (I/O-bound, not CPU-bound)
```

---

## 7. Improvements Before Advancing

These are concrete fixes to make **before** implementing sub-accounts or other major features. Ordered by impact.

### 7.1 Priority 1: Log Rotation (Disk Growth)

**Problem**: Log files grow ~100 MB/day with no rotation.
**Impact**: 3 GB/month disk consumption; fills up small VPS instances.
**Fix**: Replace `FileHandler` with `RotatingFileHandler` in `src/utils/logger.py`.

```python
# Current:
handler = logging.FileHandler(log_path)

# Fix:
handler = RotatingFileHandler(
    log_path,
    maxBytes=100_000_000,  # 100 MB per file
    backupCount=7,          # Keep 7 rotated files (700 MB cap)
)
```

**Effort**: ~30 minutes. **Risk**: Zero.

### 7.2 Priority 2: Bar Buffer Bounds (Memory Growth)

**Problem**: `realtime_state.py` bar buffers use `deque()` with no maxlen.
**Impact**: ~1.7 MB/day/symbol unbounded growth.
**Fix**: Use the existing `get_bar_buffer_size()` function to set maxlen.

```python
# Current:
self._bar_buffers = defaultdict(lambda: defaultdict(deque))

# Fix: Add maxlen when creating deques (in append_bar or init)
deque(maxlen=get_bar_buffer_size(timeframe))
```

**Effort**: ~1 hour. **Risk**: Low.

### 7.3 Priority 3: Replace np.append with Circular Buffer (GC Pressure)

**Problem**: `np.append()` copies entire array on every candle (O(n) per update).
**Impact**: ~50 MB/day GC churn; heap fragmentation over weeks.
**Fix**: Pre-allocate arrays and use head/tail pointers (same pattern as `RingBuffer` in swing detector).

```python
# Current (O(n) per update):
self._close = np.append(self._close, candle.close)
if len(self._close) > self._buffer_size:
    self._close = self._close[trim_count:]

# Fix (O(1) per update):
class CircularArray:
    def __init__(self, size: int):
        self._buf = np.full(size, np.nan, dtype=np.float64)
        self._head = 0
        self._count = 0
        self._size = size

    def push(self, value: float):
        self._buf[self._head] = value
        self._head = (self._head + 1) % self._size
        if self._count < self._size:
            self._count += 1
```

**Effort**: ~2-4 hours. **Risk**: Medium (must validate indicator values match).

### 7.4 Priority 4: Callback Unregistration (Reconnect Safety)

**Problem**: `RealtimeState.on_kline_update()` appends callbacks but never removes them.
**Impact**: Low (only if callbacks registered on reconnect). But a design gap.
**Fix**: Add `off_kline_update()` method; clear callbacks on reconnect.

**Effort**: ~1 hour. **Risk**: Low.

### 7.5 Priority 5: RollingWindow maxlen (Structure Memory)

**Problem**: `RollingWindow._data_buffer = deque(maxlen=None)`.
**Impact**: ~300 KB/day growth. Low severity but violates bounded-memory principle.
**Fix**: Set `maxlen=window_size` on the deque.

**Effort**: ~30 minutes. **Risk**: Low.

### 7.6 Priority 6: Instance File Cleanup (Operational Hygiene)

**Problem**: Instance files only cleaned on startup, not during operation.
**Impact**: Stale files accumulate between restarts.
**Fix**: Add periodic cleanup task (every hour) or cleanup on stop.

**Effort**: ~1 hour. **Risk**: Low.

### 7.7 Priority 7: Snapshot Caching in Live Mode (Latency)

**Problem**: `_build_live_feed_store()` copies all indicator arrays on every signal evaluation (5-50 ms).
**Impact**: 10-50% of signal-to-order latency.
**Fix**: Cache the FeedStore snapshot and invalidate only when new candles arrive.

**Effort**: ~4-8 hours. **Risk**: Medium (cache invalidation must be correct).

---

## 8. Recommendations

### 8.1 Immediate Actions (Do Now)

| # | Fix | Effort | Impact |
|---|-----|--------|--------|
| 1 | Log rotation | 30 min | Prevents disk exhaustion |
| 2 | Bar buffer maxlen | 1 hour | Prevents memory leak |
| 3 | np.append → circular buffer | 2-4 hours | Reduces GC pressure 50 MB/day |

**Total: ~5 hours of work eliminates all significant long-run stability concerns.**

### 8.2 Before Sub-Account Work

| # | Fix | Effort | Why Before Sub-Accounts |
|---|-----|--------|------------------------|
| 4 | Callback unregistration | 1 hour | Multiple accounts = multiple callbacks |
| 5 | Instance file cleanup | 1 hour | More instances = more stale files |
| 6 | Snapshot caching | 4-8 hours | Multiple live plays = higher latency budget |

### 8.3 Language Decision

**Stay with Python 3.12+.** No rewrite needed. The architecture (O(1) indicators, compiled DSL, numpy arrays, ProcessPoolExecutor, asyncio) makes Python performant enough for all current and planned use cases.

If a native extension ever becomes needed, the **only candidate** is the LiveIndicatorCache circular buffer — and even that is a "nice to have," not a necessity.

### 8.4 Long-Run Monitoring

For production live trading, add lightweight monitoring:

```python
# Periodic health check (every hour):
- Resident memory (RSS) — alert if growing >10 MB/hour
- Log file sizes — alert if >500 MB total
- Instance file count — alert if >50 stale files
- Bar buffer sizes — alert if any deque > 10,000 entries
- GC stats (gc.get_stats()) — monitor collection frequency
```

### 8.5 Process Lifecycle

For truly long-running live trading (weeks/months), consider:

1. **Graceful daily restart**: Stop engine at a quiet time (low volume), restart fresh. State recovery ensures no position loss.
2. **External supervisor**: systemd or Docker with restart policy. The 15-second cooldown system already supports this.
3. **Rotating journal files**: Split `events.jsonl` by date (similar to log rotation).

---

## Appendix A: Data Structure Inventory

| Data Structure | File | Type | Bounded | Max Size |
|---------------|------|------|---------|----------|
| `_trades` | position_manager.py:147 | deque | Yes (10000) | ~2 MB |
| `_recent_trades` | realtime_state.py:140 | deque | Yes (100/sym) | ~20 KB |
| `_executions` | realtime_state.py:145 | deque | Yes (500) | ~100 KB |
| `_positions` | realtime_state.py:143 | dict | Yes (cleanup) | ~1 KB |
| `_orders` | realtime_state.py:144 | dict | Yes (cleanup) | ~1 KB |
| `_bar_buffers` | realtime_state.py:177 | deque | **No** | **Unbounded** |
| `_kline_callbacks` | realtime_state.py:154 | list | **No** | **Unbounded** |
| `_seen_candles` | live_runner.py:201 | set | Yes (100/TF) | ~15 KB |
| `_indicators` | live.py:260 | np.ndarray | Yes (500 bars) | ~40 KB/TF |
| `_data_buffer` (RollingWindow) | rolling_window.py | deque | **No** | **Unbounded** |
| `_buffer` (RingBuffer) | ring_buffer.py | np.ndarray | Yes (fixed) | ~88 B |

## Appendix B: Performance Benchmarks (Expected)

| Metric | Value | Notes |
|--------|-------|-------|
| Bars/second (backtest) | 2,000-10,000 | WSL2; varies by indicator count |
| Signal-to-order (live) | 60-200 ms | Network-bound |
| Snapshot build (live) | 5-50 ms | Array copy bottleneck |
| Indicator update (per bar) | 0.5-2 µs | O(1) incremental |
| Structure update (per bar) | 1-5 µs | O(1) incremental |
| Rule evaluation (per bar) | 10-50 µs | Compiled DSL |
| Memory per live instance | ~500 KB steady | After warmup data freed |
| Memory per backtest | ~23 MB | Fixed (FeedStore arrays) |
| GC pressure (live, np.append) | ~50 MB/day | Fixable with circular buffer |

## Appendix C: File Reference

| File | Lines | Role in State Management |
|------|-------|-------------------------|
| `src/engine/adapters/state.py` | ~250 | FileStateStore, EngineState |
| `src/engine/adapters/live.py` | ~2100 | LiveIndicatorCache, LiveDataProvider |
| `src/engine/play_engine.py` | ~1100 | Engine state machine, snapshot building |
| `src/engine/runners/live_runner.py` | ~700 | Live loop, reconnection, safety |
| `src/data/realtime_state.py` | ~700 | WebSocket event cache, bar buffers |
| `src/data/realtime_bootstrap.py` | ~400 | WebSocket subscription manager |
| `src/core/position_manager.py` | ~400 | Trade history, daily stats |
| `src/core/safety.py` | ~250 | PanicState, DailyLossTracker |
| `src/indicators/incremental/base.py` | ~40 | Indicator base class (O(1) contract) |
| `src/structures/detectors/` | ~2000 | Structure detectors (ring buffers) |
| `src/backtest/runtime/feed_store.py` | ~500 | FeedStore (immutable arrays) |
| `src/utils/logger.py` | ~500 | Logging (no rotation) |
| `config/defaults.yml` | 104 | System defaults |
