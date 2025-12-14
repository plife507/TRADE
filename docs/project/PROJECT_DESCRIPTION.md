# TRADE — Project Description

**Last Updated:** December 13, 2025

## Overview

TRADE is a **production-ready, modular trading bot** for Bybit Unified Trading Account (UTA). It provides:

- **Complete Bybit UTA Support**: Full HTTP and WebSocket via pybit SDK (Demo & Live)
- **Bybit-Aligned Backtest Engine**: Deterministic simulation with isolated margin model
- **All Order Types**: Market, Limit, Stop Market, Stop Limit, Batch orders
- **Position Management**: Open, close, partial close, TP/SL, trailing stops
- **Tool Registry**: Dynamic tool discovery and execution for orchestrators/bots
- **Risk Controls**: Leverage limits, position sizing, daily loss limits
- **Historical Data**: DuckDB storage for OHLCV, funding rates, open interest

## Philosophy

**Safety first. Modular always. Tools as the API surface.**

Every operation goes through the **tools layer** (`src/tools/`), which provides a clean API for CLI, orchestrators, and AI agent integration.

---

## Project Structure

```
TRADE/
├── trade_cli.py                    # Main CLI entry point
├── requirements.txt                # Python dependencies
│
├── src/
│   ├── config/                     # Central configuration
│   ├── exchanges/                  # Bybit API wrappers
│   ├── core/                       # Live trading logic
│   │   ├── exchange_manager.py     # Unified trading interface
│   │   ├── risk_manager.py         # Risk controls
│   │   ├── order_executor.py       # Order execution
│   │   └── safety.py               # Panic button
│   │
│   ├── backtest/                   # Backtest engine
│   │   ├── engine.py               # Main backtest runner
│   │   ├── sim/                    # Modular simulated exchange
│   │   │   ├── exchange.py        # Thin orchestrator
│   │   │   ├── ledger.py          # USDT accounting
│   │   │   ├── pricing/           # Price models
│   │   │   ├── execution/         # Order execution
│   │   │   ├── funding/           # Funding rates
│   │   │   ├── liquidation/       # Liquidation
│   │   │   ├── metrics/           # Exchange metrics
│   │   │   ├── constraints/       # Order validation
│   │   │   └── adapters/          # Data adapters
│   │   ├── system_config.py        # YAML config + risk profile
│   │   ├── indicators.py           # EMA/RSI/ATR (no look-ahead)
│   │   ├── metrics.py              # Performance metrics
│   │   └── proof_metrics.py        # Proof-grade metrics (V2)
│   │
│   ├── data/                       # Market data & storage
│   │   ├── historical_data_store.py # DuckDB storage
│   │   └── market_data.py          # Live market data
│   │
│   ├── tools/                      # PUBLIC API SURFACE
│   │   ├── tool_registry.py        # Tool discovery
│   │   ├── order_tools.py          # Order operations
│   │   ├── position_tools.py       # Position management
│   │   ├── data_tools.py           # Historical data ops
│   │   └── backtest_tools.py       # Backtest execution
│   │
│   ├── strategies/                 # Base classes + configs
│   │   ├── configs/                # System YAML files
│   │   └── registry.py             # Strategy registration
│   │
│   └── utils/                      # Logging, rate limiting
│
├── research/strategies/            # (Planned) research strategy implementations
├── data/                           # DuckDB + backtest artifacts
└── docs/                           # Documentation
```

---

## Trading Modes

| Mode | API Endpoint | Description |
|------|--------------|-------------|
| **DEMO** (`BYBIT_USE_DEMO=true`) | api-demo.bybit.com | Demo account (fake funds) |
| **LIVE** (`BYBIT_USE_DEMO=false`) | api.bybit.com | Live account (**REAL FUNDS**) |

| Trading Mode | Required API | Description |
|--------------|--------------|-------------|
| `paper` | DEMO API | Demo account trading |
| `real` | LIVE API | Live account trading |

**Note:** PAPER mode MUST use DEMO API, REAL mode MUST use LIVE API. Other combinations are blocked.

---

## Core Components

### Tools Layer (`src/tools/`)

Public API surface with 35+ tools:
- Returns `ToolResult` objects (success/error + data)
- No direct Bybit API calls from CLI
- Clean separation for orchestrators/bots/AI agents

