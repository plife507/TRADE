"""
Position management tools for TRADE trading bot.

These tools provide a clean, callable interface for all position-related
operations. They can be invoked by CLI, AI agents, or API endpoints.

Design principles:
- Pure functions with no user interaction (CLI handles prompts/menus)
- Return ToolResult with structured success/error information
- Use WebSocket data (RealtimeState) when available, REST fallback
- Write operations go through ExchangeManager
- Never hardcode symbols - always accept as parameters

All trading tools accept an optional `trading_env` parameter for agent/orchestrator
use. This parameter VALIDATES the caller's intent against the process config but
does NOT switch environments. If the env doesn't match, the tool returns an error.

Usage:
    from src.tools.position_tools import (
        list_open_positions_tool,
        set_trailing_stop_tool,
        close_position_tool,
    )
    
    # List positions
    result = list_open_positions_tool()
    
    # Set trailing stop
    result = set_trailing_stop_tool("BTCUSDT", trailing_distance=200.0)
    
    # Close position
    result = close_position_tool("BTCUSDT")
"""

from typing import Optional, Dict, Any, List

# Import shared types and helpers from the shared module
from .shared import (
    ToolResult,
    _get_exchange_manager,
    _get_realtime_state,
    _is_websocket_connected,
    _ensure_websocket_running,
    _get_data_source,
    validate_trading_env_or_error,
)


def _position_to_dict(pos) -> Dict[str, Any]:
    """Convert a Position object to a serializable dictionary."""
    return {
        "symbol": pos.symbol,
        "side": pos.side,
        "size": pos.size,
        "size_usd": getattr(pos, "size_usd", pos.size * pos.current_price if hasattr(pos, "current_price") else 0),
        "entry_price": pos.entry_price,
        "current_price": getattr(pos, "current_price", getattr(pos, "mark_price", 0)),
        "unrealized_pnl": pos.unrealized_pnl,
        "unrealized_pnl_percent": getattr(pos, "unrealized_pnl_percent", getattr(pos, "pnl_percent", 0)),
        "leverage": pos.leverage,
        "liquidation_price": getattr(pos, "liquidation_price", getattr(pos, "liq_price", None)),
        "take_profit": pos.take_profit,
        "stop_loss": pos.stop_loss,
        "trailing_stop": getattr(pos, "trailing_stop", None),
        "margin_mode": getattr(pos, "margin_mode", "cross"),
        "is_open": getattr(pos, "is_open", pos.size > 0),
    }


def _ws_position_to_dict(ws_pos) -> Dict[str, Any]:
    """Convert a WebSocket PositionData to a serializable dictionary."""
    return {
        "symbol": ws_pos.symbol,
        "side": ws_pos.side.lower() if ws_pos.side else "none",
        "size": ws_pos.size,
        "size_usd": ws_pos.position_value,
        "entry_price": ws_pos.entry_price,
        "current_price": ws_pos.mark_price,
        "unrealized_pnl": ws_pos.unrealized_pnl,
        "unrealized_pnl_percent": ws_pos.pnl_percent,
        "leverage": ws_pos.leverage,
        "liquidation_price": ws_pos.liq_price if ws_pos.liq_price else None,
        "take_profit": ws_pos.take_profit if ws_pos.take_profit else None,
        "stop_loss": ws_pos.stop_loss if ws_pos.stop_loss else None,
        "trailing_stop": ws_pos.trailing_stop if ws_pos.trailing_stop else None,
        "margin_mode": "cross",  # Default; WS doesn't always provide this
        "is_open": ws_pos.is_open,
    }


# ==============================================================================
# Position Listing Tools
# ==============================================================================

