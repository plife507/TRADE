# TRADE Bot — Data Pull Structure & Data Tools Review

**Last Updated:** December 12, 2025

## Executive Summary

This document provides a comprehensive review of the TRADE bot's data pull architecture and all available data management tools. The system uses DuckDB for columnar storage of historical market data, with environment-aware separation between live and demo data.

---

## 1. Data Pull Architecture

### 1.1 Core Components

The data pull system consists of three main layers:

1. **Data Source Layer** (`src/data/market_data.py`)
   - Live market data fetching via Bybit API
   - Hybrid WebSocket/REST support
   - Aggressive caching (1-5 second TTLs)
   - Environment-aware (live/demo)

2. **Historical Storage Layer** (`src/data/historical_data_store.py`)
   - DuckDB-backed columnar storage
   - Environment-specific databases and tables
   - Automatic schema management
   - Gap detection and filling

3. **Sync Operations Layer** (`src/data/historical_sync.py`)
   - Batch fetching from Bybit API
   - Incremental sync (forward-only)
   - Full range sync
   - Progress tracking and cancellation

### 1.2 Data Flow

```
Bybit LIVE API (api.bybit.com)
    ↓
HistoricalDataStore.sync()
    ↓
Fetch in batches (1000 candles/request)
    ↓
Store in DuckDB (INSERT OR REPLACE)
    ↓
Update metadata tables
    ↓
Query via get_ohlcv() / get_funding() / get_open_interest()
```

### 1.3 Environment Separation

**CRITICAL**: The system maintains strict separation between live and demo data:

| Environment | Database File | API Endpoint | Purpose |
|-------------|---------------|--------------|---------|
| **live** | `data/market_data_live.duckdb` | `api.bybit.com` | Canonical backtest data |
| **demo** | `data/market_data_demo.duckdb` | `api-demo.bybit.com` | Demo testing sessions |

- Each environment has its own DuckDB file
- Table names are env-specific (e.g., `ohlcv_live`, `ohlcv_demo`)
- API credentials are separate (`BYBIT_LIVE_DATA_API_KEY` vs `BYBIT_DEMO_DATA_API_KEY`)
- No cross-contamination between environments

### 1.4 Data Types Stored

#### A. OHLCV Candlestick Data
- **Source**: Bybit V5 `/v5/market/kline`
- **Timeframes**: `1m`, `5m`, `15m`, `1h`, `4h`, `1d`
- **Fields**: `timestamp`, `open`, `high`, `low`, `close`, `volume`, `turnover`
- **Storage**: Primary table with composite primary key `(symbol, timeframe, timestamp)`
- **Metadata**: Tracks first/last timestamp, candle count, last sync time per symbol/timeframe

#### B. Funding Rates
- **Source**: Bybit V5 `/v5/market/funding/history`
- **Update Frequency**: Every 8 hours (00:00, 08:00, 16:00 UTC)
- **Fields**: `symbol`, `timestamp`, `funding_rate`, `funding_rate_interval_hours`
- **Use Case**: Factor funding costs into backtests

#### C. Open Interest (OI)
- **Source**: Bybit V5 `/v5/market/open-interest`
- **Intervals**: `5min`, `15min`, `30min`, `1h`, `4h`, `1d`
- **Fields**: `symbol`, `timestamp`, `open_interest`
- **Use Case**: Market sentiment analysis, liquidity assessment

### 1.5 Sync Mechanisms

#### Full Sync (`sync()`)
- Syncs data for a period (e.g., "1M", "3M", "1Y")
- Fetches from `now - period` to `now`
- Can sync multiple symbols and timeframes
- Returns per-symbol/timeframe candle counts

#### Range Sync (`sync_range()`)
- Syncs specific date range
- Useful for backfilling gaps or specific windows
- More precise than period-based sync

#### Forward Sync (`sync_forward()`)
- Lightweight: only fetches new data after last stored timestamp
- No backfill of older history
- Fast for keeping data current
- Returns 0 if already current

#### Gap Fill (`fill_gaps()`)
- Auto-detects missing candles in stored data
- Scans for gaps > 1.5x expected interval
- Fetches missing data from API
- Returns per-symbol/timeframe fill counts

