"""
Stop/conditional order methods for ExchangeManager.

Handles:
- Stop market orders
- Stop limit orders
- Conditional orders (for split TPs)
"""

from typing import Any, TYPE_CHECKING
from decimal import Decimal, ROUND_DOWN

from ..exchanges.bybit_client import BybitAPIError

if TYPE_CHECKING:
    from .exchange_manager import ExchangeManager, OrderResult, TriggerDirection


def stop_market_buy(
    manager: "ExchangeManager",
    symbol: str,
    usd_amount: float,
    trigger_price: float,
    trigger_direction: int = 1,
    trigger_by: str = "LastPrice",
    reduce_only: bool = False,
    order_link_id: str = None,
) -> "OrderResult":
    """Place a conditional market buy order (triggers at price)."""
    from .exchange_manager import OrderResult
    from . import exchange_instruments as inst
    
    try:
        manager._validate_trading_operation()
        
        price = manager.get_price(symbol)
        trigger_price = inst.round_price(manager, symbol, trigger_price)
        qty = inst.calculate_qty(manager, symbol, usd_amount, price)
        
        if qty <= 0:
            return OrderResult(success=False, error=f"Order size too small for {symbol}")
        
        result = manager.bybit.session.place_order(
            category="linear", symbol=symbol, side="Buy", orderType="Market",
            qty=str(qty), triggerPrice=str(trigger_price),
            triggerDirection=trigger_direction, triggerBy=trigger_by,
            reduceOnly=reduce_only, orderLinkId=order_link_id,
        )
        
        result_data = result[0].get("result", {}) if isinstance(result, tuple) else result.get("result", {})
        
        manager.logger.trade("STOP_ORDER_PLACED", symbol=symbol, side="BUY",
                            size=usd_amount, trigger=trigger_price, qty=qty, type="market")
        
        return OrderResult(
            success=True, order_id=result_data.get("orderId"),
            order_link_id=result_data.get("orderLinkId"), symbol=symbol,
            side="Buy", order_type="Market", qty=qty,
            trigger_price=trigger_price, reduce_only=reduce_only,
            raw_response=result_data,
        )
        
    except BybitAPIError as e:
        manager.logger.error(f"Stop market buy failed: {e}")
        return OrderResult(success=False, error=str(e))
    except Exception as e:
        manager.logger.error(f"Stop market buy error: {e}")
        return OrderResult(success=False, error=str(e))


def stop_market_sell(
    manager: "ExchangeManager",
    symbol: str,
    usd_amount: float,
    trigger_price: float,
    trigger_direction: int = 2,
    trigger_by: str = "LastPrice",
    reduce_only: bool = False,
    order_link_id: str = None,
) -> "OrderResult":
    """Place a conditional market sell order (triggers at price)."""
    from .exchange_manager import OrderResult
    from . import exchange_instruments as inst
    
    try:
        manager._validate_trading_operation()
        
        price = manager.get_price(symbol)
        trigger_price = inst.round_price(manager, symbol, trigger_price)
        qty = inst.calculate_qty(manager, symbol, usd_amount, price)
        
        if qty <= 0:
            return OrderResult(success=False, error=f"Order size too small for {symbol}")
        
        result = manager.bybit.session.place_order(
            category="linear", symbol=symbol, side="Sell", orderType="Market",
            qty=str(qty), triggerPrice=str(trigger_price),
            triggerDirection=trigger_direction, triggerBy=trigger_by,
            reduceOnly=reduce_only, orderLinkId=order_link_id,
        )
        
        result_data = result[0].get("result", {}) if isinstance(result, tuple) else result.get("result", {})
        
        manager.logger.trade("STOP_ORDER_PLACED", symbol=symbol, side="SELL",
                            size=usd_amount, trigger=trigger_price, qty=qty, type="market")
        
        return OrderResult(
            success=True, order_id=result_data.get("orderId"),
            order_link_id=result_data.get("orderLinkId"), symbol=symbol,
            side="Sell", order_type="Market", qty=qty,
            trigger_price=trigger_price, reduce_only=reduce_only,
            raw_response=result_data,
        )
        
    except BybitAPIError as e:
        manager.logger.error(f"Stop market sell failed: {e}")
        return OrderResult(success=False, error=str(e))
    except Exception as e:
        manager.logger.error(f"Stop market sell error: {e}")
        return OrderResult(success=False, error=str(e))


