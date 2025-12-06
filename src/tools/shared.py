"""
Shared types and utilities for the tools layer.

This module provides:
- ToolResult: Standard return type for all tools
- Common helper functions for lazy imports and data conversion

All tools should import ToolResult from this module.
"""

from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any


@dataclass
class ToolResult:
    """
    Standard return type for all tools.
    
    Attributes:
        success: Whether the operation succeeded
        message: Human-readable success/info message
        symbol: Trading symbol (when applicable)
        data: Structured data payload (positions, order info, etc.)
        error: Error message if success=False
        source: Data source ("websocket" or "rest_api")
    """
    success: bool
    message: str = ""
    symbol: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    source: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


# ==============================================================================
# Lazy Import Helpers (Avoid Circular Dependencies)
# ==============================================================================

def _get_exchange_manager():
    """Get the ExchangeManager singleton (lazy import)."""
    from ..core.exchange_manager import ExchangeManager
    if not hasattr(_get_exchange_manager, "_instance"):
        _get_exchange_manager._instance = ExchangeManager()
    return _get_exchange_manager._instance


def _get_realtime_state():
    """Get the RealtimeState singleton (lazy import)."""
    from ..data.realtime_state import get_realtime_state
    return get_realtime_state()


def _is_websocket_connected() -> bool:
    """Check if WebSocket is connected and receiving data."""
    try:
        state = _get_realtime_state()
        priv_status = state.get_private_ws_status()
        return priv_status.is_connected
    except Exception:
        return False


# Track WebSocket startup attempts to avoid repeated failures
_ws_startup_failed = False
_ws_startup_attempt_time = 0


def _ensure_websocket_running() -> bool:
    """
    Ensure WebSocket is running, starting it if necessary.
    
    This is used by tools that need WebSocket data. If WebSocket is not
    running and auto_start is enabled, it will start the WebSocket.
    
    Includes cooldown to prevent repeated startup attempts that flood logs.
    
    Returns:
        True if WebSocket is now connected, False otherwise
    """
    global _ws_startup_failed, _ws_startup_attempt_time
    import time
    
    # First check if already connected
    if _is_websocket_connected():
        _ws_startup_failed = False  # Reset on success
        return True
    
    # If we've recently failed, don't retry (60s cooldown)
    if _ws_startup_failed:
        if time.time() - _ws_startup_attempt_time < 60:
            return False  # Silent fallback to REST
        # Reset after cooldown
        _ws_startup_failed = False
    
    # Try to start via Application
    try:
        from ..core.application import get_application
        from ..config.config import get_config
        
        config = get_config()
        
        # Only auto-start if WebSocket is enabled
        if not config.websocket.enable_websocket:
            return False
        
        app = get_application()
        
        # If app not initialized, initialize it
        if not app.is_initialized:
            if not app.initialize():
                _ws_startup_failed = True
                _ws_startup_attempt_time = time.time()
                return False
        
        # If app not running (WebSocket not started), start it
        if not app.is_running:
            result = app.start()
            if not result:
                _ws_startup_failed = True
                _ws_startup_attempt_time = time.time()
            # start() already attempts WebSocket, so check if connected now
            return _is_websocket_connected()
        
        # App is running but WebSocket might not be - try to start it
        if not _is_websocket_connected():
            result = app.start_websocket()
            if not result:
                _ws_startup_failed = True
                _ws_startup_attempt_time = time.time()
            return result
        
        return True
        
    except Exception:
        _ws_startup_failed = True
        _ws_startup_attempt_time = time.time()
        return False


def _get_data_source() -> str:
    """
    Get the current data source being used.
    
    Returns:
        "websocket" if WebSocket is connected, "rest_api" otherwise
    """
    return "websocket" if _is_websocket_connected() else "rest_api"


def _get_historical_store():
    """Get the HistoricalDataStore singleton (lazy import)."""
    from ..data.historical_data_store import get_historical_store
    return get_historical_store()


def _get_global_risk_view():
    """Get the GlobalRiskView singleton (lazy import)."""
    from ..risk import get_global_risk_view
    return get_global_risk_view()


def _ensure_symbol_subscribed(symbol: str) -> bool:
    """
    Ensure a symbol has WebSocket subscription for market data.
    
    Call this before trading a symbol to get real-time updates.
    If WebSocket is not available, returns False (REST fallback will be used).
    
    Args:
        symbol: Symbol to ensure subscription for (e.g., "SOLUSDT")
        
    Returns:
        True if subscribed (or will be), False if WebSocket unavailable
    """
    try:
        from ..data.realtime_bootstrap import get_realtime_bootstrap
        
        bootstrap = get_realtime_bootstrap()
        if bootstrap and bootstrap._running:
            return bootstrap.ensure_symbol_subscribed(symbol)
        return False
        
    except Exception:
        return False


def _get_realtime_bootstrap():
    """Get the RealtimeBootstrap singleton (lazy import)."""
    try:
        from ..data.realtime_bootstrap import get_realtime_bootstrap
        return get_realtime_bootstrap()
    except Exception:
        return None
