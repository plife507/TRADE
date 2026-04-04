# Conditions & Operators

## Condition syntax

```yaml
# 3-element (preferred): [lhs, op, rhs]
- ["ema_9", ">", "ema_21"]

# 4-element (proximity): [lhs, op, rhs, tolerance]
- ["close", "near_pct", "fib.level[0.618]", 3]

# Verbose dict (when offset needed):
- lhs: {feature_id: "rsi_14", offset: 1}
  op: "<"
  rhs: 30
```

## Operators

| Op | Types | Example |
|----|-------|---------|
| `>` `<` `>=` `<=` | Numeric | `["ema_9", ">", "ema_21"]` |
| `==` `!=` | Discrete only (INT/BOOL/ENUM, NOT float) | `["trend.direction", "==", 1]` |
| `between` | Numeric (inclusive) | `["rsi_14", "between", [30, 70]]` |
| `near_pct` | Numeric | `["close", "near_pct", "fib.level[0.618]", 3]` — 3 = 3% |
| `near_abs` | Numeric | `["close", "near_abs", "swing.high_level", 50]` |
| `in` | Discrete | `["trend.direction", "in", [1, 0]]` |
| `cross_above` | Numeric | `["ema_9", "cross_above", "ema_21"]` |
| `cross_below` | Numeric | `["ema_9", "cross_below", "ema_21"]` |

## Boolean logic

```yaml
all:                               # AND
  - ["ema_9", ">", "ema_21"]
  - ["rsi_14", "<", 70]

any:                               # OR
  - ["rsi_14", "<", 30]
  - ["close", "<", "swing.low_level"]

not:                               # NOT
  - ["rsi_14", ">", 70]

# Nested: (A AND B) OR C
any:
  - all:
      - ["ema_9", ">", "ema_21"]
      - ["rsi_14", "<", 70]
  - ["ms.bos_this_bar", "==", 1]
```

## Actions syntax

```yaml
actions:
  # Implicit all (bare list = AND)
  entry_long:
    - ["ema_9", ">", "ema_21"]

  # Explicit
  entry_long:
    all:
      - ["ema_9", ">", "ema_21"]
      - ["rsi_14", "<", 70]

  # Cases (first-match, long_short strategies)
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

  # Partial exit + metadata
  emit:
    - action: exit_long
      percent: 50
    - action: entry_long
      metadata:
        entry_atr: {feature_id: "atr_14"}
        entry_reason: "oversold_bounce"
```

## Setups (reusable condition blocks)

```yaml
setups:
  trend_up:
    all:
      - ["close", ">", "ema_50"]
      - ["ema_9", ">", "ema_21"]

  pullback_entry:
    all:
      - setup: trend_up
      - ["rsi_14", "<", 40]

actions:
  entry_long:
    all:
      - setup: pullback_entry
      - ["volume", ">", "vol_sma_20"]
```

**Rules:** parsed before actions, can nest, circular refs detected, cached per bar.

## Arithmetic

Operators: `+`, `-`, `*`, `/`, `%`. Division by zero → None (fails condition).

```yaml
# List format
- lhs: ["ema_9", "-", "ema_21"]
  op: ">"
  rhs: 100

# Dict format in RHS
- ["close", ">", {"-": ["swing.high_level", 10]}]

# Volume spike
- lhs: ["volume", "/", "volume_sma_20"]
  op: ">"
  rhs: 2.0
```

## Window operators

### Bar-based

```yaml
holds_for:                         # ALL N bars must satisfy
  bars: 5
  anchor_tf: "15m"                 # Optional
  expr:
    - ["close", ">", "ema_21"]

occurred_within:                   # At least ONE bar satisfied
  bars: 10
  expr:
    - ["ema_9", "cross_above", "ema_21"]

count_true:                        # At least M of N bars
  bars: 20
  min_true: 15
  expr:
    - ["close", ">", "ema_50"]
```

### Duration-based (recommended for cross-TF)

```yaml
holds_for_duration:
  duration: "30m"
  expr: [["rsi_14", ">", 70]]

occurred_within_duration:
  duration: "4h"
  expr: [["ema_9", "cross_above", "ema_21"]]

count_true_duration:
  duration: "1d"
  min_true: 5
  expr: [["close", ">", "ema_50"]]
```

Duration formats: `"5m"`, `"1h"`, `"1d"`. Max 24h, max 500 bars.

## Offset support

| Feature | offset=0 | offset=1 | offset>1 |
|---------|----------|----------|----------|
| `last_price` | Current 1m | Previous 1m | Not supported |
| `mark_price` | Current | Not supported | — |
| `close` | Current bar | Previous bar | Supported |
| indicators | Current bar | Previous bar | Supported |

## Cross-timeframe access

Features declared on a different TF than `exec`:
- Values forward-fill to exec TF (no lookahead)
- `offset=0` → most recent closed value from the feature's own TF
- `offset=1` → previous closed value from the feature's own TF
- Higher TF values update less frequently (e.g., `high_tf: "D"` updates once per day)

## Missing values

`None`, `NaN`, `Infinity`, feature-not-found, offset-exceeds-history → `false` (not error).
