# UTA Portfolio Management — Full Design Reference

> Compiled from Bybit V5 API docs, pybit SDK, and live account investigation.
> Date: 2026-04-03

## 1. Account Structure

### Our Account
- **Type**: UTA 2.0 Pro (`unifiedMarginStatus=6`)
- **Margin Mode**: REGULAR_MARGIN (cross)
- **Spot Hedging**: OFF
- **DCP**: OFF (should enable for live)

### UTA 2.0 Key Properties
- **Single wallet** for ALL asset classes: USDT perps, USDC perps, inverse, spot, options
- **Cross-collateral**: All eligible coins contribute to shared margin pool
- **Inverse contracts**: Fully integrated (unlike UTA 1.0 where they were separate)
- **Margin shared** across all positions in cross/portfolio mode

### Margin Modes Available

| Mode | Margin Scope | Available Balance Formula | Notes |
|------|-------------|--------------------------|-------|
| REGULAR_MARGIN | Account-wide cross | `totalMarginBalance - Haircut - totalInitialMargin` | Current setting |
| ISOLATED_MARGIN | Per-position | Per-position IM/MM | Can isolate risk |
| PORTFOLIO_MARGIN | Account-wide equity | `totalEquity - Haircut - totalInitialMargin` | Requires 1000 USDC min |

---

## 2. Instrument Categories

### Available Markets

| Category | API `category` | Count | Settlement | Symbol Pattern | Our Priority |
|----------|---------------|-------|------------|----------------|-------------|
| USDT Perps | `linear` | 578 | USDT | `BTCUSDT` | **PRIMARY** |
| USDC Perps | `linear` | 70 | USDC | `BTCPERP` | **SECONDARY** |
| Inverse Perps | `inverse` | 27 | Base coin | `BTCUSD` | DEFER |
| Spot | `spot` | 635 | Base/Quote | `BTCUSDT` | DEFER |
| Options | `option` | Many | USDT/USDC | `BTC-26MAR27-78000-P-USDT` | EXCLUDE |

### Linear Perpetuals: USDT vs USDC

| Aspect | USDT Perps | USDC Perps |
|--------|-----------|-----------|
| Symbol | `BTCUSDT` | `BTCPERP` |
| Settle coin | USDT | USDC |
| Qty denomination | Base coin (BTC) | Base coin (BTC) |
| PnL formula | `(mark - entry) * size` | `(mark - entry) * size` |
| PnL currency | USDT | USDC |
| Margin currency | USDT | USDC |
| Fee settlement | USDT | USDC |
| Funding interval | 8h (00:00, 08:00, 16:00 UTC) | 8h (same) |
| Session settlement | None (continuous) | 8-hour session settlement |
| Hedge mode | Yes (USDT only) | No (one-way only) |
| Typical taker fee | 0.055% | 0.02% |
| `minNotionalValue` | Per symbol | Per symbol |

**Key: USDC perps use identical PnL math to USDT perps.** The only differences are settlement coin, fee rates, symbol naming, and 8-hour session settlement.

### Inverse Perpetuals (Deferred)

| Aspect | Inverse |
|--------|---------|
| Symbol | `BTCUSD` |
| Settle coin | Base coin (BTC) |
| PnL formula | `(1/entry - 1/mark) * contracts * multiplier` |
| Margin | In base coin |
| Hedge mode | No (UTA 2.0: one-way only) |

**Fundamentally different math** — deferred to future milestone.

---

## 3. Wallet & Collateral

### Account-Level Fields

| Field | Type | Formula |
|-------|------|---------|
| `totalEquity` | USD | Sum of all asset equities by USD value |
| `totalWalletBalance` | USD | Sum of all coin wallet balances |
| `totalMarginBalance` | USD | `totalWalletBalance + totalPerpUPL` |
| `totalAvailableBalance` | USD | `totalMarginBalance - Haircut - totalInitialMargin` |
| `totalPerpUPL` | USD | Aggregate unrealised PnL across all perps/futures |
| `totalInitialMargin` | USD | Sum of all position IM |
| `totalMaintenanceMargin` | USD | Sum of all position MM |
| `accountIMRate` | % | Account initial margin rate |
| `accountMMRate` | % | Account maintenance margin rate |

