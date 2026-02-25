# Database Alternatives Review: Replacing DuckDB for Parallel Operations

**Date:** 2026-02-25
**Status:** Under Review
**Goal:** Eliminate write-lock contention to enable parallel backtests, shadow/demo/live warm-up without coordination overhead.

---

## Current State (DuckDB)

### Data Volumes

| Database File | Size | Purpose | Data Source |
|---------------|------|---------|-------------|
| `market_data_backtest.duckdb` | 289 MB | Backtests (read-heavy) | api.bybit.com (LIVE API) |
| `market_data_demo.duckdb` | 9.6 MB | Paper trading | api-demo.bybit.com (DEMO API) |
| `market_data_live.duckdb` | 1.5 GB | Live trading warm-up | api.bybit.com (LIVE API) |

### Schema (6 tables per environment)

```
ohlcv_{env}              — OHLCV candles (symbol, timeframe, timestamp, OHLCV, volume, turnover)
sync_metadata_{env}      — Tracks what data is synced per symbol/timeframe
funding_rates_{env}      — 8-hour funding rate snapshots
funding_metadata_{env}   — Funding sync tracking
open_interest_{env}      — Periodic open interest snapshots
open_interest_metadata_{env} — OI sync tracking
```

### Access Patterns

| Operation | Frequency | Volume | Pattern |
|-----------|-----------|--------|---------|
| Backtest data load | Once per run | 50k-100k rows | Range scan: `WHERE symbol=? AND timeframe=? AND timestamp BETWEEN ? AND ?` |
| Funding rate query | Once per run | 10-100 rows | Same range pattern |
| Open interest query | Once per run | 100-1k rows | Same range pattern |
| Live candle upsert | Every bar close | 1 row | `INSERT OR REPLACE` |
| Historical sync | Manual/scheduled | 1k-100k rows | Bulk batch insert |
| Metadata update | After sync | 1 row | Single upsert |

### Current Concurrency Workarounds

1. **Three separate DB files** — backtest/demo/live never contend with each other
2. **`force_read_only=True`** — parallel backtest workers open read-only connections
3. **File-based write locking** — `.lock` file alongside `.duckdb` with PID tracking
4. **Singleton reset** — `reset_stores()` in child processes to avoid shared state

### Pain Points

- Parallel backtests can only **read**, never write shared results
- Live warm-up writes block reads from the same DB
- Data sync locks out all other operations on that environment's DB
- The 3-file split is a workaround, not a solution — adds complexity everywhere
- `historical_data_store.py` is 2,246 lines of workaround code

### What Already Lives Outside DuckDB

- **Backtest results** — Parquet files (`trades.parquet`, `equity.parquet`)
- **Run metadata** — JSON files (`result.json`, `run_manifest.json`)
- **Run index** — JSONL files (`index.jsonl`)
- **Trade journal** — JSONL files (`events.jsonl`)

---

## Requirements for Replacement

| Requirement | Priority | Notes |
|-------------|----------|-------|
| Concurrent reads + writes | **Must** | Ingest live candles while backtests read history |
| Parallel backtest workers | **Must** | N processes querying simultaneously, no coordination |
| Live warm-up persistence | **Must** | Write closed bars without blocking reads |
| Shadow/demo writes | **Must** | Paper trading persists data without locking analysis |
| Time-series optimized | **Should** | Fast range scans on `(symbol, timeframe, timestamp)` |
| Embedded or lightweight | **Should** | No Kubernetes/Docker required, ideally `pip install` |
| Python-native | **Should** | Good DataFrame interop (Pandas/Polars) |
| Incremental migration | **Nice** | Can run alongside DuckDB during transition |

---

## Candidate Analysis

### 1. Parquet Files + Polars (No Database)

**Concept:** Store candles as partitioned Parquet files. Query with Polars (or DataFusion for SQL). No database engine at all.

**Architecture:**
```
data/
├── candles/
│   ├── BTCUSDT/
│   │   ├── 1m.parquet        # One file per symbol + timeframe
│   │   ├── 5m.parquet
│   │   ├── 15m.parquet
│   │   └── 1m_recent.parquet # Staging file for live warm-up
│   └── ETHUSDT/
│       └── ...
├── funding/
│   └── BTCUSDT.parquet
└── open_interest/
    └── BTCUSDT.parquet
```

**How it works:**
- **Reads:** Each backtest worker opens its own file handle — OS page cache handles sharing, zero lock contention.
- **Live writes:** New bars go to a small `_recent.parquet` staging file. Periodic merge (on startup or hourly) combines it into the main file via temp-file + atomic `os.replace()`.
- **Sync:** Write new data to temp file, atomic rename. Readers never see partial files.