---

## 2. Data Tools Overview

All data tools are located in `src/tools/data_tools.py` and registered in `src/tools/tool_registry.py`. Tools follow a consistent pattern:

- Return `ToolResult` objects with `success`, `message`, `data`, `error` fields
- Support `env` parameter (defaults to "live")
- Accept time ranges via `period` OR `start`/`end` parameters
- Validate inputs and provide clear error messages

### 2.1 Tool Categories

Tools are organized into logical categories:

1. **Info Tools** (`data.info`) - Query database state
2. **Sync Tools** (`data.sync`) - Pull data from exchange
3. **Query Tools** (`data.query`) - Retrieve stored data
4. **Maintenance Tools** (`data.maintenance`) - Database health and cleanup

---

## 3. Info Tools

### 3.1 `get_database_stats`

**Purpose**: Get comprehensive database statistics

**Parameters**:
- `env` (optional): "live" or "demo", defaults to "live"

**Returns**:
- Overall stats: file size, symbol counts, total records
- Per-symbol OHLCV breakdown with timeframes and candle counts
- Per-symbol funding rates breakdown
- Per-symbol open interest breakdown

**Example Output**:
```
[LIVE] Database: 45.2 MB
OHLCV: 5 symbols, 15 combinations, 1,234,567 candles
Funding: 5 symbols, 12,345 records
Open Interest: 5 symbols, 8,901 records
```

**Use Case**: Quick health check, understanding data coverage

---

### 3.2 `list_cached_symbols`

**Purpose**: List all symbols with their data summary

**Parameters**:
- `env` (optional): "live" or "demo", defaults to "live"

**Returns**:
- List of symbols with:
  - Timeframe list (e.g., "1m, 5m, 15m, 1h, 4h")
  - Total candles across all timeframes
  - Date range (earliest to latest)

**Example Output**:
```
[LIVE] Found 5 cached symbols
Symbol: BTCUSDT
  Timeframes: 1m, 5m, 15m, 1h, 4h, 1d
  Candles: 234,567
  From: 2024-01-01
  To: 2024-12-12
```

**Use Case**: See what symbols are available, check data freshness

---

### 3.3 `get_symbol_status`

**Purpose**: Get per-symbol aggregate status (aggregated across timeframes)

**Parameters**:
- `symbol` (optional): Specific symbol or None for all
- `env` (optional): "live" or "demo", defaults to "live"

**Returns**:
- Per-symbol summary:
  - List of timeframes
  - Total candles (sum across all timeframes)
  - Total gaps
  - Validity flag

**Use Case**: Quick per-symbol health check

---

### 3.4 `get_symbol_summary`

**Purpose**: High-level summary of all cached symbols

**Parameters**:
- `env` (optional): "live" or "demo", defaults to "live"

**Returns**:
- One row per symbol with:
  - Timeframe count
  - Total candles
  - Date range

**Use Case**: Quick overview without per-timeframe details

---

### 3.5 `get_symbol_timeframe_ranges`

**Purpose**: Detailed per-symbol/timeframe breakdown

**Parameters**:
- `symbol` (optional): Specific symbol or None for all
- `env` (optional): "live" or "demo", defaults to "live"

**Returns**:
- Flat list of rows with:
  - `symbol`, `timeframe`
  - `first_timestamp`, `last_timestamp`
  - `candle_count`, `gaps`, `is_current`

**Use Case**: Detailed inspection, finding gaps, checking freshness per timeframe

**Example Output**:
```
Found 15 symbol/timeframe combinations across 5 symbol(s)
Symbol: BTCUSDT, Timeframe: 1h
  First: 2024-01-01T00:00:00
  Last: 2024-12-12T23:00:00
  Candles: 8,760
  Gaps: 0
  Current: True
```

---

## 4. Sync Tools

### 4.1 `sync_symbols`

**Purpose**: Sync OHLCV data for symbols by period

