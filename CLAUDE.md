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

### Historical Data Tools
Data tools are available via the registry for orchestrators/agents:

```python
# List data tools by category
registry.list_tools(category="data.info")     # Database info, symbol status
registry.list_tools(category="data.sync")     # Sync, build history, fill gaps
registry.list_tools(category="data.maintenance")  # Heal, delete, vacuum

# Build complete history for a symbol (OHLCV + funding + OI)
result = registry.execute("build_symbol_history", symbols=["BTCUSDT"], period="1M")

# Sync forward to now (only new candles, no backfill)
result = registry.execute("sync_to_now", symbols=["BTCUSDT", "ETHUSDT"])

# View symbol timeframe ranges with date coverage
result = registry.execute("get_symbol_timeframe_ranges")
```

### Time-Range Aware History Queries (CRITICAL)

**All history endpoints require explicit time ranges.** We never rely on Bybit's implicit defaults (24h for transaction log, 7d for orders, etc.).

```python
from src.utils.time_range import TimeRange, parse_time_window

# Create time ranges from presets
time_range = TimeRange.last_24h()
time_range = TimeRange.last_7d()
time_range = TimeRange.from_window_string("4h")

# Tools accept window string or explicit timestamps
result = registry.execute("get_order_history", window="7d", symbol="BTCUSDT")
result = registry.execute("get_transaction_log", window="24h", category="linear")
result = registry.execute("get_borrow_history", window="30d")  # Max 30d for borrow

# Results include time_range metadata
print(result.data["time_range"])  # {"start_ms": ..., "end_ms": ..., "label": "last_7d"}
```

**Bybit API Time Constraints:**

| Endpoint | Default (without params) | Max Range |
|----------|--------------------------|-----------|
| Transaction Log | 24 hours | 7 days |
| Order History | 7 days | 7 days |
| Trade History | 7 days | 7 days |
| Closed PnL | 7 days | 7 days |
| Borrow History | 30 days | 30 days |

The `TimeRange` abstraction enforces these limits and ensures all API calls include explicit `startTime`/`endTime` parameters.

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

# STRICT: Canonical keys required (no fallbacks)
# Demo trading (required for DEMO mode)
BYBIT_DEMO_API_KEY=your_demo_key
BYBIT_DEMO_API_SECRET=your_demo_secret

# Live trading (required for LIVE mode)
BYBIT_LIVE_API_KEY=your_live_key
BYBIT_LIVE_API_SECRET=your_live_secret

# Live data (ALWAYS required - data uses LIVE API)
BYBIT_LIVE_DATA_API_KEY=your_live_readonly_key
BYBIT_LIVE_DATA_API_SECRET=your_live_readonly_secret

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
- **Trading mode validation**: Prevents dangerous mismatches between TRADING_MODE and BYBIT_USE_DEMO

## DEMO vs LIVE API - Critical Safety Architecture

### API Environments

Bybit provides two separate API environments:

| Environment | API Endpoint | WebSocket | Money | Purpose |
|-------------|--------------|-----------|-------|---------|
| **DEMO** | api-demo.bybit.com | stream-demo.bybit.com | FAKE ($1000) | Testing, development |
| **LIVE** | api.bybit.com | stream.bybit.com | REAL | Production trading |

### Data vs Trading Separation (IMPORTANT!)

The bot separates **data operations** from **trading operations**:

| Operation | API Used | Reason |
|-----------|----------|--------|
| Historical data sync | **ALWAYS LIVE** | Accurate market data |
| Market data (prices, tickers) | **ALWAYS LIVE** | Real market prices |
| Data capture | **ALWAYS LIVE** | Accurate data collection |
| Trading (orders, positions) | **Configured** | Depends on BYBIT_USE_DEMO |

```python
# Data operations ALWAYS use LIVE API (regardless of BYBIT_USE_DEMO)
from src.data.historical_data_store import get_historical_store
store = get_historical_store()  # Uses api.bybit.com

# Trading operations use configured API
from src.core.exchange_manager import ExchangeManager
exchange = ExchangeManager()  # Uses api-demo.bybit.com or api.bybit.com
```

### Safety Guard Rails (Strict Mapping)

The bot enforces a **strict 1:1 mapping** between trading mode and API environment:

```python
# ✅ VALID COMBINATIONS (only these two are allowed)
TRADING_MODE=paper + BYBIT_USE_DEMO=true   # ✅ Demo account (fake funds, real API orders)
TRADING_MODE=real + BYBIT_USE_DEMO=false   # ✅ Live account (real funds, real API orders)

# ❌ INVALID COMBINATIONS (hard errors, blocked at startup)
TRADING_MODE=real + BYBIT_USE_DEMO=true   # ❌ BLOCKED: REAL mode requires LIVE API
TRADING_MODE=paper + BYBIT_USE_DEMO=false  # ❌ BLOCKED: PAPER mode requires DEMO API
```

**Key Point**: We never simulate trades. Both modes execute real orders on Bybit.
The difference is which account (demo vs live) receives those orders.

### Validation at Multiple Levels

1. **Config Validation** (`config.validate_trading_mode_consistency()`)
2. **Pre-Trade Validation** (`ExchangeManager._validate_trading_operation()`)
3. **Order Executor Validation** (`OrderExecutor._validate_trading_mode()`)

### Configuring API Keys

```bash
# LIVE Data API (REQUIRED for all data operations)
BYBIT_LIVE_DATA_API_KEY=your_live_readonly_key
BYBIT_LIVE_DATA_API_SECRET=your_live_readonly_secret

# Demo Trading API (for testing)
BYBIT_DEMO_API_KEY=your_demo_key
BYBIT_DEMO_API_SECRET=your_demo_secret

# Live Trading API (for production - handle with care!)
BYBIT_LIVE_API_KEY=your_live_trading_key
BYBIT_LIVE_API_SECRET=your_live_trading_secret
```

### Best Practices

1. **Configure all 3 required keys** - BYBIT_DEMO_API_KEY (for demo), BYBIT_LIVE_API_KEY (for live), BYBIT_LIVE_DATA_API_KEY (for data)
2. **Start with DEMO trading** - Use `BYBIT_USE_DEMO=true` for development
3. **Use read-only keys for data** - Separate rate limit pools (120 RPS vs 50 RPS)
4. **No fallbacks** - Missing keys cause hard errors; generic keys (BYBIT_API_KEY) are NOT used

## API Modes & Visibility

### Where to See Current API Environment

The bot provides multiple ways to inspect which APIs are in use:

1. **CLI Header**: Shows trading mode (DEMO/LIVE) and API URLs in the subtitle
2. **CLI Menus**: Data Builder and Market Data menus show data API source status
3. **Connection Test** (Option 6): Displays detailed API environment table
4. **Health Check** (Option 7): Shows API environment and mode consistency status
5. **Logs**: All components log their API mode on initialization

### Programmatic Access

Use `get_api_environment_tool()` or the registry:

```python
from src.tools import get_api_environment_tool

result = get_api_environment_tool()
if result.success:
    print(result.data["trading"]["mode"])  # "DEMO" or "LIVE"
    print(result.data["data"]["mode"])     # Always "LIVE"
    print(result.data["websocket"]["mode"]) # Matches trading mode

# Via registry (for agents)
registry.execute("get_api_environment")
```

### Key Points

- **Data Builder & Market Data**: Always use LIVE API (`api.bybit.com`) for accuracy
- **Trading operations**: Use DEMO or LIVE based on `BYBIT_USE_DEMO` setting
- **WebSocket**: Matches trading mode (DEMO streams for demo trading)

## Reference Documentation

### Exchange API Reference (CRITICAL)

**ALWAYS reference `C:\CODE\AI\TRADE\reference\exchanges` for ALL API and exchange interface information.**

When working with exchange APIs, endpoints, or implementing exchange features:
1. **First consult** the reference documentation in `C:\CODE\AI\TRADE\reference\exchanges\`
2. **Bybit API docs**: `C:\CODE\AI\TRADE\reference\exchanges\bybit\docs\v5\` - Complete API reference, endpoints, parameters, error codes
3. **pybit SDK**: `C:\CODE\AI\TRADE\reference\exchanges\pybit\` - SDK implementation details, examples, usage patterns
4. **Never guess** API parameters, endpoints, rate limits, or behavior - always verify against reference docs
5. **When in doubt**, read the reference files before implementing or modifying exchange-related code

### Reference Paths

- **Bybit API**: `C:\CODE\AI\TRADE\reference\exchanges\bybit\docs\v5\`
- **pybit SDK**: `C:\CODE\AI\TRADE\reference\exchanges\pybit\`
