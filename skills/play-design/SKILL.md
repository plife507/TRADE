---
name: play-design
description: Guides Play YAML configuration design. Use when creating strategies, configuring indicators, or setting up trading rules.
---

# Play Design Skill

Domain knowledge for designing TRADE strategy configurations (v3.0.3).

## Trading Hierarchy

| Level | Location | Purpose |
|-------|----------|---------|
| **Block** | `strategies/blocks/` | Reusable atomic condition (features + DSL condition) |
| **Play** | `strategies/plays/` | Complete strategy (features + actions + account + risk) |
| **System** | `strategies/systems/` | Multiple Plays with regime-based weighted blending |

**Play** is the primary unit for backtesting.

## Play Structure (v3.0.3)

```yaml
id: "unique_id"
version: "3.0.0"
name: "Strategy Name"
description: "What this play does"

# Account settings
account:
  starting_equity_usdt: 10000.0
  max_leverage: 3.0
  margin_mode: "isolated_usdt"
  fee_model:
    taker_bps: 6.0
    maker_bps: 2.0

# Symbol configuration
symbol_universe: ["BTCUSDT"]
execution_tf: "15m"    # Bar-by-bar stepping (LTF)

# Features (indicators)
features:
  - id: ema_20
    tf: "15m"
    type: indicator
    indicator_type: ema
    params: { length: 20 }
  - id: ema_50_1h          # HTF with TF suffix
    tf: "1h"
    type: indicator
    indicator_type: ema
    params: { length: 50 }

# Structures (incremental market structure)
structures:
  exec:
    - type: swing
      key: swing
      params: { left: 5, right: 5 }
    - type: trend
      key: trend
      depends_on: { swing: swing }

# Actions (entry/exit rules using DSL)
actions:
  - id: entry
    cases:
      - when:
          all:
            - lhs: {feature_id: "ema_20"}
              op: gt
              rhs: {feature_id: "ema_50"}
            - lhs: {feature_id: "rsi_14"}
              op: lt
              rhs: 70
        emit:
          - action: entry_long
  - id: exit
    cases:
      - when:
          any:
            - lhs: {feature_id: "ema_20"}
              op: lt
              rhs: {feature_id: "ema_50"}
            - lhs: {feature_id: "rsi_14"}
              op: gt
              rhs: 80
        emit:
          - action: exit_long

# Position constraints
position_policy:
  mode: "long_only"
  max_positions_per_symbol: 1

# Risk model
risk_model:
  stop_loss:
    type: "atr_multiple"
    value: 2.0
    atr_feature_id: "atr_14"
  take_profit:
    type: "rr_ratio"
    value: 2.0
  sizing:
    model: "percent_equity"
    value: 2.0
    max_leverage: 3.0
```

## Feature Naming Convention (MANDATORY)

**ALWAYS use parameterized names** - encode params in the ID:

| Type | Pattern | Examples |
|------|---------|----------|
| Single-param | `{type}_{param}` | `ema_20`, `rsi_14`, `atr_14` |
| With TF | `{type}_{param}_{tf}` | `ema_50_1h`, `rsi_14_4h` |
| Multi-param | `{type}_{p1}_{p2}` | `bbands_20_2`, `stoch_14_3` |
| MACD | `macd_{fast}_{slow}_{signal}` | `macd_12_26_9` |

**NEVER use semantic names** like `ema_fast`, `ema_slow` - they hide params.

```yaml
# WRONG - semantic names hide parameters
features:
  - id: "ema_fast"    # What length?
    params: {length: 9}

# CORRECT - parameterized names are self-documenting
features:
  - id: "ema_9"       # Clearly length=9
    params: {length: 9}
```

## Available Indicators (42 Total)

### Single-Output (26)

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
| `wma` | `length` | Weighted Moving Average |
| `dema` | `length` | Double EMA |
| `tema` | `length` | Triple EMA |
| `kama` | `length` | Kaufman Adaptive MA |
| `zlma` | `length` | Zero Lag MA |
| `natr` | `length` | Normalized ATR |
| `mfi` | `length` | Money Flow Index |
| `obv` | (none) | On-Balance Volume |
| `cmf` | `length` | Chaikin Money Flow |
| `cmo` | `length` | Chande Momentum Oscillator |
| `linreg` | `length` | Linear Regression |
| `trix` | `length` | Triple Exponential |

