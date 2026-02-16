# Play DSL Reference

> Single source of truth for Play YAML syntax. DSL semantics frozen 2026-01-08.
> Validated by 170 synthetic + 60 real-data plays.

## 1. Play Skeleton

```yaml
version: "3.0.0"
name: "my_strategy"
description: "What it does"
symbol: "BTCUSDT"

timeframes:
  low_tf: "15m"        # Fast: execution, entries
  med_tf: "1h"         # Medium: structure, bias
  high_tf: "D"         # Slow: trend, context
  exec: "low_tf"       # POINTER to role, not a value

account:
  starting_equity_usdt: 10000.0
  max_leverage: 3.0
  max_drawdown_pct: 20.0
  margin_mode: "isolated_usdt"
  fee_model: { taker_bps: 5.5, maker_bps: 2.0 }
  slippage_bps: 2.0

features:
  ema_9:
    indicator: ema
    params: { length: 9 }

structures:
  exec:
    - type: swing
      key: swing
      params: { left: 5, right: 5 }

setups:                         # Optional: reusable condition blocks
  trend_up:
    all:
      - ["ema_9", ">", "ema_21"]

actions:
  entry_long:
    all:
      - setup: trend_up
      - ["rsi_14", "<", 70]
  exit_long:
    all:
      - ["ema_9", "<", "ema_21"]

risk:
  stop_loss_pct: 2.0
  take_profit_pct: 4.0
  max_position_pct: 100.0

position_policy:
  mode: "long_only"          # long_only | short_only | long_short
  exit_mode: "first_hit"     # sl_tp_only | signal | first_hit
  max_positions_per_symbol: 1

entry:                        # Optional: limit order entries
  order_type: "MARKET"        # MARKET | LIMIT
  limit_offset_pct: 0.05      # % offset from close for LIMIT
  time_in_force: "GTC"        # GTC | IOC | FOK | PostOnly
  expire_after_bars: 10       # 0 = no expiry

variables:                    # Optional template resolution
  fast_len: 9
```

## 2. Timeframe Rules (ENFORCED)

YAML keys: `low_tf`, `med_tf`, `high_tf`, `exec`. Never `ltf`, `htf`, `LTF`, `HTF`, `MTF`, `exec_tf`.
Prose: "higher timeframe" not HTF, "execution timeframe" not exec TF.

- `exec` is a **pointer** (`"low_tf"`, `"med_tf"`, or `"high_tf"`), never a raw value like `"15m"`
- Hierarchy: `high_tf >= med_tf >= low_tf` (in minutes)
- Valid Bybit intervals: `1m,3m,5m,15m,30m,1h,2h,4h,6h,12h,D,W,M` (no 8h)
- 1m candles are always loaded regardless of exec (drives fill sim, TP/SL, signal subloop)

## 3. Features (Indicators)

### Naming: encode parameters

```yaml
ema_9:               # CORRECT - length=9 obvious
  indicator: ema
  params: { length: 9 }
ema_fast:            # WRONG - hides parameters
  indicator: ema
  params: { length: 9 }
ema_50_1h:           # Cross-TF: append timeframe
  indicator: ema
  params: { length: 50 }
  tf: "1h"
```

### Full syntax

```yaml
features:
  ema_21:
    indicator: ema
    params: { length: 21 }
    tf: "1h"           # Optional: defaults to exec TF. Forward-fills if slower.
    source: close      # Optional: close|open|high|low|volume|hl2|hlc3|ohlc4
```

The `tf:` field accepts either a **concrete timeframe** (`"1h"`, `"4h"`, `"D"`) or a **role name** (`"low_tf"`, `"med_tf"`, `"high_tf"`). Role names resolve to their concrete value from the `timeframes:` section at engine startup.

```yaml
# Both are equivalent when med_tf: "1h"
tf: "1h"           # Concrete timeframe (preferred)
tf: "med_tf"       # Role name (resolved at runtime)
```

### Timeframe inheritance

| Feature `tf:` | Behavior |
|----------------|----------|
| Not specified | Inherits exec TF, updates every exec bar |
| Slower than exec | Forward-fills last closed bar value |
| Faster than exec | Sampled at exec bar boundaries |

