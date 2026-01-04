# IdeaCard Logic Operators Reference

> **Last Updated**: 2026-01-03
> **Source**: `src/backtest/idea_card.py` (RuleOperator enum)
> **Evaluation**: `src/backtest/execution_validation.py`

This document provides a complete reference for all logic operators available in IdeaCard signal rules.

---

## Table of Contents

1. [Operator Summary](#operator-summary)
2. [Comparison Operators](#comparison-operators)
3. [Crossover Operators](#crossover-operators)
4. [Comparison Modes](#comparison-modes)
5. [YAML Syntax](#yaml-syntax)
6. [Usage Examples](#usage-examples)
7. [Evaluation Logic](#evaluation-logic)

---

## Operator Summary

| Operator | YAML Value | Description | Requires History |
|----------|------------|-------------|------------------|
| Greater Than | `gt` | Current > Compare | No |
| Greater Than or Equal | `gte` | Current >= Compare | No |
| Less Than | `lt` | Current < Compare | No |
| Less Than or Equal | `lte` | Current <= Compare | No |
| Equal | `eq` | Current == Compare (with tolerance) | No |
| Cross Above | `cross_above` | Current > Compare AND Previous <= Previous Compare | Yes |
| Cross Below | `cross_below` | Current < Compare AND Previous >= Previous Compare | Yes |

---

## Comparison Operators

### GT (Greater Than)

**YAML**: `operator: "gt"`

**Logic**: `current_value > compare_value`

**Use Cases**:
- RSI > 50 (bullish momentum)
- Price > EMA (above trend)
- Volume > threshold

```yaml
conditions:
  - feature_id: "rsi_14"
    operator: "gt"
    value: 50.0
```

---

### GTE (Greater Than or Equal)

**YAML**: `operator: "gte"`

**Logic**: `current_value >= compare_value`

**Use Cases**:
- RSI >= 70 (overbought threshold)
- Trend direction >= 1 (uptrend or neutral)

```yaml
conditions:
  - feature_id: "rsi_14"
    operator: "gte"
    value: 70.0
```

---

### LT (Less Than)

**YAML**: `operator: "lt"`

**Logic**: `current_value < compare_value`

**Use Cases**:
- RSI < 30 (oversold)
- Price < lower band (zone touch)
- Volatility < threshold

```yaml
conditions:
  - feature_id: "rsi_14"
    operator: "lt"
    value: 30.0
```

---

### LTE (Less Than or Equal)

**YAML**: `operator: "lte"`

**Logic**: `current_value <= compare_value`

**Use Cases**:
- RSI <= 20 (extreme oversold)
- Trend direction <= -1 (downtrend or neutral)

```yaml
conditions:
  - feature_id: "trend_1h"
    field: "direction"
    operator: "lte"
    value: -1
```

---

### EQ (Equal)

**YAML**: `operator: "eq"`

**Logic**: `abs(current_value - compare_value) < 1e-9`

**Note**: Uses floating-point tolerance (1e-9) for safe comparison.

**Use Cases**:
- Trend direction == 1 (uptrend)
- Zone state == 1 (active)
- Discrete state matching

```yaml
conditions:
  - feature_id: "trend_1h"
    field: "direction"
    operator: "eq"
    value: 1
```

---

## Crossover Operators

### CROSS_ABOVE

**YAML**: `operator: "cross_above"`

**Logic**:
```
current_value > compare_value
AND
previous_value <= previous_compare_value
```

**Behavior**:
1. Gets current bar value of `feature_id`
2. Gets previous bar value of `feature_id` (offset=1)
3. Gets current bar value of `compare_to` (or literal `value`)
4. Gets previous bar value of `compare_to` (or same literal)
5. Returns true if crossing from below/equal to above

**Use Cases**:
- EMA fast crosses above EMA slow (golden cross)
- RSI crosses above 30 (exit oversold)
- Price crosses above resistance level

```yaml
# Feature-to-Feature Crossover (new format)
conditions:
  - feature_id: "ema_fast"
    operator: "cross_above"
    compare_to: "ema_slow"

# Legacy format (still supported)
conditions:
  - tf: "exec"
    indicator_key: "ema_fast"
    operator: "cross_above"
    value: "ema_slow"
    is_indicator_comparison: true
```

---

### CROSS_BELOW

**YAML**: `operator: "cross_below"`

**Logic**:
```
current_value < compare_value
AND
previous_value >= previous_compare_value
```

**Behavior**:
1. Gets current bar value of `feature_id`
2. Gets previous bar value of `feature_id` (offset=1)
3. Gets current bar value of `compare_to` (or literal `value`)
4. Gets previous bar value of `compare_to` (or same literal)
5. Returns true if crossing from above/equal to below

**Use Cases**:
- EMA fast crosses below EMA slow (death cross)
- RSI crosses below 70 (exit overbought)
- Price breaks below support

```yaml
# Feature-to-Feature Crossover (new format)
conditions:
  - feature_id: "ema_fast"
    operator: "cross_below"
    compare_to: "ema_slow"

# Crossing a literal threshold
conditions:
  - feature_id: "rsi_14"
    operator: "cross_below"
    value: 70.0
```

---

## Comparison Modes

### Mode 1: Compare to Literal Value

Compare feature against a fixed number.

```yaml
conditions:
  - feature_id: "rsi_14"
    operator: "gt"
    value: 50.0        # Literal value
```

### Mode 2: Compare to Another Feature

Compare two features against each other.

```yaml
conditions:
  - feature_id: "ema_fast"
    operator: "gt"
    compare_to: "ema_slow"    # Another feature ID
```

### Mode 3: Compare Specific Fields

For multi-output features (structures), specify which field to compare.

```yaml
conditions:
  # Compare swing high_level to a threshold
  - feature_id: "swing_exec"
    field: "high_level"       # Specific output field
    operator: "gt"
    value: 0.0

  # Compare trend direction (integer field)
  - feature_id: "trend_1h"
    field: "direction"
    operator: "eq"
    value: 1

  # Compare two structure fields
  - feature_id: "fib_1h"
    field: "level_0.618"
    operator: "lt"
    compare_to: "swing_exec"
    compare_field: "high_level"
```

---

## YAML Syntax

### New Format (Feature Registry v2.0)

```yaml
signal_rules:
  entry_rules:
    - direction: "long"
      conditions:
        # Simple threshold comparison
        - feature_id: "rsi_1h"
          operator: "gt"
          value: 50.0

        # Feature-to-feature comparison
        - feature_id: "ema_fast"
          operator: "gt"
          compare_to: "ema_slow"

        # Structure field comparison
        - feature_id: "trend_4h"
          field: "direction"
          operator: "eq"
          value: 1

        # Crossover with another feature
        - feature_id: "ema_fast"
          operator: "cross_above"
          compare_to: "ema_slow"

  exit_rules:
    - direction: "long"
      conditions:
        - feature_id: "ema_fast"
          operator: "cross_below"
          compare_to: "ema_slow"
```

### Legacy Format (Still Supported)

```yaml
signal_rules:
  entry_rules:
    - direction: "long"
      conditions:
        - tf: "exec"
          indicator_key: "rsi"
          operator: "gt"
          value: 50.0
          is_indicator_comparison: false

        - tf: "exec"
          indicator_key: "ema_fast"
          operator: "cross_above"
          value: "ema_slow"
          is_indicator_comparison: true
```

---

## Usage Examples

### Example 1: RSI Mean Reversion

Entry when RSI is oversold, exit when it recovers.

```yaml
signal_rules:
  entry_rules:
    - direction: "long"
      conditions:
        - feature_id: "rsi_14"
          operator: "lt"
          value: 30.0

  exit_rules:
    - direction: "long"
      conditions:
        - feature_id: "rsi_14"
          operator: "gt"
          value: 50.0
```

---

### Example 2: EMA Crossover System

Classic dual-EMA trend following.

```yaml
signal_rules:
  entry_rules:
    - direction: "long"
      conditions:
        - feature_id: "ema_fast"
          operator: "cross_above"
          compare_to: "ema_slow"

  exit_rules:
    - direction: "long"
      conditions:
        - feature_id: "ema_fast"
          operator: "cross_below"
          compare_to: "ema_slow"
```

---

### Example 3: Multi-Condition Entry

Trend + momentum + structure confirmation.

```yaml
signal_rules:
  entry_rules:
    - direction: "long"
      conditions:
        # Trend filter: 4h trend is up
        - feature_id: "trend_4h"
          field: "direction"
          operator: "eq"
          value: 1

        # Momentum filter: 1h RSI > 50
        - feature_id: "rsi_1h"
          operator: "gt"
          value: 50.0

        # Trigger: EMA crossover on exec TF
        - feature_id: "ema_fast"
          operator: "cross_above"
          compare_to: "ema_slow"

        # Structure: Valid swing high exists
        - feature_id: "swing_exec"
          field: "high_level"
          operator: "gt"
          value: 0.0
```

---

### Example 4: Zone Touch Pattern

Entry when price touches support zone.

```yaml
signal_rules:
  entry_rules:
    - direction: "long"
      conditions:
        # Price below lower Bollinger Band
        - feature_id: "mark_price"
          operator: "lt"
          compare_to: "bb"
          compare_field: "lower"

        # RSI oversold confirmation
        - feature_id: "rsi_14"
          operator: "lt"
          value: 30.0

  exit_rules:
    - direction: "long"
      conditions:
        # Exit at middle band
        - feature_id: "mark_price"
          operator: "gt"
          compare_to: "bb"
          compare_field: "middle"
```

---

### Example 5: Fibonacci Level Entry

Entry at key Fibonacci retracement level.

```yaml
signal_rules:
  entry_rules:
    - direction: "long"
      conditions:
        # Price near 0.618 fib level
        - feature_id: "mark_price"
          operator: "lte"
          compare_to: "fib"
          compare_field: "level_0.618"

        # Trend confirmation
        - feature_id: "trend_1h"
          field: "direction"
          operator: "eq"
          value: 1
```

---

## Evaluation Logic

### Condition Evaluation Order

1. **All conditions are AND-ed**: Every condition must pass for the rule to trigger
2. **Short-circuit evaluation**: First failing condition stops evaluation
3. **NaN handling**: Any NaN value causes condition to fail (returns false)

### Evaluation Code Flow

```python
# From execution_validation.py

def _evaluate_conditions(conditions, snapshot) -> bool:
    for cond in conditions:
        # Get current value
        current_val = snapshot.get_by_feature_id(
            cond.feature_id,
            offset=0,
            field=cond.field
        )

        # NaN check
        if current_val is None or np.isnan(current_val):
            return False

        # Get comparison value
        if cond.compare_to:
            compare_val = snapshot.get_by_feature_id(
                cond.compare_to,
                offset=0,
                field=cond.compare_field
            )
        else:
            compare_val = float(cond.value)

        # Apply operator
        if cond.operator == RuleOperator.GT:
            if not (current_val > compare_val):
                return False
        elif cond.operator == RuleOperator.EQ:
            if not (abs(current_val - compare_val) < 1e-9):
                return False
        elif cond.operator == RuleOperator.CROSS_ABOVE:
            prev_val = snapshot.get_by_feature_id(cond.feature_id, offset=1)
            prev_compare = ...  # Previous compare value
            if not (current_val > compare_val and prev_val <= prev_compare):
                return False
        # ... etc

    return True  # All conditions passed
```

### Crossover History Access

For `cross_above` and `cross_below`:

| Value | Source | Offset |
|-------|--------|--------|
| `current_val` | `feature_id` at current bar | 0 |
| `prev_val` | `feature_id` at previous bar | 1 |
| `compare_val` | `compare_to` at current bar | 0 |
| `prev_compare` | `compare_to` at previous bar | 1 |

**Note**: If comparing to a literal value, `prev_compare` = `compare_val` (same constant).

---

## Operator Decision Matrix

| Scenario | Recommended Operator |
|----------|---------------------|
| Above/below a threshold | `gt` / `lt` |
| At or beyond a threshold | `gte` / `lte` |
| Exact state match (integer) | `eq` |
| Trend direction check | `eq` with 1, -1, or 0 |
| Moving average crossover | `cross_above` / `cross_below` |
| RSI exit oversold | `cross_above` with value 30 |
| Zone touch entry | `lt` with band comparison |
| Breakout trigger | `cross_above` with resistance level |

---

## Common Patterns

### Pattern: Trend Filter + Momentum Trigger

```yaml
# HTF trend filter (must be true)
- feature_id: "trend_4h"
  field: "direction"
  operator: "eq"
  value: 1

# MTF momentum filter (must be true)
- feature_id: "rsi_1h"
  operator: "gt"
  value: 50.0

# Exec TF trigger (crossover event)
- feature_id: "ema_fast"
  operator: "cross_above"
  compare_to: "ema_slow"
```

### Pattern: Mean Reversion

```yaml
# Entry: Oversold
- feature_id: "rsi_14"
  operator: "lt"
  value: 25.0

# Exit: Recovered
- feature_id: "rsi_14"
  operator: "gt"
  value: 55.0
```

### Pattern: Breakout Confirmation

```yaml
# Price breaks above swing high
- feature_id: "mark_price"
  operator: "gt"
  compare_to: "swing_1h"
  compare_field: "high_level"

# Volume confirmation
- feature_id: "volume_sma"
  operator: "gt"
  value: 1000000
```

---

## Related Documentation

- `docs/architecture/IDEACARD_TRIGGER_AND_STRUCTURE_FLOW.md` - Full data flow
- `docs/architecture/INCREMENTAL_STATE_ARCHITECTURE.md` - Structure detectors
- `src/backtest/idea_card.py` - Condition and RuleOperator definitions
- `src/backtest/execution_validation.py` - Evaluation implementation
