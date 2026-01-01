## DuckDB Funding / Open Interest / Volume — End-to-End Review + Integration Guide

**Status**: ✅ Review complete (implementation pending)  
**Code version**: `320121f047e3`  
**Date**: 2025-12-17  

### Executive Summary

This system **stores** funding rates and open interest in DuckDB, and **stores** OHLCV (including `volume` and `turnover`). However, the current backtest engine:

- **Consumes OHLCV volume** (kline volume) at runtime (via `FeedStore.volume`).
- **Does not consume funding rates** during backtests (funding cashflows are effectively ignored) even though the simulated exchange **supports** applying funding if events are provided.
- **Does not consume open interest** during backtests (stored/queryable, but not materialized into arrays/features).
- **Silently drops turnover** from the backtest pipeline (present in DB, not queried into backtest frames).

This document has two goals:

- **(A) Trace the current pipeline end-to-end** with code citations so you can audit correctness.
- **(B) Provide a minimal, reviewable integration plan** to wire DuckDB funding rates into backtest PnL with deterministic semantics.

---

## 1) Data ingestion (DuckDB writes)

### 1.1 Table naming & environment mapping

- **Table names** are env-suffixed via `resolve_table_name()` (live/demo).

```148:160:src/config/constants.py
def resolve_table_name(base_table: str, env: DataEnv) -> str:
    """
    Get the table name for a given base table and environment.
    ...
    Returns:
        Full table name with env suffix (e.g., "ohlcv_live", "funding_rates_demo")
    """
    env = validate_data_env(env)
    return f"{base_table}{TABLE_SUFFIXES[env]}"
```

### 1.2 DuckDB schemas + timestamp fields

- **OHLCV**: `(symbol, timeframe, timestamp)` primary key. Timestamp field is named `timestamp`.  
- **Funding**: `(symbol, timestamp)` primary key (no timeframe column).  
- **Open interest**: `(symbol, timestamp)` primary key (no timeframe column).

```301:380:src/data/historical_data_store.py
def _init_schema(self):
    """Initialize database schema with env-specific table names."""
    # OHLCV candle data
    self.conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {self.table_ohlcv} (
            symbol VARCHAR NOT NULL,
            timeframe VARCHAR NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            open DOUBLE,
            high DOUBLE,
            low DOUBLE,
            close DOUBLE,
            volume DOUBLE,
            turnover DOUBLE,
            PRIMARY KEY (symbol, timeframe, timestamp)
        )
    """)
    ...
    # Funding rates data
    self.conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {self.table_funding} (
            symbol VARCHAR NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            funding_rate DOUBLE,
            funding_rate_interval_hours INTEGER DEFAULT 8,
            PRIMARY KEY (symbol, timestamp)
        )
    """)
    ...
    # Open interest data
    self.conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {self.table_oi} (
            symbol VARCHAR NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            open_interest DOUBLE,
            PRIMARY KEY (symbol, timestamp)
        )
    """)
```

### 1.3 Where data is written

- **OHLCV (incl. turnover)** is written during historical sync:

```346:363:src/data/historical_sync.py
def _store_dataframe(store: "HistoricalDataStore", symbol: str, timeframe: str, df: pd.DataFrame):
    """Store DataFrame to DuckDB."""
    ...
    store.conn.execute(f"""
        INSERT OR REPLACE INTO {store.table_ohlcv}
        (symbol, timeframe, timestamp, open, high, low, close, volume, turnover)
        SELECT symbol, timeframe, timestamp, open, high, low, close, volume, turnover
        FROM temp_df
    """)
```

- **Funding rates** are written via `_store_funding()` (insert/replace into `{table_funding}`):

```784:866:src/data/historical_data_store.py
def _store_funding(self, symbol: str, df: pd.DataFrame):
    """Store funding rate DataFrame in DuckDB."""
    ...
    self.conn.execute(f"""
        INSERT OR REPLACE INTO {self.table_funding} (symbol, timestamp, funding_rate)
        SELECT symbol, timestamp, funding_rate FROM df
    """)
```

- **Open interest** is written via `_store_open_interest()` (insert/replace into `{table_oi}`):

```1038:1120:src/data/historical_data_store.py
def _store_open_interest(self, symbol: str, df: pd.DataFrame):
    """Store open interest DataFrame in DuckDB."""
    ...
    self.conn.execute(f"""
        INSERT OR REPLACE INTO {self.table_oi} (symbol, timestamp, open_interest)
        SELECT symbol, timestamp, open_interest FROM df
    """)
```

### 1.4 Funding storage semantics

- **Funding is stored as discrete events** (YES), not a per-bar series.
  - Evidence: funding table has **no timeframe column**, and includes `funding_rate_interval_hours` default 8.