Forward-fill = hold last closed bar value. No lookahead.

### Built-in price features (no declaration needed)

| Feature | Resolution | Notes |
|---------|------------|-------|
| `open`, `high`, `low`, `close`, `volume` | Per exec bar | Standard OHLCV |
| `last_price` | Every 1m | Actual trade price. Use for precise entries. |
| `mark_price` | Every 1m | Index price. Used internally for margin/PnL. |

In backtest, `last_price` and `mark_price` both equal 1m close. In live they can diverge.

### Single-output indicators (25)

| Indicator | Params |
|-----------|--------|
| `ema` | `length` |
| `sma` | `length` |
| `wma` | `length` |
| `dema` | `length` |
| `tema` | `length` |
| `trima` | `length` |
| `zlma` | `length` |
| `kama` | `length` |
| `alma` | `length`, `sigma`, `offset` |
| `rsi` | `length` |
| `atr` | `length` |
| `natr` | `length` |
| `cci` | `length` |
| `willr` | `length` |
| `roc` | `length` |
| `mom` | `length` |
| `mfi` | `length` |
| `obv` | (none) |
| `cmf` | `length` |
| `cmo` | `length` |
| `linreg` | `length` |
| `midprice` | `length` |
| `ohlc4` | (none) |
| `uo` | `fast`, `medium`, `slow` |
| `vwap` | (none) |

### Multi-output indicators (19)

| Indicator | Outputs | Params |
|-----------|---------|--------|
| `macd` | `macd`, `signal`, `histogram` | `fast`, `slow`, `signal` |
| `bbands` | `lower`, `middle`, `upper`, `bandwidth`, `percent_b` | `length`, `std` |
| `stoch` | `k`, `d` | `k`, `d`, `smooth_k` |
| `stochrsi` | `k`, `d` | `length`, `rsi_length`, `k`, `d` |
| `adx` | `adx`, `dmp`, `dmn`, `adxr` | `length` |
| `aroon` | `up`, `down`, `osc` | `length` |
| `kc` | `lower`, `basis`, `upper` | `length`, `scalar` |
| `donchian` | `lower`, `middle`, `upper` | `lower_length`, `upper_length` |
| `supertrend` | `trend`, `direction`, `long`, `short` | `length`, `multiplier` |
| `psar` | `long`, `short`, `af`, `reversal` | `af0`, `af`, `max_af` |
| `squeeze` | `sqz`, `on`, `off`, `no_sqz` | `bb_length`, `bb_std`, `kc_length`, `kc_scalar` |
| `vortex` | `vip`, `vim` | `length` |
| `dm` | `dmp`, `dmn` | `length` |
| `fisher` | `fisher`, `signal` | `length` |
| `tsi` | `tsi`, `signal` | `fast`, `slow`, `signal` |
| `kvo` | `kvo`, `signal` | `fast`, `slow`, `signal` |
| `ppo` | `ppo`, `histogram`, `signal` | `fast`, `slow`, `signal` |
| `trix` | `trix`, `signal` | `length`, `signal` |
| `anchored_vwap` | `value` | `anchor_source` |

Access multi-output fields: `"macd_12_26_9.histogram"` (dotted shorthand) or `{feature_id: "macd_12_26_9", field: "histogram"}`.

## 4. Structures

Declared under `structures:` grouped by timeframe role. Dependencies via `uses:` must reference keys defined **above**.

### Timeframe grouping keys

Valid top-level keys under `structures:` are: **`exec`**, **`low_tf`**, **`med_tf`**, **`high_tf`**.

Each key resolves to its concrete timeframe from the `timeframes:` section. No need to re-specify the timeframe -- the mapping is already defined:

```yaml
timeframes:
  low_tf: "15m"      # structures under low_tf: run on 15m
  med_tf: "1h"       # structures under med_tf: run on 1h
  high_tf: "D"       # structures under high_tf: run on D
  exec: "low_tf"     # structures under exec: run on 15m (same as low_tf)
```

```yaml
structures:
  exec:                           # Resolves to exec TF (15m)
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
        levels: [0.382, 0.5, 0.618]
        mode: retracement
        use_trend_anchor: true
  high_tf:                        # Resolves to high_tf (D)
    - type: swing
      key: swing_D
      params: { left: 3, right: 3 }
    - type: trend
      key: trend_D
      uses: swing_D
```

