---
allowed-tools: Bash, Read
description: Run backtest smoke test on a specific play
argument-hint: [--play <name>]
---

# Backtest Smoke Command

Run a quick backtest smoke test to verify engine functionality for a specific play.

## Usage

```
/backtest-smoke [--play <name>]
```

## Process

1. **Run the play in smoke mode** (small window, fast wiring check):

```bash
python trade_cli.py backtest run --play <name> --smoke
```

If no play specified, run quick validation instead:

```bash
python trade_cli.py validate quick
```

2. **Verify results**:
- Preflight passes
- Trades generated (non-zero)
- Artifacts created (result.json, trades.parquet, equity.parquet)

## Report Format

```
## Backtest Smoke Report

### Play: [play_name]
- Status: PASS/FAIL
- Trades: X
- Artifacts: OK/MISSING

### Summary
Smoke test passing.
```

## See Also

For broader validation, use `/validate quick` (runs 5 core plays with synthetic data).
