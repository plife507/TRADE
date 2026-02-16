# Hyperliquid Compatibility Report

**Date:** 2026-02-13
**Status:** Investigation complete, no code written

## 1. What is Hyperliquid vs Bybit?

| Aspect | Bybit (Current) | Hyperliquid |
|--------|-----------------|-------------|
| **Type** | Centralized Exchange (CEX) | Decentralized Exchange (DEX) on Arbitrum |
| **Auth** | API key + secret | EIP-712 wallet signature (private key) |
| **Settlement** | Off-chain (centralized DB) | On-chain (blockchain) |
| **SDK** | `pybit` (REST + WS) | `hyperliquid-python-sdk` (REST + WS) |
| **Symbol format** | `"BTCUSDT"` | `"BTC"` (just coin name) |
| **Interval format** | `"15"`, `"60"`, `"D"` | `"15m"`, `"1h"`, `"1d"` |
| **Quote currency** | USDT | USD (USDC-backed) |
| **TP/SL** | Native conditional orders attached to entry | Separate trigger orders (manual grouping via `bulk_orders`) |
| **Position mode** | One-way (enforced) | One-way (default) |
| **Margin** | Isolated or Cross | Isolated or Cross |
| **Leverage** | 1-100x | 1-50x |
| **Market orders** | Native `"Market"` type | Aggressive IOC limit with slippage |
| **Order IDs** | Exchange-assigned string | Exchange OID (int) + optional CLOID (128-bit hex) |
| **Fees** | 5.5 bps taker / 2.0 bps maker | Varies by tier (similar range) |
| **WebSocket topics** | `kline.15.BTCUSDT`, `position`, `order` | `{"type":"candle","coin":"ETH","interval":"1m"}` (JSON subscription) |
| **Unique features** | Testnet, demo accounts, DCP | Agent wallets, vaults, sub-accounts, on-chain transfers, validator staking |

## 2. Current Bybit Coupling Map

The codebase has **15+ Bybit-specific touchpoints** across 6 layers:

### Layer 1: Exchange Client (~1900 LOC, 100% Bybit)
- `src/exchanges/bybit_client.py` - HTTP/WS client (pybit wrapper)
- `src/exchanges/bybit_market.py` - `get_klines()`, `get_ticker()`
- `src/exchanges/bybit_trading.py` - `create_order()`, `cancel_order()`
- `src/exchanges/bybit_account.py` - `get_balance()`, `get_positions()`
- `src/exchanges/bybit_websocket.py` - WS connect/subscribe

### Layer 2: Core Exchange Manager (~40% Bybit-coupled)
- `src/core/exchange_manager.py` - Delegates to `BybitClient`
- `src/core/exchange_orders_market.py` - Bybit field names (`avgPrice`, `takeProfit`)
- `src/core/exchange_orders_limit.py` - Bybit TIF values
- `src/core/exchange_orders_stop.py` - Bybit trigger fields
- `src/core/exchange_positions.py` - Bybit position mode, margin mode

### Layer 3: Data Models (~80% Bybit field names)
- `src/data/realtime_models.py` - `KlineData.from_bybit()`, `TickerData.from_bybit()`, `PositionData.from_bybit()`
- Hardcoded interval maps (`"15"` -> `"15m"`)

### Layer 4: Data Pipeline (~30% Bybit)
- `src/data/historical_data_store.py` - Bybit API credential routing
- `src/data/historical_sync.py` - Direct `client.get_klines()` calls
- `src/data/realtime_bootstrap.py` - Bybit WS topic format

### Layer 5: Config (100% Bybit)
- `src/config/config.py` - `BybitConfig` class, API endpoints, credential management
- `config/defaults.yml` - Bybit fee rates, margin rates

### Layer 6: Engine (mostly exchange-agnostic)
- `src/engine/` - PlayEngine, signal evaluation, indicators -- **no exchange coupling**
- `src/backtest/sim/exchange.py` - Hardcoded Bybit margin rates (0.5% MMR)
- `src/engine/adapters/live.py` - Routes through `RealtimeBootstrap` (Bybit WS)

