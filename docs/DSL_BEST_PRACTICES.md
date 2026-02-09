# Play DSL Best Practices

> Practical guide for writing correct, efficient Play YAML strategies.
> For the complete syntax reference, see `docs/PLAY_DSL_COOKBOOK.md`.

---

## Table of Contents

1. [Play Structure Checklist](#1-play-structure-checklist)
2. [Naming Conventions](#2-naming-conventions)
3. [Condition Writing Rules](#3-condition-writing-rules)
4. [Operator Selection Guide](#4-operator-selection-guide)
5. [Structure Best Practices](#5-structure-best-practices)
6. [Fibonacci Anchoring Guide](#6-fibonacci-anchoring-guide)
7. [Arithmetic Expressions](#7-arithmetic-expressions)
8. [Window Operators](#8-window-operators)
9. [Multi-Timeframe Patterns](#9-multi-timeframe-patterns)
10. [Common Mistakes](#10-common-mistakes)
11. [Strategy Recipes](#11-strategy-recipes)
12. [Pitfalls from Production Audits](#12-pitfalls-from-production-audits)

---

## 1. Play Structure Checklist

Every Play needs these sections. Missing any will cause a load-time error:

```yaml
version: "3.0.0"
name: "my_strategy"
symbol: "BTCUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "12h"
  exec: "low_tf"              # Pointer, not a value

account:
  starting_equity_usdt: 10000.0
  max_leverage: 3.0
  fee_model:
    taker_bps: 5.5
    maker_bps: 2.0

features:
  # ... at least one indicator or structure

actions:
  # ... at least one action block

risk:
  stop_loss_pct: 2.0
  take_profit_pct: 4.0

position_policy:
  mode: long_only
  exit_mode: sl_tp_only
```

**Key rules:**
- `exec` is a **pointer** to a timeframe role (`"low_tf"`, `"med_tf"`, or `"high_tf"`), never a raw value like `"15m"`.
- `symbol_universe` or `symbol` must provide at least one symbol.
- `account` is required (no silent defaults for equity or leverage).

### Timeframe Naming (ENFORCED)

```yaml
# CORRECT:
timeframes:
  low_tf: "15m"      # Fast: execution, entries
  med_tf: "1h"       # Medium: structure, bias
  high_tf: "D"       # Slow: trend, context
  exec: "low_tf"     # POINTER to which TF to step on

# WRONG (will cause errors or confusion):
# ltf, htf, LTF, HTF, MTF    - Never as YAML keys
# exec_tf: "15m"              - exec is a pointer, not a value
```

**In prose and comments:** Write full names -- "higher timeframe" not HTF, "execution timeframe" not exec TF, "multi-timeframe" for strategies using multiple timeframes.

### 1m Data is Mandatory

The engine always requires 1m candle data regardless of your execution timeframe. The 1m feed drives:

- **Fill simulation**: Entries and exits are filled at 1m bar open prices (next bar after signal).
- **TP/SL checking**: Stop loss and take profit are checked every 1m tick, not just at exec bar close.
- **Signal subloop**: `last_price` and `mark_price` update every 1m within each exec bar.
- **Slippage model**: Applied to 1m fill prices for realistic execution.

If 1m data is missing, the backtest will fail. Use `--fix-gaps` to auto-sync missing data.

---

## 2. Naming Conventions

### Indicators: Encode parameters in the name

```yaml
# CORRECT - self-documenting names
features:
  ema_9:
    indicator: ema
    params: { length: 9 }
  ema_21:
    indicator: ema
    params: { length: 21 }
  rsi_14:
    indicator: rsi
    params: { length: 14 }
  macd_12_26_9:
    indicator: macd
    params: { fast: 12, slow: 26, signal: 9 }
```

```yaml
# WRONG - semantic names hide parameters
features:
  ema_fast:          # What length? Impossible to know.
    indicator: ema
    params: { length: 9 }
  ema_slow:
    indicator: ema
    params: { length: 21 }
```

### Cross-timeframe indicators: Append the timeframe

```yaml
features:
  ema_50_1h:                   # Clear: EMA(50) on 1h bars
    indicator: ema
    params: { length: 50 }
    tf: "1h"
  rsi_14_4h:                   # Clear: RSI(14) on 4h bars
    indicator: rsi
    params: { length: 14 }
    tf: "4h"
```

### Structures: Short, descriptive keys

```yaml
structures:
  exec:
    - type: swing
      key: swing               # Simple, direct
    - type: trend
      key: trend
      uses: swing
    - type: fibonacci
      key: fib_entry
      uses: swing
    - type: fibonacci
      key: fib_targets
      uses: swing
```

---

## 3. Condition Writing Rules

### Use shorthand list format for most conditions

The 3-element list format `[lhs, operator, rhs]` is the preferred syntax:

```yaml
actions:
  entry_long:
    all:
      - ["ema_9", ">", "ema_21"]            # Feature vs feature
      - ["rsi_14", "<", 70]                  # Feature vs constant
      - ["close", "cross_above", "ema_50"]   # Crossover
      - ["trend.direction", "==", 1]         # Structure field
      - ["rsi_14", "between", [30, 70]]      # Range check
```

### Use 4-element format for proximity checks

Proximity operators (`near_pct`, `near_abs`) require a tolerance as the 4th element:

```yaml
# near_pct: tolerance is a PERCENTAGE (3 means 3%, NOT 0.03)
- ["close", "near_pct", "fib.level[0.618]", 1.5]    # Within 1.5% of fib level

# near_abs: tolerance is absolute price units
- ["close", "near_abs", "swing.high_level", 50]      # Within $50 of swing high
```

### Use verbose dict format only when you need `offset:`

```yaml
# Need previous bar's value? Use verbose format with offset:
- lhs: { feature_id: "rsi_14", offset: 1 }
  op: "<"
  rhs: 30
```

### Dotted syntax for structure fields

Access structure outputs with `key.field` notation:

```yaml
- ["swing.high_level", ">", 0]        # Swing high price
- ["trend.direction", "==", 1]        # Trend direction (1=up, -1=down, 0=range)
- ["ms.bos_this_bar", "==", 1]        # Break of structure this bar
- ["fib.level[0.618]", ">", 0]        # Fibonacci level (bracket syntax)
```

### Bracket syntax for indexed access

Fibonacci levels and zone slots use bracket syntax for readability:

```yaml
# Fibonacci levels
- ["fib.level[0.618]", ">", 0]                 # Same as fib.level_0.618
- ["close", "near_pct", "fib.level[0.5]", 1.0]

# Zone slots (derived_zone)
- ["zones.zone[0].state", "==", "active"]       # Newest zone
- ["zones.zone[0].lower", "<", "close"]
- ["zones.zone[1].touched_this_bar", "==", 1]   # Second newest
```

---

## 4. Operator Selection Guide

### Numeric values (prices, indicators)

| Want to check | Use | Example |
|---------------|-----|---------|
| Greater/less than | `>`, `<`, `>=`, `<=` | `["rsi_14", "<", 30]` |
| In a range | `between` | `["rsi_14", "between", [30, 70]]` |
| Near a level (%) | `near_pct` | `["close", "near_pct", "fib.level[0.618]", 1.5]` |
| Near a level ($) | `near_abs` | `["close", "near_abs", "swing.high_level", 50]` |
| Line cross | `cross_above` / `cross_below` | `["ema_9", "cross_above", "ema_21"]` |

### Discrete values (direction, state, flags)

| Want to check | Use | Example |
|---------------|-----|---------|
| Exact match | `==` | `["trend.direction", "==", 1]` |
| Not a value | `!=` | `["ms.bias", "!=", 0]` |
| One of several | `in` | `["trend.direction", "in", [1, 0]]` |

### Never use `==` on floats

Float equality is unreliable. Use `near_pct` or `near_abs` instead:

```yaml
# WRONG - float equality will almost never match
- ["close", "==", "fib.level[0.618]"]

# CORRECT - check proximity
- ["close", "near_pct", "fib.level[0.618]", 0.5]
```

---

## 5. Structure Best Practices

### Always declare dependencies in order

Structures are built top-to-bottom. A structure can only `uses:` keys defined **above** it:

```yaml
structures:
  exec:
    - type: swing                    # 1st: no dependencies
      key: swing
      params: { left: 5, right: 5 }

    - type: trend                    # 2nd: depends on swing
      key: trend
      uses: swing

    - type: fibonacci                # 3rd: depends on swing
      key: fib
      uses: swing
      params:
        levels: [0.382, 0.5, 0.618]
        mode: retracement

    - type: fibonacci                # 4th: depends on swing AND trend
      key: fib_trend
      uses: [swing, trend]
      params:
        levels: [0.618, 0.705, 0.786]
        mode: retracement
        use_trend_anchor: true
```

### Understand warmup requirements

Every structure needs bars to initialize. The engine skips the maximum warmup automatically:

| Structure | Warmup Formula | left=5, right=5 |
|-----------|---------------|-----------------|
| `swing` | `left + right` | 10 bars |
| `trend` | `(left + right) * 5` | 50 bars |
| `market_structure` | `(left + right) * 3` | 30 bars |
| `fibonacci` | `left + right` | 10 bars |
| `zone` | `left + right` | 10 bars |
| `derived_zone` | `left + right + 1` | 11 bars |
| `rolling_window` | `size` | size bars |

**Practical impact:** If your strategy uses `trend` with `left=5, right=5`, the first 50 bars produce no signals. On 15m bars, that is 12.5 hours of dead time.

### Choose the right swing parameters for your timeframe

| Timeframe | Suggested `left`/`right` | Why |
|-----------|--------------------------|-----|
| 1m-5m | 3-5 | Fast pivots for scalping |
| 15m-1h | 5-8 | Balanced pivot detection |
| 4h-D | 3-5 | Fewer bars, wider structure |

Larger windows mean fewer, more significant pivots. Smaller windows mean more frequent, noisier pivots.

### Use significance filtering for noisy timeframes

```yaml
structures:
  exec:
    - type: swing
      key: swing
      params:
        left: 5
        right: 5
        atr_key: atr_14           # Reference ATR indicator
        min_atr_move: 1.0         # Reject pivots < 1.0x ATR move
        major_threshold: 1.5      # Classify pivots > 1.5x ATR as "major"
```

Then filter on significance in actions:
```yaml
- ["swing.high_is_major", "==", true]
```

---

## 6. Fibonacci Anchoring Guide

### Paired mode (default) - recommended for most strategies

Levels recalculate only when a complete swing pair forms (L->H or H->L). Produces stable, non-flickering levels.

```yaml
- type: fibonacci
  key: fib
  uses: swing
  params:
    levels: [0.382, 0.5, 0.618]
    mode: retracement
    # use_paired_anchor: true   (default, can omit)
```

### Trend-wave mode - for ICT/SMC strategies

Freezes levels when trend direction is ranging (direction=0). Requires both swing and trend dependencies.

```yaml
- type: fibonacci
  key: fib_ote
  uses: [swing, trend]
  params:
    levels: [0.618, 0.705, 0.786]
    mode: retracement
    use_trend_anchor: true
    # use_paired_anchor must be false (mutually exclusive)
```

### Extension mode - auto-directional profit targets

In `extension` mode, target direction is determined by the pair:
- Bullish pair (L->H): targets project ABOVE high
- Bearish pair (H->L): targets project BELOW low

```yaml
- type: fibonacci
  key: fib_targets
  uses: swing
  params:
    levels: [0.272, 0.618, 1.0]
    mode: extension               # Auto-direction from pair
```

### Retracement formula

All levels use one formula: `level = high - (ratio x range)`

| Ratio | Result | Use |
|-------|--------|-----|
| < 0 (e.g., -0.272) | Above high | Long targets via retracement mode |
| 0.0 | = high | Reference point |
| 0.382, 0.5, 0.618 | Between high and low | Entry zones |
| 1.0 | = low | Reference point |
| > 1.0 (e.g., 1.272) | Below low | Short targets via retracement mode |

### Level key formatting

The `:g` format strips trailing zeros. Watch for this in your conditions:

| Ratio | Level Key | Shorthand |
|-------|-----------|-----------|
| 0.618 | `level_0.618` | `fib.level[0.618]` |
| 0.5 | `level_0.5` | `fib.level[0.5]` |
| 1.0 | `level_1` (NOT `level_1.0`) | `fib.level[1]` |
| 0.0 | `level_0` (NOT `level_0.0`) | `fib.level[0]` |
| 2.0 | `level_2` | `fib.level[2]` |

---

## 7. Arithmetic Expressions

### Use for difference thresholds and ratios

```yaml
# EMA spread must be positive
- lhs: ["ema_9", "-", "ema_21"]
  op: ">"
  rhs: 0

# Volume spike: current > 2x average
- lhs: ["volume", "/", "volume_sma_20"]
  op: ">"
  rhs: 2.0

# Green candle > 1%
- lhs: [["close", "-", "open"], "/", "open"]
  op: ">"
  rhs: 0.01
```

### Operators: `+`, `-`, `*`, `/`, `%`

Division by zero returns None, which fails the condition (safe).

### Both LHS and RHS support arithmetic

```yaml
# Arithmetic on the left side
- lhs: ["ema_9", "-", "ema_21"]
  op: ">"
  rhs: 100

# Arithmetic on the right side (two equivalent formats)
- ["close", ">", ["swing.high_level", "-", 10]]       # List format
- ["close", ">", { "-": ["swing.high_level", 10] }]    # Dict format
```

### Nesting is supported

```yaml
# (ema_9 - ema_21) / atr_14 > 2
- lhs: [["ema_9", "-", "ema_21"], "/", "atr_14"]
  op: ">"
  rhs: 2.0
```

---

## 8. Window Operators

### `holds_for` - condition must be true for N consecutive bars

Best for: confirming a state before acting.

```yaml
entry_long:
  all:
    - ["ema_9", "cross_above", "ema_21"]
    - holds_for:
        bars: 3
        expr:
          - ["close", ">", "ema_21"]    # Price stayed above EMA for 3 bars
```

### `occurred_within` - condition was true at least once recently

Best for: catching signals that might have fired a few bars ago.

```yaml
entry_long:
  all:
    - ["rsi_14", "<", 40]
    - occurred_within:
        bars: 5
        expr:
          - ["ema_9", "cross_above", "ema_21"]   # Cross happened within 5 bars
```

### `count_true` - condition was true M of N bars

Best for: measuring consistency of a condition.

```yaml
entry_long:
  all:
    - count_true:
        bars: 20
        min_true: 15
        expr:
          - ["close", ">", "ema_50"]    # Above EMA 75% of last 20 bars
```

### Duration-based variants (recommended for cross-timeframe)

Use explicit time instead of bar counts to avoid confusion when changing timeframes:

```yaml
# "RSI overbought for 30 minutes" means the same on any timeframe
holds_for_duration:
  duration: "30m"
  expr:
    - ["rsi_14", ">", 70]
```

Duration ceiling: 24 hours. Max 500 bars after conversion.

---

## 9. Multi-Timeframe Patterns

### Higher timeframe bias + lower timeframe entry

The most common multi-timeframe pattern:

```yaml
timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "12h"
  exec: "low_tf"               # Step on 15m bars

features:
  ema_9:
    indicator: ema
    params: { length: 9 }       # Inherits exec TF (15m)
  ema_21:
    indicator: ema
    params: { length: 21 }      # Inherits exec TF (15m)
  ema_50_1h:
    indicator: ema
    params: { length: 50 }
    tf: "1h"                    # Explicit: computed on 1h bars

actions:
  entry_long:
    all:
      - ["close", ">", "ema_50_1h"]         # 1h bias filter
      - ["ema_9", "cross_above", "ema_21"]   # 15m entry signal
```

### How forward-fill works

Slower-timeframe features hold their last closed value between closes:

```
exec bars (15m):   | bar 1 | bar 2 | bar 3 | bar 4 | bar 5 | bar 6 | bar 7 | bar 8 |
1h feature:        |     1h bar closes here ----->  |     next 1h bar close ----->   |
                   |  100     100     100     100   |  102     102     102     102    |
```

No lookahead: values reflect the **last closed** bar, never partial bars.

### Structure on multiple timeframes

```yaml
structures:
  exec:
    - type: swing
      key: swing
      params: { left: 5, right: 5 }
    - type: trend
      key: trend
      uses: swing

  high_tf:
    "4h":
      - type: swing
        key: swing_4h
        params: { left: 3, right: 3 }
      - type: trend
        key: trend_4h
        uses: swing_4h
```

---

## 10. Common Mistakes

### near_pct tolerance is a percentage, not a ratio

```yaml
# WRONG - 0.03 means 0.03% = 0.0003 ratio (way too tight)
- ["close", "near_pct", "fib.level[0.618]", 0.03]

# CORRECT - 3 means 3% = 0.03 ratio
- ["close", "near_pct", "fib.level[0.618]", 3]
```

The shorthand divides by 100 internally: tolerance `3` becomes ratio `0.03`.

### Don't use `==` on floats

```yaml
# WRONG - floating point comparison
- ["close", "==", 50000.0]

# CORRECT for prices - use proximity
- ["close", "near_abs", 50000.0, 10]    # Within $10
```

### Integer outputs use `==`, not `>`

Structure outputs like `direction` and `bias` are integers, not enums:

```yaml
# CORRECT - integer comparison
- ["trend.direction", "==", 1]        # 1 = uptrend
- ["trend.direction", "==", -1]       # -1 = downtrend
- ["ms.bos_this_bar", "==", 1]        # 1 = true (BOS occurred)

# Also valid for string fields
- ["swing.pair_direction", "==", "bullish"]
```

### Missing features return false, not error

If a feature hasn't warmed up or doesn't exist, any condition referencing it returns `false`. This is by design - it prevents crashes during warmup.

### Dependencies must be declared before use

```yaml
# WRONG - fibonacci declared before its dependency
structures:
  exec:
    - type: fibonacci              # ERROR: swing not defined yet
      key: fib
      uses: swing
    - type: swing
      key: swing
      params: { left: 5, right: 5 }

# CORRECT - swing first, then fibonacci
structures:
  exec:
    - type: swing
      key: swing
      params: { left: 5, right: 5 }
    - type: fibonacci
      key: fib
      uses: swing
      params:
        levels: [0.382, 0.618]
```

### Trend-wave and paired anchors are mutually exclusive

```yaml
# WRONG - can't use both
params:
  use_paired_anchor: true
  use_trend_anchor: true

# CORRECT - trend-wave implies paired internally
params:
  use_paired_anchor: false          # Must be false
  use_trend_anchor: true
```

### Boolean logic nesting

```yaml
# AND: all conditions must be true
all:
  - ["ema_9", ">", "ema_21"]
  - ["rsi_14", "<", 70]

# OR: at least one must be true
any:
  - ["rsi_14", "<", 30]
  - ["close", "<", "swing.low_level"]

# NOT: negate a condition (single condition auto-unwrapped)
not:
  - ["rsi_14", ">", 70]

# NOT: multiple conditions (implicitly wrapped in all)
not:
  - ["rsi_14", ">", 70]
  - ["close", ">", "ema_50"]    # NOT (overbought AND above EMA)

# Nested: (A AND B) OR C
any:
  - all:
      - ["ema_9", ">", "ema_21"]
      - ["rsi_14", "<", 70]
  - ["ms.bos_this_bar", "==", 1]
```

### Use `near_pct` for structure level comparisons

Strict `<`/`>` comparisons against structure levels (swing highs/lows, fib levels) often produce zero trades because price must cross the exact level. Use `near_pct` instead:

```yaml
# RISKY - may produce zero trades if price never exactly crosses the level
- ["close", "<", "swing.low_level"]

# BETTER - catches price within 1.5% of the level
- ["close", "near_pct", "swing.low_level", 1.5]
```

This is especially important on synthetic data where patterns get diluted across multi-timeframe bar expansion (see Section 12).

### Bracket syntax for indexed structure fields

Fibonacci levels and zone slots support bracket syntax which is internally normalized:

```yaml
# These are equivalent:
- ["fib.level[0.618]", ">", 0]      # Bracket syntax (preferred)
- ["fib.level_0.618", ">", 0]       # Underscore syntax (internal form)

# Zone slots:
- ["zones.zone[0].state", "==", "active"]
- ["zones.zone[0].lower", "<", "close"]
```

The bracket syntax `fib.level[0.618]` is converted internally to `level_0.618`. Both work in shorthand conditions.

### Arithmetic supports both list and dict formats

```yaml
# List format
- ["close", ">", ["ema_50", "+", "atr_14"]]

# Dict format (equivalent)
- ["close", ">", {"+": ["ema_50", "atr_14"]}]
```

Both work in LHS and RHS positions. The dict format is useful in shorthand conditions where nesting lists can be confusing.

---

## 11. Strategy Recipes

### Simple EMA crossover

```yaml
features:
  ema_9:
    indicator: ema
    params: { length: 9 }
  ema_21:
    indicator: ema
    params: { length: 21 }

actions:
  entry_long:
    all:
      - ["ema_9", "cross_above", "ema_21"]
  exit_long:
    all:
      - ["ema_9", "cross_below", "ema_21"]

position_policy:
  mode: long_only
  exit_mode: first_hit
```

### RSI oversold bounce with trend filter

```yaml
features:
  rsi_14:
    indicator: rsi
    params: { length: 14 }
  ema_50:
    indicator: ema
    params: { length: 50 }

actions:
  entry_long:
    all:
      - ["close", ">", "ema_50"]         # Trend filter
      - ["rsi_14", "<", 30]              # Oversold
  exit_long:
    all:
      - ["rsi_14", ">", 70]             # Overbought
```

### ICT break of structure entry

```yaml
features:
  ema_21:
    indicator: ema
    params: { length: 21 }

structures:
  exec:
    - type: swing
      key: swing
      params: { left: 5, right: 5 }
    - type: market_structure
      key: ms
      uses: swing

actions:
  entry_long:
    all:
      - ["ms.bos_this_bar", "==", 1]
      - ["ms.bias", "==", 1]
      - ["close", ">", "ema_21"]
```

### Fibonacci OTE (optimal trade entry)

```yaml
features:
  rsi_14:
    indicator: rsi
    params: { length: 14 }

structures:
  exec:
    - type: swing
      key: swing
      params: { left: 5, right: 5 }
    - type: trend
      key: trend
      uses: swing
    - type: fibonacci
      key: fib
      uses: [swing, trend]
      params:
        levels: [0.618, 0.705, 0.786]
        mode: retracement
        use_trend_anchor: true

actions:
  entry_long:
    all:
      - ["trend.direction", "==", 1]
      - ["close", "near_pct", "fib.level[0.705]", 1.5]
      - ["rsi_14", "<", 50]
```

### Volume-confirmed breakout with window operator

```yaml
features:
  ema_50:
    indicator: ema
    params: { length: 50 }
  atr_14:
    indicator: atr
    params: { length: 14 }
  volume_sma_20:
    indicator: sma
    source: volume
    params: { length: 20 }

structures:
  exec:
    - type: swing
      key: swing
      params: { left: 5, right: 5 }

actions:
  entry_long:
    all:
      - ["close", ">", "swing.high_level"]
      - ["close", ">", "ema_50"]
      - lhs: ["volume", "/", "volume_sma_20"]
        op: ">"
        rhs: 1.5
      - holds_for:
          bars: 2
          expr:
            - ["close", ">", "swing.high_level"]

position_policy:
  mode: long_only
  exit_mode: sl_tp_only

risk:
  stop_loss_pct: 2.0
  take_profit_pct: 4.0
```

### Multi-timeframe trend alignment

```yaml
features:
  ema_9:
    indicator: ema
    params: { length: 9 }
  ema_21:
    indicator: ema
    params: { length: 21 }
  ema_50_1h:
    indicator: ema
    params: { length: 50 }
    tf: "1h"
  rsi_14:
    indicator: rsi
    params: { length: 14 }

structures:
  exec:
    - type: swing
      key: swing
      params: { left: 5, right: 5 }
    - type: trend
      key: trend
      uses: swing

actions:
  entry_long:
    all:
      - ["trend.direction", "==", 1]              # 15m trend bullish
      - ["close", ">", "ema_50_1h"]               # Above 1h EMA (higher TF bias)
      - ["ema_9", "cross_above", "ema_21"]         # 15m entry signal
      - ["rsi_14", "<", 70]                        # Not overbought
```

---

## 12. Pitfalls from Production Audits

Lessons learned from the 170-play synthetic audit and 60-play real-data verification (2026-02-08).

### Multi-timeframe bar dilation on synthetic data

When using `generate_synthetic_candles` with 3 timeframes (e.g., 15m/1h/D) and `bars_per_tf=500`, the lower timeframe gets 500 * 96 = 48,000 bars (because 1 daily bar = 96 fifteen-minute bars). Patterns designed for ~500 bars get diluted across 48,000 bars, meaning per-bar price movement becomes ~96x smaller while noise stays the same amplitude.

**Symptoms:** Conditions like `close < swing.low_level` never trigger because the hunt phase barely moves price relative to noise.

**Fix:** Use `near_pct` instead of strict `<`/`>` for structure level comparisons on diluted patterns:

```yaml
# WRONG on multi-TF synthetic - price may never cross exact level
- ["close", "<", "swing.low_level"]

# CORRECT - catches price within proximity of level
- ["close", "near_pct", "swing.low_level", 3]
```

### Impossible conditions produce zero trades silently

The engine does not warn you if your conditions are mathematically impossible. Common examples from the 170-play audit:

```yaml
# IMPOSSIBLE: Donchian upper is ALWAYS >= close (by definition)
- ["close", ">", "donchian_20.upper"]   # Never true

# IMPOSSIBLE: RSI bounds are [0, 100], not larger
- ["rsi_14", ">", 120]                  # Never true

# NEAR-IMPOSSIBLE: Requiring exact equality on continuous values
- ["close", "==", "ema_50"]             # Almost never true
```

Always verify your play produces trades by checking the backtest output.

### PSAR indicator parameter names

The PSAR factory expects specific parameter names. Common wrong names are silently ignored (fall back to defaults):

```yaml
# WRONG - these parameter names are silently ignored
params:
  af_start: 0.02    # Wrong name
  af_max: 0.2       # Wrong name

# CORRECT - use these exact names
params:
  af0: 0.02          # Initial acceleration factor
  af: 0.02           # Acceleration factor step
  max_af: 0.2        # Maximum acceleration factor
```

### near_pct is a percentage, not a ratio

This is the most common mistake. The tolerance value is divided by 100 internally:

```yaml
# WRONG - 0.03 means 0.03% tolerance = nearly impossible match
- ["close", "near_pct", "fib.level[0.618]", 0.03]

# CORRECT - 3 means 3% tolerance
- ["close", "near_pct", "fib.level[0.618]", 3]
```

### Real data requires `--fix-gaps` for initial sync

When running backtests on real data for the first time, DuckDB may not have all required candle data. Use `--fix-gaps` to auto-sync:

```bash
python trade_cli.py backtest run --play my_play --fix-gaps
```

The `--data-env` defaults to `"live"` (uses `market_data_live.duckdb`), not `"backtest"`.

### Preflight validates all three timeframes

The preflight gate validates and auto-syncs data for all three timeframe feeds (`low_tf`, `med_tf`, `high_tf`), not just timeframes with declared features. If your play only declares features on `low_tf` (15m), the preflight still checks that `med_tf` (1h) and `high_tf` (D) data exists.

### Equity curve includes force-close of open positions

At the end of a backtest, any open position is force-closed at the last bar's close price (with slippage and fees applied). The final equity point in the equity curve reflects this force-close. This means `sum(trades.net_pnl)` matches `result.json net_pnl_usdt` within float tolerance.