```python
# Read (backtest worker)
df = pl.scan_parquet(f"data/candles/{symbol}/{tf}.parquet")
    .filter(pl.col("timestamp").is_between(start, end))
    .collect()

# Write (live warm-up)
new_bar = pl.DataFrame({"timestamp": [ts], "open": [o], "high": [h], ...})
new_bar.write_parquet(f"data/candles/{symbol}/{tf}_recent.parquet")

# Merge (periodic)
base = pl.read_parquet(f"data/candles/{symbol}/{tf}.parquet")
recent = pl.read_parquet(f"data/candles/{symbol}/{tf}_recent.parquet")
merged = pl.concat([base, recent]).unique(subset=["timestamp"]).sort("timestamp")
merged.write_parquet(f"data/candles/{symbol}/{tf}.parquet.tmp")
os.replace(f"...tmp", f"...parquet")  # Atomic on Linux
```

| Criteria | Rating | Notes |
|----------|--------|-------|
| Parallel reads | ★★★★★ | No locks — each process reads independently |
| Concurrent writes | ★★★★ | Atomic rename pattern; staging file for live |
| Install | ★★★★★ | `pip install polars pyarrow` (already have pyarrow) |
| Query speed | ★★★★★ | Polars on Parquet competitive with DuckDB for scans |
| Live warm-up | ★★★★ | Staging file + periodic merge |
| Complexity | ★★★★★ | No server, no connections, no locks, no migrations |
| Data size fit | ★★★★★ | 289MB-1.5GB is well within single-file Parquet range |
| Migration effort | ★★★★ | Incremental — export DuckDB to Parquet, swap reader |

**Pros:**
- Zero lock contention — fundamental problem solved by architecture, not workarounds
- You already use Parquet for backtest results — extends the same pattern
- Polars is 5-10x faster than Pandas, competitive with DuckDB for columnar scans
- Atomic file writes mean readers never see corruption
- Works everywhere (WSL2, native Linux, macOS, Windows)
- No new infrastructure — just files

**Cons:**
- No built-in upsert — merge-on-write pattern for live candle persistence
- No SQL without pairing with DataFusion or DuckDB's Parquet reader
- Schema enforcement is your responsibility
- Many small files if partitioning gets granular (mitigated by symbol+tf partitioning)

---

### 2. chDB (Embedded ClickHouse)

**Concept:** ClickHouse's full analytical engine as a Python library. `pip install chdb` — no server.

**How it works:**
- Each process creates its own chDB session
- Can query Parquet files directly (zero-copy)
- Persistent storage via MergeTree engine for live warm-up
- Full ClickHouse SQL support

```python
import chdb

# Query existing Parquet (no import needed)
result = chdb.query("""
    SELECT * FROM file('data/candles/BTCUSDT/15m.parquet', Parquet)
    WHERE timestamp BETWEEN '2025-01-01' AND '2025-06-30'
    ORDER BY timestamp
""", "DataFrame")

# Persistent session for live writes
session = chdb.Session()
session.query("CREATE DATABASE IF NOT EXISTS trade")
session.query("""
    CREATE TABLE IF NOT EXISTS trade.candles (
        symbol String, timeframe String, timestamp DateTime,
        open Float64, high Float64, low Float64, close Float64,
        volume Float64
    ) ENGINE = MergeTree() ORDER BY (symbol, timeframe, timestamp)
""")
```

| Criteria | Rating | Notes |
|----------|--------|-------|
| Parallel reads | ★★★★★ | Multi-threaded query execution within process |
| Concurrent writes | ★★★★ | Each process gets its own session; share via Parquet files |
| Install | ★★★★ | `pip install "chdb>=2.0.2"` (~200MB) |
| Query speed | ★★★★★ | Full ClickHouse engine — exceptional for analytics |
| Live warm-up | ★★★ | Persistent MergeTree works but less mature than server ClickHouse |
| Complexity | ★★★★ | More API surface, but SQL is familiar |
| Data size fit | ★★★★ | Designed for TB+, overkill but works fine at GB |
| Migration effort | ★★★★ | Can query existing Parquet files immediately |

**Pros:**
- Full SQL with ClickHouse's time-series functions
- Can query your existing Parquet files without import step
- Multi-threaded within a single process
- Stateless sessions — each backtest worker gets its own
- Rich analytical functions (moving averages, window functions, etc.)

**Cons:**
- ~200MB install size (bundles full ClickHouse engine)
- Linux/macOS only (WSL2 is fine, no native Windows)
- Relatively new project (joined ClickHouse family 2024)
- Persistent concurrent writes need careful session design
- Less battle-tested than DuckDB in embedded Python use