### Per-Coin Fields

| Field | Type | Formula |
|-------|------|---------|
| `coin` | string | Coin name |
| `equity` | coin | `walletBalance - spotBorrow + unrealisedPnl + optionValue` |
| `usdValue` | USD | USD equivalent |
| `walletBalance` | coin | Raw balance |
| `borrowAmount` | coin | Spot + derivatives liabilities |
| `spotBorrow` | coin | Spot margin + manual borrow |
| `unrealisedPnl` | coin | Perps/futures UPL for this coin |
| `cumRealisedPnl` | coin | Cumulative realized PnL |
| `locked` | coin | Locked in spot open orders |
| `totalOrderIM` | coin | Margin for pending orders |
| `totalPositionIM` | coin | Position initial margin + liq fee reserve |
| `totalPositionMM` | coin | Position maintenance margin |
| `marginCollateral` | bool | Platform eligibility |
| `collateralSwitch` | bool | User toggle (USDT/USDC always on) |
| `accruedInterest` | coin | Interest on borrows |

### Collateral Tiers (Haircut)

Endpoint: `GET /v5/spot-margin-trade/collateral` (public, no auth)

Tiered collateral ratios — as holdings increase, ratio decreases:
```
BTC: 0-1M coins = 0.85 ratio (15% haircut), >1M = 0.00
Collateral value = holding * indexPrice * collateralRatio
Haircut = holding * indexPrice * (1 - collateralRatio)
```

USDT and USDC: always 1.0 ratio (no haircut), cannot be disabled.

### Borrowing

| Endpoint | Purpose |
|----------|---------|
| `POST /v5/account/borrow` | Manual floating-rate borrow |
| `POST /v5/account/repay` | Repay (auto-converts if needed) |
| `POST /v5/account/no-convert-repay` | Repay without conversion |
| `GET /v5/account/collateral-info` | Rates, limits, current borrows |
| `GET /v5/account/borrow-history` | Historical records (30 day max) |

- Interest charged hourly at 05:00 UTC
- `freeBorrowingLimit`: interest-free for contract unrealized losses only
- Repayment blocked 04:00-05:30 UTC hourly
- Borrow limits shared across main + sub accounts

---

## 4. Position Management

### Position Fields

| Field | Type | Notes |
|-------|------|-------|
| `positionIdx` | int | 0=one-way, 1=hedge-buy, 2=hedge-sell |
| `symbol` | string | Symbol name |
| `side` | string | "Buy" (long), "Sell" (short), "" (none) |
| `size` | string | Always positive |
| `avgPrice` | string | Average entry price |
| `positionValue` | string | Notional value |
| `leverage` | string | Position leverage |
| `markPrice` | string | Current mark price |
| `liqPrice` | string | Liquidation price (empty for portfolio margin) |
| `positionIM` | string | Initial margin |
| `positionMM` | string | Maintenance margin |
| `unrealisedPnl` | string | Unrealized PnL |
| `curRealisedPnl` | string | Realized PnL for current holding |
| `cumRealisedPnl` | string | All-time cumulative realized |
| `takeProfit` | string | TP price |
| `stopLoss` | string | SL price |
| `trailingStop` | string | Trailing stop distance |
| `sessionAvgPrice` | string | USDC 8-hour session avg price |
| `positionStatus` | string | Normal, Liq, Adl |
| `adlRankIndicator` | int | 0-5 ADL rank |
| `isReduceOnly` | bool | System-enforced reduce only |
| `autoAddMargin` | int | 0=off, 1=on |
| `riskId` | int | Risk tier ID |
| `seq` | long | Cross-sequence for matching fills |

### Leverage Rules (UTA 2.0)

| Mode | Category | Buy/Sell Leverage |
|------|----------|------------------|
| One-Way | All | Must be equal |
| Hedge | Linear Isolated | Can differ |
| Hedge | Linear Cross | Must be equal |