### Structure types and outputs

**swing** (no deps)
- Params: `left`, `right`, optional `atr_key`, `min_atr_move`, `major_threshold`
- Primary outputs: `high_level`, `high_idx`, `low_level`, `low_idx`, `version`
- Version outputs: `high_version` (increments only on confirmed high pivot), `low_version` (increments only on confirmed low pivot). Unlike `version` which increments on any pivot, these track individual pivot types. Used internally by anchored VWAP for anchor resets.
- Significance outputs (require `atr_key`): `high_significance`, `low_significance`, `high_is_major`, `low_is_major`
- Paired pivot outputs: `pair_high_level`, `pair_high_idx`, `pair_low_level`, `pair_low_idx`, `pair_direction` ("bullish"/"bearish"), `pair_version`, `pair_anchor_hash`
- Tracking outputs: `last_confirmed_pivot_idx`, `last_confirmed_pivot_type` ("high"/"low")

**trend** (uses: swing)
- Params: `wave_history_size` (default 4)
- Outputs: `direction` (1/-1/0 int), `strength` (0-2), `bars_in_trend`, `wave_count`, `last_wave_direction`, `last_hh`, `last_hl`, `last_lh`, `last_ll`, `version`

**market_structure** (uses: swing)
- Params: `confirmation_close` (default false)
- Outputs: `bias` (1/-1/0 int), `bos_this_bar`, `choch_this_bar`, `bos_direction`, `choch_direction`, `last_bos_idx`, `last_bos_level`, `last_choch_idx`, `last_choch_level`, `break_level_high`, `break_level_low`, `version`
- BOS = continuation (breaks swing level in trend direction). CHoCH = reversal (breaks against trend).

**fibonacci** (uses: swing, optionally trend)
- Params: `levels`, `mode` (retracement|extension|extension_up|extension_down), `use_paired_anchor` (default true), `use_trend_anchor` (false)
- Level outputs: `level[0.382]`, `level[0.5]`, `level[0.618]` etc. (bracket syntax)
- Anchor outputs: `anchor_high`, `anchor_low`, `range`, `anchor_direction` ("bullish"/"bearish"/""), `anchor_hash`, `anchor_trend_direction`
- Formula: `level = high - (ratio * range)`
- Trend-wave mode requires `uses: [swing, trend]` + `use_trend_anchor: true` (implies `use_paired_anchor: false`)

**zone** (uses: swing)
- Params: `zone_type` (demand|supply), `width_atr`
- Outputs: `state` ("active"|"broken"|"none"), `upper`, `lower`, `anchor_idx`, `version`

**rolling_window** (no deps)
- Params: `mode` (min|max), `size`, `source` (open|high|low|close)
- Outputs: `value`

**derived_zone** (uses: swing)
- Params: `levels`, `mode`, `max_active` (K slots), `width_pct`, `use_paired_source` (default true), `break_tolerance_pct`
- Slot outputs (per zone N): `zone[N].lower`, `zone[N].upper`, `zone[N].state`, `zone[N].anchor_idx`, `zone[N].age_bars`, `zone[N].touched_this_bar`, `zone[N].touch_count`, `zone[N].last_touch_age`, `zone[N].inside`, `zone[N].instance_id`
- Aggregate outputs: `active_count`, `any_active`, `any_touched`, `any_inside`, `first_active_lower`, `first_active_upper`, `first_active_idx`, `newest_active_idx`, `source_version`

### Warmup formulas

| Structure | Formula | left=5,right=5 |
|-----------|---------|-----------------|
| swing | left + right | 10 |
| trend | (left+right) * 5 | 50 |
| market_structure | (left+right) * 3 | 30 |
| fibonacci/zone | left + right | 10 |
| derived_zone | left + right + 1 | 11 |
| rolling_window | size | size |

Engine skips first `max(all_warmups)` bars automatically.

### Referencing structures in actions

```yaml
- ["trend.direction", "==", 1]            # Dotted shorthand
- ["fib.level[0.618]", ">", 0]           # Bracket syntax
- ["zones.zone[0].state", "==", "active"] # Zone slot bracket syntax
- [{feature_id: "swing", field: "high_level"}, ">", 0]  # Verbose
```

