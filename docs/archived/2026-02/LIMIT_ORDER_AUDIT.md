# Limit Order Audit Report

**Date:** 2026-02-12
**Branch:** feature/unified-engine
**Status:** Investigation complete, no code changes made

## Executive Summary

The limit order infrastructure is **~90% built** across all layers. The SimulatedExchange, BacktestExchange adapter, ExchangeManager, `bybit_trading.py`, and pybit SDK all fully support limit orders. The **only broken links** are in the OrderExecutor (hardcodes market orders), the LiveExchange adapter (drops order type info), and the Play DSL (no order type field).

## Layer-by-Layer Validation

| Layer | Limit Orders | TP as Limit | tpOrderType / slOrderType | Trailing Stop |
|-------|-------------|-------------|--------------------------|---------------|
| **Bybit API** | `orderType: "Limit"` | `tpOrderType: "Limit"` + `tpLimitPrice` | Both in `place_order` AND `set_trading_stop` | `trailingStop` + `activePrice` |
| **pybit SDK** | `**kwargs` passthrough | Same | Same | Same |
| **`bybit_trading.py`** | `create_order(order_type="Limit")` | `tp_order_type`, `tp_limit_price` params | Both supported | `trailing_stop`, `active_price` params |
| **ExchangeManager** | `limit_buy()`, `limit_sell()`, `limit_buy_with_tpsl()`, `limit_sell_with_tpsl()` | `tp_order_type="Market"` default | Params exist, default `"Market"` | Not exposed |
| **SimulatedExchange** | `submit_limit_order()`, full OrderBook, TIF | TP fills as market-like trigger | Not in sim Order type | Not implemented |
| **BacktestExchange adapter** | Routes LIMIT/STOP correctly | N/A | N/A | N/A |
| **`interfaces.Order`** | `order_type="LIMIT"` field exists | `take_profit` field, no `tp_order_type` | Missing | Missing |
| **OrderExecutor** | **HARDCODED `market_buy()`/`market_sell()`** | N/A | N/A | N/A |
| **LiveExchange adapter** | Converts to Signal -> always market | Passes TP/SL in metadata only | Not forwarded | Not forwarded |
| **Play DSL** | No `order_type:` field | No `tp_order_type:` field | Missing | Missing |

## What Already Works (No Changes Needed)

### Bybit API (`/v5/order/create`)

Confirmed from `reference/exchanges/bybit/docs/api-explorer/v5/trade/create-order.api.mdx`:

| Parameter | Type | Values |
|-----------|------|--------|
| `orderType` | string | `Market`, `Limit` |
| `price` | string | Required for Limit, ignored for Market |
| `timeInForce` | string | `GTC`, `IOC`, `FOK`, `PostOnly` |
| `triggerPrice` | string | For stop/conditional orders |
| `tpslMode` | string | `Full`, `Partial` |
| `tpOrderType` | string | `Market`, `Limit` - order type when TP triggers |
| `slOrderType` | string | `Market`, `Limit` - order type when SL triggers |
| `tpLimitPrice` | string | Limit price when TP triggers |
| `slLimitPrice` | string | Limit price when SL triggers |
| `reduceOnly` | boolean | For close-only orders |

### Bybit Set Trading Stop (`/v5/position/trading-stop`)

Confirmed from `reference/exchanges/bybit/docs/api-explorer/v5/position/trading-stop.api.mdx`:

| Parameter | Type | Values |
|-----------|------|--------|
| `takeProfit` | string | TP price |
| `stopLoss` | string | SL price |
| `trailingStop` | string | Trailing stop distance |
| `activePrice` | string | Trailing stop trigger price |
| `tpOrderType` | string | `Market`, `Limit` |
| `slOrderType` | string | `Market`, `Limit` |
| `tpLimitPrice` | string | Limit fill price for TP |
| `slLimitPrice` | string | Limit fill price for SL |
| `tpSize` / `slSize` | string | Partial close sizes |

### pybit SDK

Both `place_order(**kwargs)` and `set_trading_stop(**kwargs)` use `**kwargs` passthrough. Any Bybit API parameter works without SDK changes.

### `src/exchanges/bybit_trading.py`

`create_order()` already accepts all parameters:
- `order_type` (Market/Limit)
- `price` (limit price)
- `time_in_force` (GTC/IOC/FOK/PostOnly)
- `tp_order_type`, `sl_order_type`
- `tp_limit_price`, `sl_limit_price`
- `tpsl_mode` (Full/Partial)
- `trigger_price`, `trigger_direction`, `trigger_by`

