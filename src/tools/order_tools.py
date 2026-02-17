"""
Order execution tools for TRADE trading bot.

These tools provide comprehensive order management:
- Market Orders (buy/sell with optional TP/SL)
- Limit Orders (GTC, IOC, FOK, PostOnly)
- Stop Orders (conditional market/limit orders)
- Order Management (amend, cancel, query)
- Batch Orders (multiple orders at once)
- Partial Position Closes

All trading tools accept an optional `trading_env` parameter for agent/orchestrator
use. This parameter VALIDATES the caller's intent against the process config but
does NOT switch environments. If the env doesn't match, the tool returns an error.
"""

from .shared import ToolResult, _get_exchange_manager, validate_trading_env_or_error
from .order_tools_common import (
    validate_order_params,
    validate_symbol,
    execute_order,
    execute_simple_order,
    build_order_data,
)


def set_leverage_tool(symbol: str, leverage: int, trading_env: str | None = None) -> ToolResult:
    """
    Set leverage for a symbol.
    
    Args:
        symbol: Trading symbol (e.g., "BTCUSDT")
        leverage: Leverage value (1-125, capped by risk settings)
        trading_env: Optional trading environment ("demo" or "live") for validation
    
    Returns:
        ToolResult with success status
    """
    if error := validate_trading_env_or_error(trading_env):
        return error
    
    if not symbol or not isinstance(symbol, str):
        return ToolResult(success=False, error="Invalid symbol parameter")
    
    if leverage < 1:
        return ToolResult(success=False, error="Leverage must be at least 1")
    
    try:
        exchange = _get_exchange_manager()
        success = exchange.set_leverage(symbol, leverage)
        
        if success:
            return ToolResult(
                success=True,
                symbol=symbol,
                message=f"Set {symbol} leverage to {leverage}x",
                data={"leverage": leverage},
            )
        else:
            return ToolResult(
                success=False,
                symbol=symbol,
                error="Failed to set leverage",
            )
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Exception setting leverage: {str(e)}",
        )


def market_buy_tool(symbol: str, usd_amount: float, trading_env: str | None = None) -> ToolResult:
    """
    Place a market buy order (open long position).

    Args:
        symbol: Trading symbol
        usd_amount: Position size in USD
        trading_env: Optional trading environment ("demo" or "live") for validation

    Returns:
        ToolResult with order details
    """
    return execute_simple_order(
        exchange_method="market_buy",
        symbol=symbol,
        trading_env=trading_env,
        usd_amount=usd_amount,
        success_message="Buy order filled: {qty} @ {price}",
        error_prefix="placing buy order",
        extra_data={"usd_amount": usd_amount},
    )


def market_sell_tool(symbol: str, usd_amount: float, trading_env: str | None = None) -> ToolResult:
    """
    Place a market sell order (open short position).

    Args:
        symbol: Trading symbol
        usd_amount: Position size in USD
        trading_env: Optional trading environment ("demo" or "live") for validation

    Returns:
        ToolResult with order details
    """
    return execute_simple_order(
        exchange_method="market_sell",
        symbol=symbol,
        trading_env=trading_env,
        usd_amount=usd_amount,
        success_message="Sell order filled: {qty} @ {price}",
        error_prefix="placing sell order",
        extra_data={"usd_amount": usd_amount},
    )


def market_buy_with_tpsl_tool(
    symbol: str,
    usd_amount: float,
    take_profit: float | None = None,
    stop_loss: float | None = None,
    trading_env: str | None = None,
) -> ToolResult:
    """
    Place a market buy order with take profit and/or stop loss.

    Args:
        symbol: Trading symbol
        usd_amount: Position size in USD
        take_profit: Take profit price (optional)
        stop_loss: Stop loss price (optional)
        trading_env: Optional trading environment ("demo" or "live") for validation

    Returns:
        ToolResult with order details
    """
    return execute_simple_order(
        exchange_method="market_buy_with_tpsl",
        symbol=symbol,
        trading_env=trading_env,
        usd_amount=usd_amount,
        success_message="Buy order with TP/SL: {qty} @ {price}",
        error_prefix="placing order",
        extra_data={"usd_amount": usd_amount, "take_profit": take_profit, "stop_loss": stop_loss},
        take_profit=take_profit,
        stop_loss=stop_loss,
    )


