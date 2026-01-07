# Play Creation Best Practices

## Purpose

This document captures best practices, gotchas, and guardrails for creating Plays. Discovered through systematic validation of the backtest engine.

---

## Findings Log

### Finding #1: Match Operator to Strategy Intent (2026-01-07)

**Source**: I_001_ema validation

**Issue**: Using level operators (`gt`, `lt`) for entry signals with TP/SL creates re-entry chains.

**Example (problematic combination)**:
```yaml
actions:
  - id: entry
    cases:
      - when:
          lhs: { feature_id: "close" }
          op: gt                        # Level operator - fires every bar
          rhs: { feature_id: "ema_21" }
        emit:
          - action: entry_long

risk_model:
  take_profit:
    type: "percent"
    value: 4.0  # TP exits, but gt still true -> immediate re-entry
```

**Behavior**: After TP exit at +4%, if `close > ema_21` still true, engine re-enters on next bar.

**Guidance**:

| Strategy Intent | Entry Operator | TP/SL | Re-entry Behavior |
|-----------------|----------------|-------|-------------------|
| "Enter on event, manage with TP/SL" | `cross_above` | Yes | Waits for new crossover |
| "Always long while condition holds" | `gt` | Usually No | Re-enters if exited |
| "Enter on event, exit on opposite event" | `cross_above` | No | Clean entry/exit pairs |

**Rule**: Don't mix level-based entries (`gt`, `lt`) with TP/SL unless you explicitly want re-entry behavior.

---

### Finding #2: Crossover Timing (2026-01-07)

**Source**: I_010_ema_cross validation

**Observation**: Entry timestamps are 1 bar after signal detection.

**Why**:
- Signal detected at bar N close (e.g., 21:00)
- Order fills at bar N+1 open (e.g., 22:00)
- Entry time in trades = fill time

**This is correct** - matches TradingView backtesting semantics.

---

### Finding #3: Level Operators Cause Re-entry Chains (2026-01-07)

**Source**: I_001_ema, I_002_sma, I_003_rsi, I_004_atr validation

**Issue**: Using level operators (`gt`, `lt`) for entry signals with TP/SL causes immediate re-entry when exit happens but condition is still true.

**Data**:

| Play | Entry Condition | Exit Reasons | Immediate Re-entries |
|------|-----------------|--------------|---------------------|
| I_001_ema | `close > ema_21` | 17 signal, 3 TP, 1 SL | 2 (after TP) |
| I_002_sma | `close > sma_21` | 23 signal, 2 TP | 2 (after TP) |
| I_003_rsi | `rsi < 30` | 7 SL, 1 TP | **6 (after SL!)** |
| I_004_atr | `atr > 35` | 6 SL, 2 TP, 1 signal | **5 (after SL)** |

**Pattern**: Oscillators (RSI) and volatility indicators (ATR) have the worst re-entry problem because they stay in "trigger zone" during strong trends.

**Guidance**:
- Level operators for entries = "maintain position while condition holds"
- Expect re-entry after any TP/SL exit if condition still true
- For "enter once, manage with TP/SL" use transition operators (`cross_above`)

---

### Finding #4: Oscillators as Validators, Not Signals (2026-01-07)

**Source**: I_003_rsi validation showing 6 consecutive SL hits during downtrend

**Issue**: RSI < 30 (oversold) staying true during strong downtrends causes repeated "catching falling knives."

**Example from I_003_rsi**:
```
Trade 0: RSI=25.7 → SL hit
Trade 1: RSI=16.3 → immediate re-entry → SL hit
Trade 2: RSI=12.2 → immediate re-entry → SL hit
Trade 3: RSI=21.4 → immediate re-entry → SL hit
```

RSI went DOWN (more oversold) but strategy kept buying and getting stopped out.

**Wrong pattern**:
```yaml
- when:
    lhs: { feature_id: "rsi_14" }
    op: lt
    rhs: 30
  emit: [entry_long]   # RSI < 30 alone = catching falling knives
```

**Correct pattern** - RSI as validator with price-based signal:
```yaml
- when:
    all:
      - lhs: { feature_id: "rsi_14" }
        op: lt
        rhs: 30                         # Validator: market is oversold
      - lhs: { feature_id: "close" }
        op: cross_above
        rhs: { feature_id: "ema_9" }    # Primary signal: price reversal
  emit: [entry_long]
```

**Rule**: Oscillators (RSI, Stochastic, CCI) and volatility indicators (ATR) should be VALIDATORS combined with price-action signals, not standalone entry triggers.

---

### Finding #5: ATR Use Cases (2026-01-07)

