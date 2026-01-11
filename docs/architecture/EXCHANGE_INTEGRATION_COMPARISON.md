# Exchange Integration Comparison: Bybit vs Hyperliquid

> **Created**: 2026-01-10 | **Status**: Future Reference | **Purpose**: Multi-exchange architecture planning

---

## Executive Summary

This document evaluates adding Hyperliquid as a second exchange to TRADE, which is currently built exclusively for Bybit. The key finding is that the codebase has a **solid foundation** for multi-exchange support, but requires **~5-6 weeks of refactoring** concentrated in the exchange integration layer.

**Key Benefit of Hyperliquid**: Native subaccount model enables running multiple strategies on the same pair simultaneously - something Bybit's 1-position-per-pair limit prevents.

---

## Architecture Fundamentals

| Aspect | Bybit | Hyperliquid |
|--------|-------|-------------|
| **Type** | Centralized Exchange (CEX) | Decentralized On-Chain Order Book |
| **Order Book** | Off-chain (server) | On-chain (HyperBFT L1) |
| **Settlement** | Internal ledger | Blockchain finality |
| **Auth Model** | API Key + Secret | Private Key Signing (EIP-712) |
| **Custody** | Exchange holds funds | Self-custody (wallet) |

---

## API Structure Comparison

| Component | Bybit | Hyperliquid |
|-----------|-------|-------------|
| **REST Base** | `api.bybit.com/v5/*` | `api.hyperliquid.xyz/*` |
| **WebSocket** | `stream.bybit.com` | `wss://api.hyperliquid.xyz/ws` |
| **SDK** | `pybit` (official) | `hyperliquid-python-sdk` |
| **Auth** | HMAC signature | EIP-712 typed data signature |
| **Rate Limits** | 10/sec/symbol orders | 1200 REST/min global |
| **Latency** | ~10-50ms | ~50-200ms REST, 10-100ms WS |

---

## Order Types Supported

| Order Type | Bybit | Hyperliquid |
|------------|-------|-------------|
| Market | Yes | Yes |
| Limit | Yes | Yes |
| Stop Market | Yes | Yes |
| Stop Limit | Yes | Yes |
| Take Profit | Yes | Yes |
| Stop Loss | Yes | Yes |
| Trailing Stop | Yes | **No** |
| Conditional | Yes | Yes (trigger orders) |
| Post-Only (ALO) | Yes | Yes |
| IOC | Yes | Yes |
| GTC | Yes | Yes |
| Reduce Only | Yes | Yes |
| **Batch Orders** | Yes | Yes |

---

## Position & Margin

| Feature | Bybit | Hyperliquid |
|---------|-------|-------------|
| **Margin Modes** | Cross / Isolated | Cross / Isolated |
| **Position Mode** | One-Way / Hedge | One-Way only |
| **Max Leverage** | Up to 100x | Up to 50x (varies) |
| **Positions per Pair** | 1 (or 2 in hedge) | 1 per account |
| **Subaccounts** | Yes (KYC each) | Yes (native, no KYC) |
| **Collateral** | USDT/USDC | USDC only |

---

## API Parameter Differences

| Parameter | Bybit | Hyperliquid |
|-----------|-------|-------------|
| **Side** | `"Buy"` / `"Sell"` | `true` (buy) / `false` (sell) |
| **Symbol** | `"BTCUSDT"` | Asset index (0 = BTC) |
| **Quantity** | `qty` (string) | `sz` (string) |
| **Price** | `price` (string) | `limit_px` (string) |
| **Order Type** | `"Market"`, `"Limit"` | Implicit in order structure |
| **Time in Force** | `timeInForce` | `tif` ("Gtc", "Ioc", "Alo") |
| **TP/SL** | Separate params | `tp_sl` nested object |
| **Reduce Only** | `reduceOnly: true` | `reduce_only: true` |

### Example Order - Bybit

```python
client.create_order(
    symbol="BTCUSDT",
    side="Buy",
    orderType="Market",
    qty="0.01",
    timeInForce="GTC"
)
```

### Example Order - Hyperliquid

```python
client.order(
    coin="BTC",
    is_buy=True,
    sz=0.01,
    limit_px=None,  # Market order
    order_type={"limit": {"tif": "Ioc"}}
)
```

---

## Multi-Strategy Position Model

### The Problem with Bybit

Bybit allows only **1 open position per pair** (or 2 in hedge mode: 1 long + 1 short). Running multiple independent strategies on the same pair requires separate KYC'd accounts.

