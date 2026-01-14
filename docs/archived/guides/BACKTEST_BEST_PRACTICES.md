# Backtest Engine Best Practices

> Based on comprehensive audit of TRADE engine vs Bybit documentation (2026-01-07)

## Overview

This guide documents best practices for using the TRADE backtest engine. All margin calculations, order execution, and PnL logic have been verified against Bybit V5 API documentation.

---

## 1. Position Sizing

### Use Bybit-Aligned Margin Formula

The engine implements Bybit's margin model:

```
Position Value = Margin × Leverage
Initial Margin = Position Value × IMR
IMR = 1 / Leverage
```

**Example Configuration:**
```yaml
account:
  starting_equity_usdt: 10000.0
  max_leverage: 10.0  # IMR = 10%, max position = 100,000 USDT

risk:
  max_position_pct: 10.0  # Use 10% of equity as margin
  # At 10x leverage: 1000 × 10 = 10,000 USDT position
```

### Sizing Models

| Model | Use Case | Formula |
|-------|----------|---------|
| `percent_equity` | Standard sizing | `position = equity × (pct/100) × leverage` |
| `risk_based` | Stop-based sizing | `position = risk$ × entry / stop_distance` |
| `fixed_usdt` | Fixed notional | `position = fixed_amount` (capped by leverage) |

**Best Practice:** Use `percent_equity` for simple strategies, `risk_based` for precise risk management.

---

## 2. Leverage Settings

### For Validation Tests

Use **1x leverage** to simplify margin calculations:

```yaml
account:
  max_leverage: 1.0  # No leverage - margin = position size
  starting_equity_usdt: 10000.0

risk:
  max_position_pct: 10.0  # 10% × 1x = 1000 USDT position
```

### For Production Strategies

Use realistic leverage with fee buffer:

```yaml
account:
  max_leverage: 10.0
  starting_equity_usdt: 10000.0

risk:
  max_position_pct: 9.5  # Leave 0.5% for fees at max leverage
```

**Why 9.5%?** At 10x leverage with 10% margin:
- Position: 10,000 USDT
- Margin required: 1,000 USDT
- Fees (0.06% × 2): ~12 USDT
- Total: 1,012 USDT > 1,000 available

---

## 3. Stop Loss and Take Profit

### Supported SL/TP Types

| Type | YAML Key | Description |
|------|----------|-------------|
| Percent | `stop_loss_pct` | % distance from entry |
| ATR Multiple | `stop_loss_atr` | ATR × multiplier |
| Fixed Points | `stop_loss_points` | Absolute price distance |
| Structure | (advanced) | Based on swing levels |

### Best Practice Configuration

```yaml
risk:
  stop_loss_pct: 2.0   # 2% stop loss
  take_profit_pct: 4.0  # 4% take profit (2:1 R:R)
```

### Using ATR-Based Stops

```yaml
features:
  atr_14:
    indicator: atr
    params:
      length: 14

risk_model:
  stop_loss:
    type: atr_multiple
    value: 2.0  # 2 × ATR
    atr_feature_id: atr_14
  take_profit:
    type: rr_ratio
    value: 2.0  # 2:1 reward:risk
```

---

## 4. DSL Operators

### Comparison Operators

| Operator | Alias | Description |
|----------|-------|-------------|
| `gt` | `>` | Greater than |
| `lt` | `<` | Less than |
| `gte` | `>=`, `ge` | Greater than or equal |
| `lte` | `<=`, `le` | Less than or equal |
| `eq` | `==` | Equal (discrete types only) |

**⚠️ Type Safety:** `eq` operator rejects floats. Use `near_abs` or `near_pct` for float comparison.

```yaml
# WRONG - will fail at runtime
- lhs: {feature_id: "rsi_14"}
  op: eq
  rhs: 50.0  # Float comparison not allowed

# CORRECT - use near_pct for float tolerance
- lhs: {feature_id: "rsi_14"}
  op: near_pct
  rhs: 50.0
  tolerance: 0.01  # Within 1%
```

### Crossover Operators

TradingView-aligned semantics:

| Operator | Condition |
|----------|-----------|
| `cross_above` | `prev <= rhs AND curr > rhs` |
| `cross_below` | `prev >= rhs AND curr < rhs` |

```yaml
actions:
  entry_long:
    all:
      - ["ema_9", "cross_above", "ema_21"]
```

### Window Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `holds_for` | True for N consecutive bars | Trend confirmation |
| `occurred_within` | True at least once in N bars | Recent signal |
| `count_true` | True M+ times in N bars | Frequency filter |

```yaml
# EMA cross must hold for 3 bars
holds_for:
  bars: 3
  expr:
    - ["ema_9", ">", "ema_21"]

# RSI crossed below 30 within last 10 bars
occurred_within:
  bars: 10
  expr:
    - ["rsi_14", "cross_below", 30]
```

---

## 5. Feature Naming Convention

### Parameterized Names (Required)

Always encode parameters in feature IDs:

```yaml
# CORRECT - parameters visible
features:
  ema_9:
    indicator: ema
    params: {length: 9}
  ema_21:
    indicator: ema
    params: {length: 21}
  rsi_14:
    indicator: rsi
    params: {length: 14}

# WRONG - semantic names hide parameters
features:
  ema_fast:   # What length?
  ema_slow:   # What length?
  rsi:        # What length?
```

### Multi-Output Indicators

Use underscore convention for multi-output:

```yaml
features:
  macd_12_26_9:
    indicator: macd
    params:
      fast: 12
      slow: 26
      signal: 9

actions:
  entry_long:
    all:
      - lhs: {feature_id: "macd_12_26_9", field: "macd"}
        op: cross_above
        rhs: {feature_id: "macd_12_26_9", field: "signal"}
```

---

## 6. Position Policy

### Exit Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| `sl_tp_only` | Exit only via SL/TP | Set-and-forget |
| `signal` | Exit via signals | Active management |
| `first_hit` | Exit on first SL/TP/signal | Hybrid |

```yaml
position_policy:
  mode: long_only  # or: short_only, long_short
  exit_mode: sl_tp_only  # Recommended for simple strategies
```

### Preventing Duplicate Trades

The engine has **three-layer protection**:

1. **Signal Evaluator**: Entry signals only when no position
2. **Engine**: Skips signal processing if position exists
3. **Exchange**: Rejects orders if position exists

**No additional configuration needed** - duplicates are automatically prevented.

---

## 7. Margin and Fees

### Fee Configuration

```yaml
account:
  fee_model:
    taker_bps: 5.5   # 0.055% taker (market orders)
    maker_bps: 2.0   # 0.02% maker (limit orders)
  slippage_bps: 2.0  # 0.02% slippage model
```

### Margin Calculation

The engine calculates entry cost as:

```
Entry Cost = Position IM + Open Fee + (Close Fee if configured)
           = (Position × IMR) + (Position × Taker Rate) + ...
```

**Best Practice:** Ensure `max_position_pct` accounts for fees:

```python
# Maximum safe position percentage
max_safe_pct = 100 / (1 + leverage * taker_fee_rate * 2)
# At 10x, 0.06% fee: 100 / (1 + 10 * 0.0006 * 2) = 98.8%
```

---

## 8. Data Requirements

### Minimum Data

- **Warmup**: At least `max(indicator_length)` bars before simulation
- **1m Data**: Required for 1m action loop and `last_price` access
- **Funding**: Optional but recommended for realistic PnL

### Data Validation

```bash
# Check data coverage before backtest
python trade_cli.py backtest preflight --play my_play --start 2025-01-01 --end 2025-12-31
```

---

## 9. Common Pitfalls

### ❌ Insufficient Margin for Position

**Symptom:** 0 trades despite signals

**Cause:** Position size + fees exceeds available margin

**Fix:** Reduce `max_position_pct` or increase starting equity

### ❌ Float Equality in DSL

**Symptom:** Runtime error "FLOAT_EQUALITY"

**Cause:** Using `eq` operator with FLOAT-typed values (like RSI, EMA)

**Note:** INT-declared fields (like `supertrend.direction`) now work with `eq` (fixed 2026-01-08).

**Fix for FLOAT fields:** Use `gt`/`lt`, `cross_above`/`cross_below`, or `near_abs`/`near_pct` with tolerance

### ❌ Missing Feature Declaration

**Symptom:** KeyError for indicator

**Cause:** Feature used in DSL not declared in `features:`

**Fix:** Declare all features explicitly

### ❌ Lookback Without History

**Symptom:** IndexError during warmup

**Cause:** Accessing `offset: N` before N bars exist

**Fix:** Ensure warmup period covers all offsets

---

## 10. Validation Checklist

Before running a backtest:

- [ ] All features declared in `features:` section
- [ ] `max_position_pct` accounts for fees
- [ ] `max_leverage` matches intended IMR
- [ ] SL/TP percentages are reasonable (not too tight)
- [ ] Data range covers warmup period
- [ ] DSL operators match value types (no float `eq`)

### Quick Validation Command

```bash
# Normalize and validate Play
python trade_cli.py backtest normalize --play my_play

# Run smoke test
python trade_cli.py backtest run --play my_play --start 2025-01-01 --end 2025-01-02 --dry-run
```

---

## 11. Performance Tips

### Reduce Context Usage

- Use parameterized feature names (e.g., `ema_9` not `ema_fast`)
- Keep action blocks simple and flat
- Avoid deeply nested boolean logic

### Optimize Backtests

- Start with short date ranges for debugging
- Use `--dry-run` to validate without full execution
- Enable debug logging for signal tracing

---

## Summary

| Aspect | Best Practice |
|--------|---------------|
| Leverage | 1x for validation, realistic for production |
| Position Size | Account for fees (use 98% max at 10x) |
| Stop Loss | Use ATR-based for volatility-adaptive |
| DSL Types | Discrete ops for ints, tolerance ops for floats |
| Features | Parameterized names always |
| Exit Mode | `sl_tp_only` for simple, `signal` for active |
| Data | Ensure warmup + 1m data available |

---

*Last updated: 2026-01-07 | Audit verified against Bybit V5 API*