### Position Mode Support (UTA 2.0)

| Contract Type | One-Way | Hedge |
|---------------|---------|-------|
| USDT Perpetual | YES | YES |
| USDT Futures | YES | NO |
| USDC Perpetual | YES | NO |
| Inverse Perpetual | YES | NO |
| Inverse Futures | YES | NO |

### Risk Limits

Tiered system per symbol:
- Each tier has: `riskLimitValue` (max position), `maintenanceMargin` (MMR), `initialMargin` (IMR), `maxLeverage`
- Higher tiers = larger positions = higher margin rates = lower max leverage
- Auto risk-limit adjustment since March 2024

### TP/SL Modes

| Mode | Scope | Limit Orders | Multiple |
|------|-------|-------------|----------|
| Full | Entire position | Market only | One per side |
| Partial | Partial qty | Market or Limit | Multiple allowed |

---

## 5. Order Management

### Order Types

| Type | `orderType` | `triggerPrice` | Margin |
|------|------------|----------------|--------|
| Market | `Market` | - | Immediate |
| Limit | `Limit` | - | Occupied |
| Conditional Stop | `Market`/`Limit` | Set | Not occupied until trigger |
| TP/SL | `Market`/`Limit` | Set | Depends on orderFilter |

### Key Parameters

| Parameter | Values | Notes |
|-----------|--------|-------|
| `timeInForce` | GTC, IOC, FOK, PostOnly | Market always IOC |
| `reduceOnly` | bool | Only reduce position, auto-splits if > max qty |
| `closeOnTrigger` | bool | Close order, cancels others if margin insufficient |
| `positionIdx` | 0, 1, 2 | Required for hedge mode |
| `isLeverage` | 0, 1 | Spot margin toggle |
| `orderFilter` | Order, StopOrder, tpslOrder | Spot filtering |
| `smpType` | None, CancelMaker, CancelTaker, CancelBoth | Self-match prevention |
| `triggerBy` | LastPrice, IndexPrice, MarkPrice | Conditional trigger type |
| `triggerDirection` | 1 (rise), 2 (fall) | Conditional direction |
| `tpslMode` | Full, Partial | TP/SL scope |

### Batch Operations

| Operation | Max Linear | Max Inverse | Max Spot |
|-----------|-----------|------------|---------|
| Batch Place | 20 | 20 | 10 |
| Batch Amend | 20 | 20 | 10 |
| Batch Cancel | 20 | 20 | 10 |

### Order Limits Per Symbol

| Category | Active Orders | Conditional | TP/SL |
|----------|--------------|-------------|-------|
| Linear | 500 | 10 | - |
| Inverse | 500 | 10 | - |
| Spot | 500 total | 30 | 30 |
| Option | 50 total | - | - |

### Order Status Flow

```
New → PartiallyFilled → Filled
New → Cancelled
New → Rejected
Untriggered → Triggered → New → ...
Untriggered → Deactivated (TP/SL cancelled before trigger)
```

---

## 6. WebSocket Streams

### Endpoints

| Type | URL |
|------|-----|
| Public Linear | `wss://stream.bybit.com/v5/public/linear` |
| Public Inverse | `wss://stream.bybit.com/v5/public/inverse` |
| Public Spot | `wss://stream.bybit.com/v5/public/spot` |
| Private | `wss://stream.bybit.com/v5/private` |

### Public Topics

| Topic | Push Rate | Fields |
|-------|-----------|--------|
| `kline.{interval}.{symbol}` | 1-60s | start, end, OHLCV, confirm, timestamp |
| `tickers.{symbol}` | 100ms (deriv), 50ms (spot) | lastPrice, markPrice, indexPrice, OI, funding, bid/ask |
| `orderbook.{depth}.{symbol}` | 10-200ms by depth | bids, asks, update ID, seq |
| `publicTrade.{symbol}` | Real-time | price, size, side, timestamp |
| `allLiquidation.{symbol}` | 500ms | side, size, bankruptcy price |