**Source**: I_004_atr validation

**Math verified**: ATR uses Wilder's RMA smoothing (alpha=1/length) with SMA seed. Matches pandas-ta within floating point precision.

**Problem with ATR as entry signal**: During high volatility periods (ATR > threshold), strategy re-enters after each SL, often into the worst market conditions.

**Correct ATR use cases**:
1. **Filter**: `trend_signal AND atr > min_volatility`
2. **Position sizing**: ATR-based stop loss distance (e.g., `sl = 2 * ATR`)
3. **Regime detection**: Choose strategy based on volatility level

---

## Categories

### Entry Logic

- (findings will be added here)

### Exit Logic

- (findings will be added here)

### Operator Usage

- (findings will be added here)

### Multi-Output Indicators

- (findings will be added here)

### Risk Model Interactions

- (findings will be added here)

---

## Quick Reference: Operator Types

| Operator | Type | Fires When |
|----------|------|------------|
| `gt`, `lt`, `gte`, `lte` | Level | Every bar condition is true |
| `cross_above`, `cross_below` | Transition | Once, when condition changes |
| `between` | Level | Every bar value in range |
| `eq`, `ne` | Level | Every bar values match/differ |

---

## Indicator Classification

| Category | Indicators | Use As | Entry Pattern |
|----------|------------|--------|---------------|
| **Trend** | EMA, SMA | Signal or Filter | `cross_above`/`cross_below` |
| **Oscillator** | RSI, Stochastic, CCI | Validator only | Combine with price signal |
| **Volatility** | ATR, BBands width | Filter or Sizing | Not for entry timing |
| **Momentum** | MACD histogram | Signal | `cross_above` zero line |

---

## Quick Reference: Common Patterns

### Pattern A: Event-Driven Entry with TP/SL

Use transition operators for entries when using TP/SL exits.

```yaml
actions:
  - id: entry
    cases:
      - when:
          lhs: { feature_id: "ema_9" }
          op: cross_above              # Transition - fires once
          rhs: { feature_id: "ema_21" }
        emit:
          - action: entry_long

risk_model:
  take_profit:
    type: "percent"
    value: 3.0
  stop_loss:
    type: "percent"
    value: 1.5
```

### Pattern B: Level-Based Position Management

Use level operators when you want to maintain position while condition holds.

```yaml
actions:
  - id: entry
    cases:
      - when:
          lhs: { feature_id: "close" }
          op: gt                       # Level - position while true
          rhs: { feature_id: "ema_200" }
        emit:
          - action: entry_long
  - id: exit
    cases:
      - when:
          lhs: { feature_id: "close" }
          op: lt                       # Exit when condition breaks
          rhs: { feature_id: "ema_200" }
        emit:
          - action: exit_long

# No TP/SL - exits controlled by opposite condition
```

### Pattern C: Crossover Entry/Exit Pairs

Use matching crossover operators for clean entry/exit logic.

```yaml
actions:
  - id: entry
    cases:
      - when:
          lhs: { feature_id: "ema_9" }
          op: cross_above
          rhs: { feature_id: "ema_21" }
        emit:
          - action: entry_long
  - id: exit
    cases:
      - when:
          lhs: { feature_id: "ema_9" }
          op: cross_below
          rhs: { feature_id: "ema_21" }
        emit:
          - action: exit_long
```

---

## Anti-Patterns

### Anti-Pattern #1: Level Entry + TP/SL (Unintended Re-entry)

**Don't do this** unless you want re-entry chains:

```yaml
# BAD: Will re-enter immediately after TP
actions:
  - id: entry
    cases:
      - when:
          lhs: { feature_id: "rsi_14" }
          op: lt
          rhs: { literal: 30 }
        emit:
          - action: entry_long

risk_model:
  take_profit:
    type: "percent"
    value: 2.0
```

**Fix**: Use a transition operator or remove TP/SL.

---

## Validation Checklist

Before deploying a Play, verify:

- [ ] Entry operator matches strategy intent (level vs transition)
- [ ] Exit mechanism is consistent with entry operator
- [ ] TP/SL only used with transition-based entries (or re-entry is intended)
- [ ] Feature IDs follow parameterized naming (`ema_21` not `ema_slow`)
- [ ] All referenced features are declared in `features:` section
- [ ] Run `normalize` to validate against engine

---

## Contributing

When adding new findings:

1. Add dated entry under "Findings Log" with source reference
2. Categorize under appropriate section
3. Include concrete YAML examples
4. State the rule clearly
5. Update Quick Reference tables if applicable
