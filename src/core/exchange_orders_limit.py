"""
Limit order methods for ExchangeManager.

Handles:
- Limit buy/sell orders
- Limit orders with TP/SL
"""

from typing import TYPE_CHECKING

from ..exchanges.bybit_client import BybitAPIError
from . import exchange_instruments as inst

if TYPE_CHECKING:
    from .exchange_manager import ExchangeManager, OrderResult


def limit_buy(
    manager: "ExchangeManager",
    symbol: str,
    usd_amount: float,
    price: float,
    time_in_force: str = "GTC",
    reduce_only: bool = False,
    order_link_id: str | None = None,
) -> "OrderResult":
    """Place a limit buy order."""
    from .exchange_manager import OrderResult
    from . import exchange_websocket as ws

    try:
        manager._validate_trading_operation()
        ws.ensure_symbol_tracked(manager, symbol)

        price = inst.round_price(manager, symbol, price)
        qty = inst.calculate_qty(manager, symbol, usd_amount, price)
        
        result = manager.bybit.create_order(
            symbol=symbol, side="Buy", order_type="Limit", qty=qty,
            price=str(price), time_in_force=time_in_force,
            reduce_only=reduce_only, order_link_id=order_link_id,
        )
        
        manager.logger.trade("LIMIT_ORDER_PLACED", symbol=symbol, side="BUY",
                            size=usd_amount, price=price, qty=qty, tif=time_in_force)
        
        return OrderResult(
            success=True, order_id=result.get("orderId"),
            order_link_id=result.get("orderLinkId"), symbol=symbol,
            side="Buy", order_type="Limit", qty=qty, price=price,
            time_in_force=time_in_force, reduce_only=reduce_only,
            raw_response=result,
        )
        
    except inst.OrderSizeError as e:
        manager.logger.warning(str(e))
        return OrderResult(success=False, error=str(e))
    except BybitAPIError as e:
        manager.logger.error(f"Limit buy failed: {e}")
        return OrderResult(success=False, error=str(e))
    except Exception as e:
        manager.logger.error(f"Limit buy error: {e}")
        return OrderResult(success=False, error=str(e))


def limit_sell(
    manager: "ExchangeManager",
    symbol: str,
    usd_amount: float,
    price: float,
    time_in_force: str = "GTC",
    reduce_only: bool = False,
    order_link_id: str | None = None,
) -> "OrderResult":
    """Place a limit sell order (short or close long)."""
    from .exchange_manager import OrderResult
    from . import exchange_websocket as ws

    try:
        manager._validate_trading_operation()
        ws.ensure_symbol_tracked(manager, symbol)

        price = inst.round_price(manager, symbol, price)
        qty = inst.calculate_qty(manager, symbol, usd_amount, price)
        
        result = manager.bybit.create_order(
            symbol=symbol, side="Sell", order_type="Limit", qty=qty,
            price=str(price), time_in_force=time_in_force,
            reduce_only=reduce_only, order_link_id=order_link_id,
        )
        
        manager.logger.trade("LIMIT_ORDER_PLACED", symbol=symbol, side="SELL",
                            size=usd_amount, price=price, qty=qty, tif=time_in_force)
        
        return OrderResult(
            success=True, order_id=result.get("orderId"),
            order_link_id=result.get("orderLinkId"), symbol=symbol,
            side="Sell", order_type="Limit", qty=qty, price=price,
            time_in_force=time_in_force, reduce_only=reduce_only,
            raw_response=result,
        )
        
    except inst.OrderSizeError as e:
        manager.logger.warning(str(e))
        return OrderResult(success=False, error=str(e))
    except BybitAPIError as e:
        manager.logger.error(f"Limit sell failed: {e}")
        return OrderResult(success=False, error=str(e))
    except Exception as e:
        manager.logger.error(f"Limit sell error: {e}")
        return OrderResult(success=False, error=str(e))


