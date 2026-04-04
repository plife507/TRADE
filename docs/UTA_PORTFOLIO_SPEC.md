# UTA Portfolio Management — Full Specification

> Branch: `feature/uta-portfolio-management`
> Status: SPEC COMPLETE, IMPLEMENTATION NOT STARTED
> Date: 2026-04-03

---

## 1. Vision

Full programmatic control of the Bybit Unified Trading Account. One manager, no fallbacks. Proven plays deploy into isolated sub-accounts and run in parallel.

**Pipeline:** Backtest (USDT, proves play) → Shadow (USDT, proves with live data) → Portfolio Deploy (any category, real money in sub-account)

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    PortfolioManager                      │
│              (main account = treasury + monitor)         │
│                                                         │
│  ┌─────────────────┐  ┌────────────────────────────┐   │
│  │InstrumentRegistry│  │    SubAccountManager       │   │
│  │ (shared cache)   │  │ (create/fund/freeze/delete)│   │
│  └────────┬────────┘  └────────────┬───────────────┘   │
│           │                         │                    │
│  ┌────────┴─────────────────────────┴────────────────┐  │
│  │              PlayDeployer                          │  │
│  │  (sub-account → fund → LiveRunner pipeline)       │  │
│  └────────┬──────────┬──────────┬────────────────────┘  │
│           │          │          │                        │
│  ┌────────▼───┐ ┌────▼────┐ ┌──▼──────┐                │
│  │Sub-Acct A  │ │Sub-Acct B│ │Sub-Acct C│  ...          │
│  │BTCUSDT play│ │ETHUSDT  │ │SOLPERP  │                │
│  │Own client  │ │Own client│ │Own client│                │
│  │Own WS      │ │Own WS   │ │Own WS   │                │
│  │Own runner  │ │Own runner│ │Own runner│                │
│  └────────────┘ └─────────┘ └─────────┘                │
└─────────────────────────────────────────────────────────┘
```

### Design Principles

1. **One manager** — `PortfolioManager` is the single source of truth. No "try X, fall back to Y" patterns.
2. **Sub-account isolation** — Each play gets its own sub-account with own API keys, rate limits, and WS connections. A play blowing up can't affect other plays.
3. **Parallel by design** — Each sub-account has independent 10/s rate limits. Queries and execution happen concurrently.
4. **Treasury model** — Main account holds capital. Sub-accounts are funded on demand. Profits can be swept back.
5. **Category-agnostic routing** — `InstrumentRegistry` resolves any symbol to its API routing params. USDT perps, USDC perps, inverse — all routed correctly.
6. **No backward compatibility** — This is a full redesign. Old USDT-only paths are replaced, not wrapped. Dead code is deleted, not commented out. All tools are web-UI-callable via `ToolResult`.

---

## 3. Account Model

### Our Account

| Field | Value |
|-------|-------|
| Account Type | UTA 2.0 Pro (`unifiedMarginStatus=6`) |
| Margin Mode | REGULAR_MARGIN (cross) |
| Main UID | (from API) |
| Sub-accounts | 0 (will be created programmatically) |

### Sub-Account Model

Each sub-account:
- Created via `POST /v5/user/create-sub-member` (memberType=1, always UTA)
- API keys generated via `POST /v5/user/create-sub-api`
- Funded via `POST /v5/asset/transfer/universal-transfer`
- Gets its own `BybitClient` instance
- Operates independently with own rate limits (10/s default per UID)
- Cannot query positions from main — must use sub's own API key

### Rate Limits

| Scope | Futures | Spot |
|-------|---------|------|
| Per sub-account | 10/s | 20/s |
| Institutional cap (all UIDs) | Varies by PRO level | Varies |

---

## 4. Supported Instruments

| Category | API `category` | Settlement | Symbol Pattern | Count | Priority |
|----------|---------------|------------|----------------|-------|----------|
| USDT Linear Perps | `linear` | USDT | `BTCUSDT` | 578 | PRIMARY |
| USDC Linear Perps | `linear` | USDC | `BTCPERP` | 70 | SECONDARY |
| Inverse Perps | `inverse` | Base coin | `BTCUSD` | 27 | DEFERRED |

### USDT vs USDC Linear — Key Differences

| Aspect | USDT | USDC |
|--------|------|------|
| PnL formula | `(mark - entry) * size` | Same |
| Fee settlement | USDT | USDC |
| Typical taker fee | 0.055% | 0.02% |
| Session settlement | None (continuous) | 8-hour sessions |
| Hedge mode | Yes | No (one-way only) |
| Symbol pattern | `{BASE}USDT` | `{BASE}PERP` |

---

## 5. Component Specifications

### 5.1 InstrumentRegistry

**File:** `src/core/instrument_registry.py`
**Purpose:** Resolve any symbol to its API routing metadata.
**Pattern:** Singleton, thread-safe, TTL cache.

```python
@dataclass(frozen=True, slots=True)
class InstrumentSpec:
    symbol: str              # "BTCUSDT", "BTCPERP", "BTCUSD"
    category: str            # "linear", "inverse"
    settle_coin: str         # "USDT", "USDC", "BTC"
    base_coin: str           # "BTC"
    quote_coin: str          # "USDT", "USDC", "USD"
    contract_type: str       # "LinearPerpetual", "InversePerpetual"
    tick_size: float
    qty_step: float
    min_order_qty: float
    max_order_qty: float
    max_mkt_order_qty: float
    min_notional: float