**Parameters**:
- `symbols` (required): List of symbols to sync
- `period` (optional): "1D", "1W", "1M", "3M", "6M", "1Y", defaults to "1M"
- `timeframes` (optional): List of timeframes or None for all
- `progress_callback` (optional): Callback for progress updates
- `env` (optional): "live" or "demo", defaults to "live"

**Returns**:
- Per-symbol/timeframe sync counts
- Total candles synced
- Cancellation status

**Use Case**: Initial data pull, refreshing historical data

**Example**:
```python
result = sync_symbols_tool(
    symbols=["BTCUSDT", "ETHUSDT"],
    period="3M",
    timeframes=["15m", "1h", "4h"],
    env="live"
)
# Returns: {total_synced: 45,678, results: {"BTCUSDT_15m": 10,234, ...}}
```

---

### 4.2 `sync_range`

**Purpose**: Sync OHLCV data for a specific date range

**Parameters**:
- `symbols` (required): List of symbols to sync
- `start` (required): Start datetime
- `end` (required): End datetime
- `timeframes` (optional): List of timeframes or None for all
- `env` (optional): "live" or "demo", defaults to "live"

**Returns**:
- Per-symbol/timeframe sync counts
- Total candles synced

**Use Case**: Backfilling specific date ranges, syncing test windows

**Example**:
```python
result = sync_range_tool(
    symbols=["BTCUSDT"],
    start=datetime(2024, 1, 1),
    end=datetime(2024, 6, 1),
    timeframes=["1h"],
    env="live"
)
```

---

### 4.3 `sync_funding`

**Purpose**: Sync funding rate history for symbols

**Parameters**:
- `symbols` (required): List of symbols to sync
- `period` (optional): "1M", "3M", "6M", "1Y", defaults to "3M"
- `progress_callback` (optional): Callback for progress updates
- `env` (optional): "live" or "demo", defaults to "live"

**Returns**:
- Per-symbol funding record counts
- Total records synced

**Use Case**: Building funding rate history for backtests

---

### 4.4 `sync_open_interest`

**Purpose**: Sync open interest history for symbols

**Parameters**:
- `symbols` (required): List of symbols to sync
- `period` (optional): "1D", "1W", "1M", "3M", defaults to "1M"
- `interval` (optional): "5min", "15min", "30min", "1h", "4h", "1d", defaults to "1h"
- `progress_callback` (optional): Callback for progress updates
- `env` (optional): "live" or "demo", defaults to "live"

**Returns**:
- Per-symbol OI record counts
- Total records synced

**Use Case**: Building open interest history for sentiment analysis

---

### 4.5 `sync_to_now`

**Purpose**: Sync data forward from last stored candle to now (no backfill)

**Parameters**:
- `symbols` (required): List of symbols to sync forward
- `timeframes` (optional): List of timeframes or None for all
- `env` (optional): "live" or "demo", defaults to "live"

**Returns**:
- Per-symbol/timeframe counts
- Total new candles synced
- Count of already-current combinations

**Use Case**: Daily/weekly updates to keep data current

**Example**:
```python
result = sync_to_now_tool(
    symbols=["BTCUSDT", "ETHUSDT"],
    timeframes=["15m", "1h", "4h"],
    env="live"
)
# Returns: {total_synced: 1,234, already_current: 2}
```

---

### 4.6 `sync_to_now_and_fill_gaps`

**Purpose**: Sync forward to now AND fill any gaps in existing data

**Parameters**:
- `symbols` (required): List of symbols to sync and heal
- `timeframes` (optional): List of timeframes or None for all
- `env` (optional): "live" or "demo", defaults to "live"

**Returns**:
- Combined summary:
  - `sync_forward`: New candles synced
  - `gap_fill`: Gap candles filled
  - `total_records`: Sum of both

**Use Case**: Comprehensive data maintenance, ensuring data is both current and complete

**Example**:
```python
result = sync_to_now_and_fill_gaps_tool(
    symbols=["BTCUSDT"],
    timeframes=["1h"],
    env="live"
)
# Returns: {
#   sync_forward: {total_synced: 168},
#   gap_fill: {total_filled: 12},
#   total_records: 180
# }
```

---

### 4.7 `build_symbol_history`