---

### 3. SQLite in WAL Mode

**Concept:** The boring, battle-tested option. SQLite with Write-Ahead Logging.

**How it works:**
- WAL mode: writers don't block readers, readers don't block writers
- Still single-writer, but writes queue rather than fail
- Built into Python stdlib — zero dependencies

```python
import sqlite3

conn = sqlite3.connect("data/market_data.db")
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")

# Reads proceed while writes happen
# (writes from another connection don't block this reader)
cursor = conn.execute("""
    SELECT timestamp, open, high, low, close, volume
    FROM ohlcv WHERE symbol=? AND timeframe=? AND timestamp BETWEEN ? AND ?
    ORDER BY timestamp
""", (symbol, tf, start, end))
```

| Criteria | Rating | Notes |
|----------|--------|-------|
| Parallel reads | ★★★★ | Multiple concurrent readers in WAL mode |
| Concurrent writes | ★★★ | Single writer, but doesn't block readers |
| Install | ★★★★★ | Built into Python — `import sqlite3` |
| Query speed | ★★★ | Row-oriented — 5-20x slower than DuckDB for analytical scans |
| Live warm-up | ★★★★ | WAL mode: inserts don't block reads |
| Complexity | ★★★★★ | Most widely deployed DB in the world |
| Data size fit | ★★★★ | Handles GB-scale fine |
| Migration effort | ★★★ | Schema rewrite, slower queries need optimization |

**Pros:**
- WAL mode solves core problem: writers don't block readers
- Zero dependencies — Python stdlib
- Battle-tested in every environment
- Can still use DuckDB to query SQLite files for heavy analytics

**Cons:**
- Row-oriented: analytical range scans 5-20x slower than DuckDB/Polars
- Still single-writer (writes queue, not parallel)
- No columnar compression — files 2-3x larger than Parquet
- Doesn't solve the *parallel write* problem, only read-during-write

---

### 4. PostgreSQL (+ TimescaleDB Extension)

**Concept:** A real database with real concurrency. Local server, full MVCC.

**How it works:**
- Full MVCC: N writers + M readers, row-level locking, zero contention
- TimescaleDB extension adds time-series hypertables, continuous aggregates
- Connection via `psycopg` or `asyncpg`

```python
import psycopg

with psycopg.connect("postgresql://localhost/trade") as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT timestamp, open, high, low, close, volume
            FROM ohlcv
            WHERE symbol = %s AND timeframe = %s
              AND timestamp BETWEEN %s AND %s
            ORDER BY timestamp
        """, (symbol, tf, start, end))
        rows = cur.fetchall()
```

| Criteria | Rating | Notes |
|----------|--------|-------|
| Parallel reads | ★★★★★ | Full MVCC, unlimited concurrent readers |
| Concurrent writes | ★★★★★ | Multiple concurrent writers, row-level locking |
| Install | ★★★ | `sudo apt install postgresql` or Docker |
| Query speed | ★★★★ | Good with proper indexes; TimescaleDB adds partitioning |
| Live warm-up | ★★★★★ | Insert while querying, zero contention |
| Complexity | ★★★ | Server process, connection management |
| Data size fit | ★★★★ | Sweet spot for GB-scale structured data |
| Migration effort | ★★ | Server setup, schema migration, connection pool |

**Pros:**
- True MVCC: N writers + M readers, zero contention — the "real" solution
- TimescaleDB adds hypertables with automatic time-based partitioning
- Excellent Python ecosystem (`psycopg`, `asyncpg`, SQLAlchemy)
- Natural graduation path toward dashboard/API layer
- Continuous aggregates for pre-computed rollups (e.g., 1m → 15m)

**Cons:**
- Not embedded — requires server process
- Operational overhead (backups, vacuuming, connection pooling)
- Overkill for "candle storage" at current scale
- Adds Docker/systemd dependency to workflow

---

### 5. QuestDB (Time-Series Specialist)

**Concept:** Purpose-built time-series database. Designed for exactly this data pattern.

**How it works:**
- Lock-free ingestion via InfluxDB Line Protocol (ILP)
- SQL queries via PGWire (PostgreSQL compatible)
- Built-in `SAMPLE BY` for OHLCV resampling
- Zero-GC hot path (inspired by HFT systems)

