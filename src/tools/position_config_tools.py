"""
Position configuration tools for TRADE trading bot.

Extracted from position_tools.py — configuration operations that are
rarely called compared to core position operations (list, SL, TP, close).

Tools:
- Risk limits (get/set)
- TP/SL mode
- Auto-add margin
- Modify position margin
- Switch margin mode (cross/isolated)
- Switch position mode (one-way/hedge)
"""

from .shared import (
    ToolResult,
    _get_exchange_manager,
    validate_trading_env_or_error,
)


# ==============================================================================
# Position Configuration Tools
# ==============================================================================

def set_risk_limit_tool(symbol: str, risk_id: int, trading_env: str | None = None) -> ToolResult:
    """
    Set risk limit for a symbol by risk ID.

    Use get_risk_limits_tool() first to see available risk IDs and their limits.

    Args:
        symbol: Trading symbol
        risk_id: Risk limit ID from get_risk_limits_tool()
        trading_env: Optional trading environment ("demo" or "live") for validation

    Returns:
        ToolResult with success status
    """
    if error := validate_trading_env_or_error(trading_env):
        return error

    if not symbol or not isinstance(symbol, str):
        return ToolResult(success=False, error="Invalid symbol parameter")

    try:
        exchange = _get_exchange_manager()
        success = exchange.set_risk_limit_by_id(symbol, risk_id)

        if success:
            return ToolResult(
                success=True,
                symbol=symbol,
                message=f"Risk limit set to ID {risk_id} for {symbol}",
                data={"risk_id": risk_id},
            )
        else:
            return ToolResult(
                success=False,
                symbol=symbol,
                error=f"Failed to set risk limit for {symbol}",
            )
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Failed to set risk limit: {str(e)}",
        )


def get_risk_limits_tool(symbol: str, trading_env: str | None = None) -> ToolResult:
    """
    Get risk limit tiers for a symbol.

    Shows available risk IDs and their corresponding position limits.

    Args:
        symbol: Trading symbol
        trading_env: Optional trading environment ("demo" or "live") for validation

    Returns:
        ToolResult with risk limit tiers
    """
    if error := validate_trading_env_or_error(trading_env):
        return error

    if not symbol or not isinstance(symbol, str):
        return ToolResult(success=False, error="Invalid symbol parameter")

    try:
        exchange = _get_exchange_manager()
        risk_limits = exchange.get_risk_limits(symbol)

        return ToolResult(
            success=True,
            symbol=symbol,
            message=f"Found {len(risk_limits)} risk limit tiers for {symbol}",
            data={
                "risk_limits": risk_limits,
                "count": len(risk_limits),
            },
            source="rest_api",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Failed to get risk limits: {str(e)}",
        )


def set_tp_sl_mode_tool(symbol: str, full_mode: bool, trading_env: str | None = None) -> ToolResult:
    """
    Set TP/SL mode for a symbol.

    Args:
        symbol: Trading symbol
        full_mode: True for Full (entire position), False for Partial
        trading_env: Optional trading environment ("demo" or "live") for validation

    Returns:
        ToolResult with success status
    """
    if error := validate_trading_env_or_error(trading_env):
        return error

    if not symbol or not isinstance(symbol, str):
        return ToolResult(success=False, error="Invalid symbol parameter")

    try:
        exchange = _get_exchange_manager()
        success = exchange.set_symbol_tp_sl_mode(symbol, full_mode)

        mode = "Full" if full_mode else "Partial"

        if success:
            return ToolResult(
                success=True,
                symbol=symbol,
                message=f"TP/SL mode set to {mode} for {symbol}",
                data={"mode": mode, "full_mode": full_mode},
            )
        else:
            return ToolResult(
                success=False,
                symbol=symbol,
                error=f"Failed to set TP/SL mode for {symbol}",
            )
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Failed to set TP/SL mode: {str(e)}",
        )


