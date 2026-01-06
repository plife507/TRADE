# TRADE Data Module

**STATUS:** CANONICAL
**PURPOSE:** Data module documentation: stores, schemas, checks, lineage, readiness
**LAST UPDATED:** December 17, 2025

---

## Overview

The Data module provides historical market data storage and retrieval via DuckDB. It serves as the source of truth for all backtesting operations.

**Key Files:**
- `src/data/historical_data_store.py` — Main DuckDB interface
- `src/data/historical_sync.py` — Sync from Bybit API
- `src/data/historical_queries.py` — Query helpers
- `src/data/historical_maintenance.py` — Heal, cleanup, vacuum
- `src/data/sessions.py` — DuckDB session management

---

## Stores & Files

| File | Purpose | Environment |
|------|---------|-------------|
| `data/market_data_live.duckdb` | Production data from LIVE API | Live |
| `data/market_data_demo.duckdb` | Demo data (isolated testing) | Demo |

**Note:** All historical data for backtesting comes from LIVE API (`api.bybit.com`). Demo API may have incomplete history.

---

## Schema

### Table: `ohlcv_live` / `ohlcv_demo`

| Column | Type | Nullable | Key | Description |
|--------|------|----------|-----|-------------|
| `symbol` | VARCHAR | NO | PK | Trading pair (e.g., BTCUSDT) |
| `timeframe` | VARCHAR | NO | PK | Candle timeframe (1m, 5m, 15m, 1h, 4h, 1d) |
| `timestamp` | TIMESTAMP | NO | PK | Bar open time (ts_open) in UTC |
| `open` | DOUBLE | YES | — | Open price |
| `high` | DOUBLE | YES | — | High price |
| `low` | DOUBLE | YES | — | Low price |
| `close` | DOUBLE | YES | — | Close price |
| `volume` | DOUBLE | YES | — | Trading volume |
| `turnover` | DOUBLE | YES | — | Turnover in quote currency |

**Primary Key:** `(symbol, timeframe, timestamp)`

### Table: `funding_rates_live` / `funding_rates_demo`

| Column | Type | Nullable | Key | Description |
|--------|------|----------|-----|-------------|
| `symbol` | VARCHAR | NO | PK | Trading pair |
| `timestamp` | TIMESTAMP | NO | PK | Funding payment time |
| `funding_rate` | DOUBLE | YES | — | Funding rate |
| `funding_rate_interval_hours` | INTEGER | YES | — | Interval (default: 8) |

**Primary Key:** `(symbol, timestamp)`

### Table: `open_interest_live` / `open_interest_demo`

| Column | Type | Nullable | Key | Description |
|--------|------|----------|-----|-------------|
| `symbol` | VARCHAR | NO | PK | Trading pair |
| `timestamp` | TIMESTAMP | NO | PK | Snapshot time |
| `open_interest` | DOUBLE | YES | — | Open interest value |

**Primary Key:** `(symbol, timestamp)`

### Metadata Tables

| Table | Purpose |
|-------|---------|
| `sync_metadata_live` | Sync state tracking |
| `funding_metadata_live` | Funding sync metadata |
| `open_interest_metadata_live` | OI sync metadata |
| `data_extremes_live` | Min/max timestamps per symbol/tf |

---

## Current Data Inventory (as of December 2025)

### OHLCV Data

| Symbol | Timeframe | Row Count | Date Range |
|--------|-----------|-----------|------------|
| BTCUSDT | 15m | 105,570 | 2022-12-11 → 2025-12-14 |
| BTCUSDT | 1h | 26,393 | 2022-12-11 → 2025-12-14 |
| BTCUSDT | 4h | 6,599 | 2022-12-11 → 2025-12-14 |
| BTCUSDT | 1d | 371 | 2024-12-09 → 2025-12-14 |
| BTCUSDT | 5m | 12,673 | 2024-10-31 → 2024-12-14 |
| ETHUSDT | 15m | 105,571 | 2022-12-11 → 2025-12-14 |
| ETHUSDT | 1h | 26,393 | 2022-12-11 → 2025-12-14 |
| ETHUSDT | 4h | 6,599 | 2022-12-11 → 2025-12-14 |
| SOLUSDT | 15m | 105,571 | 2022-12-11 → 2025-12-14 |
| SOLUSDT | 1h | 26,393 | 2022-12-11 → 2025-12-14 |
| SOLUSDT | 1m | 129,600 | 2025-09-13 → 2025-12-12 |
| XRPUSDT | 1m | 525,600 | 2024-12-09 → 2025-12-09 |
| XRPUSDT | 15m | 35,040 | 2024-12-09 → 2025-12-09 |

**Total OHLCV rows:** 1,341,343

### Funding Rates

| Symbol | Row Count |
|--------|-----------|
| BTCUSDT | 199 |
| ETHUSDT | 199 |
| SOLUSDT | 1,135 |
| XRPUSDT | 1,095 |

---

## Data Quality Checks (Audit Results)

| Check | Status | Description |
|-------|--------|-------------|
| OHLC Sanity | PASS | high >= low for all rows (0 violations) |
| Non-negative Volume | PASS | volume >= 0 for all rows (0 violations) |
| No NULL in OHLCV | PASS | All open/high/low/close/volume populated |
| No Duplicates | PASS | PK enforced, 0 duplicates |
| No Gaps (BTCUSDT 1h) | PASS | Continuous timestamps |

