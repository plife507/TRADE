# Architecture Review: Data Module

**Reviewer**: Senior Developer Perspective
**Date**: 2026-01-02
**Module**: `src/data/`
**Status**: Production-quality with minor improvement opportunities

---

## Executive Summary

The data module provides a well-architected, domain-agnostic infrastructure for market data storage and retrieval. It implements a robust DuckDB-based historical data store with comprehensive sync, query, and maintenance capabilities, plus a real-time WebSocket-driven state management system for live trading.

**Strengths**:
- Clean separation between historical (DuckDB) and real-time (WebSocket) data paths
- Thread-safe implementations throughout
- Environment-aware (live/demo) architecture
- Comprehensive gap detection and healing
- Well-designed protocol abstraction for future MongoDB migration

**Areas for Improvement**:
- Some code duplication between query functions
- Missing transaction/rollback semantics for batch operations
- Singleton pattern overuse could complicate testing
- Minor schema inefficiencies

---

## File-by-File Analysis

### 1. `historical_data_store.py` (Main DuckDB Interface)

**Purpose**: Primary interface for historical market data storage using DuckDB. Handles OHLCV, funding rates, and open interest data with environment-aware storage.

**Key Functions**:
| Function | Description |
|----------|-------------|
| `__init__()` | Initializes DuckDB connection, resolves env-specific paths/tables |
| `sync()` | Delegates to historical_sync module |
| `get_ohlcv()` | Query OHLCV data with period/date range filters |
| `get_funding()` | Query funding rate data |
| `get_open_interest()` | Query open interest data |
| `status()` | Get sync status with gap detection |
| `update_extremes()` | Update metadata bounds after bootstrap |

**Dependencies**:
- `duckdb` - Embedded analytical database
- `pandas` - DataFrame handling
- `BybitClient` - API data fetching
- Internal: `config`, `constants`, `logger`

**Schema Design**:
```sql
-- Main OHLCV table (env-specific: ohlcv_live / ohlcv_demo)
CREATE TABLE ohlcv_{env} (
    symbol VARCHAR NOT NULL,
    timeframe VARCHAR NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE,
    volume DOUBLE, turnover DOUBLE,
    PRIMARY KEY (symbol, timeframe, timestamp)
)

-- Sync metadata (tracks data ranges)
CREATE TABLE sync_metadata_{env} (
    symbol VARCHAR, timeframe VARCHAR,
    first_timestamp TIMESTAMP, last_timestamp TIMESTAMP,
    candle_count INTEGER, last_sync TIMESTAMP,
    PRIMARY KEY (symbol, timeframe)
)

-- Funding rates
CREATE TABLE funding_rates_{env} (
    symbol VARCHAR, timestamp TIMESTAMP,
    funding_rate DOUBLE, funding_rate_interval_hours INTEGER DEFAULT 8,
    PRIMARY KEY (symbol, timestamp)
)

-- Open interest
CREATE TABLE open_interest_{env} (
    symbol VARCHAR, timestamp TIMESTAMP,
    open_interest DOUBLE,
    PRIMARY KEY (symbol, timestamp)
)

-- Data extremes (bounds metadata)
CREATE TABLE data_extremes_{env} (
    symbol VARCHAR, data_type VARCHAR, timeframe VARCHAR,
    earliest_ts TIMESTAMP, latest_ts TIMESTAMP,
    row_count INTEGER, gap_count_after_heal INTEGER,
    resolved_launch_time TIMESTAMP, source VARCHAR, last_updated TIMESTAMP,
    PRIMARY KEY (symbol, data_type, timeframe)
)
```

**Issues Found**:

1. **P2 - Schema Migration Fragility** (Lines 319-325): Uses bare `try/except` to add `turnover` column. Silent failures could mask real errors.
   ```python
   try:
       self.conn.execute(f"ALTER TABLE {self.table_ohlcv} ADD COLUMN turnover DOUBLE")
   except Exception:
       pass  # Column already exists
   ```
   *Better*: Check schema first or use DuckDB's introspection.

2. **P3 - Module-level API Bug** (Lines 1712-1713): `append_ohlcv()` uses undefined variable `timeframe` instead of `tf`:
   ```python
   store._store_dataframe(symbol, tf, df)
   store._update_metadata(symbol, timeframe)  # BUG: should be 'tf'
   ```