`set_trading_stop()` already accepts:
- `tp_order_type` (defaults to `"Market"`)
- `sl_order_type` (defaults to `"Market"`)
- `tp_limit_price`, `sl_limit_price`
- `trailing_stop`, `active_price`

### ExchangeManager (`src/core/exchange_manager.py`)

Already has limit order methods:
- `limit_buy(symbol, usd_amount, price, time_in_force, reduce_only, order_link_id)`
- `limit_sell(symbol, usd_amount, price, time_in_force, reduce_only, order_link_id)`
- `limit_buy_with_tpsl(symbol, usd_amount, price, tp, sl, tif, tpsl_mode, tp_order_type, sl_order_type, order_link_id)`
- `limit_sell_with_tpsl(symbol, usd_amount, price, tp, sl, tif, tpsl_mode, tp_order_type, sl_order_type, order_link_id)`

### SimulatedExchange (`src/backtest/sim/exchange.py`)

Full limit order infrastructure:
- `submit_limit_order(side, size_usdt, limit_price, sl, tp, tif, reduce_only)`
- `submit_stop_order(side, size_usdt, trigger_price, trigger_direction, limit_price, sl, tp, reduce_only)`
- `amend_order(order_id, limit_price, trigger_price, size_usdt, sl, tp)`
- `cancel_order_by_id()` / `cancel_all_orders()`
- `OrderBook` with up to 100 concurrent orders
- `check_limit_fill()` with price improvement (buy limit fills when low <= limit_price)
- TimeInForce: GTC, IOC, FOK, PostOnly
- Maker fee rate for limit fills (vs taker for market)
- Reduce-only order support
- Smoke tests for all order types in `src/cli/smoke_tests/sim_orders.py`

### BacktestExchange Adapter (`src/engine/adapters/backtest.py`)

Already routes all order types:
```python
if order.order_type.upper() == "MARKET":
    sim_order_id = self._sim_exchange.submit_order(...)
elif order.order_type.upper() == "LIMIT":
    sim_order_id = self._sim_exchange.submit_limit_order(...)
elif order.order_type.upper() in ("STOP", "STOP_MARKET"):
    sim_order_id = self._sim_exchange.submit_stop_order(...)
```

### Unified Order Interface (`src/engine/interfaces.py`)

Already has the key fields:
```python
@dataclass(slots=True)
class Order:
    order_type: Literal["MARKET", "LIMIT", "STOP_MARKET", "STOP_LIMIT"] = "MARKET"
    limit_price: float | None = None
    trigger_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
```

## The Three Broken Links

### Link 1: OrderExecutor Hardcodes Market Orders

**File:** `src/core/order_executor.py` lines 341-344

```python
# CURRENT: always market, ignores order_type
if signal.direction == "LONG":
    order_result = self.exchange.market_buy(signal.symbol, exec_size)
elif signal.direction == "SHORT":
    order_result = self.exchange.market_sell(signal.symbol, exec_size)
```

**Fix:** Check `signal.metadata.get("order_type")` and call `self.exchange.limit_buy()` or `self.exchange.limit_buy_with_tpsl()` when order_type is LIMIT. The limit methods already exist on ExchangeManager.

### Link 2: LiveExchange Adapter Drops Order Type Info

**File:** `src/engine/adapters/live.py` lines 1539-1623

Converts unified `Order` to `Signal` and stores `order_type` and `limit_price` in `signal_metadata` dict. But `OrderExecutor.execute()` never reads those metadata fields -- it just calls `market_buy()`/`market_sell()` regardless.

### Link 3: Play DSL Has No Order Type Field

**File:** `src/core/play.py`

No `order_type:`, `limit_price:`, `tp_order_type:`, or `sl_order_type:` fields in the YAML schema. Entries are purely signal-based (conditions true -> enter at market).

## Fee Impact

| Scenario | Entry Fee | TP Fee | SL Fee | Round Trip |
|----------|-----------|--------|--------|------------|
| **Current (all market)** | 0.055% taker | 0.055% taker (Trading Stop) | 0.055% taker | **0.165%** |
| **Limit entry + limit TP** | 0.02% maker | 0.02% maker | 0.055% taker | **0.095%** |
| **Savings per $10K trade** | | | | **$7.00** |

Bybit maker fee: 0.02%. Bybit taker fee: 0.055%. Difference: 0.035% per side.

## Quickest Wins (Ranked by Effort/Value)

