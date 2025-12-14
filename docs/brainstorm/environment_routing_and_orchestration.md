## Environment Routing and Orchestration Overview

**Last Updated:** 2025-12-13  
**Status:** Current Implementation

This document explains, in detail, how environments are selected and used end‑to‑end:

- How callers (CLI, external scripts, orchestrators) specify **which environment** they want:
  - Trading: **DEMO vs LIVE**
  - Data: **live vs demo**
- How that intent flows into **config → ExchangeManager → BybitClient → REST/WebSocket**.
- How responses come back from REST and WebSocket, and how an orchestration layer can safely reason about *which environment* produced the data.

This is the foundation for building robust orchestration for the Agent Research Factory described in `docs/brainstorm/agent_research_factory_brainstorm.md`.

**Note:** This architecture is implemented and working. Backtest engine uses separate data environment selection via system config.

---

## 1. Process-Level Environment Configuration

### 1.1 Trading Environment (Per Process)

At **process startup**, the trading environment is fixed by configuration:

- `BYBIT_USE_DEMO` (bool) – selects DEMO vs LIVE *trading* endpoint.
- `TRADING_MODE` (`paper` or `real`) – selects paper vs real *trading* mode.

Valid combinations (enforced in config/ExchangeManager):

- `BYBIT_USE_DEMO=true` + `TRADING_MODE=paper` → **DEMO trading** (fake money)
- `BYBIT_USE_DEMO=false` + `TRADING_MODE=real` → **LIVE trading** (real money)
- Any other combo → rejected at startup (safety guard).

This flows into:

- `config.bybit.use_demo` – `True` for demo, `False` for live.
- `config.trading.mode` – `TradingMode.PAPER` or `TradingMode.REAL`.

Then:

- `ExchangeManager` is instantiated once per process with this config.
- `BybitClient` inside `ExchangeManager` is created with:
  - `use_demo=True` → base URL `https://api-demo.bybit.com` (DEMO trading).
  - `use_demo=False` → base URL `https://api.bybit.com` (LIVE trading).
  - Trading API keys:
    - DEMO: `BYBIT_DEMO_API_KEY/SECRET`
    - LIVE: `BYBIT_LIVE_API_KEY/SECRET`

**Key point:** Once a process is started, its **trading env** (DEMO/LIVE) cannot be changed without restarting the process.

### 1.2 Data Environment (Per Tool Call)

Data environment is **per call**, not per process.

Defined in `src/config/constants.py`:

- `DataEnv = Literal["live", "demo"]`
- `DEFAULT_DATA_ENV = "live"`

Data tools accept an `env: DataEnv` parameter:

- `env="live"`:
  - Uses DuckDB file: `data/market_data_live.duckdb`.
  - Uses `BYBIT_LIVE_DATA_API_KEY/SECRET` (or documented fallbacks) → `api.bybit.com`.
- `env="demo"`:
  - Uses `data/market_data_demo.duckdb`.
  - Uses `BYBIT_DEMO_DATA_API_KEY/SECRET` → `api-demo.bybit.com`.

**Trading and data** envs are **separate**:

- Trading REST & WS: per‑process, configured via `BYBIT_USE_DEMO` / `TRADING_MODE`.
- Data REST (for building history) and DuckDB selection: per call via `env`.

---

## 2. How External Callers Specify Environment

There are three main types of callers:

1. **CLI menus and smoke tests** (inside the process).
2. **External Python scripts** (strategies, test harnesses, etc.).
3. **Orchestrator/API server** (Agent Research Factory control plane).

### 2.1 CLI Calls (No `trading_env`, Uses Process Env)

The CLI (e.g. `trade_cli.py`, menus, smoke tests) **does not** pass `trading_env` to trading tools. Examples:

```python
# Orders menu
result = market_buy_tool(symbol=symbol, usd_amount=usd)

# Account menu
result = get_account_balance_tool()
```

Because:

- The CLI **is** the process: it already knows (and controls) whether it’s DEMO or LIVE via environment variables / startup options.
- All calls go through `_get_exchange_manager()` which returns the singleton `ExchangeManager` configured for that process’s trading env.

Result:

- CLI → tools → `ExchangeManager` (DEMO or LIVE) → `BybitClient` (correct REST endpoint + trading keys).

No `trading_env` parameter is involved; the process configuration is the single source of truth.

