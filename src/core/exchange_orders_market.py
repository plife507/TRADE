"""
Market order methods for ExchangeManager.

Handles:
- Market buy/sell orders
- Market orders with TP/SL
"""

from typing import TYPE_CHECKING

from ..exchanges.bybit_client import BybitAPIError
from . import exchange_instruments as inst

if TYPE_CHECKING:
    from .exchange_manager import ExchangeManager, OrderResult


def _extract_fill_price(result: dict, fallback_price: float) -> float:
    """
    Extract actual fill price from Bybit order response.

    Bybit returns avgPrice for filled market orders.
    Falls back to pre-order price if avgPrice not available.

    Args:
        result: Raw Bybit API response
        fallback_price: Pre-order price to use if avgPrice missing

    Returns:
        Actual fill price (avgPrice) or fallback price
    """
    try:
        avg_price = result.get("avgPrice")
        if avg_price:
            parsed = float(avg_price)
            if parsed > 0:
                return parsed
            # avgPrice=0 means order not yet filled — use fallback
    except (TypeError, ValueError):
        pass
    import logging
    logging.getLogger(__name__).warning(
        f"avgPrice missing or invalid in order response, using quote price {fallback_price:.4f}"
    )
    return fallback_price


def market_buy(manager: "ExchangeManager", symbol: str, usd_amount: float, reduce_only: bool = False) -> "OrderResult":
    """Place a market buy order."""
    from .exchange_manager import OrderResult
    from . import exchange_websocket as ws

    if usd_amount <= 0:
        return OrderResult(success=False, error=f"Invalid usd_amount: {usd_amount} (must be > 0)")

    try:
        manager._validate_trading_operation()
        ws.ensure_symbol_tracked(manager, symbol)

        quote_price = manager.get_price(symbol)
        qty = inst.calculate_qty(manager, symbol, usd_amount, quote_price)

        result = manager.bybit.create_order(
            symbol=symbol, side="Buy", order_type="Market", qty=qty,
            reduce_only=reduce_only,
        )

        # Use actual fill price from response, fallback to quote price
        fill_price = _extract_fill_price(result, quote_price)

        manager.logger.trade("ORDER_FILLED", symbol=symbol, side="BUY",
                            size=usd_amount, price=fill_price, qty=qty)

        return OrderResult(
            success=True, order_id=result.get("orderId"), symbol=symbol,
            side="Buy", order_type="Market", qty=qty, price=fill_price,
            raw_response=result,
        )

    except inst.OrderSizeError as e:
        manager.logger.warning(str(e))
        return OrderResult(success=False, error=str(e))
    except BybitAPIError as e:
        manager.logger.error(f"Market buy failed: {e}")
        return OrderResult(success=False, error=str(e))
    except Exception as e:
        manager.logger.error(f"Market buy error: {e}")
        return OrderResult(success=False, error=str(e))


def market_sell(manager: "ExchangeManager", symbol: str, usd_amount: float, reduce_only: bool = False) -> "OrderResult":
    """Place a market sell order (short)."""
    from .exchange_manager import OrderResult
    from . import exchange_websocket as ws

    if usd_amount <= 0:
        return OrderResult(success=False, error=f"Invalid usd_amount: {usd_amount} (must be > 0)")

    try:
        manager._validate_trading_operation()
        ws.ensure_symbol_tracked(manager, symbol)

        quote_price = manager.get_price(symbol)
        qty = inst.calculate_qty(manager, symbol, usd_amount, quote_price)

        result = manager.bybit.create_order(
            symbol=symbol, side="Sell", order_type="Market", qty=qty,
            reduce_only=reduce_only,
        )

        # Use actual fill price from response, fallback to quote price
        fill_price = _extract_fill_price(result, quote_price)

        manager.logger.trade("ORDER_FILLED", symbol=symbol, side="SELL",
                            size=usd_amount, price=fill_price, qty=qty)

        return OrderResult(
            success=True, order_id=result.get("orderId"), symbol=symbol,
            side="Sell", order_type="Market", qty=qty, price=fill_price,
            raw_response=result,
        )

    except inst.OrderSizeError as e:
        manager.logger.warning(str(e))
        return OrderResult(success=False, error=str(e))
    except BybitAPIError as e:
        manager.logger.error(f"Market sell failed: {e}")
        return OrderResult(success=False, error=str(e))
    except Exception as e:
        manager.logger.error(f"Market sell error: {e}")
        return OrderResult(success=False, error=str(e))


def market_close(
    manager: "ExchangeManager",
    symbol: str,
    usd_amount: float,
    position_side: str,
) -> "OrderResult":
    """
    Place a market close order with enforced reduce_only=True.

    DATA-007: Dedicated close function that cannot accidentally open a reverse
    position. Always passes reduce_only=True to the exchange.

    Args:
        manager: ExchangeManager instance
        symbol: Trading symbol
        usd_amount: Size to close in USD
        position_side: Current position side ("long" or "short")

    Returns:
        OrderResult with fill details
    """
    close_side = "Sell" if position_side.lower() == "long" else "Buy"
    if close_side == "Buy":
        return market_buy(manager, symbol, usd_amount, reduce_only=True)
    return market_sell(manager, symbol, usd_amount, reduce_only=True)