def market_sell_with_tpsl_tool(
    symbol: str,
    usd_amount: float,
    take_profit: float | None = None,
    stop_loss: float | None = None,
    trading_env: str | None = None,
) -> ToolResult:
    """
    Place a market sell order with take profit and/or stop loss.

    Args:
        symbol: Trading symbol
        usd_amount: Position size in USD
        take_profit: Take profit price (optional)
        stop_loss: Stop loss price (optional)
        trading_env: Optional trading environment ("demo" or "live") for validation

    Returns:
        ToolResult with order details
    """
    return execute_simple_order(
        exchange_method="market_sell_with_tpsl",
        symbol=symbol,
        trading_env=trading_env,
        usd_amount=usd_amount,
        success_message="Sell order with TP/SL: {qty} @ {price}",
        error_prefix="placing order",
        extra_data={"usd_amount": usd_amount, "take_profit": take_profit, "stop_loss": stop_loss},
        take_profit=take_profit,
        stop_loss=stop_loss,
    )


def cancel_all_orders_tool(symbol: str | None = None, trading_env: str | None = None) -> ToolResult:
    """
    Cancel all open orders, optionally filtered by symbol.
    
    Args:
        symbol: Trading symbol (None for all symbols)
        trading_env: Optional trading environment ("demo" or "live") for validation
    
    Returns:
        ToolResult with cancellation status
    """
    if error := validate_trading_env_or_error(trading_env):
        return error
    
    try:
        exchange = _get_exchange_manager()
        success = exchange.cancel_all_orders(symbol)
        
        scope = symbol if symbol else "all symbols"
        
        if success:
            return ToolResult(
                success=True,
                symbol=symbol,
                message=f"Cancelled all orders for {scope}",
                data={"cancelled": True, "scope": scope},
            )
        else:
            return ToolResult(
                success=False,
                symbol=symbol,
                error=f"Failed to cancel orders for {scope}",
            )
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Exception cancelling orders: {str(e)}",
        )


# ==============================================================================
# Limit Order Tools
# ==============================================================================

def limit_buy_tool(
    symbol: str,
    usd_amount: float,
    price: float,
    time_in_force: str = "GTC",
    reduce_only: bool = False,
    trading_env: str | None = None,
) -> ToolResult:
    """
    Place a limit buy order.

    Args:
        symbol: Trading symbol
        usd_amount: Position size in USD
        price: Limit price
        time_in_force: GTC (Good Till Cancel), IOC (Immediate or Cancel),
                      FOK (Fill or Kill), or PostOnly
        reduce_only: If True, only reduce position (close only)
        trading_env: Optional trading environment ("demo" or "live") for validation

    Returns:
        ToolResult with order details
    """
    return execute_simple_order(
        exchange_method="limit_buy",
        symbol=symbol,
        trading_env=trading_env,
        usd_amount=usd_amount,
        price=price,
        success_message="Limit buy order placed: {qty} @ {price}",
        error_prefix="placing limit buy",
        extra_data={"side": "Buy", "order_type": "Limit", "reduce_only": reduce_only},
        time_in_force=time_in_force,
        reduce_only=reduce_only,
    )


def limit_sell_tool(
    symbol: str,
    usd_amount: float,
    price: float,
    time_in_force: str = "GTC",
    reduce_only: bool = False,
    trading_env: str | None = None,
) -> ToolResult:
    """
    Place a limit sell order.

    Args:
        symbol: Trading symbol
        usd_amount: Position size in USD
        price: Limit price
        time_in_force: GTC, IOC, FOK, or PostOnly
        reduce_only: If True, only reduce position (close only)
        trading_env: Optional trading environment ("demo" or "live") for validation

    Returns:
        ToolResult with order details
    """
    return execute_simple_order(
        exchange_method="limit_sell",
        symbol=symbol,
        trading_env=trading_env,
        usd_amount=usd_amount,
        price=price,
        success_message="Limit sell order placed: {qty} @ {price}",
        error_prefix="placing limit sell",
        extra_data={"side": "Sell", "order_type": "Limit", "reduce_only": reduce_only},
        time_in_force=time_in_force,
        reduce_only=reduce_only,
    )


# ==============================================================================
# Partial Close Tools
# ==============================================================================