## 5. Actions

### Action types

`entry_long`, `entry_short`, `exit_long`, `exit_short`, `exit_all`, `no_action`

### Exit modes

| Mode | Behavior |
|------|----------|
| `sl_tp_only` | Exits ONLY via SL/TP. Signal exits ignored. |
| `signal` | Exits via signal. SL/TP as emergency stops. |
| `first_hit` | Whichever triggers first: signal OR SL/TP. |

TP/SL always fire BEFORE signal-based closes.

### Syntax

```yaml
actions:
  # Implicit all (list = AND)
  entry_long:
    - ["ema_9", ">", "ema_21"]

  # Explicit all/any
  entry_long:
    all:
      - ["ema_9", ">", "ema_21"]
      - ["rsi_14", "<", 70]
  exit_long:
    any:
      - ["rsi_14", ">", 80]
      - ["ema_9", "<", "ema_21"]
```

### Cases syntax (first-match)

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

### Partial exits and metadata

```yaml
emit:
  - action: exit_long
    percent: 50                          # Close 50% of position
  - action: entry_long
    metadata:
      entry_atr: {feature_id: "atr_14"}  # Captured at entry
      entry_reason: "oversold_bounce"     # Static string
```

## 6. Setups (Reusable Condition Blocks)

Define named condition blocks that can be referenced from actions or other setups.

```yaml
setups:
  trend_up:
    all:
      - ["close", ">", "ema_50"]
      - ["ema_9", ">", "ema_21"]

  rsi_oversold:
    all:
      - ["rsi_14", "<", 30]

  pullback_entry:
    all:
      - setup: trend_up          # Reference another setup
      - setup: rsi_oversold

actions:
  entry_long:
    all:
      - setup: pullback_entry    # Use setup in action
      - ["volume", ">", "vol_sma_20"]
```

### Rules

- Setups are parsed before actions (so references resolve correctly)
- Setups can reference other setups (nested composition)
- Circular references are detected at parse time: `A -> B -> A` raises `ValueError`
- Undeclared setup references raise `ValueError` with suggestions
- Feature references inside setups are validated against declared features
- Setup conditions use the same syntax as action conditions (`all:`, `any:`, `not:`, operators)

### Evaluation

Setup expressions are cached per bar. If `pullback_entry` is referenced in both `entry_long` and `exit_short`, it evaluates once and reuses the result.

## 7. Operators

### Condition formats

```yaml
# 3-element shorthand (preferred): [lhs, op, rhs]
- ["ema_9", ">", "ema_21"]

# 4-element (proximity only): [lhs, op, rhs, tolerance]
- ["close", "near_pct", "fib.level[0.618]", 3]

# Verbose dict (when you need offset:)
- lhs: {feature_id: "rsi_14", offset: 1}
  op: "<"
  rhs: 30
```

### Comparison operators

| Op | Types | Example |
|----|-------|---------|
| `>` `<` `>=` `<=` | Numeric | `["ema_9", ">", "ema_21"]` |
| `==` `!=` | Discrete only (NOT float) | `["trend.direction", "==", 1]` |
| `between` | Numeric (inclusive) | `["rsi_14", "between", [30, 70]]` |
| `near_pct` | Numeric | `["close", "near_pct", "fib.level[0.618]", 3]` |
| `near_abs` | Numeric | `["close", "near_abs", "swing.high_level", 50]` |
| `in` | Discrete | `["trend.direction", "in", [1, 0]]` |
| `cross_above` | Numeric | `["ema_9", "cross_above", "ema_21"]` |
| `cross_below` | Numeric | `["ema_9", "cross_below", "ema_21"]` |

**CRITICAL: `near_pct` tolerance is a PERCENTAGE.** `3` means 3% (ratio 0.03). Writing `0.03` means 0.03% = almost never matches.

### Boolean logic

