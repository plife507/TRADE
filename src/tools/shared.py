"""
Shared types and utilities for the tools layer.

This module provides:
- ToolResult: Standard return type for all tools
- Common helper functions for lazy imports and data conversion
- Trading environment validation for agent/orchestrator calls

All tools should import ToolResult from this module.

NOTE on Trading Environment:
- All processes use the live Bybit API (shadow and live modes)
- Tools accept an optional `trading_env` parameter to VALIDATE intent
- This enables multi-process orchestration where agents route calls correctly
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, asdict
from typing import TYPE_CHECKING, Any

from ..config.constants import DataEnv

if TYPE_CHECKING:
    from ..core.exchange_manager import ExchangeManager
    from ..data.historical_data_store import HistoricalDataStore
    from ..data.realtime_state import RealtimeState


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

_em_lock = threading.Lock()


def _get_exchange_manager() -> "ExchangeManager":
    """
    Get the ExchangeManager singleton (lazy import).

    CLI-020: Uses double-checked locking to prevent race condition where
    two threads create duplicate ExchangeManager instances.

    NOTE: The returned ExchangeManager is configured for LIVE trading.
    Use `trading_env` parameter in tools only for VALIDATION, not switching.
    """
    from ..core.exchange_manager import ExchangeManager
    if not hasattr(_get_exchange_manager, "_instance"):
        with _em_lock:
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
        - mode: "LIVE"
        - api_endpoint: The API URL being used

    Use this to query what environment a process is configured for.
    """
    return {
        "mode": "LIVE",
        "api_endpoint": "api.bybit.com",
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
        trading_env: Optional trading environment ("live").
                     If None, returns the manager without validation.
                     If provided, validates that it equals "live".

    Returns:
        ExchangeManager instance if validation passes

    Raises:
        TradingEnvMismatchError: If trading_env is not "live"
        ValueError: If trading_env is invalid
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

    # Only LIVE is supported
    if normalized_env != "live":
        raise TradingEnvMismatchError(
            f"Requested trading_env='{normalized_env}' but only 'live' is supported."
        )

    return manager


def validate_trading_env_or_error(trading_env: str | None = None) -> ToolResult | None:
    """
    Validate trading_env and return a ToolResult error if mismatched.

    This is a convenience wrapper for use in tools. Instead of try/except,
    tools can call this and return early if there's an error.

    Pattern: Agents specify their intended environment ("live"), and this
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
    """Check if WebSocket is connected and receiving non-stale data.

    Under lazy WS, returning False is the expected default --- callers fall
    through to REST. WS only connects when a play is running.

    DATA-003: Also checks ticker staleness so that a connected-but-silent
    WebSocket (e.g., dropped subscription) is treated as disconnected.
    """
    try:
        state = _get_realtime_state()
        priv_status = state.get_private_ws_status()
        if not priv_status.is_connected:
            return False
        # DATA-003: Check data freshness — connected but stale = not healthy
        if state.is_account_metrics_stale(max_age_seconds=60.0):
            return False
        return True
    except Exception:
        return False


def _get_historical_store(env: DataEnv = "live") -> "HistoricalDataStore":
    """
    Get the HistoricalDataStore singleton for a given environment (lazy import).

    Args:
        env: Data environment ("live"). Defaults to "live".

    Returns:
        HistoricalDataStore instance for the specified environment.
    """
    from ..data.historical_data_store import get_historical_store
    return get_historical_store(env=env)
