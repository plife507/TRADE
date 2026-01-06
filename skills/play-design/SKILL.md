---
name: play-design
description: Guides Play YAML configuration design. Use when creating strategies, configuring indicators, or setting up trading rules.
---

# Play Design Skill

Domain knowledge for designing TRADE strategy configurations.

## Play Structure (v3.0.0)

```yaml
id: "unique_id"
version: "3.0.0"
name: "Strategy Name"
description: "What this play does"

# Account settings
account:
  initial_equity_usdt: 10000
  leverage: 3

# Symbol configuration
symbol_universe: ["BTCUSDT"]
execution_tf: "15m"    # Bar-by-bar stepping
mtf: "1h"              # Medium timeframe (optional)
htf: "4h"              # High timeframe (optional)

# Features (indicators)
features:
  - id: ema_20
    type: ema
    params: { length: 20 }
  - id: ema_50
    type: ema
    params: { length: 50 }
  - id: ema_50_1h
    type: ema
    params: { length: 50 }
    tf: "1h"

# Structures (incremental state)
structures:
  - id: swing
    type: swing
    params: { left: 5, right: 5 }
  - id: trend
    type: trend
    depends_on:
      swing: swing

# Actions (entry/exit rules using blocks DSL)
actions:
  - action: entry_long
    when:
      all:
        - ema_20 > ema_50
        - rsi_14 < 70
  - action: exit_long
    when:
      any:
        - ema_20 < ema_50
        - rsi_14 > 80

# Position constraints
position_policy:
  max_positions: 1

# Risk model
risk_model:
  type: atr_stop
  params:
    atr_multiplier: 2.0
    take_profit_r: 2.0
```

## Available Indicators

42 indicators in INDICATOR_REGISTRY including:

| Category | Examples |
|----------|----------|
| Trend | ema, sma, wma, dema, tema |
| Momentum | rsi, macd, stoch, cci, mfi |
| Volatility | bbands, atr, keltner, supertrend |
| Volume | obv, vwap, cmf |
| Structure | pivot_points, fibonacci |

## Available Structures

6 structures in STRUCTURE_REGISTRY:

| Type | Outputs |
|------|---------|
| swing | high_level, low_level, high_idx, low_idx |
| fibonacci | level_0.382, level_0.5, level_0.618 |
| zone | state, upper, lower, anchor_idx |
| trend | direction, strength, bars_in_trend |
| rolling_window | value |
| derived_zone | zone0_*, zone1_*, any_active, closest_active_* |

## Blocks DSL Operators

| Operator | Example | Meaning |
|----------|---------|---------|
| Comparison | `ema_20 > ema_50` | Greater than |
| Boolean | `all: [...]` | All conditions true |
| Boolean | `any: [...]` | Any condition true |
| Boolean | `not: {...}` | Negation |
| Window | `cross_above(ema_20, ema_50)` | Crossed above |
| Window | `cross_below(ema_20, ema_50)` | Crossed below |
| Window | `between(rsi_14, 30, 70)` | Value in range |
| Window | `holds_for(condition, 3)` | True for N bars |
| Window | `occurred_within(condition, 5)` | True within N bars |

## Feature Naming Convention

**ALWAYS use parameterized names** - encode params in the ID:

| Type | Pattern | Examples |
|------|---------|----------|
| Single-param | `{type}_{param}` | `ema_20`, `rsi_14`, `atr_14` |
| With TF | `{type}_{param}_{tf}` | `ema_50_1h`, `rsi_14_4h` |
| Multi-param | `{type}_{p1}_{p2}` | `bbands_20_2`, `stoch_14_3` |
| MACD | `macd_{fast}_{slow}_{signal}` | `macd_12_26_9` |

**NEVER use semantic names** like `ema_fast`, `ema_slow` - they hide params.

## Best Practices

1. **Parameterized IDs**: Encode params in feature IDs
2. **Declare Before Use**: Features must be declared before rules reference them
3. **Explicit Params**: No implicit defaults
4. **Validation**: Run `play-normalize` after changes
