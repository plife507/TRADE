### Strategy Schema Review (Historical - SystemConfig Era)

**Note:** This document describes the legacy SystemConfig system. The current system uses **IdeaCard** YAML files in `configs/idea_cards/`. See `docs/reviews/IDEACARD_YAML_STRUCTURE_REVIEW.md` for current schema.

This document is a **historical reference** of the SystemConfig-based strategy schema that existed before the IdeaCard migration.

---

### Executive Summary

- **Source of truth for backtest configuration** is a **System YAML** in `src/strategies/configs/*.yml`, loaded by `src/backtest/system_config.py`.
- **Strategy code is versioned and registered** in Python via the strategy registry in `src/strategies/registry.py`.
- The “new sim” (backtest engine + simulated exchange) is **config-driven**: it executes a strategy callable with a `RuntimeSnapshot` and uses a risk policy + simulated risk manager for sizing and gating.
- Outputs are split into:
  - **Backtest contract artifacts** (`result.json` + CSVs) under `data/backtests/...` (system-first layout)
  - **Legacy epoch tracking artifacts** (`config.json`, `results.json`, `summary.json`, `trades.jsonl`) under `backtests/...`

---

### Vocabulary (Canonical Terms)

The current naming model (as implemented in the backtest config layer):

- **StrategyFamily**
  - The pure Python trading logic
  - Identified by **`strategy_id` + `strategy_version`**
- **StrategyInstance**
  - One configured use of a StrategyFamily inside a System
  - Identified by **`strategy_instance_id`** (unique within a System)
  - Has `inputs` (symbol/tf feed) and `params` (instance-specific parameters)
- **System**
  - A YAML-defined “robot”
  - Identified by **`system_id`** (human readable) and **`system_uid`** (deterministic hash for lineage)
- **Run**
  - One execution of a System over a single window (e.g., `hygiene` or `test`)
  - Identified by `run_id`

---

### Identity Model (Stable vs Per-Run)

**Stable identifiers (global / across runs):**
- `strategy_id`: stable family name (example: `ema_rsi_atr`)
- `strategy_version`: explicit version string (example: `1.0.0`)
- `strategy_instance_id`: unique within a system (example: `entry`)
- `system_id`: human-readable YAML name (example: `SOLUSDT_5m_ema_rsi_atr_pure`)
- `system_uid`: deterministic hash of the resolved config (lineage identity)

**Per-run identifiers (instance / per execution):**
- `run_id`: unique ID for a single run
- `window_name`: which window ran (`hygiene` or `test`)

---

### Where “Strategies” Live (Today)

There are two “levels”:

- **Concrete strategy implementations**: `src/strategies/*.py`
  - Example: `src/strategies/ema_rsi_atr.py`
- **Backtest System YAML configs**: `src/strategies/configs/*.yml`
  - Example: `src/strategies/configs/SOLUSDT_5m_ema_rsi_atr_pure.yml`

Note: this is distinct from the repo rule that “concrete research strategies live under `research/`”. The backtest engine today is wired to `src/strategies/registry.py` and the system YAMLs in `src/strategies/configs/`.

---

### YAML Schema (SystemConfig) — Fields & Meaning

**File location:** `src/strategies/configs/{system_id}.yml`

**Top-level fields (current):**
- `system_id`: string (often matches filename stem)
- `symbol`: string (e.g., `SOLUSDT`)
- `tf`: string (e.g., `5m`)
- `primary_strategy_instance_id`: string
- `strategies`: list of StrategyInstance blocks
- `windows`: dict (e.g., `hygiene`, `test`) each with `start/end` or `preset`
- `risk_profile`: dict (equity/leverage/fees/margin parameters)
- `risk_mode`: `"none"` or `"rules"`
- `data_build`: dict (`env`, `period`, `tfs`)
- `warmup`: dict (currently `bars_multiplier`)

**StrategyInstance block (current):**
- `strategy_instance_id`: string (required)
- `strategy_id`: string (required)
- `strategy_version`: string (defaults to `"1.0.0"` if omitted)
- `inputs`: `{ symbol: ..., tf: ... }`
- `params`: free-form dict (strategy-owned schema)
- `role`: optional string tag (e.g. `entry`, `filter`, `exit`)

**Example YAML (real, minimal):**

```yaml
system_id: SOLUSDT_5m_ema_rsi_atr_pure
symbol: SOLUSDT
tf: 5m

primary_strategy_instance_id: entry

strategies:
  - strategy_instance_id: entry
    strategy_id: ema_rsi_atr
    strategy_version: "1.0.0"
    inputs:
      symbol: SOLUSDT
      tf: 5m
    params:
      ema_fast_period: 9
      ema_slow_period: 21
      rsi_period: 14
      rsi_overbought: 70
      rsi_oversold: 30
      atr_period: 14
      atr_sl_multiplier: 1.5
      atr_tp_multiplier: 2.0
      taker_fee_bps: 6
      slippage_bps: 5
    role: entry

windows:
  hygiene:
    start: "2025-01-01"
    end: "2025-06-30"
  test:
    start: "2025-07-01"
    end: "2025-09-30"

risk_profile:
  initial_equity: 1000.0
  sizing_model: percent_equity
  risk_per_trade_pct: 1.0
  max_leverage: 2.0

risk_mode: "none"

data_build:
  env: live
  period: 1Y
  tfs: [5m]
```

