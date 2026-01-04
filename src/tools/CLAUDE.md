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

## Relationship to The Forge

The Forge (`src/forge/`) uses this tools layer for:
- Running backtests via `backtest_cli_wrapper.py`
- Loading and validating Plays
- Generating performance reports
- Running audits (validation and parity checks)

All Forge operations should go through the tools layer for consistency.

**Architecture Principle**: Tools provide the orchestration layer. The Forge provides pure computation functions. Tools decide WHEN to invoke; Forge defines WHAT to compute.

## Active TODOs

No active work in this module. Stable.

See `docs/todos/` for project-wide tracking.