### Private Topics

| Topic | Push Rate | Key Fields |
|-------|-----------|------------|
| `position` / `position.linear` / `position.inverse` | Real-time | All position fields, seq |
| `order` / `order.linear` / `order.inverse` / `order.spot` | Real-time | Full order state, cumExecQty/Fee |
| `execution` / `execution.linear` / `execution.inverse` | Real-time | execPrice, execQty, execFee, isMaker |
| `execution.fast` / `execution.fast.linear` | Real-time | Minimal fill data (faster) |
| `wallet` | Real-time | Account totals + per-coin balances |

**Important**: Wallet stream does NOT push on unrealised PnL changes alone — only on balance/position state changes.

### Category-Specific Ticker Differences

| Field | Linear | Inverse | Spot |
|-------|--------|---------|------|
| fundingRate | YES | YES | NO |
| openInterest | YES | YES | NO |
| markPrice | YES | YES | NO |
| indexPrice | YES | YES | NO |
| usdIndexPrice | NO | NO | YES |
| basis/basisRate | YES | YES | NO |

---

## 7. Settlement & Funding

### USDT Perpetuals
- Continuous funding every 8 hours (00:00, 08:00, 16:00 UTC)
- Funding = `positionValue * fundingRate`
- Long pays short when rate positive, vice versa

### USDC Perpetuals
- Same 8-hour funding intervals
- **Additional 8-hour session settlement** — PnL settled at `sessionAvgPrice`
- Funding and session combined in single transaction log entry
- Query via: `GET /v5/asset/settlement-record`

### Transaction Log
- `GET /v5/account/transaction-log` — up to 2 years
- Types: TRADE, SETTLEMENT, TRANSFER, FUNDING_FEE
- `change = cashFlow + funding - fee`
- `cashBalance` = wallet balance after transaction

---

## 8. Sub-Account Architecture

| Endpoint | Purpose |
|----------|---------|
| `GET /v5/asset/transfer/query-sub-member-list` | List all sub UIDs |
| `POST /v5/asset/transfer/universal-transfer` | Transfer between main/sub |
| `POST /v5/asset/transfer/inter-transfer` | Transfer between account types (same UID) |

- Each sub-account has its own UTA wallet
- Separate API keys per sub-account
- Sub can only transfer TO main (not to other subs)
- Borrow limits shared across main + all subs

---

## 9. Safety Features

### DCP (Disconnection Cancel-All Protection)
- Per product: SPOT, DERIVATIVES, OPTIONS
- Configurable time window: 3-300 seconds (default 10)
- When all private WS connections dead > timeWindow → cancel all orders
- **Recommendation: Enable for DERIVATIVES with 30s window**

### SMP (Self-Match Prevention)
- Prevents matching against own orders
- Types: CancelMaker, CancelTaker, CancelBoth
- Group-based (main + sub accounts can share group)

### Auto-Add Margin
- Per-symbol setting for isolated positions
- Automatically adds margin before liquidation
- `POST /v5/position/set-auto-add-margin`

---

## 10. What We Need to Build

### Phase 1: Portfolio Core (Foundation)

The portfolio layer sits BETWEEN the exchange client and the engine. It provides a unified view of the account regardless of which instrument categories are active.

```
BybitClient (raw API)
    ↓
PortfolioManager (NEW — this design)
    ↓
PlayEngine / ShadowEngine / CLI
```

**Core dataclasses:**
- `AccountSnapshot` — account-level equity, margin, available balance
- `CoinBalance` — per-coin wallet state, collateral, borrows
- `PositionView` — unified position across categories (abstracts linear/inverse)
- `InstrumentSpec` — cached instrument info (lot sizes, tick sizes, settle coin)

**Core services:**
- `PortfolioManager` — owns AccountSnapshot, refreshes from REST + WS
- `InstrumentRegistry` — caches instrument specs, resolves category/settleCoin for any symbol
- `CollateralCalculator` — tiered haircut math, available balance
- `RiskView` — account IM/MM rates, liquidation proximity, ADL rank

