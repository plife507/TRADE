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

3. **Modify the appropriate component (human-in-the-loop):**
   - Engine bug → fix engine
   - Doc error → fix cookbook
   - Design flaw → **STOP and discuss with human** before redesigning DSL

---

## Table of Contents

1. [Play Structure](#1-play-structure)
2. [Features (Indicators)](#2-features-indicators)
3. [Structures (Market Structure)](#3-structures-market-structure)
4. [Actions (Entry/Exit Rules)](#4-actions-entryexit-rules)
5. [Operators](#5-operators)
6. [Arithmetic DSL](#6-arithmetic-dsl)
7. [Window Operators](#7-window-operators)
8. [Multi-Timeframe](#8-multi-timeframe)
9. [Risk Model](#9-risk-model)
10. [Order Sizing & Execution](#10-order-sizing--execution)
11. [Complete Examples](#11-complete-examples)
12. [Synthetic Data for Validation](#12-synthetic-data-for-validation)
13. [Quick Reference Card](#quick-reference-card)

---

## 1. Play Structure

A Play is the complete backtest-ready strategy unit.

### Default Values Reference

> **Source of truth:** `config/defaults.yml`
> **Fee source:** [Bybit Trading Fees](https://www.bybit.com/en/help-center/article/Trading-Fee-Structure/)

These are the system defaults. When not specified in a Play, these values apply:

| Field | Default | Source | Notes |
|-------|---------|--------|-------|
| **Fees (Bybit Non-VIP)** ||||
| `taker_bps` | 5.5 | Bybit API | 0.055% taker fee |
| `maker_bps` | 2.0 | Bybit API | 0.02% maker fee |
| `liquidation_bps` | 5.5 | Bybit API | Same as taker |
| **Margin Model** ||||
| `margin.mode` | `isolated` | config | No cross-margin support |
| `margin.position_mode` | `oneway` | config | No hedge mode support |
| `margin.maintenance_margin_rate` | 0.005 | Bybit | 0.5% MMR lowest tier |
| **Execution** ||||
| `slippage_bps` | 2.0 | config | Conservative estimate |
| `min_trade_notional_usdt` | 10.0 | config | Minimum trade size |
| **Risk** ||||
| `max_leverage` | 1.0 | config | Conservative default |
| `risk_per_trade_pct` | 1.0 | config | 1% risk per trade |
| **Position Policy** ||||
| `mode` | `long_only` | config | Conservative default |
| `exit_mode` | `sl_tp_only` | config | Mechanical exits |
| `max_positions_per_symbol` | 1 | config | Single position |
| **Account** ||||
| `starting_equity_usdt` | 10000.0 | config | Default starting capital |

**IMPORTANT:** For production, Plays should explicitly set all values.
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
# MARKET & TIMEFRAMES (3-Feed + Exec Role System)
# ═══════════════════════════════════════════════════════════════════════════════
symbol: "BTCUSDT"              # Trading pair (USDT pairs only)

# REQUIRED: Explicit timeframes section (3 timeframes + exec pointer)
timeframes:
  low_tf: "15m"                # Lowest analysis timeframe (1m, 3m, 5m, 15m)
  med_tf: "1h"                 # Medium timeframe for context (30m, 1h, 2h, 4h)
  high_tf: "D"                 # Highest timeframe for trend/levels (12h, D)
  exec: "low_tf"               # Which timeframe to step on: "low_tf", "med_tf", or "high_tf"

# Hierarchy rule: high_tf >= med_tf >= low_tf (in minutes)
# exec is a ROLE POINTER, not a 4th feed - it points to one of the 3 feeds
#
# USAGE PATTERN: Most strategies primarily use low_tf + med_tf for entries/structure.
# high_tf is optional - use it for daily bias, session boundaries, or anchor points.

# ═══════════════════════════════════════════════════════════════════════════════
# ACCOUNT CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════
account:
  starting_equity_usdt: 10000.0
  max_leverage: 3.0
  margin_mode: "isolated_usdt"  # Must be isolated_usdt
  min_trade_notional_usdt: 10.0
  fee_model:
    taker_bps: 5.5             # 0.055% taker fee (Bybit perpetuals)
    maker_bps: 2.0             # 0.02% maker fee (Bybit perpetuals)
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
  exec:
    - type: swing
      key: swing
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

**Reserved flags (not yet supported):**
- `allow_flip: false` - Position flipping (long→short in one action)
- `allow_scale_in: false` - Adding to existing positions
- `allow_scale_out: false` - Partial position reduction

These are reserved for future use and must remain `false`.

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
| Single-param + timeframe | `{type}_{param}_{tf}` | `ema_50_1h`, `rsi_14_4h` |
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
| **Explicit (slower than exec)** | Uses specified timeframe | Forward-fills between timeframe closes |
| **Explicit (faster than exec)** | Uses specified timeframe | Sampled at exec bar boundaries |

**Important: Inheritance is flat (one level only).** There is no feature-to-feature inheritance. Each feature either:
1. Has an explicit `tf:` → uses that value
2. Has no `tf:` → defaults to the Play's main `tf:`

The `source:` field (e.g., `source: volume`) changes the **input data**, not the timeframe.

#### How It Works

```yaml
tf: "15m"                      # Main execution timeframe

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

When a feature's timeframe is **slower** than the execution timeframe, its value remains constant (forward-fills) until the slower timeframe bar closes:

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
  ema_fast:           # BAD: unclear what timeframe
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

**Best practice:** Include timeframe in feature names when using explicit `tf:` override (e.g., `ema_50_4h`, `rsi_14_1h`). This makes DSL expressions self-documenting:

```yaml
# Clear: ema_9 is 15m (exec), ema_50_4h is 4h
- ["ema_9", ">", "ema_50_4h"]

# Unclear: what timeframe is ema_slow?
- ["ema_fast", ">", "ema_slow"]
```

#### Interaction with Built-in Price Features

Built-in price features have **fixed resolutions** that do NOT follow inheritance:

| Feature | Resolution | Inheritance |
|---------|------------|-------------|
| `last_price` | Always 1m | No (fixed) |
| `mark_price` | Always 1m | No (fixed) |
| `close`, `open`, `high`, `low`, `volume` | Always execution timeframe | No (fixed) |
| Declared features without `tf:` | Execution timeframe | **Yes (inherits)** |
| Declared features with `tf:` | Specified timeframe | No (explicit) |

This means `last_price` provides 1m precision regardless of your `tf:` setting, while indicator features follow the inheritance rules above.

### Complete Indicator Registry (43 Total)

**11 indicators support O(1) incremental computation** for live trading performance:
`ema`, `sma`, `rsi`, `atr`, `macd`, `bbands`, `stoch`, `adx`, `supertrend`, `cci`, `willr`

**Single-Output (25):**

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
| `uo` | `fast`, `medium`, `slow` | Ultimate Oscillator |
| `vwap` | (none) | Volume Weighted Avg Price |

**Multi-Output (18):**

| Indicator | Outputs | Params | Incremental |
|-----------|---------|--------|-------------|
| `macd` | `macd`, `signal`, `histogram` | `fast`, `slow`, `signal` | ✓ |
| `bbands` | `lower`, `middle`, `upper`, `bandwidth`, `percent_b` | `length`, `std` | ✓ |
| `stoch` | `k`, `d` | `k`, `d`, `smooth_k` | ✓ |
| `stochrsi` | `k`, `d` | `length`, `rsi_length`, `k`, `d` | |
| `adx` | `adx`, `dmp`, `dmn`, `adxr` | `length` | ✓ |
| `aroon` | `up`, `down`, `osc` | `length` | |
| `kc` | `lower`, `basis`, `upper` | `length`, `scalar` | |
| `donchian` | `lower`, `middle`, `upper` | `lower_length`, `upper_length` | |
| `supertrend` | `trend`, `direction`, `long`, `short` | `length`, `multiplier` | ✓ |
| `psar` | `long`, `short`, `af`, `reversal` | `af0`, `af`, `max_af` | |
| `squeeze` | `sqz`, `on`, `off`, `no_sqz` | `bb_length`, `bb_std`, `kc_length`, `kc_scalar` | |
| `vortex` | `vip`, `vim` | `length` | |
| `dm` | `dmp`, `dmn` | `length` | |
| `fisher` | `fisher`, `signal` | `length` | |
| `tsi` | `tsi`, `signal` | `fast`, `slow`, `signal` | |
| `kvo` | `kvo`, `signal` | `fast`, `slow`, `signal` | |
| `ppo` | `ppo`, `histogram`, `signal` | `fast`, `slow`, `signal` | |
| `trix` | `trix`, `signal` | `length`, `signal` | |

**Accessing multi-output fields:** Use `{feature_id: "indicator_key", field: "output_name"}` or shorthand `"indicator_key.output_name"`

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
| `last_price` | Precise entries, cross-timeframe comparisons, intra-bar TP/SL checks |
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

### Backtest vs Live Behavior Warning

> **IMPORTANT FOR LIVE TRADING:**
>
> In backtest mode, both `last_price` and `mark_price` are sourced from 1m bar close
> data for simplicity. In live trading, they come from different Bybit WebSocket feeds
> and can diverge significantly during volatile periods.
>
> **Implications:**
> - Unrealized PnL in backtest may not match live behavior during flash crashes
> - Strategies should be aware that mark_price stability protects against manipulation
> - Consider testing with extreme scenarios before going live

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

**Dependency syntax:**
- Most structures: `depends_on: {swing: <swing_key>}`
- `derived_zone` only: `depends_on: {source: <swing_key>}` (uses `source:` not `swing:`)

### Structure YAML Format (Role-Based)

The engine expects structures organized by timeframe role (`exec`, `high_tf`, `med_tf`):

```yaml
structures:
  # Execution timeframe structures (list format)
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

  # high_tf structures (nested by timeframe)
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

### Duration-Based Windows (Recommended for Cross-Timeframe)

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
# PROBLEM: Bar offsets shift at different timeframe rates
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

## 8. Multi-Timeframe

**Multi-Timeframe** - The capability to use features from multiple timeframes in a single strategy.

### 3-Feed + Exec Role Architecture

The timeframe system uses **3 feeds** with an **exec role pointer**:

| Feed | Role | Typical Values | Primary Use |
|------|------|----------------|-------------|
| `low_tf` | Lowest analysis timeframe | 1m, 3m, 5m, 15m | Entry timing, precise signals |
| `med_tf` | Medium timeframe for context | 30m, 1h, 2h, 4h | Structure, pullbacks, local trend |
| `high_tf` | Highest timeframe for bias | 12h, D | Daily bias, session anchors |
| `exec` | **Pointer** to which feed we step on | `"low_tf"`, `"med_tf"`, or `"high_tf"` | - |

**Key insight:** `exec` is NOT a 4th feed - it's an alias that points to one of the 3 feeds. This determines which timeframe's bar-close triggers signal evaluation.

> **TYPICAL USAGE:** Most strategies focus on `low_tf` + `med_tf`. The `high_tf` is optional and primarily
> used for: (1) daily trend bias with `D`, or (2) session boundaries/structure anchors with `12h`.

### Multi-Timeframe Best Practices

**The Top-Down Approach:**
1. **Higher timeframe (D/12h)** - Establish directional bias (bullish, bearish, or neutral)
2. **Medium timeframe (1h-4h)** - Identify structure, support/resistance, pullback zones
3. **Lower timeframe (5m-15m)** - Time precise entries when alignment occurs

**When Timeframes Align:**
- Higher timeframe trend is clear (e.g., daily EMA 50 > EMA 200)
- Medium timeframe structure supports the bias (e.g., price at support in uptrend)
- Lower timeframe provides entry signal (e.g., bullish cross, breakout confirmation)
- **Result:** High-probability trade setup

**When to Use Each high_tf Value:**

| Value | Best For | Example Use Case |
|-------|----------|------------------|
| `D` | Daily trend bias | EMA 50/200 golden cross, daily support/resistance |
| `12h` | Session anchors | Asian/London/NY session boundaries, swing structure |

**Common Mistakes to Avoid:**
- Starting analysis on lower timeframes (bottom-up) instead of top-down
- Using more than 3 timeframes (causes analysis paralysis)
- Trading against the higher timeframe trend
- Forcing trades when timeframes conflict - wait for alignment

### Valid Timeframes (Bybit API)

**Bybit intervals**: `1,3,5,15,30,60,120,240,360,720,D,W,M`
**Internal format**: `1m,3m,5m,15m,30m,1h,2h,4h,6h,12h,D,W,M`

**NOTE**: 8h is NOT a valid Bybit interval. Use 6h or 12h instead.

**IMPORTANT - Timeframe vs Duration:**
- **Timeframe** (`timeframes.low_tf:`): Bybit candle interval → use `D` (not `1d`)
- **Duration** (window operators): Time period → use `"1d"` or `"8h"` (any hour/minute/day value)

### Config Fields (REQUIRED)

```yaml
# REQUIRED: Explicit timeframes section (3 timeframes + exec pointer)
timeframes:
  low_tf: "15m"      # Lowest analysis timeframe - engine always loads this data
  med_tf: "1h"       # Medium timeframe for context (same as low_tf if single-timeframe)
  high_tf: "D"       # Highest timeframe for trend/levels (same as med_tf if dual-timeframe)
  exec: "low_tf"     # Which feed to step on: "low_tf", "med_tf", or "high_tf"
```

**Hierarchy rule:** `high_tf >= med_tf >= low_tf` (in minutes)

> **BEST PRACTICE:** Most strategies primarily use `low_tf` + `med_tf`. The higher timeframe
> provides overall trend context but is often optional. Use a top-down approach: establish
> directional bias on the higher timeframe, identify structure on the medium timeframe, then
> time entries on the lower timeframe.

### Exec Role Examples

```yaml
# Example 1: Standard day trading (exec on low_tf) - most common
timeframes:
  low_tf: "15m"     # ← exec points here (entry timing)
  med_tf: "1h"      # Structure and pullbacks
  high_tf: "D"      # Daily trend bias
  exec: "low_tf"
# Steps on 15m bars, forward-fills 1h and D

# Example 2: Swing trading (exec on med_tf)
timeframes:
  low_tf: "15m"     # Precise entry timing
  med_tf: "1h"      # ← exec points here (main analysis)
  high_tf: "12h"    # Session boundaries, anchor points
  exec: "med_tf"
# Steps on 1h bars, looks up 15m at close, forward-fills 12h

# Example 3: Single-timeframe (all same)
timeframes:
  low_tf: "15m"
  med_tf: "15m"
  high_tf: "15m"
  exec: "low_tf"
# All feeds are the same 15m data - simpler but less context
```

### Feature Timeframe Assignment

```yaml
features:
  # Execution timeframe (implied when no tf: specified)
  ema_9:
    indicator: ema
    params: {length: 9}
    # tf defaults to execution timeframe (15m in this example)

  # Explicit higher timeframe feature
  ema_50_1h:
    indicator: ema
    params: {length: 50}
    tf: "1h"              # Higher than 15m exec -> forward-fills

  ema_200_4h:
    indicator: ema
    params: {length: 200}
    tf: "4h"              # Higher than 15m exec -> forward-fills
```

### Forward-Fill Semantics

Forward-fill behavior depends on whether a timeframe is faster or slower than exec:

| Timeframe Relationship | Behavior |
|------------------------|----------|
| **Slower than exec** | Forward-fill (hold last closed bar value) |
| **Faster than exec** | Lookup most recent closed bar at exec close |
| **Equal to exec** | Direct access (no fill needed) |

```
Example: exec=low_tf (15m), med_tf=1h, high_tf=D

exec bars (15m):  |  1  |  2  |  3  |  4  |  5  |  6  |  7  |  8  |
                  +-----+-----+-----+-----+-----+-----+-----+-----+
1h bars:          |          1h bar 0           |      1h bar 1    ...
                  '---- 1h values unchanged ----'
                        (forward-filled)
```

**No lookahead:** Values always reflect the last CLOSED bar, never partial/forming bars.

### Execution Semantics

```
Signal evaluation: At execution timeframe bar close
Order execution:   At next 1m candle open (backtest) or live ticker (live)
```

The 1m quote feed (separate from the 3 analysis feeds) provides execution prices (`px.last`, `px.mark`).

### Multi-Timeframe Strategy Example

This example demonstrates the top-down approach: daily trend bias → 15m entry timing.

```yaml
version: "3.0.0"
name: "multi_tf_trend_strategy"
description: "Trade with daily trend bias, execute on 15m"

symbol: "BTCUSDT"
timeframes:
  low_tf: "15m"     # Execution timeframe - entry timing
  med_tf: "1h"      # Structure context (not used in this simple example)
  high_tf: "D"      # Daily trend bias
  exec: "low_tf"    # Step on 15m bars

features:
  # Execution timeframe (15m) - entry/exit signals
  ema_9:
    indicator: ema
    params: {length: 9}
  ema_21:
    indicator: ema
    params: {length: 21}

  # Higher timeframe (daily) - trend filter
  ema_50_D:
    indicator: ema
    params: {length: 50}
    tf: "D"
  ema_200_D:
    indicator: ema
    params: {length: 200}
    tf: "D"

actions:
  entry_long:
    all:
      # Daily trend filter: only trade long when daily uptrend
      - ["ema_50_D", ">", "ema_200_D"]
      # 15m signal: golden cross for entry timing
      - ["ema_9", "cross_above", "ema_21"]

  exit_long:
    any:
      # Daily reversal - trend changed
      - ["ema_50_D", "<", "ema_200_D"]
      # 15m exit
      - ["ema_9", "cross_below", "ema_21"]
```

### 1m Action Model

The engine evaluates signals every 1m within each exec bar. This enables precise entry/exit timing.

```yaml
# Use last_price for precise cross-timeframe entries (1m resolution)
actions:
  entry_long:
    all:
      - ["last_price", "cross_above", "ema_200_4h"]  # Checks every 1m
      - ["rsi_14", "<", 50]
```

| Feature | Update Rate | Use Case |
|---------|-------------|----------|
| `last_price` | Every 1m | Precise entries, cross-timeframe comparisons |
| `close` | Per exec bar | Bar-level conditions |
| Higher timeframe features | Forward-fill | Trend context (update on their bar close) |

**Why 1m resolution matters:** If exec is 15m, `close` only updates 4x per hour. But `last_price` updates 60x per hour, allowing precise entry when price crosses a level.

### high_tf Structures (Multi-Timeframe Structure Detection)

Structures can be computed on higher timeframes for trend context:

```yaml
structures:
  # Execution timeframe structures (15m)
  exec:
    - type: swing
      key: swing
      params: {left: 5, right: 5}
    - type: trend
      key: trend
      depends_on: {swing: swing}

  # high_tf structures (4h) - forward-fill between closes
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
- high_tf structures forward-fill until their bar closes (same as indicators)
- Reference by key in actions: `{feature_id: "trend_4h", field: "direction"}`

### Multi-Timeframe Confluence Patterns

**Pattern 1: Execution Swing + Higher Timeframe Trend Filter**
```yaml
actions:
  entry_long:
    all:
      # Higher timeframe trend is UP
      - [{feature_id: trend_4h, field: direction}, "==", 1]
      # Execution swing low exists (bounce setup)
      - [{feature_id: swing, field: low_level}, ">", 0]
      # Price near execution swing low
      - [close, "near_pct", {feature_id: swing, field: low_level}, 2.0]
```

**Pattern 2: Dual-Timeframe Trend Alignment**
```yaml
actions:
  entry_long:
    all:
      # Both timeframes trending UP - strongest signal
      - [{feature_id: trend, field: direction}, "==", 1]
      - [{feature_id: trend_4h, field: direction}, "==", 1]
```

**Pattern 3: high_tf Fib + Exec Swing**
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
      # Price near high_tf 0.618 fib level
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

### Simplified Risk Config (RECOMMENDED)

> **Two formats are supported:**
> - `risk:` - Simplified shorthand (recommended for most strategies)
> - `risk_model:` - Full format (for advanced configurations)
>
> Both are equivalent - use whichever suits your needs.

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
| Taker Fee | 0.055% | Market order fee (Bybit perpetuals) |
| Maker Fee | 0.02% | Limit order fee (Bybit perpetuals) |
| Slippage | Configurable | Applied to fill price |

### Fee Calculation

```python
# Entry fee (taker) - Bybit perpetuals: 0.055%
entry_fee = notional x taker_fee_rate  # e.g., $10,000 x 0.00055 = $5.50

# Required margin (Bybit formula)
required = (notional x IMR) + (notional x taker_fee_rate)
# At 2x leverage (IMR=50%): $10,000 x 0.5 + $5.50 = $5,005.50

# Max fillable at 100% equity
max_notional = equity / (IMR + fee_rate)
# $10,000 / (0.5 + 0.00055) = $9,989
```

---

## 11. Complete Examples

### Example 1: Simple EMA Crossover

```yaml
version: "3.0.0"
name: "ema_crossover"
description: "Classic EMA 9/21 crossover"

symbol: "BTCUSDT"
timeframes:
  low_tf: "1h"
  med_tf: "1h"
  high_tf: "1h"
  exec: "low_tf"

features:
  ema_9:
    indicator: ema
    params: {length: 9}
  ema_21:
    indicator: ema
    params: {length: 21}

actions:
  entry_long:
    all:
      - ["ema_9", "cross_above", "ema_21"]
  exit_long:
    all:
      - ["ema_9", "cross_below", "ema_21"]
  entry_short:
    all:
      - ["ema_9", "cross_below", "ema_21"]
  exit_short:
    all:
      - ["ema_9", "cross_above", "ema_21"]

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
timeframes:
  low_tf: "15m"
  med_tf: "15m"
  high_tf: "15m"
  exec: "low_tf"

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

Uses 12h for structure anchor points (swing highs/lows for fibonacci levels).

```yaml
version: "3.0.0"
name: "multi_tf_fib_zones"
description: "Trade trend pullbacks to fib zones - 12h anchor points, 15m entries"

symbol: "BTCUSDT"
timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "12h"    # Structure anchor points
  exec: "low_tf"

features:
  # Execution timeframe (15m)
  rsi_14:
    indicator: rsi
    params: {length: 14}
  ema_20:
    indicator: ema
    params: {length: 20}

  # Higher timeframe (12h) - trend context
  ema_50_12h:
    indicator: ema
    params: {length: 50}
    tf: "12h"

structures:
  exec:
    - type: swing
      key: swing
      params: {left: 5, right: 5}
    - type: fibonacci
      key: fib
      depends_on: {swing: swing}
      params:
        levels: [0.382, 0.5, 0.618]
        mode: retracement

actions:
  entry_long:
    all:
      # high_tf trend filter
      - ["close", ">", "ema_50_12h"]
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
      - ["close", "<", "ema_50_12h"]

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
timeframes:
  low_tf: "15m"
  med_tf: "15m"
  high_tf: "15m"
  exec: "low_tf"

features:
  atr_14:
    indicator: atr
    params: {length: 14}
  volume_sma_20:
    indicator: sma
    source: volume
    params: {length: 20}

structures:
  exec:
    - type: rolling_window
      key: rolling_high
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
timeframes:
  low_tf: "1h"
  med_tf: "1h"
  high_tf: "1h"
  exec: "low_tf"

features:
  rsi_14:
    indicator: rsi
    params: {length: 14}
  atr_14:
    indicator: atr
    params: {length: 14}

structures:
  exec:
    - type: swing
      key: swing
      params: {left: 5, right: 5}
    - type: derived_zone
      key: fib_zones
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
timeframes:
  low_tf: "15m"
  med_tf: "15m"
  high_tf: "15m"
  exec: "low_tf"

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

## 12. Synthetic Data for Validation

Synthetic data generates deterministic, reproducible market conditions for testing Plays. Use it to validate expected behavior, detect edge case errors, and prevent regressions.

### Purpose

| Use Case | Description |
|----------|-------------|
| **Baseline validation** | Verify Plays behave correctly under known conditions (uptrend should profit on longs) |
| **Error detection** | Test edge cases: false breakouts, stop hunts, flash crashes |
| **Regression testing** | Deterministic seeds ensure consistent results across code changes |

### Running Backtests with Synthetic Data

```bash
# Run a Play with synthetic data (uses pattern from Play's synthetic: block)
python trade_cli.py backtest run --play my_strategy --synthetic

# Override seed for reproducibility testing
python trade_cli.py backtest run --play my_strategy --synthetic --synthetic-seed 123

# Run all synthetic pattern validations
python trade_cli.py forge validate-patterns
```

### Available Patterns

**Trend Patterns**

| Pattern | Description | Tests |
|---------|-------------|-------|
| `trend_up_clean` | Steady uptrend, 10-20% pullbacks | Long entry/exit signals |
| `trend_down_clean` | Steady downtrend, small rallies | Short entry/exit signals |
| `trend_grinding` | Slow, low-volatility trend | Patience, holding behavior |
| `trend_parabolic` | Accelerating blow-off move | Profit-taking, trailing stops |
| `trend_exhaustion` | Strong trend fails and reverses | Reversal detection, stops |
| `trend_stairs` | Step pattern: trend, pause, trend | Trend continuation logic |

**Range Patterns**

| Pattern | Description | Tests |
|---------|-------------|-------|
| `range_tight` | Low volatility squeeze | Breakout anticipation |
| `range_wide` | High volatility, no direction | False signal filtering |
| `range_ascending` | Higher lows, flat resistance | Ascending triangle breakout |
| `range_descending` | Flat support, lower highs | Descending triangle breakdown |
| `range_symmetric` | Clean horizontal channel | Support/resistance detection |

**Reversal Patterns**

| Pattern | Description | Tests |
|---------|-------------|-------|
| `reversal_v_bottom` | Sharp V-bottom recovery | Bottom detection, aggressive entries |
| `reversal_v_top` | Sharp V-top crash | Top detection, exit speed |
| `reversal_double_bottom` | Classic W pattern | Pattern recognition |
| `reversal_double_top` | Classic M pattern | Pattern recognition |
| `reversal_rounded` | Gradual U-shaped reversal | Slow reversal detection |

**Breakout Patterns**

| Pattern | Description | Tests |
|---------|-------------|-------|
| `breakout_clean` | Clear breakout with follow-through | Breakout entry signals |
| `breakout_false` | Fakeout that reverses (stop hunt) | False breakout filtering |
| `breakout_retest` | Breakout, pullback, continuation | Pullback entries |
| `breakout_failed` | Breakout attempt that fails | Exit on failure |

**Volatility Patterns**

| Pattern | Description | Tests |
|---------|-------------|-------|
| `vol_squeeze_expand` | Low volatility squeeze then expansion | Squeeze detection |
| `vol_spike_recover` | Flash crash with V-recovery | Panic behavior, holding |
| `vol_spike_continue` | Flash crash that continues down | Stop loss execution |
| `vol_decay` | High volatility settling to low | Position sizing adjustment |

**Liquidity/Manipulation Patterns**

| Pattern | Description | Tests |
|---------|-------------|-------|
| `liquidity_hunt_lows` | Sweep below support then rally | Stop placement |
| `liquidity_hunt_highs` | Sweep above resistance then drop | Entry timing |
| `choppy_whipsaw` | Rapid direction changes, no trend | Signal filtering |
| `accumulation` | Low volatility drift up | Accumulation detection |
| `distribution` | Low volatility drift down | Distribution detection |

**Multi-Timeframe Patterns**

| Pattern | Description | Tests |
|---------|-------------|-------|
| `mtf_aligned_bull` | All timeframes trending up | Aligned entry confidence |
| `mtf_aligned_bear` | All timeframes trending down | Aligned short confidence |
| `mtf_pullback_bull` | Higher timeframe up, lower pulling back | Pullback entries |
| `mtf_pullback_bear` | Higher timeframe down, lower rallying | Rally fade entries |
| `mtf_divergent` | Higher timeframe range, lower trending | Conflicting signal handling |

### Embedding Synthetic Config in Plays

Add a `synthetic:` block to define the pattern and parameters:

```yaml
version: "3.0.0"
name: "V_SYNTH_trend_up_clean"
description: "Validate long signals on clean uptrend"

synthetic:
  pattern: "trend_up_clean"
  bars: 500
  seed: 42
  config:
    trend_magnitude: 0.25    # 25% price move
    pullback_depth: 0.20     # 20% retracements

symbol: "BTCUSDT"
timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "4h"
  exec: "low_tf"

# ... features, actions, risk ...

# Expected behavior assertions (optional)
expected:
  min_trades: 3
  max_trades: 10
  win_rate_min: 0.5
  pnl_direction: positive
```

### PatternConfig Customization

Override default pattern parameters via the `config:` block:

```yaml
synthetic:
  pattern: "breakout_false"
  bars: 300
  seed: 42
  config:
    # Core parameters
    trend_magnitude: 0.20      # 20% price move for trends
    pullback_depth: 0.30       # 30% retracement on pullbacks
    volatility_base: 0.02      # 2% daily volatility
    volatility_spike: 0.10     # 10% for spike events

    # Timing parameters
    trend_bars: 100            # Bars for trend phase
    range_bars: 50             # Bars for range phase
    reversal_bars: 20          # Bars for reversal formation

    # Noise parameters
    noise_level: 0.3           # 0-1 scale for random noise
```

### Programmatic Usage

```python
from src.forge.validation import generate_synthetic_candles, PatternConfig

config = PatternConfig(
    trend_magnitude=0.30,    # 30% trend move
    volatility_base=0.03,    # 3% daily volatility
)

candles = generate_synthetic_candles(
    pattern="trend_up_clean",
    config=config,
    bars_per_tf=500,
    seed=42,
)
```

### CLI Commands Reference

```bash
# Single Play with synthetic data
python trade_cli.py backtest run --play V_SYNTH_trend_up_clean --synthetic

# Specific seed for reproducibility
python trade_cli.py backtest run --play V_SYNTH_trend_up_clean --synthetic --synthetic-seed 123

# Run full pattern validation suite
python trade_cli.py forge validate-patterns
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

### Removed Fields (Will Error)

| Removed | Use Instead | Notes |
|---------|-------------|-------|
| `blocks:` (top-level) | `actions:` | Removed in v3.0.0 - will be silently ignored |
| `signal_rules:` | `actions:` | Legacy format - no longer parsed |

### Deprecated Fields (Still Work, Will Be Removed)

| Deprecated | Use Instead | Notes |
|------------|-------------|-------|
| `margin_mode: "isolated"` | `margin_mode: "isolated_usdt"` | Will error with helpful message |

### Migration Examples

```yaml
# REMOVED - Will NOT work
blocks:
  entry_long:
    - ["ema_9", ">", "ema_21"]

# CORRECT
actions:
  entry_long:
    - ["ema_9", ">", "ema_21"]
```

```yaml
# DEPRECATED - Will error with helpful message
account:
  margin_mode: "isolated"  # Ambiguous

# CORRECT
account:
  margin_mode: "isolated_usdt"  # Explicit
```

### Engine Behavior

- `blocks:` is **no longer supported** - the Play loader only reads `actions:`
- `margin_mode: "isolated"` will raise a `ValueError` directing you to use `"isolated_usdt"`

---

## Document History

| Date | Change |
|------|--------|
| 2026-01-08 | Created as canonical source, consolidated from PLAY_SYNTAX.md + DSL_REFERENCE.md |
| 2026-01-08 | Fixed Multi-Timeframe terminology (Multi-Timeframe = capability, not role) |
| 2026-01-08 | Added exit_mode, variables, price features deep dive, deprecation notes |
| 2026-01-09 | Symbol operators now canonical (`>`, `<`, `>=`, `<=`, `==`, `!=`). Word forms removed. |
| 2026-01-09 | Added `!=` operator for discrete type comparisons |
| 2026-01-15 | Updated terminology: low_tf, med_tf, high_tf, exec, Multi-Timeframe |
| 2026-01-16 | Added wave-based trend detector with strength, wave_count, last_hh/hl/lh/ll outputs |
| 2026-01-16 | Added market_structure detector (ICT BOS/CHoCH) with bias, bos_this_bar, choch_this_bar outputs |
| 2026-01-16 | Added Example 6: ICT Market Structure strategy |
| 2026-01-17 | Fixed structure syntax to use role-based format (exec: list with type/key/params) |
| 2026-01-17 | Updated all prose to use full natural language (execution timeframe, higher timeframe, etc.) |
| 2026-01-17 | Standardized high_tf examples to use D (daily bias) or 12h (session anchors) |
| 2026-01-17 | Added Multi-Timeframe Best Practices section with top-down approach guidance |
| 2026-01-22 | Added Section 12: Synthetic Data for Validation (patterns, CLI, PatternConfig) |
| 2026-01-25 | Fixed multi-output indicator names to match registry (k/d not stoch_k/stoch_d, etc.) |
| 2026-01-25 | Added incremental indicator column - 11 O(1) indicators for live trading |
| 2026-01-25 | Moved ppo, trix to multi-output section; corrected counts (43 total: 25 single, 18 multi) |
| 2026-01-25 | Fixed Example 3 bug: ema_50_4h → ema_50_12h (matched feature declaration) |
| 2026-01-25 | Updated deprecation section: blocks: is removed (not deprecated), margin_mode errors helpfully |
| 2026-01-25 | Added risk config equivalence note (risk: and risk_model: both valid) |
| 2026-01-25 | Added structure dependency syntax clarification (source: vs swing:) |
| 2026-01-25 | Added reserved position policy flags documentation (allow_flip, etc.)

---

*This is the single source of truth for Play DSL syntax. Update this document when engine behavior changes.*
