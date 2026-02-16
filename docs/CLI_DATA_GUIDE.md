# CLI Data Guide for Backtesting

How to ensure you have the right market data for running backtests.

## How Data Works

- Market data is stored in DuckDB: `data/market_data_live.duckdb` (CLI default)
- The CLI defaults to `--data-env live` which uses this database
- Data is organized by symbol and timeframe (e.g., BTCUSDT 15m, ETHUSDT 1h)
- Each Play YAML declares 3 timeframes: `low_tf`, `med_tf`, `high_tf`
- The engine also needs 1m data for fill simulation (TP/SL evaluation), signal subloop, and mark price proxy

## Automatic Data Sync (`--sync`)

The simplest approach: `--sync` is **enabled by default** on `backtest run`.

```bash
python trade_cli.py backtest run --play my_play --start 2025-06-01 --end 2025-08-01
```

This automatically:
1. Reads the play's symbol and all 3 feed timeframes (low_tf, med_tf, high_tf)
2. Checks what data exists in DuckDB for each timeframe
3. Downloads missing ranges from Bybit
4. Includes 1m data for the execution window
5. Runs the backtest

To disable auto-sync: `--no-sync`

## Manual Data Sync (`data-fix`)

For pre-syncing data before running multiple backtests:

```bash
# Sync all timeframes for a play from a start date to now
python trade_cli.py backtest data-fix --play my_play --start 2025-01-01 --sync-to-now

# Full heal (sync + repair)
python trade_cli.py backtest data-fix --play my_play --start 2025-01-01 --heal
```

The `data-fix` command reads the play's symbol and timeframes, then syncs data for ALL of them (low_tf, med_tf, high_tf, plus 1m). Sync is on by default (`--sync` defaults to True).

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
- `1m` - always included for fill simulation and mark price proxy

Plus warmup bars before the start date (typically 200-500 bars depending on indicator lengths).

## Common Workflows

### Run a single backtest
```bash
python trade_cli.py backtest run --play my_play --start 2025-06-01 --end 2025-08-01
```
Data auto-syncs via `--sync` (default on).

### Run without network access
```bash
python trade_cli.py backtest run --play my_play --start 2025-06-01 --end 2025-08-01 --no-sync
```
Fails if data is missing. Use when you know data is already synced.

### Pre-sync data for a symbol
```bash
python trade_cli.py backtest data-fix --play my_play --start 2025-01-01 --sync-to-now
```
Ensures all timeframes are available from Jan 2025 to now.

### Run synthetic (no real data needed)
```bash
# Uses play's synthetic: block (pattern, bars, seed)
python trade_cli.py backtest run --play my_play --synthetic

# Override pattern from play's block
python trade_cli.py backtest run --play my_play --synthetic --synthetic-pattern trend_up_clean
```
Generates synthetic candles in-memory. No DuckDB access needed. The play must have a `synthetic:` block or the command fails. See `docs/SYNTHETIC_DATA_REFERENCE.md` for pattern catalog.

### Run the full 60-play verification suite
```bash
python scripts/run_real_verification.py
```
Each play auto-syncs via `--sync`.

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
- The runner scripts retry automatically (5 attempts, 3-15s backoff)

### Data environment mismatch
The CLI defaults to `--data-env live` (uses `market_data_live.duckdb`). If you synced data to a different environment:
```bash
python trade_cli.py backtest run --play my_play --data-env demo
```

## Database Files

| CLI `--data-env` | Database File | Usage |
|------------------|--------------|-------|
| `live` (default) | `data/market_data_live.duckdb` | Backtests, verification, live warm-up |
| `demo` | `data/market_data_demo.duckdb` | Paper trading (demo API feed) |

A third environment `backtest` (`data/market_data_backtest.duckdb`) exists in `src/config/constants.py` as the programmatic default for tools, but is not exposed via the CLI `--data-env` flag.