```yaml
all:                          # AND
  - ["ema_9", ">", "ema_21"]
  - ["rsi_14", "<", 70]
any:                          # OR
  - ["rsi_14", "<", 30]
  - ["close", "<", "swing.low_level"]
not:                          # NOT (single or implicit all)
  - ["rsi_14", ">", 70]
# Nested: (A AND B) OR C
any:
  - all:
      - ["ema_9", ">", "ema_21"]
      - ["rsi_14", "<", 70]
  - ["ms.bos_this_bar", "==", 1]
```

### Missing values

`None`, `NaN`, `Infinity`, feature-not-found, offset-exceeds-history all return `false` (not error).

## 8. Arithmetic

Operators: `+`, `-`, `*`, `/`, `%`. Division by zero returns None (fails condition).

```yaml
# List format: [operand, op, operand]
- lhs: ["ema_9", "-", "ema_21"]
  op: ">"
  rhs: 100

# Dict format in RHS: {op: [operand, operand]}
- ["close", ">", {"-": ["swing.high_level", 10]}]

# Nested
- lhs: [["close", "-", "open"], "/", "open"]
  op: ">"
  rhs: 0.01

# Volume spike
- lhs: ["volume", "/", "volume_sma_20"]
  op: ">"
  rhs: 2.0
```

Both list and dict formats work in LHS and RHS positions.

## 9. Window Operators

### Bar-based

```yaml
holds_for:                    # ALL N bars must satisfy
  bars: 5
  anchor_tf: "15m"            # Optional: scale to TF granularity
  expr:
    - ["close", ">", "ema_21"]

occurred_within:              # At least ONE bar satisfied
  bars: 10
  anchor_tf: "15m"            # Optional
  expr:
    - ["ema_9", "cross_above", "ema_21"]

count_true:                   # At least M of N bars
  bars: 20
  min_true: 15
  anchor_tf: "15m"            # Optional
  expr:
    - ["close", ">", "ema_50"]
```

### Duration-based (recommended for cross-timeframe)

```yaml
holds_for_duration:
  duration: "30m"             # Explicit time, not bar count
  expr:
    - ["rsi_14", ">", 70]

occurred_within_duration:
  duration: "4h"              # At least one occurrence within 4 hours
  expr:
    - ["ema_9", "cross_above", "ema_21"]

count_true_duration:
  duration: "1d"              # At least M occurrences within duration
  min_true: 5
  expr:
    - ["close", ">", "ema_50"]
```

Duration formats: `"5m"`, `"1h"`, `"1d"` etc. Max 24h, max 500 bars after conversion.

## 10. Risk Model

Two equivalent formats: `risk:` (shorthand) or `risk_model:` (full).

### Shorthand (recommended)

```yaml
risk:
  stop_loss_pct: 2.0         # ROI-based: 2% of margin at risk
  take_profit_pct: 4.0       # ROI-based: 4% margin profit
  max_position_pct: 100.0
```

**Percentages are ROI-based** (margin %), not price-based. With 10x leverage: 2% SL = 0.2% price move.

### Full format

```yaml
risk_model:
  stop_loss:
    type: "percent"           # percent | atr_multiple | structure | fixed_points | trailing_atr | trailing_pct
    value: 2.0
  take_profit:
    type: "rr_ratio"          # percent | rr_ratio | atr_multiple | fixed_points
    value: 2.0                # 2R = 2x stop distance
  sizing:
    model: "percent_equity"   # percent_equity | risk_based | fixed_usdt
    value: 10.0               # 10% of equity as margin
    max_leverage: 3.0
```

ATR-based stops require `atr_feature_id: "atr_14"` referencing a declared feature.

### Trailing stops

```yaml
risk:
  stop_loss:
    type: "trailing_atr"        # Trail using ATR distance
    atr_multiplier: 2.0         # Distance = ATR x multiplier
    atr_feature_id: "atr_14"    # Required for ATR trailing
    activation_pct: 1.0         # Start trailing after 1% profit (0 = immediate)
  # OR
  stop_loss:
    type: "trailing_pct"        # Trail using % distance
    trail_pct: 1.5              # Distance = price x 1.5%
    activation_pct: 1.0         # Start trailing after 1% profit
```

### Break-even stop

```yaml
risk:
  break_even:
    activation_pct: 1.0         # Move to BE after 1% profit
    offset_pct: 0.1             # Place stop 0.1% above entry (positive = favorable)
```

### TP/SL order types

