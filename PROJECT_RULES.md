# TRADE Project Rules

## Core Principles

1. **Safety First**: All orders go through risk manager. Demo mode by default.
2. **Modular Always**: Each component has a single responsibility.
3. **Tools as API**: All operations go through `src/tools/*` with `ToolRegistry` for orchestration.
4. **No Hardcoding**: Symbols, sizes, paths from config.

## Strict Trading Mode / API Mapping

**Canonical Contract**: Trading mode and API environment have a strict 1:1 mapping:

| TRADING_MODE | BYBIT_USE_DEMO | Result | Account |
|--------------|----------------|--------|---------|
| `paper` | `true` | ✅ Valid | Demo account (fake funds) |
| `real` | `false` | ✅ Valid | Live account (real funds) |
| `paper` | `false` | ❌ BLOCKED | Invalid configuration |
| `real` | `true` | ❌ BLOCKED | Invalid configuration |

**Key Points**:
- We **never simulate** trades. Both modes execute real orders on Bybit.
- The difference is which account (demo vs live) receives those orders.
- Invalid combinations are hard errors that block startup/trading.
- Data API (market data, historical data) **always** uses LIVE API for accuracy.
- WebSocket endpoints match the trading mode (demo WS for paper, live WS for real).

**Strict API Key Contract (No Fallbacks)**:
- `BYBIT_DEMO_API_KEY` → Required for DEMO mode trading
- `BYBIT_LIVE_API_KEY` → Required for LIVE mode trading
- `BYBIT_LIVE_DATA_API_KEY` → Required for all data operations (always LIVE)
- Generic keys (`BYBIT_API_KEY`) are **NOT used** - no fallbacks allowed

## Code Organization

### What Goes Where

| Location | Purpose |
|----------|---------|
| `src/exchanges/` | Exchange API clients only |
| `src/core/` | Core trading logic (exchange manager, risk, safety) |
| `src/data/` | Market data, historical storage, realtime state |
| `src/tools/` | Public API surface for CLI/agents |
| `src/utils/` | Logging, rate limiting, helpers |
| `src/config/` | Configuration management |

### File Size Limits

- Keep files under 1500 lines
- Split if larger

## Coding Standards

### All Tools Return ToolResult

```python
from src.tools.shared import ToolResult

def my_tool(param: str) -> ToolResult:
    try:
        # Do work
        return ToolResult(success=True, message="Done", data={"key": "value"})
    except Exception as e:
        return ToolResult(success=False, error=str(e))
```

### No Direct Bybit Calls from CLI

```python
# BAD
from src.exchanges.bybit_client import BybitClient
client = BybitClient()
client.get_positions()

# GOOD
from src.tools import list_open_positions_tool
result = list_open_positions_tool()
```

### Use Config for Everything

```python
# BAD
leverage = 5
symbol = "BTCUSDT"

# GOOD
from src.config.config import get_config
config = get_config()
leverage = config.risk.max_leverage
symbols = config.trading.default_symbols
```

## Safety Rules

1. **Demo First**: Always test on demo API before live
2. **Risk Limits**: Never bypass risk manager
3. **Panic Available**: Panic button must always work
4. **Log Everything**: Every order, every error
5. **Real Interface Testing**: Always test through actual CLI/interface, never synthetic unit tests alone

## Tool Registry

The `ToolRegistry` (`src/tools/tool_registry.py`) provides:
- Dynamic tool discovery and execution
- AI/LLM function calling format
- Batch execution
- Category-based filtering

Use it for orchestrators, bots, and AI agents that need to dynamically select and execute tools.

## Markdown Editing

When editing markdown files:
- Use `search_replace` for targeted edits
- Don't rewrite entire files
- If full rewrite needed, ask user first
