---
allowed-tools: Bash, Read
description: Run backtest smoke test with validation Plays
argument-hint: [--mixed]
---

# Backtest Smoke Command

Run backtest smoke tests to verify engine functionality.

## Usage

```
/backtest-smoke [--mixed]
```

- Default: Run single Play smoke
- `--mixed`: Run all validation Plays

## Single Smoke

```bash
python trade_cli.py --smoke backtest
```

Expected:
- Preflight passes
- Trades generated
- Artifacts created (result.json, trades.parquet, equity.parquet)

## Mixed Smoke

```bash
# Set environment for full backtest inclusion
$env:TRADE_SMOKE_INCLUDE_BACKTEST="1"

# Run with mixed smoke (tests multiple Plays)
python -c "from src.cli.smoke_tests import run_backtest_mixed_smoke; exit(run_backtest_mixed_smoke())"
```

Expected:
- All validation Plays pass
- Various trade counts per Play
- No failures

## Report Format

```
## Backtest Smoke Report

### Single Smoke
- Play: [play_name]
- Status: PASS
- Trades: X
- Artifacts: OK

### Mixed Smoke (if --mixed)
| Play | Status | Trades |
|------|--------|--------|
| T_001_simple_gt | PASS | X |
| F_001_ema_crossover | PASS | X |
| ... | ... | ... |

### Summary
All smoke tests passing.
```
