# TRADE System Review

## Architecture Overview

TRADE is a **production-ready, modular trading bot** for Bybit Unified Trading Account (UTA).

### Layers

1. **Exchange Layer** (`src/exchanges/bybit_client.py`)
   - Direct Bybit API access (HTTP + WebSocket)
   - Complete UTA support (Demo & Live)
   - Rate limiting
   - Authentication handling

2. **Core Layer** (`src/core/`)
   - `exchange_manager.py` - Unified trading interface (all order types)
   - `position_manager.py` - Position tracking
   - `risk_manager.py` - Risk controls
   - `order_executor.py` - Order execution
   - `safety.py` - Panic and circuit breakers

3. **Data Layer** (`src/data/`)
   - `market_data.py` - Live market data
   - `historical_data_store.py` - DuckDB storage
   - `realtime_state.py` - WebSocket state

4. **Tools Layer** (`src/tools/`)
   - Public API surface (35+ tools)
   - All operations return `ToolResult`
   - `tool_registry.py` - Tool discovery & orchestration
   - CLI, orchestrators, and AI agents call tools

5. **Config & Utils** (`src/config/`, `src/utils/`)
   - Central configuration
   - Logging, rate limiting, helpers

## Key Design Decisions

### Tools as API Surface
All operations go through `src/tools/*`. This ensures:
- Consistent return types (`ToolResult`)
- Single integration point for CLI, orchestrators, AI agents, HTTP
- No direct Bybit API calls from consumers
- Tool Registry enables dynamic tool discovery and execution

### Complete Order Type Support
The bot supports all Bybit UTA order types:
- Market orders (with optional TP/SL)
- Limit orders (GTC, IOC, FOK, PostOnly)
- Stop Market orders (conditional)
- Stop Limit orders (conditional)
- Batch orders (up to 10 per batch)
- Partial position closes

### Safety First
- Risk manager checks before every order
- Panic button always available
- Demo mode by default

## Module Dependencies

```
trade_cli.py
    └── src/tools/*
            └── src/core/*
                    └── src/exchanges/bybit_client.py
                            └── pybit (Bybit SDK)
```

## Configuration

All configuration via `api_keys.env`:
- `BYBIT_USE_DEMO` - Demo vs Live API
- `TRADING_MODE` - Paper vs Real trading
- `MAX_LEVERAGE`, `MAX_POSITION_SIZE_USD`, etc.

## Available Tools

### Order Tools (15+)
- Market: `market_buy`, `market_sell`, `market_buy_with_tpsl`, `market_sell_with_tpsl`
- Limit: `limit_buy`, `limit_sell`, `partial_close`
- Stop: `stop_market_buy`, `stop_market_sell`, `stop_limit_buy`, `stop_limit_sell`
- Management: `get_open_orders`, `cancel_order`, `amend_order`, `cancel_all_orders`
- Batch: `batch_market_orders`, `batch_limit_orders`, `batch_cancel_orders`

### Position Tools (10+)
- Query: `list_open_positions`, `get_position`
- TP/SL: `set_take_profit`, `set_stop_loss`, `remove_take_profit`, `remove_stop_loss`
- Trailing: `set_trailing_stop`, `set_trailing_stop_percent`
- Close: `close_position`, `panic_close_all`

### Account & Market Data (10+)
- Account: `get_balance`, `get_portfolio`, `set_leverage`
- Market: `get_price`, `get_ohlcv`, `get_funding_rate`

See `src/tools/__init__.py` for the complete list.

## Known Limitations & Future Refactoring

### ExchangeManager Singleton Limitation

**Current State:**
- `ExchangeManager` uses a singleton pattern via `_get_exchange_manager()` in `src/tools/shared.py`
- Only **one instance** can exist per process, locked to the `BYBIT_USE_DEMO` setting at initialization
- Cannot have both demo and live instances simultaneously
- Cannot switch between demo/live without process restart

**Current Approach (Demo Phase):**
- ✅ **Safe for demo trading**: Single environment per process is actually a safety feature
- ✅ **Simple and clear**: One process = one environment, no confusion
- ✅ **Sufficient for current needs**: Demo account testing, strategy development, agent integration

**Future Refactoring (Before Going Live):**

When ready for live trading, consider refactoring to support:

1. **Trading Profiles System**
   - Introduce `TradingProfile` abstraction (name, env, keys, risk config)
   - Support multiple profiles per process (demo + live, or multiple accounts)
   - Each profile owns its own `ExchangeManager`, `RiskManager`, etc.

2. **ExchangeManager Factory Pattern**
   - Replace singleton with factory: `get_exchange_manager(profile_id: str = "default")`
   - Registry pattern: `{profile_id -> ExchangeManager}`
   - `ExchangeManager` constructor accepts explicit `profile` or `use_demo` parameter

3. **Profile-Aware Tools & API**
   - Tools accept optional `profile_id` parameter
   - Tool Registry can be profile-scoped (agent gets only demo tools)
   - HTTP API endpoints include profile selection
   - All operations explicitly specify which environment they target

4. **Enhanced Safety Guard Rails**
   - Live profiles require explicit enablement (`ALLOW_LIVE_TRADING=true`)
   - Profile validation and isolation
   - Logging always includes `profile_id` and environment
   - No fallback between live/demo credentials

**Alternative Approach (Simpler):**
- Keep singleton pattern but run **separate processes** for demo and live
- Orchestrator/agents choose environment by **which service URL** they call
- Each process is locked to one environment (safety feature)
- No code refactoring needed, just deployment architecture

**Decision Point:**
- If you need **multiple environments in one process** (e.g., agent swarm with mixed demo/live): Refactor to profiles
- If **one environment per process is acceptable**: Keep current design, use separate deployments

**Files to Modify (if refactoring):**
- `src/tools/shared.py` - Factory function instead of singleton
- `src/core/exchange_manager.py` - Accept profile/config parameter
- `src/config/config.py` - Profile management
- `src/tools/*.py` - Add profile_id parameter to tools
- `src/tools/tool_registry.py` - Profile-aware tool registration