def limit_buy_with_tpsl(
    manager: "ExchangeManager",
    symbol: str,
    usd_amount: float,
    price: float,
    take_profit: float | None = None,
    stop_loss: float | None = None,
    time_in_force: str = "GTC",
    tpsl_mode: str = "Full",
    tp_order_type: str = "Market",
    sl_order_type: str = "Market",
    order_link_id: str | None = None,
) -> "OrderResult":
    """Place a limit buy order with TP/SL."""
    from .exchange_manager import OrderResult

    try:
        manager._validate_trading_operation()

        price = inst.round_price(manager, symbol, price)
        qty = inst.calculate_qty(manager, symbol, usd_amount, price)
        
        result = manager.bybit.create_order(
            symbol=symbol, side="Buy", order_type="Limit", qty=qty,
            price=str(price), time_in_force=time_in_force,
            take_profit=str(take_profit) if take_profit else None,
            stop_loss=str(stop_loss) if stop_loss else None,
            tpsl_mode=tpsl_mode if (take_profit or stop_loss) else None,
            tp_order_type=tp_order_type if take_profit else None,
            sl_order_type=sl_order_type if stop_loss else None,
            order_link_id=order_link_id,
        )
        
        manager.logger.trade("LIMIT_ORDER_PLACED", symbol=symbol, side="BUY",
                            size=usd_amount, price=price, qty=qty,
                            tp=take_profit, sl=stop_loss)
        
        return OrderResult(
            success=True, order_id=result.get("orderId"),
            order_link_id=result.get("orderLinkId"), symbol=symbol,
            side="Buy", order_type="Limit", qty=qty, price=price,
            time_in_force=time_in_force, take_profit=take_profit,
            stop_loss=stop_loss, raw_response=result,
        )
        
    except inst.OrderSizeError as e:
        manager.logger.warning(str(e))
        return OrderResult(success=False, error=str(e))
    except BybitAPIError as e:
        manager.logger.error(f"Limit buy with TP/SL failed: {e}")
        return OrderResult(success=False, error=str(e))
    except Exception as e:
        manager.logger.error(f"Limit buy with TP/SL error: {e}")
        return OrderResult(success=False, error=str(e))


def limit_sell_with_tpsl(
    manager: "ExchangeManager",
    symbol: str,
    usd_amount: float,
    price: float,
    take_profit: float | None = None,
    stop_loss: float | None = None,
    time_in_force: str = "GTC",
    tpsl_mode: str = "Full",
    tp_order_type: str = "Market",
    sl_order_type: str = "Market",
    order_link_id: str | None = None,
) -> "OrderResult":
    """Place a limit sell order with TP/SL (short)."""
    from .exchange_manager import OrderResult

    try:
        manager._validate_trading_operation()

        price = inst.round_price(manager, symbol, price)
        qty = inst.calculate_qty(manager, symbol, usd_amount, price)
        
        result = manager.bybit.create_order(
            symbol=symbol, side="Sell", order_type="Limit", qty=qty,
            price=str(price), time_in_force=time_in_force,
            take_profit=str(take_profit) if take_profit else None,
            stop_loss=str(stop_loss) if stop_loss else None,
            tpsl_mode=tpsl_mode if (take_profit or stop_loss) else None,
            tp_order_type=tp_order_type if take_profit else None,
            sl_order_type=sl_order_type if stop_loss else None,
            order_link_id=order_link_id,
        )
        
        manager.logger.trade("LIMIT_ORDER_PLACED", symbol=symbol, side="SELL",
                            size=usd_amount, price=price, qty=qty,
                            tp=take_profit, sl=stop_loss)
        
        return OrderResult(
            success=True, order_id=result.get("orderId"),
            order_link_id=result.get("orderLinkId"), symbol=symbol,
            side="Sell", order_type="Limit", qty=qty, price=price,
            time_in_force=time_in_force, take_profit=take_profit,
            stop_loss=stop_loss, raw_response=result,
        )
        
    except inst.OrderSizeError as e:
        manager.logger.warning(str(e))
        return OrderResult(success=False, error=str(e))
    except BybitAPIError as e:
        manager.logger.error(f"Limit sell with TP/SL failed: {e}")
        return OrderResult(success=False, error=str(e))
    except Exception as e:
        manager.logger.error(f"Limit sell with TP/SL error: {e}")
        return OrderResult(success=False, error=str(e))

