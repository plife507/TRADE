"""
Bybit trading methods (orders, positions, batch operations).

Contains: create_order, amend_order, cancel_order, cancel_all_orders,
get_open_orders, get_order_history, set_leverage, create_conditional_order,
set_trading_stop, get_executions, get_closed_pnl, batch operations,
position management methods.
"""

from typing import TYPE_CHECKING

from ..utils.time_range import TimeRange

if TYPE_CHECKING:
    from .bybit_client import BybitClient


def create_order(
    client: "BybitClient",
    symbol: str,
    side: str,
    order_type: str,
    qty: float,
    price: float | None = None,
    time_in_force: str = "GTC",
    reduce_only: bool = False,
    close_on_trigger: bool = False,
    order_link_id: str | None = None,
    take_profit: str | None = None,
    stop_loss: str | None = None,
    tpsl_mode: str | None = None,
    tp_order_type: str | None = None,
    sl_order_type: str | None = None,
    tp_limit_price: str | None = None,
    sl_limit_price: str | None = None,
    trigger_price: str | None = None,
    trigger_direction: int | None = None,
    trigger_by: str | None = None,
    category: str = "linear",
    position_idx: int = 0,
) -> dict:
    """Place an order on Bybit."""
    client._order_limiter.acquire()

    kwargs: dict = {
        "category": category,
        "symbol": symbol,
        "side": side,
        "orderType": order_type,
        "qty": str(qty),
        "positionIdx": position_idx,
    }

    if price is not None:
        kwargs["price"] = str(price)
    if time_in_force:
        kwargs["timeInForce"] = time_in_force
    if reduce_only:
        kwargs["reduceOnly"] = True
    if close_on_trigger:
        kwargs["closeOnTrigger"] = True
    if order_link_id:
        kwargs["orderLinkId"] = order_link_id
    if take_profit:
        kwargs["takeProfit"] = str(take_profit)
    if stop_loss:
        kwargs["stopLoss"] = str(stop_loss)
    if tpsl_mode:
        kwargs["tpslMode"] = tpsl_mode
    if tp_order_type:
        kwargs["tpOrderType"] = tp_order_type
    if sl_order_type:
        kwargs["slOrderType"] = sl_order_type
    if tp_limit_price:
        kwargs["tpLimitPrice"] = str(tp_limit_price)
    if sl_limit_price:
        kwargs["slLimitPrice"] = str(sl_limit_price)
    if trigger_price:
        kwargs["triggerPrice"] = str(trigger_price)
    if trigger_direction:
        kwargs["triggerDirection"] = trigger_direction
    if trigger_by:
        kwargs["triggerBy"] = trigger_by

    response = client._session.place_order(**kwargs)
    return client._extract_result(response)


def amend_order(
    client: "BybitClient",
    symbol: str,
    order_id: str | None = None,
    order_link_id: str | None = None,
    qty: str | None = None,
    price: str | None = None,
    take_profit: str | None = None,
    stop_loss: str | None = None,
    tpsl_mode: str | None = None,
    tp_limit_price: str | None = None,
    sl_limit_price: str | None = None,
    trigger_price: str | None = None,
    trigger_by: str | None = None,
    category: str = "linear",
) -> dict:
    """Amend an existing order."""
    client._order_limiter.acquire()

    kwargs: dict[str, str] = {
        "category": category,
        "symbol": symbol,
    }

    if order_id:
        kwargs["orderId"] = order_id
    if order_link_id:
        kwargs["orderLinkId"] = order_link_id
    if qty:
        kwargs["qty"] = str(qty)
    if price:
        kwargs["price"] = str(price)
    if take_profit:
        kwargs["takeProfit"] = str(take_profit)
    if stop_loss:
        kwargs["stopLoss"] = str(stop_loss)
    if tpsl_mode:
        kwargs["tpslMode"] = tpsl_mode
    if tp_limit_price:
        kwargs["tpLimitPrice"] = str(tp_limit_price)
    if sl_limit_price:
        kwargs["slLimitPrice"] = str(sl_limit_price)
    if trigger_price:
        kwargs["triggerPrice"] = str(trigger_price)
    if trigger_by:
        kwargs["triggerBy"] = trigger_by

    response = client._session.amend_order(**kwargs)
    return client._extract_result(response)