def partial_close_position_tool(
    symbol: str,
    close_percent: float,
    price: float | None = None,
    trading_env: str | None = None,
) -> ToolResult:
    """
    Partially close a position by percentage.
    
    Args:
        symbol: Trading symbol
        close_percent: Percentage of position to close (0-100)
        price: Optional limit price (None for market order)
        trading_env: Optional trading environment ("demo" or "live") for validation
    
    Returns:
        ToolResult with close order details
    """
    if error := validate_trading_env_or_error(trading_env):
        return error
    
    if not symbol or not isinstance(symbol, str):
        return ToolResult(success=False, error="Invalid symbol parameter")
    
    if close_percent <= 0 or close_percent > 100:
        return ToolResult(success=False, error="Close percent must be between 0 and 100")
    
    try:
        exchange = _get_exchange_manager()
        position = exchange.get_position(symbol)
        
        if not position or not position.is_open:
            return ToolResult(
                success=False,
                symbol=symbol,
                error=f"No open position for {symbol}",
            )
        
        # Calculate close amount
        close_amount_usd = position.size_usdt * (close_percent / 100.0)
        
        # Determine close side (opposite of position)
        close_side = "Sell" if position.side == "long" else "Buy"
        
        if price:
            # Limit order for partial close
            if close_side == "Sell":
                result = exchange.limit_sell(
                    symbol=symbol,
                    usd_amount=close_amount_usd,
                    price=price,
                    reduce_only=True,
                )
            else:
                result = exchange.limit_buy(
                    symbol=symbol,
                    usd_amount=close_amount_usd,
                    price=price,
                    reduce_only=True,
                )
        else:
            # Market order for partial close
            if close_side == "Sell":
                result = exchange.market_sell(
                    symbol=symbol,
                    usd_amount=close_amount_usd,
                    reduce_only=True,
                )
            else:
                result = exchange.market_buy(
                    symbol=symbol,
                    usd_amount=close_amount_usd,
                    reduce_only=True,
                )
        
        if result.success:
            order_type = "Limit" if price else "Market"
            return ToolResult(
                success=True,
                symbol=symbol,
                message=f"Partially closed {close_percent}% of {symbol} position ({order_type})",
                data={
                    "order_id": result.order_id,
                    "close_percent": close_percent,
                    "close_amount_usd": close_amount_usd,
                    "remaining_size_usdt": position.size_usdt - close_amount_usd,
                    "order_type": order_type,
                    "price": price,
                },
            )
        else:
            return ToolResult(
                success=False,
                symbol=symbol,
                error=result.error or "Failed to partially close position",
            )
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Exception partially closing position: {str(e)}",
        )


# ==============================================================================
# Stop Order Tools (Conditional Orders)
# ==============================================================================

def stop_market_buy_tool(
    symbol: str,
    usd_amount: float,
    trigger_price: float,
    trigger_direction: int = 1,
    trigger_by: str = "LastPrice",
    reduce_only: bool = False,
    trading_env: str | None = None,
) -> ToolResult:
    """
    Place a stop market buy order (triggers when price reaches trigger).

    Use cases:
    - Stop-loss for SHORT positions (trigger when price rises)
    - Breakout entry (buy when price breaks above resistance)

    Args:
        symbol: Trading symbol
        usd_amount: Position size in USD
        trigger_price: Price at which to trigger the order
        trigger_direction: 1=trigger when price RISES to trigger_price
                          2=trigger when price FALLS to trigger_price
        trigger_by: LastPrice, MarkPrice, or IndexPrice
        reduce_only: If True, only reduce position (close only)
        trading_env: Optional trading environment ("demo" or "live") for validation

    Returns:
        ToolResult with order details
    """
    if error := validate_order_params(trading_env, symbol, usd_amount=usd_amount, trigger_price=trigger_price):
        return error

    direction_str = "rises to" if trigger_direction == 1 else "falls to"
    return execute_simple_order(
        exchange_method="stop_market_buy",
        symbol=symbol,
        trading_env=None,  # Already validated
        usd_amount=usd_amount,
        success_message=f"Stop market BUY: triggers when price {direction_str} ${trigger_price:.2f}",
        error_prefix="placing stop market buy",
        extra_data={
            "trigger_price": trigger_price,
            "trigger_direction": trigger_direction,
            "trigger_by": trigger_by,
            "side": "Buy",
            "order_type": "Stop Market",
            "reduce_only": reduce_only,
        },
        trigger_price=trigger_price,
        trigger_direction=trigger_direction,
        trigger_by=trigger_by,
        reduce_only=reduce_only,
    )


