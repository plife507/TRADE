---
allowed-tools: Bash, Read
description: Run backtest smoke test with validation IdeaCards
argument-hint: [--mixed]
---

# Backtest Smoke Command

Run backtest smoke tests to verify engine functionality.

## Usage

```
/trade-workflow:backtest-smoke [--mixed]
```

- Default: Run single IdeaCard smoke
- `--mixed`: Run all validation cards (V_60-V_75)

## Single Smoke

```bash
python trade_cli.py --smoke backtest
```

Expected:
- Preflight passes
- 3 trades generated
- Artifacts created (result.json, trades.parquet, equity.parquet)

## Mixed Smoke

```bash
# Set environment for full backtest inclusion
$env:TRADE_SMOKE_INCLUDE_BACKTEST="1"

# Run with mixed smoke (tests V_60-V_75)
python -c "from src.cli.smoke_tests import run_backtest_mixed_smoke; exit(run_backtest_mixed_smoke())"
```

Expected:
- All 9 validation cards pass
- Various trade counts per card
- No failures

## Report Format

```
## Backtest Smoke Report

### Single Smoke
- IdeaCard: BTCUSDT_1h_ema_basic
- Status: PASS
- Trades: 3
- Artifacts: OK

### Mixed Smoke (if --mixed)
| Card | Status | Trades |
|------|--------|--------|
| V_60_mark_price_basic | PASS | X |
| V_61_zone_touch | PASS | X |
| ... | ... | ... |

### Summary
All smoke tests passing.
```