### Phase 2: Multi-Category Trading

- Parameterize `category` and `settleCoin` throughout exchange layer
- `InstrumentRegistry.resolve(symbol)` returns `(category, settleCoin, quoteCoin, contractType)`
- Order placement accepts any category, routes correctly
- Position queries aggregate across categories

### Phase 3: USDC Perp Support

- Same linear math as USDT (PnL, margin, liquidation)
- Different: settle coin, fee rates, session settlement
- Symbol mapping: `BTCPERP` → `(linear, USDC, USDC, LinearPerpetual)`
- 8-hour session settlement tracking

### Phase 4: Backtest/Shadow Adaptation

- SimExchange parameterized by settle coin and fee rates
- Ledger uses `quote` instead of `_usdt` naming
- Fee rate registry: `(category, settleCoin) → (taker, maker)`
- Shadow engine subscribes to correct WS channels per category

---

## 11. Current Codebase USDT Assumptions (Must Fix)

### Hard Blocks
| File | Line | Issue |
|------|------|-------|
| `system_config.py` | 112 | `validate_usdt_pair()` rejects non-USDT |
| `system_config.py` | 171 | `quote_ccy != "USDT"` validation |
| `bybit_trading.py` | 171, 201, 247 | `settleCoin="USDT"` hardcoded |
| `live.py` | 2188, 2215 | `get_wallet("USDT")` hardcoded |
| `position_manager.py` | 194, 263 | `get_wallet("USDT")` hardcoded |

### Math Assumptions (Correct for Linear, Wrong for Inverse)
| File | Issue |
|------|-------|
| `sim/types.py:269` | PnL = `(mark - entry) * size` (linear only) |
| `sim/ledger.py:198` | margin = `size * entry_price * IMR` (linear only) |
| `sim/liquidation_model.py:204` | Linear-only liquidation formula |
| `sim/funding_model.py:131` | `position_value = size * price` (linear only) |
| `execution_model.py:573` | `notional = size * price` (linear only) |

### Naming (Semantic Debt)
- All `_usdt` suffixed variables in ledger, types, constraints
- Should become `_quote` or `_settlement` for multi-currency

---

## Appendix A: Key API Endpoints

### Account
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/v5/account/info` | Account mode, margin mode, DCP |
| GET | `/v5/account/wallet-balance` | Full wallet + per-coin |
| POST | `/v5/account/set-margin-mode` | Switch margin mode |
| GET | `/v5/account/collateral-info` | Borrow rates, limits |
| POST | `/v5/account/set-collateral-switch` | Toggle coin as collateral |
| GET | `/v5/account/fee-rate` | Fee rates by category |
| GET | `/v5/account/transaction-log` | 2-year transaction history |
| GET | `/v5/account/borrow-history` | Borrow/interest records |

### Position
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/v5/position/list` | Positions by category |
| POST | `/v5/position/set-leverage` | Set leverage |
| POST | `/v5/position/switch-mode` | One-way / hedge mode |
| POST | `/v5/position/trading-stop` | TP/SL/trailing stop |
| POST | `/v5/position/set-auto-add-margin` | Auto-add margin |
| POST | `/v5/position/add-margin` | Manual margin add/reduce |
| GET | `/v5/position/closed-pnl` | Closed PnL records |
| GET | `/v5/market/risk-limit` | Risk limit tiers |

### Order
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/v5/order/create` | Place order |
| POST | `/v5/order/create-batch` | Batch place (up to 20) |
| POST | `/v5/order/amend` | Amend order |
| POST | `/v5/order/cancel` | Cancel order |
| POST | `/v5/order/cancel-all` | Cancel all (by symbol/settle/base) |
| GET | `/v5/order/realtime` | Open + recent closed orders |
| GET | `/v5/order/history` | 2-year order history |
| GET | `/v5/execution/list` | 2-year execution history |

### Market
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/v5/market/instruments-info` | Instrument specs |
| GET | `/v5/market/tickers` | Current tickers |
| GET | `/v5/market/kline` | OHLCV candles |
| GET | `/v5/market/orderbook` | Order book (up to 500 levels) |
| GET | `/v5/market/funding/history` | Funding rate history |
| GET | `/v5/market/open-interest` | Open interest |
| GET | `/v5/market/risk-limit` | Risk limit tiers |
| GET | `/v5/market/insurance` | Insurance fund |

