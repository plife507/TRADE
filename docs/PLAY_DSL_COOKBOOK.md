# TRADE Play DSL Cookbook (v3.0.0)

> **CANONICAL SOURCE OF TRUTH** for Play DSL syntax.
> All other DSL documentation is deprecated. This is the single reference.

**Status: FROZEN (2026-01-08)**

The DSL language is now frozen with 259 synthetic tests validating all operators, edge cases, and type safety rules. Changes to DSL semantics require explicit unfreezing and test updates.

## Discrepancy Resolution Workflow

When tests reveal behavior differs from this doc:

1. **Evaluate all three options:**
   - Is the **engine** wrong?
   - Is the **cookbook** wrong?
   - Is the **DSL design** wrong (types, variables, syntax organization)?

2. **Reach consensus** on what makes the most sense for:
   - Usability (intuitive for strategy authors)
   - Consistency (follows established patterns)
   - Correctness (matches trading semantics)

3. **Modify the appropriate component:**
   - Engine bug → fix engine
   - Doc error → fix cookbook
   - Design flaw → redesign DSL, then update both engine and cookbook

---

## Table of Contents

1. [Play Structure](#1-play-structure)
2. [Features (Indicators)](#2-features-indicators)
3. [Structures (Market Structure)](#3-structures-market-structure)
4. [Actions (Entry/Exit Rules)](#4-actions-entryexit-rules)
5. [Operators](#5-operators)
6. [Arithmetic DSL](#6-arithmetic-dsl)
7. [Window Operators](#7-window-operators)
8. [Multi-Timeframe (MultiTF)](#8-multi-timeframe-multitf)
9. [Risk Model](#9-risk-model)
10. [Order Sizing & Execution](#10-order-sizing--execution)
11. [Complete Examples](#11-complete-examples)
12. [Quick Reference Card](#quick-reference-card)

---

## 1. Play Structure

A Play is the complete backtest-ready strategy unit.

### Default Values Reference

These are the system defaults. When not specified in a Play, these values apply:

| Field | Default | Source | Notes |
|-------|---------|--------|-------|
| **Account Configuration** ||||
| `taker_bps` | 6.0 | Bybit API | 0.06% taker fee |
| `maker_bps` | 1.0 | Bybit API | 0.01% maker fee |
| `slippage_bps` | 2.0 | - | Conservative estimate |
| `margin_mode` | `isolated_usdt` | - | Only supported mode |
| `min_trade_notional_usdt` | 10.0 | - | Minimum trade size |
| **Risk Model** ||||
| `sizing.model` | `percent_equity` | - | Margin-based sizing |
| `sizing.max_leverage` | 1.0 | - | Conservative default |
| **Position Policy** ||||
| `mode` | `long_only` | - | Conservative default |
| `exit_mode` | `sl_tp_only` | - | Mechanical exits |
| `max_positions_per_symbol` | 1 | - | Single position |

**IMPORTANT: No implicit defaults for capital or risk.** These MUST be explicitly specified:
- `starting_equity_usdt` - Required
- `max_leverage` - Required
- `stop_loss` - Required for sl_tp_only/first_hit modes
- `take_profit` - Required for sl_tp_only/first_hit modes

```yaml
# ═══════════════════════════════════════════════════════════════════════════════
# IDENTITY
# ═══════════════════════════════════════════════════════════════════════════════
version: "3.0.0"               # Schema version
name: "my_strategy"            # Strategy name
description: "Description"     # What it does

# ═══════════════════════════════════════════════════════════════════════════════
# MARKET & TIMEFRAMES
# ═══════════════════════════════════════════════════════════════════════════════
symbol: "BTCUSDT"              # Trading pair (USDT pairs only)
tf: "15m"                      # Execution timeframe (ANY tf works: 1m, 5m, 15m, 1h, 4h, etc.)
med_tf: "1h"                   # Optional: mid timeframe for context
high_tf: "4h"                  # Optional: higher timeframe for trend/levels

# ═══════════════════════════════════════════════════════════════════════════════
# ACCOUNT CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════
account:
  starting_equity_usdt: 10000.0
  max_leverage: 3.0
  margin_mode: "isolated_usdt"  # Must be isolated_usdt
  min_trade_notional_usdt: 10.0
  fee_model:
    taker_bps: 6.0             # 0.06% taker fee (Bybit default)
    maker_bps: 1.0             # 0.01% maker fee (Bybit default)
  slippage_bps: 2.0            # Slippage estimate

# ═══════════════════════════════════════════════════════════════════════════════
# INDICATORS
# ═══════════════════════════════════════════════════════════════════════════════
features:
  ema_9:
    indicator: ema
    params: {length: 9}

# ═══════════════════════════════════════════════════════════════════════════════
# MARKET STRUCTURE
# ═══════════════════════════════════════════════════════════════════════════════
structures:
  swing:
    detector: swing
    params: {left: 5, right: 5}

# ═══════════════════════════════════════════════════════════════════════════════
# TRADING RULES
# ═══════════════════════════════════════════════════════════════════════════════
actions:
  entry_long:
    all:
      - ["ema_9", ">", "ema_21"]
  exit_long:
    all:
      - ["ema_9", "<", "ema_21"]

# ═══════════════════════════════════════════════════════════════════════════════
# RISK MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════
risk:
  stop_loss_pct: 2.0
  take_profit_pct: 4.0
  max_position_pct: 100.0

# ═══════════════════════════════════════════════════════════════════════════════
# POSITION POLICY
# ═══════════════════════════════════════════════════════════════════════════════
position_policy:
  mode: "long_only"            # "long_only", "short_only", "long_short"
  exit_mode: "first_hit"       # How positions close (see below)
  max_positions_per_symbol: 1

# ═══════════════════════════════════════════════════════════════════════════════
# VARIABLES (Optional - for template resolution)
# ═══════════════════════════════════════════════════════════════════════════════
variables:
  fast_len: 9
  slow_len: 21
```

### Position Policy Details

| Field | Values | Description |
|-------|--------|-------------|
| `mode` | `long_only`, `short_only`, `long_short` | Which directions allowed |
| `exit_mode` | `sl_tp_only`, `signal`, `first_hit` | How positions close |
| `max_positions_per_symbol` | `1` (only value) | Single position per symbol |

### Exit Mode (Critical for Trade Logic)

| Mode | Description | Use Case |
|------|-------------|----------|
| `sl_tp_only` | Exits ONLY via stop loss or take profit. No signal-based exits. | Mechanical systems, set-and-forget |
| `signal` | Exits via signal (exit_long/exit_short). SL/TP act as emergency stops only. | Discretionary exits, trend following |
| `first_hit` | Hybrid - exits on whichever triggers first: signal OR SL/TP. | Most flexible, recommended default |

**Example impact:**
```yaml
# With exit_mode: "sl_tp_only"
# - Your exit_long action is IGNORED
# - Position closes ONLY when SL or TP hit

# With exit_mode: "signal"
# - Your exit_long action triggers exit
# - SL/TP only hit if signal never fires

# With exit_mode: "first_hit"
# - If exit_long fires before SL/TP → signal exit
# - If SL/TP hit before signal → mechanical exit
```

### Variables (Template Resolution)

Variables allow parameterization for optimization:

```yaml
variables:
  fast_len: 9
  slow_len: 21
  stop_mult: 2.0

features:
  ema_fast:
    indicator: ema
    params: {length: "{{ fast_len }}"}  # Resolves to 9
  ema_slow:
    indicator: ema
    params: {length: "{{ slow_len }}"}  # Resolves to 21

risk:
  stop_loss:
    type: "atr_multiple"
    value: "{{ stop_mult }}"            # Resolves to 2.0
```

**Note:** Variable resolution uses `{{ var_name }}` syntax. Not all fields support variables yet.

---

## 2. Features (Indicators)

### Naming Convention (MANDATORY)

**Use parameterized names that encode indicator type and primary parameters.**

| Type | Pattern | Example |
|------|---------|---------|
| Single-param | `{type}_{param}` | `ema_20`, `rsi_14` |
| Single-param + TF | `{type}_{param}_{tf}` | `ema_50_1h`, `rsi_14_4h` |
| Multi-param | `{type}_{p1}_{p2}` | `bbands_20_2` |
| MACD | `macd_{f}_{s}_{sig}` | `macd_12_26_9` |

```yaml
# WRONG - semantic names hide parameters
features:
  ema_fast:
    indicator: ema
    params: {length: 9}   # What length? Unclear!

# CORRECT - parameterized names
features:
  ema_9:                  # Clearly length=9
    indicator: ema
    params: {length: 9}
```

### Full Feature Syntax

```yaml
features:
  # Simple single-output indicator
  ema_21:
    indicator: ema
    params:
      length: 21
    tf: "1h"              # Optional: defaults to execution_tf
    source: close         # Optional: defaults to close

  # Multi-output indicator (access via field)
  macd_12_26_9:
    indicator: macd
    params:
      fast: 12
      slow: 26
      signal: 9
    # Outputs: macd, signal, histogram

  # Volume-based indicator
  volume_sma_20:
    indicator: sma
    source: volume        # Use volume instead of close
    params:
      length: 20

  # Bollinger Bands (multi-output)
  bbands_20_2:
    indicator: bbands
    params:
      length: 20
      std: 2.0
    # Outputs: lower, middle, upper, bandwidth, percent_b
```

### Feature Timeframe Inheritance (IMPORTANT)

Every feature computes on a specific timeframe. **If a feature does not specify a `tf:` field, it inherits the Play's main `tf:` (execution timeframe).**

#### Inheritance Rules

| Feature `tf:` Field | Timeframe Used | Update Behavior |
|---------------------|----------------|-----------------|
| **Not specified** | Inherits main `tf:` | Updates every exec bar |
| **Explicit (slower than exec)** | Uses specified TF | Forward-fills between TF closes |
| **Explicit (faster than exec)** | Uses specified TF | Sampled at exec bar boundaries |

**Important: Inheritance is flat (one level only).** There is no feature-to-feature inheritance. Each feature either:
1. Has an explicit `tf:` → uses that value
2. Has no `tf:` → defaults to the Play's main `tf:`

The `source:` field (e.g., `source: volume`) changes the **input data**, not the timeframe.

#### How It Works

```yaml
tf: "15m"                      # Main execution TF

features:
  # NO tf: specified → inherits "15m"
  ema_9:
    indicator: ema
    params: {length: 9}
    # Computed on 15m bars, updates every 15m

  # Explicit tf: "4h" → uses 4h, forward-fills
  ema_50_4h:
    indicator: ema
    params: {length: 50}
    tf: "4h"
    # Computed on 4h bars, forward-fills for 16 exec bars (4h ÷ 15m)

  # Explicit tf: "1h" → uses 1h, forward-fills
  rsi_14_1h:
    indicator: rsi
    params: {length: 14}
    tf: "1h"
    # Computed on 1h bars, forward-fills for 4 exec bars (1h ÷ 15m)
```

#### Forward-Fill Behavior

When a feature's TF is **slower** than the execution TF, its value remains constant (forward-fills) until the slower TF bar closes:

```
exec bars (15m):  |  1  |  2  |  3  |  4  |  5  |  6  |  7  |  8  |
                  +-----+-----+-----+-----+-----+-----+-----+-----+
1h feature:       |     1h bar 0 (v=100)  |    1h bar 1 (v=102)   |
                  |  100   100   100  100 |  102   102   102  102 |
                  '---- forward-fill -----'
```

**No lookahead:** Forward-filled values always reflect the **last CLOSED bar**, never partial/forming bars.

#### Why This Matters

```yaml
tf: "15m"

features:
  ema_fast:           # BAD: unclear what TF
    indicator: ema
    params: {length: 9}

  ema_9:              # GOOD: inherits 15m (clear from context)
    indicator: ema
    params: {length: 9}

  ema_9_1h:           # GOOD: explicit 1h (clear from name + config)
    indicator: ema
    params: {length: 9}
    tf: "1h"
```

**Best practice:** Include TF in feature names when using explicit `tf:` override (e.g., `ema_50_4h`, `rsi_14_1h`). This makes DSL expressions self-documenting:

```yaml
# Clear: ema_9 is 15m (exec), ema_50_4h is 4h
- ["ema_9", ">", "ema_50_4h"]

# Unclear: what TF is ema_slow?
- ["ema_fast", ">", "ema_slow"]
```

#### Interaction with Built-in Price Features

Built-in price features have **fixed resolutions** that do NOT follow inheritance:

| Feature | Resolution | Inheritance |
|---------|------------|-------------|
| `last_price` | Always 1m | No (fixed) |
| `mark_price` | Always 1m | No (fixed) |
| `close`, `open`, `high`, `low`, `volume` | Always exec TF | No (fixed) |
| Declared features without `tf:` | Exec TF | **Yes (inherits)** |
| Declared features with `tf:` | Specified TF | No (explicit) |

This means `last_price` provides 1m precision regardless of your `tf:` setting, while indicator features follow the inheritance rules above.

### Complete Indicator Registry (43 Total)

**Single-Output (27):**

| Indicator | Params | Description |
|-----------|--------|-------------|
| `ema` | `length` | Exponential Moving Average |
| `sma` | `length` | Simple Moving Average |
| `wma` | `length` | Weighted Moving Average |
| `dema` | `length` | Double EMA |
| `tema` | `length` | Triple EMA |
| `trima` | `length` | Triangular MA |
| `zlma` | `length` | Zero Lag MA |
| `kama` | `length` | Kaufman Adaptive MA |
| `alma` | `length`, `sigma`, `offset` | Arnaud Legoux MA |
| `rsi` | `length` | Relative Strength Index |
| `atr` | `length` | Average True Range |
| `natr` | `length` | Normalized ATR |
| `cci` | `length` | Commodity Channel Index |
| `willr` | `length` | Williams %R |
| `roc` | `length` | Rate of Change |
| `mom` | `length` | Momentum |
| `mfi` | `length` | Money Flow Index |
| `obv` | (none) | On-Balance Volume |
| `cmf` | `length` | Chaikin Money Flow |
| `cmo` | `length` | Chande Momentum Oscillator |
| `linreg` | `length` | Linear Regression |
| `midprice` | `length` | Midprice |
| `ohlc4` | (none) | OHLC Average |
| `trix` | `length` | Triple Exponential |
| `uo` | `fast`, `medium`, `slow` | Ultimate Oscillator |
| `ppo` | `fast`, `slow`, `signal` | Percentage Price Oscillator |
| `vwap` | (none) | Volume Weighted Avg Price |

**Multi-Output (16):**

| Indicator | Outputs | Params |
|-----------|---------|--------|
| `macd` | `macd`, `signal`, `histogram` | `fast`, `slow`, `signal` |
| `bbands` | `lower`, `middle`, `upper`, `bandwidth`, `percent_b` | `length`, `std` |
| `stoch` | `stoch_k`, `stoch_d` | `k`, `d`, `smooth_k` |
| `stochrsi` | `stochrsi_k`, `stochrsi_d` | `length`, `rsi_length`, `k`, `d` |
| `adx` | `adx`, `dmp`, `dmn`, `adxr` | `length` |
| `aroon` | `aroon_up`, `aroon_down`, `aroon_osc` | `length` |
| `kc` | `kcl`, `kcb`, `kcu` | `length`, `scalar` |
| `donchian` | `dcl`, `dcm`, `dcu` | `lower_length`, `upper_length` |
| `supertrend` | `st`, `std`, `stl`, `sts` | `length`, `multiplier` |
| `psar` | `psar_l`, `psar_s`, `psar_af`, `psar_r` | `af0`, `af`, `max_af` |
| `squeeze` | `sqz`, `sqz_on`, `sqz_off`, `sqz_no` | `bb_length`, `bb_std`, `kc_length`, `kc_scalar` |
| `vortex` | `vip`, `vim` | `length` |
| `dm` | `dmp`, `dmn` | `length` |
| `fisher` | `fisher`, `fisher_signal` | `length` |
| `tsi` | `tsi`, `tsi_signal` | `fast`, `slow`, `signal` |
| `kvo` | `kvo`, `kvo_signal` | `fast`, `slow`, `signal` |

### Built-in Price Features (No Declaration Needed)

| Feature | Description | Update Rate | Backtest Source | Live Source (Future) |
|---------|-------------|-------------|-----------------|----------------------|
| `open`, `high`, `low`, `close`, `volume` | OHLCV data | Per exec bar | Historical candles | REST/WebSocket candles |
| `last_price` | Current price (1m resolution) | Every 1m | 1m bar close | `ticker.lastPrice` |
| `mark_price` | Fair price for margin/PnL | Every 1m | 1m bar close | `ticker.markPrice` |

### Price Features Deep Dive

**`last_price` vs `close` vs `mark_price`:**

```
Timeline within a 15m exec bar:
|----|----|----|----|----|----|----|----|----|----|----|----|----|----|----|
 1m   2m   3m   4m   5m   6m   7m   8m   9m  10m  11m  12m  13m  14m  15m

close:       Only available at bar close (15m mark)
last_price:  Updated every 1m (15 updates per exec bar)
mark_price:  Updated every 1m (used for margin calculations)
```

**Use cases:**

| Feature | When to Use |
|---------|-------------|
| `close` | Bar-level conditions, indicators, end-of-bar decisions |
| `last_price` | Precise entries, cross-TF comparisons, intra-bar TP/SL checks |
| `mark_price` | Margin calculations, PnL computation, liquidation checks |

### CRITICAL: last_price vs mark_price (Live Integration)

> **These are NOT aliases. They are semantically different in live trading.**

In backtest, both default to the same 1m close source for simplicity. In live trading, they come from **different WebSocket fields** and **can diverge significantly** during volatile periods.

**Why Bybit Has Two Prices:**

| Price | Source | Purpose | Behavior During Volatility |
|-------|--------|---------|---------------------------|
| `last_price` | Actual last trade on Bybit | Signal evaluation, entry/exit decisions | Can spike/crash with orderbook activity |
| `mark_price` | Index across multiple exchanges | PnL, liquidation, margin | Stable (anti-manipulation design) |

**Example divergence scenario:**
```
During a flash crash on Bybit:
- last_price: Drops to $50,000 (actual trades happening)
- mark_price: Stays at $51,500 (index stable across exchanges)

Your strategy sees:
- Signal evaluation uses last_price → May trigger entries
- Position PnL uses mark_price → Won't show the full paper loss
- Liquidation uses mark_price → Protected from manipulation wicks
```

**When to use which:**

```yaml
# CORRECT: Use last_price for signal evaluation
actions:
  entry_long:
    all:
      - ["last_price", "cross_above", "ema_50"]  # Actual trading price

# CORRECT: Engine internally uses mark_price for:
# - Unrealized PnL calculation
# - Liquidation distance checks
# - Margin requirement calculations
```

**Design intent:** In live trading, you want to enter/exit based on where you'll actually execute (`last_price`), but value your position based on the stable index price (`mark_price`) to avoid manipulation-triggered liquidations.

**Crossover with 1m resolution:**

```yaml
# Precise entry: last_price crosses above a 4h EMA
actions:
  entry_long:
    all:
      - ["last_price", "cross_above", "ema_50_4h"]  # 1m granularity check
```

**Offset support:**

| Feature | offset=0 | offset=1 | offset>1 |
|---------|----------|----------|----------|
| `last_price` | Current 1m close | Previous 1m close | Not supported |
| `mark_price` | Current mark | Not supported | Not supported |
| `close` | Current bar close | Previous bar close | Supported |

---

## 3. Structures (Market Structure)

Structures provide O(1) incremental market structure detection.

### Available Structure Types

| Type | Description | Depends On |
|------|-------------|------------|
| `swing` | Swing high/low pivot detection | None |
| `trend` | Wave-based trend tracking (HH/HL/LH/LL) | `swing` |
| `market_structure` | ICT-style BOS/CHoCH detection | `swing` |
| `zone` | Demand/supply zones | `swing` |
| `fibonacci` | Fib retracement/extension levels | `swing` |
| `rolling_window` | O(1) rolling min/max | None |
| `derived_zone` | Fibonacci zones from pivots | `source` (not `swing`) |

### Structure YAML Format (Role-Based)

The engine expects structures organized by timeframe role (`exec`, `high_tf`, `med_tf`):

```yaml
structures:
  # Execution TF structures (list format)
  exec:
    - type: swing
      key: swing             # Reference key for actions
      params:
        left: 5
        right: 5
        atr_key: atr_14      # Optional: ATR feature for significance filtering
      # Outputs: high_level, high_idx, low_level, low_idx, version
      #          pair_high_level, pair_low_level, pair_direction, pair_version

    - type: trend
      key: trend
      depends_on:
        swing: swing         # References the swing key above
      # Outputs: direction, strength, bars_in_trend, wave_count,
      #          last_wave_direction, last_hh, last_hl, last_lh, last_ll, version

    - type: market_structure
      key: ms
      depends_on:
        swing: swing
      # Outputs: bias, bos_this_bar, choch_this_bar, bos_direction, choch_direction,
      #          last_bos_idx, last_bos_level, last_choch_idx, last_choch_level,
      #          break_level_high, break_level_low, version

    - type: fibonacci
      key: fib
      depends_on:
        swing: swing
      params:
        levels: [0.382, 0.5, 0.618]
        mode: retracement    # or "extension", "extension_up", "extension_down"
      # Outputs: level_0.382, level_0.5, level_0.618

  # HighTF structures (nested by timeframe)
  high_tf:
    "4h":
      - type: swing
        key: swing_4h
        params: {left: 3, right: 3}
    "1h":
      - type: swing
        key: swing_1h
        params: {left: 5, right: 5}
```

**Key fields:**
- `type`: Structure detector type (swing, trend, fibonacci, etc.)
- `key`: Reference name used in actions (e.g., `{feature_id: "swing", field: "high_level"}`)
- `params`: Detector-specific parameters
- `depends_on`: Map of dependency name to key (for dependent structures)

### Structure Types Reference

```yaml
# Swing Pivot Detector
- type: swing
  key: swing
  params:
    left: 5              # Bars to left for confirmation
    right: 5             # Bars to right for confirmation
  # Outputs: high_level, high_idx, low_level, low_idx, version
  #          pair_high_level, pair_low_level, pair_direction, pair_version

# Trend Detector (wave-based, depends on swing)
- type: trend
  key: trend
  depends_on: {swing: swing}
  params:
    wave_history_size: 4     # Number of waves to track (default: 4)
  # Core outputs:
  #   direction: 1=bullish, -1=bearish, 0=ranging
  #   strength: 0=weak, 1=normal, 2=strong (based on HH/HL or LL/LH patterns)
  #   bars_in_trend: bars since last direction change
  # Wave outputs:
  #   wave_count: total completed waves
  #   last_wave_direction: 1=bullish (L→H), -1=bearish (H→L)
  # Comparison flags (from last 4 waves):
  #   last_hh: true if most recent high was higher than previous high
  #   last_hl: true if most recent low was higher than previous low
  #   last_lh: true if most recent high was lower than previous high
  #   last_ll: true if most recent low was lower than previous low
  #   version: increments on each wave completion

# Market Structure Detector (ICT BOS/CHoCH, depends on swing)
- type: market_structure
  key: ms
  depends_on: {swing: swing}
  params:
    confirmation_close: false  # Require candle close beyond level (default: false)
  # Bias output:
  #   bias: 1=bullish, -1=bearish, 0=ranging (initial state)
  # Event flags (true only on the bar they occur, reset each bar):
  #   bos_this_bar: true when Break of Structure occurs this bar
  #   choch_this_bar: true when Change of Character occurs this bar
  # Event directions (set when event occurs, persist until next event):
  #   bos_direction: 1=bullish BOS, -1=bearish BOS
  #   choch_direction: 1=bearish-to-bullish CHoCH, -1=bullish-to-bearish CHoCH
  # Level tracking:
  #   last_bos_idx: bar index of most recent BOS
  #   last_bos_level: price level of most recent BOS
  #   last_choch_idx: bar index of most recent CHoCH
  #   last_choch_level: price level of most recent CHoCH
  #   break_level_high: current swing high being watched for breaks
  #   break_level_low: current swing low being watched for breaks
  #   version: increments on each BOS or CHoCH event

# BOS vs CHoCH explanation:
# - BOS (Break of Structure): Continuation signal - price breaks swing level in trend direction
#   - In uptrend: price breaks above previous swing high → bullish BOS
#   - In downtrend: price breaks below previous swing low → bearish BOS
# - CHoCH (Change of Character): Reversal signal - price breaks swing level against trend
#   - In uptrend: price breaks below previous swing low → bearish CHoCH (trend reversal)
#   - In downtrend: price breaks above previous swing high → bullish CHoCH (trend reversal)

# Fibonacci Levels (depends on swing)
- type: fibonacci
  key: fib
  depends_on: {swing: swing}
  params:
    levels: [0.236, 0.382, 0.5, 0.618, 0.786]
    mode: retracement    # "retracement", "extension", "extension_up", "extension_down"
  # Outputs: level_0.236, level_0.382, level_0.5, level_0.618, level_0.786

# Demand/Supply Zone (depends on swing)
- type: zone
  key: demand_zone
  depends_on: {swing: swing}
  params:
    zone_type: demand    # "demand" or "supply"
    width_atr: 1.5       # Zone width in ATR units
  # Outputs: state, upper, lower, anchor_idx, version

# Rolling Window (O(1) min/max) - no dependencies
- type: rolling_window
  key: rolling_high
  params:
    mode: max            # "min" or "max"
    size: 20             # Window size in bars
    source: high         # Field to track (open, high, low, close)
  # Outputs: value

# Derived Zones (K Slots) - depends on source (swing)
# NOTE: Uses `source:` key, NOT `swing:` - this is different from other structures!
- type: derived_zone
  key: fib_zones
  depends_on: {source: swing}   # CRITICAL: Must use `source:` not `swing:`
  params:
    levels: [0.382, 0.5, 0.618]
    mode: retracement
    max_active: 5        # K slots (max zones tracked)
    width_pct: 0.002     # 0.2% zone width
  # Slot outputs: zone0_lower, zone0_upper, zone0_state, zone0_touched_this_bar...
  # Aggregate outputs: active_count, any_active, any_touched, any_inside
```

### Referencing Structures in Actions

Use the `key` field value as the `feature_id`:

```yaml
actions:
  entry_long:
    all:
      # Reference structure by key
      - lhs: {feature_id: "swing", field: "high_level"}
        op: ">"
        rhs: 0
      # Trend direction check
      - lhs: {feature_id: "trend", field: "direction"}
        op: "=="
        rhs: 1
      # Fibonacci level proximity
      - lhs: {feature_id: "close"}
        op: "near_pct"
        rhs: {feature_id: "fib", field: "level_0.618"}
        tolerance: 0.005
```

---

## 4. Actions (Entry/Exit Rules)

Actions define when to enter and exit positions.

### Valid Action Types

| Action | Description |
|--------|-------------|
| `entry_long` | Enter long position |
| `entry_short` | Enter short position |
| `exit_long` | Exit long position |
| `exit_short` | Exit short position |
| `exit_all` | Exit all positions |
| `no_action` | Do nothing |

### Basic Syntax

```yaml
actions:
  # Simple condition
  entry_long:
    - ["ema_9", ">", "ema_21"]        # List = implicit "all"

  # Explicit all (AND)
  entry_long:
    all:
      - ["ema_9", ">", "ema_21"]
      - ["rsi_14", "<", 70]

  # Explicit any (OR)
  exit_long:
    any:
      - ["ema_9", "<", "ema_21"]
      - ["rsi_14", ">", 80]
```

### Cases Syntax (First-Match)

```yaml
actions:
  - id: entry
    cases:
      - when:
          all:
            - ["rsi_14", "<", 30]
            - ["ema_9", ">", "ema_21"]
        emit:
          - action: entry_long
      - when:
          all:
            - ["rsi_14", ">", 70]
            - ["ema_9", "<", "ema_21"]
        emit:
          - action: entry_short
    else:
      emit:
        - action: no_action
```

### Partial Exits

```yaml
emit:
  - action: exit_long
    percent: 50            # Close 50% of position
```

### Dynamic Metadata

```yaml
emit:
  - action: entry_long
    metadata:
      entry_atr: {feature_id: "atr_14"}       # Captured at entry
      entry_rsi: {feature_id: "rsi_14"}
      entry_reason: "oversold_bounce"          # Static string
```

---

## 5. Operators

### Condition Syntax Formats

Two equivalent syntaxes are supported for conditions:

#### Shorthand List Format (Recommended)

Clean, readable syntax for most conditions:

```yaml
# 3-element: [lhs, operator, rhs]
- ["ema_9", ">", "ema_21"]
- ["rsi_14", "<", 30]
- ["zone.state", "==", "ACTIVE"]
- ["ema_9", "cross_above", "ema_21"]
- ["rsi_14", "between", [30, 70]]

# 4-element: [lhs, proximity_op, rhs, tolerance]
# Only for near_pct and near_abs which require tolerance
- ["close", "near_pct", {feature_id: "fib", field: "level_0.618"}, 0.5]
- ["close", "near_abs", "swing.high_level", 50]
```

#### Verbose Dict Format

Full control when you need explicit `field:` or `offset:` on feature references:

```yaml
- lhs: {feature_id: "ema_9", field: "value", offset: 1}
  op: ">"
  rhs: {feature_id: "ema_21"}

- lhs: {feature_id: "close"}
  op: "near_pct"
  rhs: {feature_id: "fib", field: "level_0.618"}
  tolerance: 0.005
```

#### When to Use Which

| Use Case | Format |
|----------|--------|
| Simple comparisons | Shorthand 3-element |
| Proximity checks | Shorthand 4-element |
| Need `offset:` for lookback | Verbose dict |
| Need explicit `field:` | Either (shorthand supports `{feature_id, field}` in any position) |

### Comparison Operators

**Symbol operators are the canonical form (refactored 2026-01-09).**

| Operator | Description | Type Restriction | Example |
|----------|-------------|------------------|---------|
| `>` | Greater than | Numeric only | `["ema_9", ">", "ema_21"]` |
| `<` | Less than | Numeric only | `["rsi_14", "<", 30]` |
| `>=` | Greater or equal | Numeric only | `["volume", ">=", "volume_avg"]` |
| `<=` | Less or equal | Numeric only | `["atr_14", "<=", 50]` |
| `==` | Equal | Discrete only (NOT float!) | `["trend.direction", "==", 1]` |
| `!=` | Not equal | Discrete only (NOT float!) | `["zone.state", "!=", "BROKEN"]` |

### Range Operators

```yaml
# between - range check (inclusive)
- ["rsi_14", "between", [30, 70]]
# Verbose form:
- lhs: {feature_id: "rsi_14"}
  op: between
  rhs: {low: 30, high: 70}

# near_abs - absolute tolerance (4-element shorthand)
- ["close", "near_abs", "swing.high_level", 50]
# Verbose form:
- lhs: {feature_id: "close"}
  op: near_abs
  rhs: {feature_id: "swing", field: "high_level"}
  tolerance: 50.0     # Within $50

# near_pct - percentage tolerance (4-element shorthand)
- ["close", "near_pct", {feature_id: "fib", field: "level_0.618"}, 0.5]
# Verbose form:
- lhs: {feature_id: "close"}
  op: near_pct
  rhs: {feature_id: "fib", field: "level_0.618"}
  tolerance: 0.005    # Within 0.5%
```

### Set Operator

```yaml
# in - membership (discrete types only)
- lhs: {feature_id: "trend", field: "direction"}
  op: in
  rhs: [1, 0]         # Bullish or neutral
```

### Crossover Operators (TradingView-aligned)

```yaml
# cross_above: prev <= target AND curr > target
- ["ema_9", "cross_above", "ema_21"]
# Explicit form:
- lhs: {feature_id: "ema_9"}
  op: cross_above
  rhs: {feature_id: "ema_21"}

# cross_below: prev >= target AND curr < target
- ["ema_9", "cross_below", "ema_21"]
```

### Boolean Logic

```yaml
# all - AND (all must be true)
all:
  - ["ema_9", ">", "ema_21"]
  - ["rsi_14", "<", 70]
  - ["volume", ">", "volume_avg"]

# any - OR (at least one true)
any:
  - ["rsi_14", "<", 30]   # Oversold
  - ["rsi_14", ">", 70]   # Overbought

# not - negation
not:
  - ["rsi_14", ">", 70]   # NOT overbought

# Nested logic: (A AND B) OR C
any:
  - all:
      - ["ema_9", ">", "ema_21"]
      - ["rsi_14", "<", 70]
  - ["close", ">", "swing.high_level"]
```

### Type Safety Rules

| Type | Allowed Operators | Notes |
|------|-------------------|-------|
| FLOAT | `>`, `<`, `>=`, `<=`, `between`, `near_abs`, `near_pct`, `cross_above`, `cross_below` | NOT `==`/`!=` (use `near_*`) |
| INT | All operators | `==`/`!=` allowed |
| BOOL | `==`, `!=`, `in` | True/False comparisons |
| ENUM | `==`, `!=`, `in` | Discrete state checks |
| STRING | `==`, `!=`, `in` | Text comparisons |

### Missing Value Handling

Values are treated as **MISSING** and comparisons return `false`:

| Condition | Result |
|-----------|--------|
| `None` | MISSING |
| `NaN` (float) | MISSING |
| `+Infinity` | MISSING |
| `-Infinity` | MISSING |
| Feature not found | MISSING |
| Offset exceeds history | MISSING |

```yaml
# If rsi_14 is NaN, this returns false (not error)
- ["rsi_14", ">", 50]

# If previous bar doesn't exist, crossover returns false
- ["ema_9", "cross_above", "ema_21"]
```

### SetupRef Circular Reference Protection

Setup references are protected against infinite recursion:

```yaml
# If setup_a references setup_b which references setup_a:
# → Returns INTERNAL_ERROR with "Circular setup reference detected"
```

---

## 6. Arithmetic DSL

Inline arithmetic expressions for difference thresholds, ratios, etc.

### Syntax

```yaml
# Basic: ema_9 - ema_21 > 100
- lhs: ["ema_9", "-", "ema_21"]
  op: ">"
  rhs: 100

# Nested: (ema_9 - ema_21) / atr_14 > 2
- lhs: [["ema_9", "-", "ema_21"], "/", "atr_14"]
  op: ">"
  rhs: 2.0

# In RHS: close > swing_high - 10
- lhs: "close"
  op: ">"
  rhs: ["swing_high", "-", 10]
```

### Operations

| Symbol | Type | Notes |
|--------|------|-------|
| `+` | add | numeric + numeric |
| `-` | subtract | numeric - numeric |
| `*` | multiply | numeric * numeric |
| `/` | divide | div by zero -> None (fails condition) |
| `%` | modulo | int % int |

### Use Cases

```yaml
# EMA difference threshold
- lhs: ["ema_9", "-", "ema_21"]
  op: ">"
  rhs: 100

# Volume spike ratio
- lhs: ["volume", "/", "volume_sma_20"]
  op: ">"
  rhs: 2.0

# Percent change
- lhs: [["close", "-", "open"], "/", "open"]
  op: ">"
  rhs: 0.01    # > 1% green candle

# Normalized position in range
- lhs: [["close", "-", "low"], "/", ["high", "-", "low"]]
  op: ">"
  rhs: 0.8    # Close in top 20% of bar range
```

---

## 7. Window Operators

Check conditions over multiple bars.

### Bar-Based Windows

```yaml
# holds_for - ALL N bars must satisfy condition
holds_for:
  bars: 5
  anchor_tf: "1m"       # Optional: scale to 1m bars
  expr:
    - ["rsi_14", ">", 50]

# occurred_within - at least ONE bar satisfied
occurred_within:
  bars: 10
  expr:
    - ["ema_9", "cross_above", "ema_21"]

# count_true - at least M of N bars satisfied
count_true:
  bars: 20
  min_true: 10          # At least 10 of 20 bars
  expr:
    - ["volume", ">", "volume_sma_20"]
```

### Duration-Based Windows (Recommended for Cross-TF)

```yaml
# holds_for_duration - condition true for time period
holds_for_duration:
  duration: "30m"       # 30 minutes
  expr:
    - ["rsi_14", ">", 70]

# occurred_within_duration - event within time period
occurred_within_duration:
  duration: "1h"
  expr:
    - ["last_price", "cross_above", "vwap"]

# count_true_duration - frequency in time period
count_true_duration:
  duration: "2h"
  min_true: 30          # At least 30 minutes true
  expr:
    - ["volume", ">", "volume_sma_20"]
```

**Duration formats:** `"5m"`, `"15m"`, `"30m"`, `"1h"`, `"4h"`, `"8h"`, `"1d"` (supports `m`, `h`, `d` - case-insensitive, e.g., `"1D"` = `"1d"`)

**Limitations:**
- Duration ceiling: 24h (1440 minutes) maximum
- Duration must be >= anchor_tf (e.g., can't use `"5m"` with 15m anchor)
- Max 500 bars after conversion to anchor_tf bars
- At 1m anchor: max ~8h (480 bars); at 15m anchor: up to 1d (96 bars); at 1h anchor: 1d (24 bars)

### Why anchor_tf Matters

```yaml
# PROBLEM: Bar offsets shift at different TF rates
holds_for:
  bars: 5              # No anchor_tf
  expr:
    - ["last_price", ">", "ema_50_4h"]
# last_price shifts 1m bars, ema_50_4h shifts 4h bars - misaligned!

# SOLUTION: Use duration or anchor_tf
holds_for_duration:
  duration: "5m"       # Both sample at 1m rate
  expr:
    - ["last_price", ">", "ema_50_4h"]
```

---

## 8. Multi-Timeframe (MultiTF)

**MultiTF = Multi-TimeFrame** - The capability to use features from multiple timeframes in a single strategy.

### Valid Timeframes (Bybit API)

**Bybit intervals**: `1,3,5,15,30,60,120,240,360,720,D,W,M`
**Internal format**: `1m,3m,5m,15m,30m,1h,2h,4h,6h,12h,D,W,M`

**NOTE**: 8h is NOT a valid Bybit interval. Use 6h or 12h instead.

**IMPORTANT - Timeframe vs Duration:**
- **Timeframe** (`tf:`, `high_tf:`): Bybit candle interval → use `D` (not `1d`)
- **Duration** (window operators): Time period → use `"1d"` or `"8h"` (any hour/minute/day value)

### Terminology Clarification

| Term | Meaning |
|------|---------|
| **MultiTF** (Multi-TimeFrame) | The capability to use multiple timeframes |
| **ExecTF** / `tf` | Execution timeframe - can be ANY value (1m, 5m, 15m, 1h, 4h, etc.) |
| **HighTF** / `high_tf` | Any timeframe higher than ExecTF for context (6h, 12h, D) |
| **MedTF** / `med_tf` | 30m, 1h, 2h, 4h - trade bias + structure |
| **LowTF** / `low_tf` | 1m, 3m, 5m, 15m - execution timing |

**Key insight:** `tf` (ExecTF) can be any timeframe you choose. There's no fixed role hierarchy - it's all relative to your chosen execution timeframe.

### Config Fields (Optional Higher TFs)

```yaml
tf: "15m"           # Execution TF - engine steps bar-by-bar at this TF
med_tf: "1h"        # Optional: intermediate TF for context (unused if not needed)
high_tf: "4h"       # Optional: higher TF for trend/levels
```

**Note:** The `med_tf:` and `high_tf:` config fields are optional convenience aliases. You can also specify TF directly on features via the `tf:` field.

### Feature TF Assignment

```yaml
features:
  # Execution TF (implied when no tf: specified)
  ema_9:
    indicator: ema
    params: {length: 9}
    # tf defaults to execution_tf (15m in this example)

  # Explicit higher TF feature
  ema_50_1h:
    indicator: ema
    params: {length: 50}
    tf: "1h"              # Higher than 15m exec -> forward-fills

  ema_200_4h:
    indicator: ema
    params: {length: 200}
    tf: "4h"              # Higher than 15m exec -> forward-fills
```

### Forward-Fill Behavior

**Key Concept:** Any TF slower than exec forward-fills until its bar closes.

```
exec bars (15m):  |  1  |  2  |  3  |  4  |  5  |  6  |  7  |  8  |
                  +-----+-----+-----+-----+-----+-----+-----+-----+
1h bars:          |          1h bar 0           |      1h bar 1    ...
                  '---- 1h values unchanged ----'
                        (forward-filled)
```

- **exec features:** Update every exec bar (no forward-fill)
- **Higher TF features:** Forward-fill until their bar closes

**No lookahead:** Values always reflect the last CLOSED bar, never partial/forming bars.

### Multi-Timeframe Strategy Example

```yaml
version: "3.0.0"
name: "multi_tf_trend_strategy"
description: "Trade with 4h trend, execute on 15m"

symbol: "BTCUSDT"
tf: "15m"            # Execution TF
high_tf: "4h"        # Higher TF for trend context

features:
  # Exec TF (15m) - entry/exit signals
  ema_9:
    indicator: ema
    params: {length: 9}
  ema_21:
    indicator: ema
    params: {length: 21}

  # Higher TF (4h) - trend filter
  ema_50_4h:
    indicator: ema
    params: {length: 50}
    tf: "4h"
  ema_200_4h:
    indicator: ema
    params: {length: 200}
    tf: "4h"

actions:
  entry_long:
    all:
      # 4h trend filter: uptrend
      - ["ema_50_4h", ">", "ema_200_4h"]
      # 15m signal: golden cross
      - cross_above: ["ema_9", "ema_21"]

  exit_long:
    any:
      # 4h reversal
      - ["ema_50_4h", "<", "ema_200_4h"]
      # 15m exit
      - cross_below: ["ema_9", "ema_21"]
```

### 1m Action Model

The engine evaluates signals every 1m within each exec bar. This enables precise entry/exit timing.

```yaml
# Use last_price for precise cross-TF entries (1m resolution)
actions:
  entry_long:
    all:
      - ["last_price", "cross_above", "ema_200_4h"]  # Checks every 1m
      - ["rsi_14", "<", 50]
```

| Feature | Update Rate | Use Case |
|---------|-------------|----------|
| `last_price` | Every 1m | Precise entries, cross-TF comparisons |
| `close` | Per exec bar | Bar-level conditions |
| Higher TF features | Forward-fill | Trend context (update on their bar close) |

**Why 1m resolution matters:** If exec is 15m, `close` only updates 4x per hour. But `last_price` updates 60x per hour, allowing precise entry when price crosses a level.

### HighTF Structures (Multi-Timeframe Structure Detection)

Structures can be computed on higher timeframes for trend context:

```yaml
structures:
  # Exec TF structures (15m)
  exec:
    - type: swing
      key: swing
      params: {left: 5, right: 5}
    - type: trend
      key: trend
      depends_on: {swing: swing}

  # HighTF structures (4h) - forward-fill between closes
  high_tf:
    "4h":
      - type: swing
        key: swing_4h
        params: {left: 5, right: 5}
      - type: trend
        key: trend_4h
        depends_on: {swing: swing_4h}
    "1h":
      - type: swing
        key: swing_1h
        params: {left: 3, right: 3}
```

**Key behavior:**
- HighTF structures forward-fill until their bar closes (same as indicators)
- Reference by key in actions: `{feature_id: "trend_4h", field: "direction"}`

### MultiTF Confluence Patterns

**Pattern 1: Exec Swing + HighTF Trend Filter**
```yaml
actions:
  entry_long:
    all:
      # HighTF trend is UP
      - [{feature_id: trend_4h, field: direction}, "==", 1]
      # Exec swing low exists (bounce setup)
      - [{feature_id: swing, field: low_level}, ">", 0]
      # Price near exec swing low
      - [close, "near_pct", {feature_id: swing, field: low_level}, 2.0]
```

**Pattern 2: Dual-Timeframe Trend Alignment**
```yaml
actions:
  entry_long:
    all:
      # Both TFs trending UP - strongest signal
      - [{feature_id: trend, field: direction}, "==", 1]
      - [{feature_id: trend_4h, field: direction}, "==", 1]
```

**Pattern 3: HighTF Fib + Exec Swing**
```yaml
structures:
  exec:
    - type: swing
      key: swing
      params: {left: 5, right: 5}
  high_tf:
    "4h":
      - type: swing
        key: swing_4h
        params: {left: 5, right: 5}
      - type: fibonacci
        key: fib_4h
        depends_on: {swing: swing_4h}
        params:
          levels: [0.5, 0.618]
          mode: retracement

actions:
  entry_long:
    all:
      # Price near HighTF 0.618 fib level
      - [close, "near_pct", {feature_id: fib_4h, field: level_0.618}, 1.5]
      # Exec swing confirms support
      - [{feature_id: swing, field: low_level}, ">", 0]
```

---

## 9. Risk Model

### Full Risk Configuration

```yaml
risk_model:
  # STOP LOSS
  stop_loss:
    type: "percent"        # Stop loss type
    value: 2.0             # 2% stop

  # TAKE PROFIT
  take_profit:
    type: "rr_ratio"       # Take profit type
    value: 2.0             # 2:1 reward/risk

  # POSITION SIZING
  sizing:
    model: "percent_equity"
    value: 2.0             # 2% of equity per trade
    max_leverage: 3.0      # Maximum leverage
```

### Stop Loss Types

**Percentage values are ROI-based** (percentage of margin), not price-based.
With 10x leverage and 2% SL, price moves 0.2% against you = 2% margin loss.

Formula: `price_distance = entry × (roi_pct / 100) / leverage`

```yaml
# ROI-based percentage stop (RECOMMENDED)
stop_loss:
  type: "percent"
  value: 2.0               # 2% ROI loss (at 10x lev = 0.2% price move)

# ATR-based stop
stop_loss:
  type: "atr_multiple"
  value: 2.0               # 2x ATR from entry
  atr_feature_id: "atr_14"

# Structure-based stop (swing low/high)
stop_loss:
  type: "structure"
  value: 1.0               # Multiplier
  buffer_pct: 0.1          # 0.1% buffer below level

# Fixed points stop
stop_loss:
  type: "fixed_points"
  value: 100               # $100 from entry (price-based)
```

### Take Profit Types

**Percentage values are ROI-based** (percentage of margin gain).
With 10x leverage and 4% TP, price moves 0.4% in your favor = 4% margin gain.

```yaml
# Risk-reward ratio
take_profit:
  type: "rr_ratio"
  value: 2.0               # 2R target (2x stop distance)

# ROI-based percentage (RECOMMENDED)
take_profit:
  type: "percent"
  value: 4.0               # 4% ROI gain (at 10x lev = 0.4% price move)

# ATR-based
take_profit:
  type: "atr_multiple"
  value: 3.0               # 3x ATR from entry
  atr_feature_id: "atr_14"

# Fixed points
take_profit:
  type: "fixed_points"
  value: 200               # $200 from entry (price-based)
```

### Sizing Models

```yaml
# Percent of equity as margin, then leverage
sizing:
  model: "percent_equity"
  value: 10.0              # 10% of equity as margin
  max_leverage: 3.0        # x leverage = 30% notional

# Risk-based sizing (sizes to risk % on stop)
sizing:
  model: "risk_based"
  value: 1.0               # 1% equity at risk
  max_leverage: 10.0

# Fixed notional
sizing:
  model: "fixed_usdt"
  value: 1000              # $1000 per trade
```

### Simplified Risk Config

```yaml
# Shorthand (most common) - percentages are ROI-based
risk:
  stop_loss_pct: 2.0       # 2% ROI loss (2% of margin at risk)
  take_profit_pct: 4.0     # 4% ROI gain (4% margin profit)
  max_position_pct: 100.0  # Max position as % of equity x leverage
```

**ROI vs Price Movement (critical for leveraged trading):**

| Leverage | 2% SL (ROI) | Price Move | 4% TP (ROI) | Price Move |
|----------|-------------|------------|-------------|------------|
| 1x | 2% loss | 2.0% | 4% gain | 4.0% |
| 5x | 2% loss | 0.4% | 4% gain | 0.8% |
| 10x | 2% loss | 0.2% | 4% gain | 0.4% |
| 20x | 2% loss | 0.1% | 4% gain | 0.2% |

---

## 10. Order Sizing & Execution

### Sizing Flow

```
Signal Generated -> SimulatedRiskManager.size_order() -> SizingResult
                          |
              Sizing Model (percent_equity / risk_based / fixed_usdt)
                          |
              Cap: size_usdt <= equity x max_leverage
                          |
              ExecutionModel.fill_entry_order()
                          |
              Slippage -> Fee -> Fill
```

### Sizing Models Explained

**1. percent_equity (Default)**
```
margin = equity x (risk_pct / 100)
position = margin x leverage

Example: $10,000 equity, 10% risk, 3x leverage
- margin = $10,000 x 10% = $1,000
- position = $1,000 x 3 = $3,000
```

**2. risk_based (Kelly-style)**
```
risk_dollars = equity x (risk_pct / 100)
size = risk_dollars x entry_price / stop_distance

Example: $10,000 equity, 1% risk, 2% stop
- risk_dollars = $100
- stop_distance = entry x 0.02 = $1,284
- size = $100 x $64,200 / $1,284 = $5,000
```

**3. fixed_usdt**
```
size = fixed_amount (capped by max_leverage)

Example: fixed $1000, max 10x leverage on $10,000
- size = $1,000 (no calculation, just cap check)
```

### Execution Model

| Component | Default | Description |
|-----------|---------|-------------|
| Taker Fee | 0.06% | Market order fee |
| Maker Fee | 0.01% | Limit order fee |
| Slippage | Configurable | Applied to fill price |

### Fee Calculation

```python
# Entry fee (taker)
entry_fee = notional x taker_fee_rate  # e.g., $10,000 x 0.0006 = $6

# Required margin (Bybit formula)
required = (notional x IMR) + (notional x taker_fee_rate)
# At 2x leverage (IMR=50%): $10,000 x 0.5 + $6 = $5,006

# Max fillable at 100% equity
max_notional = equity / (IMR + fee_rate)
# $10,000 / (0.5 + 0.0006) = $9,988
```

---

## 11. Complete Examples

### Example 1: Simple EMA Crossover

```yaml
version: "3.0.0"
name: "ema_crossover"
description: "Classic EMA 9/21 crossover"

symbol: "BTCUSDT"
tf: "1h"

features:
  ema_9:
    indicator: ema
    params: {length: 9}
  ema_21:
    indicator: ema
    params: {length: 21}

actions:
  entry_long:
    - cross_above: ["ema_9", "ema_21"]
  exit_long:
    - cross_below: ["ema_9", "ema_21"]
  entry_short:
    - cross_below: ["ema_9", "ema_21"]
  exit_short:
    - cross_above: ["ema_9", "ema_21"]

position_policy:
  mode: "long_short"

risk:
  stop_loss_pct: 2.0
  take_profit_pct: 4.0
```

### Example 2: RSI + Volume Filter

```yaml
version: "3.0.0"
name: "rsi_volume_strategy"
description: "RSI oversold with volume confirmation"

symbol: "ETHUSDT"
tf: "15m"

features:
  rsi_14:
    indicator: rsi
    params: {length: 14}
  volume_sma_20:
    indicator: sma
    source: volume
    params: {length: 20}
  ema_50:
    indicator: ema
    params: {length: 50}

actions:
  entry_long:
    all:
      - ["rsi_14", "<", 30]                          # Oversold
      - ["volume", ">", "volume_sma_20"]             # Volume spike
      - ["close", ">", "ema_50"]                     # Above trend

  exit_long:
    any:
      - ["rsi_14", ">", 70]                          # Overbought
      - ["close", "<", "ema_50"]                     # Trend break

risk:
  stop_loss_pct: 1.5
  take_profit_pct: 3.0
```

### Example 3: Multi-Timeframe Trend + Fib Zones

```yaml
version: "3.0.0"
name: "multi_tf_fib_zones"
description: "Trade 4h trend pullbacks to fib zones on 15m"

symbol: "BTCUSDT"
tf: "15m"
high_tf: "4h"

features:
  # Exec TF (15m)
  rsi_14:
    indicator: rsi
    params: {length: 14}
  ema_20:
    indicator: ema
    params: {length: 20}

  # Higher TF (4h)
  ema_50_4h:
    indicator: ema
    params: {length: 50}
    tf: "4h"

structures:
  swing:
    detector: swing
    params: {left: 5, right: 5}
  fib:
    detector: fibonacci
    depends_on: {swing: swing}
    params:
      levels: [0.382, 0.5, 0.618]
      mode: retracement

actions:
  entry_long:
    all:
      # HighTF trend filter
      - ["close", ">", "ema_50_4h"]
      # Near fib level
      - lhs: {feature_id: "close"}
        op: near_pct
        rhs: {feature_id: "fib", field: "level_0.618"}
        tolerance: 0.005
      # RSI confirmation
      - ["rsi_14", "<", 40]

  exit_long:
    any:
      - ["rsi_14", ">", 70]
      - ["close", "<", "ema_50_4h"]

risk:
  stop_loss_pct: 2.0
  take_profit_pct: 4.0
```

### Example 4: Breakout with Volume Confirmation

```yaml
version: "3.0.0"
name: "breakout_volume"
description: "Breakout above rolling high with volume spike"

symbol: "BTCUSDT"
tf: "15m"

features:
  atr_14:
    indicator: atr
    params: {length: 14}
  volume_sma_20:
    indicator: sma
    source: volume
    params: {length: 20}

structures:
  rolling_high:
    detector: rolling_window
    params:
      mode: max
      size: 20
      source: high

actions:
  entry_long:
    all:
      # Breakout above 20-bar high
      - ["close", ">", "rolling_high.value"]
      # Volume > 2x average (using arithmetic)
      - lhs: ["volume", "/", "volume_sma_20"]
        op: ">"
        rhs: 2.0
      # Volatility filter - ATR not too high
      - ["atr_14", "<", 500]

  exit_long:
    any:
      # Exit if price drops 1.5 ATR from high
      - lhs: ["high", "-", "close"]
        op: ">"
        rhs: {feature_id: "atr_14"}

risk_model:
  stop_loss:
    type: "atr_multiple"
    value: 2.0
    atr_feature_id: "atr_14"
  take_profit:
    type: "rr_ratio"
    value: 2.0
  sizing:
    model: "risk_based"
    value: 1.0
    max_leverage: 5.0
```

### Example 5: Window Operators + Derived Zones

```yaml
version: "3.0.0"
name: "zone_momentum"
description: "Enter zones only after recent RSI recovery"

symbol: "BTCUSDT"
tf: "1h"

features:
  rsi_14:
    indicator: rsi
    params: {length: 14}
  atr_14:
    indicator: atr
    params: {length: 14}

structures:
  swing:
    detector: swing
    params: {left: 5, right: 5}
  fib_zones:
    detector: derived_zone
    depends_on: {source: swing}  # NOTE: derived_zone uses `source:` not `swing:`
    params:
      levels: [0.5, 0.618]
      mode: retracement
      max_active: 3
      width_pct: 0.002

actions:
  entry_long:
    all:
      # Price in an active zone
      - lhs: {feature_id: "fib_zones", field: "any_inside"}
        op: "=="
        rhs: true
      # RSI was oversold within last 10 bars
      - occurred_within:
          bars: 10
          expr:
            - ["rsi_14", "<", 30]
      # Currently recovering
      - ["rsi_14", ">", 35]

  exit_long:
    any:
      # Zone touched and bounced
      - lhs: {feature_id: "fib_zones", field: "any_touched"}
        op: "=="
        rhs: true
      # RSI overbought for 3 bars
      - holds_for:
          bars: 3
          expr:
            - ["rsi_14", ">", 70]

risk:
  stop_loss_pct: 2.0
  take_profit_pct: 4.0
```

### Example 6: ICT Market Structure (BOS/CHoCH)

```yaml
version: "3.0.0"
name: "ict_market_structure"
description: "Trade BOS continuations, exit on CHoCH reversals"

symbol: "BTCUSDT"
tf: "15m"

account:
  starting_equity_usdt: 10000.0
  max_leverage: 3.0
  margin_mode: "isolated_usdt"
  fee_model:
    taker_bps: 5.5
    maker_bps: 2.0
  slippage_bps: 2.0

features:
  atr_14:
    indicator: atr
    params: {length: 14}
  rsi_14:
    indicator: rsi
    params: {length: 14}

structures:
  exec:
    - type: swing
      key: swing
      params:
        left: 5
        right: 5
        atr_key: atr_14      # Filter insignificant swings

    - type: market_structure
      key: ms
      depends_on:
        swing: swing

actions:
  - id: entry
    cases:
      # Bullish BOS with RSI confirmation (not overbought)
      - when:
          all:
            - [{feature_id: "ms", field: "bos_this_bar"}, "==", true]
            - [{feature_id: "ms", field: "bias"}, "==", 1]
            - ["rsi_14", "<", 70]
        emit:
          - action: entry_long
      # Bearish BOS with RSI confirmation (not oversold)
      - when:
          all:
            - [{feature_id: "ms", field: "bos_this_bar"}, "==", true]
            - [{feature_id: "ms", field: "bias"}, "==", -1]
            - ["rsi_14", ">", 30]
        emit:
          - action: entry_short

  - id: exit
    cases:
      # Exit long on bearish CHoCH (trend reversal)
      - when:
          all:
            - [{feature_id: "ms", field: "choch_this_bar"}, "==", true]
            - [{feature_id: "ms", field: "choch_direction"}, "==", -1]
        emit:
          - action: exit_long
      # Exit short on bullish CHoCH (trend reversal)
      - when:
          all:
            - [{feature_id: "ms", field: "choch_this_bar"}, "==", true]
            - [{feature_id: "ms", field: "choch_direction"}, "==", 1]
        emit:
          - action: exit_short

position_policy:
  mode: "long_short"
  exit_mode: "first_hit"
  max_positions_per_symbol: 1

risk:
  stop_loss_pct: 3.0
  take_profit_pct: 6.0
  max_position_pct: 50.0
```

---

## Quick Reference Card

### Operators (Symbols Only - Refactored 2026-01-09)

| Op | Types | Example |
|----|-------|---------|
| `>` | Numeric | `["ema_9", ">", "ema_21"]` |
| `<` | Numeric | `["rsi_14", "<", 30]` |
| `>=` | Numeric | `["volume", ">=", "vol_avg"]` |
| `<=` | Numeric | `["atr_14", "<=", 50]` |
| `==` | Discrete | `["trend.direction", "==", 1]` |
| `!=` | Discrete | `["zone.state", "!=", "BROKEN"]` |
| `between` | Numeric | `{op: "between", rhs: {low: 30, high: 70}}` |
| `near_abs` | Numeric | `{op: "near_abs", tolerance: 10}` |
| `near_pct` | Numeric | `{op: "near_pct", tolerance: 0.005}` |
| `in` | Discrete | `{op: "in", rhs: [1, 0, -1]}` |
| `cross_above` | Numeric | `["ema_9", "cross_above", "ema_21"]` |
| `cross_below` | Numeric | `["ema_9", "cross_below", "ema_21"]` |

### Arithmetic

| Op | Example |
|----|---------|
| `+` | `["ema_9", "+", "atr_14"]` |
| `-` | `["ema_9", "-", "ema_21"]` |
| `*` | `["atr_14", "*", 2]` |
| `/` | `["volume", "/", "vol_avg"]` |
| `%` | `["bar_idx", "%", 5]` |

### Boolean

| Op | Example |
|----|---------|
| `all` | `all: [cond1, cond2]` (AND) |
| `any` | `any: [cond1, cond2]` (OR) |
| `not` | `not: condition` |

### Windows

| Op | Example |
|----|---------|
| `holds_for` | `{bars: 5, expr: ...}` |
| `occurred_within` | `{bars: 10, expr: ...}` |
| `count_true` | `{bars: 20, min_true: 5, expr: ...}` |
| `holds_for_duration` | `{duration: "30m", expr: ...}` |

---

## Deprecation Notes

### Deprecated Fields (Do NOT Use)

| Deprecated | Use Instead | Notes |
|------------|-------------|-------|
| `blocks:` (top-level) | `actions:` | Renamed in v3.0.0 |
| `signal_rules:` | `actions:` | Legacy format |
| `margin_mode: "isolated"` | `margin_mode: "isolated_usdt"` | Be explicit about currency |

### Migration Examples

```yaml
# DEPRECATED
blocks:
  entry_long:
    - ["ema_9", ">", "ema_21"]

# CORRECT
actions:
  entry_long:
    - ["ema_9", ">", "ema_21"]
```

```yaml
# DEPRECATED
account:
  margin_mode: "isolated"  # Ambiguous

# CORRECT
account:
  margin_mode: "isolated_usdt"  # Explicit
```

### Engine Behavior on Deprecated Fields

Currently the engine still accepts `blocks:` and `margin_mode: "isolated"` for backward compatibility. This will be removed. Always use the correct forms.

---

## Document History

| Date | Change |
|------|--------|
| 2026-01-08 | Created as canonical source, consolidated from PLAY_SYNTAX.md + DSL_REFERENCE.md |
| 2026-01-08 | Fixed MultiTF terminology (Multi-TimeFrame = capability, not role) |
| 2026-01-08 | Added exit_mode, variables, price features deep dive, deprecation notes |
| 2026-01-09 | Symbol operators now canonical (`>`, `<`, `>=`, `<=`, `==`, `!=`). Word forms removed. |
| 2026-01-09 | Added `!=` operator for discrete type comparisons |
| 2026-01-15 | Updated terminology: LowTF, MedTF, HighTF, ExecTF, MultiTF |
| 2026-01-16 | Added wave-based trend detector with strength, wave_count, last_hh/hl/lh/ll outputs |
| 2026-01-16 | Added market_structure detector (ICT BOS/CHoCH) with bias, bos_this_bar, choch_this_bar outputs |
| 2026-01-16 | Added Example 6: ICT Market Structure strategy |

---

*This is the single source of truth for Play DSL syntax. Update this document when engine behavior changes.*