def cancel_order(
    client: "BybitClient",
    symbol: str,
    order_id: str | None = None,
    order_link_id: str | None = None,
    category: str = "linear",
) -> dict:
    """Cancel an order."""
    client._order_limiter.acquire()

    kwargs: dict[str, str] = {
        "category": category,
        "symbol": symbol,
    }
    if order_id:
        kwargs["orderId"] = order_id
    if order_link_id:
        kwargs["orderLinkId"] = order_link_id

    response = client._session.cancel_order(**kwargs)
    return client._extract_result(response)


def cancel_all_orders(client: "BybitClient", symbol: str | None = None, category: str = "linear") -> dict:
    """Cancel all open orders."""
    client._order_limiter.acquire()

    kwargs: dict[str, str] = {"category": category}
    if symbol:
        kwargs["symbol"] = symbol
    else:
        kwargs["settleCoin"] = "USDT"

    response = client._session.cancel_all_orders(**kwargs)
    return client._extract_result(response)


def get_open_orders(
    client: "BybitClient",
    symbol: str | None = None,
    order_id: str | None = None,
    order_link_id: str | None = None,
    open_only: int = 0,
    limit: int = 50,
    category: str = "linear",
) -> list[dict]:
    """Get open orders with cursor-based pagination."""
    all_orders: list[dict] = []
    cursor: str | None = None

    while True:
        client._private_limiter.acquire()

        kwargs: dict = {
            "category": category,
            "limit": min(limit, 50),
            "openOnly": open_only,
        }
        if symbol:
            kwargs["symbol"] = symbol
        else:
            kwargs["settleCoin"] = "USDT"
        if order_id:
            kwargs["orderId"] = order_id
        if order_link_id:
            kwargs["orderLinkId"] = order_link_id
        if cursor:
            kwargs["cursor"] = cursor

        response = client._session.get_open_orders(**kwargs)
        result = client._extract_result(response)
        page = result.get("list", [])
        all_orders.extend(page)

        cursor = result.get("nextPageCursor")
        if not cursor or not page:
            break

    return all_orders


def get_order_history(
    client: "BybitClient",
    time_range: TimeRange,
    symbol: str | None = None,
    order_id: str | None = None,
    order_link_id: str | None = None,
    order_status: str | None = None,
    order_filter: str | None = None,
    limit: int = 50,
    category: str = "linear",
) -> dict:
    """Get order history."""
    client._private_limiter.acquire()

    time_params = time_range.to_bybit_params()
    client.logger.debug(f"get_order_history: {time_range.label} ({time_range.format_range()})")

    kwargs: dict = {
        "category": category,
        "limit": min(limit, 50),
        "startTime": time_params["startTime"],
        "endTime": time_params["endTime"],
    }
    if symbol:
        kwargs["symbol"] = symbol
    else:
        kwargs["settleCoin"] = "USDT"
    if order_id:
        kwargs["orderId"] = order_id
    if order_link_id:
        kwargs["orderLinkId"] = order_link_id
    if order_status:
        kwargs["orderStatus"] = order_status
    if order_filter:
        kwargs["orderFilter"] = order_filter

    response = client._session.get_order_history(**kwargs)
    return client._extract_result(response)


def set_leverage(client: "BybitClient", symbol: str, leverage: int, category: str = "linear") -> dict:
    """Set leverage for a symbol."""
    client._private_limiter.acquire()

    response = client._session.set_leverage(
        category=category,
        symbol=symbol,
        buyLeverage=str(leverage),
        sellLeverage=str(leverage),
    )
    return client._extract_result(response)