---

### Strategy Code Schema (Python) — What a Strategy “Is”

There are two supported shapes in code:

#### 1) Registry strategy function (primary path for backtests)

A strategy is a callable with this shape:

```python
def strategy(snapshot: RuntimeSnapshot, params: dict) -> Signal | None:
    ...
```

Key points:
- Input is **`RuntimeSnapshot`** (Phase 2+ contract)
- Output is **`Signal` or `None`**
- Strategy parameters come from **the YAML StrategyInstance `params` dict**

Strategies are registered by `(strategy_id, strategy_version)` in `src/strategies/registry.py`.

#### 2) `BaseStrategy` class (interface exists)

There is a class interface, but the backtest tools today resolve strategies via the registry callable.

---

### How the New Sim Uses YAML → Strategy → Risk → Exchange

The “new sim” is implemented as:

- **Tools layer** (`src/tools/backtest_tools.py`) is the entry point
- **System YAML** is loaded to `SystemConfig`
- The primary StrategyInstance is selected and its `(strategy_id, strategy_version)` is used to fetch the registered callable
- **BacktestEngine** executes bar-by-bar with deterministic timing semantics and a unified mark price path

High-level flow:

```text
System YAML
  → load_system_config() → SystemConfig (includes system_uid)
  → get_primary_strategy() → StrategyInstanceConfig
  → get_strategy(strategy_id, strategy_version) → strategy callable
  → BacktestEngine.run(strategy)
      → builds RuntimeSnapshot each bar close
      → strategy(snapshot, params) → Signal | None
      → RiskPolicy (if risk_mode=rules) filters/rejects
      → SimulatedRiskManager sizes the order
      → SimulatedExchange executes fills / TP / SL
      → metrics + artifacts emitted
```

Important semantics:
- **Evaluation at bar close**; entries fill at **next bar open**
- `risk_mode="rules"` adds a **risk policy gate**; `risk_mode="none"` is “pure” strategy (but sizing/min trade constraints still apply at execution-time).

---

### JSON Formats

There are two parallel artifact “families”.

#### A) Backtest contract artifacts (system-first layout)

**Directory layout:**

```text
data/backtests/{system_id}/{symbol}/{tf}/{window_name}/{run_id}/
  result.json
  trades.csv
  equity.csv
  account_curve.csv
  run_manifest.json
  events.jsonl
```

**`result.json`** is the serialized `BacktestResult` contract (high-level: identities, window timestamps, risk settings used, metrics, stop classification, and artifact references).

Use this when you want reproducible, structured results per run in a stable, system-indexed folder tree.

#### B) Legacy epoch tracking artifacts (timestamped layout)

**Directory layout:**

```text
backtests/<YYYYMMDD_HHMMSS>/<run_id>/
  config.json
  results.json
  summary.json
  trades.jsonl
```

This format is written by `ArtifactWriter` in `src/utils/epoch_tracking.py` and is used for experiment/epoch lineage and human inspection.

---

### Common “Gotchas” / Notes

- **Versioning is explicit**: YAML selects a strategy via `(strategy_id, strategy_version)`, but the registry must actually have that version registered.
- **Primary strategy**: Current execution focuses on `primary_strategy_instance_id` even though YAML supports multiple StrategyInstances.
- **Params are free-form**: `params` is a dict, so the strategy owns validation/defaults. (Example: `ema_rsi_atr` reads `rsi_overbought`, etc.)
- **Two output families exist**: don’t confuse legacy epoch JSONs (`backtests/...`) with the backtest contract (`data/backtests/...`).

---

### Paste-Ready Context for a GPT Project

Copy this into your GPT project as “background context”:

```text
TRADE backtesting strategy schema (current):

- Backtest configs are YAML “Systems” in src/strategies/configs/*.yml. A System defines:
  - system_id (human name) and system_uid (deterministic hash of resolved config)
  - symbol, tf
  - strategies: a list of StrategyInstances, each with strategy_instance_id, strategy_id, strategy_version, inputs {symbol, tf}, params dict, optional role
  - primary_strategy_instance_id: which instance is executed (current engine focus)
  - windows: hygiene/test windows with start/end (or preset)
  - risk_profile + risk_mode (“none” pure vs “rules” gated)
  - data_build (env/period/tfs) and warmup multiplier

- Strategy identity is (strategy_id, strategy_version). Implementations are registered in src/strategies/registry.py, resolving to a callable:
  strategy(snapshot: RuntimeSnapshot, params: dict) -> Signal | None

- The backtest tool loads YAML → picks primary instance → fetches strategy callable → runs BacktestEngine.
  Strategy emits Signals at bar close; engine applies optional risk policy (risk_mode=rules), sizes via SimulatedRiskManager, and executes via SimulatedExchange.

- Outputs:
  - Backtest contract artifacts under data/backtests/{system_id}/{symbol}/{tf}/{window}/{run_id}/
    (result.json + trades/equity/account_curve CSVs + run_manifest.json + events.jsonl)
  - Legacy epoch tracking under backtests/<timestamp>/<run_id>/ (config.json, results.json, summary.json, trades.jsonl)
```


