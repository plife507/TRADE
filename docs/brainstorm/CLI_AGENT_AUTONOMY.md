# CLI Agent Autonomy — Brainstorm & Audit

Full audit of whether an autonomous agent can operate TRADE entirely from CLI flags,
without the interactive human menu.

**Date:** 2026-02-21
**Verdict:** ~85% agent-ready. Subcommand system is clean. Gaps are missing CLI flag wiring for tool functions that already exist.

---

## Architecture: Dual-Mode CLI

```
                    DUAL-MODE CLI
  ┌──────────────┐              ┌──────────────────────┐
  │ Interactive   │              │ Subcommand System    │
  │ Menu (Human)  │              │ (Agent-Friendly)     │
  │               │              │                      │
  │ 17 menus      │              │ 7 command groups     │
  │ 305 prompts   │              │ --json on all        │
  │ while True    │              │ Exit codes 0/1       │
  │ Prompt.ask()  │              │ No input() calls     │
  └──────┬───────┘              └──────────┬───────────┘
         │                                  │
         └──────────┐    ┌─────────────────┘
                    ▼    ▼
              ┌─────────────────┐
              │  src/tools/     │  110+ tool functions
              │  (Programmatic  │  ToolResult envelope
              │   API layer)    │  No blocking I/O
              └────────┬────────┘
                       ▼
         ┌─────────────────────────┐
         │ Exchange / DuckDB / FS  │
         └─────────────────────────┘
```

Both paths call the **same tool functions**. Menu collects parameters interactively;
subcommands collect them via flags. The tool layer has **zero interactive elements**.

---

## What Works Today (Agent-Ready)

### Backtest & Validation (100% CLI-capable)

```bash
python trade_cli.py backtest run --play X [--synthetic] [--sync] --json
python trade_cli.py backtest preflight --play X --json
python trade_cli.py backtest list --json
python trade_cli.py backtest indicators --play X --json
python trade_cli.py backtest data-fix --play X [--heal] --json
python trade_cli.py backtest play-normalize --play X [--write] --json
python trade_cli.py backtest play-normalize-batch --dir DIR --json

python trade_cli.py validate quick|standard|full|real --json
python trade_cli.py validate module --module X --json
python trade_cli.py validate pre-live --play X --json
python trade_cli.py validate exchange --json
```

### Play Lifecycle (100% CLI-capable)

```bash
python trade_cli.py play run --play X --mode demo|live [--confirm] --json
python trade_cli.py play status [--play X] --json
python trade_cli.py play stop --play X [--force] [--all] [--close-positions]
python trade_cli.py play pause --play X
python trade_cli.py play resume --play X
python trade_cli.py play logs --play X [-n 50]
```

### Debug (100% CLI-capable)

```bash
python trade_cli.py debug math-parity --play X --start D --end D --json
python trade_cli.py debug snapshot-plumbing --play X --start D --end D --json
python trade_cli.py debug determinism --run-a A --run-b B --json
python trade_cli.py debug metrics --json
```

### Account & Positions (Partial)

```bash
python trade_cli.py account balance --json        # works
python trade_cli.py account exposure --json        # works
python trade_cli.py position list --json           # works
python trade_cli.py position close SYMBOL          # works
python trade_cli.py panic --confirm                # works
```

---

## What's Missing (Gaps)

### P0: Order Management (CRITICAL — no CLI surface)

Tool functions exist but have zero CLI wiring:

| Tool Function | Parameters | CLI Needed |
|--------------|-----------|------------|
| `market_buy_tool` | symbol, usd_amount, trading_env | `order buy --symbol X --amount 100 --type market` |
| `market_sell_tool` | symbol, usd_amount, trading_env | `order sell --symbol X --amount 100 --type market` |
| `limit_buy_tool` | symbol, usd_amount, price, tif, reduce_only | `order buy --symbol X --amount 100 --type limit --price 50000` |
| `limit_sell_tool` | symbol, usd_amount, price, tif, reduce_only | `order sell --symbol X --amount 100 --type limit --price 50000` |
| `stop_market_buy_tool` | symbol, usd_amount, trigger_price, ... | `order buy --symbol X --amount 100 --type stop --trigger 48000` |
| `stop_limit_buy_tool` | symbol, usd_amount, trigger_price, limit_price, ... | `order buy --symbol X --type stop-limit --trigger 48000 --price 47500` |
| `market_buy_with_tpsl_tool` | symbol, usd_amount, take_profit, stop_loss | `order buy --symbol X --amount 100 --tp 55000 --sl 45000` |
| `get_open_orders_tool` | symbol, order_filter, limit | `order list [--symbol X] --json` |
| `amend_order_tool` | symbol, order_id, qty, price, tp, sl, trigger | `order amend --order-id ABC --qty 0.02 --price 50000` |
| `cancel_order_tool` | symbol, order_id | `order cancel --symbol X --order-id ABC` |
| `cancel_all_orders_tool` | symbol | `order cancel-all [--symbol X]` |
| `batch_market_orders_tool` | orders[] | `order batch --file orders.json` |
| `set_leverage_tool` | symbol, leverage | `order leverage --symbol X --leverage 3` |

### P1: Data Management (no CLI surface)

| Tool Function | CLI Needed |
|--------------|------------|
| `sync_symbols_tool` | `data sync --symbols BTCUSDT,ETHUSDT --period 30d` |
| `sync_range_tool` | `data sync --symbol X --start 2025-01-01 --end 2025-06-30` |
| `heal_data_tool` | `data heal --symbol X` |
| `get_database_stats_tool` | `data info --json` |
| `list_cached_symbols_tool` | `data symbols --json` |
| `get_symbol_status_tool` | `data status --symbol X --json` |
| `get_ohlcv_history_tool` | `data query --symbol X --tf 1m --limit 100 --json` |
| `vacuum_database_tool` | `data vacuum` |
| `delete_symbol_tool` | `data delete --symbol X --confirm` |

### P1: Market Data Queries (no CLI surface)

| Tool Function | CLI Needed |
|--------------|------------|
| `get_price_tool` | `market price --symbol X --json` |
| `get_ohlcv_tool` | `market ohlcv --symbol X --tf 15m --limit 100 --json` |
| `get_funding_rate_tool` | `market funding --symbol X --json` |
| `get_open_interest_tool` | `market oi --symbol X --json` |
| `get_orderbook_tool` | `market orderbook --symbol X --json` |
| `get_instruments_tool` | `market instruments --json` |

### P1: Account History (needs date flags)

| Tool Function | CLI Needed |
|--------------|------------|
| `get_order_history_tool` | `account history --days 7 --json` OR `--start D --end D` |
| `get_closed_pnl_tool` | `account pnl --days 7 --json` OR `--start D --end D` |
| `get_transaction_log_tool` | `account transactions --days 7 --json` |
| `get_borrow_history_tool` | `account borrows --days 30 --json` |
| `get_collateral_info_tool` | `account collateral [--currency USDT] --json` |

### P2: Position Config (needs flag wiring)

| Tool Function | CLI Needed |
|--------------|------------|
| `set_stop_loss_tool` | `position set-sl --symbol X --price 45000` |
| `set_take_profit_tool` | `position set-tp --symbol X --price 55000` |
| `set_position_tpsl_tool` | `position set-tpsl --symbol X --tp 55000 --sl 45000` |
| `set_trailing_stop_tool` | `position trailing --symbol X --distance 500` |
| `partial_close_position_tool` | `position partial-close --symbol X --percent 50` |
| `switch_margin_mode_tool` | `position margin --symbol X --isolated` |
| `set_risk_limit_tool` | `position risk-limit --symbol X --id 3` |

### P2: Health & Diagnostics

| Tool Function | CLI Needed |
|--------------|------------|
| `exchange_health_check_tool` | `health check --json` |
| `get_rate_limit_status_tool` | `health rate-limit --json` |
| `get_websocket_status_tool` | `health ws --json` |
| `test_connection_tool` | `health connection --json` |

---

## Concurrent Session Architecture

### 3-Database Model (Zero Conflicts)