def create_conditional_order(
    client: "BybitClient",
    symbol: str,
    side: str,
    qty: str,
    trigger_price: str,
    trigger_direction: int,
    order_type: str = "Market",
    price: str | None = None,
    reduce_only: bool = True,
    order_link_id: str | None = None,
    time_in_force: str = "GTC",
    trigger_by: str = "LastPrice",
    category: str = "linear",
) -> dict:
    """Create a conditional (trigger) order."""
    client._order_limiter.acquire()

    kwargs: dict = {
        "category": category,
        "symbol": symbol,
        "side": side,
        "orderType": order_type,
        "qty": str(qty),
        "triggerPrice": str(trigger_price),
        "triggerDirection": trigger_direction,
        "triggerBy": trigger_by,
        "reduceOnly": reduce_only,
        "timeInForce": time_in_force,
    }

    if price:
        kwargs["price"] = str(price)
    if order_link_id:
        kwargs["orderLinkId"] = order_link_id

    response = client._session.place_order(**kwargs)
    return client._extract_result(response)


def set_trading_stop(
    client: "BybitClient",
    symbol: str,
    position_idx: int = 0,
    take_profit: float | None = None,
    stop_loss: float | None = None,
    trailing_stop: float | None = None,
    tp_trigger_by: str = "LastPrice",
    sl_trigger_by: str = "LastPrice",
    active_price: float | None = None,
    tpsl_mode: str = "Full",
    tp_size: str | None = None,
    sl_size: str | None = None,
    tp_limit_price: str | None = None,
    sl_limit_price: str | None = None,
    tp_order_type: str = "Market",
    sl_order_type: str = "Market",
    category: str = "linear",
) -> dict:
    """Set trading stop (TP/SL/trailing) for a position."""
    client._private_limiter.acquire()

    kwargs: dict = {
        "category": category,
        "symbol": symbol,
        "positionIdx": position_idx,
    }

    if take_profit is not None:
        kwargs["takeProfit"] = str(take_profit)
        kwargs["tpTriggerBy"] = tp_trigger_by
        kwargs["tpOrderType"] = tp_order_type
    if stop_loss is not None:
        kwargs["stopLoss"] = str(stop_loss)
        kwargs["slTriggerBy"] = sl_trigger_by
        kwargs["slOrderType"] = sl_order_type
    if trailing_stop is not None:
        kwargs["trailingStop"] = str(trailing_stop)
    if active_price is not None:
        kwargs["activePrice"] = str(active_price)
    if tpsl_mode:
        kwargs["tpslMode"] = tpsl_mode
    if tp_size:
        kwargs["tpSize"] = tp_size
    if sl_size:
        kwargs["slSize"] = sl_size
    if tp_limit_price:
        kwargs["tpLimitPrice"] = tp_limit_price
    if sl_limit_price:
        kwargs["slLimitPrice"] = sl_limit_price

    response = client._session.set_trading_stop(**kwargs)
    return client._extract_result(response)


def get_executions(
    client: "BybitClient",
    time_range: TimeRange,
    symbol: str | None = None,
    order_id: str | None = None,
    exec_type: str | None = None,
    limit: int = 50,
    category: str = "linear",
) -> list[dict]:
    """Get trade execution history."""
    client._private_limiter.acquire()

    time_params = time_range.to_bybit_params()
    client.logger.debug(f"get_executions: {time_range.label} ({time_range.format_range()})")

    kwargs: dict = {
        "category": category,
        "limit": min(limit, 100),
        "startTime": time_params["startTime"],
        "endTime": time_params["endTime"],
    }
    if symbol:
        kwargs["symbol"] = symbol
    if order_id:
        kwargs["orderId"] = order_id
    if exec_type:
        kwargs["execType"] = exec_type

    response = client._session.get_executions(**kwargs)
    result = client._extract_result(response)
    return result.get("list", [])


def get_closed_pnl(
    client: "BybitClient",
    time_range: TimeRange,
    symbol: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
    category: str = "linear",
) -> dict:
    """Get closed position PnL history."""
    client._private_limiter.acquire()

    time_params = time_range.to_bybit_params()
    client.logger.debug(f"get_closed_pnl: {time_range.label} ({time_range.format_range()})")

    kwargs: dict = {
        "category": category,
        "limit": min(limit, 50),
        "startTime": time_params["startTime"],
        "endTime": time_params["endTime"],
    }
    if symbol:
        kwargs["symbol"] = symbol
    if cursor:
        kwargs["cursor"] = cursor

    response = client._session.get_closed_pnl(**kwargs)
    return client._extract_result(response)