def stop_limit_buy(
    manager: "ExchangeManager",
    symbol: str,
    usd_amount: float,
    trigger_price: float,
    limit_price: float,
    trigger_direction: int = 1,
    trigger_by: str = "LastPrice",
    time_in_force: str = "GTC",
    reduce_only: bool = False,
    order_link_id: str = None,
) -> "OrderResult":
    """Place a conditional limit buy order."""
    from .exchange_manager import OrderResult
    from . import exchange_instruments as inst
    
    try:
        manager._validate_trading_operation()
        
        trigger_price = inst.round_price(manager, symbol, trigger_price)
        limit_price = inst.round_price(manager, symbol, limit_price)
        qty = inst.calculate_qty(manager, symbol, usd_amount, limit_price)
        
        if qty <= 0:
            return OrderResult(success=False, error=f"Order size too small for {symbol}")
        
        result = manager.bybit.session.place_order(
            category="linear", symbol=symbol, side="Buy", orderType="Limit",
            qty=str(qty), price=str(limit_price), triggerPrice=str(trigger_price),
            triggerDirection=trigger_direction, triggerBy=trigger_by,
            timeInForce=time_in_force, reduceOnly=reduce_only, orderLinkId=order_link_id,
        )
        
        result_data = result[0].get("result", {}) if isinstance(result, tuple) else result.get("result", {})
        
        manager.logger.trade("STOP_LIMIT_ORDER_PLACED", symbol=symbol, side="BUY",
                            size=usd_amount, trigger=trigger_price, limit=limit_price, qty=qty)
        
        return OrderResult(
            success=True, order_id=result_data.get("orderId"),
            order_link_id=result_data.get("orderLinkId"), symbol=symbol,
            side="Buy", order_type="Limit", qty=qty, price=limit_price,
            trigger_price=trigger_price, time_in_force=time_in_force,
            reduce_only=reduce_only, raw_response=result_data,
        )
        
    except BybitAPIError as e:
        manager.logger.error(f"Stop limit buy failed: {e}")
        return OrderResult(success=False, error=str(e))
    except Exception as e:
        manager.logger.error(f"Stop limit buy error: {e}")
        return OrderResult(success=False, error=str(e))


def stop_limit_sell(
    manager: "ExchangeManager",
    symbol: str,
    usd_amount: float,
    trigger_price: float,
    limit_price: float,
    trigger_direction: int = 2,
    trigger_by: str = "LastPrice",
    time_in_force: str = "GTC",
    reduce_only: bool = False,
    order_link_id: str = None,
) -> "OrderResult":
    """Place a conditional limit sell order."""
    from .exchange_manager import OrderResult
    from . import exchange_instruments as inst
    
    try:
        manager._validate_trading_operation()
        
        trigger_price = inst.round_price(manager, symbol, trigger_price)
        limit_price = inst.round_price(manager, symbol, limit_price)
        qty = inst.calculate_qty(manager, symbol, usd_amount, limit_price)
        
        if qty <= 0:
            return OrderResult(success=False, error=f"Order size too small for {symbol}")
        
        result = manager.bybit.session.place_order(
            category="linear", symbol=symbol, side="Sell", orderType="Limit",
            qty=str(qty), price=str(limit_price), triggerPrice=str(trigger_price),
            triggerDirection=trigger_direction, triggerBy=trigger_by,
            timeInForce=time_in_force, reduceOnly=reduce_only, orderLinkId=order_link_id,
        )
        
        result_data = result[0].get("result", {}) if isinstance(result, tuple) else result.get("result", {})
        
        manager.logger.trade("STOP_LIMIT_ORDER_PLACED", symbol=symbol, side="SELL",
                            size=usd_amount, trigger=trigger_price, limit=limit_price, qty=qty)
        
        return OrderResult(
            success=True, order_id=result_data.get("orderId"),
            order_link_id=result_data.get("orderLinkId"), symbol=symbol,
            side="Sell", order_type="Limit", qty=qty, price=limit_price,
            trigger_price=trigger_price, time_in_force=time_in_force,
            reduce_only=reduce_only, raw_response=result_data,
        )
        
    except BybitAPIError as e:
        manager.logger.error(f"Stop limit sell failed: {e}")
        return OrderResult(success=False, error=str(e))
    except Exception as e:
        manager.logger.error(f"Stop limit sell error: {e}")
        return OrderResult(success=False, error=str(e))


def create_conditional_order(
    manager: "ExchangeManager",
    symbol: str,
    side: str,
    qty: float,
    trigger_price: float,
    trigger_direction: "TriggerDirection" = None,
    order_type: str = "Market",
    price: float = None,
    reduce_only: bool = True,
    order_link_id: str = None,
) -> "OrderResult":
    """Create a conditional (trigger) order - used for split take profits."""
    from .exchange_manager import OrderResult, TriggerDirection
    
    try:
        manager._validate_trading_operation()
        
        if trigger_direction is None:
            current_price = manager.get_price(symbol)
            trigger_direction = TriggerDirection.RISE if trigger_price > current_price else TriggerDirection.FALL
        
        result = manager.bybit.create_conditional_order(
            symbol=symbol, side=side, qty=str(qty), trigger_price=str(trigger_price),
            trigger_direction=trigger_direction.value if isinstance(trigger_direction, TriggerDirection) else trigger_direction,
            order_type=order_type, price=str(price) if price else None,
            reduce_only=reduce_only, order_link_id=order_link_id,
        )
        
        manager.logger.info(f"Conditional order created: {symbol} {side} {qty} @ trigger ${trigger_price}")
        
        return OrderResult(
            success=True, order_id=result.get("orderId"),
            order_link_id=result.get("orderLinkId"), symbol=symbol,
            side=side, order_type=order_type, qty=qty,
            trigger_price=trigger_price, reduce_only=reduce_only,
            raw_response=result,
        )
        
    except BybitAPIError as e:
        manager.logger.error(f"Conditional order failed: {e}")
        return OrderResult(success=False, error=str(e))
    except Exception as e:
        manager.logger.error(f"Conditional order error: {e}")
        return OrderResult(success=False, error=str(e))