def stop_market_sell_tool(
    symbol: str,
    usd_amount: float,
    trigger_price: float,
    trigger_direction: int = 2,
    trigger_by: str = "LastPrice",
    reduce_only: bool = False,
    trading_env: str | None = None,
) -> ToolResult:
    """
    Place a stop market sell order (triggers when price reaches trigger).

    Use cases:
    - Stop-loss for LONG positions (trigger when price falls)
    - Breakdown entry (sell when price breaks below support)

    Args:
        symbol: Trading symbol
        usd_amount: Position size in USD
        trigger_price: Price at which to trigger the order
        trigger_direction: 1=trigger when price RISES to trigger_price
                          2=trigger when price FALLS to trigger_price
        trigger_by: LastPrice, MarkPrice, or IndexPrice
        reduce_only: If True, only reduce position (close only)
        trading_env: Optional trading environment ("demo" or "live") for validation

    Returns:
        ToolResult with order details
    """
    if error := validate_order_params(trading_env, symbol, usd_amount=usd_amount, trigger_price=trigger_price):
        return error

    direction_str = "rises to" if trigger_direction == 1 else "falls to"
    return execute_simple_order(
        exchange_method="stop_market_sell",
        symbol=symbol,
        trading_env=None,  # Already validated
        usd_amount=usd_amount,
        success_message=f"Stop market SELL: triggers when price {direction_str} ${trigger_price:.2f}",
        error_prefix="placing stop market sell",
        extra_data={
            "trigger_price": trigger_price,
            "trigger_direction": trigger_direction,
            "trigger_by": trigger_by,
            "side": "Sell",
            "order_type": "Stop Market",
            "reduce_only": reduce_only,
        },
        trigger_price=trigger_price,
        trigger_direction=trigger_direction,
        trigger_by=trigger_by,
        reduce_only=reduce_only,
    )


def stop_limit_buy_tool(
    symbol: str,
    usd_amount: float,
    trigger_price: float,
    limit_price: float,
    trigger_direction: int = 1,
    trigger_by: str = "LastPrice",
    time_in_force: str = "GTC",
    reduce_only: bool = False,
    trading_env: str | None = None,
) -> ToolResult:
    """
    Place a stop limit buy order (triggers limit order when price reaches trigger).

    When trigger_price is reached, places a limit buy at limit_price.

    Args:
        symbol: Trading symbol
        usd_amount: Position size in USD
        trigger_price: Price at which to trigger the order
        limit_price: Limit price for the triggered order
        trigger_direction: 1=trigger when price RISES, 2=trigger when price FALLS
        trigger_by: LastPrice, MarkPrice, or IndexPrice
        time_in_force: GTC, IOC, FOK, or PostOnly
        reduce_only: If True, only reduce position (close only)
        trading_env: Optional trading environment ("demo" or "live") for validation

    Returns:
        ToolResult with order details
    """
    if error := validate_order_params(
        trading_env, symbol, usd_amount=usd_amount,
        trigger_price=trigger_price, limit_price=limit_price
    ):
        return error

    return execute_simple_order(
        exchange_method="stop_limit_buy",
        symbol=symbol,
        trading_env=None,  # Already validated
        usd_amount=usd_amount,
        success_message=f"Stop limit BUY: triggers at ${trigger_price:.2f}, limit @ ${limit_price:.2f}",
        error_prefix="placing stop limit buy",
        extra_data={
            "trigger_price": trigger_price,
            "limit_price": limit_price,
            "trigger_direction": trigger_direction,
            "side": "Buy",
            "order_type": "Stop Limit",
            "reduce_only": reduce_only,
        },
        trigger_price=trigger_price,
        limit_price=limit_price,
        trigger_direction=trigger_direction,
        trigger_by=trigger_by,
        time_in_force=time_in_force,
        reduce_only=reduce_only,
    )