3. **P3 - Connection Management**: No connection pooling or retry logic for DuckDB connection. Single connection could be a bottleneck under concurrent access (though DuckDB handles this internally).

4. **P3 - Timestamp Handling**: Stores naive timestamps assuming UTC. Could cause issues if input has mixed timezones:
   ```python
   if df["timestamp"].dt.tz is not None:
       df["timestamp"] = df["timestamp"].dt.tz_localize(None)
   ```

**Structural Concerns**:
- Class is 1700+ lines - could benefit from further modularization
- ActivityEmoji/ActivitySpinner classes (UI concerns) mixed with data logic
- Singleton pattern via global variables complicates testing

---

### 2. `historical_sync.py`

**Purpose**: Handles data synchronization from Bybit API to DuckDB, including period-based sync, range sync, and forward sync.

**Key Functions**:
| Function | Description |
|----------|-------------|
| `sync()` | Main sync orchestrator for period-based fetching |
| `sync_range()` | Sync specific date range |
| `sync_forward()` | Sync from last stored candle to now |
| `_sync_symbol_timeframe()` | Core sync logic for single symbol/TF |
| `_fetch_from_api()` | Paginated API fetching with progress |

**Dependencies**:
- `historical_data_store.py` (store reference)
- `pandas` for DataFrame handling

**Issues Found**:

1. **P2 - Incomplete Range Calculation** (Lines 276-290): When determining ranges to fetch, the logic for calculating gaps between existing data and target range is correct but doesn't handle mid-range gaps (only start/end extensions):
   ```python
   if target_start < first_ts:
       ranges_to_fetch.append((target_start, older_end))
   if target_end > last_ts:
       ranges_to_fetch.append((newer_start, target_end))
   # Mid-range gaps not handled here - relies on fill_gaps()
   ```

2. **P3 - Rate Limiting** (Lines 367-368): Hardcoded 50ms sleep between API requests:
   ```python
   time.sleep(0.05)
   ```
   Should use configurable rate limiter.

3. **P3 - Duplicate DataFrame Handling** (Lines 373-375): Drops duplicates by timestamp only - doesn't verify OHLCV values match:
   ```python
   combined = combined.drop_duplicates(subset=["timestamp"], keep="first")
   ```

**Structural Concerns**:
- Good separation from main store class
- Clean forward-only sync pattern avoids complex state management
- Could benefit from batch transaction semantics

---

### 3. `historical_queries.py`

**Purpose**: Query functions for retrieving data from DuckDB.

**Key Functions**:
| Function | Description |
|----------|-------------|
| `get_ohlcv()` | Query OHLCV with filters |
| `get_mtf_data()` | Multi-timeframe data retrieval |
| `get_funding()` | Funding rate queries |
| `get_open_interest()` | OI queries |

**Dependencies**: pandas, datetime

**Issues Found**:

1. **P2 - Inconsistent with Main Store** (Line 41-42): Query includes `turnover` column but main store's `get_ohlcv()` doesn't:
   ```python
   # historical_queries.py
   SELECT timestamp, open, high, low, close, volume, turnover

   # historical_data_store.py get_ohlcv()
   SELECT timestamp, open, high, low, close, volume  # No turnover!
   ```

2. **P3 - SQL Injection Risk** (Line 61): Uses f-string for LIMIT:
   ```python
   if limit:
       query += f" LIMIT {limit}"
   ```
   While `limit` is an int, pattern is risky. Should use parameterized query.

3. **P3 - Column Mismatch** (Line 123): References non-existent column:
   ```python
   SELECT timestamp, funding_rate, funding_rate_timestamp  # funding_rate_timestamp doesn't exist in schema
   ```

**Structural Concerns**:
- Code duplication between this file and methods in `historical_data_store.py`
- Not clear which interface should be canonical

---

### 4. `historical_maintenance.py`

**Purpose**: Data integrity maintenance operations including gap detection, healing, cleanup.

