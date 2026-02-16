---
allowed-tools: Bash, Read, Grep, Glob
description: Run TRADE validation suite (Play normalize, audits, smoke tests)
argument-hint: [tier: quick|standard|full|pre-live|exchange]
---

# Validate Command

Run the unified TRADE validation suite at the specified tier.

## Usage

```
/validate [tier]
```

- `quick` - Core plays + audits (~10s, default)
- `standard` - + structure/rollup/sim/suite/metrics (~2min)
- `full` - + full indicator/pattern suites, determinism (~10min)
- `pre-live` - Connectivity + readiness gate for specific play
- `exchange` - Exchange integration (API, account, market data, order flow) (~30s)

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

# Exchange integration
python trade_cli.py validate exchange

# JSON output for CI
python trade_cli.py validate quick --json

# Skip fail-fast (run all gates even on failure)
python trade_cli.py validate standard --no-fail-fast
```

## What Each Tier Tests

### Quick (G1-G4)
- G1: YAML parse + normalize all 5 core plays
- G2: Indicator registry contract audit (44 indicators)
- G3: Incremental vs vectorized parity audit (43 indicators)
- G4: Run 5 core plays with synthetic data (all must produce trades)

### Standard (G5-G11)
- G5: Structure detector parity (7 detectors)
- G6: 1m rollup bucket parity
- G7: Simulator order type smoke tests (6 order types)
- G8: Operator suite (plays/validation/operators/)
- G9: Structure suite (plays/validation/structures/)
- G10: Complexity ladder (plays/validation/complexity/)
- G11: Financial metrics audit (drawdown, CAGR, Calmar, TF normalization)

### Full (G12-G14)
- G12: Full indicator suite (plays/validation/indicators/)
- G13: Full pattern suite (plays/validation/patterns/)
- G14: Engine determinism (same input = same output, 5 plays x2 runs)

### Pre-Live (PL1-PL3 + G1 + G4)
- PL1: Bybit API connectivity
- PL2: Account balance sufficiency for play
- PL3: No conflicting open positions
- G1: YAML parse (core plays)
- G4: Core engine plays (synthetic)

### Exchange (EX1-EX5)
- EX1: API connectivity + server time offset
- EX2: Account balance, exposure, portfolio, collateral
- EX3: Market data (prices, OHLCV, funding, open interest, orderbook)
- EX4: Order flow (place limit buy -> verify -> cancel, demo mode only)
- EX5: Diagnostics (rate limits, WebSocket status, health check)

## Debug Commands

For targeted investigation when a gate fails:

```bash
# Indicator math parity for a specific play
python trade_cli.py debug math-parity --play <play_name> --start <date> --end <date>

# Snapshot plumbing parity
python trade_cli.py debug snapshot-plumbing --play <play_name> --start <date> --end <date>

# Engine determinism comparison
python trade_cli.py debug determinism --run-a <path_a> --run-b <path_b>

# Standalone metrics audit
python trade_cli.py debug metrics
```

## Core Validation Plays

Located in `plays/validation/core/`:

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
- G2 Registry Contract: PASS (44/44)
- G3 Incremental Parity: PASS
- G4 Core Plays: PASS (5/5, 2134 trades)

### Summary
All gates passed.
```