def stop_limit_sell_tool(
    symbol: str,
    usd_amount: float,
    trigger_price: float,
    limit_price: float,
    trigger_direction: int = 2,
    trigger_by: str = "LastPrice",
    time_in_force: str = "GTC",
    reduce_only: bool = False,
    trading_env: str | None = None,
) -> ToolResult:
    """
    Place a stop limit sell order (triggers limit order when price reaches trigger).

    When trigger_price is reached, places a limit sell at limit_price.

    Args:
        symbol: Trading symbol
        usd_amount: Position size in USD
        trigger_price: Price at which to trigger the order
        limit_price: Limit price for the triggered order
        trigger_direction: 1=trigger when price RISES, 2=trigger when price FALLS
        trigger_by: LastPrice, MarkPrice, or IndexPrice
        time_in_force: GTC, IOC, FOK, or PostOnly
        reduce_only: If True, only reduce position (close only)
        trading_env: Optional trading environment ("demo" or "live") for validation

    Returns:
        ToolResult with order details
    """
    if error := validate_order_params(
        trading_env, symbol, usd_amount=usd_amount,
        trigger_price=trigger_price, limit_price=limit_price
    ):
        return error

    return execute_simple_order(
        exchange_method="stop_limit_sell",
        symbol=symbol,
        trading_env=None,  # Already validated
        usd_amount=usd_amount,
        success_message=f"Stop limit SELL: triggers at ${trigger_price:.2f}, limit @ ${limit_price:.2f}",
        error_prefix="placing stop limit sell",
        extra_data={
            "trigger_price": trigger_price,
            "limit_price": limit_price,
            "trigger_direction": trigger_direction,
            "side": "Sell",
            "order_type": "Stop Limit",
            "reduce_only": reduce_only,
        },
        trigger_price=trigger_price,
        limit_price=limit_price,
        trigger_direction=trigger_direction,
        trigger_by=trigger_by,
        time_in_force=time_in_force,
        reduce_only=reduce_only,
    )


# ==============================================================================
# Order Management Tools
# ==============================================================================

def get_open_orders_tool(
    symbol: str | None = None,
    order_filter: str | None = None,
    limit: int = 50,
    trading_env: str | None = None,
) -> ToolResult:
    """
    Get open orders (real-time).
    
    Args:
        symbol: Filter by symbol (None for all)
        order_filter: 'Order' (normal), 'StopOrder' (conditional), 
                     'tpslOrder' (TP/SL), or None for all
        limit: Maximum orders to return (1-50)
        trading_env: Optional trading environment ("demo" or "live") for validation
    
    Returns:
        ToolResult with open orders list
    """
    if error := validate_trading_env_or_error(trading_env):
        return error
    
    try:
        exchange = _get_exchange_manager()
        orders = exchange.get_open_orders(symbol=symbol)
        
        # Filter by order type if specified
        if order_filter and orders:
            if order_filter == "StopOrder":
                orders = [o for o in orders if o.is_conditional]
            elif order_filter == "Order":
                orders = [o for o in orders if not o.is_conditional]
        
        # Limit results
        orders = orders[:limit] if orders else []
        
        order_data = []
        for o in orders:
            order_data.append({
                "order_id": o.order_id,
                "order_link_id": o.order_link_id,
                "symbol": o.symbol,
                "side": o.side,
                "order_type": o.order_type,
                "qty": o.qty,
                "price": o.price,
                "status": o.status,
                "is_conditional": o.is_conditional,
                "trigger_price": o.trigger_price,
                "reduce_only": o.reduce_only,
            })
        
        return ToolResult(
            success=True,
            symbol=symbol,
            message=f"Found {len(order_data)} open order(s)",
            data={
                "orders": order_data,
                "count": len(order_data),
            },
            source="rest_api",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Failed to get open orders: {str(e)}",
        )


def cancel_order_tool(
    symbol: str,
    order_id: str | None = None,
    order_link_id: str | None = None,
    trading_env: str | None = None,
) -> ToolResult:
    """
    Cancel a specific order by ID.
    
    Args:
        symbol: Trading symbol
        order_id: Order ID to cancel (or use order_link_id)
        order_link_id: Custom order ID to cancel (or use order_id)
        trading_env: Optional trading environment ("demo" or "live") for validation
    
    Returns:
        ToolResult with success status
    """
    if error := validate_trading_env_or_error(trading_env):
        return error
    
    if not symbol or not isinstance(symbol, str):
        return ToolResult(success=False, error="Invalid symbol parameter")
    
    if not order_id and not order_link_id:
        return ToolResult(success=False, error="Must provide order_id or order_link_id")
    
    try:
        exchange = _get_exchange_manager()
        success = exchange.cancel_order(
            symbol=symbol,
            order_id=order_id,
            order_link_id=order_link_id,
        )
        
        identifier = order_id or order_link_id
        
        if success:
            return ToolResult(
                success=True,
                symbol=symbol,
                message=f"Order {identifier} cancelled",
                data={
                    "order_id": order_id,
                    "order_link_id": order_link_id,
                },
            )
        else:
            return ToolResult(
                success=False,
                symbol=symbol,
                error=f"Failed to cancel order {identifier}",
            )
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Exception cancelling order: {str(e)}",
        )