**Key Functions**:
| Function | Description |
|----------|-------------|
| `detect_gaps()` | Find timestamp gaps in stored data |
| `fill_gaps()` | Fetch missing data to fill gaps |
| `heal()` | Combined detect + fill operation |
| `heal_comprehensive()` | Full integrity check and repair |
| `delete_symbol()` | Remove all data for symbol |
| `cleanup_empty_symbols()` | Remove orphaned metadata |

**Dependencies**: historical_sync for API fetching

**Gap Detection Algorithm**:
```python
expected_delta = timedelta(minutes=tf_minutes)
for i in range(1, len(rows)):
    actual_delta = curr_ts - prev_ts
    if actual_delta > expected_delta * 1.5:  # Gap threshold = 150%
        gaps.append((prev_ts + expected_delta, curr_ts - expected_delta))
```

**Issues Found**:

1. **P2 - Gap Detection Threshold** (Line 49): Uses 1.5x multiplier for gap detection, but weekends/holidays create legitimate large gaps for daily timeframes:
   ```python
   if actual_delta > expected_delta * 1.5:
   ```
   *Impact*: Could report false-positive gaps for daily data over weekends.

2. **P2 - SQL Query Construction** (Lines 275-322): Multiple places use string concatenation for SQL with inconsistent `AND` clause handling:
   ```python
   and_clause = f"AND symbol = '{symbol}'" if symbol else ""
   # Later:
   ".replace('AND  AND', 'AND')"  # Fragile fix
   ```

3. **P3 - No Transaction Rollback** (Lines 289-296): Deletes duplicates one-by-one without transaction:
   ```python
   for sym, tf, ts, cnt in dupes:
       store.conn.execute("DELETE FROM ...")
   ```
   If interrupted mid-way, could leave partial state.

4. **P3 - Deletion Cascade** (Lines 177-193): `delete_symbol()` deletes from multiple tables but no foreign key enforcement:
   ```python
   store.conn.execute(f"DELETE FROM {store.table_ohlcv} WHERE symbol = ?", [symbol])
   store.conn.execute(f"DELETE FROM {store.table_sync_metadata} WHERE symbol = ?", [symbol])
   # etc.
   ```

**Structural Concerns**:
- `heal_comprehensive()` at 200+ lines does too much - should be split
- Mix of user-facing print statements and logging

---

### 5. `sessions.py` (DuckDB Session Management)

**Purpose**: Provides isolated trading session abstractions with environment-scoped data access.

**Key Classes**:
| Class | Description |
|-------|-------------|
| `SessionConfig` | Configuration dataclass |
| `BaseSession` | Abstract session with warmup, MTF buffer access |
| `DemoSession` | env="demo" session |
| `LiveSession` | env="live" session |

**Key Methods**:
| Method | Description |
|--------|-------------|
| `initialize()` | Validate store access |
| `warm_up()` | Load historical data into MTF buffers |
| `get_mtf_buffer()` | Access warmed-up data |
| `start()/stop()` | Lifecycle management |

**Dependencies**:
- `RealtimeState` for MTF buffer storage
- `historical_data_store` for warmup data
- `config`, `constants`

**Issues Found**:

1. **P3 - Incomplete Async Pattern**: Module docstring mentions `await session.initialize()` but methods are synchronous:
   ```python
   # Docstring says:
   await session.initialize()  # Not actually async
   await session.warm_up()

   # Actual implementation:
   def initialize(self) -> bool:  # Sync
   ```

2. **P3 - Session ID Collision** (Lines 509, 540): Auto-generated IDs use millisecond timestamp, could collide:
   ```python
   session_id = f"demo_{int(time.time() * 1000)}"
   ```

3. **P3 - No Session Registry**: Sessions created via factory functions aren't tracked, making it hard to enumerate active sessions.

**Structural Concerns**:
- Good abstraction for environment isolation
- Could benefit from context manager pattern for lifecycle
- Warmup could be asynchronous for large datasets

---

### 6. `market_data.py`

**Purpose**: Live market data fetching with hybrid WebSocket/REST support and aggressive caching.

**Key Classes**:
| Class | Description |
|-------|-------------|
| `CacheEntry` | TTL-based cache entry |
| `MarketDataCache` | Thread-safe cache container |
| `MarketData` | Main market data provider |

