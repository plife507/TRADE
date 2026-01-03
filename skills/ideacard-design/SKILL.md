---
name: ideacard-design
description: Guides IdeaCard YAML configuration design. Use when creating strategies, configuring indicators, or setting up signal rules.
---

# IdeaCard Design Skill

Domain knowledge for designing TRADE strategy configurations.

## IdeaCard Structure

```yaml
meta:
  idea_card_id: "unique_id"
  name: "Strategy Name"
  version: "1.0.0"
  tags: [tag1, tag2]

# Symbol and timeframes
symbol: BTCUSDT
exec_tf: "15m"        # Execution timeframe
mtf: "1h"             # Medium timeframe (optional)
htf: "4h"             # High timeframe (optional)

# Risk settings
risk:
  max_leverage: 3.0
  max_position_size_usdt: 1000
  taker_fee_bps: 6.0

# Features (indicators)
features:
  exec:
    - type: ema
      key: ema_fast
      params: { period: 20 }
    - type: ema
      key: ema_slow
      params: { period: 50 }
  htf:
    - type: ema
      key: ema_htf
      params: { period: 20 }

# Structures (incremental state)
structures:
  exec:
    - type: swing
      key: swing
      params: { left: 5, right: 5 }
    - type: trend
      key: trend
      depends_on:
        swing: swing

# Signal rules
signal_rules:
  entry_rules:
    - direction: "long"
      conditions:
        - tf: "exec"
          indicator_key: "ema_fast"
          operator: "gt"
          indicator_key_compare: "ema_slow"

  exit_rules:
    - direction: "long"
      conditions:
        - tf: "exec"
          indicator_key: "ema_fast"
          operator: "lt"
          indicator_key_compare: "ema_slow"
```

## Available Indicators

42 indicators in INDICATOR_REGISTRY including:

| Category | Examples |
|----------|----------|
| Trend | ema, sma, wma, dema, tema |
| Momentum | rsi, macd, stoch, cci, mfi |
| Volatility | bbands, atr, keltner |
| Volume | obv, vwap, cmf |
| Structure | pivot_points, fibonacci |

## Available Structures

5 structures in STRUCTURE_REGISTRY:

| Type | Outputs |
|------|---------|
| swing | high_level, low_level, high_idx, low_idx |
| fibonacci | level_0.382, level_0.5, level_0.618 |
| zone | state, upper, lower, anchor_idx |
| trend | direction, strength, bars_in_trend |
| rolling_window | value |

## Rule Operators

| Operator | Meaning |
|----------|---------|
| gt | Greater than |
| lt | Less than |
| gte | Greater than or equal |
| lte | Less than or equal |
| eq | Equal |
| neq | Not equal |
| cross_above | Crossed above |
| cross_below | Crossed below |

## Best Practices

1. **Unique Keys**: Each indicator/structure needs unique key
2. **Declare Before Use**: Features must be declared before rules reference them
3. **Explicit Params**: No implicit defaults
4. **Validation**: Run normalize after changes
