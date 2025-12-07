# CLAUDE.md

Guidance for Claude when working with the TRADE trading bot.

> **Code examples**: See `docs/CODE_EXAMPLES.md` | **Env vars**: See `env.example`

## Project Overview

TRADE is a **modular, production-ready** Bybit futures trading bot with complete UTA support, comprehensive order types, position management, tool registry for orchestrator/bot integration, and risk controls.

**Key Philosophy**: Safety first, modular always, tools as the API surface.

## Quick Reference

```bash
python trade_cli.py                     # Run interactive CLI
python trade_cli.py --smoke full        # Full smoke test (data + trading)
python trade_cli.py --smoke data_extensive  # Extensive data test (clean DB, gaps, sync)
pip install -r requirements.txt         # Dependencies
```

## Architecture

```
TRADE/
├── src/
│   ├── config/config.py           # Central configuration
│   ├── exchanges/bybit_client.py  # Bybit API wrapper
│   ├── core/                      # Exchange, position, risk, safety, order execution
│   ├── data/                      # Market data, DuckDB storage, WebSocket state
│   ├── risk/global_risk.py        # Account-level risk
│   ├── tools/                     # CLI/API surface (PRIMARY INTERFACE)
│   └── utils/                     # Logging, rate limiting, helpers
├── docs/
│   ├── examples/orchestrator_example.py  # Full orchestrator/bot example
│   ├── CODE_EXAMPLES.md                 # Code snippets reference
│   ├── architecture/                   # Architecture docs
│   ├── project/                         # Project documentation
│   └── guides/                          # Setup/development guides
├── CLAUDE.md                            # AI assistant guidance (this file)
└── trade_cli.py                         # CLI entry point
```

## Critical Rules

1. **All trades through tools**: Never call `bybit_client` directly - use `src/tools/*`
2. **No hardcoding**: Symbols, sizes, paths from config or user input
3. **Safety first**: Risk manager checks before every order
4. **Demo first**: Test on demo API before live
5. **Reference docs first**: Check `reference/exchanges/` for API examples before implementing - compare to existing implementation before changes
6. **Preserve working code**: As complexity grows, verify existing processes work before modifying - don't rewrite what's already functional. If rewrite is necessary, explain why and wait for human approval before proceeding

## Agent Planning Rules

**Todo lists must be clean, actionable, and context-efficient:**
- Keep todo items short (<70 chars) - high-level goals, not implementation details
- Avoid verbose descriptions - use terse action phrases
- Never include operational steps (linting, searching, reading files) as todos
- As context window fills, consolidate completed todos and summarize progress
- Reference external files (`docs/CODE_EXAMPLES.md`, `env.example`) instead of inlining code
- When approaching max context: prioritize essential state, drop verbose history

## Tool Layer (Primary API)

All operations go through `src/tools/*`. Tools return `ToolResult` objects.

For orchestrators/bots, use `ToolRegistry` for dynamic tool discovery and execution:
- `registry.list_tools(category="orders")` - List tools
- `registry.execute("market_buy", symbol="SOLUSDT", usd_amount=100)` - Execute
- `registry.get_tool_info("market_buy")` - Get specs for AI agents

**See**: `docs/CODE_EXAMPLES.md` for complete usage patterns

## Available Order Types

| Category | Tools |
|----------|-------|
| Market | `market_buy`, `market_sell`, `market_buy_with_tpsl`, `market_sell_with_tpsl` |
| Limit | `limit_buy`, `limit_sell`, `partial_close` |
| Stop | `stop_market_buy`, `stop_market_sell`, `stop_limit_buy`, `stop_limit_sell` |
| Management | `get_open_orders`, `cancel_order`, `amend_order`, `cancel_all_orders` |
| Batch | `batch_market_orders`, `batch_limit_orders`, `batch_cancel_orders` |

## Time-Range Queries (CRITICAL)

**All history endpoints require explicit time ranges.** Never rely on Bybit's implicit defaults.

| Endpoint | Default | Max Range |
|----------|---------|-----------|
| Transaction Log | 24h | 7 days |
| Order/Trade History | 7d | 7 days |
| Closed PnL | 7d | 7 days |
| Borrow History | 30d | 30 days |

Use `TimeRange` abstraction: `TimeRange.last_24h()`, `TimeRange.from_window_string("4h")`

## Four-Leg API Architecture

The system has 4 independent API "legs" with strict separation:

| Leg | Purpose | Endpoint | Key Variable |
|-----|---------|----------|--------------|
| Trade LIVE | Real money trading | api.bybit.com | `BYBIT_LIVE_API_KEY` |
| Trade DEMO | Fake money trading | api-demo.bybit.com | `BYBIT_DEMO_API_KEY` |
| Data LIVE | Backtest/research data | api.bybit.com | `BYBIT_LIVE_DATA_API_KEY` |
| Data DEMO | Demo validation data | api-demo.bybit.com | `BYBIT_DEMO_DATA_API_KEY` |

**Selection:**
- Trading env: Set via `BYBIT_USE_DEMO` (true=demo, false=live) in env
- Data env: CLI Data Builder menu option 23 toggles LIVE/DEMO, or pass `env="demo"` to tools

**Smoke Tests:**
- `--smoke data/full/data_extensive/orders`: Force DEMO trading + LIVE data (safe)
- `--smoke live_check`: Uses LIVE credentials (opt-in, needs LIVE keys)

## REST vs WebSocket

| Use Case | REST | WebSocket |
|----------|------|-----------|
| Current state | ✅ Primary | ❌ |
| Execute trades | ✅ Always | ❌ |
| Position queries | ✅ Always | ❌ |
| Risk monitoring | ✅ Basic | ✅ GlobalRiskView (real-time) |

**Key**: Position tools use REST only. WebSocket is ONLY for GlobalRiskView risk monitoring.

## API Rate Limits

| Endpoint Type | Limit | Bot Uses |
|---------------|-------|----------|
| IP (public) | 600/5sec | 100/sec |
| Account/Position | 50/sec | 40/sec |
| Orders | 10/sec/symbol | 8/sec |

Rate limiter: `src/utils/rate_limiter.py`

## DEMO vs LIVE API (CRITICAL SAFETY)

| Environment | Endpoint | Money | Purpose |
|-------------|----------|-------|---------|
| **DEMO** | api-demo.bybit.com | FAKE | Testing |
| **LIVE** | api.bybit.com | REAL | Production |

### Strict Mode Mapping

```
✅ TRADING_MODE=paper + BYBIT_USE_DEMO=true   → Demo (fake funds)
✅ TRADING_MODE=real  + BYBIT_USE_DEMO=false  → Live (real funds)
❌ All other combinations → BLOCKED at startup
```

### Data vs Trading Separation

| Operation | API Used |
|-----------|----------|
| Historical/market data | **ALWAYS LIVE** |
| Trading (orders, positions) | **Configured** (demo or live) |

**Configuration**: See `env.example` for all environment variables

## Safety Features

- **Panic button**: `panic_close_all_tool()` closes all positions
- **Risk limits**: Enforced by `RiskManager`
- **Demo mode**: Default safe testing environment
- **Mode validation**: Prevents TRADING_MODE/BYBIT_USE_DEMO mismatches

## File Organization

| Directory | Contents |
|-----------|----------|
| `src/core/` | Exchange, position, risk, safety |
| `src/tools/` | Public API surface for CLI/agents |
| `src/data/` | Market data, historical storage, realtime state |
| `src/utils/` | Logging, rate limiting, helpers |

## Reference Documentation

**ALWAYS reference for API/exchange work:**
- Bybit API: `reference/exchanges/bybit/docs/v5/`
- pybit SDK: `reference/exchanges/pybit/`

Never guess API parameters, endpoints, or behavior - verify against reference docs.

## Smoke Tests

| Mode | Command | Env | Description |
|------|---------|-----|-------------|
| Full | `--smoke full` | DEMO | All CLI features (data + trading + diagnostics) |
| Data | `--smoke data` | DEMO | Data builder only |
| Data Extensive | `--smoke data_extensive` | DEMO | Clean DB, build sparse history, fill gaps, sync to now |
| Orders | `--smoke orders` | DEMO | All order types: market, limit, stop, TP/SL, trailing |
| Live Check | `--smoke live_check` | LIVE | Opt-in LIVE connectivity test (requires LIVE keys) |

The `data_extensive` test:
1. Deletes ALL existing data (clean slate)
2. Builds sparse OHLCV history with intentional date gaps
3. Syncs funding rates and open interest
4. Fills gaps and syncs to current
5. Queries all data types
6. Runs maintenance tools (heal, cleanup, vacuum)
7. Verifies final database state

**WARNING**: `delete_all_data_tool` is available in Data Builder menu (option 19) - this permanently deletes all historical data.

## External References

| Topic | File |
|-------|------|
| Code examples | `docs/CODE_EXAMPLES.md` |
| Orchestrator example | `docs/examples/orchestrator_example.py` |
| Environment variables | `env.example` |
| Data architecture | `docs/architecture/DATA_ARCHITECTURE.md` |
| Project rules | `docs/project/PROJECT_RULES.md` |