```yaml
risk:
  tp_order_type: "Market"       # Market | Limit (Bybit convention)
  sl_order_type: "Market"       # Market | Limit
```

## 11. Entry Order Configuration

```yaml
entry:
  order_type: "LIMIT"           # MARKET (default) | LIMIT
  limit_offset_pct: 0.05        # % offset from close price (for LIMIT orders)
  time_in_force: "GTC"          # GTC (default) | IOC | FOK | PostOnly
  expire_after_bars: 10         # Bars before unfilled LIMIT order expires (0 = no expiry)
```

| Field | Type | Default | Valid Values |
|-------|------|---------|-------------|
| `order_type` | str | `"MARKET"` | `MARKET`, `LIMIT` |
| `limit_offset_pct` | float | `0.0` | >= 0 |
| `time_in_force` | str | `"GTC"` | `GTC`, `IOC`, `FOK`, `PostOnly` |
| `expire_after_bars` | int | `0` | >= 0 (0 = no expiry) |

## 12. Multi-Timeframe

### Top-down approach

1. Higher timeframe (D/12h): directional bias
2. Medium timeframe (1h-4h): structure, support/resistance
3. Lower timeframe (5m-15m): precise entry timing

```yaml
timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "D"
  exec: "low_tf"           # Step on 15m bars

features:
  ema_9:                     # Inherits 15m (exec)
    indicator: ema
    params: { length: 9 }
  ema_50_1h:                 # Explicit 1h, forward-fills
    indicator: ema
    params: { length: 50 }
    tf: "1h"

structures:
  exec:                          # Swing/trend on 15m (exec TF)
    - type: swing
      key: swing
      params: { left: 5, right: 5 }
    - type: trend
      key: trend
      uses: swing
  high_tf:                       # Daily swing (resolves to D)
    - type: swing
      key: swing_D
      params: { left: 3, right: 3 }

actions:
  entry_long:
    all:
      - ["close", ">", "ema_50_1h"]        # Higher TF bias
      - ["trend.direction", "==", 1]        # Exec TF trend
      - ["ema_9", "cross_above", "ema_21"]  # Exec TF signal
```

### 1m signal subloop

`last_price` updates every 1m within exec bars. Use for precise entries:

```yaml
- ["last_price", "cross_above", "ema_200_4h"]  # 1m granularity
```

## 13. Account Configuration

```yaml
account:
  starting_equity_usdt: 10000.0    # Required: starting capital
  max_leverage: 3.0                 # Required: max leverage (1.0 = no margin)
  max_drawdown_pct: 20.0            # Required: halt trading at 20% drawdown
  margin_mode: "isolated_usdt"      # Must be "isolated_usdt"
  fee_model:
    taker_bps: 5.5                  # Taker fee in basis points (0.055%)
    maker_bps: 2.0                  # Maker fee in basis points (0.02%)
  slippage_bps: 2.0                 # Slippage in basis points
  min_trade_notional_usdt: 10.0     # Minimum position size
  max_notional_usdt: 100000.0       # Optional: max notional cap
  max_margin_usdt: 5000.0           # Optional: max margin per position
  maintenance_margin_rate: 0.005    # Optional: 0.5% MMR
```

| Field | Required | Default (from config/defaults.yml) |
|-------|----------|-------|
| `starting_equity_usdt` | Yes | 10000.0 |
| `max_leverage` | Yes | 1.0 |
| `max_drawdown_pct` | Yes | 20.0 |
| `margin_mode` | No | `"isolated_usdt"` |
| `fee_model.taker_bps` | No | 5.5 |
| `fee_model.maker_bps` | No | 2.0 |
| `slippage_bps` | No | 2.0 |
| `min_trade_notional_usdt` | No | 10.0 |
| `maintenance_margin_rate` | No | 0.005 |

## 14. Synthetic Data & Validation

### Embedding in plays

The `synthetic:` block is **metadata only**. It defines how to generate test data for the play but is **NOT auto-activated**. To use it, pass `--synthetic` on the CLI:

```bash
# Uses real data (synthetic: block IGNORED)
python trade_cli.py backtest run --play my_play

# Uses synthetic data via CLI args
python trade_cli.py backtest run --play my_play --synthetic

# Programmatic callers (validate.py) auto-use synthetic: block via create_engine_from_play()
```