**Key Methods**:
| Method | Description |
|--------|-------------|
| `get_latest_price()` | Current price (WS preferred) |
| `get_bid_ask()` | Bid/ask spread |
| `get_ticker()` | Full ticker data |
| `get_ohlcv()` | Historical candles with current candle update |
| `get_funding_rate()` | Funding info |

**Data Source Priority**:
1. WebSocket (RealtimeState) if fresh
2. REST API with caching as fallback

**Issues Found**:

1. **P2 - Always Uses LIVE API** (Lines 128-146): Even for demo env, uses LIVE API for market data. While documented as intentional, could cause confusion:
   ```python
   # Future: may use demo API for env="demo"
   self.client = BybitClient(
       use_demo=False,  # ALWAYS use LIVE API for data accuracy
   )
   ```

2. **P3 - Cache Key Collisions** (Lines 386-389): OHLCV cache key doesn't include environment:
   ```python
   cache_key = f"ohlcv:{symbol}:{timeframe}:{bars}"
   # Should include self.env to avoid cross-env cache pollution
   ```

3. **P3 - Stale WebSocket Update** (Lines 400-440): `_update_current_candle_from_ws()` modifies DataFrame in place using `.iloc[]` which can raise SettingWithCopyWarning.

**Structural Concerns**:
- Hybrid WS/REST approach is well-designed
- Source tracking (`_last_source`) useful for debugging
- Could benefit from circuit breaker pattern for REST fallback

---

### 7. `backend_protocol.py`

**Purpose**: Abstract interface for historical data backends, enabling future MongoDB migration.

**Key Classes**:
| Class | Description |
|-------|-------------|
| `HistoricalBackend` | ABC defining required methods |
| `MongoBackend` | Placeholder MongoDB implementation |

**Abstract Methods**:
- `connect()`, `close()`, `is_connected()`
- `get_ohlcv()`, `append_ohlcv()`, `get_ohlcv_range()`
- `get_funding()`, `append_funding()`
- `get_open_interest()`, `append_open_interest()`
- `get_symbol_list()`, `get_database_stats()`
- `delete_symbol()`, `vacuum()`

**Issues Found**:

1. **P3 - DuckDB Not Implementing Protocol**: Current `HistoricalDataStore` doesn't inherit from `HistoricalBackend`:
   ```python
   class HistoricalDataStore:  # Doesn't inherit HistoricalBackend
   ```
   Protocol is aspirational, not enforced.

2. **P3 - Factory Not Usable** (Lines 463-472):
   ```python
   def get_backend(env, backend_type="duckdb"):
       if backend_type == "duckdb":
           raise NotImplementedError("Use HistoricalDataStore directly")
   ```

**Structural Concerns**:
- Good forward-thinking design for backend abstraction
- Currently dead code - should either implement or remove
- MongoDB schema design in comments is well-thought-out

---

### 8. `realtime_models.py`

**Purpose**: Data models for WebSocket-driven real-time state.

**Key Models**:
| Model | Description |
|-------|-------------|
| `TickerData` | Normalized ticker with bid/ask, funding, OI |
| `OrderbookData` | Orderbook with delta application |
| `TradeData` | Public trade data |
| `KlineData` | Candlestick data |
| `MTFCandle` | Ring buffer candle storage |
| `PositionData` | Full position with risk metrics |
| `OrderData` | Order state |
| `ExecutionData` | Trade execution |
| `WalletData` | Per-coin balance |
| `AccountMetrics` | Unified account metrics |
| `PortfolioRiskSnapshot` | Aggregated risk view |

**Issues Found**:

1. **P3 - Timestamp Type Inconsistency**: Some models use `float` (epoch), others use `datetime`:
   ```python
   class TickerData:
       timestamp: float = field(default_factory=time.time)

   class MTFCandle:
       timestamp: datetime
   ```

2. **P3 - Risk Calculation Edge Cases** (Lines 699-707):
   ```python
   @property
   def risk_buffer(self) -> float:
       return self.total_margin_balance - self.total_maintenance_margin
   ```
   No handling for negative values which could indicate liquidation.

3. **P3 - Magic Numbers** (Lines 318-322):
   ```python
   MTF_BUFFER_SIZES = {
       "1m": 500, "3m": 400, "5m": 300, ...
   }
   ```
   Should be configurable or documented why these specific values.

