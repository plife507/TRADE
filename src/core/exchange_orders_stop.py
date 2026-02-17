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
from . import exchange_instruments as inst

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
    order_link_id: str | None = None,
) -> "OrderResult":
    """Place a conditional market buy order (triggers at price)."""
    # Runtime import required: circular dependency (exchange_manager imports this module)
    from .exchange_manager import OrderResult

    try:
        manager._validate_trading_operation()

        price = manager.get_price(symbol)
        trigger_price = inst.round_price(manager, symbol, trigger_price)
        qty = inst.calculate_qty(manager, symbol, usd_amount, price)
        
        result_data = manager.bybit.create_order(
            symbol=symbol, side="Buy", order_type="Market",
            qty=qty, trigger_price=str(trigger_price),
            trigger_direction=trigger_direction, trigger_by=trigger_by,
            reduce_only=reduce_only, order_link_id=order_link_id,
        )
        
        manager.logger.trade("STOP_ORDER_PLACED", symbol=symbol, side="BUY",
                            size=usd_amount, trigger=trigger_price, qty=qty, type="market")
        
        return OrderResult(
            success=True, order_id=result_data.get("orderId"),
            order_link_id=result_data.get("orderLinkId"), symbol=symbol,
            side="Buy", order_type="Market", qty=qty,
            trigger_price=trigger_price, reduce_only=reduce_only,
            raw_response=result_data,
        )
        
    except inst.OrderSizeError as e:
        manager.logger.warning(str(e))
        return OrderResult(success=False, error=str(e))
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
    order_link_id: str | None = None,
) -> "OrderResult":
    """Place a conditional market sell order (triggers at price)."""
    # Runtime import required: circular dependency (exchange_manager imports this module)
    from .exchange_manager import OrderResult

    try:
        manager._validate_trading_operation()

        price = manager.get_price(symbol)
        trigger_price = inst.round_price(manager, symbol, trigger_price)
        qty = inst.calculate_qty(manager, symbol, usd_amount, price)
        
        result_data = manager.bybit.create_order(
            symbol=symbol, side="Sell", order_type="Market",
            qty=qty, trigger_price=str(trigger_price),
            trigger_direction=trigger_direction, trigger_by=trigger_by,
            reduce_only=reduce_only, order_link_id=order_link_id,
        )
        
        manager.logger.trade("STOP_ORDER_PLACED", symbol=symbol, side="SELL",
                            size=usd_amount, trigger=trigger_price, qty=qty, type="market")
        
        return OrderResult(
            success=True, order_id=result_data.get("orderId"),
            order_link_id=result_data.get("orderLinkId"), symbol=symbol,
            side="Sell", order_type="Market", qty=qty,
            trigger_price=trigger_price, reduce_only=reduce_only,
            raw_response=result_data,
        )
        
    except inst.OrderSizeError as e:
        manager.logger.warning(str(e))
        return OrderResult(success=False, error=str(e))
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
    order_link_id: str | None = None,
) -> "OrderResult":
    """Place a conditional limit buy order."""
    from .exchange_manager import OrderResult

    try:
        manager._validate_trading_operation()

        trigger_price = inst.round_price(manager, symbol, trigger_price)
        limit_price = inst.round_price(manager, symbol, limit_price)
        qty = inst.calculate_qty(manager, symbol, usd_amount, limit_price)
        
        result_data = manager.bybit.create_order(
            symbol=symbol, side="Buy", order_type="Limit",
            qty=qty, price=limit_price, trigger_price=str(trigger_price),
            trigger_direction=trigger_direction, trigger_by=trigger_by,
            time_in_force=time_in_force, reduce_only=reduce_only, order_link_id=order_link_id,
        )
        
        manager.logger.trade("STOP_LIMIT_ORDER_PLACED", symbol=symbol, side="BUY",
                            size=usd_amount, trigger=trigger_price, limit=limit_price, qty=qty)
        
        return OrderResult(
            success=True, order_id=result_data.get("orderId"),
            order_link_id=result_data.get("orderLinkId"), symbol=symbol,
            side="Buy", order_type="Limit", qty=qty, price=limit_price,
            trigger_price=trigger_price, time_in_force=time_in_force,
            reduce_only=reduce_only, raw_response=result_data,
        )
        
    except inst.OrderSizeError as e:
        manager.logger.warning(str(e))
        return OrderResult(success=False, error=str(e))
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
    order_link_id: str | None = None,
) -> "OrderResult":
    """Place a conditional limit sell order."""
    from .exchange_manager import OrderResult

    try:
        manager._validate_trading_operation()

        trigger_price = inst.round_price(manager, symbol, trigger_price)
        limit_price = inst.round_price(manager, symbol, limit_price)
        qty = inst.calculate_qty(manager, symbol, usd_amount, limit_price)
        
        result_data = manager.bybit.create_order(
            symbol=symbol, side="Sell", order_type="Limit",
            qty=qty, price=limit_price, trigger_price=str(trigger_price),
            trigger_direction=trigger_direction, trigger_by=trigger_by,
            time_in_force=time_in_force, reduce_only=reduce_only, order_link_id=order_link_id,
        )
        
        manager.logger.trade("STOP_LIMIT_ORDER_PLACED", symbol=symbol, side="SELL",
                            size=usd_amount, trigger=trigger_price, limit=limit_price, qty=qty)
        
        return OrderResult(
            success=True, order_id=result_data.get("orderId"),
            order_link_id=result_data.get("orderLinkId"), symbol=symbol,
            side="Sell", order_type="Limit", qty=qty, price=limit_price,
            trigger_price=trigger_price, time_in_force=time_in_force,
            reduce_only=reduce_only, raw_response=result_data,
        )
        
    except inst.OrderSizeError as e:
        manager.logger.warning(str(e))
        return OrderResult(success=False, error=str(e))
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
    trigger_direction: "TriggerDirection | None" = None,
    order_type: str = "Market",
    price: float | None = None,
    reduce_only: bool = True,
    order_link_id: str | None = None,
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
    from . import exchange_orders_market as market
    import time

    result = {"success": False, "position_order": None, "tp_orders": [], "levels": {}, "error": None}

    try:
        manager.set_leverage(symbol, leverage)

        entry_price = manager.get_price(symbol)
        is_long = side == "Buy"

        notional_usd = margin_usd * leverage
        # OrderSizeError from calculate_qty will be caught and detailed message used
        qty = inst.calculate_qty(manager, symbol, notional_usd, entry_price)
        
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

        # Recalculate SL/TP from actual fill price (not pre-trade quote)
        actual_fill = getattr(position_result, 'price', None) or entry_price
        if actual_fill != entry_price:
            manager.logger.info(
                f"Fill price deviation: quoted={entry_price:.4f} actual={actual_fill:.4f}, "
                "recalculating SL/TP from actual fill"
            )
            risk_distance_actual = actual_fill * sl_price_pct
            stop_loss = round(actual_fill - risk_distance_actual if is_long else actual_fill + risk_distance_actual, precision)
            # Recalculate TP levels from actual fill
            for tp_cfg in tp_orders_config:
                tp_roi_pct = stop_loss_roi_pct * tp_cfg["rr"]
                tp_price_pct_actual = tp_roi_pct / leverage / 100
                tp_distance_actual = actual_fill * tp_price_pct_actual
                tp_cfg["price"] = round(actual_fill + tp_distance_actual if is_long else actual_fill - tp_distance_actual, precision)
            result["levels"]["entry"] = actual_fill
            result["levels"]["stop_loss"] = stop_loss
            result["levels"]["take_profits"] = tp_orders_config

        # G0.5: Explicit SL order as backup (TPSL mode may not be reliable)
        # Place SL conditional order immediately after entry for atomicity
        sl_trigger_direction = TriggerDirection.FALL if is_long else TriggerDirection.RISE
        sl_result = create_conditional_order(
            manager,
            symbol=symbol,
            side=close_side,
            qty=qty,
            trigger_price=stop_loss,
            trigger_direction=sl_trigger_direction,
            order_type="Market",
            reduce_only=True,
            order_link_id=f"SL_{symbol}_{int(time.time())}",
        )
        result["sl_order"] = sl_result

        if not sl_result.success:
            manager.logger.error(
                f"CRITICAL: SL order failed! Position may be unprotected: {sl_result.error}"
            )
            result["sl_warning"] = sl_result.error

        # Verify SL order exists on exchange
        if sl_result.success:
            import time as _time
            _time.sleep(0.5)  # Brief delay for order to appear
            try:
                open_orders = manager.get_open_orders(symbol=symbol)
                sl_found = any(
                    o.order_link_id and o.order_link_id.startswith("SL_")
                    for o in open_orders
                )
                if not sl_found:
                    manager.logger.error("SL order not found on exchange after placement! Retrying...")
                    sl_result = create_conditional_order(
                        manager, symbol=symbol, side=close_side, qty=qty,
                        trigger_price=stop_loss, trigger_direction=sl_trigger_direction,
                        order_type="Market", reduce_only=True,
                        order_link_id=f"SL_{symbol}_{int(time.time()) + 1}",
                    )
                    result["sl_order"] = sl_result
                    if not sl_result.success:
                        manager.logger.error("CRITICAL: SL retry also failed! Closing position as emergency measure.")
                        try:
                            manager.close_position(symbol)
                        except Exception as close_err:
                            manager.logger.error(
                                f"EMERGENCY: close_position also failed: {close_err}. "
                                "Triggering panic to halt all trading."
                            )
                            from .safety import get_panic_state
                            get_panic_state().trigger(
                                f"SL + emergency close both failed for {symbol}"
                            )
            except Exception as e:
                manager.logger.error(f"SL verification failed: {e}")

        # Place TPs only if SL succeeded (no orphan TPs for a closed/unprotected position)
        if sl_result.success:
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

        # Success requires entry + SL both placed
        result["success"] = position_result.success and sl_result.success
        manager.logger.info(f"Position opened with RR: {symbol} {side} ${margin_usd} @ {leverage}x, SL={stop_loss}, {len(result['tp_orders'])} TPs")
        return result
        
    except Exception as e:
        result["error"] = str(e)
        manager.logger.error(f"Open position with RR failed: {e}")
        return result