```yaml
synthetic:
  pattern: "trend_up_clean"
  bars: 500
  seed: 42
  config:                     # Optional overrides
    trend_magnitude: 0.25
    pullback_depth: 0.20

expected:                     # Optional assertions
  min_trades: 3
  pnl_direction: positive
```

Choose a pattern that matches the strategy concept:

| Concept | Good patterns |
|---------|--------------|
| Mean reversion / scalping | `range_wide`, `range_tight`, `vol_squeeze_expand` |
| Trend following | `trend_up_clean`, `trend_down_clean`, `trend_stairs` |
| Breakout | `breakout_clean`, `breakout_retest`, `vol_squeeze_expand` |
| Range trading | `range_tight`, `range_wide`, `range_ascending` |

For short strategies, use the corresponding down/bear patterns.

### Pattern catalog

**Trend**: `trend_up_clean`, `trend_down_clean`, `trend_grinding`, `trend_parabolic`, `trend_exhaustion`, `trend_stairs`
**Range**: `range_tight`, `range_wide`, `range_ascending`, `range_descending`
**Reversal**: `reversal_v_bottom`, `reversal_v_top`, `reversal_double_bottom`, `reversal_double_top`
**Breakout**: `breakout_clean`, `breakout_false`, `breakout_retest`
**Volatility**: `vol_squeeze_expand`, `vol_spike_recover`, `vol_spike_continue`, `vol_decay`
**Liquidity**: `liquidity_hunt_lows`, `liquidity_hunt_highs`, `choppy_whipsaw`, `accumulation`, `distribution`
**Multi-TF**: `mtf_aligned_bull`, `mtf_aligned_bear`, `mtf_pullback_bull`, `mtf_pullback_bear`
**Legacy**: `trending`, `ranging`, `volatile`, `multi_tf_aligned`

### Validation tiers

```bash
python trade_cli.py validate quick         # ~30s, 5 core plays
python trade_cli.py validate standard      # ~2min, core + audits
python trade_cli.py validate full          # ~10min, 170-play suite
python trade_cli.py validate pre-live --play X  # Real-data check
```

## 15. Pitfalls

### near_pct is a percentage, not a ratio
```yaml
# WRONG: 0.03 = 0.03% = almost never matches
- ["close", "near_pct", "fib.level[0.618]", 0.03]
# CORRECT: 3 = 3%
- ["close", "near_pct", "fib.level[0.618]", 3]
```

### Never use == on floats
```yaml
# WRONG
- ["close", "==", "fib.level[0.618]"]
# CORRECT
- ["close", "near_pct", "fib.level[0.618]", 0.5]
```

### PSAR parameter names
```yaml
# WRONG (silently ignored, falls back to defaults)
params: { af_start: 0.02, af_max: 0.2 }
# CORRECT
params: { af0: 0.02, af: 0.02, max_af: 0.2 }
```

### Impossible conditions produce zero trades silently
```yaml
# Donchian upper >= close by definition - never true
- ["close", ">", "donchian_20.upper"]
# RSI bounds are [0,100]
- ["rsi_14", ">", 120]
```

### Use near_pct for structure level comparisons
Strict `<`/`>` against swing/fib levels often produces zero trades. Use `near_pct` instead, especially on synthetic data where multi-TF bar dilation dilutes patterns ~96x.

### Dependencies must be declared before use
Structures are built top-to-bottom. A structure can only `uses:` keys defined above it.

### Trend-wave and paired anchors are mutually exclusive
`use_trend_anchor: true` requires `use_paired_anchor: false`.

### Fib level key formatting
`:g` format strips trailing zeros: ratio `1.0` becomes key `level_1` (not `level_1.0`). Bracket syntax handles this: `fib.level[1]`.

### Offset support

| Feature | offset=0 | offset=1 | offset>1 |
|---------|----------|----------|----------|
| `last_price` | Current 1m | Previous 1m | Not supported |
| `mark_price` | Current | Not supported | - |
| `close` | Current bar | Previous bar | Supported |

## 16. Recipes

