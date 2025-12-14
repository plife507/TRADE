# Backtest Engine Readiness Checklist

**Last Updated:** 2025-12-13  
**Status:** Backtest refactor complete (Phases 0–5)

## Big Picture

This document captured the highest-leverage areas to improve before building the backtest engine. The backtest refactor (Phases 0–5) is now complete. Items marked ✅ are complete; items marked 📋 are future enhancements.

---

## 1. Data Contracts & Time Ranges (Backtest‑Ready)

**Status:** ✅ COMPLETE

- ✅ **Single "data contract" for backtests**
  - Engine expects: symbol, timeframe, exact start/end from system config
  - Required fields: OHLCV (funding/OI optional per system/config)
  - Data layer guarantees:
    - UTC timezone (enforced)
    - Deduplication and sorting (via DuckDB queries)
    - Gap detection available via data tools

- ✅ **Time range utilities**
  - `TimeRange` abstraction exists in `src/utils/time_range.py`
  - System config uses explicit start/end dates or window presets
  - Engine uses config dates directly (no re-implementation)

- ✅ **Gaps & data quality**
  - Warm-up handling: engine extends query range by indicator lookback
  - First valid bar detection: `find_first_valid_bar()` skips warm-up period
  - Gap behavior: handled by DuckDB queries (no forward-fill)
  - Pre-flight: warm-up calculation ensures sufficient data before simulation starts

---

## 2. Strategy Interface & Live/Backtest Symmetry

**Status:** ✅ COMPLETE

- ✅ **Strategy I/O interface locked in**
  - `BaseStrategy` and `Signal` are identical in live vs backtest
  - **`RuntimeSnapshot`** is the canonical strategy input in backtests
  - Multi‑TF support is implemented via cached `FeatureSnapshot`s (HTF/MTF/LTF) on `RuntimeSnapshot`

- ✅ **Snapshot abstraction**
  - Engine constructs **`RuntimeSnapshot`** objects (canonical)
  - Strategies receive a stable, explicit snapshot structure (no ambiguous timestamps)
  - No mode-dependent logic in strategies

- ✅ **Config-driven strategies**
  - All parameters come from system config YAML
  - No hardcoded timeframes, indicator lengths, or thresholds
  - Strategy registry allows dynamic loading by `strategy_id` + `strategy_version`
  - Config sweeping possible without code changes

---

## 3. Execution & Risk Modeling (Simulation Layer)

**Status:** ✅ COMPLETE (Modular Architecture)

- ✅ **Simulated execution interface**
  - `SimulatedExchange` in `src/backtest/sim/exchange.py` (thin orchestrator)
  - Modular architecture with specialized modules:
    - `pricing/` - Price models (mark, spread, intrabar path)
    - `execution/` - Order execution (slippage, liquidity, impact)
    - `ledger.py` - USDT accounting with invariants
    - `funding/` - Funding rate application
    - `liquidation/` - Mark-based liquidation
  - Engine uses `SimulatedExchange` instead of `ExchangeManager`
  - Strategy → `risk_policy` → `risk_manager` → `SimulatedExchange` flow maintained

- ✅ **Fill, slippage, and fees model**
  - **Execution model**: Strategy evaluates at bar close, entry fills at next bar open
  - **TP/SL**: Checked within bar using intrabar path with deterministic tie-break
  - **Fees**: Configurable taker/maker rates from `RiskProfileConfig`
  - **Slippage**: Configurable via `ExecutionConfig` (slippage_bps)
  - **Impact**: Modeled via execution module
  - All assumptions documented in `docs/architecture/SIMULATED_EXCHANGE.md`

- ✅ **Risk manager reuse**
  - `SimulatedRiskManager` for position sizing (same logic as live)
  - `RiskPolicy` for signal filtering (none vs rules)
  - Risk profile configurable via YAML
  - Only execution target differs (simulated vs real exchange)

---

## 4. Reproducibility, Config, and Outputs

**Status:** ✅ COMPLETE

- ✅ **Backtest config format**
  - YAML-based system configs in `src/strategies/configs/`
  - Structure includes:
    - Symbol, timeframe
    - Windows (hygiene/test with start/end or presets)
    - Strategy identifier + parameters
    - Risk profile (equity, leverage, fees, stop conditions)
    - Data build config (env, period, timeframes)
  - Config is the only input (no hidden state)
  - Config loaded via `load_idea_card(idea_card_id)` (IdeaCard system)

- ✅ **Standardized output structure**
  - Results stored in: `data/backtests/{system_id}/{symbol}/{tf}/{window_name}/{run_id}/`
  - Always writes:
    - `result.json` - BacktestResult contract with metrics + config echo + lineage
    - `trades.csv` - Per-trade log with entry/exit, PnL, duration
    - `equity.csv` - Equity curve over time
    - `account_curve.csv` - Proof-grade account state per bar
    - `run_manifest.json` - Run metadata + git + config echo
    - `events.jsonl` - Event log (equity + fills + stop)
  - Includes:
    - Run config snapshot (`BacktestRunConfigEcho`)
    - Summary metrics (PnL, Sharpe, max DD, win rate, etc.)
    - Proof-grade metrics (V2) with comprehensive breakdown
    - System UID (deterministic hash) for lineage tracking
    - Data quality info (warm-up bars, simulation start)

- ✅ **Determinism**
  - Fully deterministic: same config + same data → same results
  - No stochastic components
  - Future: seed parameter can be added to config if needed

---

## 5. Performance & Ergonomics

**Status:** ✅ COMPLETE

- ✅ **Performance**
  - DuckDB queries optimized for sequential scanning
  - Indicators computed once for entire window (vectorized)
  - Bar-by-bar simulation is O(n) where n = number of bars
  - Typical backtest (1 symbol, 1 TF, 3 months) completes in seconds
  - No pre-aggregation needed at current scale

- ✅ **Developer ergonomics**
  - ✅ Backtest smoke test: `python trade_cli.py --smoke backtest`
  - ✅ CLI Backtest menu: Interactive system/window selection
  - ✅ Tools API: `backtest_run_tool(system_id, window_name)`
  - ✅ System listing: `backtest_list_systems_tool()` shows available configs
  - ✅ Artifact inspection: Results written to predictable locations


