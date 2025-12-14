# Forecast-Driven Backtest Engine & Strategy Factory  
_Vision and Roadmap_

## 0. Context and End Goal

You already have:

- A DuckDB-based historical data store.
- A data builder tool that populates DuckDB.
- A vision for a **strategy factory**:
  - Systems defined by configs (symbol, timeframe, parameters, risk).
  - Hygiene → Test → Demo → Live lifecycle.
- Plans for **agentic orchestration** and automation.

Your end goal:

> A self-healing, self-correcting, agentic trading bot that:
> - Continuously tests and refines strategies.
> - Incorporates a forecasting agent.
> - Chooses and mixes strategies based on forecasts.
> - Expands across symbols, markets, and leverage profiles over time.

This document outlines how to get there in stages.

---

## Stage 0 – Stabilize the Core Backtest Engine

**Status:** ✅ COMPLETE (Refactor complete — Phases 0–5)

### Goals (Achieved)

- ✅ One clean, boring backtest pipeline.
- ✅ Single source of truth for a "system" (strategy + parameters + windows).
- ✅ Strict hygiene vs test separation.

### Actions (Completed)

1. ✅ **System config format** - YAML-based configs in `src/strategies/configs/`

Each system has one config describing:
- ✅ Symbol (e.g. BTCUSDT)
- ✅ Primary timeframe (e.g. 5m)
- ✅ Hygiene window (start/end dates or presets)
- ✅ Test window (start/end dates or presets)
- ✅ Strategy identifier (e.g. ema_rsi_atr)
- ✅ Strategy parameters (indicator lengths, thresholds, RR, etc.)
- ✅ Risk profile (risk per trade, max leverage, fees, stop conditions)

2. ✅ **Single backtest pipeline** - `src/backtest/engine.py`

For a given system and window:
- ✅ Read candles from DuckDB with proper warm-up
- ✅ Compute indicators once for the entire window (EMA, RSI, ATR, no look-ahead)
- ✅ Loop bar-by-bar, in time order:
  - Build `RuntimeSnapshot` (canonical) from bar + cached features + exchange state
  - Call strategy to generate signals
  - Pass signals through risk policy and risk manager
  - Simulate execution via modular `SimulatedExchange`
- ✅ At the end, produce:
  - Metrics summary (PnL, max DD, Sharpe, trade count, etc.)
  - Proof-grade metrics (V2) with comprehensive breakdown
  - Trades list (trades.csv)
  - Equity curve (equity.csv)
  - Full result (result.json)
  - Account curve (account_curve.csv)
  - Run manifest (run_manifest.json)
  - Event log (events.jsonl)

3. ✅ **Hygiene vs test wiring**

- ✅ Run engine via `backtest_run_tool(system_id, window_name)`
- ✅ Results stored in `data/backtests/{system_id}/{symbol}/{tf}/{window_name}/{run_id}/`
- ✅ Clear labeling as "hygiene" or "test" in window_name

**Outcome:** ✅ Solid spine complete with modular exchange architecture + canonical timing + RuntimeSnapshot + MTF caching + mark unification. Tools/CLI integration is complete; remaining work is future instrumentation for ML datasets/forecasting.

---

## Stage 1 – Instrumentation for Future Forecasting

**Status:** 📋 FUTURE (Phase 3)

Before building a forecasting agent, you need data that models can learn from. That comes from how backtests log information.

**Note:** The backtest refactor (Phases 0–5) is complete. This stage builds on top of the existing artifact structure and adds “learning-ready” per-bar exports.

### Goals

- Record not just final metrics, but per-bar context and outcomes.
- Make future supervised learning datasets easy to extract.

### Actions

1. **Define what a "training row" looks like**

For each bar, you will eventually want:

- Time.
- Symbol and timeframe.
- All features available to the strategy at that time (snapshot flattened):
  - price features
  - indicator values
  - multi-timeframe summaries
  - position/account state features (if needed).
- A strategy identifier, where applicable.

