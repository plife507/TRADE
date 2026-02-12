"""
Shared types and utilities for the tools layer.

This module provides:
- ToolResult: Standard return type for all tools
- Common helper functions for lazy imports and data conversion
- Trading environment validation for agent/orchestrator calls

All tools should import ToolResult from this module.

NOTE on Trading Environment:
- A running process has a FIXED trading env (DEMO or LIVE) set at startup
- Tools accept an optional `trading_env` parameter to VALIDATE intent
- If the caller's requested env doesn't match the process, tools return an error
- This enables multi-process orchestration where agents route calls correctly
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import TYPE_CHECKING, Any

from ..config.constants import DataEnv  # noqa: F401 - used in type annotations

if TYPE_CHECKING:
    from ..core.exchange_manager import ExchangeManager
    from ..data.historical_data_store import HistoricalDataStore
    from ..data.realtime_bootstrap import RealtimeBootstrap
    from ..data.realtime_state import RealtimeState
    from ..risk.global_risk import GlobalRiskView


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
    symbol: str | None = None
    data: dict[str, Any] | None = None
    error: str | None = None
    source: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


# ==============================================================================
# Lazy Import Helpers (Avoid Circular Dependencies)
# ==============================================================================

def _get_exchange_manager() -> "ExchangeManager":
    """
    Get the ExchangeManager singleton (lazy import).

    NOTE: Per-process trading env is fixed at startup. The returned ExchangeManager
    is either configured for DEMO or LIVE based on BYBIT_USE_DEMO and TRADING_MODE.
    Use `trading_env` parameter in tools only for VALIDATION, not switching.
    """
    from ..core.exchange_manager import ExchangeManager
    if not hasattr(_get_exchange_manager, "_instance"):
        _get_exchange_manager._instance = ExchangeManager()
    return _get_exchange_manager._instance


# ==============================================================================
# Trading Environment Validation (Agent/Orchestrator Support)
# ==============================================================================

def get_trading_env_summary() -> dict[str, Any]:
    """
    Get summary of the current process's trading environment.
    
    Returns:
        Dict with keys:
        - mode: "DEMO" or "LIVE"
        - use_demo: bool (config.bybit.use_demo)
        - trading_mode: "paper" or "real" (config.trading.mode)
        - api_endpoint: The API URL being used
        
    Use this to query what environment a process is configured for.
    """
    from ..config.config import get_config
    
    config = get_config()
    use_demo = config.bybit.use_demo
    trading_mode = str(config.trading.mode)
    
    return {
        "mode": "DEMO" if use_demo else "LIVE",
        "use_demo": use_demo,
        "trading_mode": trading_mode,
        "api_endpoint": "api-demo.bybit.com" if use_demo else "api.bybit.com",
    }


class TradingEnvMismatchError(Exception):
    """Raised when a tool's trading_env doesn't match the process config."""
    pass


def _get_exchange_manager_for_env(trading_env: str | None = None) -> "ExchangeManager":
    """
    Get the ExchangeManager singleton, validating against the requested trading_env.

    This function enables agents/orchestrators to assert they're talking to the
    correct environment. It does NOT switch environments - it only validates.

    Args:
        trading_env: Optional trading environment ("demo" or "live").
                     If None, returns the manager without validation.
                     If provided, validates against the process's configured env.

    Returns:
        ExchangeManager instance if validation passes

    Raises:
        TradingEnvMismatchError: If trading_env doesn't match process config
        ValueError: If trading_env is invalid

    Usage:
        # Agent calling for DEMO trading
        manager = _get_exchange_manager_for_env("demo")

        # If this process is configured for LIVE, raises TradingEnvMismatchError
        # with a clear message explaining the mismatch
    """
    manager = _get_exchange_manager()
    
    # If no trading_env specified, return without validation
    if trading_env is None:
        return manager
    
    # Validate trading_env value
    from ..config.constants import validate_trading_env
    try:
        normalized_env = validate_trading_env(trading_env)
    except ValueError as e:
        raise ValueError(f"Invalid trading_env: {e}")
    
    # Get current process config
    env_summary = get_trading_env_summary()
    process_env = "demo" if env_summary["use_demo"] else "live"
    
    # Check for mismatch
    if normalized_env != process_env:
        raise TradingEnvMismatchError(
            f"Requested trading_env='{normalized_env}' but this process is configured "
            f"for {env_summary['mode']} (use_demo={env_summary['use_demo']}, "
            f"trading_mode={env_summary['trading_mode']}). "
            f"To use {normalized_env.upper()}, start a process with the appropriate "
            f"BYBIT_USE_DEMO and TRADING_MODE settings."
        )
    
    return manager


def validate_trading_env_or_error(trading_env: str | None = None) -> ToolResult | None:
    """
    Validate trading_env and return a ToolResult error if mismatched.

    This is a convenience wrapper for use in tools. Instead of try/except,
    tools can call this and return early if there's an error.

    Pattern: Agents specify their intended environment ("demo"/"live"), and this
    validates against the process config. Prevents routing errors in multi-process setups.

    Args:
        trading_env: Optional trading environment to validate

    Returns:
        None if validation passes (or trading_env is None)
        ToolResult with success=False if there's a mismatch

    Usage in a tool:
        def my_trading_tool(symbol: str, trading_env: str | None = None):
            if error := validate_trading_env_or_error(trading_env):
                return error
            # ... proceed with tool logic
    """
    if trading_env is None:
        return None
    
    try:
        _get_exchange_manager_for_env(trading_env)
        return None
    except TradingEnvMismatchError as e:
        return ToolResult(
            success=False,
            error=str(e),
        )
    except ValueError as e:
        return ToolResult(
            success=False,
            error=str(e),
        )


def _get_realtime_state() -> "RealtimeState":
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
_ws_startup_attempt_time = 0.0


def _ensure_websocket_running() -> bool:
    """
    Ensure WebSocket is running, starting it if necessary.

    This is used by tools that need WebSocket data. If WebSocket is not
    running and auto_start is enabled, it will start the WebSocket.

    Includes 60-second cooldown to prevent repeated startup attempts that flood logs.
    Falls back silently to REST on failure.

    Returns:
        True if WebSocket is now connected, False otherwise (use REST fallback)
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

    except Exception as e:
        import logging
        logging.getLogger(__name__).debug(f"WebSocket startup failed: {e}")
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


def _get_historical_store(env: DataEnv = "live") -> "HistoricalDataStore":
    """
    Get the HistoricalDataStore singleton for a given environment (lazy import).

    Args:
        env: Data environment ("live" or "demo"). Defaults to "live".

    Returns:
        HistoricalDataStore instance for the specified environment.
    """
    from ..data.historical_data_store import get_historical_store
    return get_historical_store(env=env)


def _get_global_risk_view() -> "GlobalRiskView":
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

    except Exception as e:
        import logging
        logging.getLogger(__name__).debug(f"Symbol subscription failed: {e}")
        return False


def _get_realtime_bootstrap() -> "RealtimeBootstrap | None":
    """Get the RealtimeBootstrap singleton (lazy import)."""
    try:
        from ..data.realtime_bootstrap import get_realtime_bootstrap
        return get_realtime_bootstrap()
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug(f"RealtimeBootstrap not available: {e}")
        return None
