"""
Common utilities for order tools.

Provides shared validation and execution patterns to reduce boilerplate
across order tool functions. Each order tool can use these helpers to:
1. Validate common parameters (trading_env, symbol, amounts, prices)
2. Execute exchange operations with unified error handling
3. Build consistent ToolResult responses

ARCHITECTURE:
- validate_* functions return ToolResult on error, None on success
- execute_order() wraps the full exchange call pattern
- build_order_data() creates consistent response data structures
"""

from typing import Any, Callable

from .shared import ToolResult, _get_exchange_manager, validate_trading_env_or_error


def validate_symbol(symbol: str | None) -> ToolResult | None:
    """
    Validate symbol parameter.

    Returns:
        ToolResult with error if invalid, None if valid
    """
    if not symbol or not isinstance(symbol, str):
        return ToolResult(success=False, error="Invalid symbol parameter")
    return None


def validate_positive_amount(amount: float | None, name: str = "Amount") -> ToolResult | None:
    """
    Validate that amount is positive.

    Returns:
        ToolResult with error if invalid, None if valid
    """
    if amount is None or amount <= 0:
        return ToolResult(success=False, error=f"{name} must be positive")
    return None


def validate_positive_price(price: float | None, name: str = "Price") -> ToolResult | None:
    """
    Validate that price is positive.

    Returns:
        ToolResult with error if invalid, None if valid
    """
    if price is None or price <= 0:
        return ToolResult(success=False, error=f"{name} must be positive")
    return None


def validate_order_params(
    trading_env: str | None,
    symbol: str | None,
    usd_amount: float | None = None,
    price: float | None = None,
    trigger_price: float | None = None,
    limit_price: float | None = None,
) -> ToolResult | None:
    """
    Validate common order parameters.

    Validates in order:
    1. Trading environment
    2. Symbol
    3. USD amount (if provided)
    4. Price (if provided)
    5. Trigger price (if provided)
    6. Limit price (if provided)

    Returns:
        ToolResult with error if any validation fails, None if all valid
    """
    if error := validate_trading_env_or_error(trading_env):
        return error

    if error := validate_symbol(symbol):
        return error

    if usd_amount is not None:
        if error := validate_positive_amount(usd_amount, "USD amount"):
            return error

    if price is not None:
        if error := validate_positive_price(price, "Price"):
            return error

    if trigger_price is not None:
        if error := validate_positive_price(trigger_price, "Trigger price"):
            return error

    if limit_price is not None:
        if error := validate_positive_price(limit_price, "Limit price"):
            return error

    return None


def build_order_data(
    result: Any,
    extra_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build standard order data dict from exchange result.

    Args:
        result: Exchange operation result with order_id, side, qty, price, etc.
        extra_data: Additional fields to include in response

    Returns:
        Dict with order data for ToolResult
    """
    data = {
        "order_id": getattr(result, "order_id", None),
        "side": getattr(result, "side", None),
        "qty": getattr(result, "qty", None),
        "price": getattr(result, "price", None),
    }

    # Add order_link_id if present
    if hasattr(result, "order_link_id") and result.order_link_id:
        data["order_link_id"] = result.order_link_id

    # Merge extra data
    if extra_data:
        data.update(extra_data)

    return data


def execute_order(
    operation: Callable[..., Any],
    symbol: str,
    success_message: str,
    error_prefix: str,
    extra_data: dict[str, Any] | None = None,
    **kwargs: Any,
) -> ToolResult:
    """
    Execute an exchange order operation with unified error handling.

    This is the core pattern used by all order tools:
    1. Get exchange manager
    2. Call the operation
    3. Build success/error ToolResult

    Args:
        operation: Exchange method to call (e.g., exchange.market_buy)
        symbol: Trading symbol
        success_message: Message template for success (can use {qty}, {price})
        error_prefix: Prefix for error messages
        extra_data: Additional data to include in success response
        **kwargs: Arguments to pass to the operation

    Returns:
        ToolResult with order details or error
    """
    try:
        result = operation(**kwargs)

        if result.success:
            # Format message with result values if placeholders present
            message = success_message
            if "{qty}" in message:
                message = message.replace("{qty}", str(result.qty))
            if "{price}" in message:
                message = message.replace("{price}", f"${result.price:,.2f}")

            return ToolResult(
                success=True,
                symbol=symbol,
                message=message,
                data=build_order_data(result, extra_data),
            )
        else:
            return ToolResult(
                success=False,
                symbol=symbol,
                error=result.error or f"{error_prefix} failed",
            )
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Exception {error_prefix.lower()}: {e!s}",
        )


def execute_simple_order(
    exchange_method: str,
    symbol: str,
    trading_env: str | None,
    success_message: str,
    error_prefix: str,
    usd_amount: float | None = None,
    price: float | None = None,
    extra_data: dict[str, Any] | None = None,
    **kwargs: Any,
) -> ToolResult:
    """
    Full order execution with validation.

    Combines validate_order_params + execute_order for simple cases.

    Args:
        exchange_method: Name of exchange method to call
        symbol: Trading symbol
        trading_env: Trading environment for validation
        success_message: Message template for success
        error_prefix: Prefix for error messages
        usd_amount: USD amount (validated if provided)
        price: Price (validated if provided)
        extra_data: Additional data for response
        **kwargs: Additional arguments for exchange method

    Returns:
        ToolResult with order details or error
    """
    # Validate parameters
    if error := validate_order_params(
        trading_env=trading_env,
        symbol=symbol,
        usd_amount=usd_amount,
        price=price,
    ):
        return error

    # Get exchange and execute
    try:
        exchange = _get_exchange_manager()
        operation = getattr(exchange, exchange_method)

        # Build operation kwargs
        op_kwargs = {"symbol": symbol}
        if usd_amount is not None:
            op_kwargs["usd_amount"] = usd_amount
        if price is not None:
            op_kwargs["price"] = price
        op_kwargs.update(kwargs)

        return execute_order(
            operation=operation,
            symbol=symbol,
            success_message=success_message,
            error_prefix=error_prefix,
            extra_data=extra_data,
            **op_kwargs,
        )
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Exception {error_prefix.lower()}: {e!s}",
        )