```

**Public API:**

| Method | Returns | Notes |
|--------|---------|-------|
| `resolve(symbol)` | `InstrumentSpec` | Raises `KeyError` if unknown |
| `get_routing(symbol)` | `{"category": str, "settleCoin": str}` | For API call params |
| `refresh(categories)` | `int` (count loaded) | Fetches from Bybit REST |
| `list_symbols(category, settle_coin)` | `list[str]` | Filtered listing |
| `is_loaded()` | `bool` | Whether cache is populated |

**Internals:**
- `_cache: dict[str, InstrumentSpec]` keyed by symbol
- `_lock: threading.RLock` for thread safety
- `_last_refresh: float` (epoch) for TTL
- `_ttl: float = 3600` (1 hour default)
- Loads from `GET /v5/market/instruments-info` for categories `["linear", "inverse"]`
- Pagination via cursor (Bybit returns max 1000 per page)

**Dependencies:** `BybitClient` (any — main account client is fine)

---

### 5.2 SubAccountManager

**File:** `src/core/sub_account_manager.py`
**Purpose:** Full lifecycle management for sub-accounts.
**Pattern:** Stateful, persists to disk.

```python
@dataclass
class SubAccountInfo:
    uid: int
    username: str
    api_key: str
    api_secret: str
    status: str              # "active", "frozen", "deleted"
    play_id: str | None      # Currently deployed play
    created_at: datetime
    funded_coin: str         # "USDT", "USDC"
    funded_amount: float     # Cumulative transferred in
    withdrawn_amount: float  # Cumulative transferred out
```

**Public API:**

| Method | Returns | Notes |
|--------|---------|-------|
| `create(username)` | `SubAccountInfo` | Creates sub + API keys |
| `get_client(uid)` | `BybitClient` | Lazily created, cached |
| `fund(uid, coin, amount)` | `bool` | Main → sub transfer |
| `withdraw(uid, coin, amount)` | `bool` | Sub → main transfer |
| `get_balance(uid, coin)` | `dict` | Via main API key |
| `get_positions(uid)` | `list[PositionData]` | Via sub's own client |
| `freeze(uid)` | `bool` | Freeze sub-account |
| `delete(uid)` | `bool` | Delete (must be empty) |
| `list()` | `list[SubAccountInfo]` | All managed subs |
| `save_state()` | `None` | Persist to disk |
| `load_state()` | `None` | Load from disk |

**State persistence:** `data/runtime/sub_accounts.json`
- Contains UIDs, usernames, API keys, status, play assignments
- File is inside `data/` which is in `.gitignore`
- On startup, `load_state()` reconnects to existing sub-accounts

**Bybit API calls used:**

| Action | Endpoint |
|--------|----------|
| Create sub | `POST /v5/user/create-sub-member` |
| Create API key | `POST /v5/user/create-sub-api` |
| List subs | `GET /v5/user/query-sub-members` |
| Transfer | `POST /v5/asset/transfer/universal-transfer` |
| Query balance | `GET /v5/asset/transfer/query-account-coin-balance` |
| Freeze | `POST /v5/user/freeze-sub-uid` |
| Delete | `POST /v5/user/delete-sub-uid` |
| Delete API key | `POST /v5/user/delete-sub-api` |

**Dependencies:** `BybitClient` (main account, needs SubMemberTransfer + AccountTransfer perms)

---

### 5.3 Exchange Layer Changes

**Goal:** Replace all hardcoded `settleCoin="USDT"` and `category="linear"` in the exchange and core layers. No backward compatibility — old USDT-only paths are deleted.

**Files affected:**

| File | Change |
|------|--------|
| `bybit_trading.py:171,201,247` | Replace `settleCoin="USDT"` with required `settle_coin` param. Callers must provide it. |
| `bybit_account.py:30` | `settle_coin` becomes required (no default). Callers resolve via InstrumentRegistry. |
| `exchange_orders_market.py` | All order functions require `category` from InstrumentRegistry. Delete USDT assumption. |
| `exchange_orders_limit.py` | Same — category required, resolved from registry. |
| `exchange_orders_stop.py` | Same. |
| `exchange_positions.py` | Replace `get_positions()` with `get_all_positions()` that queries all categories. Delete `coin="USDT"` in mode switching — iterate all settle coins. |
| `exchange_manager.py` | Replace `get_balance()` (USDT-only filter at line 265) with UTA-aware version that returns full wallet. Delete old method. |
| `position_manager.py:194,263` | Delete `get_wallet("USDT")` — use `AccountMetrics` only. |
| `live.py:2188,2215` | Delete `get_wallet("USDT")` fallback — `AccountMetrics` is THE source. |

**No backward compatibility.** All callers are updated. If something relied on the USDT-only path, it gets fixed in this phase.

---

### 5.4 PortfolioManager

**File:** `src/core/portfolio_manager.py`
**Purpose:** THE one manager. Aggregates main + all sub-accounts.
**Pattern:** Stateful, owns SubAccountManager and InstrumentRegistry.

```python
@dataclass
class SubAccountSnapshot:
    uid: int
    username: str
    play_id: str | None
    status: str
    equity: float
    available_balance: float
    positions: list[dict]
    open_orders: int
    unrealized_pnl: float

