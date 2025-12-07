# TRADE Bot - Data Architecture & Backtesting Guide

## Executive Summary

This document provides a comprehensive overview of the data architecture for the TRADE trading bot, including:
- **Live Data Sources**: What data we pull from Bybit's live API
- **Historical Storage**: What data is stored in DuckDB for backtesting
- **Data Flow**: How data moves from API → Storage → Backtesting
- **DuckDB Performance Issues**: Solutions for terminal freezing and optimization strategies

---

## 1. Live Data Sources (Bybit API)

### 1.1 API Environment

**CRITICAL**: All data operations use **Bybit LIVE API** (`api.bybit.com`) regardless of trading mode.

| Operation Type | API Used | Reason |
|----------------|----------|--------|
| Historical data sync | **LIVE** | Accurate market data |
| Market data (prices, tickers) | **LIVE** | Real market prices |
| Data capture | **LIVE** | Accurate data collection |
| Trading (orders, positions) | **DEMO or LIVE** | Depends on `BYBIT_USE_DEMO` |

**Why LIVE for data?** Demo API may return different or incomplete historical data. For accurate backtesting and analysis, we always use the live API for data operations.

### 1.2 Data Types Pulled from Bybit

#### A. OHLCV Candlestick Data

**Source**: Bybit V5 Public API - `/v5/market/kline`

**Data Retrieved**:
- **Open, High, Low, Close** prices (OHLC)
- **Volume** (trading volume for the candle period)
- **Timestamp** (candle start time in UTC)

**Supported Timeframes**:
- `1m` (1 minute)
- `5m` (5 minutes)
- `15m` (15 minutes)
- `1h` (1 hour)
- `4h` (4 hours)
- `1d` (1 day)

**API Limits**:
- Max 1000 candles per request
- Rate limit: 120 requests/second (public endpoints)
- Data available: Up to ~2 years of history (varies by symbol)

**Use Cases**:
- Live trading: Current price, recent candles for indicators
- Backtesting: Historical price action, strategy simulation
- Analysis: Chart patterns, technical indicators

#### B. Funding Rates

**Source**: Bybit V5 Public API - `/v5/market/funding/history`

**Data Retrieved**:
- **Funding Rate** (percentage, typically -0.01% to 0.01%)
- **Timestamp** (funding payment time)
- **Funding Rate Interval** (typically 8 hours for perpetuals)

**Update Frequency**: Every 8 hours (00:00, 08:00, 16:00 UTC)

**Use Cases**:
- Backtesting: Factor in funding costs for long-term positions
- Strategy optimization: Avoid high funding rate periods
- Risk management: Calculate total cost of holding positions

#### C. Open Interest (OI)

**Source**: Bybit V5 Public API - `/v5/market/open-interest`

**Data Retrieved**:
- **Open Interest** (total number of outstanding contracts)
- **Timestamp** (snapshot time)

**Supported Intervals**:
- `5min`, `15min`, `30min`, `1h`, `4h`, `1d`

**Use Cases**:
- Backtesting: Market sentiment analysis, liquidity assessment
- Strategy signals: OI changes can indicate trend strength
- Risk management: High OI = high liquidity, easier to exit

#### D. Ticker Data (Live Only)

**Source**: Bybit V5 Public API - `/v5/market/tickers` or WebSocket

**Data Retrieved**:
- Last traded price
- Bid/Ask prices
- 24h high/low
- 24h volume/turnover
- Price change percentage
- Mark price
- Funding rate (current)
- Open interest (current)

**Update Frequency**: Real-time via WebSocket, or cached REST (1-5 seconds)

**Use Cases**:
- Live trading: Current prices for order execution
- Real-time monitoring: Position PnL, market conditions
- **NOT stored in DuckDB** (only current snapshot)

#### E. Order Book (Live Only)

**Source**: Bybit V5 WebSocket Public Stream

**Data Retrieved**:
- Bid/Ask levels with quantities
- Best bid/ask prices

**Use Cases**:
- Live trading: Order placement, slippage estimation
- **NOT stored in DuckDB** (too high frequency)

---

## 2. Historical Data Storage (DuckDB)

### 2.1 Database Schema

DuckDB stores historical data in a columnar format optimized for analytical queries.

