# TRADE - Bybit Trading Bot

A production-ready, modular trading bot for Bybit Unified Trading Account (UTA).

## Philosophy

**Safety first. Modular always. Tools as API.**

TRADE provides a complete foundation for Bybit futures trading:
- Full Bybit UTA support (Demo & Live)
- All order types (Market, Limit, Stop, Batch)
- Position management (TP/SL, Trailing Stops, Partial Closes)
- Tool Registry for orchestrator/bot integration
- Risk controls and safety features
- Diagnostic tools and health checks

## Quick Start

### 1. Install Dependencies

```bash
cd TRADE
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
```

### 2. Configure API Keys

```bash
cp env.example api_keys.env
# Edit api_keys.env with your Bybit API keys
```

Get API keys from: https://www.bybit.com/app/user/api-management

### 3. Run the CLI

```bash
python trade_cli.py
```

## Project Structure

```
TRADE/
├── trade_cli.py              # Main CLI entry point
├── api_keys.env              # Your API keys (not in git)
├── requirements.txt          # Python dependencies
│
├── src/
│   ├── config/               # Configuration management
│   │   ├── config.py         # Central config
│   │   └── constants.py      # Trading constants
│   │
│   ├── exchanges/            # Exchange clients
│   │   └── bybit_client.py   # Bybit API wrapper (HTTP + WS)
│   │
│   ├── core/                 # Core trading logic
│   │   ├── exchange_manager.py   # Unified trading interface
│   │   ├── position_manager.py   # Position tracking
│   │   ├── risk_manager.py       # Risk controls
│   │   ├── order_executor.py     # Order execution
│   │   └── safety.py             # Panic button
│   │
│   ├── data/                 # Data modules
│   │   ├── market_data.py        # Live market data
│   │   ├── data_capture.py       # Historical data collection
│   │   ├── historical_data_store.py  # DuckDB storage
│   │   ├── realtime_state.py     # WebSocket state
│   │   └── realtime_bootstrap.py # WS bootstrap
│   │
│   ├── risk/                 # Risk management
│   │   └── global_risk.py    # Account-level risk view
│   │
│   ├── tools/                # Tool layer (CLI/API surface)
│   │   ├── account_tools.py      # Account/balance info
│   │   ├── order_tools.py        # Order execution
│   │   ├── position_tools.py     # Position management
│   │   ├── diagnostics_tools.py  # Connection tests
│   │   ├── market_data_tools.py  # Price/OHLCV queries
│   │   └── data_tools.py         # Historical data management
│   │
│   └── utils/                # Utilities
│       ├── logger.py         # Logging system
│       ├── rate_limiter.py   # API rate limiting
│       └── helpers.py        # Helper functions
│
├── data/                     # Runtime data
│   ├── market_data.duckdb    # Historical data database
│   └── historical/           # Additional data files
│
└── logs/                     # Log files
```

## Trading Modes

| Mode | API | Description |
|------|-----|-------------|
| `BYBIT_USE_DEMO=true` | api-demo.bybit.com | Demo trading with fake money |
| `BYBIT_USE_DEMO=false` | api.bybit.com | **LIVE trading with REAL money** |

| TRADING_MODE | Description |
|--------------|-------------|
| `paper` | Simulated trades (learning/testing) |
| `real` | Executes actual orders |

**Start with Demo mode**, test thoroughly, then switch to Live when ready.

## CLI Menu

```
MAIN MENU
----------------------------------------
  1. Account & Balance
  2. Positions
  3. Orders
  4. Market Data
  5. Historical Data
  6. Connection Test
  7. Health Check
  8. PANIC: Close All & Stop
  9. Exit
----------------------------------------
```

## Tools Layer

All trading operations go through the tools layer (`src/tools/`). This provides a clean API for:
- CLI usage
- Orchestrator/bot integration via `ToolRegistry`
- AI agent function calling
- Future HTTP API

### Direct Tool Usage
```python
from src.tools import market_buy_tool, get_account_balance_tool

# Get balance
result = get_account_balance_tool()
if result.success:
    print(f"Balance: {result.data['available_balance']}")

# Place order
result = market_buy_tool("BTCUSDT", usd_amount=50)
if result.success:
    print(f"Order filled: {result.data}")
```

### Tool Registry (For Orchestrators/Bots)
```python
from src.tools.tool_registry import get_registry

registry = get_registry()

# Discover tools
tools = registry.list_tools(category="orders")

# Execute dynamically
result = registry.execute("market_buy", symbol="SOLUSDT", usd_amount=100)

# Get specs for AI agents
specs = registry.get_all_tools_info()
```

See `examples/orchestrator_example.py` for complete usage patterns.

## Safety Features

- **Panic button**: Close all positions with one command
- **Risk limits**: Max leverage, position size, daily loss limits
- **Demo mode**: Default to demo API for safe testing
- **Rate limiting**: Respects Bybit API limits

## Environment Variables

```bash
# api_keys.env
TRADING_MODE=paper              # paper or real
BYBIT_USE_DEMO=true             # true = demo API, false = LIVE

# API Keys
BYBIT_DEMO_API_KEY=your_demo_key
BYBIT_DEMO_API_SECRET=your_demo_secret
BYBIT_LIVE_API_KEY=your_live_key
BYBIT_LIVE_API_SECRET=your_live_secret

# Risk (optional)
MAX_LEVERAGE=3
MAX_POSITION_SIZE_USD=50
MAX_DAILY_LOSS_USD=20
```

## Available Tools

### Order Tools
- **Market**: `market_buy`, `market_sell`, `market_buy_with_tpsl`, `market_sell_with_tpsl`
- **Limit**: `limit_buy`, `limit_sell`, `partial_close`
- **Stop**: `stop_market_buy`, `stop_market_sell`, `stop_limit_buy`, `stop_limit_sell`
- **Management**: `get_open_orders`, `cancel_order`, `amend_order`, `cancel_all_orders`
- **Batch**: `batch_market_orders`, `batch_limit_orders`, `batch_cancel_orders`

### Position Tools
- **Query**: `list_open_positions`, `get_position`
- **TP/SL**: `set_take_profit`, `set_stop_loss`, `remove_take_profit`, `remove_stop_loss`
- **Trailing**: `set_trailing_stop`, `set_trailing_stop_percent`
- **Close**: `close_position`, `panic_close_all`

### Account & Market Data
- **Account**: `get_balance`, `get_portfolio`, `set_leverage`
- **Market**: `get_price`, `get_ohlcv`, `get_funding_rate`

See `src/tools/__init__.py` for the complete list of 35+ tools.

## License

MIT License - See LICENSE file