**Structural Concerns**:
- Comprehensive model coverage
- Good use of `@classmethod` factories for Bybit parsing
- `to_dict()` methods enable easy serialization
- 950 lines - could split into market/account model files

---

### 9. `realtime_state.py`

**Purpose**: Thread-safe centralized state manager for WebSocket data.

**Key Features**:
- Thread-safe read/write via `RLock`
- Event queue for event-driven processing
- Callback registration for state changes
- MTF ring buffers for strategy warmup
- Connection status tracking

**Key Methods**:
| Method | Description |
|--------|-------------|
| `update_ticker()` | Thread-safe ticker update |
| `get_ticker()` | Read current ticker |
| `is_ticker_stale()` | Check data freshness |
| `on_ticker_update()` | Register callback |
| `init_mtf_buffer()` | Initialize from historical data |
| `append_mtf_candle()` | Add closed candle to buffer |
| `build_portfolio_snapshot()` | Aggregate risk view |

**Issues Found**:

1. **P2 - Unbounded Event Queue** (Line 161):
   ```python
   self._event_queue: Queue = Queue()  # No maxsize
   ```
   Could grow unbounded if consumers don't keep up.

2. **P3 - Callback Error Handling** (Lines 787-793):
   ```python
   def _invoke_callbacks(self, callbacks: List[Callable], data: Any):
       for callback in callbacks:
           try:
               callback(data)
           except Exception as e:
               self.logger.error(f"Callback error: {e}")
   ```
   Continues to next callback on error, but error in one callback shouldn't affect others - this is correct. However, no way to unregister failed callbacks.

3. **P3 - MTF Buffer Environment Handling** (Lines 187-190):
   ```python
   self._mtf_buffers: Dict[str, Dict[str, Dict[str, Deque[MTFCandle]]]] = {
       "live": defaultdict(lambda: defaultdict(deque)),
       "demo": defaultdict(lambda: defaultdict(deque)),
   }
   ```
   Nested defaultdicts create buffers without maxlen, but `init_mtf_buffer()` creates proper bounded deques.

**Structural Concerns**:
- Well-designed thread-safety model
- Good separation of market vs account data
- Singleton pattern via global variable works but complicates testing
- 930 lines - quite large but cohesive

---

### 10. `realtime_bootstrap.py`

**Purpose**: WebSocket connection management and subscription handling.

**Key Classes**:
| Class | Description |
|-------|-------------|
| `SubscriptionConfig` | Configure which streams to enable |
| `RealtimeBootstrap` | Main WebSocket manager |

**Key Methods**:
| Method | Description |
|--------|-------------|
| `start()` | Connect and subscribe to streams |
| `stop()` | Graceful shutdown |
| `subscribe_symbol_dynamic()` | Add symbol at runtime |
| `_start_public_streams()` | Initialize market data streams |
| `_start_private_streams()` | Initialize account streams |
| `_fetch_initial_private_state()` | REST bootstrap for private data |

**Issues Found**:

1. **P2 - Initial State Race Condition** (Lines 641-645): Private streams may receive updates before initial REST fetch completes:
   ```python
   self._private_connected = True
   self.state.set_private_ws_connected()
   # REST fetch happens AFTER marking connected
   self._fetch_initial_private_state()
   ```
   Could miss updates or have stale initial state.

2. **P2 - Reconnection Not Implemented** (Line 912-930): `_handle_stale_connection()` only logs and updates status, doesn't actually reconnect:
   ```python
   def _handle_stale_connection(self):
       self.logger.warning("WebSocket stale - switching to REST fallback")
       # No reconnection attempt!
   ```

3. **P3 - Hardcoded Monitor Interval** (Line 874):
   ```python
   self._stop_event.wait(30)  # Check every 30 seconds
   ```
   Should be configurable.

4. **P3 - Rate Limit Error Suppression** (Lines 294-297):
   ```python
   if "Too many connection attempts" not in error_msg:
       self.logger.error(f"Failed to start: {e}")
   ```
   Suppressing error logs can hide persistent issues.

**Structural Concerns**:
- Good configuration flexibility via `SubscriptionConfig`
- `demo_safe()` config preset is thoughtful
- Missing automatic reconnection is a significant gap
- 1080 lines - largest file in module

