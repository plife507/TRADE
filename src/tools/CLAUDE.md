# Tools Module

CLI/API surface. Primary interface for all operations.

## Key Files

| File | Purpose |
|------|---------|
| `backtest_cli_wrapper.py` | Backtest CLI tools |
| `order_tools.py` | Order placement |
| `position_tools.py` | Position management |
| `data_tools.py` | Data sync tools |

## Rules

- **Single entry point**: External callers use tools, not internal modules
- **ToolResult**: All tools return ToolResult with success/error
- **ToolRegistry**: Use for dynamic discovery

```python
from src.tools import ToolRegistry
registry = ToolRegistry()
registry.execute("market_buy", symbol="SOLUSDT", usd_amount=100)
```

## Active TODOs

No active work in this module. Stable.

See `docs/todos/` for project-wide tracking.
