# Unified Trade Structure & Sub-Account Review

> **Date**: 2026-02-24
> **Scope**: Full architectural evaluation of the unified engine, account model, and sub-account strategy for live multi-play trading.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current Architecture Overview](#2-current-architecture-overview)
3. [The Unified Engine (What We Have)](#3-the-unified-engine-what-we-have)
4. [Current Account Model (Single Account)](#4-current-account-model-single-account)
5. [Bybit Sub-Account Capabilities](#5-bybit-sub-account-capabilities)
6. [Gap Analysis: Current vs Multi-Account](#6-gap-analysis-current-vs-multi-account)
7. [Proposed Sub-Account Architecture](#7-proposed-sub-account-architecture)
8. [Implementation Roadmap](#8-implementation-roadmap)
9. [Risk Analysis](#9-risk-analysis)
10. [Recommendations](#10-recommendations)

---

## 1. Executive Summary

The TRADE system has a **strong unified engine** (`PlayEngine`) that runs identical signal logic across backtest, demo, and live modes. The adapter pattern (DataProvider + ExchangeAdapter) cleanly separates concerns. However, the **account model is single-tenant** — one Bybit account per process, hardcoded to `accountType="UNIFIED"`, with no sub-account routing.

**Key findings:**

| Dimension | Current State | Target State |
|-----------|--------------|--------------|
| Engine architecture | Unified (excellent) | No change needed |
| Account model | Single account per process | Sub-account per play |
| Concurrent live plays | Max 1 live instance | Multiple (1 per sub-account) |
| Capital isolation | None (shared wallet) | Full (per sub-account wallet) |
| Risk isolation | Per-play config only | Per-account + per-play |
| Bybit API coverage | UTA basics only | Full sub-account lifecycle |

**Verdict**: The engine is production-ready. The bottleneck is the account layer — it needs sub-account awareness to safely run multiple live plays concurrently.

---

## 2. Current Architecture Overview

### 2.1 Four-Layer Stack

```
┌───────────────────────────────────────────────────────────────┐
│  CLI / Runners                                                │
│  BacktestRunner (sync loop) │ LiveRunner (async WebSocket)    │
├───────────────────────────────────────────────────────────────┤
│  PlayEngine (Unified Core)                                    │
│  process_bar() → Signal │ execute_signal() → OrderResult      │
│  Identical logic across ALL modes                             │
├────────────────┬──────────────────┬───────────────────────────┤
│  DataProvider  │  ExchangeAdapter │  StateStore               │
│  (candles,     │  (orders,        │  (crash recovery,         │
│   indicators,  │   positions,     │   state persistence)      │
│   structures)  │   balance)       │                           │
├────────────────┴──────────────────┴───────────────────────────┤
│  Infrastructure                                               │
│  DuckDB │ WebSocket │ Bybit REST API │ File System            │
└───────────────────────────────────────────────────────────────┘
```

### 2.2 Mode Adapter Matrix

| Component | Backtest | Demo | Live | Shadow |
|-----------|----------|------|------|--------|
| DataProvider | BacktestDP (array O(1)) | LiveDP (WebSocket) | LiveDP (WebSocket) | LiveDP (WebSocket) |
| Exchange | SimulatedExchange | LiveExchange (demo API) | LiveExchange (live API) | ShadowExchange (no-op) |
| StateStore | InMemory | FileStateStore | FileStateStore | InMemory |
| Database | market_data_backtest.duckdb | market_data_demo.duckdb | market_data_live.duckdb | market_data_live.duckdb |
| Fill Source | Next 1m bar open + slippage | Bybit demo exchange | Bybit live exchange | None (log only) |

### 2.3 Instance Limits (EngineManager)

```
Hard limits enforced via advisory file lock:
├── Max 1 live instance (safety)
├── Max 1 demo per symbol (prevents duplicate signals)
└── Max 1 backtest at a time (DuckDB sequential access)
```

These limits exist because the system assumes a **single shared account**. With sub-accounts, these constraints could be relaxed.

---

## 3. The Unified Engine (What We Have)

### 3.1 Strengths

**Signal parity across modes**: The PlayEngine runs the exact same `process_bar()` logic whether backtesting on historical data or trading live. Mode differences are entirely in the adapters. This is the project's strongest architectural decision — it means backtest results are directly comparable to live behavior.

**Deterministic hashing**: Every component in the pipeline produces reproducible hashes (`play_hash`, `input_hash`, `trades_hash`, `equity_hash`, `run_hash`). This enables artifact comparison, regression detection, and audit trails.

**Multi-timeframe support**: The 3-feed system (`low_tf`, `med_tf`, `high_tf`) with an `exec` pointer allows strategies to consume data at multiple granularities without complexity leaking into signal logic. Forward-fill indexing handles slower timeframes cleanly.

**Incremental computation**: All 44 indicators use O(1) incremental updates. Structures (swing, trend, zone, fibonacci, market_structure, rolling_window, derived_zone) also update incrementally. This makes the engine fast enough for real-time 1m bar processing.

**Safety architecture**: Fail-closed design throughout — WebSocket health gates, position sync gates, daily loss tracking, max drawdown enforcement, panic state with DCP (Disconnect Cancel All).

### 3.2 Engine Configuration Flow

```
Play YAML
  └─► Play.from_dict()
        └─► PlayEngineFactory.create(play, mode)
              ├─► DataProvider (mode-specific)
              ├─► ExchangeAdapter (mode-specific)
              ├─► StateStore (mode-specific)
              ├─► SizingModel (unified)
              ├─► TFIndexManager (unified)
              └─► PlayEngine(config, adapters...)
                    └─► Runner.run() / Runner.start()
```

### 3.3 What Doesn't Need to Change

The PlayEngine, signal evaluation, indicator computation, structure detection, sizing model, and state persistence are **all mode-agnostic and account-agnostic**. They don't know or care which Bybit account they're connected to. This is excellent — it means sub-account support is purely an infrastructure change at the adapter and manager layers.

---

## 4. Current Account Model (Single Account)

### 4.1 How It Works Today

```
Process startup
  └─► Config loads credentials from environment:
        BYBIT_DEMO_API_KEY / BYBIT_DEMO_API_SECRET
        BYBIT_LIVE_API_KEY / BYBIT_LIVE_API_SECRET
  └─► ExchangeManager singleton created (thread-safe)
        └─► BybitClient initialized with ONE credential set
  └─► All operations (balance, positions, orders) go through
        this single client, targeting accountType="UNIFIED"
```

### 4.2 Account Data Models

**AccountMetrics** (account-level):
```python
@dataclass
class AccountMetrics:
    account_type: str = "UNIFIED"        # Always hardcoded
    account_im_rate: float               # Initial Margin Ratio
    account_mm_rate: float               # Maintenance Margin Ratio
    total_equity: float
    total_wallet_balance: float
    total_margin_balance: float
    total_available_balance: float
    total_perp_upl: float               # Unrealized P&L
    total_initial_margin: float
    total_maintenance_margin: float
```

**Key limitation**: There's no `account_id` or `sub_account_uid` field anywhere in these models. The system fundamentally assumes "there is one account."

### 4.3 Play-Level Account Config

Each play embeds its own financial parameters:

```yaml
account:
  starting_equity_usdt: 10000.0     # Used in backtest; overridden by real balance in live
  max_leverage: 3.0
  max_drawdown_pct: 20.0
  margin_mode: "isolated_usdt"
  fee_model: { taker_bps: 5.5, maker_bps: 2.0 }
  slippage_bps: 2.0
  min_trade_notional_usdt: 10.0
```

In **backtest mode**, `starting_equity_usdt` determines the initial capital. In **live mode**, the real exchange balance replaces it. But there's no way to say "use sub-account X's balance."

### 4.4 What's Missing

| Feature | Status | Impact |
|---------|--------|--------|
| Sub-account selection per play | Not implemented | Can't isolate capital per strategy |
| Sub-account credential routing | Not implemented | Single API key for everything |
| Per-account balance tracking | Not implemented | All plays see same wallet |
| Cross-account transfer tools | Not implemented | Manual fund management only |
| Account-aware instance limits | Not implemented | Limit is global, not per-account |
| Portfolio-level risk aggregation | Not implemented | No cross-play risk view |

---

## 5. Bybit Sub-Account Capabilities

### 5.1 Master → Sub Architecture

Bybit supports a hierarchical account model:

```
Master Account (uid: 1234567)
├── API Key (master_key): Full permissions
├── Wallet: USDT balance, positions, orders
│
├── Sub-Account A (uid: 2345678)
│   ├── API Key (sub_key_a): Scoped permissions
│   └── Wallet: Independent USDT balance
│
├── Sub-Account B (uid: 3456789)
│   ├── API Key (sub_key_b): Scoped permissions
│   └── Wallet: Independent USDT balance
│
└── Sub-Account C (uid: 4567890)
    ├── API Key (sub_key_c): Scoped permissions
    └── Wallet: Independent USDT balance
```

**Key properties:**
- Each sub-account has its own **independent wallet, positions, and orders**
- Sub-accounts are **automatically UTA** (Unified Trading Account)
- The master account can **transfer funds** to/from any sub-account
- Each sub-account gets its own **API keys with scoped permissions**
- Sub-accounts can subscribe to their own **private WebSocket streams**

### 5.2 Available API Operations

**Sub-Account Lifecycle:**
| Operation | Endpoint | Notes |
|-----------|----------|-------|
| Create sub-account | `POST /v5/user/create-sub-member` | Returns uid |
| List sub-accounts | `GET /v5/user/query-sub-members` | Up to 10k |
| Freeze/unfreeze | `POST /v5/user/froze-subuid` | Emergency stop |
| Delete sub-account | `POST /v5/user/rm-subuid` | Requires zero balance |

**API Key Management:**
| Operation | Endpoint | Notes |
|-----------|----------|-------|
| Create sub API key | `POST /v5/user/create-sub-api` | Granular permissions |
| List sub API keys | `GET /v5/user/list-sub-apikeys` | Per sub-account |
| Delete sub API key | `POST /v5/user/delete-sub-api-key` | Revoke access |

**Fund Transfers:**
| Operation | Endpoint | Notes |
|-----------|----------|-------|
| Internal (within UID) | `POST /v5/asset/transfer/inter-transfer` | UNIFIED ↔ CONTRACT |
| Universal (cross UID) | `POST /v5/asset/transfer/universal-transfer` | Master ↔ Sub |
| Query sub balance | `GET /v5/asset/account-coin-balance?memberId=X` | Master key required |

### 5.3 Permission Scoping

Each sub-account API key can be scoped to specific capabilities:

```
ContractTrade: ["Order", "Position"]    # Derivatives trading
Spot: ["SpotTrade"]                      # Spot trading
Wallet: ["AccountTransfer"]              # Internal transfers only
Derivatives: ["DerivativesTrade"]        # Auto-enabled for UTA
```

**Security benefit**: A sub-account key with only `ContractTrade` permissions **cannot withdraw funds**. Only the master account can move money between accounts.

### 5.4 WebSocket Independence

Each sub-account's API key can independently:
- Subscribe to private streams (orders, positions, executions, wallet)
- Subscribe to public streams (candles, orderbook, trades)
- Maintain separate heartbeat/health tracking

This means each play's LiveRunner can have its own WebSocket connection scoped to its sub-account.

---

## 6. Gap Analysis: Current vs Multi-Account

### 6.1 What Works As-Is

| Component | Multi-Account Ready? | Notes |
|-----------|---------------------|-------|
| PlayEngine | Yes | Account-agnostic, pure signal logic |
| Signal Evaluator | Yes | No account dependency |
| Indicators (44) | Yes | Pure math, no account state |
| Structures (7) | Yes | Pure market analysis |
| SizingModel | Yes | Takes equity as input parameter |
| BacktestRunner | Yes | Already isolated per play |
| BacktestExchange | Yes | Simulated, fully isolated |
| StateStore (File) | Yes | Already namespaced by instance_id |
| DuckDB data layer | Yes | Market data is account-independent |
| Play DSL | Yes | Already self-contained per play |
| Hashing pipeline | Yes | Deterministic, no account dependency |

### 6.2 What Needs Changes

| Component | Change Required | Difficulty |
|-----------|----------------|------------|
| **BybitConfig** | Add per-sub-account credential sets | Low |
| **ExchangeManager** | Remove singleton; create per-account instances | Medium |
| **LiveExchange adapter** | Accept account credentials at construction | Low |
| **LiveDataProvider** | Accept account-scoped WebSocket | Low |
| **RealtimeBootstrap** | Remove global singleton; per-account instances | Medium |
| **RealtimeState** | Remove global singleton; per-account instances | Medium |
| **EngineManager** | Account-aware instance limits | Medium |
| **Play YAML schema** | Add optional `account_id` / `sub_account` field | Low |
| **LiveRunner** | Wire per-account exchange + data provider | Low |
| **PlayEngineFactory** | Route credentials based on play's account config | Medium |
| **Account tools** | Add sub-account management tools | Medium |
| **CLI subcommands** | Add account management commands | Low |
| **Risk aggregation** | New: portfolio-level risk view across accounts | High |

### 6.3 Singleton Problem

The biggest architectural obstacle is the **singleton pattern** used by three critical components:

```python
# Current: Global singletons — one per process
ExchangeManager._instance       # ONE exchange connection
RealtimeBootstrap._instance     # ONE WebSocket manager
RealtimeState._instance         # ONE event cache

# Needed: Per-account instances
account_managers: dict[str, ExchangeManager]     # Keyed by sub_uid
account_bootstraps: dict[str, RealtimeBootstrap]  # Keyed by sub_uid
account_states: dict[str, RealtimeState]          # Keyed by sub_uid
```

This is the core refactor — moving from "one of everything" to "one of everything per account."

---

## 7. Proposed Sub-Account Architecture

### 7.1 Target Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Master Orchestrator (new)                                       │
│  ├─ Portfolio Risk View (aggregate across sub-accounts)          │
│  ├─ Fund Transfer Manager (rebalance between sub-accounts)       │
│  └─ Sub-Account Registry (credentials, limits, status)           │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────┐  ┌─────────────────────┐               │
│  │  Play A Instance    │  │  Play B Instance    │  ...          │
│  │  sub_uid: 2345678   │  │  sub_uid: 3456789   │               │
│  │                     │  │                     │               │
│  │  PlayEngine (same)  │  │  PlayEngine (same)  │               │
│  │  LiveDP (scoped WS) │  │  LiveDP (scoped WS) │               │
│  │  LiveExchange (own) │  │  LiveExchange (own) │               │
│  │  FileState (own)    │  │  FileState (own)    │               │
│  │  RiskManager (own)  │  │  RiskManager (own)  │               │
│  └─────────────────────┘  └─────────────────────┘               │
│                                                                  │
│  ┌─────────────────────┐                                        │
│  │  Shared Services    │                                        │
│  │  ├─ DuckDB (market data - account independent)               │
│  │  ├─ Public WebSocket (shared candle streams)                 │
│  │  └─ Indicator Cache (per-symbol, not per-account)            │
│  └─────────────────────┘                                        │
└──────────────────────────────────────────────────────────────────┘
```

### 7.2 Play YAML Extension

```yaml
# Current (unchanged for backtest):
account:
  starting_equity_usdt: 10000.0
  max_leverage: 3.0
  # ... same as today

# New for live/demo — optional sub-account binding:
live_account:
  sub_account: "strategy_momentum"      # Human-readable name
  # OR
  sub_uid: "2345678"                    # Direct Bybit sub-UID
  #
  # Credentials resolved from:
  #   1. Environment: BYBIT_SUB_{NAME}_API_KEY
  #   2. Config file: config/accounts.yml
  #   3. Secrets manager (future)
```

### 7.3 Account Registry (New File: `config/accounts.yml`)

```yaml
# Account registry — maps human names to Bybit sub-accounts
# API keys stored in environment variables (never in YAML)
accounts:
  momentum:
    sub_uid: "2345678"
    description: "Momentum strategies (EMA cross, RSI divergence)"
    max_capital_usdt: 5000.0           # Capital allocation limit
    env_key_prefix: "BYBIT_SUB_MOMENTUM"  # → BYBIT_SUB_MOMENTUM_API_KEY
    allowed_symbols: ["BTCUSDT", "ETHUSDT"]

  mean_reversion:
    sub_uid: "3456789"
    description: "Mean reversion strategies (BBands, RSI extremes)"
    max_capital_usdt: 3000.0
    env_key_prefix: "BYBIT_SUB_MR"
    allowed_symbols: ["BTCUSDT", "SOLUSDT"]

  experimental:
    sub_uid: "4567890"
    description: "Testing and experimental strategies"
    max_capital_usdt: 1000.0
    env_key_prefix: "BYBIT_SUB_EXP"
    allowed_symbols: ["*"]             # Any symbol
```

### 7.4 Instance Limit Changes

```
Current limits (global):
  Max 1 live instance (total)
  Max 1 demo per symbol (total)

Proposed limits (per sub-account):
  Max 1 live instance per sub-account per symbol
  Max 1 demo instance per sub-account per symbol
  Max N live instances total (configurable, default 5)
  Max 1 live instance per symbol across ALL sub-accounts
    (prevents two plays fighting over the same market)
```

The last rule is critical — even with account isolation, two plays on the same symbol can produce conflicting signals that destabilize each other's positions.

### 7.5 Shared vs Isolated Components

| Component | Shared or Isolated | Reason |
|-----------|-------------------|--------|
| Public WebSocket (candles) | **Shared** | Market data is account-independent; saves connections |
| Private WebSocket (orders, wallet) | **Isolated** per account | Each sub-account has its own state |
| DuckDB (market data) | **Shared** | Historical candles are the same for everyone |
| Indicator cache | **Shared** per symbol+tf | Same indicators regardless of account |
| ExchangeManager | **Isolated** per account | Different credentials, balances, positions |
| RiskManager | **Isolated** per account | Different equity, different limits |
| PositionManager | **Isolated** per account | Each account has its own positions |
| StateStore | **Isolated** per instance | Already namespaced by instance_id |
| PanicState | **Isolated** per account | Panic in one account shouldn't halt others |

### 7.6 Fund Management Flow

```
Master Account (holds reserve capital)
        │
        ├── Transfer 5000 USDT ──► Sub: momentum
        ├── Transfer 3000 USDT ──► Sub: mean_reversion
        └── Transfer 1000 USDT ──► Sub: experimental

Rebalancing (manual or scheduled):
  1. Master queries all sub-account balances
  2. Compares to target allocations in accounts.yml
  3. Executes universal transfers to rebalance
  4. Logs all transfers for audit trail
```

---

## 8. Implementation Roadmap

### Phase 1: Foundation (Account Registry + Credential Routing)

**Goal**: Multiple credential sets, no singleton assumption.

```
- [ ] Create config/accounts.yml schema and loader
- [ ] Add AccountRegistry class to src/config/
- [ ] Modify BybitConfig to support per-account credentials
- [ ] Add sub_account field to Play YAML schema (optional)
- [ ] Modify PlayEngineFactory to accept account credentials
- [ ] GATE: Existing tests pass (no behavioral change for single-account)
```

### Phase 2: Singleton Removal (Per-Account Instances)

**Goal**: Each play gets its own exchange connection.

```
- [ ] Refactor ExchangeManager: remove singleton, accept credentials at init
- [ ] Refactor RealtimeBootstrap: split public (shared) vs private (per-account)
- [ ] Refactor RealtimeState: per-account private state, shared public state
- [ ] Modify LiveExchange adapter: accept ExchangeManager instance (not singleton)
- [ ] Modify LiveDataProvider: accept RealtimeBootstrap instance
- [ ] Modify LiveRunner: wire per-account dependencies
- [ ] GATE: Single-account demo mode still works
```

### Phase 3: Instance Management (Multi-Play Live)

**Goal**: Run multiple live plays safely.

```
- [ ] Update EngineManager instance limits (per-account + per-symbol)
- [ ] Add cross-account symbol conflict detection
- [ ] Per-account PanicState (isolated emergency stops)
- [ ] Per-account DailyLossTracker
- [ ] Per-account FileStateStore namespacing
- [ ] GATE: Two demo plays run concurrently on different sub-accounts
```

### Phase 4: Sub-Account Tools + CLI

**Goal**: Full lifecycle management from CLI.

```
- [ ] Add sub-account management tools (create, list, freeze, delete)
- [ ] Add fund transfer tools (universal transfer, balance query)
- [ ] Add CLI subcommands: account create/list/freeze/transfer/balance
- [ ] Portfolio risk view (aggregate across all sub-accounts)
- [ ] GATE: Can create sub-account, fund it, run a play, and view results
```

### Phase 5: Production Hardening

**Goal**: Safe for real money multi-play trading.

```
- [ ] Pre-live validation gate includes sub-account verification
- [ ] Sub-account health monitoring (balance, margin, connection status)
- [ ] Automated rebalancing (optional, with manual approval)
- [ ] Cross-account risk aggregation (total exposure across all plays)
- [ ] Emergency: master-level panic (freeze all sub-accounts)
- [ ] GATE: validate pre-live passes for multi-account setup
```

---

## 9. Risk Analysis

### 9.1 Risks of Multi-Account Trading

| Risk | Severity | Mitigation |
|------|----------|------------|
| Two plays on same symbol, same direction | Medium | Per-symbol-across-accounts limit |
| Two plays on same symbol, opposing directions | High | Block: net exposure becomes unpredictable |
| Sub-account runs out of margin mid-trade | Medium | Pre-trade balance check + margin buffer |
| Master account drained by transfers | High | Reserve minimum in master; transfer limits |
| API key compromise on one sub-account | Low | Scoped permissions (no withdrawal) |
| WebSocket disconnect on one account | Low | Per-account reconnect; doesn't affect others |
| Panic in one account cascades | Medium | Isolated PanicState per account |
| Correlated losses across all accounts | High | Portfolio-level drawdown circuit breaker |
| DuckDB lock during multi-play data access | Medium | Market data is read-only in live; shared safely |

### 9.2 Risks of NOT Using Sub-Accounts

| Risk | Severity | Notes |
|------|----------|-------|
| Single point of failure | High | One bug → all capital at risk |
| No capital isolation | High | Losing play consumes winning play's margin |
| Position confusion | High | Two plays on same symbol share one position |
| Cannot A/B test strategies live | Medium | Must run sequentially, not concurrently |
| Liquidation cascade | Critical | One play's liquidation affects entire account |

---

## 10. Recommendations

### 10.1 Short Term (Use Now)

**Run one play at a time in live mode.** The current architecture is solid for single-play live trading. The unified engine, safety guards, and state persistence are production-quality. Don't rush multi-account support if you're running a single strategy.

### 10.2 Medium Term (Next Major Feature)

**Implement Phase 1 and Phase 2 of the roadmap.** The singleton removal is the hardest part — once ExchangeManager, RealtimeBootstrap, and RealtimeState are per-instance, everything else follows naturally. The Play YAML extension is backward-compatible (omit `live_account` and it works exactly as today).

### 10.3 Long Term (Portfolio Management)

**Phase 4-5 enable true portfolio management.** This is where the sub-account model pays off:
- Each strategy runs with its own capital allocation
- Risk is isolated per strategy
- Master account retains control over fund distribution
- Portfolio-level risk aggregation provides a holistic view
- Emergency freeze on any sub-account doesn't affect others

### 10.4 What NOT to Do

- **Don't run multiple plays on the same Bybit account concurrently** — position conflicts are inevitable.
- **Don't create one sub-account per trade** — sub-accounts are for strategy isolation, not trade isolation.
- **Don't store API keys in accounts.yml** — always use environment variables.
- **Don't remove the single-account path** — keep it as the default for simplicity. Sub-accounts are an opt-in feature.
- **Don't share private WebSocket connections across accounts** — each account needs its own authenticated stream.

---

## Appendix A: File Inventory (Current Account-Related Code)

| File | Lines | Purpose |
|------|-------|---------|
| `src/config/config.py` | ~200 | BybitConfig with 4 credential sets |
| `src/exchanges/bybit_client.py` | ~300 | REST client wrapper |
| `src/exchanges/bybit_account.py` | ~400 | Account operations (balance, UTA) |
| `src/core/exchange_manager.py` | ~350 | Singleton exchange manager |
| `src/core/risk_manager.py` | ~300 | Position sizing, leverage checks |
| `src/core/safety.py` | ~250 | PanicState, DailyLossTracker |
| `src/data/realtime_bootstrap.py` | ~400 | WebSocket singleton |
| `src/data/realtime_state.py` | ~300 | Event cache singleton |
| `src/engine/manager.py` | ~1070 | Instance limits (global) |
| `src/engine/adapters/live.py` | ~2100 | LiveDP + LiveExchange |
| `src/engine/factory.py` | ~438 | Engine creation |
| `src/tools/account_tools.py` | ~500 | 14 account tools |
| `config/defaults.yml` | 104 | System defaults |

**Total account-adjacent code**: ~6,700 lines across 13 files.

## Appendix B: Bybit Sub-Account API Coverage (pybit SDK)

| Feature | pybit Method | Integrated? |
|---------|-------------|-------------|
| Create sub-account | `create_sub_uid()` | No |
| List sub-accounts | `get_sub_uid_list()` | No |
| Create sub API key | `create_sub_api_key()` | No |
| List sub API keys | `get_all_sub_api_keys()` | No |
| Freeze sub-account | `freeze_sub_uid()` | No |
| Delete sub-account | `delete_sub_uid()` | No |
| Query sub balance | `get_coins_balance(memberId=X)` | No |
| Universal transfer | `create_universal_transfer()` | No |
| Transfer records | `get_universal_transfer_records()` | No |
| Internal transfer | `create_internal_transfer()` | Partial (no sub-account routing) |

**0/10 sub-account operations currently integrated.**

## Appendix C: Comparison Matrix

| Feature | Current TRADE | Sub-Account TRADE | Other Bots (typical) |
|---------|--------------|-------------------|---------------------|
| Engine parity (backtest=live) | Yes | Yes | Rare |
| Capital isolation per strategy | No | Yes (per sub-account) | Sometimes (virtual) |
| True exchange-level isolation | No | Yes (separate wallets) | No (usually virtual) |
| Concurrent live strategies | No (max 1) | Yes (1 per sub-account) | Yes (shared account) |
| Independent risk management | Partial (per-play config) | Full (per-account) | Partial |
| Fund rebalancing | N/A | API-driven | Manual |
| Emergency per-strategy freeze | No (global panic) | Yes (freeze sub-account) | Rare |
| Deterministic backtesting | Yes (hash-traced) | Yes (unchanged) | Rare |
| Multi-timeframe support | Yes (3-feed) | Yes (unchanged) | Sometimes |
| Portfolio risk aggregation | No | Planned (Phase 5) | Rare |
