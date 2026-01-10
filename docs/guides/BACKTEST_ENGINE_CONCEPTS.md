# Backtest Engine Conceptual Guide

A conceptual guide for developers new to the TRADE backtest engine. This document explains how the engine works under the hood and why it's designed this way.

---

## Table of Contents

1. [Introduction: What is a Backtest?](#introduction-what-is-a-backtest)
2. [The Golden Rule: No Lookahead](#the-golden-rule-no-lookahead)
3. [The Hot Loop: Where Performance Matters](#the-hot-loop-where-performance-matters)
4. [Data Caching Architecture](#data-caching-architecture)
5. [Multi-Timeframe Architecture](#multi-timeframe-architecture)
6. [Window Operators: Temporal Conditions](#window-operators-temporal-conditions)
7. [Complete Flow Diagram](#complete-flow-diagram)
8. [Common Pitfalls](#common-pitfalls)

---

## Introduction: What is a Backtest?

Think of a backtest as a **time machine for your trading strategy**. You're simulating what would have happened if you had traded your strategy on historical market data.

```
Today (2026-01-10)
        ↑
        │  [Time Machine]
        │
    ┌───┴───────────────────────────────────┐
    │  Your strategy runs on data from:     │
    │  2024-01-01 to 2025-12-31            │
    │                                        │
    │  Bar by bar, the engine:              │
    │  1. Shows you market data up to time T│
    │  2. Asks "what do you want to do?"    │
    │  3. Simulates the trade execution     │
    │  4. Moves to time T+1                 │
    │  5. Repeats...                        │
    └────────────────────────────────────────┘
```

The engine **replays history** one bar at a time, giving your strategy only the information that would have been available at that moment. This is critical for realistic simulation.

<details>
<summary>Test Your Understanding</summary>

**Q1:** If I'm backtesting from 2024-01-01 to 2025-12-31, can my strategy on bar 100 see what happens on bar 101?

**A1:** No - that would be lookahead. The strategy can only see bars 0-100. Bar 101 is "in the future" from the perspective of bar 100.

**Q2:** Why does it matter if we peek at future bars? The past data isn't changing.

**A2:** Because your strategy won't have that future information in live trading. If your backtest uses future data (even accidentally), you'll get amazing backtest results but terrible live results. This is called "curve fitting" or "overfitting."

</details>

---

## The Golden Rule: No Lookahead

**Lookahead** is when your strategy accidentally uses information from the future. This is the #1 way to create misleading backtests.

### Examples of Lookahead (What NOT to Do)

```python
# ❌ WRONG: Looking at tomorrow's close
if bar[i].close < bar[i+1].close:  # i+1 is the future!
    buy()

# ❌ WRONG: Using today's data in an indicator that updates at bar close
# If the bar isn't closed yet, you don't have the final values
def my_indicator(data):
    return data.rolling(window=20).mean()  # Uses partial bar data

# ❌ WRONG: Computing indicators inside the loop on growing data
for bar in bars:
    ema = compute_ema(bars[:current_index])  # Recomputes entire EMA each bar!
```

### How TRADE Prevents Lookahead

The TRADE engine has **runtime assertions** that enforce the golden rule:

```python
# From engine.py - this assertion runs on EVERY bar
assert snapshot.ts_close == bar.ts_close, "Lookahead detected!"
```

If your snapshot timestamp doesn't match the bar timestamp, the engine **crashes immediately**. This fail-fast design prevents subtle lookahead bugs.

Additionally:
- **Indicators are precomputed** BEFORE the loop (vectorized numpy/pandas)
- **Strategy is invoked ONLY at bar close** (never mid-bar)
- **HTF/MTF features forward-fill** from last CLOSED bar only

<details>
<summary>Test Your Understanding</summary>

**Q1:** Can I look backward at previous bars (e.g., bar[i-1], bar[i-2])?

**A1:** Yes! Looking backward is fine - that's historical data your strategy would have known. The engine provides helper methods like `prev_close(lookback=1)` for this.

**Q2:** Why are indicators computed outside the hot loop instead of inside?

**A2:** Two reasons:
1. **Performance**: Computing EMA(50) from scratch at every bar is O(n²) complexity. Precomputing once is O(n).
2. **Lookahead Prevention**: Precomputed indicators use only closed bars, ensuring no partial bar data leaks in.

</details>

---

## The Hot Loop: Where Performance Matters

The "hot loop" is the bar-by-bar iteration at the core of the backtest. It's called "hot" because it runs thousands of times per backtest and performance matters.

### The Two Phases: Warmup vs Trading

```
Timeline:
├─────────────────┬───────────────────────────────────────────┤
│   Warmup Phase  │          Trading Phase                   │
├─────────────────┼───────────────────────────────────────────┤
│ Bars 0-199      │ Bars 200-10,000                          │
│                 │                                           │
│ Purpose:        │ Purpose:                                  │
│ - Fill indicator│ - Evaluate strategy                       │
│   buffers (EMA, │ - Execute trades                          │
│   ATR need      │ - Track equity                            │
│   history)      │ - Check stop conditions                   │
│ - Build state   │                                           │
│   structures    │                                           │
│                 │                                           │
│ NO TRADING      │ FULL EVALUATION                           │
└─────────────────┴───────────────────────────────────────────┘
```

**Warmup Phase** (bars 0 to sim_start_idx):
- Updates indicators and structures
- Fills history windows (for `holds_for`, `occurred_within`)
- NO strategy evaluation, NO trades
- Ensures all indicators have valid values before trading starts

**Trading Phase** (bars sim_start_idx to end):
- Full strategy evaluation at each bar close
- Order execution simulation
- Stop condition checking (TP/SL, equity drawdown, etc.)
- Equity curve tracking

### Steps Within Each Bar (Trading Phase)

```
For each bar in trading phase:

1. BUILD BAR
   ├─ Extract OHLCV from FeedStore arrays (O(1) lookup)
   └─ Create CanonicalBar object

2. UPDATE STRUCTURES
   ├─ Update incremental detectors (swing, trend, zones)
   └─ Detect transitions (Layer 2 rationalization)

3. UPDATE MTF INDICES
   ├─ Check if HTF bar closed → update htf_idx
   ├─ Check if MTF bar closed → update mtf_idx
   └─ Forward-fill semantics: indices unchanged until TF closes

4. ACCUMULATE 1M QUOTES
   ├─ Collect 1m bars between last exec close and current
   └─ Build rollup aggregates (min, max, volume, etc.)

5. BUILD SNAPSHOT
   ├─ Create RuntimeSnapshotView (O(1) - just indices!)
   ├─ Wire in FeedStore references
   └─ No data copying

6. EVALUATE STRATEGY (1m sub-loop)
   ├─ For each 1m bar within this exec bar:
   │  ├─ Build snapshot with 1m mark/last prices
   │  ├─ Evaluate strategy conditions
   │  └─ If signal → break (max 1 entry per exec bar)
   └─ Use last evaluated snapshot for consistency

7. PROCESS SIGNAL
   ├─ Apply risk sizing (size_usdt calculation)
   ├─ Check risk policy gates
   └─ Submit order to simulated exchange

8. STEP EXCHANGE (1m granularity)
   ├─ Check TP/SL at each 1m bar (intrabar precision)
   ├─ Update unrealized PnL (mark-to-market)
   ├─ Process funding settlements (8h intervals)
   └─ Detect liquidations

9. RECORD EQUITY
   ├─ Snapshot equity and account state
   └─ Append to equity curve
```

### Why Pre-Compute Indicators?

**The YouTube Quant Trap**: Many tutorial backtests do this:

```python
# ❌ WRONG: O(n²) disaster
for i in range(len(bars)):
    ema_9 = bars[:i].ewm(span=9).mean()[-1]   # Recomputes from scratch!
    ema_21 = bars[:i].ewm(span=21).mean()[-1] # Recomputes from scratch!

    if ema_9 > ema_21:
        buy()
```

**Complexity**: O(n²) - for 10,000 bars, this is 100 million operations.

**TRADE's approach**:

```python
# ✅ CORRECT: O(n) precomputation
# BEFORE the hot loop:
df['ema_9'] = df['close'].ewm(span=9).mean()   # Vectorized: ~10,000 ops
df['ema_21'] = df['close'].ewm(span=21).mean() # Vectorized: ~10,000 ops

# INSIDE the hot loop:
for i in range(len(bars)):
    ema_9 = feed.indicators['ema_9'][i]   # O(1) array lookup
    ema_21 = feed.indicators['ema_21'][i] # O(1) array lookup

    if ema_9 > ema_21:
        buy()
```

**Complexity**: O(n) - 10,000 bars = 20,000 operations total (10,000x faster!).

<details>
<summary>Test Your Understanding</summary>

**Q1:** Why do we need a warmup phase? Can't we just start trading immediately?

**A1:** Indicators need history to produce valid values. EMA(50) needs at least 50 bars of data. If you start trading at bar 10, your EMA(50) will be NaN or invalid, leading to bad signals.

**Q2:** What's the difference between O(n) and O(n²) complexity in practice?

**A2:** For 10,000 bars:
- O(n): ~10,000 operations = milliseconds
- O(n²): ~100 million operations = minutes or hours

The difference becomes dramatic as data size grows. At 100,000 bars, O(n²) is literally 10,000x slower.

**Q3:** When the engine evaluates my strategy at bar 500, can I ask for the EMA value at bar 499 or 498?

**A3:** Yes! The snapshot provides methods like `prev_indicator('ema_9', lookback=1)` that use O(1) array lookups into the precomputed indicator arrays. Looking backward is free and encouraged.

</details>

---

## Data Caching Architecture

The engine uses a **two-layer caching architecture** for O(1) data access in the hot loop. Think of it like a filing cabinet with an efficient index system.

### Layer 1: FeedStore (The Filing Cabinet)

**FeedStore** is an immutable container of precomputed numpy arrays. It's built ONCE before the hot loop starts.

```
FeedStore Structure:
┌──────────────────────────────────────────────┐
│ Symbol: BTCUSDT                              │
│ Timeframe: 15m                               │
│ Length: 10,000 bars                          │
├──────────────────────────────────────────────┤
│ OHLCV Arrays (float64):                      │
│  ├─ ts_open[10000]    (datetime64)          │
│  ├─ ts_close[10000]   (datetime64)          │
│  ├─ open[10000]       │                      │
│  ├─ high[10000]       │ All precomputed     │
│  ├─ low[10000]        │ numpy arrays        │
│  ├─ close[10000]      │ O(1) access         │
│  └─ volume[10000]     │                      │
├──────────────────────────────────────────────┤
│ Indicator Arrays (float32 for efficiency):  │
│  ├─ indicators['ema_9'][10000]              │
│  ├─ indicators['ema_21'][10000]             │
│  ├─ indicators['rsi_14'][10000]             │
│  ├─ indicators['atr_14'][10000]             │
│  └─ indicators['bbands_20_upper'][10000]    │
├──────────────────────────────────────────────┤
│ O(1) Lookup Maps:                            │
│  ├─ ts_close_ms_to_idx: {timestamp → index} │
│  └─ close_ts_set: {set of close timestamps} │
├──────────────────────────────────────────────┤
│ Market Data (optional):                      │
│  ├─ funding_rate[10000]                     │
│  ├─ open_interest[10000]                    │
│  └─ funding_settlement_times: {set}         │
└──────────────────────────────────────────────┘
```

**Key Properties**:
- **Immutable**: Once built, never modified
- **Contiguous memory**: Numpy arrays for cache efficiency
- **Type optimized**: float32 for indicators (50% memory vs float64)
- **Zero allocation in hot loop**: All arrays pre-allocated

**File**: `src/backtest/runtime/feed_store.py`

### Layer 2: RuntimeSnapshotView (The Finger Pointing)

**RuntimeSnapshotView** is a **lightweight view** created at every bar. It doesn't copy data - it just stores indices that point into the FeedStore arrays.

```
RuntimeSnapshotView (created every bar):
┌──────────────────────────────────────────────┐
│ exec_idx: 5000          ← Just an integer!   │
│ exec_ctx: TFContext                          │
│   ├─ feed: → FeedStore (reference)          │
│   └─ current_idx: 5000                       │
│                                               │
│ htf_idx: 333            ← Forward-filled     │
│ htf_ctx: TFContext                           │
│   ├─ feed: → HTF_FeedStore (reference)      │
│   └─ current_idx: 333                        │
│                                               │
│ mtf_idx: 1000           ← Forward-filled     │
│ mtf_ctx: TFContext                           │
│   ├─ feed: → MTF_FeedStore (reference)      │
│   └─ current_idx: 1000                       │
└──────────────────────────────────────────────┘

Memory footprint: ~200 bytes (just indices + refs)
Comparison: A DataFrame copy would be ~800KB+ per bar!
```

**When you access data**:

```python
# Inside your strategy:
ema_9 = snapshot.indicator('ema_9')

# What actually happens (O(1)):
value = exec_ctx.feed.indicators['ema_9'][exec_ctx.current_idx]
#         └─────────────────┬───────────────┘  └────────┬────┘
#              FeedStore array reference         Array index
#              (already in memory)                (integer)
```

No DataFrame operations, no row scanning, no memory allocation. Just array indexing.

**File**: `src/backtest/runtime/snapshot_view.py`

### Why This Matters: Performance Contract

```
Performance Guarantees:
┌─────────────────────────────────────────────────────┐
│ Operation              │ Complexity │ Time (approx) │
├────────────────────────┼────────────┼───────────────┤
│ Create snapshot        │ O(1)       │ <1 μs         │
│ Access OHLCV field     │ O(1)       │ <100 ns       │
│ Access indicator       │ O(1)       │ <100 ns       │
│ Access HTF indicator   │ O(1)       │ <100 ns       │
│ Lookup prev value      │ O(1)       │ <100 ns       │
│                                                      │
│ NEVER in hot loop:                                  │
│ ❌ df.iloc[i]         │ O(n)       │ milliseconds  │
│ ❌ df.loc[ts]         │ O(log n)   │ microseconds  │
│ ❌ pd.Series.rolling  │ O(n)       │ milliseconds  │
└─────────────────────────────────────────────────────┘
```

For a 10,000 bar backtest:
- **TRADE engine**: Completes in seconds
- **Naive pandas loop**: Takes minutes to hours

<details>
<summary>Test Your Understanding</summary>

**Q1:** If FeedStore contains 10,000 bars of data, how much memory does creating a snapshot allocate?

**A1:** Almost nothing (~200 bytes). The snapshot just stores indices (integers) and references (pointers). It doesn't copy any of the FeedStore data.

**Q2:** Why use float32 for indicators instead of float64?

**A2:** Price precision. For indicators, 6-7 significant figures (float32) is plenty. For prices (OHLCV), we use float64 to preserve exchange precision. This saves 50% memory with no meaningful loss of accuracy.

**Q3:** What happens if I modify an indicator value through the snapshot?

**A3:** You can't - FeedStore is immutable and the snapshot only provides read access. This is by design to prevent bugs from accidental data corruption.

</details>

---

## Multi-Timeframe Architecture

Trading strategies often combine multiple timeframes: "trade the 15m trend but use 1h structure for bias."

### Timeframe Role Definitions

The engine uses a three-level hierarchy:

```
Timeframe Hierarchy (example: exec=15m):
┌───────────────────────────────────────────────────┐
│                                                    │
│  HTF (High Timeframe)      MTF (Mid Timeframe)   │
│  ↓                         ↓                      │
│  4h structure/trend        1h swing context       │
│         ↘                       ↓                 │
│           ↘                     ↓                 │
│             ↘               ┌───┴───┐            │
│               ↘             │       │            │
│                 ↘           │  15m  │ ← exec TF  │
│                   ↘         │ (LTF) │            │
│                     ↘       │       │            │
│                       ↘     └───┬───┘            │
│                         ↘       ↓                │
│                           ↘   1m ticker          │
│                             ↘   ↓                │
│                               ↘ Aggregated       │
│                                 into exec bar    │
└───────────────────────────────────────────────────┘
```

**Role Definitions**:

| Role | Meaning | Typical Values | Purpose |
|------|---------|----------------|---------|
| **exec** (LTF) | Execution timeframe | 1m, 3m, 5m, 15m | Bar-by-bar decision evaluation. Engine steps at this rate. |
| **MTF** | Mid timeframe | 30m, 1h, 2h, 4h | Trade bias, intermediate structure |
| **HTF** | High timeframe | 4h, 6h, 12h, D | Major trend, higher-level context |

**Hierarchy rule**: `HTF >= MTF >= exec` (in minutes). This is enforced at config load time.

### The Forward-Fill Principle

**Critical concept**: Any timeframe slower than exec **forward-fills its values** until its bar closes.

#### Visual Timeline

```
Example: exec=15m, HTF=1h

Time:    09:00   09:15   09:30   09:45   10:00   10:15   10:30   10:45   11:00
         │       │       │       │       │       │       │       │       │
exec:    └──1────┴──2────┴──3────┴──4────┴──5────┴──6────┴──7────┴──8────┴──→
         │       │       │       │       │       │       │       │       │
HTF:     └───────────────────── HTF Bar 0 ──────┴──────────── HTF Bar 1 ─────┴→
         close                              close                         close

exec_idx:  1       2       3       4       5       6       7       8
htf_idx:   0       0       0       0       1       1       1       1
           └───────────────────┘           └───────────────────┘
           HTF values unchanged            HTF values updated at 10:00,
           (forward-filled)                then unchanged until 11:00
```

**What this means**:

At exec bar 2 (09:15):
```python
snapshot.exec_ctx.close  # 09:15 close price ← Current exec bar
snapshot.htf_ctx.close   # 09:00 close price ← Last CLOSED 1h bar
snapshot.htf_indicator('ema_50')  # EMA from 09:00 bar ← Forward-filled
```

At exec bar 5 (10:00):
```python
snapshot.exec_ctx.close  # 10:00 close price ← Current exec bar
snapshot.htf_ctx.close   # 10:00 close price ← HTF bar just closed!
snapshot.htf_indicator('ema_50')  # EMA from 10:00 bar ← Just updated
```

At exec bar 6 (10:15):
```python
snapshot.exec_ctx.close  # 10:15 close price ← Current exec bar
snapshot.htf_ctx.close   # 10:00 close price ← Forward-filled again
snapshot.htf_indicator('ema_50')  # EMA from 10:00 bar ← Unchanged
```

### Why Forward-Fill?

**Purpose**: No lookahead. HTF values reflect the last CLOSED bar only, never partial/forming bars.

**Example of what NOT to do**:

```
❌ WRONG: Using partial HTF bar data

At 09:30 (halfway through 1h bar):
- 09:00-09:30 has closed (30 minutes)
- 09:30-10:00 hasn't happened yet (30 minutes in the future)

If you computed EMA using the partial bar:
- High so far: $65,000
- Low so far: $64,500
- Close (when bar finishes): $64,000 ← You don't know this yet!

Using partial bar = lookahead.
```

**✅ CORRECT: Forward-fill from last closed bar**:

```
At 09:30 (halfway through 1h bar):
- Use EMA from 09:00 bar (last CLOSED bar)
- This is conservative but honest
- Matches TradingView "lookahead off" mode
```

### Update Behavior by TF Role

| TF Role | Relation to Exec | Behavior |
|---------|------------------|----------|
| **1m ticker** | Faster | Aggregated into rollups (max/min/range per exec bar) |
| **exec** | Reference | Updates every bar (no forward-fill) |
| **MTF** | Slower | Forward-fill until MTF bar closes |
| **HTF** | Slower | Forward-fill until HTF bar closes |

### How Forward-Fill Works Internally

The engine maintains **context indices** for each timeframe:

```python
# At each exec bar:
exec_idx = 5000          # Always current exec bar

# HTF index - only changes when HTF bar closes
if exec_bar.ts_close in htf_feed.close_ts_set:
    htf_idx += 1  # HTF bar just closed - advance
else:
    htf_idx = htf_idx  # HTF bar still open - keep same index

# MTF index - only changes when MTF bar closes
if exec_bar.ts_close in mtf_feed.close_ts_set:
    mtf_idx += 1  # MTF bar just closed - advance
else:
    mtf_idx = mtf_idx  # MTF bar still open - keep same index
```

**Detection is data-driven**, not modulo-based. The engine pre-builds a set of close timestamps for each TF, then checks membership (O(1) lookup).

**File**: `src/backtest/runtime/cache.py` (TimeframeCache)

<details>
<summary>Test Your Understanding</summary>

**Q1:** I'm trading on 5m bars but want to use 15m EMA for trend. What will `snapshot.mtf_indicator('ema_20')` return at 10:07 (middle of the 10:00-10:15 bar)?

**A1:** The EMA value from the 10:00 bar (last closed 15m bar). The 10:00-10:15 bar hasn't closed yet, so the 10:00 value is forward-filled.

**Q2:** Why not just compute the 15m EMA using data up to the current 5m bar?

**A2:** That would be lookahead. If you're at 10:07, you're using data from 10:00-10:07 (7 minutes into the 15m bar). The final 10:00-10:15 close could be very different from the current mid-bar value. You won't have the complete 15m bar data until 10:15.

**Q3:** Does forward-fill apply to structures (swing highs, zones) too?

**A3:** Yes! All HTF/MTF data forward-fills: indicators, structures, everything. The principle is universal: only use last CLOSED bar data.

**Q4:** How do I know when an HTF bar closes in my strategy?

**A4:** You don't need to! The engine handles forward-fill automatically. Just access `snapshot.htf_indicator('ema_50')` and it will always give you the correct forward-filled value.

</details>

---

## Window Operators: Temporal Conditions

Window operators let you express temporal logic: "buy if RSI was below 30 for at least 3 bars" or "sell if price crossed above the zone in the last 5 bars."

### Three Core Operators

| Operator | Purpose | Example |
|----------|---------|---------|
| **holds_for** | Condition held continuously for N bars | RSI < 30 for 5 bars |
| **occurred_within** | Condition true at least once in last N bars | Price touched zone in last 10 bars |
| **count_true** | Count how many times condition was true | True at least 3 times in last 20 bars |

### How They Work: Looking Backward

Window operators evaluate a condition at multiple historical bars using **offset lookups**:

```python
# Conceptual implementation of holds_for:

def holds_for(expr, bars, snapshot):
    """Check if expr was true for last N bars."""
    for offset in range(bars):
        # Get snapshot at (current bar - offset)
        historical_snapshot = snapshot.with_offset(offset)

        # Evaluate condition at that historical bar
        result = evaluate(expr, historical_snapshot)

        if not result:
            return False  # Condition broke - failed

    return True  # Condition held for all N bars
```

**Key insight**: Window operators don't store history - they walk backward through the precomputed FeedStore arrays using offsets.

```
Example: holds_for(rsi < 30, bars=3) at bar 1000

Check bar 1000: rsi[1000] < 30?  → True
Check bar  999: rsi[999]  < 30?  → True
Check bar  998: rsi[998]  < 30?  → True

All three checks pass → holds_for returns True
```

### The anchor_tf Parameter

Window operators default to **1m granularity** (since strategies evaluate every 1m within an exec bar).

Use `anchor_tf` to scale the window to a coarser timeframe:

```yaml
# Without anchor_tf: 3 bars = 3 minutes (1m granularity)
holds_for:
  expr: {feature_id: rsi_14, op: lt, value: 30}
  bars: 3

# With anchor_tf: 3 bars in 15m TF = 45 minutes
holds_for:
  expr: {feature_id: rsi_14, op: lt, value: 30}
  bars: 3
  anchor_tf: "15m"  # Scales bars: 3 * 15m = 45m

# With HTF anchor: 3 bars in 1h TF = 180 minutes
holds_for:
  expr: {feature_id: rsi_14, op: lt, value: 30}
  bars: 3
  anchor_tf: "1h"  # Scales bars: 3 * 1h = 180m
```

**Why it matters**: Allows you to express "3 consecutive 15m bars" instead of "45 consecutive 1m bars" - much more intuitive.

### Duration-Based Windows

Alternative syntax using time durations instead of bar counts:

```yaml
# Bar-based (depends on bar size)
holds_for:
  expr: {...}
  bars: 12
  anchor_tf: "5m"  # = 60 minutes

# Duration-based (explicit time)
holds_for_duration:
  expr: {...}
  duration: "60m"  # Exactly 60 minutes, regardless of bar size
```

Supported formats: `30m`, `2h`, `1d` (max 24h ceiling).

**When to use which**:
- Use **bars** for "N consecutive candles" logic (common in TA)
- Use **duration** for strict time-based conditions (e.g., "held for 2 hours")

<details>
<summary>Test Your Understanding</summary>

**Q1:** What's the difference between `holds_for` and `occurred_within`?

**A1:**
- `holds_for`: Condition must be true for ALL N bars (continuous streak)
- `occurred_within`: Condition must be true at LEAST ONCE in last N bars (any bar)

Example: If RSI was [25, 35, 28] over the last 3 bars:
- `holds_for(rsi < 30, 3)` → False (bar 2 broke the streak with 35)
- `occurred_within(rsi < 30, 3)` → True (bars 1 and 3 satisfied it)

**Q2:** If I use `holds_for` with `bars=5` and no `anchor_tf`, what timeframe is it checking?

**A2:** 1m granularity (default). It checks the last 5 minutes, evaluating the condition at each 1m bar within the current exec bar.

**Q3:** Can I use `occurred_within` with structure fields like zone state?

**A3:** Yes! Window operators work with any condition expression:
```yaml
occurred_within:
  expr: {feature_id: demand_zone, field: state, op: eq, value: "ACTIVE"}
  bars: 10
  anchor_tf: "5m"
```
Checks if the zone was active in any of the last 10 5m bars.

**Q4:** What happens if I request `holds_for` with `bars=100` but I'm only 50 bars into the backtest?

**A4:** The window is clamped to available history. If you're at bar 50, it checks bars 0-50 (51 bars total) instead of failing. The condition must hold for all available bars.

</details>

---

## Complete Flow Diagram

This ASCII diagram shows the complete backtest execution flow from configuration to results.

```
                    BACKTEST ENGINE FLOW
                    ====================

┌─────────────────────────────────────────────────────────────┐
│                  PHASE 1: INITIALIZATION                    │
└─────────────────────────────────────────────────────────────┘
                            │
    ┌───────────────────────┴────────────────────────┐
    │  Load Play Config (YAML)                       │
    │  ├─ Symbol, timeframe, window                  │
    │  ├─ Features (indicators + structures)         │
    │  ├─ Actions (entry/exit rules)                 │
    │  └─ Risk profile (sizing, fees, slippage)      │
    └────────────────────┬───────────────────────────┘
                         │
    ┌────────────────────┴────────────────────────────┐
    │  Create BacktestEngine                          │
    │  ├─ Validate config (USDT pair, isolated mode)  │
    │  ├─ Initialize SimulatedExchange                │
    │  ├─ Create RiskManager                          │
    │  └─ Setup multi-TF mapping (exec/MTF/HTF)       │
    └────────────────────┬────────────────────────────┘
                         │
┌─────────────────────────────────────────────────────────────┐
│                  PHASE 2: DATA PREPARATION                  │
└─────────────────────────────────────────────────────────────┘
                         │
    ┌────────────────────┴────────────────────────────┐
    │  Load OHLCV from DuckDB                         │
    │  ├─ Query window range + warmup period          │
    │  ├─ Load exec TF, MTF, HTF                      │
    │  ├─ Load 1m data (for mark/last price)          │
    │  └─ Load funding rates + open interest          │
    └────────────────────┬────────────────────────────┘
                         │
    ┌────────────────────┴────────────────────────────┐
    │  Compute Indicators (VECTORIZED)                │
    │  ├─ Apply FeatureSpecs to each TF DataFrame     │
    │  ├─ EMA, RSI, ATR, Bollinger Bands, etc.        │
    │  ├─ Validate no NaN in warmup period            │
    │  └─ Find first bar with all valid indicators    │
    └────────────────────┬────────────────────────────┘
                         │
    ┌────────────────────┴────────────────────────────┐
    │  Build FeedStores (IMMUTABLE ARRAYS)            │
    │  ├─ Convert DataFrames → numpy arrays           │
    │  ├─ Build ts_close_ms_to_idx maps (O(1) lookup) │
    │  ├─ Create exec_feed, htf_feed, mtf_feed        │
    │  └─ Build quote_feed (1m prices)                │
    └────────────────────┬────────────────────────────┘
                         │
    ┌────────────────────┴────────────────────────────┐
    │  Initialize Incremental State                   │
    │  ├─ Create structure detectors (swing, trend)   │
    │  ├─ Setup derived zones (Fibonacci levels)      │
    │  └─ Build StateRationalizer (Layer 2)           │
    └────────────────────┬────────────────────────────┘
                         │
┌─────────────────────────────────────────────────────────────┐
│                   PHASE 3: MAIN BAR LOOP                    │
└─────────────────────────────────────────────────────────────┘
                         │
         ┌───────────────┴──────────────┐
         │   FOR EACH BAR (i = 0..N):   │
         └───────────────┬──────────────┘
                         │
         ┌───────────────┴──────────────────────────────┐
         │  3.1: BUILD BAR                              │
         │  ├─ Extract OHLCV from exec_feed[i]          │
         │  └─ Create CanonicalBar(ts_close, OHLCV)     │
         └───────────────┬──────────────────────────────┘
                         │
    ┌────────────────────┴────────────────────────┐
    │  IS THIS A WARMUP BAR?                      │
    │  (i < sim_start_idx)                        │
    └────────┬──────────────────────┬─────────────┘
             │ YES                  │ NO
             │                      │
    ┌────────┴────────┐    ┌───────┴──────────────────────────┐
    │  WARMUP MODE    │    │  TRADING MODE                    │
    │  ├─ Update      │    │  ├─ All warmup steps             │
    │  │  structures  │    │  ├─ PLUS:                        │
    │  ├─ Fill        │    │  │  ├─ Evaluate strategy         │
    │  │  history     │    │  │  ├─ Process signals           │
    │  │  windows     │    │  │  ├─ Execute trades            │
    │  └─ NO TRADING  │    │  │  ├─ Check stops (TP/SL)       │
    │                 │    │  │  └─ Track equity curve        │
    └────────┬────────┘    └───────┬──────────────────────────┘
             │                     │
             └──────┬──────────────┘
                    │
         ┌──────────┴─────────────────────────────────┐
         │  3.2: UPDATE INCREMENTAL STRUCTURES        │
         │  ├─ Call update() on each detector         │
         │  │  ├─ Swing: Detect new pivots            │
         │  │  ├─ Trend: Classify direction           │
         │  │  ├─ Fibonacci: Update retracement levels│
         │  │  └─ Zones: Track active/broken states   │
         │  └─ Rationalize state (Layer 2)            │
         │     ├─ Detect transitions                  │
         │     └─ Compute derived values              │
         └──────────┬─────────────────────────────────┘
                    │
         ┌──────────┴─────────────────────────────────┐
         │  3.3: UPDATE MTF/HTF FORWARD-FILL INDICES  │
         │  ├─ Check: is exec_bar.ts_close in htf_set?│
         │  │  └─ YES: htf_idx++ (HTF bar closed)     │
         │  │  └─ NO:  htf_idx unchanged (hold)       │
         │  └─ Check: is exec_bar.ts_close in mtf_set?│
         │     └─ YES: mtf_idx++ (MTF bar closed)     │
         │     └─ NO:  mtf_idx unchanged (hold)       │
         └──────────┬─────────────────────────────────┘
                    │
         ┌──────────┴─────────────────────────────────┐
         │  3.4: ACCUMULATE 1M QUOTES (if available)  │
         │  ├─ Find 1m bars between last & current    │
         │  │  exec close                             │
         │  ├─ Accumulate into rollup bucket:         │
         │  │  ├─ min_1m (lowest 1m low)              │
         │  │  ├─ max_1m (highest 1m high)            │
         │  │  ├─ volume_1m (sum of volumes)          │
         │  │  └─ bars_1m (count)                     │
         │  └─ Freeze rollups at exec close           │
         └──────────┬─────────────────────────────────┘
                    │
         ┌──────────┴─────────────────────────────────┐
         │  3.5: BUILD SNAPSHOT (O(1) operation!)     │
         │  ├─ Create RuntimeSnapshotView             │
         │  │  ├─ Set exec_idx = i                    │
         │  │  ├─ Set htf_idx (forward-filled)        │
         │  │  ├─ Set mtf_idx (forward-filled)        │
         │  │  └─ Wire FeedStore references           │
         │  ├─ Attach exchange state                  │
         │  ├─ Attach rollups                         │
         │  ├─ Attach incremental state               │
         │  └─ Attach rationalized state              │
         └──────────┬─────────────────────────────────┘
                    │
         ┌──────────┴─────────────────────────────────┐
         │  3.6: EVALUATE STRATEGY (1m sub-loop)      │
         │  ├─ Get 1m bar range for this exec bar     │
         │  └─ FOR EACH 1m bar within exec bar:       │
         │     ├─ Get mark_price from 1m close        │
         │     ├─ Get last_price from 1m close        │
         │     ├─ Build snapshot with 1m prices       │
         │     ├─ Evaluate actions (entry/exit rules) │
         │     └─ If signal triggered: BREAK           │
         │        (max 1 entry per exec bar)          │
         └──────────┬─────────────────────────────────┘
                    │
         ┌──────────┴─────────────────────────────────┐
         │  3.7: PROCESS SIGNAL (if triggered)        │
         │  ├─ Apply risk sizing:                     │
         │  │  ├─ Calculate position size (risk %)    │
         │  │  └─ Apply leverage limits                │
         │  ├─ Risk policy gates:                     │
         │  │  ├─ Check max position count            │
         │  │  ├─ Check max drawdown                  │
         │  │  └─ Check equity minimum                │
         │  ├─ Submit order to exchange:              │
         │  │  ├─ side (long/short)                   │
         │  │  ├─ size_usdt                           │
         │  │  ├─ stop_loss (if set)                  │
         │  │  └─ take_profit (if set)                │
         │  └─ Record in debug log                    │
         └──────────┬─────────────────────────────────┘
                    │
         ┌──────────┴─────────────────────────────────┐
         │  3.8: STEP SIMULATED EXCHANGE              │
         │  ├─ FOR EACH 1m bar within exec bar:       │
         │  │  ├─ Get 1m OHLC                         │
         │  │  ├─ Check TP hit? (intrabar precision)  │
         │  │  ├─ Check SL hit? (intrabar precision)  │
         │  │  ├─ Check liquidation?                  │
         │  │  └─ Update unrealized PnL               │
         │  ├─ Process funding settlements (8h)       │
         │  │  └─ Apply funding fee if at settlement  │
         │  ├─ Fill pending orders (next bar open)    │
         │  └─ Close expired orders                   │
         └──────────┬─────────────────────────────────┘
                    │
         ┌──────────┴─────────────────────────────────┐
         │  3.9: CHECK STOP CONDITIONS                │
         │  ├─ Equity below stop_equity_usdt?         │
         │  ├─ Drawdown exceeds max_drawdown_pct?     │
         │  ├─ Margin call? (equity < maint margin)   │
         │  └─ If terminal stop → BREAK LOOP          │
         └──────────┬─────────────────────────────────┘
                    │
         ┌──────────┴─────────────────────────────────┐
         │  3.10: RECORD EQUITY POINT                 │
         │  ├─ Snapshot equity_usdt                   │
         │  ├─ Snapshot available_balance              │
         │  ├─ Snapshot unrealized_pnl                │
         │  ├─ Snapshot position state                │
         │  └─ Append to equity curve                 │
         └──────────┬─────────────────────────────────┘
                    │
              ┌─────┴─────┐
              │  i += 1   │  (next bar)
              └─────┬─────┘
                    │
         ┌──────────┴─────────────┐
         │  MORE BARS?            │
         │  (i < total_bars)      │
         └──┬──────────────────┬──┘
            │ YES              │ NO
            │                  │
            └──────────┐       │
                       ↓       ↓
                 (loop back)  (continue to Phase 4)
                              │
┌─────────────────────────────────────────────────────────────┐
│                    PHASE 4: POST-LOOP                       │
└─────────────────────────────────────────────────────────────┘
                              │
         ┌────────────────────┴──────────────────────┐
         │  4.1: CLOSE REMAINING POSITION            │
         │  └─ If position open: force close at      │
         │     final bar close price                 │
         └────────────────────┬──────────────────────┘
                              │
         ┌────────────────────┴──────────────────────┐
         │  4.2: COMPUTE METRICS                     │
         │  ├─ Win rate, profit factor               │
         │  ├─ Sharpe, Sortino, Calmar               │
         │  ├─ Max drawdown (USD and %)              │
         │  ├─ Trade statistics (avg win/loss)       │
         │  ├─ Risk metrics (VaR, CVaR, tail risk)   │
         │  ├─ Benchmark alpha (vs buy-and-hold)     │
         │  └─ Leverage usage (avg, max exposure)    │
         └────────────────────┬──────────────────────┘
                              │
         ┌────────────────────┴──────────────────────┐
         │  4.3: BUILD BACKTEST RESULT               │
         │  ├─ Metadata (symbol, TF, window, UID)    │
         │  ├─ Metrics (62 fields)                   │
         │  ├─ Trades list (all closed trades)       │
         │  ├─ Equity curve (per-bar snapshots)      │
         │  ├─ Account curve (margin, PnL tracking)  │
         │  └─ Stop details (if stopped early)       │
         └────────────────────┬──────────────────────┘
                              │
         ┌────────────────────┴──────────────────────┐
         │  4.4: WRITE ARTIFACTS (if run_dir set)    │
         │  ├─ result.json (full structured result)  │
         │  ├─ trades.csv (trade-by-trade log)       │
         │  ├─ equity.csv (equity curve over time)   │
         │  └─ manifest.json (run metadata + config) │
         └────────────────────┬──────────────────────┘
                              │
         ┌────────────────────┴──────────────────────┐
         │  4.5: RETURN BACKTEST RESULT              │
         │  └─ BacktestResult object                 │
         │     └─ Ready for analysis, plotting, etc. │
         └───────────────────────────────────────────┘
```

### Key Takeaways from the Flow

1. **Initialization is declarative**: You describe WHAT you want (features, actions), engine figures out HOW
2. **Data prep is vectorized**: All indicators computed once, before loop
3. **Main loop is lightweight**: Just array indexing and simple logic
4. **Warmup is separate**: No trading during warmup, just state-building
5. **1m granularity**: TP/SL checks and signal evaluation happen every 1m
6. **Forward-fill is automatic**: HTF/MTF values managed by the engine
7. **Results are structured**: All metrics, trades, equity - ready for analysis

<details>
<summary>Test Your Understanding</summary>

**Q1:** In Phase 2 (Data Preparation), why do we "Find first bar with all valid indicators" instead of just starting at the beginning of the data?

**A1:** Indicators need history to become valid. For example, EMA(50) needs at least 50 bars of data before it produces a meaningful value. The engine finds the first bar where ALL indicators are valid and starts trading from there. Everything before that is the warmup phase.

**Q2:** In Phase 3, step 3.6, why does the strategy evaluate at 1m granularity even if I'm trading 15m bars?

**A2:** Precision. In live trading, your signals could trigger at any moment within a bar. By evaluating every 1m, the backtest better simulates live behavior. If you only evaluated at 15m bar close, you'd miss intrabar opportunities and your backtest wouldn't match live results.

**Q3:** What's the difference between the "equity curve" and the "account curve"?

**A3:**
- **Equity curve**: Simple timeline of total equity (balance + unrealized PnL) at each bar
- **Account curve**: Detailed snapshot including used margin, free margin, maintenance margin, position details, etc.

Equity curve is for plotting. Account curve is for deep analysis of margin usage and risk exposure.

**Q4:** The flow shows "BREAK LOOP" on terminal stop conditions. What happens to the rest of the data after that?

**A4:** The backtest ends immediately. If your equity drops below the configured stop level at bar 5,000, bars 5,001-10,000 never run. This simulates realistic risk management - you wouldn't keep trading after blowing your account.

</details>

---

## Common Pitfalls

### 1. Confusing Mark Price vs Last Price

**Problem**: Using the wrong price for the wrong purpose.

```python
# ❌ WRONG: Using last_price for PnL calculation
unrealized_pnl = position_size * (last_price - entry_price)

# ✅ CORRECT: Use mark_price for PnL (index-derived, manipulation-resistant)
unrealized_pnl = position_size * (mark_price - entry_price)

# ❌ WRONG: Using mark_price for signal evaluation
if mark_price > ema_50:
    buy()  # mark_price might not reflect actual trade execution

# ✅ CORRECT: Use last_price for signals (actual ticker price)
if last_price > ema_50:
    buy()
```

**Why it matters**:
- **mark_price**: Used by Bybit for PnL and liquidations, derived from index across multiple exchanges
- **last_price**: Actual last trade on Bybit orderbook

In volatile markets, these can diverge by 1-2%. Using the wrong one = inaccurate simulation.

### 2. Forgetting About Warmup

**Problem**: Starting trading before indicators are valid.

```yaml
# ❌ WRONG: Not enough warmup for EMA(200)
features:
  ema_200:
    indicator: ema
    params: {length: 200}

# warmup_multiplier: 1.5 → 300 bars of warmup
# If your data starts at bar 0, you have 300 bars of warmup
# BUT if your window starts at bar 100, you only have 100 bars!

# ✅ CORRECT: Ensure data start is earlier than window start
# Load data from (window_start - warmup_period)
```

**Symptom**: Your first trades happen with NaN indicators, leading to random signals.

**Fix**: Engine auto-extends data loading, but verify with preflight:
```bash
python trade_cli.py backtest preflight --play-id <play_id>
```

### 3. Window Operator Confusion

**Problem**: Misunderstanding bar counts vs timeframe scaling.

```yaml
# ❌ WRONG: Expecting "3 consecutive 15m bars"
holds_for:
  expr: {feature_id: rsi_14, op: lt, value: 30}
  bars: 3
# This checks 3 MINUTES (1m granularity), not 3 bars!

# ✅ CORRECT: Use anchor_tf to scale
holds_for:
  expr: {feature_id: rsi_14, op: lt, value: 30}
  bars: 3
  anchor_tf: "15m"  # Now it's 3 * 15m = 45 minutes
```

**Symptom**: Your conditions trigger way more or less often than expected.

### 4. Modifying Snapshot Data

**Problem**: Trying to change indicator values in your strategy.

```python
# ❌ WRONG: Snapshots are read-only
snapshot.indicators['ema_9'][i] = 100  # AttributeError or silent failure

# ✅ CORRECT: If you need custom indicators, compute them in the Play config
features:
  custom_ema:
    indicator: ema
    params: {length: 9}
    # Precomputed before loop
```

**Why**: Immutability prevents bugs from accidental state corruption. All data is read-only by design.

### 5. Ignoring Forward-Fill Semantics

**Problem**: Expecting HTF indicators to update every exec bar.

```python
# Your expectation:
for i in range(10000):
    htf_ema = snapshot.htf_indicator('ema_50')  # Updates every bar?

# Reality:
# exec=15m, HTF=1h → HTF updates every 4 bars
# Bars 0-3: htf_ema = value from bar 0 (forward-filled)
# Bar 4: htf_ema = value from bar 4 (just updated)
# Bars 5-7: htf_ema = value from bar 4 (forward-filled)
```

**Symptom**: HTF strategy logic doesn't react to price changes within the HTF bar.

**Fix**: This is correct behavior! HTF values SHOULD be stable between HTF closes. Use `snapshot.htf_is_stale` to check if HTF is forward-filling.

### 6. Overusing Indicators

**Problem**: Adding dozens of indicators "just in case."

```yaml
# ❌ WRONG: Indicator soup
features:
  ema_9, ema_12, ema_21, ema_26, ema_50, ema_100, ema_200,
  sma_9, sma_20, sma_50, sma_200,
  rsi_7, rsi_14, rsi_21,
  bbands_20, bbands_50,
  macd_12_26_9, macd_fast_slow,
  atr_7, atr_14, atr_21,
  ... (30 more indicators)
```

**Consequences**:
- Slower backtests (more computation)
- More memory usage
- Longer warmup periods
- "Kitchen sink" strategies that don't generalize

**Fix**: Start minimal. Add indicators only when you have a specific hypothesis to test.

### 7. Incorrect Timeframe Hierarchy

**Problem**: Defining MTF/HTF incorrectly.

```yaml
# ❌ WRONG: HTF faster than MTF
tf: "15m"  # exec
mtf: "1h"
htf: "30m"  # Breaks HTF >= MTF >= exec rule
```

**Symptom**: Config validation fails with clear error message.

**Fix**: Ensure `HTF >= MTF >= exec` in minutes:
```yaml
tf: "15m"   # exec: 15 minutes
mtf: "1h"   # MTF:  60 minutes
htf: "4h"   # HTF: 240 minutes
```

### 8. Not Running Preflight Checks

**Problem**: Diving straight into backtests without validation.

```bash
# ❌ WRONG: Just run it
python trade_cli.py backtest run --play-id myplay

# ✅ CORRECT: Preflight first
python trade_cli.py backtest preflight --play-id myplay
# Checks:
# - Data coverage (is the window fully covered?)
# - Warmup sufficiency (enough bars before window?)
# - Indicator validity (no NaN in trading period?)
# - 1m data availability (for mark/last prices)
```

**Why**: Preflight catches 90% of common issues before you waste time on a broken backtest.

---

## Further Reading

Now that you understand the concepts, explore these docs for implementation details:

| Document | What It Covers |
|----------|----------------|
| `docs/specs/PLAY_DSL_COOKBOOK.md` | Complete DSL reference (operators, windows, syntax) |
| `docs/architecture/INCREMENTAL_STATE_ARCHITECTURE.md` | How market structures work (swing, trend, zones) |
| `docs/architecture/SIMULATED_EXCHANGE.md` | Exchange simulation details (fills, fees, liquidations) |
| `docs/architecture/PLAY_ENGINE_FLOW.md` | Technical flow from YAML to execution |
| `src/backtest/CLAUDE.md` | Module-specific rules and conventions |

### Key Source Files

| File | Purpose |
|------|---------|
| `src/backtest/engine.py` | Main orchestrator (start here!) |
| `src/backtest/runtime/feed_store.py` | FeedStore implementation |
| `src/backtest/runtime/snapshot_view.py` | RuntimeSnapshotView |
| `src/backtest/runtime/cache.py` | TimeframeCache (MTF forward-fill) |
| `src/backtest/rules/evaluation/window_ops.py` | Window operator implementations |
| `src/backtest/sim/exchange.py` | Simulated exchange |

---

## Final Mental Model

When you run a backtest, picture this:

1. **Loading Phase**: You're loading a massive filing cabinet (FeedStore) with pre-organized folders (numpy arrays)
2. **Warmup Phase**: You're flipping through the first pages to get context, but not making any decisions yet
3. **Hot Loop**: Every bar, you:
   - Point your finger at a row in the filing cabinet (create snapshot with index)
   - Read the values at that row (O(1) array access)
   - Ask your strategy "what do you want to do?" (evaluate rules)
   - Record the decision (execute trade in sim)
   - Move your finger to the next row (increment index)
4. **Results Phase**: You close the filing cabinet and analyze what happened

No copying, no DataFrame operations, no recomputation. Just indexing and simple logic. That's why TRADE is fast.

**Welcome to the engine! Now go write some profitable strategies.** 🚀

---

*Last updated: 2026-01-10*
*For questions or improvements, see `docs/SESSION_HANDOFF.md`*