### Multi-Output (16)

| Type | Outputs | Params |
|------|---------|--------|
| `macd` | `macd`, `macd_signal`, `macd_hist` | `fast`, `slow`, `signal` |
| `bbands` | `bbl`, `bbm`, `bbu`, `bbb`, `bbp` | `length`, `std` |
| `stoch` | `stoch_k`, `stoch_d` | `k`, `d`, `smooth_k` |
| `adx` | `adx`, `dmp`, `dmn`, `adxr` | `length` |
| `supertrend` | `st`, `std`, `stl`, `sts` | `length`, `multiplier` |
| `kc` | `kcl`, `kcb`, `kcu` | `length`, `scalar` |
| `donchian` | `dcl`, `dcm`, `dcu` | `lower_length`, `upper_length` |
| `aroon` | `aroon_up`, `aroon_down`, `aroon_osc` | `length` |

## Available Structures (6 Total)

| Type | Outputs | Depends On |
|------|---------|------------|
| `swing` | `high_level`, `low_level`, `high_idx`, `low_idx`, `version` | None |
| `fibonacci` | `level_0.382`, `level_0.5`, `level_0.618` | `swing` |
| `zone` | `state`, `upper`, `lower`, `anchor_idx`, `version` | `swing` |
| `trend` | `direction`, `strength`, `bars_in_trend`, `version` | `swing` |
| `rolling_window` | `value` | None |
| `derived_zone` | K slots + aggregates (see below) | `swing` |

### Derived Zone Outputs

**Slot Fields** (per zone 0 to K-1):
- `zone{N}_lower`, `zone{N}_upper`, `zone{N}_state` (NONE/ACTIVE/BROKEN)

**Aggregates**:
- `active_count`, `any_active`, `any_touched`, `closest_active_lower`

## Actions DSL Operators

### Comparison Operators

| Operator | Example | Meaning |
|----------|---------|---------|
| `gt` | `ema_20 > ema_50` | Greater than |
| `gte` | `rsi_14 >= 50` | Greater than or equal |
| `lt` | `rsi_14 < 30` | Less than |
| `lte` | `rsi_14 <= 30` | Less than or equal |
| `eq` | `trend.direction == 1` | Equal (discrete types) |
| `between` | `30 <= rsi_14 <= 70` | In range |
| `near_abs` | `|price - level| <= 10` | Near (absolute) |
| `near_pct` | `|price - level| / level <= 0.01` | Near (percentage) |
| `in` | `direction in [1, -1]` | In set |
| `cross_above` | `ema_9 crosses above ema_21` | Crossover up |
| `cross_below` | `ema_9 crosses below ema_21` | Crossover down |

### Boolean Logic

```yaml
# AND logic
all:
  - lhs: {feature_id: "ema_9"}
    op: gt
    rhs: {feature_id: "ema_21"}
  - lhs: {feature_id: "rsi_14"}
    op: lt
    rhs: 70

# OR logic
any:
  - lhs: {feature_id: "rsi_14"}
    op: lt
    rhs: 30
  - lhs: {feature_id: "rsi_14"}
    op: gt
    rhs: 70

# NOT logic
not:
  lhs: {feature_id: "rsi_14"}
  op: gt
  rhs: 70
```

### Window Operators

```yaml
# Condition true for N consecutive bars
holds_for:
  bars: 5
  expr:
    lhs: {feature_id: "rsi_14"}
    op: gt
    rhs: 50

# Condition was true at least once in last N bars
occurred_within:
  bars: 3
  expr:
    lhs: {feature_id: "ema_9"}
    op: cross_above
    rhs: {feature_id: "ema_21"}

# Condition true at least M times in last N bars
count_true:
  bars: 10
  min_true: 3
  expr:
    lhs: {feature_id: "rsi_14"}
    op: gt
    rhs: 70
```