```
Terminal 1: LIVE play   → market_data_live.duckdb      → api.bybit.com
Terminal 2: DEMO play   → market_data_demo.duckdb      → api-demo.bybit.com
Terminal 3: BACKTEST    → market_data_backtest.duckdb   → no exchange (simulated)
```

All three run simultaneously with **zero resource conflicts**:
- Different DuckDB files (no lock contention)
- Different API endpoints (no rate-limit collision)
- Different WebSocket streams (no subscription overlap)
- Different EngineManager instances (per-process singletons)

### Instance Limits

| Mode | Max | Scope | Enforced By |
|------|-----|-------|-------------|
| Live | 1 total | Global safety | EngineManager |
| Demo | 1 per symbol | Per-symbol | EngineManager |
| Backtest | Unlimited (read-only) | N/A | Bypasses EngineManager |

### Cross-Process Coordination

File-based IPC in `~/.trade/instances/`:
- Instance JSON files track running plays (PID, mode, symbol, started_at)
- `.pause` files control pause/resume (checked every candle)
- Stale PID cleanup on `list_all()`

---

## Tool Layer: Programmatic API (Alternative to CLI)

An agent can **skip the CLI entirely** and call tool functions directly:

```python
from src.tools.order_tools import market_buy_tool
from src.tools.position_tools import list_open_positions_tool
from src.tools.market_data_tools import get_price_tool

price = get_price_tool(symbol="BTCUSDT")
result = market_buy_tool(symbol="BTCUSDT", usd_amount=500, trading_env="demo")
positions = list_open_positions_tool(trading_env="demo")
```

### ToolRegistry (Dynamic Discovery)

```python
from src.tools.tool_registry import ToolRegistry
registry = ToolRegistry()
registry.list_tools()                          # All 110+ tool names
registry.get_tool_info("market_buy")           # JSON schema + params
registry.execute("market_buy", symbol="BTCUSDT", usd_amount=100)
```

### Return Envelope (Consistent)

```python
@dataclass
class ToolResult:
    success: bool
    message: str = ""
    symbol: str | None = None
    data: dict[str, Any] | None = None
    error: str | None = None
    source: str | None = None  # "websocket" or "rest_api"
```

### Key Patterns

- **`trading_env` parameter**: Validates caller intent (demo/live). Mismatches fail immediately.
- **Lazy singleton**: `_get_exchange_manager()` creates connection on first use. No "connect" step.
- **WS vs REST fallback**: Tools try WebSocket first, fall back to REST. WS not required.
- **Error isolation**: All tools catch exceptions → `ToolResult(success=False, error=...)`.

---

## Exchange Connection Lifecycle

### Subcommands Auto-Connect (No Menu Needed)

```
Agent calls:  python trade_cli.py account balance --json
  ↓
handle_account_balance(args)
  ↓
get_account_balance_tool()
  ↓
_get_exchange_manager()      ← LAZY INIT: Creates on first use
  ↓                            Loads .env credentials
  ↓                            Creates BybitClient (REST)
  ↓                            Validates mode consistency
exchange.get_balance()       ← Single REST call
  ↓
ToolResult → JSON → stdout   ← Connection NOT persisted
```

### Credentials (.env)

```
BYBIT_DEMO_API_KEY=...
BYBIT_DEMO_API_SECRET=...
BYBIT_LIVE_API_KEY=...
BYBIT_LIVE_API_SECRET=...
TRADING_MODE=paper|real
BYBIT_USE_DEMO=true|false
```

Mode validation is strict — `TRADING_MODE=paper` + `BYBIT_USE_DEMO=true` (OK).
Mismatches throw `ValueError` at startup.

---

## Implementation Plan: Full CLI Autonomy

### Phase 1: Order Subcommand Group (~4-6 hours)