def amend_order_tool(
    symbol: str,
    order_id: str | None = None,
    order_link_id: str | None = None,
    qty: float | None = None,
    price: float | None = None,
    take_profit: float | None = None,
    stop_loss: float | None = None,
    trigger_price: float | None = None,
    trading_env: str | None = None,
) -> ToolResult:
    """
    Amend an existing order (modify price, quantity, or TP/SL).
    
    Args:
        symbol: Trading symbol
        order_id: Order ID to amend (or use order_link_id)
        order_link_id: Custom order ID to amend (or use order_id)
        qty: New quantity (optional)
        price: New price (optional)
        take_profit: New TP price (optional)
        stop_loss: New SL price (optional)
        trigger_price: New trigger price for stop orders (optional)
        trading_env: Optional trading environment ("demo" or "live") for validation
    
    Returns:
        ToolResult with success status
    """
    if error := validate_trading_env_or_error(trading_env):
        return error
    
    if not symbol or not isinstance(symbol, str):
        return ToolResult(success=False, error="Invalid symbol parameter")
    
    if not order_id and not order_link_id:
        return ToolResult(success=False, error="Must provide order_id or order_link_id")
    
    # At least one field to amend
    if all(v is None for v in [qty, price, take_profit, stop_loss, trigger_price]):
        return ToolResult(success=False, error="Must provide at least one field to amend")
    
    try:
        exchange = _get_exchange_manager()
        success = exchange.amend_order(
            symbol=symbol,
            order_id=order_id,
            order_link_id=order_link_id,
            qty=qty,
            price=price,
            take_profit=take_profit,
            stop_loss=stop_loss,
            trigger_price=trigger_price,
        )
        
        identifier = order_id or order_link_id
        
        if success:
            changes = []
            if qty is not None:
                changes.append(f"qty={qty}")
            if price is not None:
                changes.append(f"price=${price:.2f}")
            if take_profit is not None:
                changes.append(f"TP=${take_profit:.2f}")
            if stop_loss is not None:
                changes.append(f"SL=${stop_loss:.2f}")
            if trigger_price is not None:
                changes.append(f"trigger=${trigger_price:.2f}")
            
            changes_str = ", ".join(changes)
            return ToolResult(
                success=True,
                symbol=symbol,
                message=f"Order {identifier} amended: {changes_str}",
                data={
                    "order_id": order_id,
                    "order_link_id": order_link_id,
                    "changes": changes,
                },
            )
        else:
            return ToolResult(
                success=False,
                symbol=symbol,
                error=f"Failed to amend order {identifier}",
            )
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Exception amending order: {str(e)}",
        )


# ==============================================================================
# Batch Order Tools
# ==============================================================================

def batch_market_orders_tool(orders: list[dict[str, object]], trading_env: str | None = None) -> ToolResult:
    """
    Place multiple market orders in a batch (max 10 per batch).
    
    Args:
        orders: List of order dicts with:
            - symbol: Trading symbol
            - side: "Buy" or "Sell"
            - usd_amount: Amount in USD
            - take_profit: Optional TP price
            - stop_loss: Optional SL price
        trading_env: Optional trading environment ("demo" or "live") for validation
    
    Example:
        orders = [
            {"symbol": "BTCUSDT", "side": "Buy", "usd_amount": 100},
            {"symbol": "ETHUSDT", "side": "Sell", "usd_amount": 50, "stop_loss": 1800},
        ]
    
    Returns:
        ToolResult with batch results
    """
    if error := validate_trading_env_or_error(trading_env):
        return error
    
    if not orders or len(orders) == 0:
        return ToolResult(success=False, error="No orders provided")
    
    if len(orders) > 10:
        return ToolResult(success=False, error="Maximum 10 orders per batch (use multiple calls)")
    
    try:
        exchange = _get_exchange_manager()
        results = exchange.batch_market_orders(orders)
        
        success_count = sum(1 for r in results if r.success)
        failed_count = len(results) - success_count
        
        result_data = []
        for r in results:
            result_data.append({
                "success": r.success,
                "order_id": r.order_id,
                "symbol": r.symbol,
                "side": r.side,
                "qty": r.qty,
                "error": r.error,
            })
        
        return ToolResult(
            success=success_count > 0,
            message=f"Batch market orders: {success_count}/{len(orders)} succeeded",
            data={
                "results": result_data,
                "success_count": success_count,
                "failed_count": failed_count,
                "total": len(orders),
            },
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Exception placing batch orders: {str(e)}",
        )


