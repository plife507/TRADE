# Core Module

Live trading execution. Exchange-native semantics.

## Key Files

| File | Purpose |
|------|---------|
| `risk_manager.py` | Pre-trade risk checks |
| `position_manager.py` | Position state tracking |
| `order_executor.py` | Order submission logic |

## Rules

- **Currency**: Use `size_usdt` globally (unified across live and simulator domains)
- **API boundary**: Go through `src/tools/`, never `bybit_client` directly
- **Demo first**: Test in demo before live
- **Domain isolation**: Do NOT import from `src/backtest/`

## Relationship to The Forge

The Forge (`src/forge/`) is for strategy development and validation. Once a Play is validated in the Forge, it can be promoted to live trading through this module. The Core module handles actual order execution and position management.

## Active TODOs

No active work in this module. Stable.

See `docs/todos/` for project-wide tracking.