def list_open_positions_tool(symbol: Optional[str] = None, trading_env: Optional[str] = None) -> ToolResult:
    """
    List all open positions, optionally filtered by symbol.
    
    Uses WebSocket data if already connected, otherwise uses REST.
    Does NOT auto-start WebSocket - use REST for simple queries.
    
    Args:
        symbol: Optional symbol to filter (None for all positions)
        trading_env: Optional trading environment ("demo" or "live") for validation
    
    Returns:
        ToolResult with data["positions"] containing list of position dicts
    """
    if error := validate_trading_env_or_error(trading_env):
        return error
    
    try:
        # Check if WebSocket is already running (don't start it)
        # WebSocket is only for risk manager, not for simple position queries
        if _is_websocket_connected():
            state = _get_realtime_state()
            ws_positions = state.get_all_positions()
            
            positions = []
            for sym, ws_pos in ws_positions.items():
                if ws_pos.is_open:
                    if symbol is None or sym == symbol:
                        positions.append(_ws_position_to_dict(ws_pos))
            
            return ToolResult(
                success=True,
                message=f"Found {len(positions)} open position(s)",
                data={"positions": positions, "count": len(positions)},
                source="websocket",
            )
        
        # Fallback to REST
        exchange = _get_exchange_manager()
        rest_positions = exchange.get_all_positions()
        
        positions = []
        for pos in rest_positions:
            if pos.is_open:
                if symbol is None or pos.symbol == symbol:
                    positions.append(_position_to_dict(pos))
        
        return ToolResult(
            success=True,
            message=f"Found {len(positions)} open position(s)",
            data={"positions": positions, "count": len(positions)},
            source="rest_api",
        )
        
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Failed to list positions: {str(e)}",
        )


def get_position_detail_tool(symbol: str, trading_env: Optional[str] = None) -> ToolResult:
    """
    Get detailed information for a specific position.
    
    Uses WebSocket data if already connected, otherwise uses REST.
    Does NOT auto-start WebSocket - use REST for simple queries.
    
    Args:
        symbol: Trading symbol (e.g., "BTCUSDT")
        trading_env: Optional trading environment ("demo" or "live") for validation
    
    Returns:
        ToolResult with position data or error if no position exists
    """
    if error := validate_trading_env_or_error(trading_env):
        return error
    
    if not symbol or not isinstance(symbol, str):
        return ToolResult(
            success=False,
            error="Invalid symbol parameter",
        )
    
    try:
        # Check if WebSocket is already running (don't start it)
        # WebSocket is only for risk manager, not for simple position queries
        if _is_websocket_connected():
            state = _get_realtime_state()
            ws_pos = state.get_position(symbol)
            
            if ws_pos and ws_pos.is_open:
                return ToolResult(
                    success=True,
                    symbol=symbol,
                    message=f"Position found for {symbol}",
                    data=_ws_position_to_dict(ws_pos),
                    source="websocket",
                )
        
        # Fallback to REST
        exchange = _get_exchange_manager()
        pos = exchange.get_position(symbol)
        
        if pos and pos.is_open:
            return ToolResult(
                success=True,
                symbol=symbol,
                message=f"Position found for {symbol}",
                data=_position_to_dict(pos),
                source="rest_api",
            )
        
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"No open position found for {symbol}",
        )
        
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Failed to get position: {str(e)}",
        )


# ==============================================================================
# Stop Loss Tools
# ==============================================================================

def set_stop_loss_tool(symbol: str, stop_price: float, trading_env: Optional[str] = None) -> ToolResult:
    """
    Set or update the stop loss price for an existing position.
    
    Args:
        symbol: Trading symbol
        stop_price: Stop loss price
        trading_env: Optional trading environment ("demo" or "live") for validation
    
    Returns:
        ToolResult with success status
    """
    if error := validate_trading_env_or_error(trading_env):
        return error
    
    if not symbol or not isinstance(symbol, str):
        return ToolResult(success=False, error="Invalid symbol parameter")
    
    if stop_price <= 0:
        return ToolResult(success=False, error="Stop price must be positive")
    
    try:
        exchange = _get_exchange_manager()
        
        # Verify position exists
        pos = exchange.get_position(symbol)
        if not pos or not pos.is_open:
            return ToolResult(
                success=False,
                symbol=symbol,
                error=f"No open position for {symbol}",
            )
        
        # Set stop loss (leave TP unchanged by not passing it)
        success = exchange.set_position_tpsl(
            symbol=symbol,
            stop_loss=stop_price,
        )
        
        if success:
            return ToolResult(
                success=True,
                symbol=symbol,
                message=f"Stop loss set to {stop_price}",
                data={"stop_loss": stop_price},
            )
        else:
            return ToolResult(
                success=False,
                symbol=symbol,
                error="Failed to set stop loss",
            )
            
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Exception setting stop loss: {str(e)}",
        )


