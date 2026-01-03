# Data Module

Market data storage. Domain-agnostic.

## Key Files

| File | Purpose |
|------|---------|
| `historical_data_store.py` | DuckDB OHLCV (source of truth) |
| `data_manager.py` | Sync, gap filling |

## Rules

- **Source of truth**: DuckDB for all historical data
- **No trading logic**: Data only, no execution semantics
- **Explicit time ranges**: Never rely on implicit defaults
- **Domain agnostic**: Used by both live and simulator

## Active TODOs

No active work in this module. Stable.

See `docs/todos/` for project-wide tracking.