#### Table: `ohlcv`

Stores OHLCV candlestick data for all symbols and timeframes.

```sql
CREATE TABLE ohlcv (
    symbol VARCHAR NOT NULL,           -- Trading symbol (e.g., "BTCUSDT")
    timeframe VARCHAR NOT NULL,        -- Timeframe ("1m", "5m", "15m", "1h", "4h", "1d")
    timestamp TIMESTAMP NOT NULL,      -- Candle start time (UTC)
    open DOUBLE,                       -- Opening price
    high DOUBLE,                       -- Highest price
    low DOUBLE,                        -- Lowest price
    close DOUBLE,                      -- Closing price
    volume DOUBLE,                     -- Trading volume
    PRIMARY KEY (symbol, timeframe, timestamp)
);
```

**Indexes**:
- `idx_ohlcv_symbol_tf` on `(symbol, timeframe)` - Fast symbol/timeframe queries
- `idx_ohlcv_timestamp` on `(timestamp)` - Fast time-range queries

**Storage Estimate**:
- ~50 bytes per candle
- 1M candles ≈ 50 MB
- 10 symbols × 6 timeframes × 1 year ≈ 1-2 GB (varies by timeframe)

#### Table: `funding_rates`

Stores historical funding rate payments.

```sql
CREATE TABLE funding_rates (
    symbol VARCHAR NOT NULL,           -- Trading symbol
    timestamp TIMESTAMP NOT NULL,      -- Funding payment time
    funding_rate DOUBLE,               -- Funding rate (decimal, e.g., 0.0001 = 0.01%)
    funding_rate_interval_hours INTEGER DEFAULT 8,  -- Payment interval
    PRIMARY KEY (symbol, timestamp)
);
```

**Storage Estimate**:
- ~40 bytes per record
- 3 records/day per symbol (every 8 hours)
- 1 year ≈ 1,095 records ≈ 44 KB per symbol

#### Table: `open_interest`

Stores historical open interest snapshots.

```sql
CREATE TABLE open_interest (
    symbol VARCHAR NOT NULL,           -- Trading symbol
    timestamp TIMESTAMP NOT NULL,      -- Snapshot time
    open_interest DOUBLE,             -- Total open interest
    PRIMARY KEY (symbol, timestamp)
);
```

**Storage Estimate**:
- ~40 bytes per record
- 24 records/day per symbol (if 1h interval)
- 1 year ≈ 8,760 records ≈ 350 KB per symbol

#### Metadata Tables

Each data type has a corresponding metadata table tracking sync status:

- `sync_metadata`: OHLCV sync status (first/last timestamp, candle count, last sync time)
- `funding_metadata`: Funding rate sync status
- `open_interest_metadata`: Open interest sync status

### 2.2 Data Storage Characteristics

**Format**: Columnar storage (DuckDB)
- **Advantages**: Fast analytical queries, efficient compression
- **Disadvantages**: Slower writes, requires periodic VACUUM

**File Location**: `data/market_data.duckdb`

**Write-Ahead Log (WAL)**: `data/market_data.duckdb.wal`
- Stores uncommitted changes
- Can grow large if not periodically committed
- **This may cause freezing if WAL is too large**

---

## 3. Data Flow: API → Storage → Backtesting

### 3.1 Data Collection Flow

```
Bybit LIVE API
    ↓
HistoricalDataStore.sync()
    ↓
Fetch in batches (1000 candles/request)
    ↓
Store in DuckDB (INSERT OR REPLACE)
    ↓
Update metadata tables
```

### 3.2 Data Retrieval for Backtesting

```
Backtesting Engine
    ↓
HistoricalDataStore.get_ohlcv()
    ↓
SQL Query: SELECT * FROM ohlcv WHERE symbol=? AND timeframe=? AND timestamp BETWEEN ? AND ?
    ↓
Return pandas DataFrame
    ↓
Strategy backtesting
```

### 3.3 Multi-Timeframe Data

For multi-timeframe strategies, data is retrieved for multiple timeframes simultaneously:

```python
# Example: Get swing trading data (1d, 4h, 1h)
data = store.get_mtf_data("BTCUSDT", preset="swing", period="1Y")
# Returns: {"htf": DataFrame(1d), "mtf": DataFrame(4h), "ltf": DataFrame(1h)}
```