```python
from questdb.ingress import Sender, IngressError
import psycopg  # PGWire for reads

# Write (lock-free ILP)
with Sender("localhost", 9009) as sender:
    sender.row("ohlcv",
        symbols={"symbol": "BTCUSDT", "timeframe": "15m"},
        columns={"open": 50000.0, "high": 50100.0, ...},
        at=timestamp)

# Read (SQL via PGWire)
with psycopg.connect("postgresql://localhost:8812/trade") as conn:
    df = pd.read_sql("""
        SELECT * FROM ohlcv
        WHERE symbol = 'BTCUSDT' AND timeframe = '15m'
          AND timestamp IN '2025-01-01;2025-06-30'
        ORDER BY timestamp
    """, conn)
```

| Criteria | Rating | Notes |
|----------|--------|-------|
| Parallel reads | ★★★★★ | Concurrent SQL via PGWire |
| Concurrent writes | ★★★★★ | Lock-free ILP ingestion |
| Install | ★★★ | Server binary or Docker (not pip-installable) |
| Query speed | ★★★★★ | 4 billion rows/sec benchmarks, time-range optimized |
| Live warm-up | ★★★★★ | Designed for real-time ingest + query simultaneously |
| Complexity | ★★★ | Server process, but simple config |
| Data size fit | ★★★★★ | Built for exactly this scale and pattern |
| Migration effort | ★★ | Server setup, new ingestion protocol |

**Pros:**
- Fastest time-series benchmarks (1.4M rows/sec ingest, 4B rows/sec query)
- Built-in `SAMPLE BY` for OHLCV resampling (1m → 15m natively)
- Lock-free ingestion — write from N processes simultaneously
- Zero-GC hot path designed for trading systems
- SQL interface via PGWire (works with psycopg/pandas)

**Cons:**
- Not embeddable — requires separate server process
- Smaller ecosystem than PostgreSQL
- Python client is writer-only; reads go through SQL
- Another service to manage (though lightweight)

---

### 6. Apache DataFusion (Embedded Query Engine)

**Concept:** Arrow-native SQL engine. Like DuckDB but stateless — queries files, no storage engine.

**How it works:**
- SQL and DataFrame API over Parquet/CSV/JSON files
- Multi-threaded, morsel-driven parallelism
- Zero concurrency issues — stateless, just reads files
- Pair with Parquet storage (same as Option 1)

```python
import datafusion

ctx = datafusion.SessionContext()
ctx.register_parquet("candles", "data/candles/BTCUSDT/15m.parquet")

df = ctx.sql("""
    SELECT timestamp, open, high, low, close, volume
    FROM candles
    WHERE timestamp BETWEEN '2025-01-01' AND '2025-06-30'
    ORDER BY timestamp
""")
result = df.to_pandas()
```

| Criteria | Rating | Notes |
|----------|--------|-------|
| Parallel reads | ★★★★★ | Multi-threaded, morsel-driven parallelism |
| Concurrent writes | N/A | Not a storage engine — queries files |
| Install | ★★★★ | `pip install datafusion` |
| Query speed | ★★★★★ | Recently benchmarked faster than DuckDB on Parquet |
| Live warm-up | ★★★★ | Same Parquet file pattern as Option 1 |
| Complexity | ★★★★ | SQL + DataFrame API, no server |
| Data size fit | ★★★★★ | Designed for this scale |
| Migration effort | ★★★★ | Queries existing Parquet, minimal code changes |

**Pros:**
- Full SQL on Parquet files — SQL without a database
- Fastest single-node Parquet query engine (recent benchmarks)
- Arrow-native: zero-copy interop with Pandas/Polars
- No concurrency issues — stateless

**Cons:**
- Not a database — no writes, indexes, or upserts
- Less mature Python API than DuckDB or Polars
- Must pair with file-based storage pattern
- Smaller community than DuckDB

---

## Comparison Matrix

| Option | Parallel Reads | Parallel Writes | Live Warm-up | Install Ease | Query Speed | Migration Effort | Overall Fit |
|--------|---------------|----------------|-------------|-------------|-------------|-----------------|------------|
| **Parquet + Polars** | ★★★★★ | ★★★★ | ★★★★ | ★★★★★ | ★★★★★ | ★★★★ | **Best** |
| **chDB** | ★★★★★ | ★★★★ | ★★★ | ★★★★ | ★★★★★ | ★★★★ | Good |
| **SQLite WAL** | ★★★★ | ★★★ | ★★★★ | ★★★★★ | ★★★ | ★★★ | OK |
| **PostgreSQL** | ★★★★★ | ★★★★★ | ★★★★★ | ★★★ | ★★★★ | ★★ | Good (heavy) |
| **QuestDB** | ★★★★★ | ★★★★★ | ★★★★★ | ★★★ | ★★★★★ | ★★ | Good (heavy) |
| **DataFusion** | ★★★★★ | N/A | ★★★★ | ★★★★ | ★★★★★ | ★★★★ | Good |