def open_position_with_rr(
    manager: "ExchangeManager",
    symbol: str,
    side: str,
    margin_usd: float,
    leverage: int,
    stop_loss_roi_pct: float,
    take_profits: list[dict[str, float]],
) -> dict[str, Any]:
    """Open a position with RR-based stop loss and multiple take profits."""
    from .exchange_manager import TriggerDirection
    from . import exchange_instruments as inst
    from . import exchange_orders_market as market
    import time
    
    result = {"success": False, "position_order": None, "tp_orders": [], "levels": {}, "error": None}
    
    try:
        try:
            manager.set_leverage(symbol, leverage)
        except Exception as e:
            if "not modified" not in str(e).lower():
                manager.logger.warning(f"Leverage set warning: {e}")
        
        entry_price = manager.get_price(symbol)
        is_long = side == "Buy"
        
        notional_usd = margin_usd * leverage
        qty = inst.calculate_qty(manager, symbol, notional_usd, entry_price)
        
        if qty <= 0:
            result["error"] = f"Order size too small for {symbol}"
            return result
        
        # Calculate stop loss price
        sl_price_pct = stop_loss_roi_pct / leverage / 100
        risk_distance = entry_price * sl_price_pct
        precision = inst.get_price_precision(manager, symbol)
        stop_loss = round(entry_price - risk_distance if is_long else entry_price + risk_distance, precision)
        
        # Calculate TPs
        tp_orders_config = []
        remaining_qty = qty
        close_side = "Sell" if is_long else "Buy"
        trigger_direction = TriggerDirection.RISE if is_long else TriggerDirection.FALL
        
        for i, tp in enumerate(take_profits):
            tp_roi_pct = stop_loss_roi_pct * tp["rr"]
            tp_price_pct = tp_roi_pct / leverage / 100
            tp_distance = entry_price * tp_price_pct
            tp_price = round(entry_price + tp_distance if is_long else entry_price - tp_distance, precision)
            
            is_last = (i == len(take_profits) - 1)
            if is_last:
                tp_qty = remaining_qty
            else:
                tp_qty = qty * (tp["close_pct"] / 100)
                info = inst.get_instrument_info(manager, symbol)
                qty_step = float(info.get("lotSizeFilter", {}).get("qtyStep", 0.001))
                tp_qty = float(Decimal(str(tp_qty)).quantize(Decimal(str(qty_step)), rounding=ROUND_DOWN))
                remaining_qty -= tp_qty
            
            tp_orders_config.append({"price": tp_price, "qty": tp_qty, "rr": tp["rr"], "close_pct": tp["close_pct"]})
        
        result["levels"] = {
            "entry": entry_price, "stop_loss": stop_loss, "take_profits": tp_orders_config,
            "qty": qty, "notional_usd": notional_usd, "margin_usd": margin_usd, "leverage": leverage,
        }
        
        # Open position
        position_result = (market.market_buy_with_tpsl if is_long else market.market_sell_with_tpsl)(
            manager, symbol=symbol, usd_amount=notional_usd, stop_loss=stop_loss,
        )
        result["position_order"] = position_result
        
        if not position_result.success:
            result["error"] = f"Failed to open position: {position_result.error}"
            return result
        
        # Place TPs
        for i, tp_config in enumerate(tp_orders_config):
            tp_result = create_conditional_order(
                manager, symbol=symbol, side=close_side, qty=tp_config["qty"],
                trigger_price=tp_config["price"], trigger_direction=trigger_direction,
                order_type="Market", reduce_only=True,
                order_link_id=f"TP{i+1}_{symbol}_{int(time.time())}",
            )
            result["tp_orders"].append(tp_result)
            if not tp_result.success:
                manager.logger.warning(f"TP{i+1} order failed: {tp_result.error}")
        
        result["success"] = True
        manager.logger.info(f"Position opened with RR: {symbol} {side} ${margin_usd} @ {leverage}x, SL={stop_loss}, {len(result['tp_orders'])} TPs")
        return result
        
    except Exception as e:
        result["error"] = str(e)
        manager.logger.error(f"Open position with RR failed: {e}")
        return result

