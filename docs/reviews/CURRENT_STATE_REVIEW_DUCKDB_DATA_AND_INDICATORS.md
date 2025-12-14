## Current State Review — DuckDB Data + Indicators (Debug-Oriented)

**Scope of this review**
- How the repo currently loads *historical* candles from DuckDB for backtests
- What “indicators” exist today, how they are named, and how they are declared (explicit-only)
- A practical checklist for the next round of debugging (data coverage, env routing, warmup, missing keys, MTF readiness)

This is intentionally **repo-specific** and points at the real implementation files.

---

## 1) System overview (high level)

TRADE is split into three major domains:
- **DATA (shared)**: fetch + store historical market data (DuckDB), plus tools to maintain/query it (`src/data/`, `src/tools/`)
- **SIMULATOR / BACKTEST**: deterministic engine + simulated exchange + runtime snapshot model (`src/backtest/`)
- **LIVE trading**: exchange manager / risk / execution (`src/core/`, `src/exchanges/`) — separate semantics from simulator

For this document we only care about the **backtest/data path**.

---

## 2) Backtest pipeline (what happens when you run a backtest)

### 2.1 Declarative inputs (IdeaCard → FeatureSpecs)

Indicators/features are declared explicitly via **IdeaCards**:
- **Canonical location**: `configs/idea_cards/`
- Loader: `src/backtest/idea_card.py` (`load_idea_card()`)

An IdeaCard contains:
- `symbol_universe`
- `tf_configs` keyed by role: `exec` (required), and optional `htf` / `mtf`
- each `tf_config` can declare `feature_specs` (the indicator declarations)

### 2.2 Engine does (data → indicators → warmup → run)

The backtest engine (`src/backtest/engine.py`) does:
1. **Validate simulator mode locks** (USDT symbol, isolated margin, etc.)
2. **Load OHLCV candles from DuckDB** for the required `(symbol, tf)` and time window
3. **Extend start backwards for warmup** (warmup span depends on indicator lookbacks)
4. **Compute indicators** from declared FeatureSpecs (no silent defaults)
5. **Find first index where all required indicator columns are non-NaN**
6. **Run bar-by-bar simulation** and write artifacts

MTF mode adds:
- load multiple timeframes
- compute per-TF `ts_close`
- build “close timestamp maps” from real data and forward-fill HTF/MTF values between closes

---

## 3) DuckDB data: how “the right data” is selected

### 3.1 Environment routing (live vs demo)

Historical data is stored in **separate DuckDB files** per “data env”:
- `data/market_data_live.duckdb`
- `data/market_data_demo.duckdb`

The storage layer is `src/data/historical_data_store.py`:
- `get_historical_store(env=...)` returns a cached singleton per env
- each env uses **env-specific table names** via `resolve_table_name("ohlcv", env)` (so you get `ohlcv_live` or `ohlcv_demo`)

**Debug implication**: “no data found” is often just **the wrong env**.

### 3.2 Table semantics (OHLCV)

The OHLCV schema is created in `HistoricalDataStore._init_schema()` and includes:
- `symbol` (uppercase normalized)
- `timeframe` (string like `1m`, `1h`, `4h`, `1d`)
- `timestamp` = **bar open time** (UTC-naive storage)
- `open/high/low/close/volume` (+ turnover column in the store schema)

The backtest engine treats:
- `timestamp` as \(ts\_open\)
- `ts_close` as computed: `timestamp + tf_duration(tf)`

### 3.3 Query semantics (get_ohlcv)

Backtests read candles via:
- `HistoricalDataStore.get_ohlcv(symbol, tf, start, end)`

Important details:
- symbol is normalized to uppercase
- DuckDB timestamps are treated as **UTC-naive**
- if `start/end` are timezone-aware, the store strips tzinfo before querying
- query is ordered by timestamp

**Debug implication**: timezone-aware window bounds that don’t match stored naive UTC can lead to confusing coverage results.

### 3.4 Practical “data correctness” checks before debugging strategy logic

When debugging a backtest run, validate these first:
- **env**: are you querying `live` or `demo`? does the DB file have the data you expect?
- **symbol**: in DB it is uppercase (e.g., `BTCUSDT`)
- **timeframe**: must match stored timeframe strings (e.g., `1h`, not `60`)
- **coverage**: does the DB have candles from `(window_start - warmup_span)` through `window_end`?

If those aren’t true, indicator/engine errors downstream will be misleading.

---

## 4) Indicators: what exists today

### 4.1 Supported indicator types

The supported indicator types are defined in `src/backtest/features/feature_spec.py`:
- **Single-output**: `ema`, `sma`, `rsi`, `atr`
- **Multi-output**:
  - `macd` → outputs: `macd`, `signal`, `histogram`
  - `bbands` → outputs: `upper`, `middle`, `lower`, `bandwidth`, `percent_b`
  - `stoch` → outputs: `k`, `d`
  - `stochrsi` → outputs: `k`, `d`