@dataclass
class PortfolioSnapshot:
    timestamp: datetime
    # Main account (treasury)
    main_equity: float
    main_available_balance: float
    main_coins: list[dict]
    # Account-wide metrics
    total_equity: float
    total_margin_balance: float
    total_available_balance: float
    total_initial_margin: float
    total_maintenance_margin: float
    margin_utilization_pct: float
    liquidation_risk_level: str
    # Sub-accounts
    sub_accounts: list[SubAccountSnapshot]
    # Aggregates
    total_deployed_equity: float
    total_undeployed: float
    active_plays: int
    total_positions: int
    total_unrealized_pnl: float
```

**Public API:**

| Method | Returns | Notes |
|--------|---------|-------|
| `get_snapshot()` | `PortfolioSnapshot` | Parallel queries across all subs |
| `deploy_play(play_id, symbol, capital)` | `int` (sub UID) | Full pipeline |
| `stop_play(uid)` | `bool` | Stop runner, close positions |
| `rebalance(uid, new_capital)` | `bool` | Add/remove capital |
| `recall_all()` | `bool` | Emergency stop all |
| `get_margin_headroom()` | `float` | Available for new deploys |

**Parallel execution:** `get_snapshot()` uses `concurrent.futures.ThreadPoolExecutor` to query all sub-account balances and positions concurrently. Each sub has its own BybitClient and rate limits.

**Dependencies:** `BybitClient` (main), `InstrumentRegistry`, `SubAccountManager`

---

### 5.5 PlayDeployer

**File:** `src/core/play_deployer.py`
**Purpose:** Automates: load play → create sub → fund → create engine → start runner.

**Deploy pipeline:**
1. Load and validate Play from YAML
2. Resolve symbol → `(category, settleCoin)` via InstrumentRegistry
3. Create sub-account via SubAccountManager
4. Generate API keys for sub
5. Transfer capital from main → sub
6. Create `BybitClient` for sub
7. Create `PlayEngine` with `LiveExchange` using sub's client
8. Start `LiveRunner` in background asyncio task
9. Register in active runners map

**Stop pipeline:**
1. Stop LiveRunner gracefully
2. Close all positions via sub's client (reduce_only)
3. Wait for settlement
4. Transfer remaining capital sub → main
5. Optionally freeze/delete sub-account

**Engine factory change:** `PlayEngineFactory._create_live()` accepts optional `client: BybitClient`. When provided, `LiveExchange` uses that client instead of the global singleton.

**LiveExchange change:** `get_balance()` and `get_equity()` use `AccountMetrics` only (no `get_wallet("USDT")` fallback). `AccountMetrics.total_available_balance` is already account-wide and works for any sub-account regardless of what coins it holds.

---

### 5.6 Tool Layer (Web UI Ready)

**File:** `src/tools/portfolio_tools.py`
**Pattern:** Every operation is a `def xxx_tool(...) -> ToolResult` function registered in `ToolRegistry`.
**Design:** The tool layer is the ONLY public API surface. CLI commands, AI agents, and the future Node.js web UI all call the same tool functions. Each returns `ToolResult(success, message, data, error, source)`.

**Complete Tool Inventory (24 tools):**

```python
# ── Portfolio State ──────────────────────────────────────
get_portfolio_snapshot_tool() -> ToolResult
    # Full portfolio: main + all subs + aggregates
    # data: PortfolioSnapshot.to_dict()

