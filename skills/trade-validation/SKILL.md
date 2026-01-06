---
name: trade-validation
description: Guides TRADE validation patterns. Use when running tests, creating validation plays, or verifying changes.
---

# TRADE Validation Skill

Domain knowledge for validating TRADE code changes.

## Validation Philosophy

**CLI-Only**: All tests run through CLI commands, never pytest.

**Play-Driven**: Validation plays define test scenarios.

**Tiered Approach**: Quick checks first, integration last.

## Validation Tiers

### TIER 0: Quick Check (<10 sec)
```bash
python -m py_compile src/backtest/engine.py
```

### TIER 1: Play Normalization
```bash
python trade_cli.py backtest play-normalize-batch --dir configs/plays/_validation
```
- Validates indicator keys match registry
- Validates params are valid
- Validates actions reference declared features

### TIER 2: Unit Audits
```bash
python trade_cli.py backtest audit-toolkit      # 42/42 indicators
python trade_cli.py backtest audit-rollup       # Rollup parity
python trade_cli.py backtest structure-smoke    # Market structure
python trade_cli.py backtest metadata-smoke     # Indicator metadata
```

### TIER 3: Integration
```bash
python trade_cli.py --smoke backtest
```

## Validation Plays

Location: `configs/plays/_validation/`

| Prefix | Category | Examples |
|--------|----------|----------|
| I_ | Indicators | I_001_ema, I_005_macd, I_010_ema_cross |
| M_ | Multi-TF | M_001_mtf |
| O_ | Operators | O_001_between, O_003_crossover |
| R_ | Risk | R_001_atr_stop, R_005_long_short |
| S_ | Structures | S_001_swing, S_006_derived_zone |

## When to Run What

| Changed | Run |
|---------|-----|
| indicator_registry.py | TIER 1 + audit-toolkit |
| engine*.py | TIER 1 + smoke |
| sim/*.py | TIER 2 audits |
| plays/*.yml | TIER 1 normalize |
| Any backtest code | TIER 1-2 |

## Creating Validation Plays

```yaml
id: I_XXX_feature_name
version: "3.0.0"
name: "Validation: Feature Name"
description: "Tests feature X"

account:
  initial_equity_usdt: 10000
  leverage: 1

symbol_universe: ["BTCUSDT"]
execution_tf: "1h"

features:
  - id: indicator_20
    type: indicator_type
    params: { length: 20 }

actions:
  - action: entry_long
    when: indicator_20 > 50
```