## 3. What's Already Exchange-Agnostic (Good News)

The **core engine is clean**. These need zero changes:

- PlayEngine signal evaluation loop
- All 44 incremental indicators
- All 7 structure types
- DSL parser and condition evaluator
- Play YAML schema (except adding `exchange:` field)
- DuckDB OHLCV schema (timestamp, open, high, low, close, volume, turnover)
- Risk manager logic (daily loss, position caps, drawdown circuit breaker)
- Sizing model (percent equity, risk-based)
- OrderExecutor pipeline (signal -> risk check -> submit)

## 4. What Would Need to Change

### Option A: Full Port (Replace Bybit with Hyperliquid)

| Work Item | Files | Effort |
|-----------|-------|--------|
| Create `src/exchanges/hyperliquid_client.py` | 1 new | Medium |
| Create `src/exchanges/hyperliquid_market.py` | 1 new | Low |
| Create `src/exchanges/hyperliquid_trading.py` | 1 new | Medium |
| Create `src/exchanges/hyperliquid_account.py` | 1 new | Low |
| Create `src/exchanges/hyperliquid_websocket.py` | 1 new | Medium |
| Add `HyperliquidConfig` to config | 1 edit | Low |
| Add `KlineData.from_hyperliquid()` | 1 edit | Low |
| Add `TickerData.from_hyperliquid()` | 1 edit | Low |
| Update `exchange_manager.py` to use HL client | 1 edit | Medium |
| Update `realtime_bootstrap.py` for HL WS topics | 1 edit | Medium |
| Update `historical_sync.py` for HL candle fetch | 1 edit | Low |
| Update `exchange.py` sim for HL margin/fee model | 1 edit | Low |
| **Total** | **~12 files** | **~1-2 weeks** |

### Option B: Multi-Exchange Compatibility (Support Both)

Everything in Option A, plus:

| Work Item | Files | Effort |
|-----------|-------|--------|
| Create `ExchangeClient` ABC interface | 1 new | Medium |
| Create `ExchangeFactory` | 1 new | Low |
| Add `exchange:` field to Play YAML | 1 edit | Low |
| Refactor `exchange_manager.py` to be polymorphic | 1 edit | High |
| Refactor `realtime_bootstrap.py` for multi-exchange | 1 edit | High |
| Update `historical_data_store.py` with exchange column | 1 edit | Medium |
| Update preflight for exchange-aware validation | 1 edit | Low |
| Add `--exchange` CLI flag | 1 edit | Low |
| **Total (on top of Option A)** | **~8 additional files** | **+1 week** |

## 5. Key Friction Points (Hardest Parts)

### 5a. Authentication Model is Fundamentally Different
Bybit: API key + secret (standard HMAC)
Hyperliquid: Ethereum private key + EIP-712 signing (requires `eth_account` library)

This means `BybitConfig` credential management doesn't translate. Need a new `HyperliquidConfig` with wallet private key handling and optional agent key delegation.

### 5b. TP/SL Mechanism Differs
Bybit: Attach `takeProfit`/`stopLoss` fields directly to the entry order
Hyperliquid: Place separate trigger orders, optionally grouped via `bulk_orders(grouping="normalTpsl")`

Our `exchange_orders_market.py` sends TP/SL as entry order fields. For Hyperliquid, we'd need to refactor to a two-step flow: entry order + separate TP/SL trigger orders.

### 5c. Symbol Format Conversion
Bybit: `"BTCUSDT"` / Hyperliquid: `"BTC"`
Every Play YAML uses `symbol: "BTCUSDT"`. Need a conversion layer or accept both formats.

### 5d. Market Order Semantics
Bybit: Native `orderType: "Market"`
Hyperliquid: Aggressive IOC limit order with slippage (`market_open()` helper wraps this)