# ==================== Batch Operations ====================

def batch_create_orders(client: "BybitClient", orders: list[dict], category: str = "linear") -> dict:
    """Place multiple orders in a single request (max 10)."""
    client._order_limiter.acquire()

    response = client._session.place_batch_order(
        category=category,
        request=orders[:10],
    )
    return client._extract_result(response)


def batch_amend_orders(client: "BybitClient", orders: list[dict], category: str = "linear") -> dict:
    """Amend multiple orders in a single request (max 10)."""
    client._order_limiter.acquire()

    response = client._session.amend_batch_order(
        category=category,
        request=orders[:10],
    )
    return client._extract_result(response)


def batch_cancel_orders(client: "BybitClient", orders: list[dict], category: str = "linear") -> dict:
    """Cancel multiple orders in a single request (max 10)."""
    client._order_limiter.acquire()

    response = client._session.cancel_batch_order(
        category=category,
        request=orders[:10],
    )
    return client._extract_result(response)


# ==================== Position Management ====================

def set_risk_limit(
    client: "BybitClient",
    symbol: str,
    risk_id: int,
    position_idx: int = 0,
    category: str = "linear",
) -> dict:
    """Set risk limit tier for a symbol."""
    client._private_limiter.acquire()

    response = client._session.set_risk_limit(
        category=category,
        symbol=symbol,
        riskId=risk_id,
        positionIdx=position_idx,
    )
    return client._extract_result(response)


def set_tp_sl_mode(
    client: "BybitClient",
    symbol: str,
    tp_sl_mode: str,
    category: str = "linear",
) -> dict:
    """Set TP/SL mode (Full or Partial)."""
    client._private_limiter.acquire()

    response = client._session.set_tp_sl_mode(
        category=category,
        symbol=symbol,
        tpSlMode=tp_sl_mode,
    )
    return client._extract_result(response)


def set_auto_add_margin(
    client: "BybitClient",
    symbol: str,
    auto_add_margin: int,
    position_idx: int = 0,
    category: str = "linear",
) -> dict:
    """Enable/disable auto add margin."""
    client._private_limiter.acquire()

    response = client._session.set_auto_add_margin(
        category=category,
        symbol=symbol,
        autoAddMargin=auto_add_margin,
        positionIdx=position_idx,
    )
    return client._extract_result(response)


def modify_position_margin(
    client: "BybitClient",
    symbol: str,
    margin: str,
    position_idx: int = 0,
    category: str = "linear",
) -> dict:
    """Add or reduce position margin."""
    client._private_limiter.acquire()

    response = client._session.add_or_reduce_margin(
        category=category,
        symbol=symbol,
        margin=margin,
        positionIdx=position_idx,
    )
    return client._extract_result(response)


def switch_cross_isolated_margin(
    client: "BybitClient",
    symbol: str,
    trade_mode: int,
    buy_leverage: str,
    sell_leverage: str,
    category: str = "linear",
) -> dict:
    """Switch between cross and isolated margin."""
    client._private_limiter.acquire()

    response = client._session.switch_margin_mode(
        category=category,
        symbol=symbol,
        tradeMode=trade_mode,
        buyLeverage=buy_leverage,
        sellLeverage=sell_leverage,
    )
    return client._extract_result(response)


def switch_position_mode_v5(
    client: "BybitClient",
    mode: int,
    symbol: str | None = None,
    coin: str | None = None,
    category: str = "linear",
) -> dict:
    """Switch position mode (One-way: 0, Hedge: 3)."""
    client._private_limiter.acquire()

    kwargs: dict = {
        "category": category,
        "mode": mode,
    }
    if symbol:
        kwargs["symbol"] = symbol
    if coin:
        kwargs["coin"] = coin

    response = client._session.switch_position_mode(**kwargs)
    return client._extract_result(response)


def set_disconnect_cancel_all(client: "BybitClient", time_window: int) -> dict:
    """Set Disconnect Cancel All (DCP) window."""
    client._private_limiter.acquire()

    response = client._session.set_dcp(timeWindow=str(time_window))
    return client._extract_result(response)
