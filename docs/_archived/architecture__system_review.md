# TRADE System Review — Complete Technical Overview

**Last Updated:** December 13, 2025  
**Status:** Production-ready (Demo/Backtest), backtest refactor complete (Phases 0–5)

---

## Executive Summary

TRADE is a **production-ready, modular trading bot** for Bybit Unified Trading Account (UTA) with a complete backtesting engine. The system follows a strict layered architecture where all operations flow through the tools layer, ensuring safety, consistency, and orchestrator/AI compatibility.

**Core Capabilities:**
- Complete Bybit UTA support (Demo & Live)
- All order types (Market, Limit, Stop, Batch)
- Bybit-aligned backtesting engine (isolated margin, USDT linear)
- DuckDB historical data storage
- Tool Registry for orchestrator/agent integration
- Risk controls, panic button, circuit breakers

---

## Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│                        CLI / Agents                          │
│                    (trade_cli.py, HTTP API)                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Tools Layer                             │
│              src/tools/*.py (35+ tools)                      │
│         Returns ToolResult, Tool Registry for discovery      │
└─────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   Core Layer    │  │  Backtest Layer │  │   Data Layer    │
│   src/core/     │  │  src/backtest/  │  │   src/data/     │
│ ExchangeManager │  │ BacktestEngine  │  │ HistoricalStore │
│  RiskManager    │  │SimulatedExchange│  │   MarketData    │
│ OrderExecutor   │  │     Metrics     │  │  RealtimeState  │
└─────────────────┘  └─────────────────┘  └─────────────────┘
          │                   │                   │
          ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────┐
│                    Exchange Layer                            │
│              src/exchanges/bybit_client.py                   │
│                 (pybit SDK wrapper)                          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Bybit API                               │
│         LIVE: api.bybit.com | DEMO: api-demo.bybit.com      │
└─────────────────────────────────────────────────────────────┘
```

---

## Module Overview

### 1. Tools Layer (`src/tools/`)

**Purpose:** Public API surface for all operations.

| File | Purpose | Key Tools |
|------|---------|-----------|
| `tool_registry.py` | Dynamic tool discovery & execution | `list_tools()`, `execute()`, `get_tool_info()` |
| `order_tools.py` | Order operations | `market_buy`, `limit_sell`, `cancel_order` |
| `position_tools.py` | Position management | `list_positions`, `set_stop_loss`, `panic_close_all` |
| `account_tools.py` | Account queries | `get_balance`, `get_portfolio` |
| `data_tools.py` | Historical data ops | `sync_to_now`, `build_symbol_history` |
| `backtest_tools.py` | Backtest execution | `backtest_run`, `list_systems` |
| `shared.py` | Common utilities | `ToolResult`, `_get_exchange_manager()` |

**Design Principle:** All tools return `ToolResult(success, message, data, error)`.

```python
from src.tools import market_buy_tool

result = market_buy_tool(symbol="BTCUSDT", usd_amount=100)
if result.success:
    print(f"Order placed: {result.data}")
else:
    print(f"Failed: {result.error}")
```

### 2. Core Layer (`src/core/`)

**Purpose:** Live trading logic and execution.

| File | Purpose |
|------|---------|
| `exchange_manager.py` | Unified trading interface (all order types) |
| `order_executor.py` | Order execution pipeline with validation |
| `position_manager.py` | Position tracking and PnL |
| `risk_manager.py` | Risk controls and signal validation |
| `safety.py` | Panic button and circuit breakers |

**Execution Flow:**
```
Signal → RiskManager.check() → OrderExecutor.execute() → ExchangeManager → Bybit
```

### 3. Backtest Layer (`src/backtest/`)

**Purpose:** Deterministic historical simulation with modular exchange architecture.

| File | Purpose |
|------|---------|
| `engine.py` | Main backtest orchestrator |
| `sim/exchange.py` | Exchange orchestrator (thin, ~200 LOC) |
| `sim/ledger.py` | USDT accounting with invariants |
| `sim/pricing/` | Price models (mark, spread, intrabar path) |
| `sim/execution/` | Order execution (slippage, liquidity, impact) |
| `sim/funding/` | Funding rate application |
| `sim/liquidation/` | Mark-based liquidation |
| `sim/metrics/` | Exchange-side metrics |
| `sim/constraints/` | Tick/lot/min_notional validation |
| `sim/adapters/` | Data conversion helpers |
| `system_config.py` | YAML config loader + risk profile |
| `indicators.py` | EMA, RSI, ATR calculation (no look-ahead) |
| `metrics.py` | Performance metrics calculation |
| `proof_metrics.py` | Proof-grade metrics (V2) |
| `risk_policy.py` | `none` vs `rules` risk mode |
| `types.py` | Core dataclasses (Bar, Trade, BacktestResult) - Bar is canonical with ts_open/ts_close |
| `window_presets.py` | Hygiene/test window definitions |
| `simulated_risk_manager.py` | Risk-based position sizing |

**Backtest Flow:**
```
IdeaCard → BacktestEngine → SimulatedExchange → BacktestResult
                │                │
        ┌───────┴────────┐       │
        ▼                 ▼       │
  Indicators          RiskPolicy  │
     (no look-ahead)    (none/rules)  │
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                 ▼
              Pricing            Execution          Ledger
            (mark/spread)    (slippage/impact)   (accounting)
                    │                 │                 │
                    └─────────────────┴─────────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                 ▼
                Funding          Liquidation         Metrics
```

**Modular Exchange Architecture:**
- **Thin orchestrator**: `SimulatedExchange` coordinates specialized modules
- **Separation of concerns**: Each module handles one aspect (pricing, execution, funding, etc.)
- **Deterministic**: All modules produce deterministic outputs for reproducible backtests
- **Bybit-aligned**: Accounting model matches Bybit's isolated margin, USDT linear perpetual

### 4. Data Layer (`src/data/`)

**Purpose:** Market data access and storage.

| File | Purpose |
|------|---------|
| `historical_data_store.py` | DuckDB storage (OHLCV, funding, OI) |
| `market_data.py` | Live market data access |
| `realtime_state.py` | WebSocket state management |
| `realtime_bootstrap.py` | WebSocket bootstrap |

**Data Storage:** DuckDB at `data/market_data.duckdb`

### 5. Exchange Layer (`src/exchanges/`)

**Purpose:** Exchange-specific API wrappers.

| File | Purpose |
|------|---------|
| `bybit_client.py` | Main Bybit client (HTTP + WS) |
| `bybit_account.py` | Account operations |
| `bybit_market.py` | Market data operations |
| `bybit_trading.py` | Trading operations |
| `bybit_websocket.py` | WebSocket client |

---

## Four-Leg API Architecture

The system uses 4 independent API "legs" for strict separation:

| Leg | Purpose | Endpoint | Key Variable |
|-----|---------|----------|--------------|
| **Trade LIVE** | Real money trading | api.bybit.com | `BYBIT_LIVE_API_KEY` |
| **Trade DEMO** | Fake money trading | api-demo.bybit.com | `BYBIT_DEMO_API_KEY` |
| **Data LIVE** | Backtest/research data | api.bybit.com | `BYBIT_LIVE_DATA_API_KEY` |
| **Data DEMO** | Demo validation data | api-demo.bybit.com | `BYBIT_DEMO_DATA_API_KEY` |

**Critical Rules:**
- Historical data **always** uses LIVE API for accuracy
- Trading mode determined by `BYBIT_USE_DEMO` env var
- No fallback between keys (strict API key contract)

---

## Backtest Engine (Refactor Complete — Phases 0–5)

### Overview

The backtest engine provides deterministic historical simulation using a Bybit-aligned accounting model.

**Capabilities:**
- Single symbol, single timeframe per run
- YAML-driven system configuration
- Hygiene + Test windows (config-only switching)
- Bybit-style isolated margin model
- Configurable fees, leverage, stop conditions
- Canonical timing: `Bar.ts_open` (fills) + `Bar.ts_close` (step/eval)
- Canonical strategy input: `RuntimeSnapshot` only
- MTF/HTF caching with readiness gate
- Mark price unification (single mark per step, exchange → snapshot)
- Preflight data health gate + bounded heal loop (tools)

### System Config Structure

```yaml
system_id: SOLUSDT_5m_ema_rsi_atr_pure
symbol: SOLUSDT
tf: 5m

strategies:
  - strategy_instance_id: entry
    strategy_id: ema_rsi_atr
    strategy_version: "1.0.0"
    params:
      ema_fast_period: 9
      ema_slow_period: 21
      rsi_period: 14
      atr_period: 14

primary_strategy_instance_id: entry

windows:
  hygiene:
    start: "2024-09-01"
    end: "2024-10-31"
  test:
    start: "2024-11-01"
    end: "2024-11-30"

risk_profile:
  initial_equity: 1000.0
  max_leverage: 10.0
  min_trade_usd: 1.0
  stop_equity_usd: 0.0
  taker_fee_rate: 0.0006
  maintenance_margin_rate: 0.005
  include_est_close_fee_in_entry_gate: false

risk_mode: "none"  # or "rules"
```

### SimulatedExchange Accounting Model

**Bybit-Aligned State (explicit, always available):**

```python
exchange.cash_balance_usd      # Realized cash (initial + PnL - fees)
exchange.unrealized_pnl_usd    # Current mark-to-market unrealized PnL
exchange.equity_usd            # = cash_balance_usd + unrealized_pnl_usd
exchange.used_margin_usd       # Position IM = position_value × IMR
exchange.free_margin_usd       # = equity_usd - used_margin_usd
exchange.available_balance_usd # = max(0, free_margin_usd)
```

**Core Formulas:**

| Concept | Formula |
|---------|---------|
| Initial Margin (IM) | `position_value × IMR` |
| IMR | `1 / leverage` |
| Maintenance Margin (MM) | `position_value × MMR` |
| Equity | `cash_balance + unrealized_pnl` |
| Free Margin | `equity - used_margin` |
| Available Balance | `max(0, free_margin)` |

**Entry Gate (Active Order IM):**
```
Required = Position IM + Est Open Fee [+ Est Close Fee]
```

**Stop Conditions:**

| Condition | Trigger |
|-----------|---------|
| `account_blown` | `equity_usd <= stop_equity_usd` |
| `insufficient_free_margin` | `available_balance_usd < min_trade_usd` |

### Running a Backtest

**Via CLI:**
```bash
python trade_cli.py
# Select Backtest menu → Run Backtest → Select system → Select window
```

**Via Tools:**
```python
from src.tools.backtest_tools import backtest_run_tool

result = backtest_run_tool(
    system_id="SOLUSDT_5m_ema_rsi_atr_pure",
    window_name="hygiene",
    write_artifacts=True,
)

if result.success:
    print(f"Trades: {result.data['metrics']['total_trades']}")
    print(f"Net PnL: ${result.data['metrics']['net_profit']:.2f}")
```

**Via Smoke Test:**
```bash
python trade_cli.py --smoke backtest
```

### Artifact Output

```
data/backtests/{system_id}/{symbol}/{tf}/{window}/{run_id}/
├── result.json         # BacktestResult contract
├── trades.csv          # Trade list
├── equity.csv          # Equity curve
├── account_curve.csv   # Proof-grade account state per bar
├── run_manifest.json   # Run metadata + git + config echo
└── events.jsonl        # Event log (equity + fills + stop)
```

---

## Risk Profile Configuration

### Complete Field Reference

```python
@dataclass
class RiskProfileConfig:
    # Core
    initial_equity: float = 1000.0
    sizing_model: str = "percent_equity"
    risk_per_trade_pct: float = 1.0
    max_leverage: float = 2.0
    min_trade_usd: float = 1.0
    stop_equity_usd: float = 0.0
    
    # Margin model (Bybit-aligned)
    _initial_margin_rate: Optional[float] = None  # Default: 1/max_leverage
    maintenance_margin_rate: float = 0.005        # 0.5% (Bybit lowest tier)
    mark_price_source: str = "close"              # Engine guardrail (currently close-only)
    
    # Fee model
    taker_fee_rate: float = 0.0006                # 0.06%
    maker_fee_rate: Optional[float] = None
    fee_mode: str = "taker_only"
    
    # Entry gate
    include_est_close_fee_in_entry_gate: bool = False
```

### Override via CLI/Tools

```python
from src.backtest.system_config import resolve_risk_profile

merged = resolve_risk_profile(
    base=config.risk_profile,
    overrides={
        "initial_equity": 5000.0,
        "max_leverage": 20.0,
        "stop_equity_usd": 100.0,
    }
)
```

---

## Tool Registry

### Dynamic Tool Discovery

```python
from src.tools.tool_registry import ToolRegistry

registry = ToolRegistry()

# List available tools
tools = registry.list_tools(category="orders")

# Execute a tool
result = registry.execute("market_buy", symbol="BTCUSDT", usd_amount=100)

# Get tool info (for AI function calling)
info = registry.get_tool_info("market_buy")
```

### Tool Categories

| Category | Examples |
|----------|----------|
| `orders` | `market_buy`, `limit_sell`, `cancel_order` |
| `positions` | `list_positions`, `set_stop_loss`, `close_position` |
| `account` | `get_balance`, `get_portfolio`, `set_leverage` |
| `data.sync` | `sync_to_now`, `build_symbol_history` |
| `data.info` | `get_symbol_ranges`, `get_db_info` |
| `backtest` | `backtest_run`, `list_systems` |
| `diagnostics` | `connection_test`, `health_check` |

---

## Safety Features

### Risk Manager Checks

All trades pass through risk manager validation:

```python
from src.core.risk_manager import Signal, RiskManager

signal = Signal(
    symbol="BTCUSDT",
    direction="LONG",
    size_usd=1000,
    strategy="momentum-v1"
)

result = risk_manager.check_signal(signal, portfolio_snapshot)
if not result.allowed:
    print(f"Blocked: {result.reason}")
```

### Panic Button

```python
from src.tools import panic_close_all_tool

result = panic_close_all_tool()  # Closes ALL positions immediately
```

### Circuit Breakers

- Daily loss limit
- Minimum balance threshold
- Maximum position size
- Maximum total exposure

---

## Trading Mode / API Mapping

### Strict Mapping (Enforced)

| TRADING_MODE | BYBIT_USE_DEMO | Result |
|--------------|----------------|--------|
| `paper` | `true` | ✅ Demo account (fake funds) |
| `real` | `false` | ✅ Live account (real funds) |
| `paper` | `false` | ❌ BLOCKED |
| `real` | `true` | ❌ BLOCKED |

### Environment Visibility

```python
from src.tools import get_api_environment_tool

result = get_api_environment_tool()
# Returns: trading mode, data mode, URLs, key status, safety checks
```

---

## Data Architecture

### Storage

- **Database:** DuckDB at `data/market_data.duckdb`
- **Tables:** `ohlcv`, `funding_rates`, `open_interest`, metadata tables
- **Indexes:** Optimized for `(symbol, timeframe, timestamp)` queries

### Data Types

| Type | Source | Stored | Used for Backtest |
|------|--------|--------|-------------------|
| OHLCV | Bybit LIVE | ✅ | ✅ Primary |
| Funding Rates | Bybit LIVE | ✅ | ✅ Secondary |
| Open Interest | Bybit LIVE | ✅ | ✅ Secondary |
| Ticker | Bybit LIVE | ❌ | ❌ Live only |
| Order Book | WebSocket | ❌ | ❌ Live only |

### Data Operations

```python
from src.data.historical_data_store import get_historical_store

store = get_historical_store(env="live")

# Query data
df = store.get_ohlcv("BTCUSDT", "1h", start=start_dt, end=end_dt)

# Sync new data
store.sync_to_now("BTCUSDT", "1h")
```

---

## Project Structure

```
TRADE/
├── trade_cli.py                    # Main CLI entry point
├── requirements.txt                # Python dependencies
├── env.example                     # Environment variables template
│
├── src/
│   ├── config/                     # Central configuration
│   ├── exchanges/                  # Exchange-specific code (Bybit)
│   ├── core/                       # Core trading logic
│   ├── backtest/                   # Backtest engine
│   ├── data/                       # Market data & storage
│   ├── strategies/                 # Strategy base classes + configs
│   ├── tools/                      # Public API surface
│   ├── utils/                      # Utilities
│   └── cli/                        # CLI interface
│
├── research/
│   └── strategies/                 # Concrete strategies
│       ├── pending/                # Strategies in testing
│       ├── final/                  # Validated strategies
│       └── archived/               # Retired strategies
│
├── data/
│   ├── market_data.duckdb          # Historical data
│   └── backtests/                  # Backtest artifacts
│
├── docs/
│   ├── architecture/               # Technical documentation
│   ├── guides/                     # How-to guides
│   ├── project/                    # Project documentation
│   └── examples/                   # Code examples
│
├── tests/                          # Test suite
├── logs/                           # Application logs
└── backtests/                      # Epoch tracking artifacts
```

---

## Key Invariants

### Always True

1. **All trades through tools** - Never call `bybit_client` directly
2. **No hardcoding** - Symbols, sizes, paths from config
3. **Safety first** - Risk manager checks before every order
4. **Demo first** - Test on demo API before live
5. **Time ranges required** - All history endpoints need explicit ranges

### Backtest Accounting Invariants

```python
# These are verified every bar:
assert equity_usd == cash_balance_usd + unrealized_pnl_usd
assert free_margin_usd == equity_usd - used_margin_usd
assert available_balance_usd == max(0.0, free_margin_usd)
assert used_margin_usd == position_value * initial_margin_rate
```

---

## API Rate Limits

| Endpoint Type | Limit | Bot Uses |
|---------------|-------|----------|
| IP (public) | 600/5sec | 100/sec |
| Account/Position | 50/sec | 40/sec |
| Orders | 10/sec/symbol | 8/sec |

Rate limiter: `src/utils/rate_limiter.py`

---

## Quick Reference

### Run CLI
```bash
python trade_cli.py
```

### Smoke Tests
```bash
python trade_cli.py --smoke full              # Full test
python trade_cli.py --smoke data_extensive    # Data test
python trade_cli.py --smoke backtest          # Backtest test
```

### Key Files

| Purpose | File |
|---------|------|
| Main CLI | `trade_cli.py` |
| System Configs | `src/strategies/configs/*.yml` |
| Backtest Engine | `src/backtest/engine.py` |
| Simulated Exchange | `src/backtest/sim/exchange.py` |
| Risk Profile | `src/backtest/system_config.py` |
| Tool Registry | `src/tools/tool_registry.py` |
| Historical Data | `src/data/historical_data_store.py` |

---

## Changelog

- **2025-12-13:** Major update - Bybit-aligned SimulatedExchange refactor, new RiskProfileConfig fields, comprehensive documentation
- **2025-12-12:** Backtest refactor phases (0–5) completed (RuntimeSnapshot/MTF/mark unification)
- **2025-12-06:** Initial system review