```339:347:src/data/historical_data_store.py
CREATE TABLE IF NOT EXISTS {self.table_funding} (
    symbol VARCHAR NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    funding_rate DOUBLE,
    funding_rate_interval_hours INTEGER DEFAULT 8,
    PRIMARY KEY (symbol, timestamp)
)
```

---

## 2) Data extraction / prep (DuckDB → backtest frames)

### 2.1 What the backtest engine loads from DuckDB today

- **Engine backtest prep loads OHLCV only** (YES). It does **not** query funding or open interest in the preparation path.

```455:488:src/backtest/engine.py
store = get_historical_store(env=self.config.data_build.env)
...
# Load extended data
df = store.get_ohlcv(
    symbol=self.config.symbol,
    tf=self.config.tf,
    start=extended_start,
    end=requested_end,
)
```

### 2.2 Funding queried anywhere in backtest “prep”?

- **Only in preflight tooling**, where funding is queried for **coverage checks**, not to build runtime series/arrays.

```260:294:src/tools/backtest_tools.py
# Check funding data if required
funding_df = store.get_funding(
    symbol=config.symbol,
    start=load_window.load_start,
    end=load_window.load_end,
)
funding_ts = funding_df["timestamp"].tolist() if not funding_df.empty else []
...
health_check = DataHealthCheck(
    ...
    required_series=["ohlcv", "funding"],
)
...
timestamps_by_series_tf={
    "ohlcv": timestamps_by_tf,
    "funding": {config.tf: funding_ts},  # Funding has no TF but we key it for consistency
},
```

### 2.3 Alignment to exec `ts_close` / `ts_close_ms`

- **Funding / OI are not aligned to exec `ts_close_ms` anywhere today** (NO). There is no resample/ffill/join into the backtest frame used to build `FeedStore`.
- The only alignment-related logic is **preflight coverage tolerance** for funding (8h schedule).

```19:21:src/backtest/runtime/data_health.py
# Funding happens every 8 hours, so allow this tolerance for coverage checks
FUNDING_INTERVAL_TOLERANCE = timedelta(hours=8)
```

---

## 3) Runtime exposure (FeedStore / RuntimeSnapshotView)

### 3.1 Are funding rate and open interest exposed as arrays?

- **Funding rate in FeedStore arrays**: **NO**  
- **Open interest in FeedStore arrays**: **NO**

`FeedStore` only contains OHLCV arrays and indicator arrays.

```1:82:src/backtest/runtime/feed_store.py
Provides O(1) array access for the hot loop:
- OHLCV arrays (open, high, low, close, volume)
- Indicator arrays (ema_fast, ema_slow, rsi, atr, etc.)
...
# Core OHLCV as numpy arrays
ts_open: np.ndarray
ts_close: np.ndarray
open: np.ndarray
high: np.ndarray
low: np.ndarray
close: np.ndarray
volume: np.ndarray

# Indicator arrays
indicators: Dict[str, np.ndarray] = field(default_factory=dict)
```

### 3.2 Can `RuntimeSnapshotView.get_feature()` access funding/OI today?

- **Funding**: **NO**  
- **Open interest**: **NO**  
- **Turnover**: **NO** (see section 5.2)

`get_feature()` supports only OHLCV keys `open/high/low/close/volume` and keys present in `feed.indicators`.

```500:589:src/backtest/runtime/snapshot_view.py
def get_feature(self, indicator_key: str, tf_role: str = "exec", offset: int = 0) -> Optional[float]:
    ...
    # Handle OHLCV keys
    if indicator_key == "open":
        return float(feed.open[target_idx])
    elif indicator_key == "high":
        return float(feed.high[target_idx])
    elif indicator_key == "low":
        return float(feed.low[target_idx])
    elif indicator_key == "close":
        return float(feed.close[target_idx])
    elif indicator_key == "volume":
        return float(feed.volume[target_idx])

    # Handle indicator keys
    if indicator_key not in feed.indicators:
        return None
```

### 3.3 Where do funding/OI drop out?

- They drop out at **engine data preparation**: only OHLCV is loaded into `df` for backtests (no join against funding/OI), which means `FeedStore` never sees them.

```455:488:src/backtest/engine.py
df = store.get_ohlcv(...)
```

---

## 4) PnL / cashflow modeling (funding)

### 4.1 Is funding cashflow applied to equity today?

- **In backtests end-to-end**: **NO (effectively ignored)**  
- **In the simulated exchange model (if events provided)**: **YES**

#### Exchange supports applying funding if `funding_events` are passed

