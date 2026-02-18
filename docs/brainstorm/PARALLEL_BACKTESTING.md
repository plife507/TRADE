# Parallel Backtesting in TRADE (DuckDB + Process Workers)

This note is a **brainstorm + implementation-ready design** for running large Play suites quickly and safely in parallel in this codebase.

It’s written to match TRADE’s existing philosophy:

- **Sync once, run many** (single writer, many readers)
- **Deterministic runs** (hashes + stable artifact layout)
- **Gates before execution** (preflight should be real, not vibes)
- **No accidental DB corruption** (Windows file locking realities)

If you only read one section, read **“The Golden Path”**.

---

## TL;DR (The Golden Path)

### The fastest *correct* parallel model

**Phase A — Serial (single process, allowed to write):**

1. Pick suite window (start/end).
2. For each Play (or for a manifest), run **preflight with auto-sync** so DuckDB is complete and 1m coverage is guaranteed.
3. After this phase finishes, **no process writes to DuckDB** until all backtests complete.

**Phase B — Parallel (many processes, read-only):**

1. Spawn workers using `ProcessPoolExecutor`.
2. In each worker process:
   - call `reset_stores(force_read_only=True)` first
   - run `backtest_run_play_tool(..., skip_preflight=True, sync=False)`

This is already the intended design of:

- `src/engine/runners/parallel.py`
- `src/data/historical_data_store.py` (read-only connection mode + `reset_stores`)
- `src/tools/backtest_play_tools.py` (explicit `skip_preflight` path)

---

## Where the code already supports this (references)

### 1) Read-only DuckDB per process (safe parallel readers)

`HistoricalDataStore` supports `read_only=True`, and `reset_stores(force_read_only=True)` flips a process-level flag so all future store access is read-only.

- File: `src/data/historical_data_store.py`
  - `HistoricalDataStore.__init__(..., read_only: bool = False)` opens: `duckdb.connect(..., read_only=read_only)`
  - `reset_stores(force_read_only=True)` sets `_force_read_only`
  - `get_historical_store()` returns **fresh read-only instances** when `_force_read_only` is set

Why this matters:

- DuckDB is excellent at **concurrent reads**.
- DuckDB is *not* a “many writers” database.
- On Windows, file locks are not forgiving—this design avoids the pain.

### 2) Parallel runner exists (process pool)

File: `src/engine/runners/parallel.py`

It already does the correct “child process first line”:

- `reset_stores(force_read_only=True)` before DB imports are used
- `skip_preflight=True` in the worker (expects the parent to have synced already)

### 3) Preflight gate does the right “data correctness” work

File: `src/backtest/runtime/preflight.py`

Key properties:

- Computes warmup requirements once (`compute_warmup_requirements(play)`)
- Validates coverage, monotonic timestamps, duplicates, alignment sanity
- Enforces **mandatory 1m coverage** for all plays
- Validates **exec→1m mapping feasibility**
- When enabled, **auto-sync goes through tools** (important discipline)

### 4) Data fixing goes through tools (and tools write)

Files:

- `src/backtest/runtime/preflight.py` (auto-sync calls tools)
- `src/tools/data_tools_sync.py` and friends
- `src/tools/backtest_play_tools.py` (`sync=True` default; and `skip_preflight` exists)

This separation is exactly what we want:

- **Sync/heal** = write work (serial)
- **Backtest** = read work (parallel)

---

## What limits “parallel backtesting” in practice?

When you parallelize backtests, you’re parallelizing three very different workloads:

1. **DB reads (I/O bound)**: DuckDB reading candles into pandas.
2. **Indicator computation (CPU bound)**: applying feature specs across frames.
3. **Simulation loop (CPU bound)**: stepping bars, exchange sim, risk logic.

Common failure mode:

- “I set workers = 32 and it got slower.”

Why:

- Disk becomes the bottleneck first if every worker loads large overlapping ranges.
- CPU becomes bottleneck once data is cached in OS page cache.
- On Windows, too many concurrent readers can thrash the file system cache.

Rule of thumb:

- Start with **min(physical_cores - 1, 8)** workers, then tune.

---

## The big danger: “read-only workers” are only safe if nothing writes

Parallel readers are safe **only if writes are not happening simultaneously**.

In your codebase, there are multiple ways data can be written:

- `HistoricalDataStore.sync*()` calls
- `fill_gaps()`, `heal()`
- live/demo candle upserts (different DB env, but still: don’t mix in the same file)

### Concrete policy (recommended)

- **During Phase B (parallel backtests):**
  - Disable all sync / heal
  - Ensure `skip_preflight=True` and `sync=False`
  - Ensure data tools are not being called concurrently from another process

The simplest enforcement mechanism:

- Use a “suite runner” wrapper that does:
  - serial sync gate
  - then parallel run gate
  - never both at once

---

## Artifact collisions: the subtle parallel bug

### Why this is easy to miss

Your runner creates deterministic artifact folders using hashes.

File: `src/backtest/runner.py`

It builds a stable run folder:

- `play_hash` + window + universe + other components → `InputHashComponents.compute_short_hash()` → `run_id`
- output folder is created from that

In a parallel context:

- If two workers execute the **same Play with the same window** simultaneously, they will compute the **same run folder**.
- That can lead to:
  - file write races
  - partial artifacts
  - corrupted `index.jsonl` style logs

### Two safe strategies

**Strategy A (preferred):**

- Ensure each parallel job is unique: one run per Play/window combo.

**Strategy B (explicit override / suffix):**

- Add an `attempt_id` or a `run_nonce` included in artifact path generation.
- Tradeoff: you lose strict identity mapping between config and artifacts.

Given TRADE’s determinism goals, Strategy A is typically correct.

---

## The practical runbooks

### Runbook 1: Parallel Play suite (real data)

Goal: run N plays over a fixed real-data window fast.

**Phase A — Sync window serially**

- Compute the union set of:
  - symbols (likely `play.symbol_universe[0]` for each)
  - timeframes (all required by each play including mandatory `1m`)
  - window start/end expanded by warmup + safety buffer

Then run a serial sync:

```bash
# Example pattern (exact flags depend on your CLI subcommands)
python trade_cli.py data sync-range --symbols BTCUSDT,ETHUSDT --tf 1m,5m,15m,1h,4h,D --start 2025-01-01 --end 2025-06-30 --env backtest
python trade_cli.py data sync-data --symbol BTCUSDT --tf 1m --env backtest
python trade_cli.py data sync-data --symbol BTCUSDT --tf 15m --env backtest
```

Then run preflight for each Play (still serial, or at most lightly parallel but **no sync** here):

```bash
python trade_cli.py backtest preflight --play PLAY_A --start 2025-01-01 --end 2025-06-30 --sync
python trade_cli.py backtest preflight --play PLAY_B --start 2025-01-01 --end 2025-06-30 --sync
```

**Phase B — Run in parallel**

- Spawn workers
- `reset_stores(force_read_only=True)` in each child
- call `backtest_run_play_tool(..., skip_preflight=True, sync=False)`

This is exactly the pattern in `src/engine/runners/parallel.py`.

### Runbook 2: Parallel suite (synthetic)

Synthetic is special:

- It **never touches DuckDB** when `use_synthetic=True`.
- That means you can run synthetic suites at very high parallelism safely.

In `src/tools/backtest_play_tools.py`, synthetic mode sets `skip_preflight=True` automatically and uses a `SyntheticCandlesProvider`.

Recommendation:

- For synthetic suites: crank workers higher (CPU bound).
- For real-data suites: cap workers (I/O bound).

---

## “Should we sink all missing candles then run tests in memory in parallel?”

Yes. You’re already architected for that:

- Preflight auto-sync uses tools (safe, serializable).
- Backtest execution loads data into pandas and computes indicators.
- The sim loop operates on in-memory arrays / DataFrames.

### Why this is the “best of both worlds”

- **Correctness**: the DB is the canonical historical store; preflight ensures it’s clean.
- **Speed**: once loaded, simulation is CPU-only.
- **Parallel safety**: read-only DB access avoids locking.

### What you should *not* do

- Try to “sync missing candles” concurrently from multiple workers.
  - Even if you add a lock, you’ll serialize and add overhead.
  - Also, concurrent writes are where DuckDB is most fragile on Windows.

---

## How to use DuckDB in parallel (in this repo)

### The supported pattern

- Each worker is a **separate OS process**
- Each worker opens DuckDB in **read-only mode**
- No worker writes to DuckDB

Your code already enforces this with:

- `reset_stores(force_read_only=True)`
- `duckdb.connect(..., read_only=True)`

### What about threads instead of processes?

Threads are not ideal here because:

- Python GIL will throttle CPU-heavy indicator + simulation work.
- DuckDB connections aren’t designed to be shared freely across threads.

If you want concurrency in a single process, use it for:

- orchestrating IO-bound tasks (but again: backtests quickly become CPU bound)

Processes are correct.

---

## DB alternatives: which ones are actually worth it?

The big question is: **what problem are you solving?**

### If your primary problem is “suite runs are slow locally”

Best upgrades (lowest risk):

1. **Stay with DuckDB** (it’s already integrated)
2. Add **Parquet mirror** (see below)
3. Improve cache behavior and avoid repeated loads

### If your primary problem is “multiple machines / shared data / central store”

You’ll want a server DB:

- **Postgres + TimescaleDB**
  - Pros: reliable, concurrent writers/readers, ecosystem
  - Cons: ops complexity, often slower for large scans than columnar
- **ClickHouse**
  - Pros: extremely fast analytics, concurrency, compression
  - Cons: more infra + query model changes

### If your primary problem is “store is too big / ingestion too slow”

Consider:

- **Parquet partitioned dataset** as the canonical store
  - store each symbol/tf partition separately
  - reads become “open only what you need”

---

## Parquet as the “parallel backtesting accelerator”

This is the most realistic next step if you want faster parallel suite runs without leaving your current architecture.

### The idea

Keep DuckDB as:

- metadata store / integrity checks / convenient queries

But store candles as:

- Parquet files partitioned by:
  - `env=backtest|demo|live`
  - `symbol=BTCUSDT`
  - `timeframe=1m`

Then:

- each worker reads only the partitions needed for its Play/window
- OS caching works better
- you avoid a single huge `.duckdb` file becoming the hotspot

### Tradeoffs

- You need to define “canonical truth” (DuckDB vs Parquet).
- You need a compaction story.

### A pragmatic middle ground

- DuckDB remains canonical.
- A nightly/commanded export creates Parquet mirrors for hot ranges.
- Backtests can prefer Parquet if available, otherwise DuckDB.

---

## Advanced: job batching and cache locality

When running 100+ plays, many share:

- same symbol
- same exec TF
- similar windows

### Optimization: group plays by data signature

Compute a signature:

- `(env, symbol, tf_set, window_start, window_end)`

Then run a batch of plays with the same signature in the same worker process sequentially.

Why:

- reduces repeated DB reads
- reduces repeated indicator computations (if you cache feature frames by tf)

This can outperform “one play per worker task” even with fewer workers.

---

## Recommended roadmap (actionable, codebase-aligned)

### P0: Adopt the existing parallel runner everywhere

- Standardize parallel suites on `src/engine/runners/parallel.py`
- Ensure parent orchestration always does “sync gate” before parallel run

### P1: Build a “suite manifest” for real-data runs

In `docs/TODO.md`, you already have a `REAL_DATA_SYNC_MANIFEST` concept in the validation tier. Extend that pattern:

- manifest entries define:
  - symbols
  - TFs
  - date window

Then suite execution is deterministic and reproducible.

### P2: Artifact collision hardening

Enforce “one job per Play/window” or incorporate an explicit `attempt_id` knob.

### P3: Add Parquet mirror (optional, high ROI)

Only if suite time is still dominated by I/O.

---

## Appendix: concrete “worker-safe” rules

### In worker processes

- MUST call `reset_stores(force_read_only=True)` before any data-store usage
- MUST set `skip_preflight=True`
- MUST set `sync=False`
- MUST NOT call any data tool that mutates DuckDB

### In parent process

- MUST do data sync/heal serially
- MUST run a full preflight gate at least once per Play/window class
- MUST ensure 1m coverage exists and exec→1m mapping passes (preflight already does this)

---

## Appendix: quick reference to relevant files

- `src/engine/runners/parallel.py` — process pool parallel backtests
- `src/data/historical_data_store.py` — DuckDB store, read-only mode, singleton reset
- `src/backtest/runtime/preflight.py` — coverage/gaps + auto-sync discipline, mandatory 1m checks
- `src/tools/backtest_play_tools.py` — golden-path tool wrapper; `skip_preflight` support
- `src/backtest/runner.py` — gates runner + deterministic artifact generation