**Purpose**: Build complete historical data (OHLCV + funding + open interest)

**Parameters**:
- `symbols` (required): List of symbols to build history for
- `period` (optional): "1D", "1W", "1M", "3M", "6M", "1Y", defaults to "1M"
- `timeframes` (optional): List of OHLCV timeframes or None for all
- `oi_interval` (optional): Open interest interval, defaults to "1h"
- `env` (optional): "live" or "demo", defaults to "live"

**Returns**:
- Combined summary for all data types:
  - `ohlcv`: OHLCV sync results
  - `funding`: Funding rate sync results
  - `open_interest`: Open interest sync results
  - `total_records`: Sum across all types

**Use Case**: One-stop shop for fully populating data for new symbols

**Example**:
```python
result = build_symbol_history_tool(
    symbols=["SOLUSDT"],
    period="6M",
    timeframes=["15m", "1h", "4h"],
    oi_interval="1h",
    env="live"
)
# Returns: {
#   ohlcv: {total_synced: 45,678},
#   funding: {total_synced: 540},
#   open_interest: {total_synced: 4,380},
#   total_records: 50,598
# }
```

---

## 5. Query Tools

### 5.1 `get_ohlcv_history`

**Purpose**: Get OHLCV candlestick history from DuckDB

**Parameters**:
- `symbol` (required): Trading symbol
- `timeframe` (optional): "1m", "5m", "15m", "1h", "4h", "1d", defaults to "1h"
- `period` (optional): Relative period (e.g., "1M", "3M") - alternative to start/end
- `start` (optional): Start datetime or ISO string (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
- `end` (optional): End datetime or ISO string
- `limit` (optional): Maximum number of candles to return
- `env` (optional): "live" or "demo", defaults to "live"

**Returns**:
- `candles`: List of `{timestamp, open, high, low, close, volume, turnover}` dicts
- `count`: Number of candles
- `timeframe`: The queried timeframe
- `time_range`: Metadata about queried range

**Time Range Rules**:
- Use either `period` OR `start`/`end` (not both)
- Maximum range: 365 days when using `start`/`end`
- `start`/`end` can be datetime objects or ISO strings

**Use Case**: Retrieving historical price data for backtesting or analysis

**Example**:
```python
# Using period
result = get_ohlcv_history_tool(
    symbol="BTCUSDT",
    timeframe="1h",
    period="1M",
    env="live"
)

# Using explicit range
result = get_ohlcv_history_tool(
    symbol="BTCUSDT",
    timeframe="1h",
    start="2024-01-01",
    end="2024-06-01",
    limit=1000,
    env="live"
)
```

---

### 5.2 `get_funding_history`

**Purpose**: Get funding rate history from DuckDB

**Parameters**:
- `symbol` (required): Trading symbol
- `period` (optional): Relative period (e.g., "1M", "3M") - alternative to start/end
- `start` (optional): Start datetime or ISO string
- `end` (optional): End datetime or ISO string
- `env` (optional): "live" or "demo", defaults to "live"

**Returns**:
- `records`: List of `{timestamp, funding_rate}` dicts
- `count`: Number of records
- `time_range`: Metadata about queried range

**Time Range Rules**:
- Use either `period` OR `start`/`end` (not both)
- Maximum range: 365 days when using `start`/`end`

**Use Case**: Analyzing funding costs, backtesting with funding fees

---

### 5.3 `get_open_interest_history`

**Purpose**: Get open interest history from DuckDB

**Parameters**:
- `symbol` (required): Trading symbol
- `period` (optional): Relative period (e.g., "1M", "3M") - alternative to start/end
- `start` (optional): Start datetime or ISO string
- `end` (optional): End datetime or ISO string
- `env` (optional): "live" or "demo", defaults to "live"

**Returns**:
- `records`: List of `{timestamp, open_interest}` dicts
- `count`: Number of records
- `time_range`: Metadata about queried range

**Time Range Rules**:
- Use either `period` OR `start`/`end` (not both)
- Maximum range: 365 days when using `start`/`end`

**Use Case**: Market sentiment analysis, liquidity assessment

---

## 6. Maintenance Tools

### 6.1 `fill_gaps`

**Purpose**: Auto-detect and fill gaps in cached data

**Parameters**:
- `symbol` (optional): Specific symbol or None for all
- `timeframe` (optional): Specific timeframe or None for all
- `progress_callback` (optional): Callback for progress updates
- `env` (optional): "live" or "demo", defaults to "live"

**Returns**:
- Per-symbol/timeframe gap fill counts
- Total candles filled

**Gap Detection**:
- Scans for missing candles where interval > 1.5x expected
- Fetches missing data from API
- Updates metadata after filling

**Use Case**: Repairing incomplete data, ensuring data continuity

---

### 6.2 `heal_data`

**Purpose**: Run comprehensive data integrity check and repair

**Parameters**:
- `symbol` (optional): Specific symbol or None for all
- `fix_issues` (optional): Auto-fix issues, defaults to True
- `fill_gaps_after` (optional): Fill gaps after fixing, defaults to True
- `env` (optional): "live" or "demo", defaults to "live"

**Checks Performed**:
- Duplicate timestamps
- Invalid OHLCV (high < low, open/close outside range)
- Negative/zero volumes
- NULL values in critical columns
- Symbol casing inconsistencies
- Time gaps

**Returns**:
- `report`: Detailed heal report with:
  - `issues_found`: Total issues detected
  - `issues_fixed`: Issues successfully fixed
  - Per-issue-type breakdowns

**Use Case**: Comprehensive data health check, fixing data corruption

---

### 6.3 `delete_symbol`

**Purpose**: Delete all data for a symbol

**Parameters**:
- `symbol` (required): Symbol to delete
- `vacuum` (optional): Whether to vacuum after deletion, defaults to True
- `env` (optional): "live" or "demo", defaults to "live"

**Returns**:
- `deleted_count`: Number of candles deleted
- `vacuumed`: Whether vacuum was performed

**Use Case**: Removing unwanted symbols, cleaning up test data

**WARNING**: This permanently deletes all OHLCV, funding, and OI data for the symbol.

---

### 6.4 `cleanup_empty_symbols`

**Purpose**: Remove symbols with no data (invalid symbols)

**Parameters**:
- `env` (optional): "live" or "demo", defaults to "live"

**Returns**:
- `cleaned_symbols`: List of removed symbols
- `count`: Number of symbols cleaned

**Use Case**: Removing symbols that failed to sync or were invalid

---

### 6.5 `vacuum_database`

**Purpose**: Vacuum the database to reclaim space

**Parameters**:
- `env` (optional): "live" or "demo", defaults to "live"

**Returns**:
- `vacuumed`: Confirmation flag

**Use Case**: Reclaiming disk space after deletions, optimizing database performance

**Note**: Vacuuming can take time on large databases. Consider running during off-hours.

---

### 6.6 `delete_all_data`

**Purpose**: Delete ALL data from the database (OHLCV, funding, OI)

**Parameters**:
- `vacuum` (optional): Whether to vacuum after deletion, defaults to True
- `env` (optional): "live" or "demo", defaults to "live"

**Returns**:
- Per-table deletion counts:
  - `ohlcv`: OHLCV candles deleted
  - `sync_metadata`: Metadata records deleted
  - `funding`: Funding records deleted
  - `funding_metadata`: Funding metadata deleted
  - `open_interest`: OI records deleted
  - `oi_metadata`: OI metadata deleted
- `total_deleted`: Sum of all deletions

**WARNING**: This is **DESTRUCTIVE** and **CANNOT BE UNDONE**. Only affects historical market data in DuckDB, not trading positions or balances.

**Use Case**: Complete database reset, starting fresh

---

## 7. Tool Usage Patterns

### 7.1 Initial Data Setup

```python
# 1. Build complete history for new symbols
result = build_symbol_history_tool(
    symbols=["BTCUSDT", "ETHUSDT"],
    period="6M",
    timeframes=["15m", "1h", "4h"],
    env="live"
)

# 2. Verify data was synced
stats = get_database_stats_tool(env="live")
ranges = get_symbol_timeframe_ranges_tool(env="live")
```

### 7.2 Daily Data Updates

```python
# Sync forward to keep data current
result = sync_to_now_tool(
    symbols=["BTCUSDT", "ETHUSDT"],
    timeframes=["15m", "1h", "4h"],
    env="live"
)
```

### 7.3 Data Health Check

```python
# 1. Check overall stats
stats = get_database_stats_tool(env="live")

# 2. Check for gaps
ranges = get_symbol_timeframe_ranges_tool(env="live")
# Look for rows with gaps > 0

# 3. Heal data if needed
heal_result = heal_data_tool(
    fix_issues=True,
    fill_gaps_after=True,
    env="live"
)
```

### 7.4 Querying Data for Backtesting

```python
# Get OHLCV data for backtest window
ohlcv = get_ohlcv_history_tool(
    symbol="BTCUSDT",
    timeframe="1h",
    start="2024-01-01",
    end="2024-06-01",
    env="live"
)

# Get funding rates for same period
funding = get_funding_history_tool(
    symbol="BTCUSDT",
    start="2024-01-01",
    end="2024-06-01",
    env="live"
)
```

### 7.5 Comprehensive Maintenance

```python
# 1. Sync forward and fill gaps
result = sync_to_now_and_fill_gaps_tool(
    symbols=["BTCUSDT", "ETHUSDT"],
    timeframes=["15m", "1h", "4h"],
    env="live"
)

# 2. Heal any remaining issues
heal_result = heal_data_tool(
    fix_issues=True,
    fill_gaps_after=True,
    env="live"
)

# 3. Vacuum to reclaim space
vacuum_result = vacuum_database_tool(env="live")
```

---

## 8. Implementation Details

### 8.1 Time Range Normalization

All query tools use `_normalize_time_range_params()` helper which:
- Accepts datetime objects or ISO strings
- Supports multiple ISO formats:
  - `YYYY-MM-DD`
  - `YYYY-MM-DDTHH:MM:SS`
  - `YYYY-MM-DD HH:MM:SS`
- Validates range (start < end, max 365 days)
- Returns normalized datetimes or error message

### 8.2 Period Parsing

Period strings are parsed using `HistoricalDataStore.parse_period()`:
- Format: `{number}{unit}` (e.g., "1M", "3M", "6M", "1Y")
- Units: `Y` (years), `M` (months), `W` (weeks), `D` (days), `H` (hours)
- Months = 30 days, Years = 365 days
- Returns `timedelta` object

### 8.3 Environment Resolution

All tools default to `DEFAULT_DATA_ENV` ("live") but accept `env` parameter:
- `env="live"`: Uses `market_data_live.duckdb` and LIVE API
- `env="demo"`: Uses `market_data_demo.duckdb` and DEMO API
- Environment is validated via `validate_data_env()`

### 8.4 Error Handling

All tools return `ToolResult` objects:
- `success`: Boolean indicating success/failure
- `message`: Human-readable message
- `data`: Structured data (dict/list)
- `error`: Error message if `success=False`
- `source`: Always "duckdb" for data tools

### 8.5 Progress Tracking

Sync tools support optional `progress_callback`:
- Signature: `callback(symbol: str, timeframe: str, message: str)`
- Called for each symbol/timeframe combination
- Useful for CLI progress displays

---

## 9. Performance Considerations

### 9.1 Batch Fetching

- API fetches 1000 candles per request
- Multiple requests batched automatically
- Rate limiting handled by `BybitClient`

### 9.2 Database Indexes

Indexes created automatically:
- `(symbol, timeframe)` on OHLCV table
- `timestamp` on OHLCV, funding, OI tables
- Speeds up queries and gap detection

### 9.3 WAL Management

- DuckDB uses Write-Ahead Log (WAL)
- WAL can grow large if not periodically committed
- Large WAL can cause freezing
- **Recommendation**: Run `vacuum_database` periodically

### 9.4 Query Optimization

- Use `limit` parameter when querying large ranges
- Prefer `period` over `start`/`end` for relative queries
- Query specific timeframes rather than all timeframes

---

## 10. Best Practices

### 10.1 Data Setup

1. Use `build_symbol_history_tool()` for initial setup
2. Verify with `get_symbol_timeframe_ranges_tool()`
3. Check for gaps and heal if needed

### 10.2 Regular Maintenance

1. Run `sync_to_now_tool()` daily/weekly
2. Periodically run `heal_data_tool()` to check integrity
3. Run `vacuum_database_tool()` after deletions or monthly

### 10.3 Querying

1. Use `period` for relative queries (e.g., "1M")
2. Use `start`/`end` for specific date ranges
3. Always specify `timeframe` when querying OHLCV
4. Use `limit` to cap large result sets

### 10.4 Environment Management

1. Use `env="live"` for backtesting (canonical data)
2. Use `env="demo"` for demo testing sessions
3. Never mix environments in the same operation

---

## 11. Common Issues & Solutions

### 11.1 "No data cached" Errors

**Problem**: Query returns empty results

**Solutions**:
1. Check if data exists: `list_cached_symbols_tool()`
2. Sync data: `sync_symbols_tool()` or `build_symbol_history_tool()`
3. Verify symbol/timeframe: `get_symbol_timeframe_ranges_tool()`

### 11.2 Gaps in Data

**Problem**: Missing candles in time series

**Solutions**:
1. Detect gaps: `get_symbol_timeframe_ranges_tool()` (check `gaps` field)
2. Fill gaps: `fill_gaps_tool()`
3. Or use: `sync_to_now_and_fill_gaps_tool()`

### 11.3 Database Size Growth

**Problem**: Database file growing too large

**Solutions**:
1. Delete unused symbols: `delete_symbol_tool()`
2. Vacuum: `vacuum_database_tool()`
3. Archive old data (manual process, not yet automated)

### 11.4 Slow Queries

**Problem**: Querying large date ranges is slow

**Solutions**:
1. Use `limit` parameter
2. Query specific timeframes
3. Ensure indexes exist (automatic, but check if missing)
4. Vacuum database to optimize

---

## 12. Tool Registry Integration

All data tools are registered in `ToolRegistry` with categories:

- `data.info.*`: Info tools
- `data.sync.*`: Sync tools
- `data.query.*`: Query tools
- `data.maintenance.*`: Maintenance tools

**Usage via Registry**:
```python
from src.tools.tool_registry import get_registry

registry = get_registry()

# List all data tools
tools = registry.list_tools(category="data")

# Get tool info
info = registry.get_tool_info("sync_symbols")

# Execute tool
result = registry.execute(
    "sync_symbols",
    symbols=["BTCUSDT"],
    period="1M",
    env="live"
)
```

---

## 13. Summary

### Data Pull Structure

- **Source**: Bybit LIVE API (for live env) or DEMO API (for demo env)
- **Storage**: DuckDB columnar database (separate files per environment)
- **Data Types**: OHLCV, funding rates, open interest
- **Sync Modes**: Full sync, range sync, forward sync, gap fill

### Data Tools

- **25 total tools** organized into 4 categories
- **Info Tools**: 5 tools for querying database state
- **Sync Tools**: 7 tools for pulling data from exchange
- **Query Tools**: 3 tools for retrieving stored data
- **Maintenance Tools**: 6 tools for database health and cleanup

### Key Features

- Environment-aware (live/demo separation)
- Time range flexibility (period or explicit dates)
- Comprehensive error handling
- Progress tracking support
- Gap detection and filling
- Data integrity checks

---

## 14. Future Enhancements

Potential improvements for consideration:

1. **Incremental Sync Optimization**: Track last sync per symbol/timeframe to avoid redundant fetches
2. **Data Archiving**: Automatic archiving of old data to reduce database size
3. **Compression**: Enable DuckDB compression for better storage efficiency
4. **Parallel Sync**: Sync multiple symbols/timeframes in parallel
5. **Data Validation**: Pre-sync validation to catch API errors early
6. **Metrics Export**: Export database stats to monitoring systems
7. **Backup/Restore**: Tools for backing up and restoring databases

---

**End of Document**

