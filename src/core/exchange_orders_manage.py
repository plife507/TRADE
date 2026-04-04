"""
Order management methods for ExchangeManager.

Handles:
- Get open orders
- Cancel order(s)
- Amend orders
- Close position(s)
- Order history/executions
- Batch operations
"""

from typing import Any, TYPE_CHECKING

from ..utils.datetime_utils import parse_bybit_ts as _parse_bybit_ts
from ..utils.helpers import safe_float
from ..utils.logger import get_module_logger
from ..config.constants import LINEAR_SETTLE_COINS
from ..utils.time_range import TimeRange

logger = get_module_logger(__name__)

if TYPE_CHECKING:
    from .exchange_manager import ExchangeManager, OrderResult, Order


# =============================================================================
# Order Queries
# =============================================================================

def get_open_orders(manager: "ExchangeManager", symbol: str | None = None) -> list["Order"]:
    """Get all open orders. When no symbol, queries all settle coins."""
    from .exchange_manager import Order

    try:
        if symbol:
            raw_orders = manager.bybit.get_open_orders(symbol=symbol)
        else:
            # Query all settle coins to get complete order list
            raw_orders = []
            for settle_coin in LINEAR_SETTLE_COINS:
                raw_orders.extend(manager.bybit.get_open_orders(settle_coin=settle_coin))

        orders = []
        for order in raw_orders:
            orders.append(Order(
                order_id=str(order.get("orderId", "")),
                order_link_id=order.get("orderLinkId"),
                symbol=str(order.get("symbol", "")),
                side=str(order.get("side", "")),
                order_type=str(order.get("orderType", "")),
                price=safe_float(order.get("price")) if order.get("price") else None,
                qty=safe_float(order.get("qty", 0)),
                filled_qty=safe_float(order.get("cumExecQty", 0)),
                remaining_qty=safe_float(order.get("leavesQty", 0)),
                status=str(order.get("orderStatus", "")),
                time_in_force=str(order.get("timeInForce", "")),
                reduce_only=order.get("reduceOnly", False),
                trigger_price=safe_float(order.get("triggerPrice")) if order.get("triggerPrice") else None,
                trigger_by=order.get("triggerBy"),
                take_profit=safe_float(order.get("takeProfit")) if order.get("takeProfit") else None,
                stop_loss=safe_float(order.get("stopLoss")) if order.get("stopLoss") else None,
                created_time=_parse_bybit_ts(order.get("createdTime")),
                updated_time=_parse_bybit_ts(order.get("updatedTime")),
            ))
        
        return orders
        
    except Exception as e:
        manager.logger.error("Get open orders failed: %s", e)
        return []


# =============================================================================
# Cancel/Amend Orders
# =============================================================================

def cancel_order(
    manager: "ExchangeManager",
    symbol: str,
    order_id: str | None = None,
    order_link_id: str | None = None,
) -> bool:
    """Cancel a specific order."""
    if not order_id and not order_link_id:
        manager.logger.error("Must provide order_id or order_link_id")
        return False
    
    try:
        manager.bybit.cancel_order(symbol=symbol, order_id=order_id, order_link_id=order_link_id)
        manager.logger.info("Cancelled order %s for %s", order_id or order_link_id, symbol)
        return True
    except Exception as e:
        manager.logger.error("Cancel order failed: %s", e)
        return False


def cancel_all_orders(manager: "ExchangeManager", symbol: str | None = None) -> bool:
    """Cancel all open orders."""
    try:
        orders = get_open_orders(manager, symbol)
        if not orders:
            manager.logger.debug("No orders to cancel%s", f" for {symbol}" if symbol else "")
            return True
        
        if symbol is None:
            symbols = set(order.symbol for order in orders)
            success_count = 0
            for sym in symbols:
                try:
                    manager.bybit.cancel_all_orders(symbol=sym)
                    success_count += 1
                except Exception as e:
                    manager.logger.warning("Failed to cancel orders for %s: %s", sym, e)
            
            total = len(symbols)
            if success_count < total:
                manager.logger.error("Partial cancel: only %s/%s symbol(s) succeeded", success_count, total)
            else:
                manager.logger.info("Cancelled orders for all %s symbol(s)", total)
            return success_count == total
        else:
            manager.bybit.cancel_all_orders(symbol)
            manager.logger.warning("Cancelled all orders for %s", symbol)
            return True
            
    except Exception as e:
        manager.logger.error("Cancel all orders failed: %s", e)
        return False