---

## 4. Data Used for Backtesting

### 4.1 Primary Data: OHLCV Candles

**What**: Historical price action (open, high, low, close, volume)

**Timeframes Available**:
- `1m`, `5m`, `15m`, `1h`, `4h`, `1d`

**Typical Backtest Periods**:
- Short-term strategies: 1-3 months
- Medium-term strategies: 3-6 months
- Long-term strategies: 6 months - 2 years

**Data Quality**:
- Gap detection and filling
- Duplicate removal
- Invalid data filtering (high < low, negative volumes, etc.)

### 4.2 Secondary Data: Funding Rates

**What**: Historical funding rate payments

**Use Cases**:
- Calculate total funding costs for long-term positions
- Optimize entry/exit timing to avoid high funding periods
- Factor in funding costs for accurate PnL calculation

**Integration**: Funding rates are joined with OHLCV data by timestamp for backtesting.

### 4.3 Secondary Data: Open Interest

**What**: Historical open interest snapshots

**Use Cases**:
- Market sentiment analysis
- Liquidity assessment (high OI = easier to exit)
- Trend confirmation (OI increasing with price = strong trend)

**Integration**: Open interest is joined with OHLCV data by timestamp for backtesting.

### 4.4 Data NOT Used for Backtesting

- **Ticker data**: Only current snapshot, not historical
- **Order book**: Too high frequency, not stored
- **Trade history**: Not stored (only OHLCV aggregates)
- **Account data**: Not relevant for backtesting (positions, orders, etc.)

---

## 5. DuckDB Performance Issues & Solutions

### 5.1 Common Issues

#### Issue 1: Terminal Freezing When Opening Database

**Symptoms**:
- Terminal hangs when opening DuckDB file
- High CPU usage
- No response for minutes/hours

**Root Causes**:
1. **Large WAL (Write-Ahead Log) file**: Uncommitted changes accumulate
2. **Database lock contention**: Multiple processes accessing database
3. **Large database size**: Queries scanning millions of rows
4. **Missing indexes**: Full table scans on large tables
5. **Corrupted database**: File system issues or incomplete writes

#### Issue 2: Slow Queries

**Symptoms**:
- Queries take seconds/minutes
- High memory usage
- Database file grows unexpectedly

**Root Causes**:
1. **No indexes on query columns**: Full table scans
2. **Large result sets**: Fetching millions of rows
3. **Inefficient queries**: No WHERE clauses, unnecessary JOINs
4. **Fragmented database**: Deletions leave gaps

### 5.2 Solutions

#### Solution 1: WAL Management

**Problem**: WAL file can grow very large if not periodically committed.

**Solution**: Force checkpoint and WAL truncation:

```python
# In HistoricalDataStore class
def checkpoint(self):
    """Force checkpoint to commit WAL changes."""
    self.conn.execute("CHECKPOINT")
    self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

# Call after large sync operations
store.sync(...)
store.checkpoint()
```

**Automated**: Add periodic checkpoint after every sync operation.

#### Solution 2: Connection Management

**Problem**: Multiple connections can cause lock contention.

**Solution**: Use connection pooling or singleton pattern:

```python
# Current implementation uses singleton
_store: Optional[HistoricalDataStore] = None

def get_historical_store() -> HistoricalDataStore:
    global _store
    if _store is None:
        _store = HistoricalDataStore()
    return _store
```

**Best Practice**: Always use `get_historical_store()` instead of creating new instances.

#### Solution 3: Database Optimization

**Problem**: Database becomes fragmented after deletions.

**Solution**: Periodic VACUUM operation:

```python
# Reclaim space and optimize
store.vacuum()
```

**When to VACUUM**:
- After deleting large amounts of data
- When database file size is unexpectedly large
- Periodically (e.g., weekly) for maintenance

#### Solution 4: Query Optimization

**Problem**: Slow queries on large tables.

**Solution**: Ensure proper indexing and use efficient queries:

