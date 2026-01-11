# Play Folder Structure

> **Canonical location for production Play YAML files.**

## Current Structure

```
strategies/
└── plays/                         # ← Production Plays (proven strategies)
    ├── README.md                  # This file
    └── TEMPLATE.yml               # Template for new Plays

tests/
├── validation/plays/              # ← Validation Plays (V_100+) - DSL contract tests
├── stress/plays/                  # ← Stress Test Plays - engine verification
└── functional/strategies/         # ← Functional Test Plays

backtests/                         # ← Backtest artifacts (auto-generated, gitignored)
└── {category}/{play_id}/{symbol}/{run_hash}/
```

## Naming Convention

| Prefix | Purpose | Location |
|--------|---------|----------|
| `V_` | Validation Plays (DSL testing) | `tests/validation/plays/` |
| `S_` | Stress Test Plays | `tests/stress/plays/` |
| `{SYMBOL}_` | Production strategies | `strategies/plays/` |

## Play Structure (actions DSL v3.0.0)

> **Note**: The YAML key is `actions:` (renamed from `blocks:` on 2026-01-05)

```yaml
# Identity
id: BTCUSDT_15m_ema_crossover
version: "3.0.0"
name: "EMA Crossover Strategy"
description: "Simple EMA crossover on 15m timeframe"

# Account (REQUIRED - no defaults)
account:
  starting_equity_usdt: 10000.0
  max_leverage: 3.0
  margin_mode: "isolated_usdt"
  min_trade_notional_usdt: 10.0
  fee_model:
    taker_bps: 5.5
    maker_bps: 2.0
  slippage_bps: 2.0

# Symbol
symbol_universe:
  - "BTCUSDT"

# Execution timeframe
tf: "15m"

# Features (use parameterized naming: ema_9, not ema_fast)
features:
  - id: "ema_9"
    indicator: ema
    params:
      length: 9

  - id: "ema_21"
    indicator: ema
    params:
      length: 21

# Position Policy
position_policy:
  mode: "long_only"
  max_positions_per_symbol: 1
  allow_flip: false

# Strategy Logic (actions DSL v3.0.0)
actions:
  - id: entry
    cases:
      - when:
          lhs: {feature_id: "ema_9"}
          op: cross_above
          rhs: {feature_id: "ema_21"}
        emit:
          - action: entry_long

  - id: exit
    cases:
      - when:
          lhs: {feature_id: "ema_9"}
          op: cross_below
          rhs: {feature_id: "ema_21"}
        emit:
          - action: exit_long

# Risk Model
risk_model:
  stop_loss:
    type: "percent"
    value: 2.0
  take_profit:
    type: "rr_ratio"
    value: 2.0
  sizing:
    model: "percent_equity"
    value: 2.0
    max_leverage: 3.0
```

## DSL Operators (Frozen 2026-01-08)

| Category | Operators |
|----------|-----------|
| Comparison | `gt`, `lt`, `gte`, `lte` |
| Equality | `eq` (discrete values only) |
| Crossover | `cross_above`, `cross_below` |
| Range | `between` |
| Proximity | `near_abs`, `near_pct` |
| Membership | `in` |
| Window (bars) | `holds_for`, `occurred_within`, `count_true` |
| Window (duration) | `holds_for_duration`, `occurred_within_duration`, `count_true_duration` |

## Boolean Logic

```yaml
# AND - all must be true
all:
  - lhs: {feature_id: "ema_9"}
    op: gt
    rhs: {feature_id: "ema_21"}
  - lhs: {feature_id: "rsi_14"}
    op: lt
    rhs: 70

# OR - any must be true
any:
  - lhs: {feature_id: "rsi_14"}
    op: lt
    rhs: 30
  - lhs: {feature_id: "rsi_14"}
    op: gt
    rhs: 70

# NOT - negate condition
not:
  lhs: {feature_id: "trend"}
  op: eq
  rhs: "down"
```

## CLI Commands

```bash
# Normalize (validate) a single Play
python trade_cli.py backtest play-normalize --id BTCUSDT_15m_ema_crossover

# Normalize validation Plays
python trade_cli.py backtest play-normalize-batch --dir tests/validation/plays

# Run a backtest
python trade_cli.py backtest run --play BTCUSDT_15m_ema_crossover --start 2025-10-01 --end 2026-01-10
```

## See Also

- `docs/specs/PLAY_DSL_COOKBOOK.md` - Full DSL reference
- `docs/guides/DSL_STRATEGY_PATTERNS.md` - 7 strategy patterns
- `tests/validation/plays/` - DSL contract tests

---

**DEPRECATED**: The old `signal_rules` and `blocks:` formats are no longer supported. Use `actions:` (v3.0.0).
