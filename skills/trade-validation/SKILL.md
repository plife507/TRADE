---
name: trade-validation
description: Guides TRADE validation patterns. Use when running tests, creating validation plays, or verifying changes.
---

# TRADE Validation Skill

Domain knowledge for validating TRADE code changes.

## Validation Philosophy

**CLI-Only**: All tests run through CLI commands, never pytest.

**Play-Driven**: Validation Plays define test scenarios.

**Tiered Approach**: Quick checks first, integration last.

**Two-Agent System**: `validate` runs tests, `validate-updater` updates coverage.

## Validation Tiers

### TIER 0: Quick Check (<10 sec)
```bash
python -m py_compile src/backtest/engine.py
```

### TIER 1: Play Normalization (ALWAYS FIRST)
```bash
python trade_cli.py backtest play-normalize-batch --dir configs/plays/_validation
```
- Validates indicator keys match registry
- Validates params are valid
- Validates actions reference declared features
- Validates schema correctness

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

### TIER 4: Forge Stress Test
```bash
# Full pipeline validation with hash tracing
python trade_cli.py forge stress-test
```

## Two-Agent Validation System

| Agent | Model | Role | Can Modify |
|-------|-------|------|------------|
| `validate` | Sonnet | Runs tests, reports results | Nothing (read-only) |
| `validate-updater` | Opus | Updates validation system | Plays, validate.md, CLAUDE.md |

**Flow**:
1. `validate` runs tests, reports failures/coverage gaps
2. If validation system needs updating → invoke `validate-updater`
3. `validate-updater` adds Plays, updates expectations, fixes coverage

**When to invoke `validate-updater`**:
- New indicator added to registry
- Indicator params/output_keys changed
- New engine feature needs test coverage
- Test expectations changed
- Coverage gap identified

## Validation Plays

Location: `configs/plays/_validation/`

### Indicator Plays (I_)

| Play | Purpose |
|------|---------|
| `I_001_ema.yml` | EMA indicator validation |
| `I_002_sma.yml` | SMA indicator validation |
| `I_003_rsi.yml` | RSI indicator validation |
| `I_004_atr.yml` | ATR indicator validation |
| `I_005_macd.yml` | MACD multi-output validation |
| `I_006_bbands.yml` | Bollinger Bands validation |
| `I_007_stoch.yml` | Stochastic validation |
| `I_008_adx.yml` | ADX multi-output validation |
| `I_009_supertrend.yml` | SuperTrend validation |
| `I_010_ema_cross.yml` | EMA crossover pattern |

### Multi-TF Plays (M_)

| Play | Purpose |
|------|---------|
| `M_001_mtf.yml` | Multi-timeframe feature alignment |

### Operator Plays (O_)

| Play | Purpose |
|------|---------|
| `O_001_between.yml` | Between operator validation |
| `O_002_all_any.yml` | Nested all/any boolean logic |
| `O_003_holds_for.yml` | holds_for window operator |
| `O_004_near_operators.yml` | near_abs/near_pct operators |
| `O_005_occurred_within.yml` | occurred_within window operator |
| `O_006_count_true.yml` | count_true window operator |
| `O_007_partial_exit.yml` | Partial exit actions |
| `O_008_dynamic_metadata.yml` | Dynamic action metadata |

### Risk Plays (R_)

| Play | Purpose |
|------|---------|
| `R_001_atr_stop.yml` | ATR-based stop loss |
| `R_002_rr_ratio.yml` | Risk-reward ratio TP |
| `R_003_fixed_sizing.yml` | Fixed USDT sizing |
| `R_004_short_only.yml` | Short-only position mode |
| `R_005_long_short.yml` | Long/short position mode |

### Structure Plays (S_)

| Play | Purpose |
|------|---------|
| `S_001_swing.yml` | Swing high/low detection |
| `S_002_fibonacci.yml` | Fibonacci levels |
| `S_003_trend.yml` | Trend classification |
| `S_004_rolling.yml` | Rolling window min/max |
| `S_005_zone.yml` | Demand/supply zones |
| `S_006_derived_zone.yml` | Derived zones (K slots) |
| `S_007_structure_only.yml` | Structure-only Play (no features) |

