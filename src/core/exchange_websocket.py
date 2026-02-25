"""
WebSocket integration and cleanup callbacks for ExchangeManager.

Handles:
- Position update callbacks for automatic TP order cleanup
- Symbol tracking for real-time updates
- Conditional order cancellation on position close
"""

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .exchange_manager import ExchangeManager


def setup_position_close_cleanup(manager: "ExchangeManager"):
    """
    Setup callbacks for automatic conditional order cleanup on position close.

    When a position closes (SL hit, TP filled, manual close), this automatically
    cancels any remaining conditional TP orders to prevent orphaned orders.

    Registers a RealtimeState position-update callback. The callback fires
    whenever the WebSocket receives a position update (only while WS is running).
    """
    try:
        from ..data.realtime_state import get_realtime_state
        state = get_realtime_state()

        # Register callback for position updates
        state.on_position_update(lambda pos_data: on_position_update_cleanup(manager, pos_data))

        manager.logger.info("Position-close cleanup callback registered")
    except ImportError:
        manager.logger.debug("RealtimeState not available - position cleanup disabled")
    except Exception as e:
        manager.logger.warning("Could not setup position-close cleanup: %s", e)


def on_position_update_cleanup(manager: "ExchangeManager", position_data):
    """
    Callback triggered when position updates via WebSocket.

    Automatically cancels conditional TP orders when position closes.
    Also handles symbol unsubscription when positions close.
    Only cancels orders with bot-generated order_link_id pattern.
    """
    try:
        if not hasattr(position_data, 'symbol') or not position_data.symbol:
            manager.logger.error("WS position update missing 'symbol' field: %s", type(position_data).__name__)
            return
        symbol = position_data.symbol
        is_open = position_data.is_open

        # Check and update tracking with lock
        with manager._position_tracking_lock:
            was_open = manager._previous_positions.get(symbol, False)
            manager._previous_positions[symbol] = is_open
            position_just_closed = was_open and not is_open

        # Detect position closure (was open, now closed) - do cleanup outside lock
        if position_just_closed:
            manager.logger.info(
                "Position closed for %s (detected via WebSocket) - "
                "cleaning up conditional orders",
                symbol,
            )

            # Cancel all bot-generated conditional reduce-only orders for this symbol
            cancelled = cancel_conditional_orders_for_symbol(manager, symbol)

            if cancelled:
                manager.logger.info(
                    "Auto-cancelled %s conditional orders for %s", len(cancelled), symbol
                )

            # Remove symbol from websocket tracking (no longer needed)
            # Note: pybit doesn't support dynamic unsubscription, but we stop tracking it
            remove_symbol_from_websocket(manager, symbol)

    except Exception as e:
        # Don't let callback errors break WebSocket processing
        manager.logger.warning("Error in position cleanup callback for %s: %s", getattr(position_data, 'symbol', 'unknown'), e)


def cancel_conditional_orders_for_symbol(manager: "ExchangeManager", symbol: str) -> list[str]:
    """
    Cancel all bot-generated conditional reduce-only orders for a symbol.
    
    Used when position closes and we don't know the original side.
    Only cancels orders with bot-generated order_link_id pattern.
    
    Args:
        manager: ExchangeManager instance
        symbol: Trading symbol
    
    Returns:
        List of cancelled order identifiers
    """
    cancelled = []
    
    try:
        orders = manager.get_open_orders(symbol)
        
        # Pattern for bot-generated TP/SL orders: TP1_BTCUSDT_1234567890 or SL_BTCUSDT_1234567890
        tp_pattern = re.compile(rf"^(TP\d+|SL)_{re.escape(symbol)}_\d+$")
        
        # Cancel all bot-generated conditional reduce-only orders
        orders_to_cancel = [
            order for order in orders
            if order.is_conditional
            and order.reduce_only
            and order.is_active
            and order.order_link_id
            and tp_pattern.match(order.order_link_id)
        ]
        
        for order in orders_to_cancel:
            try:
                if manager.cancel_order(
                    symbol=symbol,
                    order_id=order.order_id,
                    order_link_id=order.order_link_id,
                ):
                    cancelled.append(order.order_link_id or order.order_id)
            except Exception as e:
                manager.logger.warning("Failed to cancel order: %s", e)
    
    except Exception as e:
        manager.logger.warning("Error cancelling conditional orders for %s: %s", symbol, e)
    
    return cancelled


def ensure_symbol_tracked(manager: "ExchangeManager", symbol: str):
    """
    Ensure symbol is tracked for real-time updates.
    
    Dynamically subscribes to WebSocket streams for the symbol
    if not already subscribed. This enables real-time market data
    and position updates for the symbol.
    
    Only subscribes if websocket is running (for risk manager).
    
    Args:
        manager: ExchangeManager instance
        symbol: Symbol to track (e.g., "SOLUSDT")
    """
    try:
        from ..data.realtime_bootstrap import get_realtime_bootstrap

        bootstrap = get_realtime_bootstrap()
        if bootstrap and bootstrap.is_running:
            bootstrap.ensure_symbol_subscribed(symbol)
    except ImportError:
        # BUG-001 fix: Bootstrap module not available
        pass
    except (ConnectionError, OSError, RuntimeError) as e:
        # BUG-001 fix: WebSocket not available, REST fallback will be used
        # Log but don't fail - this is expected when WS is down
        manager.logger.debug("WebSocket unavailable for %s: %s", symbol, e)


def remove_symbol_from_websocket(manager: "ExchangeManager", symbol: str):
    """
    Remove symbol from websocket tracking when position closes.
    
    Note: pybit doesn't support dynamic unsubscription, but we stop
    tracking the symbol. The websocket will continue receiving data
    but we'll ignore it.
    
    Args:
        manager: ExchangeManager instance
        symbol: Symbol to remove from tracking
    """
    try:
        from ..data.realtime_bootstrap import get_realtime_bootstrap
        
        bootstrap = get_realtime_bootstrap()
        if bootstrap:
            bootstrap.remove_symbol(symbol)
            manager.logger.debug("Removed %s from websocket tracking (position closed)", symbol)
    except Exception as e:
        manager.logger.debug("Could not remove %s from websocket: %s", symbol, e)

