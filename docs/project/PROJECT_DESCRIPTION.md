# TRADE - Project Description

## Overview

TRADE is a **production-ready, modular trading bot** for Bybit Unified Trading Account (UTA). It provides:

- **Complete Bybit UTA Support**: Full HTTP and WebSocket support via official pybit SDK (Demo & Live)
- **All Order Types**: Market, Limit, Stop Market, Stop Limit, Batch orders
- **Position Management**: Open, close, partial close, TP/SL, trailing stops
- **Tool Registry**: Dynamic tool discovery and execution for orchestrators/bots
- **Risk Controls**: Leverage limits, position sizing, daily loss limits
- **Safety Features**: Panic button, circuit breakers
- **Diagnostic Tools**: Connection tests, health checks, rate limit monitoring
- **Historical Data**: DuckDB storage for OHLCV data

## Philosophy

**Safety first. Modular always.**

Every operation goes through the **tools layer** (`src/tools/`), which provides a clean API for CLI usage and future agent/HTTP integration.

## Project Structure

```
TRADE/
├── trade_cli.py                    # Main CLI entry point
├── api_keys.env                    # Environment variables (API keys)
├── requirements.txt                # Python dependencies
│
├── src/
│   ├── config/
│   │   ├── config.py               # Central configuration
│   │   └── constants.py            # Trading constants
│   │
│   ├── exchanges/
│   │   └── bybit_client.py         # Bybit API wrapper
│   │
│   ├── core/
│   │   ├── exchange_manager.py     # Unified trading interface
│   │   ├── position_manager.py     # Position tracking & PnL
│   │   ├── risk_manager.py         # Risk controls
│   │   ├── order_executor.py       # Order execution pipeline
│   │   └── safety.py               # Panic button
│   │
│   ├── data/
│   │   ├── market_data.py          # Live market data access
│   │   ├── historical_data_store.py # DuckDB storage (OHLCV, funding, OI)
│   │   ├── realtime_state.py       # WebSocket state management
│   │   └── realtime_bootstrap.py   # WebSocket bootstrap
│   │
│   ├── risk/
│   │   └── global_risk.py          # Account-level risk view
│   │
│   ├── tools/                      # CLI/API surface
│   │   ├── account_tools.py        # Balance, exposure, account info
│   │   ├── order_tools.py          # Market, Limit, Stop, Batch orders
│   │   ├── position_tools.py       # Position management, TP/SL, trailing
│   │   ├── diagnostics_tools.py    # Connection tests, health checks
│   │   ├── market_data_tools.py    # Price, OHLCV, funding rates
│   │   ├── data_tools.py           # Historical data management
│   │   ├── shared.py               # ToolResult type, helpers
│   │   └── tool_registry.py        # Tool discovery & orchestration
│   │
│   └── utils/
│       ├── logger.py               # Logging system
│       ├── rate_limiter.py         # API rate limiting
│       └── helpers.py              # Utility functions
│
├── data/
│   ├── market_data.duckdb          # Historical data database
│   └── historical/                 # Additional data files
│
└── logs/                           # Log files
```

## Trading Modes

| Mode | API Endpoint | Description |
|------|--------------|-------------|
| **DEMO** (`BYBIT_USE_DEMO=true`) | api-demo.bybit.com | Demo account (fake funds) |
| **LIVE** (`BYBIT_USE_DEMO=false`) | api.bybit.com | Live account (**REAL FUNDS**) |

| Trading Mode | Required API | Description |
|--------------|--------------|-------------|
| `paper` | DEMO API | Demo account trading (fake funds, real API orders) |
| `real` | LIVE API | Live account trading (real funds, real API orders) |

**Note**: PAPER mode MUST use DEMO API, REAL mode MUST use LIVE API. Other combinations are blocked.

### API Environment Visibility

The bot provides multiple ways to see which APIs are in use:

| Location | What It Shows |
|----------|---------------|
| **CLI Header** | Trading mode (DEMO/LIVE), API URLs in subtitle |
| **Data Builder Menu** | Data source: LIVE API, key status |
| **Market Data Menu** | Market data source, authentication status |
| **Connection Test** | Full API environment table |
| **Health Check** | API environment + mode consistency check |
| **Logs** | All components log their API mode on init |

**Programmatic Access** (for agents/orchestrators):
```python
from src.tools import get_api_environment_tool
result = get_api_environment_tool()
# Returns: trading mode, data mode, URLs, key status, safety checks
```

## Core Components

### Exchange Manager (`src/core/exchange_manager.py`)
Unified interface for all trading operations:
- Market, Limit, Stop Market, Stop Limit orders
- Batch order operations
- Position management
- TP/SL and trailing stop handling

### Tools Layer (`src/tools/`)
Public API surface with 35+ tools:
- Returns `ToolResult` objects (success/error + data)
- No direct Bybit API calls from CLI
- Clean separation for orchestrators/bots/AI agents

### Tool Registry (`src/tools/tool_registry.py`)
Dynamic tool discovery and execution:
- List available tools by category
- Execute tools by name with arguments
- Get tool specs for AI/LLM function calling
- Batch execution support

### Safety (`src/core/safety.py`)
- Panic close all positions
- Circuit breakers
- Risk limit enforcement

## Available Features

### Order Types
- **Market Orders**: Buy/Sell with optional TP/SL
- **Limit Orders**: GTC, IOC, FOK, PostOnly
- **Stop Orders**: Stop Market and Stop Limit (conditional)
- **Batch Orders**: Up to 10 orders per batch
- **Partial Closes**: Market or Limit, by percentage

### Position Management
- **TP/SL**: Set, modify, remove take profit and stop loss
- **Trailing Stops**: By distance or percentage callback rate
- **Partial Closes**: Close percentage of position
- **Panic Close**: Emergency close all positions

### Tool Registry
- **Discovery**: List tools by category
- **Execution**: Execute tools dynamically
- **AI Integration**: Function calling format for LLMs
- **Batch Operations**: Execute multiple tools in sequence

## Dependencies

Core dependencies (see `requirements.txt`):
- `pybit>=5.13.0` - Official Bybit Python SDK
- `pandas>=2.0.0` - Data processing
- `duckdb>=0.9.0` - Historical data storage
- `python-dotenv>=1.0.0` - Environment configuration

## Historical Data Builder

The Data Builder provides comprehensive historical data management via `src/tools/data_tools.py`.

### Data Types Stored
- **OHLCV Candles**: 1m, 5m, 15m, 1h, 4h, 1d timeframes
- **Funding Rates**: 8-hour funding rate history
- **Open Interest**: Configurable intervals (5min to 1d)

### Key Operations

| Tool | Description |
|------|-------------|
| `get_symbol_timeframe_ranges_tool` | View detailed per-symbol/timeframe date ranges and health |
| `build_symbol_history_tool` | One-click sync of OHLCV, funding, and OI for symbols |
| `sync_to_now_tool` | Fetch only new candles since last sync (forward-only) |
| `sync_to_now_and_fill_gaps_tool` | Sync forward AND backfill any gaps in history |

### CLI Menu (Data Builder)
Access via Main Menu → Data Builder:
- **Database Info**: Stats, symbols, timeframe ranges
- **Build Data**: Full history builder, sync forward, sync+fill gaps
- **Sync Individual**: OHLCV, funding, open interest separately
- **Maintenance**: Fill gaps, heal data, delete symbols, vacuum

### ToolRegistry Integration
All data tools are registered for orchestrator/agent use:

```python
from src.tools.tool_registry import get_registry

registry = get_registry()

# List data tools
registry.list_tools(category="data.sync")   # sync operations
registry.list_tools(category="data.info")   # info/query tools

# Execute data tools
result = registry.execute("build_symbol_history", symbols=["BTCUSDT"], period="1M")
result = registry.execute("sync_to_now", symbols=["BTCUSDT", "ETHUSDT"])
```