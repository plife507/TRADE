# CLAUDE.md

Guidance for Claude when working with the TRADE trading bot.

## Project Overview

TRADE is a **modular, production-ready** Bybit futures trading bot with:
- Complete Bybit Unified Trading Account (UTA) support
- Comprehensive order types (Market, Limit, Stop Market, Stop Limit, Batch)
- Position management (TP/SL, Trailing Stops, Partial Closes)
- Tool Registry for orchestrator/bot integration
- Risk controls and safety features
- Diagnostic tools and health checks

**Key Philosophy**: Safety first, modular always, tools as the API surface.

## Quick Reference

```bash
# Run CLI
python trade_cli.py

# Dependencies
pip install -r requirements.txt
```

## Architecture

```
TRADE/
├── src/
│   ├── config/config.py        # Central configuration
│   ├── exchanges/bybit_client.py   # Bybit API wrapper
│   ├── core/
│   │   ├── application.py          # Application lifecycle manager
│   │   ├── exchange_manager.py     # Unified trading interface
│   │   ├── position_manager.py     # Position tracking (hybrid WS/REST)
│   │   ├── risk_manager.py         # Risk controls
│   │   ├── order_executor.py       # Order execution
│   │   └── safety.py               # Panic button
│   ├── data/
│   │   ├── market_data.py          # Live market data
│   │   ├── historical_data_store.py # DuckDB storage
│   │   ├── realtime_state.py       # WebSocket state manager
│   │   └── realtime_bootstrap.py   # WebSocket connection manager
│   ├── risk/global_risk.py         # Account-level risk
│   ├── tools/                      # CLI/API surface
│   │   ├── account_tools.py
│   │   ├── order_tools.py          # Market, Limit, Stop, Batch orders
│   │   ├── position_tools.py
│   │   ├── diagnostics_tools.py
│   │   ├── market_data_tools.py
│   │   ├── data_tools.py
│   │   ├── tool_registry.py        # Tool discovery & orchestration
│   │   └── shared.py               # ToolResult type, WebSocket helpers
│   └── utils/
│       ├── logger.py
│       ├── rate_limiter.py
│       └── helpers.py
└── trade_cli.py                # CLI entry point
```

## Key Patterns

### Tools Layer (Primary API Surface)
All operations go through `src/tools/*`. Tools return `ToolResult` objects:

```python
from src.tools import market_buy_tool, get_account_balance_tool, ToolResult

result: ToolResult = get_account_balance_tool()
if result.success:
    print(result.data)  # Dict with balance info
else:
    print(result.error)
```

### Tool Registry (For Orchestrators/Bots)
Use `ToolRegistry` for dynamic tool discovery and execution:

```python
from src.tools.tool_registry import get_registry

registry = get_registry()

# List available tools
tools = registry.list_tools(category="orders")

# Execute a tool
result = registry.execute("market_buy", symbol="SOLUSDT", usd_amount=100)

# Get tool specs for AI agents
spec = registry.get_tool_info("market_buy")
```

### Exchange Access
```python
from src.core.exchange_manager import ExchangeManager

exchange = ExchangeManager()  # Auto-loads config

# Market orders
result = exchange.market_buy("BTCUSDT", usd_amount=50)
result = exchange.market_sell_with_tpsl("ETHUSDT", 100, take_profit=2000, stop_loss=1800)

# Position management
position = exchange.get_position("BTCUSDT")
exchange.set_position_tpsl("BTCUSDT", take_profit=50000, stop_loss=40000)
exchange.close_all_positions()  # Panic
```

### REST vs WebSocket Architecture

| Use Case | REST API | WebSocket |
|----------|----------|-----------|
| Get current state | ✅ Primary | ❌ No initial snapshot |
| Execute trades | ✅ Always | ❌ Not for orders |
| Position queries | ✅ Always | ❌ Not needed |
| Risk management | ✅ Basic checks | ✅ GlobalRiskView (real-time) |

**Flow:**
```
1. App Start → REST API (get positions, orders, balance)
2. Risk Manager → Starts WebSocket ONLY if GlobalRiskView enabled
3. Trading → REST + dynamic WebSocket subscription for new positions
4. Position Close → Symbol removed from WebSocket tracking
```

### REST-First (Default)
```python
# Position tools use REST only - no websocket needed
from src.tools import list_open_positions_tool, get_open_orders_tool

positions = list_open_positions_tool()  # REST: fast, reliable, no websocket
orders = get_open_orders_tool()         # REST: always works
```

### WebSocket for Risk Manager Only
```python
# WebSocket is ONLY started by Risk Manager when GlobalRiskView is enabled
# This provides real-time account-level risk monitoring

# Position tools do NOT start websocket - they use REST only
# WebSocket is purely for risk management, not for position queries
```