```sql
-- Good: Uses index on (symbol, timeframe)
SELECT * FROM ohlcv 
WHERE symbol = 'BTCUSDT' AND timeframe = '1h' 
AND timestamp >= '2024-01-01' AND timestamp <= '2024-12-31'
ORDER BY timestamp;

-- Bad: Full table scan (no WHERE clause)
SELECT * FROM ohlcv ORDER BY timestamp;
```

**Indexes Already Created**:
- `idx_ohlcv_symbol_tf` on `(symbol, timeframe)`
- `idx_ohlcv_timestamp` on `(timestamp)`
- `idx_funding_symbol` on `funding_rates(symbol)`
- `idx_funding_timestamp` on `funding_rates(timestamp)`
- `idx_oi_symbol` on `open_interest(symbol)`
- `idx_oi_timestamp` on `open_interest(timestamp)`

#### Solution 5: Read-Only Mode for Queries

**Problem**: Write operations can block reads.

**Solution**: Use read-only connections for queries:

```python
# For read-only queries (backtesting)
conn = duckdb.connect(str(db_path), read_only=True)
```

**Note**: Current implementation uses single connection. Consider separate read/write connections for better performance.

#### Solution 6: Database Size Management

**Problem**: Database grows too large.

**Solution**: 
1. **Archive old data**: Move data older than X months to separate archive database
2. **Delete unused symbols**: Remove symbols you no longer trade
3. **Compress database**: Use DuckDB's compression features

```python
# Archive old data (example)
def archive_old_data(cutoff_date: datetime):
    # Move data older than cutoff to archive database
    archive_conn = duckdb.connect("data/archive.duckdb")
    # Copy old data
    archive_conn.execute("""
        INSERT INTO ohlcv 
        SELECT * FROM 'data/market_data.duckdb'.ohlcv 
        WHERE timestamp < ?
    """, [cutoff_date])
    # Delete from main database
    store.conn.execute("DELETE FROM ohlcv WHERE timestamp < ?", [cutoff_date])
    store.vacuum()
```

### 5.3 Recommended Maintenance Routine

**Daily**:
- Sync forward new data (lightweight)
- Check database size

**Weekly**:
- Run `heal_data_tool()` to check data integrity
- Fill gaps if detected
- Check WAL file size

**Monthly**:
- Run `vacuum_database_tool()` to reclaim space
- Review and delete unused symbols
- Archive data older than 1 year (if needed)

**On Issues**:
- If terminal freezes: Check WAL file size, run CHECKPOINT
- If queries are slow: Check indexes, optimize queries
- If database is large: Archive old data, delete unused symbols

---

## 6. Alternative Storage Solutions

### 6.1 Current: DuckDB (Columnar)

**Pros**:
- Fast analytical queries
- Efficient compression
- SQL interface
- Single file (easy backup)

**Cons**:
- Can freeze on large WAL
- Slower writes
- Requires periodic VACUUM

### 6.2 Alternative 1: PostgreSQL

**Pros**:
- Robust, battle-tested
- Better concurrent access
- More features (full-text search, etc.)

**Cons**:
- Requires separate server
- More complex setup
- Overkill for single-user bot

### 6.3 Alternative 2: Parquet Files + DuckDB

**Pros**:
- Immutable files (no WAL issues)
- Easy to archive/backup
- Fast reads

**Cons**:
- More complex file management
- Slower writes (file creation)
- Need to manage multiple files

### 6.4 Alternative 3: Time-Series Database (InfluxDB, TimescaleDB)

**Pros**:
- Optimized for time-series data
- Built-in retention policies
- Efficient compression

**Cons**:
- Requires separate server
- Different query language
- More complex setup

### 6.5 Recommendation

**For current use case**: Stick with DuckDB but implement:
1. **Automatic checkpointing** after syncs
2. **Read-only connections** for queries
3. **Periodic VACUUM** scheduling
4. **WAL size monitoring**

**If issues persist**: Consider migrating to PostgreSQL or Parquet files.

---

## 7. Data Quality & Integrity

### 7.1 Data Validation

The system performs automatic validation:

- **Duplicate detection**: PRIMARY KEY prevents duplicates
- **Invalid OHLCV**: Removes candles where high < low
- **Negative volumes**: Sets to 0
- **NULL values**: Removes rows with NULL critical fields
- **Symbol casing**: Normalizes to uppercase
- **Gap detection**: Identifies missing candles