def batch_limit_orders_tool(orders: list[dict[str, object]], trading_env: str | None = None) -> ToolResult:
    """
    Place multiple limit orders in a batch (max 10 per batch).
    
    Args:
        orders: List of order dicts with:
            - symbol: Trading symbol
            - side: "Buy" or "Sell"
            - usd_amount: Amount in USD
            - price: Limit price
            - time_in_force: Optional (default GTC)
            - take_profit: Optional TP price
            - stop_loss: Optional SL price
            - reduce_only: Optional (default False)
        trading_env: Optional trading environment ("demo" or "live") for validation
    
    Example:
        orders = [
            {"symbol": "BTCUSDT", "side": "Buy", "usd_amount": 100, "price": 40000},
            {"symbol": "ETHUSDT", "side": "Sell", "usd_amount": 50, "price": 2000},
        ]
    
    Returns:
        ToolResult with batch results
    """
    if error := validate_trading_env_or_error(trading_env):
        return error
    
    if not orders or len(orders) == 0:
        return ToolResult(success=False, error="No orders provided")
    
    if len(orders) > 10:
        return ToolResult(success=False, error="Maximum 10 orders per batch (use multiple calls)")
    
    # Validate all orders have required fields
    for i, order in enumerate(orders):
        if "price" not in order:
            return ToolResult(success=False, error=f"Order {i+1} missing 'price' field")
    
    try:
        exchange = _get_exchange_manager()
        results = exchange.batch_limit_orders(orders)
        
        success_count = sum(1 for r in results if r.success)
        failed_count = len(results) - success_count
        
        result_data = []
        for r in results:
            result_data.append({
                "success": r.success,
                "order_id": r.order_id,
                "symbol": r.symbol,
                "side": r.side,
                "qty": r.qty,
                "price": r.price,
                "error": r.error,
            })
        
        return ToolResult(
            success=success_count > 0,
            message=f"Batch limit orders: {success_count}/{len(orders)} succeeded",
            data={
                "results": result_data,
                "success_count": success_count,
                "failed_count": failed_count,
                "total": len(orders),
            },
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Exception placing batch limit orders: {str(e)}",
        )


def batch_cancel_orders_tool(orders: list[dict[str, str]], trading_env: str | None = None) -> ToolResult:
    """
    Cancel multiple orders in a batch (max 10 per batch).
    
    Args:
        orders: List of order dicts with:
            - symbol: Trading symbol
            - orderId: Order ID to cancel (or orderLinkId)
            - orderLinkId: Custom order ID (or orderId)
        trading_env: Optional trading environment ("demo" or "live") for validation
    
    Example:
        orders = [
            {"symbol": "BTCUSDT", "orderId": "12345"},
            {"symbol": "ETHUSDT", "orderLinkId": "my-order-1"},
        ]
    
    Returns:
        ToolResult with batch results
    """
    if error := validate_trading_env_or_error(trading_env):
        return error
    
    if not orders or len(orders) == 0:
        return ToolResult(success=False, error="No orders provided")
    
    if len(orders) > 10:
        return ToolResult(success=False, error="Maximum 10 orders per batch (use multiple calls)")
    
    try:
        exchange = _get_exchange_manager()
        results = exchange.batch_cancel_orders(orders)
        
        success_count = sum(1 for r in results if r)
        failed_count = len(results) - success_count
        
        return ToolResult(
            success=success_count > 0,
            message=f"Batch cancel: {success_count}/{len(orders)} orders cancelled",
            data={
                "results": results,
                "success_count": success_count,
                "failed_count": failed_count,
                "total": len(orders),
            },
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Exception cancelling batch orders: {str(e)}",
        )
