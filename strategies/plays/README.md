# Play Folder Structure

> **Canonical location for Play YAML files used in backtesting.**

## Folder Tree

```
strategies/
└── plays/                         # ← Canonical Plays (for backtesting)
    ├── README.md                  # This file
    ├── _validation/               # Validation Plays (V_100+)
    │   ├── V_100_blocks_basic.yml
    │   ├── V_101_all_any.yml
    │   └── ...
    └── _stress_test/              # Stress Test Plays (T_001+)
        ├── T_001_ema_crossover.yml
        └── ...

backtests/                         # ← Backtest artifacts (auto-generated)
└── {play_id}/
    └── {symbol}/
        └── run-{NNN}/
            ├── trades.csv
            ├── equity.csv
            ├── result.json
            └── pipeline_signature.json
```

## Naming Convention

| Prefix | Purpose | Examples |
|--------|---------|----------|
| `V_` | Validation Plays (DSL testing) | `V_100_blocks_basic`, `V_101_all_any` |
| `T_` | Stress Test Plays (backtest testing) | `T_001_ema_crossover` |
| `{SYMBOL}_` | Production strategies | `SOLUSDT_5m_ema_crossover` |

## Play Structure (blocks DSL v3.0.0)

```yaml
# Identity
id: V_100_blocks_basic
version: "3.0.0"
name: "Display Name"
description: "Description"

# Account (REQUIRED - no defaults)
account:
  starting_equity_usdt: 10000.0
  max_leverage: 3.0
  margin_mode: "isolated_usdt"
  min_trade_notional_usdt: 10.0
  fee_model:
    taker_bps: 6.0
    maker_bps: 2.0
  slippage_bps: 2.0

# Symbol
symbol_universe:
  - "BTCUSDT"

# Execution timeframe (bar stepping granularity)
execution_tf: "1h"

# Features (indicators + structures)
features:
  - id: "ema_fast"
    tf: "1h"
    type: indicator
    indicator_type: ema
    params:
      length: 9

  - id: "ema_slow"
    tf: "1h"
    type: indicator
    indicator_type: ema
    params:
      length: 21

# Position Policy
position_policy:
  mode: "long_only"
  max_positions_per_symbol: 1
  allow_flip: false

# Strategy Logic (blocks DSL v3.0.0)
blocks:
  - id: entry
    cases:
      - when:
          lhs:
            feature_id: "ema_fast"
          op: gt
          rhs:
            feature_id: "ema_slow"
        emit:
          - action: entry_long
    else:
      emit:
        - action: no_action

  - id: exit
    cases:
      - when:
          lhs:
            feature_id: "ema_fast"
          op: lt
          rhs:
            feature_id: "ema_slow"
        emit:
          - action: exit_long

# Risk Model
risk_model:
  stop_loss:
    type: "percent"
    value: 5.0
  take_profit:
    type: "rr_ratio"
    value: 2.0
  sizing:
    model: "percent_equity"
    value: 2.0
    max_leverage: 3.0
```

## Blocks DSL v3.0.0

### Operators

| Operator | Type | Description |
|----------|------|-------------|
| `gt`, `lt`, `gte`, `lte` | Comparison | Numeric comparisons |
| `eq` | Equality | Discrete values (enum, bool) |
| `cross_above`, `cross_below` | Crossover | Previous vs current comparison |
| `between` | Range | Value in range (inclusive) |
| `near_abs`, `near_pct` | Proximity | Within absolute/percent distance |
| `in` | Membership | Value in set |
| `holds_for` | Window | Condition true for N bars |
| `occurred_within` | Window | Condition occurred in last N bars |
| `count_true` | Window | Count true conditions in window |

### Boolean Logic

```yaml
# AND (all must be true)
all:
  - lhs: {feature_id: "ema_fast"}
    op: gt
    rhs: {feature_id: "ema_slow"}
  - lhs: {feature_id: "rsi"}
    op: lt
    rhs: 70

# OR (any must be true)
any:
  - lhs: {feature_id: "rsi"}
    op: lt
    rhs: 30
  - lhs: {feature_id: "rsi"}
    op: gt
    rhs: 70

# NOT (negate condition)
not:
  lhs: {feature_id: "trend"}
    op: eq
    rhs: "down"
```

### Nested Logic

```yaml
# (EMA crossover) AND (RSI not overbought OR RSI not oversold)
when:
  all:
    - lhs: {feature_id: "ema_fast"}
      op: gt
      rhs: {feature_id: "ema_slow"}
    - any:
        - lhs: {feature_id: "rsi"}
          op: lt
          rhs: 70
        - lhs: {feature_id: "rsi"}
          op: gt
          rhs: 30
```

## Validation Plays

| Play | Purpose |
|------|---------|
| V_100 | Basic blocks DSL |
| V_101 | Nested all/any logic |
| V_102 | Between operator |
| V_103 | Crossover operators |
| V_104 | holds_for window |
| V_105 | occurred_within window |
| V_106 | NOT operator |
| V_107-V_110 | near_abs, near_pct, in, count_true |
| V_115 | Type-safe operators |
| V_120-V_122 | Derived zones |
| V_300-V_301 | Setup references |

## CLI Commands

```bash
# Normalize (validate) a single Play
python trade_cli.py backtest play-normalize --id V_100_blocks_basic

# Normalize all validation Plays
python trade_cli.py backtest play-normalize-batch --dir strategies/plays/_validation

# Run smoke test
python trade_cli.py --smoke forge
```

---

**DEPRECATED**: The old `signal_rules` format is no longer supported. Use `blocks` (v3.0.0).