def amend_order(
    manager: "ExchangeManager",
    symbol: str,
    order_id: str | None = None,
    order_link_id: str | None = None,
    qty: float | None = None,
    price: float | None = None,
    take_profit: float | None = None,
    stop_loss: float | None = None,
    trigger_price: float | None = None,
) -> bool:
    """Amend an existing order."""
    from . import exchange_instruments as inst
    
    if not order_id and not order_link_id:
        manager.logger.error("Must provide order_id or order_link_id")
        return False
    
    try:
        kwargs = {"symbol": symbol, "order_id": order_id, "order_link_id": order_link_id}
        if qty is not None:
            kwargs["qty"] = str(qty)
        if price is not None:
            kwargs["price"] = str(inst.round_price(manager, symbol, price))
        if take_profit is not None:
            kwargs["take_profit"] = str(take_profit)
        if stop_loss is not None:
            kwargs["stop_loss"] = str(stop_loss)
        if trigger_price is not None:
            kwargs["trigger_price"] = str(trigger_price)

        manager.bybit.amend_order(**kwargs)
        manager.logger.info("Amended order %s for %s", order_id or order_link_id, symbol)
        return True
        
    except Exception as e:
        manager.logger.error("Amend order failed: %s", e)
        return False


# =============================================================================
# Close Positions
# =============================================================================

def close_position(
    manager: "ExchangeManager",
    symbol: str,
    cancel_conditional_orders: bool = True,
) -> "OrderResult":
    """Close position for a symbol."""
    from .exchange_manager import OrderResult
    from . import exchange_websocket as ws
    from . import exchange_positions as pos

    position = manager.get_position(symbol)
    
    if position is None or not position.is_open:
        return OrderResult(success=True, error="No position to close")
    
    close_side = "Sell" if position.side == "long" else "Buy"

    try:
        # DATA-018: Close position FIRST, then cancel conditionals.
        # If close fails, TP/SL remain active to protect the position.
        result = manager.bybit.create_order(
            symbol=symbol, side=close_side, order_type="Market",
            qty=position.size, reduce_only=True,
        )

        # Close succeeded — now safe to cancel remaining conditional orders
        cancelled_orders = []
        if cancel_conditional_orders:
            try:
                cancelled_orders = pos.cancel_position_conditional_orders(
                    manager, symbol=symbol, position_side=position.side,
                )
            except Exception as cancel_err:
                # Non-fatal: position is closed, stale conditionals will be
                # rejected by exchange (reduce_only on a closed position).
                manager.logger.warning(
                    "Position closed but failed to cancel conditionals for %s: %s", symbol, cancel_err
                )

        logger.info(
            "[POSITION_CLOSED] symbol=%s side=%s size=$%.2f pnl=$%.2f cancelled_conditional_orders=%d",
            symbol, close_side, position.size_usdt, position.unrealized_pnl, len(cancelled_orders),
        )

        ws.remove_symbol_from_websocket(manager, symbol)

        return OrderResult(
            success=True, order_id=result.get("orderId"), symbol=symbol,
            side=close_side, qty=position.size, raw_response=result,
        )

    except Exception as e:
        manager.logger.error("Close position failed for %s: %s", symbol, e)
        return OrderResult(success=False, error=str(e))


def close_all_positions(manager: "ExchangeManager") -> list["OrderResult"]:
    """Close all open positions."""
    from .exchange_manager import OrderResult

    results = []
    positions = manager.get_all_positions()
    
    manager.logger.warning("Closing all positions (%s open)", len(positions))
    
    for pos in positions:
        result = close_position(manager, pos.symbol)
        results.append(result)
    
    return results


# =============================================================================
# Order History & Executions
# =============================================================================