### 2.2 External Callers: Trading Tools (`trading_env`)

For external callers (orchestrators, scripts, test harnesses), trading tools now expose:

- `trading_env: Optional[str] = None` with allowed values `"demo"` or `"live"`.

Typical pattern inside a tool (e.g. `market_buy_tool`):

```python
from .shared import validate_trading_env_or_error, _get_exchange_manager

def market_buy_tool(symbol: str, usd_amount: float, trading_env: Optional[str] = None) -> ToolResult:
    # 1) Validate caller's intent against process config
    if error := validate_trading_env_or_error(trading_env):
        return error  # ToolResult(success=False, error=...)

    # 2) Use this process's ExchangeManager (already configured to DEMO/LIVE)
    exchange = _get_exchange_manager()
    # ...
```

`validate_trading_env_or_error(trading_env)` does:

1. If `trading_env is None`:
   - Returns `None` → **no validation** (for backward compatibility).
2. Else:
   - Normalizes `"DEMO"`/`"Demo"` to `"demo"`, `"LIVE"`/`"Live"` to `"live"`.
   - Calls `_get_exchange_manager_for_env(trading_env)`:
     - Looks at `config.bybit.use_demo` and `config.trading.mode`:
       - If process is DEMO and `trading_env=="demo"` → OK.
       - If process is LIVE and `trading_env=="live"` → OK.
       - Otherwise → raises `TradingEnvMismatchError`.
   - Converts errors into `ToolResult(success=False, error="...")`.

**Effect:**

- External caller can say:

```python
# External script wants DEMO trading:
result = market_buy_tool("SOLUSDT", 20.0, trading_env="demo")
```

- If this process is configured for DEMO:
  - Tool executes normally on `api-demo.bybit.com`.
- If this process is configured for LIVE:
  - Tool returns `ToolResult(success=False, error="Requested trading_env='demo' but this process is configured for LIVE ...")`.

This is **validation only**: it does not switch the active env; it just prevents accidental cross‑wiring.

#### 2.2.1 Via `ToolRegistry` (orchestration-friendly)

`src/tools/tool_registry.py` exposes all tools and parameters for agents/orchestrators:

- `TRADING_ENV_PARAM` describes the parameter in JSON-like schema.
- All trading/account/position tools include a `trading_env` entry in `parameters`.

Orchestrator usage:

```python
from src.tools.tool_registry import get_registry

registry = get_registry()

# Inspect tool schema
info = registry.get_tool_info("market_buy")
# info["parameters"]["trading_env"] is present

# Execute with env validation
result = registry.execute(
    "market_buy",
    symbol="SOLUSDT",
    usd_amount=20,
    trading_env="demo",
)
```

If the process is DEMO:

- `result.success == True` → order sent to `api-demo.bybit.com`.

If the process is LIVE:

- `result.success == False` and `result.error` explains the env mismatch.

### 2.3 External Callers: Data Tools (`env`)

Data tools (e.g. in `src/tools/data_tools.py`) accept:

- `env: DataEnv = DEFAULT_DATA_ENV` where `DataEnv` is `"live"` or `"demo"`.

Examples:

```python
result = build_symbol_history_tool(symbols=["BTCUSDT"], period="1Y", env="live")
result = get_ohlcv_history_tool(symbol="SOLUSDT", timeframe="1h", period="3M", env="demo")
```

Flow:

1. Tool passes `env` down to `_get_historical_store(env=env)`.
2. `HistoricalDataStore(env)`:
   - Chooses DuckDB file (`market_data_live.duckdb` / `market_data_demo.duckdb`).
   - Chooses data API credentials + `use_demo` flag for `BybitClient`:
     - `env="live"` → `api.bybit.com` + live data keys.
     - `env="demo"` → `api-demo.bybit.com` + demo data keys.

**Trading env** and **data env** can be different:

- Example:
  - DEMO trading process (for demonstration strategies).
  - But using LIVE data for canonical backtests (`env="live"`).
- Or:
  - Dedicated demo-validation process using DEMO data (`env="demo"`).

---

## 3. How Environment Flows Down to REST and WebSocket

### 3.1 REST (Trading)

Path for trading REST calls:

1. **Caller** → Tool (`market_buy_tool`, etc.) with optional `trading_env`.
2. **Validation** (if `trading_env` set) by `validate_trading_env_or_error`.
3. `exchange = _get_exchange_manager()`:
   - `ExchangeManager` was instantiated using `config.bybit.use_demo`.
4. `BybitClient` inside `ExchangeManager`:
   - `use_demo=True`:
     - Base URL: `https://api-demo.bybit.com`
     - Auth: DEMO trading keys.
   - `use_demo=False`:
     - Base URL: `https://api.bybit.com`
     - Auth: LIVE trading keys.

Therefore, every trading REST response is implicitly associated with exactly one trading environment:

- DEMO process → DEMO REST.
- LIVE process → LIVE REST.

### 3.2 REST (Data)

Path for data REST calls:

1. **Caller** → Data tool (`build_symbol_history_tool`, `sync_to_now_tool`, `get_ohlcv_history_tool`, etc.) with `env`.
2. `store = _get_historical_store(env)`:
   - `resolve_db_path(env)` selects DuckDB file.
3. `HistoricalDataStore(env)` chooses credentials:
   - For `env="live"`:
     - Use LIVE data keys → `api.bybit.com`.
   - For `env="demo"`:
     - Use DEMO data keys → `api-demo.bybit.com`.
4. `BybitClient` inside `HistoricalDataStore` sends data requests accordingly.

All data REST responses are associated with exactly one **data env** (live/demo) per call, and the `env` parameter in the tool call is the explicit selector.

### 3.3 WebSocket (Trading State)

WebSocket is **per trading process**, not per call. Rough flow:

1. **Application initialization** (`src/core/application.py`):
   - Reads `config.bybit.use_demo`.
   - Instantiates `RealtimeBootstrap` and WebSocket configs.
2. `RealtimeBootstrap` in `src/data/realtime_bootstrap.py`:
   - Uses trading mode to select WS endpoints:
     - DEMO: `wss://stream-demo.bybit.com`.
     - LIVE: `wss://stream.bybit.com`.
   - Starts public/private streams.
3. Incoming WS messages:
   - Normalized into models like `PositionData`, `OrderData`, `ExecutionData` in `realtime_models.py`.
   - Stored in singleton `RealtimeState` via methods like:
     - `state.update_position(position)`
     - `state.update_order(order)`
     - `state.add_execution(execution)`.
4. `RealtimeState` exposes both state and callbacks:
   - Getters:
     - `get_all_positions()`, `get_position(symbol)`, `get_ticker(symbol)`, etc.
   - Callbacks:
     - `on_position_update(callback)`
     - `on_order_update(callback)`
     - `on_execution(callback)`
     - plus others for ticker/kline/trades.

**Env binding:**

- A DEMO process’s `RealtimeState` is fed only by DEMO WebSocket streams.
- A LIVE process’s `RealtimeState` is fed only by LIVE WebSocket streams.
- There is no cross‑env mixing inside a single `RealtimeState`.

---

## 4. How Environment Comes Back in Results

### 4.1 ToolResult and `source`

All tools return a `ToolResult` with fields:

- `success: bool`
- `message: str`
- `symbol: Optional[str]`
- `data: Optional[Dict[str, Any]]`
- `error: Optional[str]`
- `source: Optional[str]` – typically `"rest_api"` or `"websocket"` where applicable.

Examples:

- REST-based tools often set:
  - `source="rest_api"`.
- WS-based or WS-favored tools (positions, risk snapshot) may set:
  - `source="websocket"` if data originated from `RealtimeState`.
  - Or `"rest_api"` if they fell back to REST.

**Env is not currently encoded explicitly in `ToolResult`**, but:

- For trading:
  - The env is known implicitly from the process:
    - DEMO process → all trading data/results belong to DEMO env.
    - LIVE process → belong to LIVE env.
- For data:
  - The env is explicit in the input parameter (`env`) and, for data tools, often echoed in `data`.

For orchestration:

- You typically have one RPC channel per process (e.g. “demo runner”, “live runner”), and you know the env from **which process** you’re talking to.
- For extra robustness, you could add `env` fields to `ToolResult` (future enhancement) to avoid any ambiguity.

### 4.2 Using `get_api_environment_tool`

`get_api_environment_tool()` exposes a **full env matrix** for a process:

- `data["trading"]` – active trading leg (DEMO/LIVE, REST URL, key-configured).
- `data["data"]` – legacy, always LIVE data summary.
- `data["trade_live"]` and `data["trade_demo"]` – statuses for both trading legs.
- `data["data_live"]` and `data["data_demo"]` – statuses for both data legs.
- `data["websocket"]` – WS mode and URLs.
- `data["safety"]` – validation messages (e.g., missing keys, inconsistent modes).

Orchestrator can:

1. Call this once per runner process.
2. Store a mapping:
   - “Runner A” → `trading.mode="DEMO"`.
   - “Runner B” → `trading.mode="LIVE"`.

This allows robust routing and validation at the orchestration level.

---

## 5. How This Supports Robust Orchestration (Research Factory)

Linking back to `docs/brainstorm/agent_research_factory_brainstorm.md`:

You want multiple **tracks**:

- Backtests (data only).
- Demo trading (DEMO trading leg).
- Live test + production (LIVE trading leg).

Given the env design above, you can structure the orchestration layer as follows.

### 5.1 Separate Runners per Track

- **Backtest Runner**:
  - No trading, only data tools:
    - Calls `build_symbol_history_tool(...)`, `get_ohlcv_history_tool(...)` with `env="live"`.
- **Demo Runner**:
  - DEMO trading + typically LIVE data:
    - Process: `BYBIT_USE_DEMO=true`, `TRADING_MODE=paper`.
    - Trading tools called with `trading_env="demo"` (for safety).
- **Live Runner**:
  - LIVE trading + LIVE data:
    - Process: `BYBIT_USE_DEMO=false`, `TRADING_MODE=real`.
    - Trading tools called with `trading_env="live"`.

### 5.2 Orchestrator Logic

1. **Discovery Phase:**
   - For each runner process:
     - Call `get_api_environment_tool` to confirm env legs and safety status.
2. **Routing Phase:**
   - For a “demo” system:
     - Send trading tool calls to DEMO runner:
       - `registry.execute("market_buy", ..., trading_env="demo")`.
   - For a “live_test/production” system:
     - Send to LIVE runner:
       - `registry.execute("market_buy", ..., trading_env="live")`.
   - For backtests:
     - Use data tools on a dedicated backtest runner or on any runner with `env="live"` for data.
3. **Verification Phase:**
   - On every call:
     - Let `trading_env` validation fail fast if orchestration routes to the wrong runner.
   - Out-of-band:
     - Periodically query `get_api_environment_tool` to ensure no config drift.

### 5.3 Event Layer (Future Work)

To fully integrate with the Agent Research Factory (demo track, live track, etc.), you will likely want an **event distribution mechanism**:

- Inside each runner:
  - Use `RealtimeState` callbacks:
    - `on_position_update`, `on_order_update`, `on_execution`, etc.
  - Publish events tagged with env:

```python
event = {
    "env": "demo",  # or "live"
    "type": "position_update",
    "symbol": position.symbol,
    "is_open": position.is_open,
    "size": position.size,
    "ts": position.timestamp,
}
# Publish to Redis / NATS / RabbitMQ / Kafka / HTTP webhook
```

- Orchestrator subscribes and routes events to the right strategies and tracks.

This keeps:

- **State ownership** per runner (trading and WS state live together).
- **Routing** in the orchestrator (who cares about which env and which strategy).
- **Safety** (LIVE vs DEMO separation) still enforced at process boundaries.

---

## 6. Summary

- **Trading env** is **fixed per process** and derived from config (`BYBIT_USE_DEMO`, `TRADING_MODE`).
- **Data env** is **per call** via `env="live"|"demo"` in data tools.
- External callers and orchestrators:
  - Specify desired **trading env** via `trading_env="demo"|"live"` (validation only).
  - Specify desired **data env** via `env="live"|"demo"` in data tools.
- REST and WS:
  - REST trading/data endpoints are determined by `use_demo` and `env`.
  - WebSocket environment is bound to the process’s trading env.
- Results:
  - `ToolResult.source` tells you `"websocket"` vs `"rest_api"`.
  - The env is known from process config (and can be added explicitly to results later if desired).

This gives a clean, **composable** foundation to:

- Spin up dedicated runners for each track in the Agent Research Factory (backtest, demo, live).
- Route tool calls and events correctly and safely across DEMO and LIVE.
- Extend into a full orchestration layer without mixing DEMO and LIVE risk.