New `order` subcommand group with:
```bash
order buy   --symbol X --amount 100 --type market|limit|stop|stop-limit [--price P] [--trigger T] [--tp TP] [--sl SL] [--tif GTC] [--reduce-only] --json
order sell  --symbol X --amount 100 --type market|limit|stop|stop-limit [--price P] [--trigger T] [--tp TP] [--sl SL] --json
order list  [--symbol X] [--filter Order|StopOrder] --json
order amend --symbol X --order-id ID [--qty Q] [--price P] [--tp TP] [--sl SL] --json
order cancel --symbol X --order-id ID --json
order cancel-all [--symbol X] --json
order leverage --symbol X --leverage N --json
```

Routes to existing tools: `market_buy_tool`, `limit_sell_tool`, `stop_market_buy_tool`, etc.

**GATE**: Place and cancel a limit order via CLI flags only.

### Phase 2: Data Subcommand Group (~3-4 hours)

New `data` subcommand group with:
```bash
data sync    --symbols X,Y --period 30d [--start D --end D] [--heal] --json
data info    --json
data symbols --json
data status  --symbol X --json
data query   --symbol X --tf 1m [--period 7d | --start D --end D] [--limit 100] --json
data heal    --symbol X --json
data vacuum  --json
data delete  --symbol X --confirm --json
```

Routes to existing tools: `sync_symbols_tool`, `get_database_stats_tool`, `heal_data_tool`, etc.

**GATE**: Sync 7 days of BTCUSDT 1m data via CLI flags only.

### Phase 3: Market & Account Extensions (~3-4 hours)

New `market` subcommand group:
```bash
market price      --symbol X --json
market ohlcv      --symbol X --tf 15m [--limit 100] --json
market funding    --symbol X --json
market oi         --symbol X --json
market orderbook  --symbol X [--depth 25] --json
market instruments [--symbol X] --json
```

Extend `account` subcommand group:
```bash
account history      [--days 7 | --start D --end D] [--symbol X] --json
account pnl          [--days 7 | --start D --end D] [--symbol X] --json
account transactions [--days 7 | --start D --end D] --json
account collateral   [--currency USDT] --json
```

**GATE**: Query BTCUSDT price + 7-day PnL via CLI flags only.

### Phase 4: Position Config & Health (~3-4 hours)

Extend `position` subcommand group:
```bash
position set-tp       --symbol X --price P --json
position set-sl       --symbol X --price P --json
position set-tpsl     --symbol X [--tp P] [--sl P] --json
position trailing     --symbol X --distance D [--active-price P] --json
position partial-close --symbol X --percent N [--price P] --json
position margin       --symbol X --mode cross|isolated --json
```

New `health` subcommand group:
```bash
health check       --json
health connection   --json
health rate-limit   --json
health ws           --json
```

**GATE**: Set TP/SL on demo position via CLI flags only.

---

## Agent Workflow Patterns

### Safe Autonomous Workflow

```bash
# 1. Verify environment
python trade_cli.py account balance --json

# 2. Check data coverage
python trade_cli.py backtest preflight --play X --json

# 3. Run backtest
python trade_cli.py backtest run --play X --synthetic --json

# 4. Start demo play (background)
python trade_cli.py play run --play X --mode demo &

# 5. Monitor (polling loop)
while true; do
  python trade_cli.py play status --json
  python trade_cli.py position list --json
  sleep 30
done

# 6. Stop
python trade_cli.py play stop --play X --close-positions
```

### What Agents Should NEVER Do

```bash
python trade_cli.py                    # Hangs forever (interactive menu)
python trade_cli.py play watch         # Blocks forever (Rich dashboard)
python trade_cli.py play logs -f       # Blocks forever (tail follow)
python trade_cli.py play run --mode live  # Missing --confirm
```

---

## Key Insights

1. **The tool layer IS the API.** CLI is just argparse → tool call → `_json_result()`. An agent can import `src.tools.*` directly.
2. **ToolRegistry enables dynamic agent discovery** — list tools, inspect schemas, execute at runtime.
3. **3-database model eliminates concurrency issues** — backtest/demo/live truly cannot interfere.
4. **No "connect" step needed** — subcommands lazy-init ExchangeManager from `.env` credentials.
5. **All 18 gaps are pure wiring** — tool functions exist with correct signatures. The work is argparse definitions.