```306:387:src/backtest/sim/exchange.py
def process_bar(..., funding_events: Optional[List[FundingEvent]] = None) -> StepResult:
    ...
    funding_result = self._funding.apply_events(
        funding_events or [], prev_ts, step_time, self.position
    )
    if funding_result.funding_pnl != 0:
        self._ledger.apply_funding(funding_result.funding_pnl)
```

#### Ledger applies funding into cash balance (equity)

```234:254:src/backtest/sim/ledger.py
def apply_funding(self, funding_pnl: float) -> LedgerUpdate:
    self._cash_balance_usdt += funding_pnl
    self._recompute_derived()
```

#### But engine never passes events into `process_bar()`

```1097:1124:src/backtest/engine.py
for i in range(num_bars):
    ...
    step_result = self._exchange.process_bar(bar, prev_bar)
```

### 4.2 Funding timestamp semantics (if wired)

Funding adapters + funding model consistently treat events as applying within the window **(prev_ts, ts]**:

```61:96:src/backtest/sim/adapters/funding_adapter.py
def adapt_funding_rows(...):
    """
    Convert funding rows to events, filtering to time window (prev_ts, ts].
    ...
    """
```

---

## 5) Volume semantics (OHLCV vs other series)

### 5.1 What “volume” strategies can access today

- **YES**: kline OHLCV `volume` is available at runtime as `volume` in `get_feature()`.

```541:552:src/backtest/runtime/snapshot_view.py
elif indicator_key == "volume":
    return float(feed.volume[target_idx])
```

### 5.2 Turnover is stored but not used in backtests

- **Stored in DuckDB** (YES): OHLCV schema includes `turnover`.

```305:315:src/data/historical_data_store.py
timestamp TIMESTAMP NOT NULL,
...
volume DOUBLE,
turnover DOUBLE,
```

- **Written during sync** (YES): insert includes turnover.

```358:362:src/data/historical_sync.py
(symbol, timeframe, timestamp, open, high, low, close, volume, turnover)
SELECT symbol, timeframe, timestamp, open, high, low, close, volume, turnover
```

- **Not queried into backtest OHLCV frames** (NO): backtest OHLCV query omits turnover (this is a silent drop).

```1177:1181:src/data/historical_data_store.py
query = f"""
    SELECT timestamp, open, high, low, close, volume
    FROM {self.table_ohlcv}
    WHERE symbol = ? AND timeframe = ?
"""
```

### 5.3 Any buy/sell volume, delta, etc. available to strategies?

- **NO**: there are no runtime features/arrays for buy/sell volume, delta, or similar derived volume series in the backtest pipeline today (only OHLCV `volume` plus indicators computed from the OHLCV frame).

---

## 6) Gaps & risks (silent drops + long-horizon correctness)

### 6.1 Silent drops / mismatches

- **Funding exists in DuckDB but is ignored by engine** (silent drop):
  - Engine does not pass events to exchange: see `process_bar()` call above.
- **Open interest exists in DuckDB but is ignored** (silent drop):
  - No join into prepared frame; not in `FeedStore`; not in `get_feature()`.
- **Turnover exists in DuckDB but is ignored** (silent drop):
  - Written and stored, but not queried into backtest frame.
- **Preflight may require funding coverage** even though runtime ignores funding:
  - Preflight queries `get_funding()` and requires `["ohlcv","funding"]`.

```281:288:src/tools/backtest_tools.py
health_check = DataHealthCheck(
    ...
    required_series=["ohlcv", "funding"],
)
```

### 6.2 Long-horizon perp backtest correctness

If you run long-horizon perps backtests without funding cashflows:

- **PnL/equity curves are materially wrong** for strategies that hold positions across funding timestamps.
- Performance comparisons between strategies can be skewed (funding dominates for some regimes).

---

## Integration Guide: Wire funding cashflows into backtests (minimal change)

### Goal

Make backtests apply funding by:

1. Loading funding rows from DuckDB once for the run window
2. Converting to `FundingEvent` list (sorted)
3. Slicing events per bar into **(prev_ts, ts_close]**
4. Passing them into `SimulatedExchange.process_bar(..., funding_events=...)`

### Decision you must make (behavior change policy)

- **Option A — Always-on funding in simulator** (recommended for perps; build-forward):
  - Pros: correct by default for perps; simplest wiring.
  - Cons: changes backtest results immediately for existing IdeaCards.

- **Option B — Explicit “funding enabled” config gate** (strict mode / fail-loud):
  - Pros: prevents silent behavior changes; makes intent explicit.
  - Cons: requires introducing a new config field and migrating all IdeaCards/SystemConfigs that should run.

This repo generally prefers **build-forward** + **no silent defaults**; you’ll want to pick one explicitly before implementing.

### Minimal implementation sketch (engine-side)

This is intentionally written as a small, reviewable patch to `BacktestEngine.run()`; it does not change strategy APIs or `FeedStore`.