def remove_stop_loss_tool(symbol: str, trading_env: Optional[str] = None) -> ToolResult:
    """
    Remove the stop loss from an existing position.
    
    Args:
        symbol: Trading symbol
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
        
        # Verify position exists
        pos = exchange.get_position(symbol)
        if not pos or not pos.is_open:
            return ToolResult(
                success=False,
                symbol=symbol,
                error=f"No open position for {symbol}",
            )
        
        # Remove stop loss by setting to 0
        success = exchange.set_position_tpsl(
            symbol=symbol,
            stop_loss=0,
        )
        
        if success:
            return ToolResult(
                success=True,
                symbol=symbol,
                message="Stop loss removed",
            )
        else:
            return ToolResult(
                success=False,
                symbol=symbol,
                error="Failed to remove stop loss",
            )
            
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Exception removing stop loss: {str(e)}",
        )


# ==============================================================================
# Take Profit Tools
# ==============================================================================

def set_take_profit_tool(symbol: str, take_profit_price: float, trading_env: Optional[str] = None) -> ToolResult:
    """
    Set or update the take profit price for an existing position.
    
    Args:
        symbol: Trading symbol
        take_profit_price: Take profit price
        trading_env: Optional trading environment ("demo" or "live") for validation
    
    Returns:
        ToolResult with success status
    """
    if error := validate_trading_env_or_error(trading_env):
        return error
    
    if not symbol or not isinstance(symbol, str):
        return ToolResult(success=False, error="Invalid symbol parameter")
    
    if take_profit_price <= 0:
        return ToolResult(success=False, error="Take profit price must be positive")
    
    try:
        exchange = _get_exchange_manager()
        
        # Verify position exists
        pos = exchange.get_position(symbol)
        if not pos or not pos.is_open:
            return ToolResult(
                success=False,
                symbol=symbol,
                error=f"No open position for {symbol}",
            )
        
        # Set take profit
        success = exchange.set_position_tpsl(
            symbol=symbol,
            take_profit=take_profit_price,
        )
        
        if success:
            return ToolResult(
                success=True,
                symbol=symbol,
                message=f"Take profit set to {take_profit_price}",
                data={"take_profit": take_profit_price},
            )
        else:
            return ToolResult(
                success=False,
                symbol=symbol,
                error="Failed to set take profit",
            )
            
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Exception setting take profit: {str(e)}",
        )


def remove_take_profit_tool(symbol: str, trading_env: Optional[str] = None) -> ToolResult:
    """
    Remove the take profit from an existing position.
    
    Args:
        symbol: Trading symbol
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
        
        # Verify position exists
        pos = exchange.get_position(symbol)
        if not pos or not pos.is_open:
            return ToolResult(
                success=False,
                symbol=symbol,
                error=f"No open position for {symbol}",
            )
        
        # Remove take profit by setting to 0
        success = exchange.set_position_tpsl(
            symbol=symbol,
            take_profit=0,
        )
        
        if success:
            return ToolResult(
                success=True,
                symbol=symbol,
                message="Take profit removed",
            )
        else:
            return ToolResult(
                success=False,
                symbol=symbol,
                error="Failed to remove take profit",
            )
            
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Exception removing take profit: {str(e)}",
        )


# ==============================================================================
# Combined TP/SL Tool
# ==============================================================================

def set_position_tpsl_tool(
    symbol: str,
    take_profit: Optional[float] = None,
    stop_loss: Optional[float] = None,
    tpsl_mode: str = "Full",
    trading_env: Optional[str] = None,
) -> ToolResult:
    """
    Set both take profit and stop loss for an existing position.
    
    Args:
        symbol: Trading symbol
        take_profit: Take profit price (None to leave unchanged, 0 to remove)
        stop_loss: Stop loss price (None to leave unchanged, 0 to remove)
        tpsl_mode: "Full" (entire position) or "Partial"
        trading_env: Optional trading environment ("demo" or "live") for validation
    
    Returns:
        ToolResult with success status
    """
    if error := validate_trading_env_or_error(trading_env):
        return error
    
    if not symbol or not isinstance(symbol, str):
        return ToolResult(success=False, error="Invalid symbol parameter")
    
    if take_profit is None and stop_loss is None:
        return ToolResult(success=False, error="Must provide at least take_profit or stop_loss")
    
    try:
        exchange = _get_exchange_manager()
        
        # Verify position exists
        pos = exchange.get_position(symbol)
        if not pos or not pos.is_open:
            return ToolResult(
                success=False,
                symbol=symbol,
                error=f"No open position for {symbol}",
            )
        
        # Set TP/SL
        success = exchange.set_position_tpsl(
            symbol=symbol,
            take_profit=take_profit,
            stop_loss=stop_loss,
            tpsl_mode=tpsl_mode,
        )
        
        if success:
            changes = []
            if take_profit is not None:
                changes.append(f"TP={take_profit}" if take_profit > 0 else "TP removed")
            if stop_loss is not None:
                changes.append(f"SL={stop_loss}" if stop_loss > 0 else "SL removed")
            
            return ToolResult(
                success=True,
                symbol=symbol,
                message=f"Position updated: {', '.join(changes)}",
                data={"take_profit": take_profit, "stop_loss": stop_loss},
            )
        else:
            return ToolResult(
                success=False,
                symbol=symbol,
                error="Failed to set TP/SL",
            )
            
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Exception setting TP/SL: {str(e)}",
        )


