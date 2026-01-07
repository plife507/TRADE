# Timeframe Semantics (1m Action Model)

This document defines the timeframe terminology and evaluation model used in the TRADE backtest engine.

---

## Core Concepts

### The 1m Action Model

The backtest engine uses a **1m action model** where:

1. **Signals are evaluated every 1m** - regardless of the declared `execution_tf`
2. **TP/SL is checked every 1m** - for accurate price-based exits
3. **Indicators update at their declared TF** - and forward-fill between closes

This matches live trading semantics where the bot evaluates every tick/1m bar.

---

## Timeframe Roles

| Role | Definition | Configurable | Example |
|------|------------|--------------|---------|
| **action_tf** | Where signals are evaluated and TP/SL checked | No (always 1m) | `1m` |
| **eval_tf** | Bar-stepping granularity from Play YAML | Yes (`execution_tf`) | `15m`, `1h` |
| **condition_tf** | Where indicators/structures compute | Yes (per feature) | `1h`, `4h` |
| **LTF** | Low Timeframe role | Yes (`tf_mapping`) | `15m` |
| **MTF** | Mid Timeframe role | Yes (`tf_mapping`) | `1h` |
| **HTF** | High Timeframe role | Yes (`tf_mapping`) | `4h` |

### Relationship Between Roles

```
action_tf (1m) ─────► Where we evaluate signals and check TP/SL
                      (fixed, not configurable)

eval_tf ────────────► Bar-stepping granularity
                      (from Play.execution_tf)

condition_tf ───────► Where indicators compute and forward-fill from
                      (from each feature's tf declaration)

LTF/MTF/HTF ────────► Relative roles for tf_mapping
                      (used for multi-TF indicator access)
```

---

## Evaluation Flow

### Current Implementation

```
for exec_idx in range(num_bars):  # eval_tf bars (e.g., 15m)
    bar = exec_feed[exec_idx]

    # Get 1m range for this eval_tf bar
    start_1m, end_1m = get_1m_range(exec_idx)

    # MANDATORY 1m action loop
    for action_idx in range(start_1m, end_1m + 1):
        # Build snapshot with 1m context
        snapshot = build_snapshot(
            eval_idx=exec_idx,
            action_idx=action_idx,
            last_price=1m_feed.close[action_idx],
        )

        # Evaluate actions at 1m granularity
        signal = evaluate(snapshot)

        # Check TP/SL at 1m granularity
        check_tp_sl(position, 1m_bar)
```

### Why 1m Evaluation Matters

1. **Accurate TP/SL**: Price may cross SL/TP multiple times within a 15m bar
2. **Live parity**: Live trading evaluates every tick/1m
3. **Signal timing**: Entry signals fire at the exact 1m bar price crosses indicator
4. **No missed exits**: Ensures we catch exits even when price spikes then reverses

---

## Forward-Fill Semantics

### How Forward-Fill Works

Any indicator/structure declared at a slower TF than action_tf (1m) **forward-fills** until its next bar closes:

```
exec bars (15m):  |  1  |  2  |  3  |  4  |  5  |  6  |  7  |  8  |
                  ├─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤
HTF bars (1h):    |          HTF bar 0          |     HTF bar 1    ...
                  │                             │
                  └─── HTF values unchanged ────┘
                       (forward-filled)

1m bars:          | 1m₀ | 1m₁ | 1m₂ | ... | 1m₁₄| 1m₁₅| 1m₁₆| ...
                  │                             │
                  └─── All see same HTF value ──┘
```

### What Forward-Fill Means for Trading

| Scenario | Behavior |
|----------|----------|
| `last_price gt ema_50_1h` | 1m price compared to forward-filled 1h EMA |
| `cross_above` with HTF indicator | Fires when 1m price crosses the static HTF value |
| `holds_for_duration: "30m"` | Checks 30 1m bars; HTF indicator may be same for all |
| Structure access (`swing.high_level`) | Forward-filled from last HTF close |

### No Lookahead Guarantee

Forward-fill ensures **no lookahead bias**:
- Values reflect the **last CLOSED bar**, never partial/forming bars
- HTF indicator doesn't change until HTF bar closes
- This matches TradingView `lookahead_off` semantics

---

## Price Variables

| Variable | Meaning | Source at action_tf |
|----------|---------|---------------------|
| `last_price` | Current ticker price | 1m bar close |
| `mark_price` | Fair price for PnL | From PriceModel (usually = last_price in backtest) |
| `close` | Bar close at declared TF | eval_tf bar close |
| `close_1h` | Explicit TF close | 1h bar close (forward-filled) |

### DSL Usage

```yaml
# 1m ticker price (action price)
lhs: {feature_id: "last_price"}

# eval_tf bar close (unchanged from before)
lhs: {feature_id: "close"}

# Explicit TF close
lhs: {feature_id: "close_1h"}
```

---

## Window Operators and Timeframes

Window operators now support two modes: **duration-based** and **bar-based with anchor_tf**.

