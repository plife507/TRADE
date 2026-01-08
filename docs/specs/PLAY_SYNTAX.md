# Play Syntax Reference (v3.0.0)

Complete syntax guide for the Play DSL - declarative strategy specification.

**Renamed**: 2026-01-04 (formerly IDEACARD_SYNTAX.md)

---

## Terminology (2026-01-05)

### Trading Hierarchy (Smallest → Largest)

| Level | Location | Purpose |
|-------|----------|---------|
| **Block** | `strategies/blocks/` | Reusable atomic condition (features + DSL condition) |
| **Play** | `strategies/plays/` | Complete strategy (features + actions + account + risk) |
| **Playbook** | `strategies/playbooks/` | Collection of Plays with weights/roles |
| **System** | `strategies/systems/` | Multiple Playbooks with global risk |

### Play Sections

A Play is composed of these section types:

| Section | Purpose |
|---------|---------|
| `features:` | Indicator declarations |
| `structures:` | Market structure declarations |
| `actions:` | Entry/exit rules (DSL format) |
| `risk:` | Stop loss, take profit, sizing |
| `account:` | Capital, leverage, fees |
| `variables:` | Tunable parameters |

**Note**: The `actions:` section was previously called `blocks:` (renamed 2026-01-05).

See: `docs/architecture/LAYER_2_RATIONALIZATION_ARCHITECTURE.md` for complete architecture.

---

## Table of Contents

