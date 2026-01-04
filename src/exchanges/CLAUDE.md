# Exchanges Module

Bybit API client. Live trading domain.

## Key Files

| File | Purpose |
|------|---------|
| `bybit_client.py` | Pybit SDK wrapper |

## Rules

- **Never call directly** - All trades go through `src/tools/`
- **Check reference docs** - `reference/exchanges/bybit/docs/v5/`
- **Four-leg API** - Trade LIVE/DEMO + Data LIVE/DEMO (see root CLAUDE.md)

## Rate Limits

| Endpoint | Limit |
|----------|-------|
| IP (public) | 600/5sec |
| Account/Position | 50/sec |
| Orders | 10/sec/symbol |

## Relationship to The Forge

The Forge (`src/forge/`) uses the SimulatedExchange for backtesting, not this module. This module is only used for live trading execution after a Play has been validated and promoted.

## Active TODOs

No active work in this module. Stable.

See `docs/todos/` for project-wide tracking.