```python
from src.tools.tool_registry import ToolRegistry

registry = ToolRegistry()
result = registry.execute("market_buy", symbol="BTCUSDT", usd_amount=100)
```

### Backtest Engine (`src/backtest/`)

Bybit-aligned deterministic simulation:
- Isolated margin model (USDT linear perpetual)
- Configurable fees, leverage, stop conditions
- YAML-driven system configuration
- Hygiene + Test window switching

```python
from src.tools.backtest_tools import backtest_run_tool

result = backtest_run_tool(
    system_id="SOLUSDT_5m_ema_rsi_atr_pure",
    window_name="hygiene",
)
```

### SimulatedExchange Accounting

```python
# Explicit USD-named state (Bybit-aligned)
exchange.cash_balance_usd      # Realized cash
exchange.unrealized_pnl_usd    # Mark-to-market PnL
exchange.equity_usd            # = cash + unrealized_pnl
exchange.used_margin_usd       # Position IM
exchange.free_margin_usd       # = equity - used_margin
exchange.available_balance_usd # = max(0, free_margin)
```

### Safety (`src/core/safety.py`)

- Panic close all positions
- Circuit breakers
- Risk limit enforcement

---

## Available Features

### Order Types

- **Market Orders**: Buy/Sell with optional TP/SL
- **Limit Orders**: GTC, IOC, FOK, PostOnly
- **Stop Orders**: Stop Market and Stop Limit
- **Batch Orders**: Up to 10 orders per batch
- **Partial Closes**: Market or Limit, by percentage

### Position Management

- **TP/SL**: Set, modify, remove
- **Trailing Stops**: By distance or percentage
- **Partial Closes**: Close percentage of position
- **Panic Close**: Emergency close all

### Backtest Features

- **Deterministic**: Same inputs → same outputs
- **Config-driven**: YAML system configs
- **Risk modes**: `none` (pure) or `rules` (with risk manager)
- **Stop conditions**: `account_blown`, `insufficient_free_margin`
- **Artifacts**: trades.csv, equity.csv, result.json

---

## Risk Profile Configuration

```yaml
risk_profile:
  initial_equity: 1000.0
  max_leverage: 10.0
  min_trade_usd: 1.0
  stop_equity_usd: 0.0
  taker_fee_rate: 0.0006           # 0.06%
  maintenance_margin_rate: 0.005   # 0.5%
  include_est_close_fee_in_entry_gate: false
```

---

## Historical Data

### Data Types Stored

- **OHLCV Candles**: 1m, 5m, 15m, 1h, 4h, 1d timeframes
- **Funding Rates**: 8-hour funding rate history
- **Open Interest**: Configurable intervals

### Key Operations

| Tool | Description |
|------|-------------|
| `build_symbol_history_tool` | One-click sync of OHLCV, funding, OI |
| `sync_to_now_tool` | Fetch only new candles since last sync |
| `get_symbol_timeframe_ranges_tool` | View date ranges and health |

---

## Dependencies

Core dependencies (see `requirements.txt`):

- `pybit>=5.13.0` — Bybit Python SDK
- `duckdb>=0.9.0` — Historical data storage
- `pandas>=2.0.0` — Data processing
- `rich>=13.0.0` — CLI display
- `pyyaml>=6.0` — Config parsing

---

## Quick Start

```bash
# Run CLI
python trade_cli.py

# Smoke tests
python trade_cli.py --smoke full              # Full test
python trade_cli.py --smoke backtest          # Backtest only

# Environment setup
cp env.example api_keys.env
# Edit api_keys.env with your keys
```

---

## Documentation

| Document | Purpose |
|----------|---------|
| `docs/project/PROJECT_OVERVIEW.md` | High-level overview |
| `docs/architecture/SYSTEM_REVIEW.md` | Complete technical review |
| `docs/architecture/SIMULATED_EXCHANGE.md` | Backtest accounting model |
| `docs/architecture/DATA_ARCHITECTURE.md` | Data storage details |
| `docs/project/PROJECT_RULES.md` | Coding standards |
| `docs/project/PROJECT_ROADMAP.md` | Development roadmap |
