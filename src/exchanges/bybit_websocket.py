"""
Bybit WebSocket connection and subscription methods.

Contains: connect_public_ws, connect_private_ws, subscribe_* methods,
close_websockets, and cleanup utilities.
"""

# G6.4.13: Removed unused sys import
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

from pybit.unified_trading import WebSocket

if TYPE_CHECKING:
    from .bybit_client import BybitClient


# Global flag to track if cleanup hook is installed
_ws_cleanup_hook_installed = False


def _install_ws_cleanup_hook():
    """Install a thread exception hook to suppress WebSocket cleanup errors."""
    global _ws_cleanup_hook_installed
    if _ws_cleanup_hook_installed:
        return
    
    original_excepthook = threading.excepthook
    
    def ws_cleanup_excepthook(args):
        if args.exc_type == OSError and "Bad file descriptor" in str(args.exc_value):
            return
        original_excepthook(args)
    
    threading.excepthook = ws_cleanup_excepthook
    _ws_cleanup_hook_installed = True


def connect_public_ws(
    client: "BybitClient",
    channel_type: str = "linear",
    use_live_for_market_data: bool = False,
) -> WebSocket:
    """
    Connect to public WebSocket stream for market data.
    
    Args:
        client: BybitClient instance
        channel_type: Channel type (linear, inverse, spot, option)
        use_live_for_market_data: If True, use LIVE stream even when client is in DEMO mode
    """
    if client._ws_public is not None:
        return client._ws_public
    
    # Determine stream mode: LIVE or DEMO
    if use_live_for_market_data:
        ws_demo = False
        stream_type = "LIVE"
    else:
        ws_demo = client.use_demo
        stream_type = "DEMO" if client.use_demo else "LIVE"
    
    client._ws_public = WebSocket(
        testnet=False,
        demo=ws_demo,
        channel_type=channel_type,
        retries=5,
        restart_on_error=True,
        ping_interval=20,
        ping_timeout=10,
    )
    
    client.logger.info(f"Connected to public WebSocket ({channel_type}, {stream_type})")
    return client._ws_public


def connect_private_ws(client: "BybitClient") -> WebSocket:
    """Connect to private WebSocket stream for positions/orders."""
    if client._ws_private is not None:
        return client._ws_private
    
    if not client.api_key or not client.api_secret:
        raise ValueError("API credentials required for private WebSocket")
    
    client._ws_private = WebSocket(
        testnet=False,
        demo=client.use_demo,
        channel_type="private",
        api_key=client.api_key,
        api_secret=client.api_secret,
        retries=5,
        restart_on_error=True,
        ping_interval=20,
        ping_timeout=10,
    )
    
    # Only two modes: DEMO or LIVE
    stream_type = "DEMO (FAKE MONEY)" if client.use_demo else "LIVE (REAL MONEY)"
    
    client.logger.info(f"Connected to private WebSocket ({stream_type})")
    return client._ws_private


def subscribe_ticker(client: "BybitClient", symbol: str | list[str], callback: Callable):
    """Subscribe to ticker updates."""
    ws = connect_public_ws(client)
    ws.ticker_stream(symbol=symbol, callback=callback)
    client.logger.info(f"Subscribed to ticker: {symbol}")


def subscribe_orderbook(client: "BybitClient", symbol: str | list[str], callback: Callable, depth: int = 50):
    """Subscribe to orderbook updates."""
    ws = connect_public_ws(client)
    ws.orderbook_stream(depth=depth, symbol=symbol, callback=callback)
    client.logger.info(f"Subscribed to orderbook({depth}): {symbol}")


def subscribe_trades(client: "BybitClient", symbol: str | list[str], callback: Callable):
    """Subscribe to public trade stream."""
    ws = connect_public_ws(client)
    ws.trade_stream(symbol=symbol, callback=callback)
    client.logger.info(f"Subscribed to trades: {symbol}")


def subscribe_klines(client: "BybitClient", symbol: str | list[str], interval: int, callback: Callable):
    """Subscribe to kline/candlestick updates."""
    ws = connect_public_ws(client)
    ws.kline_stream(interval=interval, symbol=symbol, callback=callback)
    client.logger.info(f"Subscribed to klines({interval}): {symbol}")


def subscribe_positions(client: "BybitClient", callback: Callable):
    """Subscribe to position updates."""
    ws = connect_private_ws(client)
    ws.position_stream(callback=callback)
    client.logger.info("Subscribed to position updates")


def subscribe_orders(client: "BybitClient", callback: Callable):
    """Subscribe to order updates."""
    ws = connect_private_ws(client)
    ws.order_stream(callback=callback)
    client.logger.info("Subscribed to order updates")


def subscribe_executions(client: "BybitClient", callback: Callable):
    """Subscribe to execution/fill updates."""
    ws = connect_private_ws(client)
    ws.execution_stream(callback=callback)
    client.logger.info("Subscribed to execution updates")


def subscribe_wallet(client: "BybitClient", callback: Callable):
    """Subscribe to wallet/balance updates."""
    ws = connect_private_ws(client)
    ws.wallet_stream(callback=callback)
    client.logger.info("Subscribed to wallet updates")


def close_websockets(client: "BybitClient", suppress_errors: bool = True, wait_for_threads: float = 0.5):
    """Close all WebSocket connections gracefully."""
    import time
    
    if suppress_errors:
        _install_ws_cleanup_hook()
    
    if client._ws_public:
        try:
            client._ws_public.exit()
        except Exception:
            pass
        client._ws_public = None
    
    if client._ws_private:
        try:
            client._ws_private.exit()
        except Exception:
            pass
        client._ws_private = None
    
    if wait_for_threads > 0:
        time.sleep(wait_for_threads)
    
    client.logger.info("WebSocket connections closed")

