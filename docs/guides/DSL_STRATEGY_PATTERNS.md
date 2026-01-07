# DSL Strategy Patterns

Strategy patterns enabled by the TRADE DSL window operators, crossover operators, and multi-timeframe features.

---

## 1. Momentum Confirmation (holds_for_duration)

Wait for momentum to persist before entering - filters out fake breakouts:

```yaml
# Only enter if RSI stays overbought for 15 minutes
actions:
  - id: entry
    cases:
      - when:
          holds_for_duration:
            duration: "15m"
            expr:
              lhs: {feature_id: "rsi_14"}
              op: gt
              rhs: 70
        emit:
          - action: entry_long
```

**Use case**: Trend following - ensures momentum is sustained, not just a spike.

---

## 2. Dip Buying / Mean Reversion (occurred_within_duration)

Enter when price recently touched a level but has now bounced:

```yaml
# Buy if price touched lower Bollinger Band in last 30 min AND now recovering
actions:
  - id: entry
    cases:
      - when:
          all:
            - occurred_within_duration:
                duration: "30m"
                expr:
                  lhs: {feature_id: "close"}
                  op: lt
                  rhs: {feature_id: "bbands_20_2_lower"}
            - lhs: {feature_id: "close"}
              op: gt
              rhs: {feature_id: "ema_9"}
        emit:
          - action: entry_long
```

**Use case**: Mean reversion - catch the bounce after oversold conditions.

---

## 3. Multi-Timeframe Confirmation (anchor_tf)

Require conditions on higher timeframe bars:

```yaml
# Enter only if 1h trend is bullish for 3 consecutive 1h bars
actions:
  - id: entry
    cases:
      - when:
          all:
            - holds_for:
                bars: 3
                anchor_tf: "1h"
                expr:
                  lhs: {feature_id: "ema_20_1h"}
                  op: gt
                  rhs: {feature_id: "ema_50_1h"}
            - lhs: {feature_id: "rsi_14"}
              op: cross_above
              rhs: 50
        emit:
          - action: entry_long
```

**Use case**: HTF trend + LTF trigger - only trade in direction of higher timeframe trend.

---

## 4. Breakout with Volume Confirmation (count_true_duration)

Require volume spikes to confirm breakout validity:

```yaml
# Breakout valid if volume exceeded average 3+ times in last hour
actions:
  - id: entry
    cases:
      - when:
          all:
            - lhs: {feature_id: "close"}
              op: cross_above
              rhs: {feature_id: "resistance_level"}
            - count_true_duration:
                duration: "1h"
                min_true: 3
                expr:
                  lhs: {feature_id: "volume"}
                  op: gt
                  rhs: {feature_id: "volume_sma_20"}
        emit:
          - action: entry_long
```

**Use case**: Breakout trading - filters low-volume false breakouts.

---

## 5. Price Action Crossovers (last_price + cross_above/below)

React to real-time 1m price crossing indicator levels:

```yaml
# Enter when 1m price crosses above VWAP
actions:
  - id: entry
    cases:
      - when:
          lhs: {feature_id: "last_price"}
          op: cross_above
          rhs: {feature_id: "vwap"}
        emit:
          - action: entry_long
```

**Use case**: Intraday scalping - precise entries at key levels using 1m price action.

---

## 6. Cooldown / Anti-Chop Filter (occurred_within)

Prevent re-entry too soon after a signal:

```yaml
# Don't enter if we already had an RSI extreme in last 5 bars
actions:
  - id: entry
    cases:
      - when:
          all:
            - lhs: {feature_id: "rsi_14"}
              op: lt
              rhs: 30
            - not:
                occurred_within:
                  bars: 5
                  expr:
                    lhs: {feature_id: "rsi_14"}
                    op: lt
                    rhs: 30
        emit:
          - action: entry_long
```

**Use case**: Choppy market filter - avoid repeated signals in consolidation.

---

## 7. Exhaustion Detection (count_true + trend)

Detect when a trend is exhausting:

```yaml
# Exit if bearish candles dominated last 10 bars (7+ red)
actions:
  - id: exit
    cases:
      - when:
          count_true:
            bars: 10
            min_true: 7
            expr:
              lhs: {feature_id: "close"}
              op: lt
              rhs: {feature_id: "open"}
        emit:
          - action: exit_long
```

**Use case**: Trend exhaustion exit - get out before reversal completes.

---

## Strategy Complexity Matrix

| Feature | Simple Strategies | Advanced Strategies |
|---------|-------------------|---------------------|
| `cross_above/below` | EMA crossover entries | Multi-indicator confluence |
| `holds_for_duration` | Momentum confirmation | Regime persistence filters |
| `occurred_within` | Recent touch detection | Support/resistance bounce |
| `count_true` | Volume spike counting | Candle pattern frequency |
| `anchor_tf` | HTF trend filter | Multi-TF alignment scoring |
| `last_price` | Real-time level cross | Scalping micro-entries |

---

## Duration vs Bar-Based Operators

### Duration-Based (time-relative)
- `holds_for_duration`, `occurred_within_duration`, `count_true_duration`
- Express conditions in wall-clock time: "30m", "1h", "4h"
- Always evaluated at 1m granularity
- Use when you care about **time elapsed**

### Bar-Based (TF-relative)
- `holds_for`, `occurred_within`, `count_true`
- Express conditions in bar counts with optional `anchor_tf`
- Use when you care about **N bars at specific timeframe**

```yaml
# These are equivalent for 15m anchor_tf:
holds_for_duration:
  duration: "45m"      # 45 minutes = 45 checks at 1m

holds_for:
  bars: 3
  anchor_tf: "15m"     # 3 bars at 15m = 45 minutes, but only 3 checks
```

The bar-based version with `anchor_tf` is more efficient (fewer evaluations) when you want TF-aligned checks.

---

## Combining Patterns

Complex strategies combine multiple patterns:

```yaml
# HTF trend + momentum persistence + volume confirmation + precise entry
actions:
  - id: entry
    cases:
      - when:
          all:
            # HTF trend filter (1h)
            - holds_for:
                bars: 3
                anchor_tf: "1h"
                expr:
                  lhs: {feature_id: "ema_20_1h"}
                  op: gt
                  rhs: {feature_id: "ema_50_1h"}
            # Momentum persistence (15m)
            - holds_for_duration:
                duration: "15m"
                expr:
                  lhs: {feature_id: "rsi_14"}
                  op: gt
                  rhs: 50
            # Volume confirmation
            - count_true_duration:
                duration: "30m"
                min_true: 2
                expr:
                  lhs: {feature_id: "volume"}
                  op: gt
                  rhs: {feature_id: "volume_sma_20"}
            # Precise entry trigger
            - lhs: {feature_id: "last_price"}
              op: cross_above
              rhs: {feature_id: "vwap"}
        emit:
          - action: entry_long
```

This combines:
1. Higher timeframe trend alignment
2. Momentum persistence filter
3. Volume confirmation
4. Precise 1m entry trigger