def get_order_history(
    manager: "ExchangeManager",
    time_range: TimeRange,
    symbol: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Get order history. TimeRange is REQUIRED. Queries all settle coins when no symbol."""
    try:
        if symbol:
            result = manager.bybit.get_order_history(time_range=time_range, symbol=symbol, limit=limit)
            return result.get("list", [])
        else:
            all_orders: list[dict] = []
            for settle_coin in LINEAR_SETTLE_COINS:
                result = manager.bybit.get_order_history(
                    time_range=time_range, symbol=None, limit=limit, settle_coin=settle_coin,
                )
                all_orders.extend(result.get("list", []))
            return all_orders
    except Exception as e:
        manager.logger.error("Get order history failed: %s", e)
        return []


def get_executions(
    manager: "ExchangeManager",
    time_range: TimeRange,
    symbol: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Get trade execution history. TimeRange is REQUIRED."""
    try:
        return manager.bybit.get_executions(time_range=time_range, symbol=symbol, limit=limit)
    except Exception as e:
        manager.logger.error("Get executions failed: %s", e)
        return []


def get_closed_pnl(
    manager: "ExchangeManager",
    time_range: TimeRange,
    symbol: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Get closed position PnL history. TimeRange is REQUIRED.

    Raises on failure so callers can distinguish real-zero from errors.
    """
    result = manager.bybit.get_closed_pnl(time_range=time_range, symbol=symbol, limit=limit)
    return result.get("list", [])


# =============================================================================
# Batch Operations
# =============================================================================

def batch_market_orders(
    manager: "ExchangeManager",
    orders: list[dict[str, Any]],
) -> list["OrderResult"]:
    """Execute multiple market orders in a batch."""
    from .exchange_manager import OrderResult
    from . import exchange_instruments as inst

    # Safety: check panic state before batch execution
    from .safety import get_panic_state
    if get_panic_state().is_triggered:
        return [OrderResult(success=False, error="Batch rejected: panic state active")]

    # Validate all order amounts
    for order in orders:
        amt = order.get("usd_amount", 0)
        if not isinstance(amt, (int, float)) or amt <= 0:
            return [OrderResult(success=False, error=f"Invalid usd_amount in batch: {amt}")]
    
    if len(orders) > 10:
        manager.logger.warning("Batch orders limited to 10, splitting...")
        results = []
        for i in range(0, len(orders), 10):
            results.extend(batch_market_orders(manager, orders[i:i+10]))
        return results
    
    batch_orders = []
    results_skipped: list[OrderResult] = []
    for order in orders:
        symbol = order["symbol"]
        price = manager.get_price(symbol)
        qty = inst.calculate_qty(manager, symbol, order["usd_amount"], price)

        if qty <= 0:
            manager.logger.warning("Batch order skipped: qty=%s for %s (usd_amount=%s)", qty, symbol, order['usd_amount'])
            results_skipped.append(OrderResult(success=False, error=f"Calculated qty <= 0 for {symbol}"))
            continue

        batch_order = {"symbol": symbol, "side": order["side"], "orderType": "Market", "qty": str(qty)}
        if order.get("take_profit"):
            batch_order["takeProfit"] = str(order["take_profit"])
        if order.get("stop_loss"):
            batch_order["stopLoss"] = str(order["stop_loss"])
        batch_orders.append(batch_order)

    if not batch_orders:
        return results_skipped
    
    try:
        result = manager.bybit.batch_create_orders(batch_orders)
        
        results = []
        batch_list = result.get("list", []) if isinstance(result, dict) else []
        for item in batch_list:
            code = item.get("code")
            order_id = item.get("orderId", "")
            is_success = (code == 0 or code is None) and bool(order_id)
            results.append(OrderResult(
                success=is_success, order_id=order_id,
                order_link_id=item.get("orderLinkId"), symbol=item.get("symbol"),
                order_type="Market", error=item.get("msg") if not is_success else None,
            ))
        
        manager.logger.info("Batch created %s/%s market orders", sum(1 for r in results if r.success), len(results))
        return results_skipped + results
        
    except Exception as e:
        manager.logger.error("Batch market orders failed: %s", e)
        return [OrderResult(success=False, error=str(e))]


def batch_limit_orders(
    manager: "ExchangeManager",
    orders: list[dict[str, Any]],
) -> list["OrderResult"]:
    """Execute multiple limit orders in a batch."""
    from .exchange_manager import OrderResult
    from . import exchange_instruments as inst

    # Safety: check panic state before batch execution
    from .safety import get_panic_state
    if get_panic_state().is_triggered:
        return [OrderResult(success=False, error="Batch rejected: panic state active")]

    # Validate all order amounts
    for order in orders:
        amt = order.get("usd_amount", 0)
        if not isinstance(amt, (int, float)) or amt <= 0:
            return [OrderResult(success=False, error=f"Invalid usd_amount in batch: {amt}")]
    
    if len(orders) > 10:
        manager.logger.warning("Batch orders limited to 10, splitting...")
        results = []
        for i in range(0, len(orders), 10):
            results.extend(batch_limit_orders(manager, orders[i:i+10]))
        return results
    
    batch_orders = []
    results_skipped: list[OrderResult] = []
    for order in orders:
        symbol = order["symbol"]
        price = inst.round_price(manager, symbol, order["price"])
        qty = inst.calculate_qty(manager, symbol, order["usd_amount"], price)

        if qty <= 0:
            manager.logger.warning("Batch limit order skipped: qty=%s for %s (usd_amount=%s)", qty, symbol, order['usd_amount'])
            results_skipped.append(OrderResult(success=False, error=f"Calculated qty <= 0 for {symbol}"))
            continue
        
        batch_order = {
            "symbol": symbol, "side": order["side"], "orderType": "Limit",
            "qty": str(qty), "price": str(price),
            "timeInForce": order.get("time_in_force", "GTC"),
        }
        if order.get("take_profit"):
            batch_order["takeProfit"] = str(order["take_profit"])
        if order.get("stop_loss"):
            batch_order["stopLoss"] = str(order["stop_loss"])
        if order.get("reduce_only"):
            batch_order["reduceOnly"] = True
        batch_orders.append(batch_order)
    
    if not batch_orders:
        return results_skipped

    try:
        result = manager.bybit.batch_create_orders(batch_orders)

        results = []
        batch_list = result.get("list", []) if isinstance(result, dict) else []
        for item in batch_list:
            code = item.get("code")
            order_id = item.get("orderId", "")
            is_success = (code == 0 or code is None) and bool(order_id)
            results.append(OrderResult(
                success=is_success, order_id=order_id,
                order_link_id=item.get("orderLinkId"), symbol=item.get("symbol"),
                order_type="Limit", error=item.get("msg") if not is_success else None,
            ))

        manager.logger.info("Batch created %s/%s limit orders", sum(1 for r in results if r.success), len(results))
        return results_skipped + results

    except Exception as e:
        manager.logger.error("Batch limit orders failed: %s", e)
        return results_skipped + [OrderResult(success=False, error=str(e))]


def batch_cancel_orders(
    manager: "ExchangeManager",
    orders: list[dict[str, str]],
) -> list[bool]:
    """Cancel multiple orders in a batch."""
    if len(orders) > 10:
        results = []
        for i in range(0, len(orders), 10):
            results.extend(batch_cancel_orders(manager, orders[i:i+10]))
        return results
    
    try:
        result = manager.bybit.batch_cancel_orders(orders)
        results = [item.get("code") == 0 for item in result.get("list", [])]
        manager.logger.info("Batch cancelled %s/%s orders", sum(results), len(results))
        return results
    except Exception as e:
        manager.logger.error("Batch cancel failed: %s", e)
        return [False] * len(orders)


def batch_amend_orders(
    manager: "ExchangeManager",
    orders: list[dict[str, Any]],
) -> list[bool]:
    """Amend multiple orders in a batch."""
    from . import exchange_instruments as inst

    if len(orders) > 10:
        results = []
        for i in range(0, len(orders), 10):
            results.extend(batch_amend_orders(manager, orders[i:i+10]))
        return results
    
    formatted_orders = []
    for order in orders:
        formatted = {k: v for k, v in order.items()}
        if "price" in formatted:
            formatted["price"] = str(inst.round_price(manager, order["symbol"], order["price"]))
        if "qty" in formatted:
            formatted["qty"] = str(order["qty"])
        formatted_orders.append(formatted)
    
    try:
        result = manager.bybit.batch_amend_orders(formatted_orders)
        results = [item.get("code") == 0 for item in result.get("list", [])]
        manager.logger.info("Batch amended %s/%s orders", sum(results), len(results))
        return results
    except Exception as e:
        manager.logger.error("Batch amend failed: %s", e)
        return [False] * len(orders)