## When to Run What

| Changed | Run |
|---------|-----|
| `indicator_registry.py` | TIER 1 + audit-toolkit |
| `engine*.py` | TIER 1 + smoke |
| `sim/*.py` | TIER 2 audits |
| `plays/*.yml` | TIER 1 normalize |
| `incremental/detectors/*.py` | TIER 1 + structure-smoke |
| Any backtest code | TIER 1-2 |

## Creating Validation Plays

```yaml
id: I_XXX_feature_name
version: "3.0.0"
name: "Validation: Feature Name"
description: "Tests feature X"

account:
  starting_equity_usdt: 10000.0
  max_leverage: 1.0
  margin_mode: "isolated_usdt"
  fee_model:
    taker_bps: 6.0
    maker_bps: 2.0

symbol_universe: ["BTCUSDT"]
execution_tf: "1h"

features:
  - id: indicator_20
    tf: "1h"
    type: indicator
    indicator_type: indicator_type
    params: { length: 20 }

position_policy:
  mode: "long_only"
  max_positions_per_symbol: 1

actions:
  - id: entry
    cases:
      - when:
          lhs: {feature_id: "indicator_20"}
          op: gt
          rhs: 50
        emit:
          - action: entry_long
    else:
      emit:
        - action: no_action

risk_model:
  stop_loss:
    type: "percent"
    value: 5.0
  take_profit:
    type: "rr_ratio"
    value: 2.0
  sizing:
    model: "percent_equity"
    value: 1.0
```

## Forge Stress Test Suite

Full validation + backtest pipeline with hash tracing.

**8-Step Pipeline**:
1. Generate synthetic candle data → `synthetic_data_hash`
2. Validate all plays (normalize-batch) → `config_hash`
3. Run toolkit audit (registry contract) → `registry_hash`
4. Run structure parity → `structure_hash`
5. Run indicator parity → `indicator_hash`
6. Run rollup audit → `rollup_hash`
7. Execute validation plays as backtests → `trades_hash`
8. Verify artifacts + determinism → `run_hash`

```bash
python trade_cli.py forge stress-test
```

## Validation Invocation Pattern

```python
# In Claude Code agent context
from src.tools import spawn_validate_agent

# Invoke validate agent
result = spawn_validate_agent(
    prompt="Run audit-toolkit and normalize-batch",
    subagent_type="validate"
)

# If coverage gap found, invoke updater
if result.needs_coverage_update:
    spawn_validate_agent(
        prompt="Add I_XXX_new_indicator.yml for new_indicator",
        subagent_type="validate-updater"
    )
```

## Key Commands Reference

```bash
# Quick syntax check
python -m py_compile src/backtest/engine.py

# Play normalization
python trade_cli.py backtest play-normalize-batch --dir configs/plays/_validation

# Single play normalize
python trade_cli.py backtest play-normalize --play I_001_ema

# Indicator registry audit
python trade_cli.py backtest audit-toolkit

# Rollup parity
python trade_cli.py backtest audit-rollup

# Structure smoke
python trade_cli.py backtest structure-smoke

# Metadata smoke
python trade_cli.py backtest metadata-smoke

# Full smoke test
python trade_cli.py --smoke backtest

# Forge stress test
python trade_cli.py forge stress-test
```

## Best Practices

1. **TIER 1 First**: Always run normalization before other tests
2. **Incremental**: Run only relevant tiers for changed code
3. **Add Coverage**: New features need validation Plays
4. **Parameterized Names**: Use `ema_20` not `ema_fast` in Plays
5. **Explicit Params**: No implicit defaults in validation Plays

## See Also

- `docs/specs/PLAY_SYNTAX.md` - Play YAML reference
- `src/forge/CLAUDE.md` - Forge development environment
- `docs/audits/OPEN_BUGS.md` - Bug tracker