def market_buy_with_tpsl(
    manager: "ExchangeManager",
    symbol: str,
    usd_amount: float,
    take_profit: float | None = None,
    stop_loss: float | None = None,
    tpsl_mode: str = "Full",
    tp_order_type: str = "Market",
    sl_order_type: str = "Market",
) -> "OrderResult":
    """Place a market buy order with TP/SL."""
    from .exchange_manager import OrderResult
    from . import exchange_websocket as ws

    if usd_amount <= 0:
        return OrderResult(success=False, error=f"Invalid usd_amount: {usd_amount} (must be > 0)")

    try:
        manager._validate_trading_operation()
        ws.ensure_symbol_tracked(manager, symbol)

        quote_price = manager.get_price(symbol)
        qty = inst.calculate_qty(manager, symbol, usd_amount, quote_price)

        result = manager.bybit.create_order(
            symbol=symbol, side="Buy", order_type="Market", qty=qty,
            take_profit=str(take_profit) if take_profit else None,
            stop_loss=str(stop_loss) if stop_loss else None,
            tpsl_mode=tpsl_mode if (take_profit or stop_loss) else None,
            tp_order_type=tp_order_type if take_profit else None,
            sl_order_type=sl_order_type if stop_loss else None,
        )

        # Use actual fill price from response, fallback to quote price
        fill_price = _extract_fill_price(result, quote_price)

        manager.logger.trade("ORDER_FILLED", symbol=symbol, side="BUY",
                            size=usd_amount, price=fill_price, qty=qty,
                            tp=take_profit, sl=stop_loss)

        return OrderResult(
            success=True, order_id=result.get("orderId"),
            order_link_id=result.get("orderLinkId"), symbol=symbol,
            side="Buy", order_type="Market", qty=qty, price=fill_price,
            take_profit=take_profit, stop_loss=stop_loss,
            raw_response=result,
        )

    except inst.OrderSizeError as e:
        manager.logger.warning(str(e))
        return OrderResult(success=False, error=str(e))
    except BybitAPIError as e:
        manager.logger.error(f"Market buy with TP/SL failed: {e}")
        return OrderResult(success=False, error=str(e))
    except Exception as e:
        manager.logger.error(f"Market buy with TP/SL error: {e}")
        return OrderResult(success=False, error=str(e))


def market_sell_with_tpsl(
    manager: "ExchangeManager",
    symbol: str,
    usd_amount: float,
    take_profit: float | None = None,
    stop_loss: float | None = None,
    tpsl_mode: str = "Full",
    tp_order_type: str = "Market",
    sl_order_type: str = "Market",
) -> "OrderResult":
    """Place a market sell order with TP/SL (short)."""
    from .exchange_manager import OrderResult
    from . import exchange_websocket as ws

    if usd_amount <= 0:
        return OrderResult(success=False, error=f"Invalid usd_amount: {usd_amount} (must be > 0)")

    try:
        manager._validate_trading_operation()
        ws.ensure_symbol_tracked(manager, symbol)

        quote_price = manager.get_price(symbol)
        qty = inst.calculate_qty(manager, symbol, usd_amount, quote_price)

        result = manager.bybit.create_order(
            symbol=symbol, side="Sell", order_type="Market", qty=qty,
            take_profit=str(take_profit) if take_profit else None,
            stop_loss=str(stop_loss) if stop_loss else None,
            tpsl_mode=tpsl_mode if (take_profit or stop_loss) else None,
            tp_order_type=tp_order_type if take_profit else None,
            sl_order_type=sl_order_type if stop_loss else None,
        )

        # Use actual fill price from response, fallback to quote price
        fill_price = _extract_fill_price(result, quote_price)

        manager.logger.trade("ORDER_FILLED", symbol=symbol, side="SELL",
                            size=usd_amount, price=fill_price, qty=qty,
                            tp=take_profit, sl=stop_loss)

        return OrderResult(
            success=True, order_id=result.get("orderId"),
            order_link_id=result.get("orderLinkId"), symbol=symbol,
            side="Sell", order_type="Market", qty=qty, price=fill_price,
            take_profit=take_profit, stop_loss=stop_loss,
            raw_response=result,
        )

    except inst.OrderSizeError as e:
        manager.logger.warning(str(e))
        return OrderResult(success=False, error=str(e))
    except BybitAPIError as e:
        manager.logger.error(f"Market sell with TP/SL failed: {e}")
        return OrderResult(success=False, error=str(e))
    except Exception as e:
        manager.logger.error(f"Market sell with TP/SL error: {e}")
        return OrderResult(success=False, error=str(e))