```python
from datetime import timedelta

def _load_funding_events_for_exec_range(store, symbol: str, start_ts, end_ts):
    from src.backtest.sim.adapters.funding_adapter import adapt_funding_dataframe

    # Buffer to avoid edge misses at window boundaries
    q_start = start_ts - timedelta(hours=8)
    q_end = end_ts + timedelta(hours=8)

    df = store.get_funding(symbol=symbol, start=q_start, end=q_end)
    if df is None or df.empty:
        return []

    # HistoricalDataStore.get_funding returns timestamp,funding_rate (no symbol column)
    df = df.copy()
    df["symbol"] = symbol

    return adapt_funding_dataframe(df)

# In BacktestEngine.run(), after exec_feed is available:
store = get_historical_store(env=self.config.data_build.env)
all_funding_events = _load_funding_events_for_exec_range(
    store=store,
    symbol=self.config.symbol,
    start_ts=exec_feed.get_ts_close_datetime(0),
    end_ts=exec_feed.get_ts_close_datetime(num_bars - 1),
)
funding_ptr = 0

# In the bar loop, before process_bar():
prev_ts = prev_bar.ts_close if prev_bar is not None else None
step_events = []
while funding_ptr < len(all_funding_events) and all_funding_events[funding_ptr].timestamp <= bar.ts_close:
    ev = all_funding_events[funding_ptr]
    if prev_ts is None or ev.timestamp > prev_ts:
        step_events.append(ev)
    funding_ptr += 1

step_result = self._exchange.process_bar(bar, prev_bar, funding_events=step_events)
```

### Expected outputs after wiring funding

The exchange metrics collector already tracks funding PnL and event counts. After wiring, you should see these become non-zero for runs holding positions across funding times:

```40:79:src/backtest/sim/metrics/metrics.py
# Funding metrics
total_funding_pnl_usdt: float = 0.0
funding_events_count: int = 0
...
def to_dict(self) -> Dict[str, Any]:
    return {
        ...
        "total_funding_pnl_usdt": self.total_funding_pnl_usdt,
        "funding_events_count": self.funding_events_count,
        ...
    }
```

---

## Validation checklist (CLI-first, no pytest)

### Step 0 — Confirm you have funding rows

Use your existing CLI tooling (`get_funding_history_tool` via smoke suite) or inspect DuckDB directly. The key is: funding rows must exist in `{funding_rates_live|funding_rates_demo}` for the window.

### Step 1 — Compile

Run:

- `python -m py_compile src/backtest/engine.py`

### Step 2 — Preflight coverage (already checks funding)

Run:

- `python trade_cli.py backtest preflight --idea-card <card> --start <date> --end <date> --json`

Expectation:
- Preflight should pass for both OHLCV and funding coverage (subject to the funding 8h tolerance).

### Step 3 — Run backtest and confirm funding metrics change

Run:

- `python trade_cli.py backtest run --idea-card <card> --start <date> --end <date> --json`

Expectation:
- `total_funding_pnl_usdt` and `funding_events_count` should be non-zero **if** the strategy holds positions across funding timestamps.

### Step 4 — Regression gates

Run (these should remain unchanged by funding wiring):

- `python trade_cli.py backtest audit-toolkit --json`
- `python trade_cli.py backtest phase2-audit --idea-card verify/<card> --start <date> --end <date> --json`
- `python trade_cli.py backtest audit-snapshot-plumbing --idea-card <card> --start <date> --end <date> --json`

---

## Follow-on integrations (not part of the minimal funding wiring)

### Expose funding rate to strategies as a per-bar feature (future)

To make `snapshot.get_feature("funding_rate", ...)` work, you’d need:

- A per-bar series aligned to exec `ts_close` (likely forward-filled between funding events)
- A place to store it (either as a new OHLCV-like array on `FeedStore`, or as an “indicator” column produced during frame prep)

### Expose open interest to strategies (future)

Similar requirements as funding:

- Decide semantics (raw OI events at 1h cadence, per-bar series, forward-fill policy)
- Align to exec `ts_close`
- Add to `FeedStore` / `get_feature()` key space

---

## Appendix: Quick answers (YES/NO)

- **Funding stored as discrete events in DuckDB?** YES.  
- **Open interest stored in DuckDB?** YES.  
- **Backtest prep queries funding for runtime use?** NO (only preflight coverage).  
- **Backtests apply funding cashflows to equity today?** NO (engine doesn’t pass events).  
- **Simulator has funding model implemented?** YES (event-driven).  
- **Snapshot API exposes funding or OI as features today?** NO.  
- **Strategies can access volume today?** YES (OHLCV volume).  
- **Strategies can access turnover today?** NO (stored, but not loaded).  


