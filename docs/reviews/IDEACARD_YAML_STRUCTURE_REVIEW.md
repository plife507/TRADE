# IdeaCard YAML Structure Review

> **Purpose**: Comprehensive review of the IdeaCard YAML structure, including considerations, questions, and best practices for creating trading strategy configurations.

## Table of Contents

1. [Overview](#overview)
2. [Structure Breakdown](#structure-breakdown)
3. [Key Considerations](#key-considerations)
4. [Common Questions](#common-questions)
5. [Best Practices](#best-practices)
6. [Examples](#examples)

---

## Overview

IdeaCard YAML files define complete trading strategies with:
- **Multi-timeframe support** (exec, HTF, MTF)
- **Explicit indicator declarations** (no implicit defaults)
- **Signal-based entry/exit rules** (conditions-based logic)
- **Risk management** (stop loss, take profit, sizing)

**Location**: `configs/idea_cards/*.yml`

**Validation**: Use CLI commands to validate:
```bash
python trade_cli.py backtest indicators --idea-card YOUR_CARD --print-keys
python trade_cli.py backtest preflight --idea-card YOUR_CARD
python trade_cli.py backtest run --idea-card YOUR_CARD --smoke --strict
```

---

## Structure Breakdown

### 1. Identity Section

```yaml
id: SOLUSDT_15m_ema_crossover          # Unique identifier (filename without .yml)
version: "1.0.0"                       # Semantic version
name: "SOLUSDT 15m EMA Crossover"      # Display name
description: "EMA crossover strategy with HTF/MTF confirmation"
```

**Considerations**:
- `id` must be unique and match filename (without extension)
- `version` should follow semantic versioning (major.minor.patch)
- `name` and `description` are for documentation only

**Questions**:
- ❓ Can multiple IdeaCards share the same `id`? **No** - must be unique
- ❓ Does version affect execution? **No** - informational only, but tracked in artifacts

---

### 2. Symbol Universe

```yaml
symbol_universe:
  - SOLUSDT
```

**Considerations**:
- Currently supports **single symbol only** (first in list is used)
- Symbol must end in "USDT" (enforced by validation)
- Symbol is normalized to uppercase automatically

**Questions**:
- ❓ Can I specify multiple symbols? **Not yet** - only first symbol is used
- ❓ What if symbol doesn't exist in database? **Preflight check will fail** with actionable error

---

### 3. Timeframe Configurations (`tf_configs`)

```yaml
tf_configs:
  exec:                                # Required: Execution timeframe
    tf: "15m"                          # Canonical: 1m, 5m, 15m, 1h, 4h, 1d
    role: "exec"
    warmup_bars: 60                    # Bars needed for indicator stabilization
    feature_specs:                     # Indicators for this TF
      - indicator_type: "ema"
        output_key: "ema_20"
        params:
          length: 20
        input_source: "close"
  
  htf:                                 # Optional: Higher timeframe
    tf: "4h"
    role: "htf"
    warmup_bars: 200
    feature_specs: [...]
  
  mtf:                                 # Optional: Medium timeframe
    tf: "1h"
    role: "mtf"
    warmup_bars: 200
    feature_specs: [...]
```

**Considerations**:

1. **Exec TF is required** - this is where trades execute
2. **HTF/MTF are optional** - used for bias/confirmation filters
3. **Warmup bars** - must be sufficient for indicator computation:
   - EMA/SMA: typically `length` bars
   - RSI: typically `length` bars
   - ATR: typically `length` bars
   - MACD: typically `slow` period bars
   - Use `warmup_multiplier` (default 1) for safety margin
4. **Canonical timeframes** - must use `1m`, `5m`, `15m`, `1h`, `4h`, `1d` (not `60`, `240`, `D`)
5. **HTF/MTF forward-fill** - values carry forward until that TF closes (no partial candles)

**Questions**:
- ❓ What if warmup_bars is too small? **Indicators will be NaN** - preflight will warn, strict mode will fail
- ❓ Can HTF be smaller than exec? **Technically yes, but defeats purpose** - HTF should be higher timeframe
- ❓ How are HTF/MTF values updated? **Only when that TF bar closes** - then forward-filled until next close
- ❓ What if I don't specify HTF/MTF? **Strategy runs in single-TF mode** - only exec indicators available

---

### 4. Indicator Types and Multi-Output

**Single-Output Indicators**:
- `ema`, `sma`, `rsi`, `atr` → One column per indicator

**Multi-Output Indicators**:
- `macd` → `{output_key}_macd`, `{output_key}_signal`, `{output_key}_hist`
- `bbands` → `{output_key}_lower`, `{output_key}_mid`, `{output_key}_upper`
- `stoch` → `{output_key}_k`, `{output_key}_d`
- `stochrsi` → `{output_key}_k`, `{output_key}_d`

**Considerations**:
- Multi-output indicators expand to multiple columns automatically
- Use `backtest indicators --print-keys` to see exact column names
- In signal rules, reference the expanded keys (e.g., `macd_signal`, not just `macd`)

**Questions**:
- ❓ How do I reference MACD signal line? **Use `macd_signal`** (where `macd` is your output_key)
- ❓ Can I use only one part of a multi-output indicator? **Yes** - reference the specific key
- ❓ What if I want custom names? **Not supported** - use standard expansion pattern

---

### 5. Signal Rules

```yaml
signal_rules:
  entry_rules:
    - direction: "long"
      conditions:
        - indicator_key: "ema_20"
          operator: "cross_above"
          value: "ema_50"
          is_indicator_comparison: true
          tf: "exec"
    - direction: "short"
      conditions: [...]
  exit_rules: []
```

**Considerations**:

1. **All conditions must be true** (AND logic) - entry only triggers when ALL conditions pass
2. **HTF/MTF bias** - Add conditions with `tf: "htf"` or `tf: "mtf"` for trend/momentum filters
3. **Operators**:
   - `gt`, `lt`, `gte`, `lte`, `eq` - Comparison operators
   - `cross_above`, `cross_below` - Crossover detection (requires `prev_offset: 1`)
4. **Indicator comparison**:
   - `is_indicator_comparison: true` → `value` is another indicator key
   - `is_indicator_comparison: false` → `value` is a fixed number
5. **Empty exit_rules** → Uses risk_model TP/SL only

**Questions**:
- ❓ How do I add HTF/MTF bias? **Add conditions with `tf: "htf"` or `tf: "mtf"`**
- ❓ Can I use OR logic? **Not directly** - create separate entry rules for each OR case
- ❓ What's the difference between `cross_above` and `gt`? **`cross_above` detects the moment of crossing**, `gt` checks current state
- ❓ Can I exit on signal? **Yes** - add exit_rules with conditions (not just TP/SL)
- ❓ How do I reference HTF indicators? **Use `tf: "htf"` and the indicator key from HTF feature_specs**

**Example with HTF/MTF Bias**:
```yaml
entry_rules:
  - direction: "long"
    conditions:
      # Exec: Entry trigger
      - indicator_key: "ema_20"
        operator: "cross_above"
        value: "ema_50"
        is_indicator_comparison: true
        tf: "exec"
      
      # HTF: Trend bias (price above HTF EMA)
      - indicator_key: "close"
        operator: "gt"
        value: "ema_200"
        is_indicator_comparison: true
        tf: "htf"                    # ← HTF bias
      
      # MTF: Momentum bias (RSI > 50)
      - indicator_key: "rsi_14"
        operator: "gt"
        value: 50.0
        is_indicator_comparison: false
        tf: "mtf"                    # ← MTF bias
```

---

### 6. Risk Model

```yaml
risk_model:
  stop_loss:
    type: "percent"                   # or "atr_multiple"
    value: 2.0                        # 2% stop loss
    atr_key: "atr_14"                 # Required if type="atr_multiple"
    buffer_pct: 0.0                   # Optional buffer
  
  take_profit:
    type: "rr_ratio"                  # or "percent"
    value: 2.0                        # 2:1 reward:risk ratio
  
  sizing:
    model: "percent_equity"           # or "fixed_usdt"
    value: 1.0                        # 1% of equity per trade
    max_leverage: 1.0                 # Maximum leverage (1.0 = no leverage)
```

**Considerations**:

1. **Stop Loss Types**:
   - `percent` - Fixed percentage from entry price
   - `atr_multiple` - ATR-based stop (requires `atr_key` in exec TF)
2. **Take Profit Types**:
   - `rr_ratio` - Reward:Risk ratio (e.g., 2.0 = 2:1)
   - `percent` - Fixed percentage from entry price
3. **Sizing Models**:
   - `percent_equity` - Percentage of current equity
   - `fixed_usdt` - Fixed USDT amount per trade
4. **Initial Equity** - Currently hardcoded to 1000 USDT (not in YAML)

**Questions**:
- ❓ How do I set initial capital? **In `account.starting_equity_usdt`** - e.g., `starting_equity_usdt: 10000.0`
- ❓ Can I use ATR-based stops? **Yes** - set `type: "atr_multiple"` and specify `atr_key`
- ❓ What's the difference between `percent_equity` and `fixed_usdt`? **`percent_equity` scales with account**, `fixed_usdt` is constant
- ❓ How does leverage work? **`max_leverage: 2.0` allows 2x position size** (e.g., $1000 equity → $2000 position)
- ❓ Can I disable TP/SL? **No** - risk_model is required, but you can set very wide stops

---

### 7. Position Policy

```yaml
position_policy:
  mode: "long_short"                  # long_only, short_only, long_short
  max_positions_per_symbol: 1
  allow_flip: false                  # Allow reversing position direction
  allow_scale_in: false               # Allow adding to position
  allow_scale_out: false              # Allow partial exits
```

**Considerations**:
- `mode` controls allowed directions
- `allow_flip` - If true, can reverse position (e.g., long → short) without closing first
- `allow_scale_in/out` - Currently not fully implemented in all execution paths

**Questions**:
- ❓ What's the difference between `long_only` and `long_short`? **`long_only` ignores short signals**
- ❓ Can I have multiple positions? **Not yet** - `max_positions_per_symbol: 1` enforced
- ❓ What does `allow_flip` do? **Allows reversing position** without closing first (e.g., long → short)

---

## Key Considerations

### 1. Warmup Requirements

**Critical**: Ensure `warmup_bars` is sufficient for all indicators:
- EMA/SMA: `length` bars minimum
- RSI: `length` bars minimum
- ATR: `length` bars minimum
- MACD: `slow` period bars minimum

**Best Practice**: Use `warmup_multiplier` (default 1) or add safety margin:
```yaml
warmup_bars: 200  # For EMA200, use 200+ for safety
```

### 2. HTF/MTF Forward-Fill Behavior

**Important**: HTF/MTF indicators are forward-filled:
- Computed **only when that TF bar closes**
- Values **carry forward unchanged** until next TF close
- This prevents lookahead bias but means values may be "stale"

**Example**: 4h HTF closes at 00:00, next close at 04:00
- All 15m exec bars from 00:00-03:45 use the same HTF value
- At 04:00, HTF updates to new value

### 3. Indicator Key Naming

**Multi-output indicators expand automatically**:
- `macd` → `macd_macd`, `macd_signal`, `macd_hist`
- `bbands` → `bbands_lower`, `bbands_mid`, `bbands_upper`

**Always check keys**:
```bash
python trade_cli.py backtest indicators --idea-card YOUR_CARD --print-keys
```

### 4. Signal Rule Logic

**All conditions are AND logic**:
- Entry triggers only when ALL conditions pass
- For OR logic, create separate entry rules

**HTF/MTF bias**:
- Add conditions with `tf: "htf"` or `tf: "mtf"`
- These use forward-filled values (last closed bar)

### 5. Account Configuration (Required)

**Account section is now required** in all IdeaCards:

```yaml
account:
  starting_equity_usdt: 10000.0     # Starting capital in USDT
  max_leverage: 3.0                 # Maximum allowed leverage
  margin_mode: "isolated_usdt"      # Only isolated USDT supported
  min_trade_notional_usdt: 10.0     # Minimum trade size
  fee_model:
    taker_bps: 6.0                  # Taker fee (0.06%)
    maker_bps: 2.0                  # Maker fee (0.02%)
  slippage_bps: 2.0                 # Expected slippage
```

**No defaults** - all values must be explicitly specified.

---

## Common Questions

### Q: How do I add trend bias using HTF?

**A**: Add a condition with `tf: "htf"`:
```yaml
conditions:
  - indicator_key: "close"
    operator: "gt"
    value: "ema_200"
    is_indicator_comparison: true
    tf: "htf"                    # Uses HTF EMA200
```

### Q: Can I use the same indicator on multiple TFs?

**A**: Yes, but use different `output_key` names:
```yaml
exec:
  feature_specs:
    - indicator_type: "ema"
      output_key: "ema_50"       # Exec TF EMA50
htf:
  feature_specs:
    - indicator_type: "ema"
      output_key: "ema_200"      # HTF EMA200
```

### Q: How do I exit on signal instead of TP/SL?

**A**: Add `exit_rules`:
```yaml
exit_rules:
  - direction: "long"
    exit_type: "signal"
    conditions:
      - indicator_key: "ema_20"
        operator: "cross_below"
        value: "ema_50"
        is_indicator_comparison: true
        tf: "exec"
```

### Q: What if my indicator needs more warmup?

**A**: Increase `warmup_bars` in the TF config:
```yaml
exec:
  warmup_bars: 100  # Increase from default
```

### Q: Can I compare exec indicator to HTF indicator?

**A**: Yes, but specify which TF each indicator comes from:
```yaml
conditions:
  - indicator_key: "ema_20"      # Exec TF EMA
    operator: "gt"
    value: "ema_200"             # HTF EMA
    is_indicator_comparison: true
    tf: "exec"                   # Compare exec EMA to HTF EMA
```

**Note**: This compares exec EMA20 to HTF EMA200 (cross-TF comparison).

### Q: How do I know if my IdeaCard is valid?

**A**: Use CLI validation:
```bash
# Check indicator keys
python trade_cli.py backtest indicators --idea-card YOUR_CARD --print-keys

# Run preflight (data + config validation)
python trade_cli.py backtest preflight --idea-card YOUR_CARD

# Run smoke test (full pipeline)
python trade_cli.py backtest run --idea-card YOUR_CARD --smoke --strict
```

### Q: What happens if data is missing?

**A**: Preflight check will fail with actionable error:
```
Issue: Window ends at 2025-12-14 12:42 but DB latest is 2025-12-12 02:00. 
Run: python trade_cli.py backtest data-fix --idea-card YOUR_CARD --sync-to-now
```

### Q: Can I use custom indicator parameters?

**A**: Yes, via `params` in `feature_specs`:
```yaml
feature_specs:
  - indicator_type: "ema"
    output_key: "ema_custom"
    params:
      length: 21                    # Custom length
    input_source: "close"           # Custom input
```

---

## Best Practices

### 1. Naming Conventions

- **IdeaCard ID**: Use descriptive names like `SOLUSDT_15m_ema_crossover`
- **Output Keys**: Use descriptive names like `ema_20`, `rsi_14`, `atr_14`
- **Version**: Start at `1.0.0`, increment for changes

### 2. Warmup Safety

- **Always add margin**: If EMA needs 50 bars, use `warmup_bars: 60`
- **HTF/MTF need more**: Higher timeframes need more history
- **Check preflight**: It will warn if warmup is insufficient

### 3. HTF/MTF Bias

- **HTF for trend**: Use HTF for directional bias (e.g., price > HTF EMA)
- **MTF for momentum**: Use MTF for momentum filters (e.g., RSI > 50)
- **Keep it simple**: Don't over-complicate with too many bias conditions

### 4. Risk Management

- **Use ATR stops**: More adaptive than fixed percentage
- **Reasonable RR**: 2:1 or 3:1 reward:risk is standard
- **Conservative sizing**: Start with 1-2% of equity per trade

### 5. Testing Workflow

1. **Create YAML** → `configs/idea_cards/YOUR_CARD.yml`
2. **Check keys** → `backtest indicators --print-keys`
3. **Preflight** → `backtest preflight`
4. **Smoke test** → `backtest run --smoke --strict`
5. **Full backtest** → `backtest run --start ... --end ...`

---

## Examples

### Example 1: Simple EMA Crossover (No Bias)

```yaml
id: BTCUSDT_1h_ema_simple
version: "1.0.0"
name: "BTCUSDT 1h Simple EMA Crossover"

symbol_universe:
  - BTCUSDT

tf_configs:
  exec:
    tf: "1h"
    role: "exec"
    warmup_bars: 60
    feature_specs:
      - indicator_type: "ema"
        output_key: "ema_20"
        params:
          length: 20
        input_source: "close"
      - indicator_type: "ema"
        output_key: "ema_50"
        params:
          length: 50
        input_source: "close"

bars_history_required: 2

position_policy:
  mode: "long_short"
  max_positions_per_symbol: 1
  allow_flip: false
  allow_scale_in: false
  allow_scale_out: false

signal_rules:
  entry_rules:
    - direction: "long"
      conditions:
        - indicator_key: "ema_20"
          operator: "cross_above"
          value: "ema_50"
          is_indicator_comparison: true
          tf: "exec"
    - direction: "short"
      conditions:
        - indicator_key: "ema_20"
          operator: "cross_below"
          value: "ema_50"
          is_indicator_comparison: true
          tf: "exec"
  exit_rules: []

risk_model:
  stop_loss:
    type: "percent"
    value: 2.0
  take_profit:
    type: "rr_ratio"
    value: 2.0
  sizing:
    model: "percent_equity"
    value: 1.0
    max_leverage: 1.0
```

### Example 2: EMA Crossover with HTF/MTF Bias

```yaml
id: ETHUSDT_15m_ema_trend_momentum
version: "1.0.0"
name: "ETHUSDT 15m EMA with Trend & Momentum Bias"

symbol_universe:
  - ETHUSDT

tf_configs:
  exec:
    tf: "15m"
    role: "exec"
    warmup_bars: 60
    feature_specs:
      - indicator_type: "ema"
        output_key: "ema_20"
        params:
          length: 20
        input_source: "close"
      - indicator_type: "ema"
        output_key: "ema_50"
        params:
          length: 50
        input_source: "close"
      - indicator_type: "atr"
        output_key: "atr_14"
        params:
          length: 14
  htf:
    tf: "4h"
    role: "htf"
    warmup_bars: 200
    feature_specs:
      - indicator_type: "ema"
        output_key: "ema_200"
        params:
          length: 200
        input_source: "close"
  mtf:
    tf: "1h"
    role: "mtf"
    warmup_bars: 200
    feature_specs:
      - indicator_type: "rsi"
        output_key: "rsi_14"
        params:
          length: 14
        input_source: "close"

bars_history_required: 2

position_policy:
  mode: "long_short"
  max_positions_per_symbol: 1
  allow_flip: false
  allow_scale_in: false
  allow_scale_out: false

signal_rules:
  entry_rules:
    - direction: "long"
      conditions:
        # Entry trigger: EMA crossover
        - indicator_key: "ema_20"
          operator: "cross_above"
          value: "ema_50"
          is_indicator_comparison: true
          tf: "exec"
        # HTF bias: Uptrend (price > HTF EMA200)
        - indicator_key: "close"
          operator: "gt"
          value: "ema_200"
          is_indicator_comparison: true
          tf: "htf"
        # MTF bias: Momentum (RSI > 50)
        - indicator_key: "rsi_14"
          operator: "gt"
          value: 50.0
          is_indicator_comparison: false
          tf: "mtf"
    - direction: "short"
      conditions:
        # Entry trigger: EMA cross below
        - indicator_key: "ema_20"
          operator: "cross_below"
          value: "ema_50"
          is_indicator_comparison: true
          tf: "exec"
        # HTF bias: Downtrend (price < HTF EMA200)
        - indicator_key: "close"
          operator: "lt"
          value: "ema_200"
          is_indicator_comparison: true
          tf: "htf"
        # MTF bias: Momentum (RSI < 50)
        - indicator_key: "rsi_14"
          operator: "lt"
          value: 50.0
          is_indicator_comparison: false
          tf: "mtf"
  exit_rules: []

risk_model:
  stop_loss:
    type: "atr_multiple"
    value: 1.5
    atr_key: "atr_14"
    buffer_pct: 0.0
  take_profit:
    type: "rr_ratio"
    value: 3.0
  sizing:
    model: "percent_equity"
    value: 2.0
    max_leverage: 2.0
```

---

## Summary

### What Works Well

✅ **Explicit indicator declarations** - No magic, everything is declared
✅ **Multi-timeframe support** - HTF/MTF bias filters work correctly
✅ **Forward-fill semantics** - Prevents lookahead bias
✅ **CLI validation** - Comprehensive preflight and smoke tests
✅ **Structured risk model** - Flexible TP/SL and sizing options

### What's Missing or Unclear

⚠️ **OR logic** - Must create separate entry rules
⚠️ **Multiple symbols** - Only first symbol in universe is used
⚠️ **Scale in/out** - Declared but not fully implemented
⚠️ **Custom exit rules** - Can be added but examples are sparse

### What Was Fixed (2025-12-14)

✅ **Account section** - Now required with `starting_equity_usdt`, `max_leverage`, fees
✅ **History for crossovers** - Auto-detected from signal rules (no manual config needed)
✅ **Multi-TF mode** - Automatically enabled when HTF/MTF defined in tf_configs

### Recommendations

1. **Document OR logic patterns** - Show how to create multiple entry rules
2. **Add more examples** - Especially for exit rules and complex conditions
3. **Clarify HTF/MTF semantics** - Emphasize forward-fill behavior in docs

---

## Validation Checklist

Before using an IdeaCard, verify:

- [ ] `id` matches filename (without .yml)
- [ ] All timeframes are canonical (`1m`, `5m`, `15m`, `1h`, `4h`, `1d`)
- [ ] `warmup_bars` is sufficient for all indicators
- [ ] Indicator keys are referenced correctly in signal rules
- [ ] HTF/MTF indicators use `tf: "htf"` or `tf: "mtf"` in conditions
- [ ] Multi-output indicators use expanded keys (e.g., `macd_signal`)
- [ ] Risk model has valid stop_loss and take_profit types
- [ ] Run `backtest indicators --print-keys` to verify keys
- [ ] Run `backtest preflight` to verify data coverage
- [ ] Run `backtest run --smoke --strict` to verify pipeline

---

**Last Updated**: 2025-12-14
**Reviewer**: CLI-First Backtest Implementation