---

## Cross-Cutting Concerns

### 1. Singleton Pattern Usage

Multiple files use module-level singletons:
- `_store_live`, `_store_demo` in `historical_data_store.py`
- `_market_data_live`, `_market_data_demo` in `market_data.py`
- `_realtime_state` in `realtime_state.py`
- `_realtime_bootstrap` in `realtime_bootstrap.py`

**Impact**: Makes testing difficult, can't easily mock or reset state.

**Recommendation**: Consider dependency injection or context-based instance management.

### 2. Environment (Live/Demo) Handling

Consistent pattern across all files:
```python
env: DataEnv = validate_data_env(env)
```

Tables and paths are environment-specific, preventing cross-contamination.

**Good**: Clean separation.
**Gap**: No automated tests verifying isolation.

### 3. Error Handling Patterns

Inconsistent error handling:
- Some places use bare `except Exception`
- Some places log and continue
- Some places raise
- No custom exception hierarchy

**Recommendation**: Define `DataModuleError` hierarchy.

### 4. Logging

Uses centralized `get_logger()` consistently. Good use of log levels.

**Gap**: No structured logging (would help with log aggregation).

---

## Summary of Issues by Priority

### P1 - Critical (None Found)

### P2 - High Priority (7 Issues)
1. Schema migration uses bare try/except
2. Sync doesn't handle mid-range gaps
3. Query column mismatch (turnover)
4. Gap detection false positives for daily data
5. SQL construction with string manipulation
6. Always uses LIVE API for demo market data
7. Initial state race condition in bootstrap

### P3 - Medium Priority (19 Issues)
1. Module-level API bug (`timeframe` vs `tf`)
2. No connection pooling
3. Naive timestamp storage
4. Hardcoded rate limiting sleep
5. Duplicate handling doesn't verify values
6. SQL injection risk pattern
7. Column reference to non-existent column
8. No transaction rollback for batch ops
9. Incomplete async pattern in sessions
10. Session ID collision potential
11. Cache key missing environment
12. DataFrame modification warning
13. Protocol not enforced
14. Timestamp type inconsistency
15. Risk calculation edge cases
16. Magic numbers in buffer sizes
17. Unbounded event queue
18. No callback unregistration
19. No reconnection implementation

---

## Recommendations

### Short-Term (1-2 sprints)

1. **Fix the bugs**:
   - Fix `append_ohlcv()` variable name bug
   - Add missing `turnover` to main store query
   - Remove non-existent column reference

2. **Add transaction semantics**:
   ```python
   with store.conn.begin() as transaction:
       # batch operations
       transaction.commit()
   ```

3. **Implement reconnection logic** in RealtimeBootstrap

### Medium-Term (1-2 months)

1. **Consolidate query interfaces**:
   - Decide if `historical_queries.py` or `historical_data_store.py` methods are canonical
   - Deprecate the other

2. **Add schema migrations**:
   - Proper version tracking
   - Rollback support

3. **Replace singletons with factory pattern**:
   ```python
   class DataModule:
       def __init__(self, config: DataConfig):
           self.store = HistoricalDataStore(config)
           self.market_data = MarketData(config)
   ```

### Long-Term

1. **Implement MongoDB backend** or remove dead protocol code
2. **Add comprehensive integration tests** for environment isolation
3. **Consider async/await** for IO-bound operations

---

## Appendix: File Metrics

| File | Lines | Classes | Functions | Complexity |
|------|-------|---------|-----------|------------|
| historical_data_store.py | 1779 | 4 | 45+ | High |
| historical_sync.py | 421 | 0 | 8 | Medium |
| historical_queries.py | 199 | 0 | 4 | Low |
| historical_maintenance.py | 461 | 0 | 9 | Medium |
| sessions.py | 549 | 4 | 18 | Medium |
| market_data.py | 790 | 3 | 25 | Medium |
| backend_protocol.py | 473 | 2 | 15 | Low |
| realtime_models.py | 950 | 16 | 40+ | Medium |
| realtime_state.py | 931 | 1 | 55+ | High |
| realtime_bootstrap.py | 1079 | 3 | 35 | High |
| **Total** | **7632** | **33** | **254+** | - |

---

*End of Architecture Review*