### 7.2 Data Healing

Run `heal_data_tool()` to:
- Check for all data quality issues
- Automatically fix issues (if `fix_issues=True`)
- Fill gaps in data (if `fill_gaps_after=True`)

### 7.3 Gap Filling

Gaps are detected by comparing expected vs. actual candle intervals:

```python
# Gap detection logic
expected_interval = timedelta(minutes=timeframe_minutes)
actual_gap = next_timestamp - current_timestamp
if actual_gap > expected_interval * 1.5:
    # This is a gap - fill it
    store.sync_range(symbol, timeframe, gap_start, gap_end)
```

---

## 8. API Rate Limits & Best Practices

### 8.1 Bybit Rate Limits

**Public Endpoints** (data fetching):
- IP-based: 600 requests per 5 seconds
- Account-based: 120 requests per second

**Best Practices**:
- Batch requests when possible (1000 candles per request)
- Use rate limiter (0.1s delay between requests)
- Cache results (avoid redundant API calls)

### 8.2 Data Sync Strategy

**Initial Sync**:
- Sync in batches (1000 candles per API call)
- Show progress indicators
- Allow cancellation (Ctrl+C)

**Incremental Sync**:
- Use `sync_forward()` to only fetch new data
- Much faster than full sync
- Run daily to keep data current

**Gap Filling**:
- Detect gaps automatically
- Fill gaps on-demand or scheduled
- Prevents missing data in backtests

---

## 9. Summary

### Data Sources

| Data Type | Source | Stored in DuckDB | Used for Backtesting |
|-----------|--------|------------------|----------------------|
| OHLCV Candles | Bybit LIVE API | ✅ Yes | ✅ Primary data |
| Funding Rates | Bybit LIVE API | ✅ Yes | ✅ Secondary (costs) |
| Open Interest | Bybit LIVE API | ✅ Yes | ✅ Secondary (sentiment) |
| Ticker Data | Bybit LIVE API | ❌ No | ❌ Live only |
| Order Book | Bybit WebSocket | ❌ No | ❌ Live only |

### Key Takeaways

1. **All data operations use LIVE API** for accuracy
2. **DuckDB stores historical data** for backtesting
3. **OHLCV is primary data** for backtesting
4. **Funding rates and OI** are secondary data
5. **WAL management is critical** to prevent freezing
6. **Periodic maintenance** (VACUUM, checkpoint) is essential

### Next Steps

1. **Implement automatic checkpointing** after syncs
2. **Add WAL size monitoring** and alerts
3. **Schedule periodic VACUUM** operations
4. **Consider read-only connections** for queries
5. **Monitor database size** and archive old data if needed

---

## 10. External Use Considerations

### 10.1 For External Developers/Users

**Data Access**:
- All data tools are available via `ToolRegistry`
- Use `get_historical_store()` for direct access
- Data is stored in `data/market_data.duckdb`

**API Requirements**:
- **REQUIRED**: `BYBIT_LIVE_DATA_API_KEY` and `BYBIT_LIVE_DATA_API_SECRET`
- These are separate from trading keys
- Used exclusively for data operations

**Database Location**:
- Default: `data/market_data.duckdb`
- Can be customized via `HistoricalDataStore(db_path=...)`

**Performance Recommendations**:
- Use `sync_forward()` for incremental updates (faster)
- Run `vacuum_database_tool()` weekly
- Monitor WAL file size (`market_data.duckdb.wal`)
- Use read-only mode for backtesting queries

### 10.2 For Integration with Other Systems

**Data Export**:
```python
# Export to CSV
df = store.get_ohlcv("BTCUSDT", "1h", period="1M")
df.to_csv("btcusdt_1h_1m.csv")

# Export to Parquet
df.to_parquet("btcusdt_1h_1m.parquet")
```

**Data Import** (if migrating from another system):
- Use `sync_range()` with explicit start/end dates
- Or insert directly into DuckDB (bypass API)

**API Compatibility**:
- All tools return `ToolResult` objects
- Can be used via CLI or programmatically
- Tool registry provides discovery and execution

---

**Document Version**: 1.0  
**Last Updated**: 2024-12-07  
**Maintained By**: TRADE Bot Development Team