# ==============================================================================
# Trailing Stop Tools
# ==============================================================================

def set_trailing_stop_tool(
    symbol: str,
    trailing_distance: float,
    active_price: Optional[float] = None,
    trading_env: Optional[str] = None,
) -> ToolResult:
    """
    Set or remove a trailing stop for an existing position.
    
    Args:
        symbol: Trading symbol
        trailing_distance: Trailing stop distance in price units (0 to remove)
        active_price: Price at which trailing becomes active (optional)
        trading_env: Optional trading environment ("demo" or "live") for validation
    
    Returns:
        ToolResult with success status
    """
    if error := validate_trading_env_or_error(trading_env):
        return error
    
    if not symbol or not isinstance(symbol, str):
        return ToolResult(success=False, error="Invalid symbol parameter")
    
    if trailing_distance < 0:
        return ToolResult(success=False, error="Trailing distance cannot be negative")
    
    try:
        exchange = _get_exchange_manager()
        
        # Verify position exists
        pos = exchange.get_position(symbol)
        if not pos or not pos.is_open:
            return ToolResult(
                success=False,
                symbol=symbol,
                error=f"No open position for {symbol}",
            )
        
        # Set trailing stop
        success = exchange.set_trailing_stop(
            symbol=symbol,
            trailing_stop=trailing_distance,
            active_price=active_price,
        )
        
        if success:
            if trailing_distance == 0:
                msg = "Trailing stop removed"
            else:
                msg = f"Trailing stop set: {trailing_distance}"
                if active_price:
                    msg += f" (activates at {active_price})"
            
            return ToolResult(
                success=True,
                symbol=symbol,
                message=msg,
                data={
                    "trailing_distance": trailing_distance,
                    "active_price": active_price,
                },
            )
        else:
            action = "remove" if trailing_distance == 0 else "set"
            return ToolResult(
                success=False,
                symbol=symbol,
                error=f"Failed to {action} trailing stop",
            )
            
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Exception setting trailing stop: {str(e)}",
        )


def set_trailing_stop_by_percent_tool(symbol: str, percent: float, trading_env: Optional[str] = None) -> ToolResult:
    """
    Set a trailing stop using a percentage of current price.
    
    Args:
        symbol: Trading symbol
        percent: Trailing stop as percentage of current price (e.g., 1.5 for 1.5%)
        trading_env: Optional trading environment ("demo" or "live") for validation
    
    Returns:
        ToolResult with success status
    """
    if error := validate_trading_env_or_error(trading_env):
        return error
    
    if not symbol or not isinstance(symbol, str):
        return ToolResult(success=False, error="Invalid symbol parameter")
    
    if percent <= 0:
        return ToolResult(success=False, error="Percent must be positive")
    
    try:
        # Get current price (prefer WebSocket)
        current_price = None
        
        if _is_websocket_connected():
            state = _get_realtime_state()
            ticker = state.get_ticker(symbol)
            if ticker:
                current_price = ticker.last_price
        
        if current_price is None:
            exchange = _get_exchange_manager()
            current_price = exchange.get_price(symbol)
        
        if not current_price or current_price <= 0:
            return ToolResult(
                success=False,
                symbol=symbol,
                error=f"Could not get current price for {symbol}",
            )
        
        # Calculate absolute distance from percent
        trailing_distance = current_price * percent / 100
        
        # Use the main trailing stop tool
        result = set_trailing_stop_tool(symbol, trailing_distance)
        
        # Enhance message with percent info
        if result.success:
            result.message = f"Trailing stop set: {trailing_distance:.2f} ({percent}% of {current_price:.2f})"
            result.data["percent"] = percent
            result.data["price_used"] = current_price
        
        return result
        
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Exception setting trailing stop: {str(e)}",
        )


# ==============================================================================
# Position Close Tools
# ==============================================================================