### Checks Run

```sql
-- 1. OHLC Sanity
SELECT COUNT(*) FROM ohlcv_live WHERE high < low;  -- Result: 0

-- 2. Non-negative volume
SELECT COUNT(*) FROM ohlcv_live WHERE volume < 0;  -- Result: 0

-- 3. NULL checks
SELECT COUNT(*) FROM ohlcv_live WHERE open IS NULL;   -- Result: 0
SELECT COUNT(*) FROM ohlcv_live WHERE high IS NULL;   -- Result: 0
SELECT COUNT(*) FROM ohlcv_live WHERE low IS NULL;    -- Result: 0
SELECT COUNT(*) FROM ohlcv_live WHERE close IS NULL;  -- Result: 0
SELECT COUNT(*) FROM ohlcv_live WHERE volume IS NULL; -- Result: 0

-- 4. Duplicate check
SELECT COUNT(*) - COUNT(DISTINCT (symbol, timeframe, timestamp)) FROM ohlcv_live;  -- Result: 0

-- 5. Gap check (sample)
WITH ordered AS (
    SELECT timestamp, LAG(timestamp) OVER (ORDER BY timestamp) as prev_ts
    FROM ohlcv_live WHERE symbol = 'BTCUSDT' AND timeframe = '1h'
)
SELECT COUNT(*) FROM ordered WHERE timestamp - prev_ts > INTERVAL 1 HOUR;  -- Result: 0
```

---

## Time Semantics

| Field | Meaning |
|-------|---------|
| `timestamp` (in DuckDB) | Bar open time (ts_open) |
| `Bar.ts_open` | Bar open time — fills occur here |
| `Bar.ts_close` | Bar close time = ts_open + TF duration |

**Invariant:** `ts_close = ts_open + timeframe_duration`

**Closed-candle rule:** Indicators computed only on closed candles. Current (partial) bar excluded from computation.

---

## Data Flow

```
Bybit LIVE API (api.bybit.com)
    ↓
HistoricalDataStore.sync() / sync_range_tool()
    ↓
DuckDB (INSERT OR REPLACE into ohlcv_live)
    ↓
HistoricalDataStore.get_ohlcv_df()
    ↓
FeatureFrameBuilder (prep phase, outside hot loop)
    ↓
FeedStore (numpy arrays)
    ↓
RuntimeSnapshotView (hot loop, O(1) access)
```

---

## Lineage & Mutation

### Writers

| Operation | Function | Behavior |
|-----------|----------|----------|
| Sync OHLCV | `sync_ohlcv()` | INSERT OR REPLACE |
| Sync Funding | `sync_funding_rates()` | INSERT OR REPLACE |
| Sync OI | `sync_open_interest()` | INSERT OR REPLACE |
| Fill Gaps | `fill_gaps()` | INSERT missing bars |
| Delete All | `delete_all_data()` | TRUNCATE tables |

### Mutation Rules

1. **Append-only semantic:** New data inserted, old data not modified
2. **Upsert on conflict:** INSERT OR REPLACE handles re-syncs
3. **No versioning:** Latest data replaces previous
4. **Deterministic:** Same sync range → same data

### Reproducibility

- Historical data is deterministic once synced
- Re-syncing same range produces identical results
- No external state dependencies during backtest

---

## CLI Commands

```bash
# Sync OHLCV for specific range
python trade_cli.py  # → Data Builder → Sync OHLCV

# Fill gaps
python trade_cli.py  # → Data Builder → Fill Gaps

# Heal data
python trade_cli.py  # → Data Builder → Heal Data

# Vacuum/cleanup
python trade_cli.py  # → Data Builder → Vacuum

# Query extremes
python trade_cli.py  # → Data Builder → Query Extremes

# Full sync test
python trade_cli.py --smoke data_extensive
```

---

## Warmup Coverage

Warmup data ensures indicators have sufficient lookback before simulation starts.

**Warmup calculation:**
```
warmup_bars = max(indicator_lookback) * warmup_multiplier
load_start = sim_start - (warmup_bars * tf_duration)
```

**Default warmup_multiplier:** 2x (configurable in Play)

**Preflight check:** `backtest preflight` validates warmup coverage before run.

---

## MTF Join Feasibility

Multi-timeframe backtests require aligned data across TFs:

| Exec TF | HTF | MTF | Alignment Check |
|---------|-----|-----|-----------------|
| 15m | 4h | 1h | Feasible if all TF data present |
| 5m | 1h | 15m | Feasible |
| 1m | 15m | 5m | Requires dense 1m data |

**MTF alignment rules:**
1. HTF/MTF indices update only on TF close
2. Forward-fill between closes
3. ts_close alignment validated at engine init

---

## Readiness Verdict

| Stage | Status | Blockers |
|-------|--------|----------|
| Backtest | GREEN | None |
| Sim Validation | GREEN | None |
| Demo Trading | GREEN | None (uses live data) |
| Live Trading | GREEN | None |

**Overall:** Data module is production-ready for all stages.

---

## Known Gaps

| Gap | Severity | Notes |
|-----|----------|-------|
| BTCUSDT 1d limited history | P3 | Only 371 rows (starts 2024-12) |
| Some symbols missing 1m data | P3 | Not all symbols have 1m TF |

**Note:** These are not blockers; they affect only specific backtest configurations.

---