### Dynamic Symbol Subscription
```python
# Symbols are automatically subscribed when positions open
exchange.market_buy("SOLUSDT", 100)  # Auto-subscribes to SOLUSDT

# Symbols are automatically unsubscribed when positions close
exchange.close_position("SOLUSDT")  # Removes SOLUSDT from tracking

# Only symbols with open positions are tracked
# No default symbols - websocket is for positions, not market watching
```

### Configuration
```python
from src.config.config import get_config

config = get_config()
config.bybit.use_demo      # True = demo API
config.risk.max_leverage   # Hard-capped at 10x
config.trading.mode        # "paper" or "real"
```

### Application Lifecycle
The `Application` class manages component initialization and WebSocket lifecycle:

```python
from src.core.application import Application, get_application

# Option 1: Context manager (recommended)
with Application() as app:
    # WebSocket auto-started, all components ready
    # Do your work here
# Automatic cleanup on exit

# Option 2: Manual control
app = get_application()
app.initialize()
app.start()
try:
    # Your code here
finally:
    app.stop()
```

### WebSocket Real-Time Data
WebSocket is ONLY started by Risk Manager when GlobalRiskView is enabled:

```python
from src.data.realtime_state import get_realtime_state

state = get_realtime_state()

# Get real-time data (only if websocket is running)
if state.is_private_ws_connected:
    ticker = state.get_ticker("BTCUSDT")
    positions = state.get_all_positions()
else:
    # Use REST API instead
    from src.tools import list_open_positions_tool
    positions = list_open_positions_tool()
```

**Data Flow:**
1. Risk Manager → Starts WebSocket (if GlobalRiskView enabled)
2. WebSocket streams → RealtimeBootstrap (parses messages)
3. RealtimeBootstrap → RealtimeState (thread-safe storage)
4. RealtimeState → Risk Manager (GlobalRiskView monitoring)
5. Position Tools → REST API only (no websocket needed)

**Key Points:**
- WebSocket is for risk management, not position queries
- Position tools use REST only (no forced websocket startup)
- Symbols are dynamically added when positions open
- Symbols are dynamically removed when positions close
- No default symbols - only positions trigger subscriptions

## Development Rules

### Critical Rules

1. **All trades through tools**: Never call `bybit_client` directly from CLI or future agents.
2. **No hardcoding**: Symbols, sizes, paths all from config.
3. **Safety first**: Risk manager checks before every order.
4. **Demo first**: Test on demo API before live.

### File Organization

- **Core modules** (`src/core/`): Exchange, position, risk, safety.
- **Tools** (`src/tools/`): Public API surface for CLI/agents.
- **Data** (`src/data/`): Market data, historical storage, realtime state.
- **Utils** (`src/utils/`): Logging, rate limiting, helpers.

### Available Order Types

The bot supports all Bybit UTA order types:
- **Market Orders**: `market_buy`, `market_sell`, `market_buy_with_tpsl`, `market_sell_with_tpsl`
- **Limit Orders**: `limit_buy`, `limit_sell`, `partial_close`
- **Stop Orders**: `stop_market_buy`, `stop_market_sell`, `stop_limit_buy`, `stop_limit_sell`
- **Order Management**: `get_open_orders`, `cancel_order`, `amend_order`, `cancel_all_orders`
- **Batch Orders**: `batch_market_orders`, `batch_limit_orders`, `batch_cancel_orders`

See `tests/test_comprehensive_smoke.py` for test coverage.

## Environment Variables

```bash
# api_keys.env
TRADING_MODE=paper
BYBIT_USE_DEMO=true

BYBIT_DEMO_API_KEY=your_key
BYBIT_DEMO_API_SECRET=your_secret
BYBIT_LIVE_API_KEY=your_key
BYBIT_LIVE_API_SECRET=your_secret

MAX_LEVERAGE=3
MAX_POSITION_SIZE_USD=50
MAX_DAILY_LOSS_USD=20

# WebSocket Configuration
ENABLE_WEBSOCKET=true
WS_AUTO_START=true
WS_STARTUP_TIMEOUT=10.0
WS_SHUTDOWN_TIMEOUT=5.0
DEFAULT_SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT
```

## API Rate Limits

Follow Bybit V5 limits:
- IP (public): 600/5sec
- Account/Position: 50/sec
- Orders: 10/sec/symbol

Rate limiter in `src/utils/rate_limiter.py` handles this.

## Safety Features

- **Panic button**: `panic_close_all_tool()` closes all positions
- **Risk limits**: Enforced by `RiskManager`
- **Demo mode**: Default safe testing environment

## Reference Documentation

- **Bybit API**: `C:\CODE\AI\TRADE\reference\exchanges\bybit\docs\v5\`
- **pybit SDK**: `C:\CODE\AI\TRADE\reference\exchanges\pybit\`