get_portfolio_wallet_tool() -> ToolResult
    # All wallet coins with balances, collateral, borrows
    # data: {coins: [...], total_equity, total_available}

get_portfolio_risk_tool() -> ToolResult
    # Account-level risk: margin util, liq proximity, ADL ranks
    # data: {margin_utilization_pct, risk_buffer_pct, liquidation_risk_level, ...}

get_portfolio_exposure_tool() -> ToolResult
    # Exposure by category, settle_coin, and direction
    # data: {by_category: {...}, by_settle_coin: {...}, long: ..., short: ..., net: ...}

# ── Instrument Discovery ─────────────────────────────────
resolve_instrument_tool(symbol: str) -> ToolResult
    # Resolve symbol to full spec
    # data: InstrumentSpec.to_dict()

list_instruments_tool(category: str | None, settle_coin: str | None) -> ToolResult
    # List available instruments with filters
    # data: {instruments: [...], count: int}

# ── Sub-Account Management ───────────────────────────────
list_sub_accounts_tool() -> ToolResult
    # All managed sub-accounts
    # data: {sub_accounts: [...], count: int}

create_sub_account_tool(username: str) -> ToolResult
    # Create sub-account + API keys
    # data: {uid, username, status}

fund_sub_account_tool(uid: int, coin: str, amount: float) -> ToolResult
    # Transfer main → sub
    # data: {transfer_id, uid, coin, amount, status}

withdraw_sub_account_tool(uid: int, coin: str, amount: float) -> ToolResult
    # Transfer sub → main
    # data: {transfer_id, uid, coin, amount, status}

get_sub_account_balance_tool(uid: int) -> ToolResult
    # Sub-account wallet balance
    # data: {uid, coins: [...], total_equity}

get_sub_account_positions_tool(uid: int) -> ToolResult
    # Sub-account open positions
    # data: {uid, positions: [...], count: int}

freeze_sub_account_tool(uid: int) -> ToolResult
    # Freeze sub-account (stop trading)
    # data: {uid, status: "frozen"}

delete_sub_account_tool(uid: int) -> ToolResult
    # Delete sub-account (must be empty)
    # data: {uid, status: "deleted"}

# ── Play Deployment ──────────────────────────────────────
deploy_play_tool(play_id: str, symbol: str, capital: float, confirm: bool) -> ToolResult
    # Full pipeline: create sub → fund → start runner
    # data: {uid, play_id, symbol, capital, status: "running"}

stop_play_tool(uid: int, close_positions: bool = True) -> ToolResult
    # Stop runner, optionally close positions
    # data: {uid, play_id, status: "stopped", positions_closed: int}

get_play_status_tool(uid: int) -> ToolResult
    # Status of a deployed play
    # data: {uid, play_id, status, equity, positions, pnl, bars_processed, uptime}

rebalance_play_tool(uid: int, new_capital: float) -> ToolResult
    # Add/remove capital from deployed play
    # data: {uid, old_capital, new_capital, transfer_amount, direction}

list_active_plays_tool() -> ToolResult
    # All running plays
    # data: {plays: [...], count: int, total_deployed: float}

# ── Emergency ────────────────────────────────────────────
recall_all_tool(confirm: bool) -> ToolResult
    # Stop all plays, close all positions, sweep to main
    # data: {plays_stopped: int, positions_closed: int, funds_recalled: float}

# ── Collateral Management ────────────────────────────────
get_collateral_tiers_tool(currency: str | None) -> ToolResult
    # Tiered collateral ratios (public endpoint)
    # data: {tiers: [...]}

toggle_collateral_tool(coin: str, enabled: bool) -> ToolResult
    # Enable/disable coin as collateral
    # data: {coin, collateral_switch, margin_collateral}

# ── DCP Safety ───────────────────────────────────────────
get_dcp_status_tool() -> ToolResult
    # DCP configuration per product
    # data: {products: [{product, status, time_window}]}

set_dcp_tool(product: str, time_window: int) -> ToolResult
    # Configure DCP for a product
    # data: {product, status: "ON", time_window}