## Partial Exit Actions (v3.0.3)

```yaml
emit:
  - action: exit_long
    percent: 50      # Close 50% of position
```

## Dynamic Action Metadata (v3.0.3)

Capture feature values at entry/exit:

```yaml
emit:
  - action: entry_long
    metadata:
      entry_atr: {feature_id: "atr_14"}    # Dynamic
      entry_rsi: {feature_id: "rsi_14"}    # Dynamic
      reason: "rsi_oversold"                # Static
```

## Risk Model Types

### Stop Loss

```yaml
# Percentage
stop_loss:
  type: "percent"
  value: 2.0

# ATR-based
stop_loss:
  type: "atr_multiple"
  value: 2.0
  atr_feature_id: "atr_14"

# Structure-based
stop_loss:
  type: "structure"
  buffer_pct: 0.1
```

### Take Profit

```yaml
# Risk-reward ratio
take_profit:
  type: "rr_ratio"
  value: 2.0

# Percentage
take_profit:
  type: "percent"
  value: 4.0

# ATR-based
take_profit:
  type: "atr_multiple"
  value: 3.0
  atr_feature_id: "atr_14"
```

### Sizing Models

```yaml
# Percent of equity
sizing:
  model: "percent_equity"
  value: 2.0

# Fixed USDT
sizing:
  model: "fixed_usdt"
  value: 1000.0

# Risk-based (size to risk X%)
sizing:
  model: "risk_based"
  value: 1.0
```

## Multi-Timeframe Patterns

### Timeframe Roles

| Role | Typical Values | Purpose |
|------|----------------|---------|
| **LTF/exec** | 1m, 5m, 15m | Execution timing, micro-structure |
| **MTF** | 30m, 1h, 2h, 4h | Trade bias, structure context |
| **HTF** | 6h, 8h, 12h, 1D | Higher-level trend (max 1D) |

**Hierarchy Rule**: `HTF >= MTF >= LTF`

### Forward-Fill Behavior

Any timeframe **slower than exec** forward-fills until its bar closes:

```
exec bars (15m):  |  1  |  2  |  3  |  4  |  5  |  6  |  7  |  8  |
HTF bars (1h):    |          HTF bar 0          |     HTF bar 1    ...
                  └─── HTF values unchanged ────┘
```

### MTF Pattern Example

```yaml
execution_tf: "15m"

features:
  # Execution TF (no suffix)
  - id: "ema_9"
    tf: "15m"
    type: indicator
    indicator_type: ema
    params: { length: 9 }

  # HTF trend filter (TF suffix)
  - id: "ema_50_1h"
    tf: "1h"
    type: indicator
    indicator_type: ema
    params: { length: 50 }

actions:
  - id: entry
    cases:
      - when:
          all:
            # HTF filter: price above 1h EMA
            - lhs: {feature_id: "close"}
              op: gt
              rhs: {feature_id: "ema_50_1h"}
            # LTF signal: EMA crossover
            - lhs: {feature_id: "ema_9"}
              op: cross_above
              rhs: {feature_id: "ema_21"}
        emit:
          - action: entry_long
```

## Position Policy

```yaml
position_policy:
  mode: "long_only"              # "long_only", "short_only", "long_short"
  max_positions_per_symbol: 1    # Must be 1
  allow_flip: false              # Not yet supported
  allow_scale_in: false          # Not yet supported
  allow_scale_out: false         # Not yet supported
```

## Best Practices

1. **Parameterized IDs**: Always encode params in feature IDs
2. **Declare Before Use**: Features must be declared before actions reference them
3. **Explicit Params**: No implicit defaults
4. **Validate Often**: Run `play-normalize` after changes
5. **HTF Suffix**: Append timeframe to HTF feature IDs (`ema_50_1h`)
6. **No Lookahead**: All values reflect last CLOSED bar

## See Also

- `docs/specs/PLAY_SYNTAX.md` - Complete syntax reference
- `strategies/plays/_validation/` - Validation play examples
- `src/forge/CLAUDE.md` - Forge development environment