### Hyperliquid's Solution

```
MASTER WALLET (main funds, never exposed)
└── Authorizes API wallets + subaccounts

    ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
    │ Sub-1  │ │ Sub-2  │ │ Sub-3  │ │ Sub-N  │
    │ BTCUSD │ │ BTCUSD │ │ BTCUSD │ │ BTCUSD │
    │ Trend  │ │ Mean-R │ │ Breakout│ │ Scalp  │
    │ API-1  │ │ API-2  │ │ API-3  │ │ API-N  │
    └────────┘ └────────┘ └────────┘ └────────┘
         │          │          │          │
         └──────────┴──────────┴──────────┘
                        │
              All same pair, different strategies
```

**Key Benefits**:
- 1 master wallet + N subaccounts (no KYC per sub)
- Independent margin per subaccount
- Separate API wallets for blast radius isolation
- Native to protocol (not a workaround)

---

## Current TRADE Codebase Analysis

### Coupling Assessment

| Component | Bybit Coupling | Change Required |
|-----------|----------------|-----------------|
| `BybitClient` | 100% | Create `HyperliquidClient` |
| `ExchangeManager` | Direct instantiation | Factory pattern |
| Order params | `"Buy"/"Sell"` hardcoded | Normalizer layer |
| Instrument info | Bybit field names | Abstract `InstrumentSpec` |
| WebSocket | pybit channels | Channel mapping |
| Config | `BybitConfig` class | Generic `ExchangeConfig` |
| Rate limiter | Bybit buckets | Exchange-configurable |
| **Backtest engine** | **No coupling** | **No changes needed** |

### Existing Abstractions (Strengths)

1. **Normalized Types**: `Position`, `Order`, `OrderResult` are platform-agnostic
2. **Delegation Pattern**: Order logic in separate modules (`exchange_orders_*.py`)
3. **Currency Standard**: Global `size_usdt` eliminates currency confusion
4. **Backend Protocol**: Historical data has `HistoricalBackend` abstraction
5. **Tool Layer**: All operations go through tools, not internal modules

### Tight Coupling (Weaknesses)

1. **Client Instantiation**: Direct `BybitClient()` in ExchangeManager
2. **Order Parameters**: "Buy"/"Sell" hardcoded, not normalized
3. **Instrument Fields**: priceFilter/lotSizeFilter baked into code
4. **WebSocket Integration**: Pybit WebSocket tightly coupled
5. **No Protocol Base**: No ABC for ExchangeClient

---

## Integration Effort Estimate

| Phase | Work | Effort |
|-------|------|--------|
| **1. Abstraction Layer** | `ExchangeClient` protocol, factory | 1 week |
| **2. Bybit Adapter** | Wrap existing code | 3-4 days |
| **3. Hyperliquid Client** | New API wrapper | 1 week |
| **4. Order Normalizer** | Side/type/param mapping | 3-4 days |
| **5. Instrument Provider** | Tick size, lot size abstraction | 2-3 days |
| **6. WebSocket** | Abstract connection + channels | 1 week |
| **7. Config & Rate Limits** | Generic config, exchange limits | 2-3 days |
| **8. Testing** | Validation plays both exchanges | 1 week |
| **Total** | | **5-6 weeks** |

---

## Recommended Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    TRADE Codebase                       │
├─────────────────────────────────────────────────────────┤
│  Tools Layer (unchanged)                                │
│  ↓                                                      │
│  ExchangeManager                                        │
│  ↓                                                      │
│  ExchangeFactory.create("bybit" | "hyperliquid")       │
│  ↓                                                      │
├──────────────────┬──────────────────────────────────────┤
│  BybitAdapter    │  HyperliquidAdapter                  │
│  ↓               │  ↓                                   │
│  BybitClient     │  HyperliquidClient                   │
│  (pybit)         │  (hyperliquid-python-sdk)            │
└──────────────────┴──────────────────────────────────────┘
```

### Key Abstractions Needed

```python
# src/core/exchange_protocol.py (new)
from abc import ABC, abstractmethod

class ExchangeClient(ABC):
    @abstractmethod
    def create_order(self, symbol: str, side: str, qty: float,
                     order_type: str = "Market", **kwargs) -> dict: pass

    @abstractmethod
    def get_positions(self, symbol: str | None = None) -> list[Position]: pass

    @abstractmethod
    def get_balance(self) -> dict: pass

    @abstractmethod
    def cancel_order(self, symbol: str, order_id: str) -> bool: pass