1. [Overview](#overview)
2. [Required Sections](#required-sections)
3. [Features (Indicators)](#features-indicators)
4. [Structures (Market Structure)](#structures-market-structure)
5. [Actions (Entry/Exit Rules)](#actions-entryexit-rules)
6. [Operators](#operators)
7. [Boolean Logic (all/any/not)](#boolean-logic-allanynot)
8. [Window Operators](#window-operators)
9. [Accessing Features and Structures](#accessing-features-and-structures)
10. [Risk Model](#risk-model)
11. [Complete Examples](#complete-examples)

---

## Overview

A Play is a YAML file that defines a complete trading strategy:

```yaml
id: my_strategy
version: "3.0.0"
name: "My Strategy Name"
description: "What this strategy does"

account: { ... }          # Account configuration
symbol_universe: [...]    # Symbols to trade
execution_tf: "1h"        # Execution timeframe
features: [...]           # Indicators
actions: [...]            # Entry/exit rules (DSL format)
position_policy: { ... }  # Position constraints
risk_model: { ... }       # SL/TP/sizing
```

---

## Required Sections

### Identity

```yaml
id: V_100_my_strategy       # Unique identifier (filename without .yml)
version: "3.0.0"            # Schema version (3.0.0 for blocks format)
name: "Strategy Name"       # Human-readable name
description: "Description"  # What it does
```

### Account Configuration

```yaml
account:
  starting_equity_usdt: 10000.0   # Required: starting capital
  max_leverage: 3.0               # Required: max leverage allowed
  margin_mode: "isolated_usdt"    # Must be "isolated_usdt"
  min_trade_notional_usdt: 10.0   # Minimum trade size
  fee_model:
    taker_bps: 6.0                # Taker fee in basis points (0.06%)
    maker_bps: 2.0                # Maker fee in basis points
  slippage_bps: 2.0               # Slippage estimate
```

### Symbol Universe

```yaml
symbol_universe:
  - "BTCUSDT"
  - "ETHUSDT"
```

### Execution Timeframe

```yaml
execution_tf: "1h"   # Bar-by-bar stepping granularity
```

Valid timeframes: `1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `6h`, `8h`, `12h`, `1D`

**Running Backtests**: Date ranges are auto-inferred from DB coverage:
```bash
# Auto-infer dates from database (uses full available range)
python trade_cli.py backtest run --play my_strategy

# Or specify explicit dates
python trade_cli.py backtest run --play my_strategy --start 2026-01-01 --end 2026-01-05
```

### Position Policy

```yaml
position_policy:
  mode: "long_only"              # "long_only", "short_only", "long_short"
  max_positions_per_symbol: 1    # Must be 1 (single position only)
  allow_flip: false              # Not yet supported
  allow_scale_in: false          # Not yet supported
  allow_scale_out: false         # Not yet supported
```

---

## Feature Naming Convention

Use **parameterized names** that encode the indicator type and primary parameters. This makes DSL expressions self-documenting and enables future arithmetic expressions.

### Naming Rules

| Indicator Type | Pattern | Examples |
|----------------|---------|----------|
| Single-param | `{type}_{param}` | `ema_20`, `sma_50`, `rsi_14`, `atr_14` |
| Single-param + TF | `{type}_{param}_{tf}` | `ema_50_1h`, `rsi_14_4h` |
| Multi-param | `{type}_{p1}_{p2}` | `bbands_20_2`, `stoch_14_3` |
| MACD | `macd_{fast}_{slow}_{signal}` | `macd_12_26_9` |
| SuperTrend | `supertrend_{len}_{mult}` | `supertrend_10_3` |

### Why Parameterized Names?

```yaml
# BAD: Semantic names hide parameters
features:
  - id: "ema_fast"      # What length? Unknown
    params: {length: 9}
  - id: "ema_slow"      # What length? Unknown
    params: {length: 21}

# GOOD: Parameterized names are self-documenting
features:
  - id: "ema_9"         # Clearly length=9
    params: {length: 9}
  - id: "ema_21"        # Clearly length=21
    params: {length: 21}
```

Benefits:
- **Self-documenting**: `ema_9 > ema_21` immediately tells you what's being compared
- **Agent-friendly**: AI agents can parse and compose strategies more easily
- **Future arithmetic**: `ema_9 - ema_21 > 0` is readable (when arithmetic is supported)

### Multi-TF Naming

For multi-timeframe features, append the timeframe when it differs from execution TF:

```yaml
features:
  - id: "ema_9"         # Execution TF (implied)
    tf: "15m"
    params: {length: 9}
  - id: "ema_50_1h"     # Higher TF (explicit in name)
    tf: "1h"
    params: {length: 50}
```

---

## Features (Indicators)

Features define indicators with unique IDs for reference in actions.

**Note**: Structure-only Plays with `features: []` is valid if `structures:` is defined.

### Basic Syntax

```yaml
features:
  - id: "ema_21"             # Parameterized name (type_param)
    tf: "1h"                 # Timeframe
    type: indicator          # "indicator" for technical indicators
    indicator_type: ema      # Indicator type from registry
    params:
      length: 21             # Indicator-specific parameters
```

### Common Indicators

```yaml
# EMA (Exponential Moving Average)
- id: "ema_50"
  tf: "1h"
  type: indicator
  indicator_type: ema
  params:
    length: 50

# SMA (Simple Moving Average)
- id: "sma_20"
  tf: "1h"
  type: indicator
  indicator_type: sma
  params:
    length: 20

# RSI (Relative Strength Index)
- id: "rsi_14"
  tf: "1h"
  type: indicator
  indicator_type: rsi
  params:
    length: 14

# ATR (Average True Range)
- id: "atr_14"
  tf: "1h"
  type: indicator
  indicator_type: atr
  params:
    length: 14

# MACD (Moving Average Convergence Divergence)
# Multi-output: macd, macd_signal, macd_hist
- id: "macd"
  tf: "1h"
  type: indicator
  indicator_type: macd
  params:
    fast: 12
    slow: 26
    signal: 9

# Bollinger Bands
# Multi-output: bbl (lower), bbm (middle), bbu (upper)
- id: "bbands"
  tf: "1h"
  type: indicator
  indicator_type: bbands
  params:
    length: 20
    std: 2.0

# Stochastic
# Multi-output: stoch_k, stoch_d
- id: "stoch"
  tf: "1h"
  type: indicator
  indicator_type: stoch
  params:
    k: 14
    d: 3
    smooth_k: 3
```

### Complete Indicator Registry (42 Total)

**Single-Output Indicators (26)**:

| Type | Params | Description |
|------|--------|-------------|
| `ema` | `length` | Exponential Moving Average |
| `sma` | `length` | Simple Moving Average |
| `rsi` | `length` | Relative Strength Index |
| `atr` | `length` | Average True Range |
| `cci` | `length` | Commodity Channel Index |
| `willr` | `length` | Williams %R |
| `roc` | `length` | Rate of Change |
| `mom` | `length` | Momentum |
| `kama` | `length` | Kaufman Adaptive MA |
| `alma` | `length`, `sigma`, `offset` | Arnaud Legoux MA |
| `wma` | `length` | Weighted Moving Average |
| `dema` | `length` | Double EMA |
| `tema` | `length` | Triple EMA |
| `trima` | `length` | Triangular MA |
| `zlma` | `length` | Zero Lag MA |
| `natr` | `length` | Normalized ATR |
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

**Multi-Output Indicators (16)**:

| Type | Outputs | Params |
|------|---------|--------|
| `macd` | `macd`, `macd_signal`, `macd_hist` | `fast`, `slow`, `signal` |
| `bbands` | `bbl`, `bbm`, `bbu`, `bbb`, `bbp` | `length`, `std` |
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

### Multi-Timeframe Features

```yaml
features:
  # Execution TF indicator (no TF suffix needed)
  - id: "ema_9"
    tf: "15m"
    type: indicator
    indicator_type: ema
    params: { length: 9 }

  # Higher TF indicator (TF suffix for clarity)
  - id: "ema_50_1h"
    tf: "1h"
    type: indicator
    indicator_type: ema
    params: { length: 50 }
```

---

## Structures (Market Structure)

Structures provide O(1) market structure detection. They are declared separately from features.

### Structure Types

| Type | Description | Outputs |
|------|-------------|---------|
| `swing` | Swing high/low detection | `high_level`, `low_level`, `high_idx`, `low_idx`, `version` |
| `trend` | Trend classification (HH/HL) | `direction`, `strength`, `bars_in_trend`, `version` |
| `zone` | Demand/supply zones | `state`, `upper`, `lower`, `version` |
| `fibonacci` | Fibonacci levels | `level_0.382`, `level_0.5`, `level_0.618`, etc. |
| `rolling_window` | O(1) rolling min/max | `value` |
| `derived_zone` | Fib zones from pivots | K slots + aggregates (see below) |

### Derived Zones (K Slots + Aggregates)

Derived zones create Fibonacci zones from swing pivots:

```yaml
- id: "fib_zones"
  tf: "1h"
  type: structure
  structure_type: derived_zone
  depends_on: {source: "swing"}
  params: {levels: [0.382, 0.5, 0.618], mode: retracement, max_active: 5}
```

**Slot Fields**: `zone{N}_lower`, `zone{N}_upper`, `zone{N}_state` (NONE/ACTIVE/BROKEN)

**Aggregates**: `active_count`, `any_active`, `any_touched`, `closest_active_lower`

### Structure Declaration (in tf_configs)

```yaml
timeframes:
  exec: "15m"
  htf: "1h"

tf_configs:
  exec:
    role: "exec"
    warmup_bars: 50
    feature_specs:
      - indicator_type: "ema"
        output_key: "ema_fast"
        params: { length: 9 }

structures:
  exec:
    # Swing detector
    - type: swing
      key: swing              # Reference as "structure.swing"
      params:
        left: 5               # Bars to left for confirmation
        right: 5              # Bars to right for confirmation

    # Trend detector (depends on swing)
    - type: trend
      key: trend              # Reference as "structure.trend"
      depends_on:
        swing: swing          # Uses swing detector for pattern analysis

    # Zone detector
    - type: zone
      key: demand_zone
      depends_on:
        swing: swing
      params:
        zone_type: demand     # "demand" or "supply"
        width_atr: 1.5        # Zone width in ATR units

    # Fibonacci levels
    - type: fibonacci
      key: fib
      depends_on:
        swing: swing
      params:
        levels: [0.382, 0.5, 0.618]
        mode: retracement

    # Rolling window min/max
    - type: rolling_window
      key: recent_low
      params:
        size: 20              # Window size in bars
        field: low            # Field to track
        mode: min             # "min" or "max"

  # HTF structures
  htf:
    "1h":
      - type: swing
        key: swing_1h
        params: { left: 3, right: 3 }
      - type: trend
        key: trend_1h
        depends_on:
          swing: swing_1h
```

---

## Actions (Entry/Exit Rules)

Actions define entry/exit logic with nested boolean expressions.

### Basic Action Structure

```yaml
actions:
  - id: entry                 # Block identifier
    cases:                    # List of cases (first-match wins)
      - when:                 # Condition expression
          lhs:
            feature_id: "ema_9"
          op: gt
          rhs:
            feature_id: "ema_21"
        emit:                 # Actions if condition is true
          - action: entry_long
    else:                     # Optional: if no case matches
      emit:
        - action: no_action

  - id: exit
    cases:
      - when:
          lhs:
            feature_id: "ema_9"
          op: lt
          rhs:
            feature_id: "ema_21"
        emit:
          - action: exit_long
```

### Valid Actions

| Action | Description |
|--------|-------------|
| `entry_long` | Enter long position |
| `entry_short` | Enter short position |
| `exit_long` | Exit long position |
| `exit_short` | Exit short position |
| `exit_all` | Exit all positions |
| `no_action` | Do nothing |

### Partial Exit Actions (v3.0.3)

Close a percentage of position instead of full exit:

```yaml
emit:
  - action: exit_long
    percent: 50      # Close 50% of position

emit:
  - action: exit_long
    percent: 100     # Full close (default, same as omitting percent)
```

**Rules**:
- `percent` must be in range (0, 100]
- `percent: 0` is invalid (raises ValueError)
- `percent: 100` is equivalent to a full exit
- Partial exits reduce position size proportionally
- PnL is realized proportionally for the closed portion
- Position remains open with reduced size until final exit

**Example: Scaling out of a position**:

```yaml
actions:
  - id: partial_take_profit
    cases:
      # First target: close 50% at RSI 60
      - when:
          lhs: {feature_id: "rsi_14"}
          op: gt
          rhs: 60
        emit:
          - action: exit_long
            percent: 50

  - id: full_exit
    cases:
      # Final exit: close remaining at RSI 75
      - when:
          lhs: {feature_id: "rsi_14"}
          op: gt
          rhs: 75
        emit:
          - action: exit_long
```

### Dynamic Action Metadata (v3.0.3)

Reference features in action metadata for dynamic values:

```yaml
emit:
  - action: entry_long
    metadata:
      entry_atr: {feature_id: "atr_14"}           # Dynamic: resolved at evaluation
      entry_ema: {feature_id: "ema_20"}           # Dynamic: resolved at evaluation
      static_note: "captured at entry"             # Static: passed through as-is
```

**Syntax**:
- Dynamic reference: `{feature_id: "id", field: "field"}` (field defaults to "value")
- Static value: Any scalar (string, number, boolean)

**FAIL LOUD**: If a referenced feature cannot be resolved, evaluation raises `ValueError`:
```
ValueError: Dynamic metadata 'entry_atr' references missing feature: atr_14.value
```

**Use cases**:
- Capture indicator values at entry/exit time
- Store context for trade analysis
- Debugging and auditing signal decisions

**Example: Capturing context at entry/exit**:

```yaml
actions:
  - id: entry
    cases:
      - when:
          lhs: {feature_id: "rsi_14"}
          op: lt
          rhs: 35
        emit:
          - action: entry_long
            metadata:
              entry_atr: {feature_id: "atr_14"}
              entry_rsi: {feature_id: "rsi_14"}
              entry_reason: "rsi_oversold"

  - id: exit
    cases:
      - when:
          lhs: {feature_id: "rsi_14"}
          op: gt
          rhs: 70
        emit:
          - action: exit_long
            metadata:
              exit_atr: {feature_id: "atr_14"}
              exit_rsi: {feature_id: "rsi_14"}
              exit_reason: "rsi_overbought"
```

---

## Operators

### Comparison Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `gt` | Greater than | `RSI > 50` |
| `gte` | Greater than or equal | `RSI >= 50` |
| `lt` | Less than | `RSI < 30` |
| `lte` | Less than or equal | `RSI <= 30` |
| `eq` | Equal (discrete types) | `trend.direction == 1` |
| `approx_eq` | Approximate equality (float) | `\|price - level\| <= tolerance` |
| `between` | In range (inclusive) | `30 <= RSI <= 70` |
| `near_abs` | Near (absolute tolerance) | `|price - level| <= 10` |
| `near_pct` | Near (percentage tolerance) | `|price - level| / level <= 0.01` |
| `in` | In set of values | `direction in [1, -1]` |

### Crossover Operators

| Operator | Description | Semantics |
|----------|-------------|-----------|
| `cross_above` | Cross above | `prev <= target AND curr > target` |
| `cross_below` | Cross below | `prev >= target AND curr < target` |

### Operator Examples

```yaml
# Simple comparison: RSI < 30
- when:
    lhs:
      feature_id: "rsi_14"
    op: lt
    rhs: 30

# Feature comparison: EMA 9 > EMA 21
- when:
    lhs:
      feature_id: "ema_9"
    op: gt
    rhs:
      feature_id: "ema_21"

# Between: RSI in neutral zone
- when:
    lhs:
      feature_id: "rsi_14"
    op: between
    rhs:
      low: 30
      high: 70

# Near percent: Price near fib level (within 0.5%)
- when:
    lhs:
      feature_id: "mark_price"
    op: near_pct
    rhs:
      feature_id: "fib"
      field: "level_0.618"
    tolerance: 0.005

# Crossover: EMA 9 crosses above EMA 21
- when:
    lhs:
      feature_id: "ema_9"
    op: cross_above
    rhs:
      feature_id: "ema_21"

# Equality: Trend is up (direction = 1)
- when:
    lhs:
      feature_id: "trend"
      field: "direction"
    op: eq
    rhs: 1

# Approximate equality: Price near fib level (absolute tolerance)
- when:
    lhs:
      feature_id: "close"
    op: approx_eq
    rhs:
      feature_id: "fib"
      field: "level_0.618"
    tolerance: 10.0
```

---

## Boolean Logic (all/any/not)

### AND Logic (all)

```yaml
- when:
    all:
      - lhs:
          feature_id: "ema_9"
        op: gt
        rhs:
          feature_id: "ema_21"
      - lhs:
          feature_id: "rsi_14"
        op: lt
        rhs: 70
```

### OR Logic (any)

```yaml
- when:
    any:
      - lhs:
          feature_id: "rsi_14"
        op: lt
        rhs: 30
      - lhs:
          feature_id: "rsi_14"
        op: gt
        rhs: 70
```

### NOT Logic (not)

```yaml
- when:
    not:
      lhs:
        feature_id: "rsi_14"
      op: gt
      rhs: 70
```

### Nested Logic

```yaml
# (EMA 9 > EMA 21) AND (RSI < 70 OR RSI > 30)
- when:
    all:
      - lhs:
          feature_id: "ema_9"
        op: gt
        rhs:
          feature_id: "ema_21"
      - any:
          - lhs:
              feature_id: "rsi_14"
            op: lt
            rhs: 70
          - lhs:
              feature_id: "rsi_14"
            op: gt
            rhs: 30
```

---

## Window Operators

Window operators check conditions over multiple bars. Two forms are available:

| Form | Syntax | Best For |
|------|--------|----------|
| **Duration-based** | `holds_for_duration: "30m"` | Cross-TF comparisons (recommended) |
| **Bar-based** | `holds_for: {bars: 5}` | Same-TF conditions |

### Duration-Based Window Operators (Recommended for Cross-TF)

Duration-based operators express time explicitly and always sample at 1m rate:

#### holds_for_duration

Condition must be true for the specified duration:

```yaml
- when:
    holds_for_duration:
      duration: "30m"        # 30 minutes (= 30 bars at 1m)
      expr:
        lhs:
          feature_id: "rsi_14_1h"   # Forward-filled from 1h
        op: gt
        rhs: 50
```

#### occurred_within_duration

Condition was true at least once within the duration:

```yaml
- when:
    occurred_within_duration:
      duration: "1h"         # Within last hour
      expr:
        lhs:
          feature_id: "last_price"
        op: cross_above
        rhs:
          feature_id: "ema_50_4h"
```

#### count_true_duration

Condition was true at least M times within the duration:

```yaml
- when:
    count_true_duration:
      duration: "2h"         # Within last 2 hours
      min_true: 30           # At least 30 times
      expr:
        lhs:
          feature_id: "rsi_14_1h"
        op: lt
        rhs: 40
```

**Duration format**: `"Nm"` (minutes) or `"Nh"` (hours). Max: 24 hours (1440 minutes).

### Bar-Based Window Operators

Bar-based operators use bar counts. Use `anchor_tf` for cross-TF conditions:

#### holds_for

```yaml
# Same-TF: bars counted at feature's TF
- when:
    holds_for:
      bars: 5
      expr:
        lhs:
          feature_id: "rsi_14"
        op: gt
        rhs: 50

# Cross-TF: explicit anchor_tf for correct sampling
- when:
    holds_for:
      bars: 30
      anchor_tf: "1m"        # Sample at 1m rate
      expr:
        lhs:
          feature_id: "last_price"    # 1m
        op: gt
        rhs:
          feature_id: "ema_50_4h"     # Forward-filled from 4h
```

#### occurred_within

```yaml
- when:
    occurred_within:
      bars: 10
      anchor_tf: "1m"        # Optional: explicit sampling rate
      expr:
        lhs:
          feature_id: "ema_9"
        op: cross_above
        rhs:
          feature_id: "ema_21"
```

#### count_true

```yaml
- when:
    count_true:
      bars: 60
      min_true: 20
      anchor_tf: "1m"        # Check 60 1m bars, need 20+ true
      expr:
        lhs:
          feature_id: "rsi_14_1h"
        op: gt
        rhs: 70
```

### Why anchor_tf Matters (Cross-TF Problem)

Without `anchor_tf`, bar-based windows shift features at their declared TFs, causing misalignment:

```
holds_for: 5 bars (NO anchor_tf, comparing 1m to 1h)

Offset | last_price (1m) | rsi_14_1h (1h) | Problem
-------|-----------------|----------------|--------
0      | NOW             | NOW            | OK
1      | 1m ago          | 1h ago         | BROKEN - wrong comparison
2      | 2m ago          | 2h ago         | BROKEN
```

With `anchor_tf: "1m"` or duration-based operators, both sides sample at the same rate:

```
holds_for_duration: "5m" (or holds_for: {bars: 5, anchor_tf: "1m"})

Offset | last_price (1m) | rsi_14_1h (forward-filled) | Result
-------|-----------------|----------------------------|-------
0      | NOW             | Current 1h value           | OK
1      | 1m ago          | Same 1h value (forward-fill) | OK
2      | 2m ago          | Same 1h value              | OK
```

**Rule of thumb**: Use duration-based operators for cross-TF conditions.

---

## Accessing Features and Structures

### Referencing Features

```yaml
# Simple feature reference
lhs:
  feature_id: "ema_21"

# With field (for multi-output indicators)
lhs:
  feature_id: "macd_12_26_9"
  field: "signal"      # Access MACD signal line

# With offset (previous bar)
lhs:
  feature_id: "close"
  offset: 1            # Previous bar's close
```

### Referencing Structures

Structures are referenced by their key with field selection. Both short and explicit prefix formats work:

```yaml
# Short form (recommended) - auto-resolved to structure.*
lhs:
  feature_id: "swing"
  field: "high_level"    # Swing high price

# Explicit prefix form - also valid
lhs:
  feature_id: "structure.swing"
  field: "high_level"    # Same as above

# Trend structure
lhs:
  feature_id: "trend"
  field: "direction"     # 1=up, -1=down, 0=neutral

# Fibonacci structure
lhs:
  feature_id: "fib"
  field: "level_0.618"   # 61.8% fib level

# Zone structure
lhs:
  feature_id: "demand_zone"
  field: "upper"         # Zone upper boundary

# Rolling window
lhs:
  feature_id: "recent_low"
  field: "value"         # Window min/max value
```

### Built-in Features

Available without declaration:

```yaml
# OHLCV data (at execution_tf)
feature_id: "open"
feature_id: "high"
feature_id: "low"
feature_id: "close"
feature_id: "volume"

# Price features
feature_id: "last_price"   # 1m ticker close (action price in hot loop)
feature_id: "mark_price"   # Fair price for PnL calculation
```

**Price Feature Semantics (1m Action Model)**:

| Feature | Source | Update Rate | Use Case |
|---------|--------|-------------|----------|
| `last_price` | 1m bar close | Every 1m | Cross-TF comparisons, precise entries |
| `close` | execution_tf bar close | Every exec bar | Bar-level conditions |
| `mark_price` | Price model | Every 1m | PnL, margin calculations |

The engine evaluates signals every 1m within each `execution_tf` bar. Use `last_price` when comparing price to forward-filled HTF indicators for responsive entries.

---

## Risk Model

```yaml
risk_model:
  stop_loss:
    type: "percent"        # or "atr_multiple", "structure", "fixed_points"
    value: 2.0             # 2% stop loss

  take_profit:
    type: "rr_ratio"       # or "atr_multiple", "percent", "fixed_points"
    value: 2.0             # 2:1 reward-to-risk ratio

  sizing:
    model: "percent_equity"  # or "fixed_usdt", "risk_based"
    value: 2.0               # 2% of equity per trade
    max_leverage: 3.0        # Maximum leverage
```

### Stop Loss Types

```yaml
# Percentage-based
stop_loss:
  type: "percent"
  value: 2.0

# ATR-based
stop_loss:
  type: "atr_multiple"
  value: 2.0
  atr_feature_id: "atr_14"   # Reference to ATR feature

# Structure-based (e.g., swing low)
stop_loss:
  type: "structure"
  value: 1.0                 # Multiplier
  buffer_pct: 0.1            # Buffer percentage
```

### Take Profit Types

```yaml
# Risk-reward ratio
take_profit:
  type: "rr_ratio"
  value: 2.0         # 2R target

# Percentage
take_profit:
  type: "percent"
  value: 4.0         # 4% take profit

# ATR-based
take_profit:
  type: "atr_multiple"
  value: 3.0
  atr_feature_id: "atr_14"
```

---

## Complete Examples

### Example 1: Simple EMA Crossover

```yaml
id: ema_crossover
version: "3.0.0"
name: "EMA Crossover Strategy"
description: "Long when EMA(9) crosses above EMA(21)"

account:
  starting_equity_usdt: 10000.0
  max_leverage: 3.0
  margin_mode: "isolated_usdt"
  fee_model:
    taker_bps: 6.0
    maker_bps: 2.0

symbol_universe:
  - "BTCUSDT"

execution_tf: "1h"

features:
  - id: "ema_9"
    tf: "1h"
    type: indicator
    indicator_type: ema
    params: { length: 9 }

  - id: "ema_21"
    tf: "1h"
    type: indicator
    indicator_type: ema
    params: { length: 21 }

position_policy:
  mode: "long_only"
  max_positions_per_symbol: 1

actions:
  - id: entry
    cases:
      - when:
          lhs:
            feature_id: "ema_9"
          op: cross_above
          rhs:
            feature_id: "ema_21"
        emit:
          - action: entry_long
    else:
      emit:
        - action: no_action

  - id: exit
    cases:
      - when:
          lhs:
            feature_id: "ema_9"
          op: cross_below
          rhs:
            feature_id: "ema_21"
        emit:
          - action: exit_long

risk_model:
  stop_loss:
    type: "percent"
    value: 3.0
  take_profit:
    type: "rr_ratio"
    value: 2.0
  sizing:
    model: "percent_equity"
    value: 2.0
    max_leverage: 3.0
```

### Example 2: Multi-Condition with RSI Filter

```yaml
id: ema_rsi_strategy
version: "3.0.0"
name: "EMA + RSI Strategy"
description: "Long when EMA bullish AND RSI not overbought"

account:
  starting_equity_usdt: 10000.0
  max_leverage: 3.0
  margin_mode: "isolated_usdt"
  fee_model:
    taker_bps: 6.0

symbol_universe:
  - "BTCUSDT"

execution_tf: "1h"

features:
  - id: "ema_9"
    tf: "1h"
    type: indicator
    indicator_type: ema
    params: { length: 9 }

  - id: "ema_21"
    tf: "1h"
    type: indicator
    indicator_type: ema
    params: { length: 21 }

  - id: "rsi_14"
    tf: "1h"
    type: indicator
    indicator_type: rsi
    params: { length: 14 }

position_policy:
  mode: "long_only"
  max_positions_per_symbol: 1

actions:
  - id: entry
    cases:
      - when:
          all:
            - lhs:
                feature_id: "ema_9"
              op: gt
              rhs:
                feature_id: "ema_21"
            - lhs:
                feature_id: "rsi_14"
              op: lt
              rhs: 70
        emit:
          - action: entry_long
    else:
      emit:
        - action: no_action

  - id: exit
    cases:
      - when:
          any:
            - lhs:
                feature_id: "ema_9"
              op: lt
              rhs:
                feature_id: "ema_21"
            - lhs:
                feature_id: "rsi_14"
              op: gt
              rhs: 80
        emit:
          - action: exit_long

risk_model:
  stop_loss:
    type: "percent"
    value: 3.0
  take_profit:
    type: "rr_ratio"
    value: 2.0
  sizing:
    model: "percent_equity"
    value: 2.0
    max_leverage: 3.0
```

### Example 3: Multi-Timeframe with Trend Filter

```yaml
id: mtf_trend_strategy
version: "3.0.0"
name: "MTF Trend Strategy"
description: "Trade with 1h trend, execute on 15m"

account:
  starting_equity_usdt: 10000.0
  max_leverage: 3.0
  margin_mode: "isolated_usdt"
  fee_model:
    taker_bps: 6.0

symbol_universe:
  - "BTCUSDT"

execution_tf: "15m"

features:
  # Execution TF indicators (no TF suffix needed)
  - id: "ema_9"
    tf: "15m"
    type: indicator
    indicator_type: ema
    params: { length: 9 }

  - id: "ema_21"
    tf: "15m"
    type: indicator
    indicator_type: ema
    params: { length: 21 }

  # HTF trend indicator (TF suffix for clarity)
  - id: "ema_50_1h"
    tf: "1h"
    type: indicator
    indicator_type: ema
    params: { length: 50 }

position_policy:
  mode: "long_only"
  max_positions_per_symbol: 1

actions:
  - id: entry
    cases:
      - when:
          all:
            # HTF filter: price above 1h EMA (uptrend)
            - lhs:
                feature_id: "close"
              op: gt
              rhs:
                feature_id: "ema_50_1h"
            # LTF signal: EMA crossover
            - lhs:
                feature_id: "ema_9"
              op: cross_above
              rhs:
                feature_id: "ema_21"
        emit:
          - action: entry_long
    else:
      emit:
        - action: no_action

  - id: exit
    cases:
      - when:
          lhs:
            feature_id: "ema_9"
          op: cross_below
          rhs:
            feature_id: "ema_21"
        emit:
          - action: exit_long

risk_model:
  stop_loss:
    type: "percent"
    value: 2.0
  take_profit:
    type: "rr_ratio"
    value: 2.0
  sizing:
    model: "percent_equity"
    value: 1.5
    max_leverage: 3.0
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 3.0.4 | 2026-01-07 | 1m action model: `last_price`, duration-based windows (`holds_for_duration`, etc.), `anchor_tf` parameter |
| 3.0.3 | 2026-01-06 | Partial exit actions (`percent` field), dynamic action metadata (feature refs in `metadata`) |
| 3.0.2 | 2026-01-05 | Structure refs auto-resolve (both `swing` and `structure.swing` work); structure-only Plays valid; auto-infer date window |
| 3.0.1 | 2026-01-05 | Renamed `blocks:` field to `actions:` |
| 3.0.0 | 2026-01-04 | Actions-based DSL with nested all/any/not, window operators |
| 2.0.0 | — | Legacy signal_rules format (deprecated) |

---

## See Also

- `tests/validation/plays/` - Validation play examples
- `docs/specs/PLAY_VISION.md` - Play design vision
- `docs/specs/INCREMENTAL_STATE_ARCHITECTURE.md` - Structure detectors
- `docs/architecture/LAYER_2_RATIONALIZATION_ARCHITECTURE.md` - StateRationalizer and Forge