```

**Tool Specs:** Each tool has a corresponding spec in `src/tools/specs/portfolio_specs.py` following the existing pattern:
```python
{
    "name": "get_portfolio_snapshot",
    "description": "Get complete UTA portfolio snapshot (main + all sub-accounts)",
    "category": "portfolio.state",
    "parameters": {},
    "required": [],
}
```

**Category taxonomy:**
- `portfolio.state` — snapshot, wallet, risk, exposure
- `portfolio.instruments` — resolve, list
- `portfolio.subs` — create, fund, withdraw, balance, positions, freeze, delete, list
- `portfolio.deploy` — deploy, stop, status, rebalance, list active, recall
- `portfolio.collateral` — tiers, toggle
- `portfolio.safety` — DCP

**CLI mapping:** Every tool maps 1:1 to a CLI subcommand:
```
python3 trade_cli.py portfolio snapshot [--json]
python3 trade_cli.py portfolio wallet [--json]
python3 trade_cli.py portfolio risk [--json]
python3 trade_cli.py portfolio instruments [--category linear] [--settle-coin USDC] [--json]
python3 trade_cli.py portfolio resolve BTCPERP [--json]
python3 trade_cli.py portfolio subs list [--json]
python3 trade_cli.py portfolio subs create --username play_btc_01
python3 trade_cli.py portfolio subs fund --uid 12345 --coin USDT --amount 100
python3 trade_cli.py portfolio subs withdraw --uid 12345 --coin USDT --amount 100
python3 trade_cli.py portfolio subs balance --uid 12345 [--json]
python3 trade_cli.py portfolio subs positions --uid 12345 [--json]
python3 trade_cli.py portfolio subs freeze --uid 12345
python3 trade_cli.py portfolio subs delete --uid 12345
python3 trade_cli.py portfolio deploy --play scalp_1m --symbol BTCUSDT --capital 100 --confirm
python3 trade_cli.py portfolio stop --uid 12345 [--close-positions]
python3 trade_cli.py portfolio status --uid 12345 [--json]
python3 trade_cli.py portfolio plays [--json]
python3 trade_cli.py portfolio recall-all --confirm
python3 trade_cli.py portfolio collateral [--currency BTC] [--json]
python3 trade_cli.py portfolio dcp [--json]
```

---

## 6. Existing Code Reuse

| Existing | Location | Reused For |
|----------|----------|------------|
| `WalletData` | `realtime_models.py:704` | Per-coin wallet state |
| `AccountMetrics` | `realtime_models.py:767` | Account-level equity/margin/risk |
| `PositionData` | `realtime_models.py:447` | Position with `category` field |
| `RealtimeState` | `realtime_state.py` | WS state store (multi-coin ready) |
| `BybitClient` | `bybit_client.py` | One instance per sub-account |
| `PlayEngineFactory` | `engine/factory.py` | Creates engine per sub |
| `LiveRunner` | `engine/runners/live_runner.py` | Runs engine per sub |
| `ToolResult` | `tools/shared.py` | CLI output envelope |
| `get_module_logger` | `utils/logger.py` | Logging |

---

## 7. What Is NOT Changed

| Module | Why |
|--------|-----|
| `src/backtest/sim/` | USDT-only. Proves plays work. |
| `src/backtest/system_config.py` | USDT validation for backtest stays. |
| `src/shadow/` | USDT-only. Simulated trades. |
| `src/engine/adapters/backtest.py` | BacktestExchange stays USDT. |
| Play YAML DSL | No structural changes. Category resolved at deploy time. |
| Sim math (ledger, liquidation, PnL) | Only applies to USDT backtest. |

---

## 8. Security Considerations

- Sub-account API keys stored in `data/runtime/sub_accounts.json` (gitignored)
- Main account API key has SubMemberTransfer + AccountTransfer permissions
- Sub-account API keys have ContractTrade + Wallet (AccountTransfer, SubMemberTransferList) permissions
- DCP should be enabled for all sub-accounts running plays (30s window recommended)
- `recall_all()` is the emergency kill switch — stops all runners, closes positions, sweeps funds

---

## 9. Phase Summary

| Phase | Name | New Files | Modified Files | Risk |
|-------|------|-----------|----------------|------|
| 0 | InstrumentRegistry | 1 | 0 | Zero |
| 1 | SubAccountManager | 1 | 0 | Zero |
| 2 | Exchange Layer | 0 | 6 | Low |
| 3 | PortfolioManager | 1 | 0 | Zero |
| 4 | CLI Tools | 3 | 3 | Zero |
| 5 | PlayDeployer | 1 | 2 | Medium |
| **Total** | | **7 new** | **~11 modified** | |

Phases 0+1 parallel → Phase 2 → Phase 3 → Phases 4+5 parallel.