### EMA crossover with trend filter
```yaml
features:
  ema_9: { indicator: ema, params: { length: 9 } }
  ema_21: { indicator: ema, params: { length: 21 } }
  ema_50_1h: { indicator: ema, params: { length: 50 }, tf: "1h" }
actions:
  entry_long:
    all:
      - ["close", ">", "ema_50_1h"]
      - ["ema_9", "cross_above", "ema_21"]
```

### ICT BOS entry with cases
```yaml
structures:
  exec:
    - type: swing
      key: swing
      params: { left: 5, right: 5, atr_key: atr_14 }
    - type: market_structure
      key: ms
      uses: swing
actions:
  - id: entry
    cases:
      - when:
          all:
            - ["ms.bos_this_bar", "==", 1]
            - ["ms.bias", "==", 1]
        emit:
          - action: entry_long
      - when:
          all:
            - ["ms.bos_this_bar", "==", 1]
            - ["ms.bias", "==", -1]
        emit:
          - action: entry_short
```

### Fibonacci OTE with trend-wave anchoring
```yaml
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

### Zone entry with window operator
```yaml
structures:
  exec:
    - type: swing
      key: swing
      params: { left: 5, right: 5 }
    - type: derived_zone
      key: fib_zones
      uses: swing
      params:
        levels: [0.5, 0.618]
        mode: retracement
        max_active: 3
        width_pct: 0.002
actions:
  entry_long:
    all:
      - ["fib_zones.any_inside", "==", 1]
      - occurred_within:
          bars: 10
          expr:
            - ["rsi_14", "<", 30]
      - ["rsi_14", ">", 35]
```

### Breakout with volume confirmation and ATR risk
```yaml
features:
  atr_14: { indicator: atr, params: { length: 14 } }
  volume_sma_20: { indicator: sma, source: volume, params: { length: 20 } }
structures:
  exec:
    - type: rolling_window
      key: rolling_high
      params: { mode: max, size: 20, source: high }
actions:
  entry_long:
    all:
      - ["close", ">", "rolling_high.value"]
      - lhs: ["volume", "/", "volume_sma_20"]
        op: ">"
        rhs: 2.0
risk_model:
  stop_loss: { type: "atr_multiple", value: 2.0, atr_feature_id: "atr_14" }
  take_profit: { type: "rr_ratio", value: 2.0 }
  sizing: { model: "risk_based", value: 1.0, max_leverage: 5.0 }
```

### Trailing stop with break-even
```yaml
features:
  atr_14: { indicator: atr, params: { length: 14 } }
risk:
  stop_loss:
    type: "trailing_atr"
    atr_multiplier: 2.0
    atr_feature_id: "atr_14"
    activation_pct: 1.0
  take_profit_pct: 6.0
  max_position_pct: 10.0
  break_even:
    activation_pct: 1.0
    offset_pct: 0.1
```

### Limit order entry with expiry
```yaml
entry:
  order_type: LIMIT
  limit_offset_pct: 0.05
  time_in_force: GTC
  expire_after_bars: 5
risk:
  stop_loss_pct: 2.0
  take_profit_pct: 4.0
  tp_order_type: Limit
  sl_order_type: Market
```

## 17. Defaults Reference

Source: `config/defaults.yml`

| Field | Default |
|-------|---------|
| `taker_bps` | 5.5 (0.055%) |
| `maker_bps` | 2.0 (0.02%) |
| `slippage_bps` | 2.0 |
| `margin.mode` | isolated_usdt |
| `margin.maintenance_margin_rate` | 0.005 (0.5%) |
| `max_leverage` | 1.0 |
| `risk_per_trade_pct` | 1.0 |
| `max_drawdown_pct` | 20.0 |
| `starting_equity_usdt` | 10000.0 |
| `min_trade_notional_usdt` | 10.0 |
| `mode` | long_only |
| `exit_mode` | sl_tp_only |
| `entry_order_type` | MARKET |
| `time_in_force` | GTC |
| `tp_order_type` | Market |
| `sl_order_type` | Market |

## 18. Deprecations

| Removed | Use Instead |
|---------|-------------|
| `blocks:` (top-level) | `actions:` |
| `signal_rules:` | `actions:` |
| `margin_mode: "isolated"` | `margin_mode: "isolated_usdt"` |