def close_position_tool(
    symbol: str,
    cancel_conditional_orders: bool = True,
    trading_env: Optional[str] = None,
) -> ToolResult:
    """
    Close an open position for a symbol.
    
    Automatically cancels related conditional TP orders when closing.
    
    Args:
        symbol: Trading symbol
        cancel_conditional_orders: If True, cancel conditional TP orders first
        trading_env: Optional trading environment ("demo" or "live") for validation
    
    Returns:
        ToolResult with close order details
    """
    if error := validate_trading_env_or_error(trading_env):
        return error
    
    if not symbol or not isinstance(symbol, str):
        return ToolResult(success=False, error="Invalid symbol parameter")
    
    try:
        exchange = _get_exchange_manager()
        
        # Get position first for summary
        pos = exchange.get_position(symbol)
        if not pos or not pos.is_open:
            return ToolResult(
                success=True,
                symbol=symbol,
                message="No position to close",
                data={"had_position": False},
            )
        
        # Close position
        result = exchange.close_position(
            symbol=symbol,
            cancel_conditional_orders=cancel_conditional_orders,
        )
        
        if result.success:
            return ToolResult(
                success=True,
                symbol=symbol,
                message=f"Position closed for {symbol}",
                data={
                    "order_id": result.order_id,
                    "side": result.side,
                    "qty": result.qty,
                    "closed_pnl": pos.unrealized_pnl,
                    "had_position": True,
                },
            )
        else:
            return ToolResult(
                success=False,
                symbol=symbol,
                error=result.error or "Failed to close position",
            )
            
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Exception closing position: {str(e)}",
        )


# ==============================================================================
# Panic / Emergency Tools
# ==============================================================================

def panic_close_all_tool(reason: Optional[str] = None, trading_env: Optional[str] = None) -> ToolResult:
    """
    Emergency close all positions and cancel all orders.
    
    This is the "panic button" - closes everything immediately.
    
    Args:
        reason: Optional reason for the panic close (for logging)
        trading_env: Optional trading environment ("demo" or "live") for validation
    
    Returns:
        ToolResult with summary of closed positions and cancelled orders
    """
    if error := validate_trading_env_or_error(trading_env):
        return error
    
    try:
        exchange = _get_exchange_manager()
        
        if reason:
            from ..utils.logger import get_logger
            logger = get_logger()
            logger.warning(f"PANIC triggered: {reason}")
        
        # Get current state for reporting
        positions_before = exchange.get_all_positions()
        open_positions = [p for p in positions_before if p.is_open]
        
        # Cancel all orders first
        cancel_success = exchange.cancel_all_orders()
        
        # Close all positions
        close_results = exchange.close_all_positions()
        
        # Build summary
        closed_count = sum(1 for r in close_results if r.success)
        failed_count = len(close_results) - closed_count
        
        total_pnl = sum(p.unrealized_pnl for p in open_positions)
        
        summary = {
            "positions_closed": closed_count,
            "positions_failed": failed_count,
            "orders_cancelled": cancel_success,
            "estimated_pnl": total_pnl,
            "details": [
                {
                    "symbol": r.symbol,
                    "success": r.success,
                    "error": r.error,
                }
                for r in close_results
            ],
        }
        
        if failed_count == 0:
            return ToolResult(
                success=True,
                message=f"PANIC: Closed {closed_count} position(s), cancelled orders",
                data=summary,
            )
        else:
            return ToolResult(
                success=False,
                message=f"PANIC: Closed {closed_count}, failed {failed_count}",
                data=summary,
                error=f"{failed_count} position(s) failed to close",
            )
            
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"PANIC failed: {str(e)}",
        )


# ==============================================================================
# Position Configuration Tools
# ==============================================================================

def set_risk_limit_tool(symbol: str, risk_id: int, trading_env: Optional[str] = None) -> ToolResult:
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


def get_risk_limits_tool(symbol: str, trading_env: Optional[str] = None) -> ToolResult:
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


def set_tp_sl_mode_tool(symbol: str, full_mode: bool, trading_env: Optional[str] = None) -> ToolResult:
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


def set_auto_add_margin_tool(symbol: str, enabled: bool, trading_env: Optional[str] = None) -> ToolResult:
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


def modify_position_margin_tool(symbol: str, margin: float, trading_env: Optional[str] = None) -> ToolResult:
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


def switch_margin_mode_tool(symbol: str, isolated: bool, leverage: Optional[int] = None, trading_env: Optional[str] = None) -> ToolResult:
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


def switch_position_mode_tool(hedge_mode: bool, trading_env: Optional[str] = None) -> ToolResult:
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
