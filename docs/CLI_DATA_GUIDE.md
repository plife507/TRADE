# CLI Data Guide for Backtesting

How to ensure you have the right market data for running backtests.

## How Data Works

- Market data is stored in DuckDB: `data/market_data_live.duckdb` (default)
- The CLI defaults to `--data-env live` which uses this database
- Data is organized by symbol and timeframe (e.g., BTCUSDT 15m, ETHUSDT 1h)
- Each Play YAML declares 3 timeframes: `low_tf`, `med_tf`, `high_tf`
- The engine also needs 1m data for mark price simulation

## Automatic Data Sync (`--fix-gaps`)

The simplest approach: `--fix-gaps` is **enabled by default** on `backtest run`.

```bash
python trade_cli.py backtest run --play my_play --start 2025-06-01 --end 2025-08-01
```

This automatically:
1. Reads the play's symbol and all 3 feed timeframes (low_tf, med_tf, high_tf)
2. Checks what data exists in DuckDB for each timeframe
3. Downloads missing ranges from Bybit
4. Includes 1m data for the execution window (mark price simulation)
5. Runs the backtest

To disable auto-sync: `--no-fix-gaps`

## Manual Data Sync (`data-fix`)

For pre-syncing data before running multiple backtests:

```bash
# Sync all timeframes for a play from a start date to now
python trade_cli.py backtest data-fix --play my_play --start 2025-01-01 --sync-to-now

# Sync and fill any gaps
python trade_cli.py backtest data-fix --play my_play --start 2025-01-01 --fill-gaps

# Full heal (sync + fill gaps + repair)
python trade_cli.py backtest data-fix --play my_play --start 2025-01-01 --heal
```

The `data-fix` command reads the play's symbol and timeframes, then syncs data for ALL of them (low_tf, med_tf, high_tf, plus 1m).

## What Gets Synced

Given a play with:
```yaml
timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "D"
  exec: "low_tf"
```

The preflight gate syncs these timeframes for the play's symbol:
- `15m` (low_tf / exec) - main execution data
- `1h` (med_tf) - medium timeframe structure data
- `D` (high_tf) - daily context data
- `1m` - always included for mark price simulation

Plus warmup bars before the start date (typically 200-500 bars depending on indicator lengths).

## Common Workflows

### Run a single backtest
```bash
python trade_cli.py backtest run --play my_play --start 2025-06-01 --end 2025-08-01
```
Data auto-syncs via `--fix-gaps` (default on).

### Run without network access
```bash
python trade_cli.py backtest run --play my_play --start 2025-06-01 --end 2025-08-01 --no-fix-gaps
```
Fails if data is missing. Use when you know data is already synced.

### Pre-sync data for a symbol
```bash
python trade_cli.py backtest data-fix --play my_play --start 2025-01-01 --sync-to-now --fill-gaps
```
Ensures all timeframes are available from Jan 2025 to now.

### Run the full 60-play verification suite
```bash
python scripts/run_real_verification.py
```
Each play auto-syncs via `--fix-gaps`. Dates extracted from play description fields.

### Run synthetic (no real data needed)
```bash
python trade_cli.py backtest run --play my_play --synthetic --synthetic-pattern trending
```
Generates synthetic candles in-memory. No DuckDB access needed.

## Troubleshooting

### "No data for timeframe X"
The play declares a timeframe that has no data in DuckDB. Fix:
```bash
python trade_cli.py backtest data-fix --play my_play --start 2025-01-01 --sync-to-now
```

### "Window start before earliest data"
Your `--start` date is before any available data. Either:
- Use a later `--start` date
- Sync older data: `--start 2024-01-01 --sync-to-now`

### DuckDB lock errors
DuckDB allows only one writer at a time. If another process has the database open:
- Close other Python processes using the database
- The runner script retries automatically (5 attempts with backoff)

### Data environment mismatch
The CLI defaults to `--data-env live` (uses `market_data_live.duckdb`). If you synced data to a different database, specify the environment:
```bash
python trade_cli.py backtest run --play my_play --data-env live
```

## Database Files

| Environment | Database File | Usage |
|-------------|--------------|-------|
| `live` (default) | `data/market_data_live.duckdb` | Production backtests, verification |
| `demo` | `data/market_data_demo.duckdb` | Testnet data |
