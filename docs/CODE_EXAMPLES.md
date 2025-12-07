# TRADE Bot - Code Examples Reference

This file contains code examples for the TRADE trading bot. Reference this file when you need implementation patterns.

> **For agents**: These examples are externalized from CLAUDE.md to reduce context window usage. Only load this file when you need specific code patterns.

## Quick Links

- **Full orchestrator example**: See `docs/examples/orchestrator_example.py`
- **Environment variables**: See `env.example`
- **Data architecture**: See `docs/architecture/DATA_ARCHITECTURE.md`

---

## Tool Layer Usage

### Basic Tool Execution

```python
from src.tools import market_buy_tool, get_account_balance_tool, ToolResult

result: ToolResult = get_account_balance_tool()
if result.success:
    print(result.data)
else:
    print(result.error)
```

### Tool Registry (For Orchestrators)

```python
from src.tools.tool_registry import get_registry

registry = get_registry()

# List/execute tools
tools = registry.list_tools(category="orders")
result = registry.execute("market_buy", symbol="SOLUSDT", usd_amount=100)
spec = registry.get_tool_info("market_buy")  # For AI function calling
```

### Data Tools via Registry

```python
registry.list_tools(category="data.info")        # DB info, symbol status
registry.list_tools(category="data.sync")        # Sync, build history
registry.list_tools(category="data.query")       # Query OHLCV, funding, OI
registry.list_tools(category="data.maintenance") # Heal, vacuum

# Build/sync data
result = registry.execute("build_symbol_history", symbols=["BTCUSDT"], period="1M")
result = registry.execute("sync_to_now", symbols=["BTCUSDT", "ETHUSDT"])

# Query data (period OR start/end)
result = registry.execute("get_ohlcv_history", symbol="BTCUSDT", timeframe="1h", period="1M")
result = registry.execute("get_funding_history", symbol="SOLUSDT", start="2024-01-01", end="2024-06-01")
```

---

## Time Range Queries

### Bybit API History (Preset or Custom)

```python
from src.utils.time_range import TimeRange, parse_time_window

# Preset windows
time_range = TimeRange.last_24h()
time_range = TimeRange.last_7d()
time_range = TimeRange.from_window_string("4h")

# Custom date range
from datetime import datetime
time_range = TimeRange.from_dates(
    start=datetime(2024, 1, 1),
    end=datetime(2024, 1, 7),
    endpoint_type="order_history"
)

# Tools accept window strings OR start_ms/end_ms
result = registry.execute("get_order_history", window="7d", symbol="BTCUSDT")
result = registry.execute("get_transaction_log", window="24h", category="linear")

# Custom range via millisecond timestamps
start_ms = int(datetime(2024, 1, 1).timestamp() * 1000)
end_ms = int(datetime(2024, 1, 7).timestamp() * 1000)
result = registry.execute(
    "get_order_history",
    start_ms=start_ms,
    end_ms=end_ms,
    symbol="BTCUSDT"
)
```

### DuckDB Historical Data Queries

```python
# Query OHLCV with period (relative)
result = registry.execute(
    "get_ohlcv_history",
    symbol="BTCUSDT",
    timeframe="1h",
    period="1M"  # Last month
)

# Query OHLCV with custom date range (ISO strings)
result = registry.execute(
    "get_ohlcv_history",
    symbol="BTCUSDT",
    timeframe="1h",
    start="2024-01-01",
    end="2024-06-01"
)

# Query funding rate history
result = registry.execute(
    "get_funding_history",
    symbol="SOLUSDT",
    start="2024-01-01",
    end="2024-03-01"
)

# Query open interest history
result = registry.execute(
    "get_open_interest_history",
    symbol="ETHUSDT",
    period="3M"
)

# Response includes time_range metadata
if result.success:
    data = result.data
    print(f"Records: {data['count']}")
    print(f"Range: {data['time_range']['first_record']} to {data['time_range']['last_record']}")
```

---

## Exchange Manager

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

---

## Configuration

```python
from src.config.config import get_config

config = get_config()
config.bybit.use_demo      # True = demo API
config.risk.max_leverage   # Hard-capped at 10x
config.trading.mode        # "paper" or "real"
```

---

## Application Lifecycle

```python
from src.core.application import Application, get_application

# Context manager (recommended)
with Application() as app:
    # WebSocket auto-started, all components ready
    pass  # Automatic cleanup on exit

# Manual control
app = get_application()
app.initialize()
app.start()
try:
    pass  # Your code
finally:
    app.stop()
```

---

## WebSocket Real-Time Data