2. **Define future targets**

Examples of targets (no need to implement all at once):

- Next N bars return over a chosen horizon (e.g. next 24 hours on 1h).
- Next N bars volatility.
- Regime label for the next horizon (trend up, trend down, chop, crash).
- For each strategy:
  - Forward performance of that strategy from this bar over N bars
  - (PnL, max DD, risk-adjusted metrics, etc.).

3. **Extend backtest logging**

As backtests run:

- Log per-bar features.
- Log per-bar realized outcomes over your chosen horizons (computed outside the strategy logic).
- Keep the schema stable so it can be reused for training datasets.

Outcome: backtests now produce rich logs, not just final metrics.

---

## Stage 2 – Define the Forecasting "Contract"

Decide what a forecasting agent is allowed to say and what it sees as input.

### Goals

- One clear forecast horizon to start with.
- A fixed forecast output schema.
- Clean input features aligned with what strategies already see.

### Actions

1. **Choose an initial forecast horizon**

Examples:

- Next 24 hours on 1h bars.
- Next 12 bars on 15m.

Pick one horizon H₁ for version 1 and commit to it.

2. **Define forecast output**

For each forecast, define fields such as:

- Horizon identifier (e.g. H₁).
- Expected return over H₁.
- Expected volatility over H₁.
- Regime class:
  - trend_up
  - trend_down
  - chop
  - crash
- Confidence score.

3. **Define forecast inputs**

- Use the same feature set as the strategy snapshot (or a superset):
  - recent prices and returns
  - indicators
  - volatility and trend measures
  - multi-timeframe aggregates
- No future information is allowed.

Outcome: a clear contract:
"Given features at time t, the forecaster outputs a forecast object for horizon H₁."

---

## Stage 3 – Build Training Datasets from Historical Backtests

Use the enriched logs from Stage 1 to build datasets for forecasting and strategy selection.

### Goals

- One dataset for market-level forecasting.
- One dataset for per-strategy forward performance.

### Actions

1. **Market forecasting dataset**

For each timestamp t in historical data:

- Input:
  - Feature vector at t (snapshot features).
- Target:
  - Market outcomes between t and t + H₁:
    - return
    - volatility
    - regime label

This dataset trains a model to answer:
"Given state at t, what will the market likely do over the next H₁?"

2. **Strategy selection dataset**

Using backtest results for multiple strategies:

- For each time t and each strategy S:
  - Input:
    - Features at t.
    - Static information about S (style tags, timeframes, risk profile).
  - Target:
    - Forward performance of S from t to t + H₁:
      - PnL, risk-adjusted return, max DD, etc.

This dataset supports:
"Given the current environment, which strategy is likely to perform best over H₁?"

3. **Store these datasets cleanly**

- Export them from DuckDB (or build them via DuckDB queries).
- Keep a stable schema for:
  - Feature columns.
  - Target columns.
  - Strategy identifiers.

Outcome: you now have two supervised learning problems defined and ready.

---

## Stage 4 – First Forecasting Agent and Simple Policy (Offline Only)

Introduce forecasting as a separate layer, but keep everything offline for now.

### Goals

- A basic forecasting agent for H₁.
- A simple policy that maps forecasts to strategy choices.
- Offline evaluation of the composite.

### Actions

1. **Train a basic forecaster**

Using the market forecasting dataset:

- Train a simple model to predict:
  - expected return
  - volatility
  - regime
  for horizon H₁.

No need for complexity at first; the goal is to validate the pipeline.

2. **Design a simple policy**

Define a rule-based or simple learned mapping:

- Inputs:
  - Forecast object (expected return, vol, regime, confidence).
- Outputs:
  - Which strategies to turn on or off.
  - Optionally, how much weight or risk to assign to each.

Examples:

- If forecast regime = trend_up and volatility is moderate:
  - Enable trend strategies; disable mean-reversion.
- If volatility is very high and forecast is uncertain:
  - Reduce risk or stay flat.

