---
name: trade-validation
description: Guides TRADE validation patterns. Use when running tests, creating validation cards, or verifying changes.
---

# TRADE Validation Skill

Domain knowledge for validating TRADE code changes.

## Validation Philosophy

**CLI-Only**: All tests run through CLI commands, never pytest.

**IdeaCard-Driven**: Validation cards define test scenarios.

**Tiered Approach**: Quick checks first, integration last.

## Validation Tiers

### TIER 0: Quick Check (<10 sec)
```bash
python -m py_compile src/backtest/engine.py
```

### TIER 1: IdeaCard Normalization
```bash
python trade_cli.py backtest idea-card-normalize-batch --dir configs/idea_cards/_validation
```
- Validates indicator keys match registry
- Validates params are valid
- Validates signal rules reference declared features

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

## Validation IdeaCards

Location: `configs/idea_cards/_validation/`

| Card | Tests |
|------|-------|
| V_60_mark_price_basic | mark_price in conditions |
| V_61_zone_touch | mark_price vs BBands |
| V_62_entry_timing | MTF patterns |
| V_70_swing_basic | Swing detection |
| V_71_fibonacci | Fib levels |
| V_72_zone_state | Zone state machine |
| V_73_trend_direction | Trend classification |
| V_74_rolling_window | Rolling min/max |
| V_75_multi_tf | Multi-TF structures |

## When to Run What

| Changed | Run |
|---------|-----|
| indicator_registry.py | TIER 1 + audit-toolkit |
| engine*.py | TIER 1 + smoke |
| sim/*.py | TIER 2 audits |
| idea_cards/*.yml | TIER 1 normalize |
| Any backtest code | TIER 1-2 |

## Creating Validation Cards

```yaml
meta:
  idea_card_id: V_XX_feature_name
  tags: [validation]

symbol: BTCUSDT
exec_tf: "15m"

features:
  exec:
    - type: indicator_type
      key: test_key
      params: {...}

signal_rules:
  entry_rules:
    - direction: "long"
      conditions:
        - tf: "exec"
          indicator_key: "test_key"
          operator: "gt"
          value: 0
```
