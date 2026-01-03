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

## Active TODOs

No active work in this module. Stable.

See `docs/todos/` for project-wide tracking.