def set_auto_add_margin_tool(symbol: str, enabled: bool, trading_env: str | None = None) -> ToolResult:
    """
    Enable or disable auto-add-margin for isolated margin position.

    Args:
        symbol: Trading symbol
        enabled: True to enable, False to disable
        trading_env: Optional trading environment ("demo" or "live") for validation

    Returns:
        ToolResult with success status
    """
    if error := validate_trading_env_or_error(trading_env):
        return error

    if not symbol or not isinstance(symbol, str):
        return ToolResult(success=False, error="Invalid symbol parameter")

    try:
        exchange = _get_exchange_manager()
        success = exchange.set_auto_add_margin(symbol, enabled)

        action = "enabled" if enabled else "disabled"

        if success:
            return ToolResult(
                success=True,
                symbol=symbol,
                message=f"Auto-add-margin {action} for {symbol}",
                data={"enabled": enabled},
            )
        else:
            return ToolResult(
                success=False,
                symbol=symbol,
                error=f"Failed to set auto-add-margin for {symbol}",
            )
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Failed to set auto-add-margin: {str(e)}",
        )


def modify_position_margin_tool(symbol: str, margin: float, trading_env: str | None = None) -> ToolResult:
    """
    Add or reduce margin for isolated margin position.

    Args:
        symbol: Trading symbol
        margin: Amount to add (positive) or reduce (negative)
        trading_env: Optional trading environment ("demo" or "live") for validation

    Returns:
        ToolResult with success status
    """
    if error := validate_trading_env_or_error(trading_env):
        return error

    if not symbol or not isinstance(symbol, str):
        return ToolResult(success=False, error="Invalid symbol parameter")

    if margin == 0:
        return ToolResult(success=False, error="Margin amount cannot be zero")

    try:
        exchange = _get_exchange_manager()
        success = exchange.modify_position_margin(symbol, margin)

        action = "Added" if margin > 0 else "Reduced"

        if success:
            return ToolResult(
                success=True,
                symbol=symbol,
                message=f"{action} {abs(margin):.4f} margin for {symbol}",
                data={"margin_change": margin},
            )
        else:
            return ToolResult(
                success=False,
                symbol=symbol,
                error=f"Failed to modify margin for {symbol}",
            )
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Failed to modify margin: {str(e)}",
        )


def switch_margin_mode_tool(symbol: str, isolated: bool, leverage: int | None = None, trading_env: str | None = None) -> ToolResult:
    """
    Switch between cross and isolated margin mode for a symbol.

    Args:
        symbol: Trading symbol
        isolated: True for isolated, False for cross
        leverage: Leverage to set (uses default if None)
        trading_env: Optional trading environment ("demo" or "live") for validation

    Returns:
        ToolResult with success status
    """
    if error := validate_trading_env_or_error(trading_env):
        return error

    if not symbol or not isinstance(symbol, str):
        return ToolResult(success=False, error="Invalid symbol parameter")

    try:
        exchange = _get_exchange_manager()

        if isolated:
            success = exchange.switch_to_isolated_margin(symbol, leverage)
            mode = "isolated"
        else:
            success = exchange.switch_to_cross_margin(symbol, leverage)
            mode = "cross"

        if success:
            return ToolResult(
                success=True,
                symbol=symbol,
                message=f"Switched {symbol} to {mode} margin mode",
                data={"mode": mode, "isolated": isolated, "leverage": leverage},
            )
        else:
            return ToolResult(
                success=False,
                symbol=symbol,
                error=f"Failed to switch {symbol} to {mode} margin",
            )
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Failed to switch margin mode: {str(e)}",
        )


def switch_position_mode_tool(hedge_mode: bool, trading_env: str | None = None) -> ToolResult:
    """
    Switch position mode for the account.

    Args:
        hedge_mode: True for hedge mode (both Buy & Sell),
                   False for one-way mode (Buy OR Sell)
        trading_env: Optional trading environment ("demo" or "live") for validation

    Returns:
        ToolResult with success status
    """
    if error := validate_trading_env_or_error(trading_env):
        return error

    try:
        exchange = _get_exchange_manager()

        if hedge_mode:
            success = exchange.switch_to_hedge_mode()
            mode = "hedge (both sides)"
        else:
            success = exchange.switch_to_one_way_mode()
            mode = "one-way"

        if success:
            return ToolResult(
                success=True,
                message=f"Switched to {mode} position mode",
                data={"mode": mode, "hedge_mode": hedge_mode},
            )
        else:
            return ToolResult(
                success=False,
                error=f"Failed to switch to {mode} position mode",
            )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Failed to switch position mode: {str(e)}",
        )