3. **Evaluate the composite offline**

Define a composite system:

- Forecaster id and version.
- Policy id and version.
- Strategy pool (list of candidate strategies).

Run a backtest over historical data where:

- On each bar:
  - The forecaster produces a forecast.
  - The policy chooses which strategy or combination to run.
  - The chosen strategies generate signals.
  - The backtest engine simulates trades as usual.

Compare results against baseline systems:

- Always running a single fixed strategy.
- Equal-weight blending of strategies.

Outcome: proof that "forecast + policy + strategy pool" can be treated as a system and evaluated like any other.

---

## Stage 5 – Integrate Forecasting into the System Lifecycle

Once the composite works offline, embed it in the same lifecycle as your other systems.

### Goals

- Use the same hygiene → test → demo → live pipeline.
- Let the orchestrator treat forecast-driven composites as first-class citizens.

### Actions

1. **Extend system configs**

For a composite system, configs include:

- System identifier.
- Forecaster identifier and version.
- Policy identifier and version.
- Strategy pool (ids of base strategies).
- Symbol and timeframe.
- Windows:
  - hygiene
  - test
- Risk profile for the composite.

2. **Use the same orchestrator**

The orchestrator:

- Reads system configs (single strategy or composite).
- Runs hygiene and test backtests for each system.
- Applies thresholds to metrics.
- If a system passes test:
  - Schedules it for demo.

The orchestrator does not need to know internal details of how the forecaster or policy work; it only sees metrics and risk outcomes.

3. **Demo and live**

In demo:

- On each bar:
  - Forecaster runs on live data (from the demo API).
  - Policy picks strategies and exposures.
  - Trades are executed on the demo account.
- Performance is tracked over a fixed demo period (e.g. 1–4 weeks).

If demo passes and risk rules are satisfied:

- System becomes eligible for live deployment with real capital.

Outcome: forecast-driven systems go through the same discipline as simple strategies.

---

## Stage 6 – Self-Healing / Self-Correcting Behavior

Turn the whole setup into a learning and replacement machine.

### Goals

- Continuous learning from new data.
- Automatic promotion/demotion of systems.
- Systematic exploration of new ideas and markets.

### Actions

1. **Continuous data and model refresh (offline)**

On a regular schedule (e.g. weekly or monthly):

- Append new market data into DuckDB.
- Regenerate training datasets from:
  - Historical backtests.
  - Demo and live performance logs.
- Retrain:
  - Forecasters.
  - Optionally strategy-selection policies.
- Version models and policies.

2. **Performance-based system lifecycle management**

The orchestrator monitors:

- Hygiene, test, demo, and live metrics for each system.
- Risk rule violations and drawdown behavior.

Actions:

- Underperforming live systems:
  - Demoted, disabled, or scaled down automatically.
- New candidate systems from research:
  - Enter at hygiene stage and move forward only if they pass.

3. **Expanding idea space: symbols, markets, leverage**

As you add:

- New strategies and variations.
- New symbols and timeframes.
- Different leverage profiles and risk regimes.

Each new "idea" is just another system (or composite) that:

- Gets defined via config.
- Enters hygiene → test → demo → live.
- Either proves itself or gets rejected by the same mechanism.

Outcome: a self-healing, self-correcting agentic trading system that:

- Learns from historical and recent performance.
- Promotes what works.
- Prunes what does not.
- Constantly explores new combinations as you feed it more research and ideas.

---

## Immediate Starting Point

From where you are today, the next concrete steps are:

1. **Finalize the system config schema** for single-strategy systems (no forecasting yet).
2. **Ensure the backtest engine can**:
   - Run hygiene and test windows.
   - Emit consistent run summaries (metrics, trades, equity).
3. **Add per-bar logging** in a stable format so:
   - Future forecasting datasets can be derived from these logs without redesign.

Once those foundations are stable, you can start implementing Stage 3 (training dataset extraction) and then the first simple forecaster and policy on top.
