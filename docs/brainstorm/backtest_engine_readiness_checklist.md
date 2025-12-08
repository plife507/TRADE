# Backtest Engine Readiness Checklist

## Big Picture

Before building the backtest engine, the main wins are tightening a few **contracts and invariants** so the engine can plug into the existing data, strategy, and risk layers without surprises.

This document captures the highest-leverage areas to improve first.

---

## 1. Data Contracts & Time Ranges (Backtest‑Ready)

- **Clarify a single “data contract” for backtests**
  - Define what the engine expects from the data layer for a run:
    - Symbol set, timeframe(s), exact start/end
    - Required fields (OHLCV, funding, OI)
  - Define what the data layer guarantees:
    - No gaps, or documented gap behavior (error vs forward‑fill)
    - Timezone: UTC only
    - Deduplication and sorting guarantees

- **Tighten time‑range utilities for backtests**
  - Promote a canonical `TimeRange` / period abstraction so backtests use it everywhere instead of raw `start`/`end`/`period` strings.
  - Add explicit helpers like:
    - `TimeRange.last_n_bars(n, timeframe)`
    - `TimeRange.from_period("6M")`
  - The backtest engine should call these helpers rather than re‑implementing logic.

- **Gaps & data quality policy**
  - Decide how a backtest should behave if data has:
    - Missing candles
    - Partial days
    - Missing funding/open interest
  - Implement pre‑flight checks in the data layer:
    - `validate_backtest_dataset(symbols, timeframes, range, env)`
    - Returns a structured report with `ok` / `warnings` / `fatal` statuses.

---

## 2. Strategy Interface & Live/Backtest Symmetry

- **Lock in the strategy I/O interface**
  - Ensure `BaseStrategy` and `Signal` are identical in live vs backtest usage.
  - For multi‑TF:
    - Finalize the `MultiTFSnapshot` (or equivalent) shape.
    - Ensure this is what strategies see in both modes.

- **Snapshot abstraction, not raw rows**
  - The backtest engine should construct the same snapshot objects the live path uses (e.g., `MarketSnapshot` / `MultiTFSnapshot`).
  - Strategies should never depend on whether they are in live or backtest mode.

- **Config‑driven strategies, no hardcoded params**
  - Double‑check strategy configs are entirely parameter‑driven:
    - No hardcoded timeframes, indicator lengths, or thresholds.
  - This allows sweeping configs in backtests without touching strategy code.

---

## 3. Execution & Risk Modeling (Simulation Layer)

- **Define a simulated execution interface that mirrors `ExchangeManager`**
  - Sketch a `SimulatedExchangeManager` (or adapter) with the same methods your strategies and executor currently depend on:
    - Place order, cancel order, get positions, etc.
  - In backtests, the engine calls this simulated exchange instead of the real `ExchangeManager`, while keeping:
    - Strategy → `risk_manager` → `order_executor` unchanged.

- **Decide on fill, slippage, and fees model**
  - Minimal first pass:
    - Market orders fill at OHLCV close or bid/ask mid.
    - Limit orders fill if price trades through the level.
    - Fees: simple constant maker/taker rate from config.
  - Document these assumptions so they are explicit and can be iterated later.

- **Reuse risk manager where possible**
  - Aim for the same risk pipeline in backtest and live:
    - Position sizing, max leverage, daily loss caps.
  - Only the final execution target should differ (simulated vs real exchange).

---

## 4. Reproducibility, Config, and Outputs

- **Lock down a backtest config format**
  - Use a simple YAML/JSON structure for:
    - Symbols, timeframes, time range (`TimeRange`)
    - Strategy name + parameters
    - Environment (live/demo data)
    - Execution model options
  - The config should be the only input to a run (no hidden environment state).

- **Standardized output structure**
  - Decide where results live, e.g.:
    - `backtests/YYYYMMDD_HHMMSS/<run_id>/`
  - Always write:
    - Run config snapshot.
    - Equity curve and per‑trade log.
    - Summary metrics (CAGR, max drawdown, win rate, average R, etc.).
    - Data quality & environment info:
      - Which DuckDB file
      - Which API environment (live/demo data keys)

- **Determinism and seeds**
  - If you add any stochastic components (randomized entry offsets, Monte Carlo, etc.):
    - Define a global `seed` parameter in the config.
    - Centralize random number generation so runs are reproducible.

---

## 5. Performance & Ergonomics

- **Performance expectations up front**
  - Identify target scale for typical backtests, e.g.:
    - Number of symbols × timeframes × years.
  - Test a few DuckDB queries simulating that load.
  - If needed, add:
    - Pre‑aggregated views (e.g. `ohlcv_1h_cached`).
    - Index/ordering checks to keep sequential scanning fast.

- **Developer ergonomics: one‑command sanity check**
  - Before the full engine, add a very small “backtest smoke” command:
    - For example: `python trade_cli.py --backtest-smoke`.
  - This can:
    - Validate data for a standard symbol/timeframe/range.
    - Load a trivial test strategy.
    - Confirm contracts without running a full simulation.