### The Cross-TF Problem (Why This Matters)

Without timeframe anchoring, bar-based windows shift features at different TFs:

```
holds_for: 5 bars (without anchor_tf)
Offset | last_price (1m) | rsi_14_1h (1h) | Comparison
-------|-----------------|----------------|------------
0      | NOW             | NOW            | ✅ Sensible
1      | 1m ago          | 1h ago         | ❌ Broken
2      | 2m ago          | 2h ago         | ❌ Broken
```

Duration-based and anchor_tf windows fix this by sampling ALL features at the same rate.

### Duration-Based Windows (Recommended for Cross-TF)

Explicit time duration - always converted to 1m bars:

```yaml
# holds_for_duration: Expression must be true for entire duration
- when:
    holds_for_duration:
      duration: "30m"
      expr:
        lhs: {feature_id: "rsi_14_1h"}  # Forward-filled
        op: gt
        rhs: 70

# occurred_within_duration: Expression was true at least once
- when:
    occurred_within_duration:
      duration: "15m"
      expr:
        lhs: {feature_id: "ema_9"}
        op: cross_above
        rhs: {feature_id: "ema_21"}

# count_true_duration: Expression true at least N times
- when:
    count_true_duration:
      duration: "1h"
      min_true: 30  # True for at least 30 of 60 1m bars
      expr:
        lhs: {feature_id: "rsi_14"}
        op: gt
        rhs: 70
```

**Supported duration formats**: `"5m"`, `"30m"`, `"1h"`, `"4h"`, etc.

**Maximum duration**: 24 hours (1440 minutes)

### Bar-Based Windows with anchor_tf

For bar-counting at a specific TF rate:

```yaml
# anchor_tf specifies the sampling rate
holds_for:
  bars: 30
  anchor_tf: "1m"  # Sample at 1m rate
  expr:
    lhs: {feature_id: "rsi_14_1h"}
    op: gt
    rhs: 70

# Without anchor_tf, defaults to action_tf (1m)
holds_for:
  bars: 5
  expr:  # Sampled at 1m by default
    lhs: {feature_id: "last_price"}
    op: gt
    rhs: {feature_id: "ema_50_1h"}
```

### Evaluation Semantics

| Operator | Duration-Based | Bars | Behavior |
|----------|---------------|------|----------|
| holds_for | `holds_for_duration` | `holds_for` | True for ALL bars in window |
| occurred_within | `occurred_within_duration` | `occurred_within` | True for ANY bar in window |
| count_true | `count_true_duration` | `count_true` | True for >= min_true bars |

### Forward-Fill Within Windows

Features slower than the anchor rate forward-fill their last closed value:

```
Window: holds_for_duration: "30m" (30 × 1m bars)
Feature: rsi_14_1h (updates every 1h)

Bar | 1m close | rsi_14_1h | Comparison
----|----------|-----------|------------
0   | 50100    | 72.5      | 72.5 > 70 ✓
1   | 50050    | 72.5      | 72.5 > 70 ✓ (same value)
... | ...      | 72.5      | Forward-fills until 1h close
29  | 50200    | 72.5      | 72.5 > 70 ✓
```

---

## Play Configuration

### execution_tf vs action_tf

| YAML Field | Meaning | Default |
|------------|---------|---------|
| `execution_tf` | Bar-stepping granularity (eval_tf) | Required |
| (implicit) | Signal evaluation (action_tf) | Always 1m |

```yaml
# Example Play
id: my_strategy
execution_tf: "1h"  # Bar-stepping is hourly

features:
  - id: "ema_50_1h"
    tf: "1h"  # Indicator computed at 1h, forward-fills within
    ...

# Actions are evaluated every 1m within each 1h bar
# last_price is the 1m close; ema_50_1h forward-fills
```

### Multi-Timeframe Features

```yaml
features:
  - id: "ema_21"
    tf: "15m"  # LTF - updates every 15m
  - id: "ema_50_1h"
    tf: "1h"   # MTF - updates every 1h, forward-fills between
  - id: "ema_200_4h"
    tf: "4h"   # HTF - updates every 4h, forward-fills between
```

---

## Constants

Defined in `src/backtest/runtime/timeframe.py`:

```python
ACTION_TF = "1m"              # Fixed action timeframe
ACTION_TF_MINUTES = 1         # Duration in minutes
WINDOW_DURATION_CEILING_MINUTES = 1440  # 24 hours max window
```

---

## Related Files

| File | Purpose |
|------|---------|
| `src/backtest/runtime/timeframe.py` | Constants and TF utilities |
| `src/backtest/engine.py` | 1m action loop implementation |
| `src/backtest/runtime/snapshot_view.py` | `last_price` property |
| `src/backtest/rules/dsl_eval.py` | Window operator evaluation |
| `docs/architecture/PRICE_SEMANTICS.md` | Price variable definitions |
| `docs/architecture/WINDOW_OPERATORS.md` | Window operator semantics |