### 4.2 Indicator backend (where math comes from)

`src/backtest/indicator_vendor.py` is the **only** module that imports `pandas_ta`.
Everything else calls the vendor wrappers via the feature system.

### 4.3 Output key naming (critical for “missing indicator” bugs)

Indicators are keyed by **strings** that must match between:
- what the IdeaCard declares (`FeatureSpec.output_key` and multi-output expansion)
- what the runtime reads (`snapshot.indicator_strict("...")` or `TFContext.get_indicator_strict(...)`)

Rules:
- **Single-output** indicators produce exactly the key you declare as `output_key`.
  - Example: `output_key: ema_fast` → runtime key is `ema_fast`
- **Multi-output** indicators expand to multiple keys:
  - If you declare `output_key: macd` and do **not** provide custom `outputs`,
    then keys become:
    - `macd_macd`
    - `macd_signal`
    - `macd_histogram`
  - If you provide `outputs`, you control the exact keys per output name.

**Debug implication**: `KeyError: Indicator 'X' not declared` usually means you used the wrong key string (or forgot to declare it).

---

## 5) How to define indicators (IdeaCard example)

Below is a minimal example of declaring indicators on the **exec** timeframe.

```yaml
id: BTCUSDT_1h_example
version: "1.0.0"
symbol_universe: ["BTCUSDT"]

tf_configs:
  exec:
    tf: 1h
    role: exec
    warmup_bars: 250
    feature_specs:
      - indicator_type: ema
        output_key: ema_fast
        params: { length: 9 }
        input_source: close

      - indicator_type: ema
        output_key: ema_slow
        params: { length: 21 }
        input_source: close

      - indicator_type: rsi
        output_key: rsi_14
        params: { length: 14 }
        input_source: close
```

Notes:
- `exec` is required; `htf`/`mtf` are optional.
- `warmup_bars` is allowed, but the effective warmup also depends on indicator-specific warmup logic.
- Keep your **strategy indicator key strings** aligned to these `output_key` values.

---

## 6) Runtime access: how strategies read indicators (and how to debug keys)

Strategies read indicators via the runtime snapshot (view) layer:
- `src/backtest/runtime/snapshot_view.py`

Useful debug properties/methods:
- `snapshot.available_indicators` → what keys exist on exec TF
- `snapshot.available_htf_indicators` / `snapshot.available_mtf_indicators`
- `snapshot.indicator_strict(name)` → raises if not declared or if NaN
- `snapshot.indicator(name)` → returns `None` if undeclared or NaN

**Debug tactic**: when you hit a KeyError for an indicator, print/log:
- `snapshot.available_indicators` and compare directly to the key you requested.

---

## 7) Debugging checklist (next round)

### 7.1 “No data found … Run data sync first”

Likely causes:
- wrong **data env** (live vs demo)
- wrong timeframe string (e.g. `60` instead of `1h`)
- window outside your DB’s earliest/latest range

What to do:
- inspect `HistoricalDataStore.status()` / `get_database_stats()` for that env
- confirm the requested window *including warmup* is covered

### 7.2 “Indicator ‘X’ not declared”

Likely causes:
- the IdeaCard does not declare that key
- multi-output naming mismatch (`macd_signal` vs `macd_sig` etc.)
- you declared the indicator on HTF/MTF but you’re reading from exec context (or vice versa)

What to do:
- log `snapshot.available_indicators` (and HTF/MTF versions)
- compare strings exactly (case-sensitive)
- confirm your IdeaCard’s `feature_specs` include the indicator on the TF role you’re reading from

### 7.3 “Indicator ‘X’ is NaN … Possible warmup period issue”

Likely causes:
- warmup bars too small for the longest indicator warmup
- insufficient candle history before `window_start` in DuckDB

What to do:
- increase warmup span (or shrink indicator lengths)
- ensure DB coverage extends far enough before the window start

### 7.4 Multi-timeframe readiness / staleness confusion

Symptoms:
- HTF/MTF indicators appear “stuck” for many exec bars

This is expected when:
- HTF/MTF values are forward-filled between TF closes

What to do:
- check `snapshot.htf_is_stale` / `snapshot.mtf_is_stale`
- validate your HTF/MTF candles exist and their `ts_close` map is correct

---

## 8) Quick file map (for targeted debugging)

- **DuckDB storage + queries**: `src/data/historical_data_store.py`
- **IdeaCard schema + loading**: `src/backtest/idea_card.py`
- **FeatureSpec types + naming rules**: `src/backtest/features/feature_spec.py`
- **Indicator backend (pandas_ta wrappers)**: `src/backtest/indicator_vendor.py`
- **Feature computation builder**: `src/backtest/features/feature_frame_builder.py`
- **Engine orchestration + MTF close maps**: `src/backtest/engine.py`
- **Runtime indicator access (strict/optional)**: `src/backtest/runtime/snapshot_view.py`


