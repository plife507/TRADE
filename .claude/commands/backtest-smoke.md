---
allowed-tools: Bash, Read
description: Run backtest smoke test with validation Plays
---

# Backtest Smoke Command

Run backtest smoke tests to verify engine functionality.

## Usage

```bash
# Preferred: use unified validate
python trade_cli.py validate quick

# Legacy smoke (still functional)
python trade_cli.py --smoke full
python trade_cli.py --smoke backtest
```

Expected:
- Preflight passes
- Trades generated
- Artifacts created (result.json, trades.parquet, equity.parquet)

## Report Format

```
## Backtest Smoke Report

### Single Smoke
- Play: [play_name]
- Status: PASS
- Trades: X
- Artifacts: OK

### Summary
All smoke tests passing.
```
