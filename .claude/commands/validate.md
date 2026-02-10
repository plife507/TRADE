---
allowed-tools: Bash, Read, Grep, Glob
description: Run TRADE validation suite (Play normalize, audits, smoke tests)
argument-hint: [tier: quick|standard|full|pre-live]
---

# Validate Command

Run the unified TRADE validation suite at the specified tier.

## Usage

```
/validate [tier]
```

- `quick` - Core plays + audits (~10s, default)
- `standard` - + synthetic suites (~2min)
- `full` - + full indicator/pattern suites, math verification (~10min)
- `pre-live` - Connectivity + readiness gate for specific play

## Execution

```bash
# Quick (pre-commit)
python trade_cli.py validate quick

# Standard (pre-merge)
python trade_cli.py validate standard

# Full (pre-release)
python trade_cli.py validate full

# Pre-live (specific play readiness)
python trade_cli.py validate pre-live --play <play_name>

# JSON output for CI
python trade_cli.py validate quick --json

# Skip fail-fast (run all gates even on failure)
python trade_cli.py validate standard --no-fail-fast
```

## What Each Tier Tests

### Quick (G1-G4)
- G1: YAML parse + normalize all 5 core plays
- G2: Indicator toolkit contract audit (43+ indicators)
- G3: Incremental parity audit
- G4: Run 5 core plays with synthetic data (all must produce trades)

### Standard (G5-G10)
- G5-G8: Structure parity, rollup parity, sim orders, operator/structure/complexity suites
- G9-G10: Additional suite coverage

### Full (G11-G12)
- G11: Full 170-play synthetic suite
- G12: 60-play real-data verification with math checks

### Pre-Live (PL1-PL3)
- PL1: Exchange connectivity
- PL2: Play-specific readiness
- PL3: Risk parameter validation

## Core Validation Plays

Located in `plays/core_validation/`:

| Play | Exercises |
|------|-----------|
| V_CORE_001_indicator_cross | EMA crossover, swing/trend structures, first_hit exit |
| V_CORE_002_structure_chain | swing -> trend -> market_structure, BOS/CHoCH |
| V_CORE_003_cases_metadata | cases/when/emit, metadata capture, bbands multi-output |
| V_CORE_004_multi_tf | Higher timeframe features + structures, forward-fill |
| V_CORE_005_arithmetic_window | holds_for, occurred_within, between, near_pct, rolling_window |

## Report Format

```
## Validation Report

### Quick Tier
- G1 YAML Parse: PASS (5/5)
- G2 Toolkit Audit: PASS (43/43)
- G3 Incremental Parity: PASS
- G4 Core Plays: PASS (5/5, 2134 trades)

### Summary
All gates passed.
```