Our fill tracking assumes REST response has `avgPrice`. Hyperliquid returns `filled.avgPx` in a different response structure.

### 5e. WebSocket Message Format
Bybit: Topic-based (`"kline.15.BTCUSDT"`)
Hyperliquid: JSON subscription objects (`{"type":"candle","coin":"ETH","interval":"1m"}`)

Different callback payload structures. Our `_on_kline_update()` parses Bybit topic strings.

### 5f. Demo/Testnet Model
Bybit: Separate demo API endpoint (`api-demo.bybit.com`)
Hyperliquid: Separate testnet URL (`TESTNET_API_URL` constant) -- similar concept but different URLs

## 6. What Hyperliquid Gives Us That Bybit Doesn't

- **Agent wallets** - Delegated trading keys (create sub-keys for bots without exposing main wallet)
- **Atomic order grouping** - `bulk_orders(grouping="normalTpsl")` for entry + TP/SL in one call
- **On-chain settlement** - Verifiable execution, no counterparty risk
- **CLOID** - Client-assigned 128-bit order IDs for idempotent order management
- **No rate limit anxiety** - DEX infrastructure, less restrictive than CEX API limits
- **Vault/sub-account** - Built-in multi-strategy isolation

## 7. Recommendation

**Option B (multi-exchange compatibility) is the right move**, but do it incrementally:

1. **Phase 1** - Create `ExchangeClient` ABC from current Bybit code (extract interface)
2. **Phase 2** - Implement `HyperliquidClient` against that interface
3. **Phase 3** - Add `exchange:` field to Play YAML + factory routing
4. **Phase 4** - Refactor TP/SL to support both attachment models

The engine, indicators, structures, DSL, and risk management are already exchange-agnostic. The work is concentrated in the **exchange client layer** (~5 files) and the **glue code** (config, bootstrap, data sync, order manager).

Estimated total effort: **2-3 weeks** for full multi-exchange support with both Bybit and Hyperliquid working.

## 8. Hyperliquid SDK Reference

SDK cloned to `reference/hyperliquid-python-sdk/` (gitignored).

Key files:
- `hyperliquid/exchange.py` - Order placement, leverage, transfers
- `hyperliquid/info.py` - Market data, positions, balances, candles
- `hyperliquid/websocket_manager.py` - Real-time streaming
- `hyperliquid/utils/signing.py` - EIP-712 wallet signing
- `hyperliquid/utils/types.py` - TypedDict definitions
- `examples/` - Usage patterns for all features

### Hyperliquid API Quick Reference

| Operation | Method |
|-----------|--------|
| Place limit order | `exchange.order(coin, is_buy, sz, px, {"limit":{"tif":"Gtc"}})` |
| Place market order | `exchange.market_open(coin, is_buy, sz, slippage=0.05)` |
| Place stop loss | `exchange.order(coin, ..., {"trigger":{"triggerPx":px,"isMarket":True,"tpsl":"sl"}}, reduce_only=True)` |
| Place take profit | `exchange.order(coin, ..., {"trigger":{"triggerPx":px,"isMarket":True,"tpsl":"tp"}}, reduce_only=True)` |
| Entry + TP/SL atomic | `exchange.bulk_orders([entry, tp, sl], grouping="normalTpsl")` |
| Cancel order | `exchange.cancel(coin, oid)` |
| Get positions | `info.user_state(address)["assetPositions"]` |
| Get balance | `info.user_state(address)["marginSummary"]["accountValue"]` |
| Get candles | `info.candles_snapshot(coin, interval, startTime, endTime)` |
| Get orderbook | `info.l2_snapshot(coin)` |
| Stream candles | `info.subscribe({"type":"candle","coin":"ETH","interval":"1m"}, callback)` |
| Stream fills | `info.subscribe({"type":"userFills","user":addr}, callback)` |
| Set leverage | `exchange.update_leverage(leverage, coin, is_cross=True)` |
| Close position | `exchange.market_close(coin)` |
