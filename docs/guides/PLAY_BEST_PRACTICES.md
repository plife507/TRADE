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

#### Finding #10: Float Equality and INT Coercion (2026-01-08)

**Source**: Multiple indicator functional tests, T3_03_supertrend systematic test

**Issue**: The DSL's `eq` operator rejects float equality comparisons to prevent floating-point precision bugs. However, pandas/numpy stores ALL indicator values as float64, including fields declared as INT (like `supertrend.direction`).

**Error**: `FLOAT_EQUALITY: Float equality not allowed with 'eq'. Use 'approx_eq' with tolerance`

**Fix Applied (2026-01-08)**: INT-declared fields now automatically coerce integer-like floats (1.0, -1.0) to INT during DSL evaluation. This uses the registry's declared type information.

**Current behavior by type**:

| Registry Type | Runtime Storage | `eq` Works? | Example |
|---------------|-----------------|-------------|---------|
| INT | float64 (1.0, -1.0) | ✅ Yes (auto-coerced) | `[direction, "eq", 1]` |
| FLOAT | float64 | ❌ No (use alternatives) | `[rsi, "cross_above", 30]` |
| BOOL | bool | ✅ Yes | `[is_valid, "eq", true]` |
| ENUM | string | ✅ Yes | `[state, "eq", "ACTIVE"]` |

**For continuous FLOAT fields**, use these alternatives:

| Use Case | Operator | Example |
|----------|----------|---------|
| Crossing a level | `cross_above`/`cross_below` | `[rsi, "cross_above", 30]` |
| Above/below threshold | `gt`/`lt` | `[rsi, "gt", 70]` |
| Near a value | `near_pct`/`near_abs` | `[price, "near_pct", level, 0.1]` |

---

#### Finding #11: Donchian Breakout Conditions (2026-01-07)

**Source**: F_IND_031_donchian functional test

**Issue**: `close > upper` rarely triggers during consolidation because new 20-bar highs are infrequent.

**Better patterns**:
```yaml
# Trend following: cross above middle
- ["close", "cross_above", {"feature_id": "donchian_20", "field": "middle"}]

# Breakout: cross above upper (more signals)
- ["close", "cross_above", {"feature_id": "donchian_20", "field": "upper"}]

# Channel position
- [{"feature_id": "donchian_20", "field": "percent_b"}, "gt", 0.8]  # Near upper
```

### Multi-Output Indicators

#### Finding #6: TRIX and PPO are Multi-Output (2026-01-07)

**Source**: Functional test suite F_IND_006_trix, F_IND_008_ppo

**Issue**: TRIX and PPO indicators return multiple outputs but were incorrectly marked as single-output.

**Correct declaration**:
```yaml
features:
  trix_18:
    indicator: trix
    params:
      length: 18
      signal: 9  # Optional signal line period

# Access fields:
actions:
  entry_long:
    all:
      - [{"feature_id": "trix_18", "field": "trix"}, "cross_above", 0]

# Available fields:
# - trix: Main TRIX value
# - signal: Signal line (EMA of TRIX)
```

**PPO outputs**: `ppo`, `histogram`, `signal`

---

#### Finding #7: Squeeze Fields are INT, Not BOOL (2026-01-07)

**Source**: F_IND_019_squeeze functional test

**Issue**: Squeeze indicator's `on`, `off`, `no_sqz` fields output integers (0/1), not Python booleans.

**Wrong** (DSL rejects `gt` for BOOL):
```yaml
# This fails if registry types them as BOOL
- [{"feature_id": "squeeze_20", "field": "off"}, "eq", true]
```

**Correct**:
```yaml
# Registry types them as INT - use numeric comparison
- [{"feature_id": "squeeze_20", "field": "off"}, "gt", 0]
```

**Rule**: Check `FEATURE_OUTPUT_TYPES` in `indicator_registry.py` for the actual output types.

---

#### Finding #8: PSAR Reversal is INT, Not BOOL (2026-01-07)

**Source**: F_IND_018_psar functional test

**Issue**: PSAR's `reversal` field outputs 0 or 1 as integers, but stored as float64 in FeedStore.

**Wrong**:
```yaml
# Fails: float64 equality comparison rejected
- [{"feature_id": "psar_0.02", "field": "reversal"}, "eq", 1]
```

**Correct**:
```yaml
# Use gt for integer-like comparisons
- [{"feature_id": "psar_0.02", "field": "reversal"}, "gt", 0]
```

---

#### Finding #9: VWAP Requires Timestamps (2026-01-07)

**Source**: F_IND_032_vwap functional test

**Issue**: pandas_ta's VWAP requires DatetimeIndex for session boundary detection.

**Solution**: The engine automatically passes `ts_open` timestamps to VWAP computation. No special handling required in Plays.

**Use case**: VWAP works with the `anchor` parameter for session resets:
- `anchor: "D"` - Daily VWAP reset
- `anchor: "W"` - Weekly VWAP reset

```yaml
features:
  vwap_daily:
    indicator: vwap
    params:
      anchor: "D"  # Reset at midnight UTC
```

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

---

## Indicator Output Types Quick Reference

**Important**: All values stored as float64 in FeedStore. Use appropriate operators.

| Indicator | Field | Registry Type | Recommended Operator |
|-----------|-------|---------------|---------------------|
| psar | reversal | INT | `eq 1` (fires on reversal) or `gt 0` |
| squeeze | on, off, no_sqz | INT | `eq 1` or `gt 0` |
| supertrend | direction | INT | `eq 1` (long) / `eq -1` (short) |
| aroon | up, down, osc | FLOAT | `cross_above`/`cross_below` |
| macd | histogram | FLOAT | `cross_above 0` |
| bbands | percent_b | FLOAT | `gt 1.0` (above upper) |
| trix | trix | FLOAT | `cross_above 0` |
| ppo | histogram | FLOAT | `cross_above 0` |

**Note**: INT-declared fields now support `eq` operator (fixed 2026-01-08). Both `eq 1` and `gt 0` work for boolean-like integers.

---

## Validation Checklist

Before deploying a Play, verify:

- [ ] Entry operator matches strategy intent (level vs transition)
- [ ] Exit mechanism is consistent with entry operator
- [ ] TP/SL only used with transition-based entries (or re-entry is intended)
- [ ] Feature IDs follow parameterized naming (`ema_21` not `ema_slow`)
- [ ] All referenced features are declared in `features:` section
- [ ] Multi-output indicators use field accessor: `{"feature_id": "...", "field": "..."}`
- [ ] FLOAT fields use appropriate operators (`gt`, `cross_above`, not `eq`)
- [ ] Run `normalize` to validate against engine

---

## Contributing

When adding new findings:

1. Add dated entry under "Findings Log" with source reference
2. Categorize under appropriate section
3. Include concrete YAML examples
4. State the rule clearly
5. Update Quick Reference tables if applicable