---

## Recommendation

### Primary: Parquet + Polars

**Why this is the best fit for TRADE:**

1. **You already use Parquet** — backtest results are `trades.parquet` and `equity.parquet`. This extends the same pattern to candle storage.

2. **Zero lock contention** — the fundamental problem is solved by architecture (independent files) rather than database-level workarounds.

3. **Polars is fast enough** — for range scans on 50k-100k candles, Polars on Parquet is competitive with DuckDB. Your queries are simple `WHERE symbol=? AND tf=? AND ts BETWEEN ? AND ?` scans, not complex joins.

4. **Live warm-up is solvable** — staging file + periodic merge with atomic rename. Readers never see partial data.

5. **Migration is incremental** — keep DuckDB for sync operations initially, export to Parquet for reads. Swap the reader in `engine_data_prep.py` first, then migrate writes.

6. **No new infrastructure** — `pip install polars`. No servers, no Docker, no connections.

### Upgrade Path: Add DataFusion for SQL

If you miss SQL, pair Parquet with DataFusion (`pip install datafusion`). Full SQL over Parquet files, faster than DuckDB in recent benchmarks, zero concurrency issues.

### Graduation Path: PostgreSQL + TimescaleDB

When you need a dashboard, multi-user access, API layer, or continuous aggregates, PostgreSQL is the natural evolution. But at current scale (1.5 GB max), it adds complexity without proportional benefit.

---

## Migration Strategy (If Parquet + Polars is chosen)

### Phase 1: Export & Read
- [ ] Export DuckDB candle data to Parquet files (one per symbol+timeframe)
- [ ] Add Polars-based reader alongside existing DuckDB reader
- [ ] Switch `engine_data_prep.py` to use Parquet reader
- [ ] Validate: parallel backtests work without `force_read_only` hack
- [ ] **GATE**: `python trade_cli.py validate quick` passes

### Phase 2: Write Path
- [ ] Implement Parquet-based candle writer with staging file pattern
- [ ] Migrate `upsert_candle()` (live warm-up) to write staging Parquet
- [ ] Implement periodic merge (staging → main file)
- [ ] Migrate `upsert_candles_batch()` (historical sync) to write Parquet directly
- [ ] **GATE**: `python trade_cli.py validate standard` passes

### Phase 3: Remove DuckDB
- [ ] Remove `historical_data_store.py` DuckDB code paths
- [ ] Remove DuckDB dependency from `requirements.txt`
- [ ] Remove `.duckdb` files and lock file logic
- [ ] Update `constants.py` — remove DB path resolution
- [ ] **GATE**: `python trade_cli.py validate full` passes
- [ ] **GATE**: `python scripts/run_full_suite.py` — all plays pass

---

## References

- [DuckDB vs SQLite Comparison](https://motherduck.com/learn-more/duckdb-vs-sqlite-databases/)
- [8 DuckDB Alternatives](https://www.tinybird.co/blog/duckdb-alternatives)
- [SQLite WAL Mode Documentation](https://sqlite.org/wal.html)
- [QuestDB: Scaling a Trading Bot](https://questdb.com/blog/scaling-trading-bot-with-time-series-database/)
- [QuestDB Benchmark: 4Bn rows/sec](https://questdb.com/blog/2022/05/26/query-benchmark-questdb-versus-clickhouse-timescale/)
- [chDB: Embedded ClickHouse](https://clickhouse.com/blog/welcome-chdb-to-clickhouse)
- [chDB Installation (Python)](https://clickhouse.com/docs/chdb/install/python)
- [Apache DataFusion](https://datafusion.apache.org/)
- [DataFusion Python API](https://datafusion.apache.org/python/)
- [Polars DataFrame Library](https://pola.rs/)
- [Polars vs Pandas Comparison](https://www.databricks.com/glossary/polaris-vs-pandas)
- [ClickHouse vs DuckDB 2026](https://tasrieit.com/blog/clickhouse-vs-duckdb-2026)
- [LanceDB Concurrent Writes](https://github.com/lancedb/lancedb/issues/213)
- [DuckDB vs PostgreSQL](https://airbyte.com/data-engineering-resources/duckdb-vs-postgres)
- [Abusing SQLite for Concurrency](https://blog.skypilot.co/abusing-sqlite-to-handle-concurrency/)
- [InfluxDB FDAP Architecture (Arrow + Parquet + DataFusion)](https://www.influxdata.com/blog/flight-datafusion-arrow-parquet-fdap-architecture-influxdb/)
