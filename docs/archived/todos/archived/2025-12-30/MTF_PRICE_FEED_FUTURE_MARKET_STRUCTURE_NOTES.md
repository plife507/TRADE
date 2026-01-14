# Core Concepts Review (MTF + Price Feed + Future Market Structure)

## 1) End Goal
Build a backtest/sim architecture that:
- Evaluates strategies **only on `tf_exec` candle closes**
- Uses the **same IdeaCards + packet format** later for demo/live (adapter swap)
- Supports **indicators + future market-structure entities** together
- Adds a “ticker-like” **price feed element** in sim using **1m data**, enabling granular zone interaction logic (e.g., 4h pocket touched/entered) without intrabar strategy execution.

---

## 2) Timeframes and Roles
### `tf_exec`
- The only timeframe where **strategy evaluation and order intent generation** occurs.
- Example: `5m` or `15m`.

### `tf_ctx[]`
- Higher or additional timeframes that provide context.
- Updated **only on their own closes**.
- Forward-filled into the packet at each `tf_exec` close.
- Example: `1h`, `4h`.

### `1m` (mandatory base feed)
- Used as the simulator’s **quote/ticker proxy**.
- Enables **granular price interaction** detection (touch/enter) between `tf_exec` closes.
- Must be included in **all preflight coverage checks**.

---

## 3) MTF Integration Model (No Double/Triple Compute)
### Compute once per TF close
Maintain one feed + one feature state per `(symbol, tf)`:
- `Bars[tf]`: closed candles only
- `Features[tf]`: computed only on TF close (indicators now; market structure later)

### Packet build uses pointer-based forward fill
At each `tf_exec` close time `T_exec`:
- `exec_idx` = index of the exec bar that just closed
- For each `tf_ctx`:
  - `ctx_idx` = last closed bar index where `ctx.ts_close <= T_exec`
- Packet reads HTF values via `ctx_idx` (forward-fill by reference).
- No recompute; only O(1) reads.

---

## 4) “Ticker / Live Feed Element” in Simulator (Using 1m Data)
### Why it’s needed
- HTF zones/levels (e.g., future 4h fib pocket bounds) update infrequently.
- We still need granular detection of:
  - “price touched the zone”
  - “price entered the zone”
  - “price spent time in the zone”
- Live/demo has tick/mark streams; sim must approximate this with 1m data.

### How it works
- Treat **1m bars as a quote stream**.
- Do NOT recompute HTF zones every minute.
- Instead, on each 1m bar, compute cheap checks against forward-filled bounds:
  - `touch_1m`: overlap([low_1m, high_1m], [zone_low, zone_high])
  - `in_zone_1m`: zone_low <= close_1m <= zone_high
  - `entered_1m`: in_zone_1m && !prev_in_zone_1m
  - `distance_to_zone_1m`: 0 if in_zone else min(|close-low|, |close-high|)

### Rollups into `tf_exec` packet (no window scanning)
Maintain an incremental **ExecRollupBucket** between exec closes:
- `touched_since_last_exec` (bool)
- `entered_since_last_exec` (bool)
- `minutes_in_zone` (int)
- `min_distance_to_zone` (float)
- `max_price_since_last_exec`, `min_price_since_last_exec`
Freeze these into the packet at `tf_exec` close and reset.

---

## 5) Two Price Streams (Live/Demo Compatibility)
Use two price channels with different responsibilities:
- `px.last` (signals/entries): ticker / last trade price
- `px.mark` (risk): mark price for margin/liquidation logic

### Simulator mapping
- `px.last`: derived from 1m OHLC (close/high/low)
- `px.mark`: ideally from 1m **mark-price klines** (if stored); otherwise approximate (lower fidelity for risk)

---

## 6) Market Structure Planning (Not Implemented Yet)
### Key principle
Market structure ≠ indicators. It is a **state machine** that emits:
1) **Sparse events** (one-bar pulses on confirmation)
2) **Forward-filled context/levels** (persist while active)

### Lifecycle concept (per structure entity)
State progression:
- `none → candidate → valid → invalid`
Forward-fill context while `candidate` or `valid`.

### Consumption model
IdeaCards should be able to mix:
- HTF structure context (e.g., pocket bounds from 4h)
- Trend regime from 1h
- Entry triggers from 5m/15m (volume spike, EMA cross)
- Granular “entered/touched” from 1m rollups

Default safety direction:
- Include candidates in packets if needed, but strategies typically default to **validated-only** unless explicitly opting into candidates.

---

## 7) Preflight / Warmup Requirements (Critical)
### Warmup meaning
No strategy evaluation until ALL requirements are satisfied:
- `tf_exec` warmup
- each `tf_ctx` warmup
- indicator warmups (per TF)
- future structure warmups (per TF, includes confirmation delays)
- **mandatory 1m coverage** for price feed rollups

### New rule
**1m must be included in every preflight validation** for any backtest:
- Coverage exists for `[start - warmup_buffer, end]`
- Exec-to-1m mapping is feasible (to compute rollups without scanning)

---

## 8) Key Decisions Already Made
- Strategy evaluation happens **only on `tf_exec` closes**
- `tf_ctx` updates only on its TF close and is forward-filled into `tf_exec` packets
- Use **1m bars as sim quote feed**
- Keep **two price channels** (`px.last` for signals, `px.mark` for risk)
- Add 1m to **all preflight checks** for any backtest

---

## 9) Open Decisions for Tomorrow
1) **Exec TF choice** for zone/entry systems:
   - `5m` (more reactive) vs `15m` (cleaner confirmations)

2) Zone interaction definition default:
   - Touch = 1m high/low overlaps zone (captures wicks)
   - Enter = 1m close inside zone (stricter)

3) Mark-price historical availability:
   - Do we store 1m mark-price klines in the DB now, or accept approximation short-term?

4) Packet key namespace:
   - Standardize keys for price-feed rollups (e.g., `px.last.*`, `px.mark.*`, `px.rollup.*`)

---

## 10) Immediate Next Build Steps (Order)
1) Update **preflight** to require 1m coverage for all backtests.
2) Implement simulator **1m-driven PriceFeed + ExecRollupBucket** and inject rollups into packets at exec close.
3) Keep strategy evaluation restricted to `tf_exec` close; confirm no HTF recompute.
4) After that foundation, start market-structure entity design (swings → BOS/CHoCH → pocket bounds).

---