```python
from src.data.realtime_state import get_realtime_state

state = get_realtime_state()

if state.is_private_ws_connected:
    ticker = state.get_ticker("BTCUSDT")
    positions = state.get_all_positions()
else:
    from src.tools import list_open_positions_tool
    positions = list_open_positions_tool()  # REST fallback
```

---

## REST-First Position Tools

```python
from src.tools import list_open_positions_tool, get_open_orders_tool

positions = list_open_positions_tool()  # REST: fast, reliable
orders = get_open_orders_tool()         # REST: always works
```

---

## Data API Separation

```python
# Data operations ALWAYS use LIVE API
from src.data.historical_data_store import get_historical_store
store = get_historical_store()  # Uses api.bybit.com

# Trading operations use configured API
from src.core.exchange_manager import ExchangeManager
exchange = ExchangeManager()  # Uses demo or live based on config
```

---

## Safety Mode Validation

```python
# ✅ VALID COMBINATIONS
TRADING_MODE=paper + BYBIT_USE_DEMO=true   # Demo account
TRADING_MODE=real + BYBIT_USE_DEMO=false   # Live account

# ❌ BLOCKED (hard errors)
TRADING_MODE=real + BYBIT_USE_DEMO=true    # Invalid
TRADING_MODE=paper + BYBIT_USE_DEMO=false  # Invalid
```

---

## API Environment Tool

```python
from src.tools import get_api_environment_tool

result = get_api_environment_tool()
if result.success:
    print(result.data["trading"]["mode"])   # "DEMO" or "LIVE"
    print(result.data["data"]["mode"])      # Always "LIVE"
    print(result.data["websocket"]["mode"]) # Matches trading mode

# Via registry
registry.execute("get_api_environment")
```

---

## Agent Trading Environment Selection

Trading tools accept an optional `trading_env` parameter that agents/orchestrators
use to **validate** their intent. This does NOT switch environments - it only checks
that the agent is talking to the correct process.

### Why This Matters

- A running process is either DEMO or LIVE (fixed at startup)
- If an agent asks for `trading_env="live"` on a DEMO process, the tool returns an error
- This prevents accidental trades on the wrong environment

### Basic Usage

```python
from src.tools.tool_registry import get_registry

registry = get_registry()

# Agent asserts it wants DEMO trading
result = registry.execute(
    "market_buy",
    symbol="SOLUSDT",
    usd_amount=100,
    trading_env="demo"  # Validates process is DEMO
)

if not result.success and "trading_env" in result.error:
    # Mismatch: agent asked for DEMO but process is LIVE (or vice versa)
    print("Wrong environment! Route to correct process.")
```

### Checking Process Environment

```python
from src.tools.shared import get_trading_env_summary

# Query what environment this process is configured for
env_info = get_trading_env_summary()
print(env_info)
# {"mode": "DEMO", "use_demo": True, "trading_mode": "paper", "api_endpoint": "api-demo.bybit.com"}

# Or via tool
result = registry.execute("get_api_environment")
process_trading_mode = result.data["trading"]["mode"]  # "DEMO" or "LIVE"
```

### Multi-Process Orchestration Pattern

For orchestrators that need both DEMO and LIVE trading:

```python
# Start two separate processes:
# Process A: BYBIT_USE_DEMO=true, TRADING_MODE=paper  (DEMO)
# Process B: BYBIT_USE_DEMO=false, TRADING_MODE=real  (LIVE)

# Orchestrator routes based on strategy requirements:
class StrategyOrchestrator:
    def __init__(self, demo_process_url, live_process_url):
        self.demo_api = demo_process_url
        self.live_api = live_process_url
    
    def execute_trade(self, strategy_env: str, tool_name: str, **kwargs):
        # Route to correct process
        if strategy_env == "demo":
            return self._call_api(self.demo_api, tool_name, trading_env="demo", **kwargs)
        else:
            return self._call_api(self.live_api, tool_name, trading_env="live", **kwargs)
```

### Environment Validation Flow

```
Agent calls tool with trading_env="demo"
    │
    ▼
Tool checks process config:
- config.bybit.use_demo = True?
- config.trading.mode = "paper"?
    │
    ├── YES → Execute tool normally
    │
    └── NO → Return error:
            "Requested trading_env='demo' but this process is configured for LIVE"
```

### Available in All Trading Tools

```python
# All of these support trading_env validation:
registry.execute("market_buy", symbol="...", usd_amount=100, trading_env="demo")
registry.execute("limit_sell", symbol="...", price=100, usd_amount=50, trading_env="live")
registry.execute("cancel_order", symbol="...", order_id="...", trading_env="demo")
registry.execute("close_position", symbol="...", trading_env="live")
registry.execute("list_positions", trading_env="demo")
registry.execute("get_balance", trading_env="live")
registry.execute("panic_close_all", trading_env="demo")
```