| # | Change | Files to Modify | Effort | Impact |
|---|--------|----------------|--------|--------|
| 1 | TP as limit order (live) | `order_executor.py`, `live.py` adapter - pass `tp_order_type="Limit"` | ~20 lines | Saves 0.035%/trade on every TP hit |
| 2 | Wire `order_type` through OrderExecutor | `order_executor.py` - check metadata, call `limit_buy()` when LIMIT | ~30 lines | Enables limit entries end-to-end |
| 3 | Add `order_type:` + `limit_price:` to Play DSL | `play.py` parser, `PLAY_DSL_REFERENCE.md` | ~50 lines | Play authors can specify limit entries |
| 4 | Add `tpOrderType`/`slOrderType` to sim | `sim/types.py` Order, `sim/exchange.py` TP/SL eval | ~40 lines | Backtest parity for limit TP fills |
| 5 | Trailing stop support (live) | `live.py` adapter - pass `trailing_stop` to `set_trading_stop()` | ~20 lines | Dynamic SL adjustment |
| 6 | PostOnly enforcement for limit entries | Pass `time_in_force="PostOnly"` | ~5 lines | Guarantees maker fee |

## What the Play DSL Would Need

```yaml
# Future DSL (proposed, not implemented):
entry:
  direction: long
  conditions: [...]
  order_type: limit              # NEW: market (default) | limit
  limit_offset_pct: -0.3         # NEW: offset from signal price (negative = below for buys)
  time_in_force: GTC             # NEW: GTC | IOC | FOK | PostOnly
  expire_after_bars: 5           # NEW: cancel unfilled limit after N exec bars

exit:
  conditions: [...]
  take_profit: 2.0
  tp_order_type: Limit           # NEW: Market (default) | Limit
  stop_loss: 1.0
  sl_order_type: Market          # NEW: Market (default) -- SL should stay market for safety
```

## Sim Gaps for Full Parity

The SimulatedExchange supports limit entries/exits but lacks:

| Feature | Bybit Has | Sim Has | Gap |
|---------|-----------|---------|-----|
| `tpOrderType` per position | Yes | No | TP always fills as market-trigger |
| `slOrderType` per position | Yes | No | SL always fills as market-trigger |
| `tpLimitPrice` | Yes | No | No limit fill price for TP |
| `slLimitPrice` | Yes | No | No limit fill price for SL |
| `tpslMode` Full/Partial | Yes | No | No partial TP/SL close |
| `trailingStop` | Yes | No | No trailing stop logic |
| Maker vs taker fee on TP/SL | Yes (implicit) | Partial | All TP/SL fills use taker fee |

## File Reference

| File | Role |
|------|------|
| `src/core/order_executor.py` | **Broken link 1** - hardcodes market_buy/sell |
| `src/engine/adapters/live.py` | **Broken link 2** - drops order type in Signal conversion |
| `src/core/play.py` | **Broken link 3** - no order_type in DSL |
| `src/core/exchange_manager.py:356-370` | limit_buy/sell/with_tpsl methods (WORKING) |
| `src/core/exchange_orders_limit.py` | Limit order Bybit API calls (WORKING) |
| `src/core/exchange_orders_market.py` | Market order Bybit API calls (WORKING) |
| `src/exchanges/bybit_trading.py` | Low-level Bybit create_order/set_trading_stop (WORKING) |
| `src/backtest/sim/exchange.py` | SimulatedExchange with full limit support (WORKING) |
| `src/backtest/sim/types.py` | Order/OrderBook/TimeInForce types (WORKING) |
| `src/engine/adapters/backtest.py` | BacktestExchange routes all order types (WORKING) |
| `src/engine/interfaces.py` | Unified Order with order_type field (WORKING) |
| `src/cli/smoke_tests/sim_orders.py` | Limit order smoke tests (WORKING) |
| `reference/exchanges/bybit/docs/api-explorer/v5/trade/create-order.api.mdx` | Bybit Place Order API spec |
| `reference/exchanges/bybit/docs/api-explorer/v5/position/trading-stop.api.mdx` | Bybit Set Trading Stop API spec |
| `reference/exchanges/bybit/docs/api-explorer/v5/position/tpsl-mode.api.mdx` | Bybit TP/SL Mode API spec |
| `reference/exchanges/pybit/pybit/_v5_trade.py` | pybit place_order (kwargs passthrough) |
| `reference/exchanges/pybit/pybit/_v5_position.py` | pybit set_trading_stop (kwargs passthrough) |