### Asset
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/v5/asset/transfer/inter-transfer` | Internal transfer |
| POST | `/v5/asset/transfer/universal-transfer` | Sub-account transfer |
| GET | `/v5/asset/settlement-record` | USDC session settlements |
| GET | `/v5/asset/delivery-record` | Futures delivery records |
| GET | `/v5/spot-margin-trade/collateral` | Tiered collateral ratios |

## Appendix B: pybit Method Map

```python
from pybit.unified_trading import HTTP, WebSocket

# REST
session = HTTP(testnet=False, demo=False, api_key=KEY, api_secret=SECRET)

# Account
session.get_wallet_balance(accountType="UNIFIED")
session.get_account_info()
session.set_margin_mode(setMarginMode="REGULAR_MARGIN")
session.get_collateral_info(currency="BTC")
session.set_collateral_coin(coin="BTC", collateralSwitch="ON")
session.get_fee_rate(category="linear", symbol="BTCUSDT")
session.get_transaction_log(accountType="UNIFIED", category="linear")
session.get_borrow_history(currency="USDT")

# Position
session.get_positions(category="linear", symbol="BTCUSDT")
session.set_leverage(category="linear", symbol="BTCUSDT", buyLeverage="10", sellLeverage="10")
session.switch_position_mode(category="linear", symbol="BTCUSDT", mode=0)
session.set_trading_stop(category="linear", symbol="BTCUSDT", takeProfit="50000", positionIdx=0)
session.set_auto_add_margin(category="linear", symbol="BTCUSDT", autoAddMargin=1, positionIdx=0)
session.get_closed_pnl(category="linear", symbol="BTCUSDT")

# Orders
session.place_order(category="linear", symbol="BTCUSDT", side="Buy", orderType="Market", qty="0.001")
session.place_batch_order(category="linear", request=[...])
session.amend_order(category="linear", symbol="BTCUSDT", orderId="...", price="50000")
session.cancel_order(category="linear", symbol="BTCUSDT", orderId="...")
session.cancel_all_orders(category="linear", settleCoin="USDT")
session.get_open_orders(category="linear", symbol="BTCUSDT")
session.get_order_history(category="linear", symbol="BTCUSDT")
session.get_executions(category="linear", symbol="BTCUSDT")

# Market
session.get_instruments_info(category="linear", symbol="BTCUSDT")
session.get_tickers(category="linear", symbol="BTCUSDT")
session.get_kline(category="linear", symbol="BTCUSDT", interval="15")
session.get_orderbook(category="linear", symbol="BTCUSDT")
session.get_funding_rate_history(category="linear", symbol="BTCUSDT")
session.get_open_interest(category="linear", symbol="BTCUSDT", intervalTime="1h")
session.get_risk_limit(category="linear", symbol="BTCUSDT")

# Asset
session.get_coin_balance(accountType="UNIFIED", coin="USDT")
session.create_internal_transfer(transferId="uuid", coin="USDT", amount="100",
                                  fromAccountType="UNIFIED", toAccountType="FUND")

# WebSocket
ws_linear = WebSocket(channel_type="linear")
ws_linear.kline_stream(interval=1, symbol="BTCUSDT", callback=handle_kline)
ws_linear.ticker_stream(symbol="BTCUSDT", callback=handle_ticker)

ws_private = WebSocket(channel_type="private", api_key=KEY, api_secret=SECRET)
ws_private.position_stream(callback=handle_position)
ws_private.order_stream(callback=handle_order)
ws_private.execution_stream(callback=handle_execution)
ws_private.wallet_stream(callback=handle_wallet)
```