class ExchangeFactory:
    _providers: dict[str, type[ExchangeClient]] = {}

    @classmethod
    def register(cls, name: str, provider: type[ExchangeClient]):
        cls._providers[name] = provider

    @classmethod
    def create(cls, exchange_name: str, **kwargs) -> ExchangeClient:
        return cls._providers[exchange_name](**kwargs)
```

---

## Key Differences That Affect Integration

| Difference | Impact |
|------------|--------|
| **EIP-712 signing** | Need web3/eth signing library |
| **Asset indices** | Symbol mapping layer required |
| **Boolean side** | `true/false` vs `"Buy"/"Sell"` |
| **No trailing stops** | Feature parity check in strategy |
| **USDC only** | Currency handling (vs USDT) |
| **Subaccount model** | Native support = simpler multi-strategy |

---

## What's the Same (Good News)

| Feature | Status |
|---------|--------|
| REST + WebSocket model | Same pattern |
| Order types (core) | Market, limit, stop, TP/SL |
| Margin modes | Cross / Isolated |
| Position queries | Similar structure |
| Batch operations | Both support |
| Historical data | Both provide OHLCV |

---

## Tradeoffs Summary

| Aspect | Bybit | Hyperliquid |
|--------|-------|-------------|
| **Liquidity** | Deep, mature | Growing, less on altcoins |
| **Latency** | Faster (CEX) | Slower (on-chain) |
| **Subaccounts** | KYC per account | Native, no KYC |
| **Trailing Stops** | Yes | No |
| **Max Leverage** | 100x | 50x |
| **Custody** | Exchange | Self-custody |
| **Multi-strategy** | Hard (separate accounts) | Easy (subaccounts) |

---

## Use Case Fit

| Scenario | Recommended |
|----------|-------------|
| Single strategy, max leverage | Bybit |
| Multi-strategy same pair | Hyperliquid |
| Altcoin trading | Bybit |
| Self-custody requirement | Hyperliquid |
| Lowest latency | Bybit |
| Evolutionary learning live validation | Hyperliquid |

---

## Evolutionary Learning Integration Path

```
Phase 1: Backtest 10k strategies locally (current system)
Phase 2: Top 10 winners → 10 Hyperliquid subaccounts
Phase 3: Live parallel validation on same pair
Phase 4: Capital allocation based on live performance
```

Each subaccount runs independently - if one strategy blows up, others unaffected.

---

## Files That Would Need Changes

### Critical (Complete Refactor)

- `src/core/exchange_manager.py` - Factory pattern + generic client
- `src/core/exchange_orders_*.py` (all 4 files) - Normalization layer
- `src/core/exchange_instruments.py` - Abstraction + providers

### High (Moderate Changes)

- `src/config/config.py` - Generic exchange config
- `src/exchanges/bybit_client.py` - Keep as-is, create parallel
- `src/core/exchange_positions.py` - Normalize position queries
- `src/data/historical_sync.py` - Exchange data provider

### Medium (Light Refactoring)

- `src/core/exchange_websocket.py` - WebSocketProvider abstraction
- `src/data/market_data.py` - Use ExchangeClient
- `src/tools/order_tools.py` - Minimal (already uses ExchangeManager)

### None Required

- `src/backtest/*` - Fully decoupled from exchange
- `src/core/risk_manager.py` - Uses normalized types
- `src/core/order_executor.py` - Uses normalized types

---

## References

- [Hyperliquid API Docs](https://hyperliquid.gitbook.io/hyperliquid-docs/)
- [Hyperliquid Order Types](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/order-types)
- [Hyperliquid TP/SL](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/take-profit-and-stop-loss-orders-tp-sl)
- [Hyperliquid API Wallets](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/nonces-and-api-wallets)
- [Hummingbot Hyperliquid Integration](https://hummingbot.org/exchanges/hyperliquid/)
- [Chainstack Hyperliquid Guide](https://docs.chainstack.com/reference/hyperliquid-getting-started)

---

## Bottom Line

| Metric | Value |
|--------|-------|
| **API Similarity** | ~70% compatible |
| **Refactoring Scope** | 20% of live trading code |
| **Backtest Impact** | Zero |
| **Effort** | 5-6 weeks |
| **Recommended Approach** | Factory + Adapter pattern |
