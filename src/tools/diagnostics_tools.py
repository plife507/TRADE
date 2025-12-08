"""
Diagnostics and connection testing tools for TRADE trading bot.

These tools provide exchange connection testing, health checks, and status reporting.
"""

from typing import Optional, Dict, Any
from .shared import ToolResult, _get_exchange_manager, _get_realtime_state
from src.config.config import get_config


def test_connection_tool() -> ToolResult:
    """
    Test exchange connection and return comprehensive status.
    
    Returns:
        ToolResult with connection status, environment info, and balances
    """
    try:
        exchange = _get_exchange_manager()
        result = exchange.test_connection()
        
        is_demo = result.get("demo_mode", True)
        env = "DEMO (fake money)" if is_demo else "LIVE (real money)"
        
        # Determine success - public must work, private should work if key is configured
        public_ok = result.get("public_ok", False)
        private_ok = result.get("private_ok")
        is_success = public_ok and (private_ok is None or private_ok is True)
        
        # Collect any errors for display
        errors = []
        if result.get("error"):
            errors.append(f"Public API: {result.get('error')}")
        if result.get("private_error"):
            errors.append(f"Private API: {result.get('private_error')}")
        error_msg = "; ".join(errors) if errors else None
        
        # Build status message
        if is_success:
            message = f"✓ Connected to {env}"
        elif not public_ok:
            message = f"✗ Cannot reach Bybit API ({env})"
        else:
            message = f"✗ Public API OK but private API failed ({env})"
        
        return ToolResult(
            success=is_success,
            message=message,
            error=error_msg,
            data={
                "environment": env,
                "is_demo": is_demo,
                "base_url": result.get("base_url"),
                "public_ok": public_ok,
                "private_ok": private_ok,
                "btc_price": result.get("btc_price"),
                "usdt_balance": result.get("usdt_balance"),
                "error": result.get("error"),
                "private_error": result.get("private_error"),
            },
            source="rest_api",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Connection test failed: {str(e)}",
        )


def get_server_time_offset_tool() -> ToolResult:
    """
    Get the time offset between local machine and exchange server.
    
    Returns:
        ToolResult with offset in milliseconds and sync status
    """
    try:
        exchange = _get_exchange_manager()
        offset = exchange.get_server_time_offset()
        
        is_synced = abs(offset) < 5000  # Within 5 seconds
        
        # Check if clock is ahead (which causes ErrCode 10002)
        clock_ahead = offset < -1000
        
        return ToolResult(
            success=True,
            message=f"Time offset: {offset}ms ({'synced' if is_synced else 'NOT synced'})",
            data={
                "offset_ms": offset,
                "is_synced": is_synced,
                "threshold_ms": 5000,
                "clock_ahead_warning": clock_ahead,
            },
            source="rest_api",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Failed to get server time: {str(e)}",
        )


def get_rate_limit_status_tool() -> ToolResult:
    """
    Get current rate limit status from the exchange.
    
    Returns:
        ToolResult with remaining requests and limit info
    """
    try:
        exchange = _get_exchange_manager()
        status = exchange.get_rate_limit_status()
        
        # Handle None values safely (before any API request completes)
        remaining = status.get("remaining")
        limit = status.get("limit")
        
        # Convert to int if present, else -1
        try:
            remaining_int = int(remaining) if remaining is not None else -1
        except (ValueError, TypeError):
            remaining_int = -1
        
        try:
            limit_int = int(limit) if limit is not None else -1
        except (ValueError, TypeError):
            limit_int = -1
        
        if remaining_int >= 0 and limit_int >= 0:
            is_healthy = remaining_int > 5
            return ToolResult(
                success=True,
                message=f"Rate limit: {remaining_int}/{limit_int} remaining",
                data={
                    "remaining": remaining_int,
                    "limit": limit_int,
                    "is_healthy": is_healthy,
                    "raw": status,
                },
                source="rest_api",
            )
        else:
            return ToolResult(
                success=True,
                message="Rate limit status not available yet",
                data={"available": False, "raw": status},
                source="rest_api",
            )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Failed to get rate limit status: {str(e)}",
        )


def get_ticker_tool(symbol: str) -> ToolResult:
    """
    Get ticker data for a symbol (for diagnostics/connection testing).
    
    Args:
        symbol: Trading symbol
    
    Returns:
        ToolResult with ticker data including last price
    """
    if not symbol or not isinstance(symbol, str):
        return ToolResult(success=False, error="Invalid symbol parameter")
    
    try:
        exchange = _get_exchange_manager()
        ticker = exchange.bybit.get_ticker(symbol)
        
        price = ticker.get("lastPrice", "N/A")
        
        return ToolResult(
            success=True,
            symbol=symbol,
            message=f"{symbol}: ${float(price):,.2f}" if price != "N/A" else f"{symbol}: N/A",
            data={
                "symbol": symbol,
                "last_price": float(price) if price != "N/A" else None,
                "raw": ticker,
            },
            source="rest_api",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Failed to get ticker: {str(e)}",
        )


def get_websocket_status_tool() -> ToolResult:
    """
    Get detailed WebSocket connection status.
    
    Returns:
        ToolResult with public/private connection status and data stats
    """
    try:
        state = _get_realtime_state()
        
        pub_status = state.get_public_ws_status()
        priv_status = state.get_private_ws_status()
        stats = state.get_stats()
        
        ws_connected = pub_status.is_connected or priv_status.is_connected
        using_rest_fallback = not ws_connected
        
        if ws_connected:
            status_msg = "WebSocket connected"
        else:
            status_msg = "Using REST API fallback"
        
        return ToolResult(
            success=True,
            message=status_msg,
            data={
                "websocket_connected": ws_connected,
                "using_rest_fallback": using_rest_fallback,
                "healthy": True,  # Either WS or REST works
                "public": {
                    "is_connected": pub_status.is_connected,
                    "uptime_seconds": pub_status.uptime_seconds,
                    "reconnect_count": pub_status.reconnect_count,
                    "last_error": pub_status.last_error,
                },
                "private": {
                    "is_connected": priv_status.is_connected,
                    "uptime_seconds": priv_status.uptime_seconds,
                    "reconnect_count": priv_status.reconnect_count,
                    "last_error": priv_status.last_error,
                },
                "stats": {
                    "ticker_count": stats.get("ticker_count", 0),
                    "orderbook_count": stats.get("orderbook_count", 0),
                    "position_count": stats.get("position_count", 0),
                    "open_order_count": stats.get("open_order_count", 0),
                    "event_queue_size": stats.get("event_queue_size", 0),
                    "update_counts": stats.get("update_counts", {}),
                },
            },
            source="websocket" if ws_connected else "rest_api",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Failed to get WebSocket status: {str(e)}",
        )


def is_healthy_for_trading_tool() -> ToolResult:
    """
    Quick health check for agents before trading.
    
    Returns True if the system is healthy enough for trading operations.
    Works with both WebSocket and REST API fallback.
    
    Use this before placing orders to ensure connectivity.
    """
    try:
        # Try REST API first (most reliable check)
        exchange = _get_exchange_manager()
        result = exchange.test_connection()
        
        is_healthy = result.get("public_ok", False)
        
        # Check WebSocket status
        state = _get_realtime_state()
        pub_status = state.get_public_ws_status()
        priv_status = state.get_private_ws_status()
        ws_connected = pub_status.is_connected or priv_status.is_connected
        
        return ToolResult(
            success=is_healthy,
            message="System healthy for trading" if is_healthy else "System NOT healthy for trading",
            data={
                "healthy": is_healthy,
                "websocket_connected": ws_connected,
                "rest_api_ok": result.get("public_ok", False),
                "private_api_ok": result.get("private_ok", False),
                "data_source": "websocket" if ws_connected else "rest_api",
            },
            source="rest_api",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            message="System NOT healthy for trading",
            error=f"Health check failed: {str(e)}",
            data={"healthy": False},
        )


def exchange_health_check_tool(symbol: str) -> ToolResult:
    """
    Run a comprehensive health check on the exchange connection.
    
    Tests: public API, private API, time sync, rate limits.
    
    Args:
        symbol: Symbol to use for public API tests
    
    Returns:
        ToolResult with all test results
    """
    if not symbol or not isinstance(symbol, str):
        return ToolResult(
            success=False,
            error="Invalid symbol parameter - provide a valid symbol like 'BTCUSDT'",
        )
    
    tests = {}
    
    # Test 1: Public API (ticker)
    try:
        exchange = _get_exchange_manager()
        ticker = exchange.bybit.get_ticker(symbol)
        price = ticker.get("lastPrice", "N/A")
        tests["public_api"] = {
            "passed": True,
            "message": f"Connected ({symbol}: ${float(price):,.2f})" if price != "N/A" else "Connected",
        }
    except Exception as e:
        tests["public_api"] = {"passed": False, "message": str(e)}
    
    # Test 2: Private API (balance)
    try:
        exchange = _get_exchange_manager()
        balance = exchange.get_balance()
        total = balance.get("total", 0)
        tests["private_api"] = {
            "passed": True,
            "message": f"Authenticated (Balance: ${total:,.2f})",
        }
    except Exception as e:
        tests["private_api"] = {"passed": False, "message": str(e)}
    
    # Test 3: Time sync
    try:
        exchange = _get_exchange_manager()
        offset = exchange.get_server_time_offset()
        is_synced = abs(offset) < 5000
        tests["time_sync"] = {
            "passed": is_synced,
            "message": f"{'Synced' if is_synced else 'Large offset'} ({offset}ms)",
        }
    except Exception as e:
        tests["time_sync"] = {"passed": False, "message": str(e)}
    
    # Test 4: Rate limits
    try:
        exchange = _get_exchange_manager()
        status = exchange.get_rate_limit_status()
        remaining = status.get("remaining")
        limit = status.get("limit")
        # Handle None values safely
        try:
            remaining_int = int(remaining) if remaining is not None else -1
        except (ValueError, TypeError):
            remaining_int = -1
        try:
            limit_int = int(limit) if limit is not None else -1
        except (ValueError, TypeError):
            limit_int = -1
            
        if remaining_int >= 0 and limit_int >= 0:
            tests["rate_limits"] = {
                "passed": remaining_int > 5,
                "message": f"OK ({remaining_int}/{limit_int} remaining)",
            }
        else:
            tests["rate_limits"] = {
                "passed": True,
                "message": "Status not available yet",
            }
    except Exception as e:
        tests["rate_limits"] = {"passed": False, "message": str(e)}
    
    # Test 5: Connection test method
    try:
        exchange = _get_exchange_manager()
        conn_result = exchange.test_connection()
        env = "DEMO" if conn_result.get("demo_mode") else "LIVE"
        pub_ok = "✓" if conn_result.get("public_ok") else "✗"
        priv_ok = "✓" if conn_result.get("private_ok") else "✗"
        tests["connection_test"] = {
            "passed": conn_result.get("public_ok") and conn_result.get("private_ok", True),
            "message": f"{env} - Public: {pub_ok}, Private: {priv_ok}",
        }
    except Exception as e:
        tests["connection_test"] = {"passed": False, "message": str(e)}
    
    # Summary
    passed_count = sum(1 for t in tests.values() if t["passed"])
    total_count = len(tests)
    all_passed = passed_count == total_count
    
    # Get API environment info (all 4 legs)
    try:
        config = get_config()
        api_env = config.bybit.get_api_environment_summary()
        api_environment = {
            "trading_mode": api_env["trading"]["mode"],
            "trading_base_url": api_env["trading"]["base_url"],
            "trade_live_configured": api_env["trade_live"]["key_configured"],
            "trade_demo_configured": api_env["trade_demo"]["key_configured"],
            "data_live_configured": api_env["data_live"]["key_configured"],
            "data_demo_configured": api_env["data_demo"]["key_configured"],
            "websocket_mode": api_env["websocket"]["mode"],
        }
    except Exception:
        api_environment = {}
    
    return ToolResult(
        success=all_passed,
        message=f"Health check: {passed_count}/{total_count} passed",
        data={
            "tests": tests,
            "passed_count": passed_count,
            "total_count": total_count,
            "all_passed": all_passed,
            "api_environment": api_environment,
        },
        source="rest_api",
    )


def get_api_environment_tool() -> ToolResult:
    """
    Get comprehensive API environment information for all 4 legs.
    
    The system has 4 independent API legs:
    - Trade LIVE: Real money trading (api.bybit.com)
    - Trade DEMO: Fake money trading (api-demo.bybit.com)
    - Data LIVE: Canonical historical data for backtesting (api.bybit.com)
    - Data DEMO: Demo-only history for demo validation (api-demo.bybit.com)
    
    Returns:
        ToolResult with all 4 leg statuses and current active mode
    """
    try:
        config = get_config()
        env = config.bybit.get_api_environment_summary()
        
        # Current active trading mode
        trading = env["trading"]
        websocket = env["websocket"]
        safety = env["safety"]
        
        # All 4 legs
        trade_live = env["trade_live"]
        trade_demo = env["trade_demo"]
        data_live = env["data_live"]
        data_demo = env["data_demo"]
        
        # Build status indicators
        tl = "✓" if trade_live["key_configured"] else "✗"
        td = "✓" if trade_demo["key_configured"] else "✗"
        dl = "✓" if data_live["key_configured"] else "✗"
        dd = "✓" if data_demo["key_configured"] else "✗"
        
        trading_status = f"Active Trading: {trading['mode']} ({trading['base_url']})"
        legs_status = f"Keys: Trade[L:{tl} D:{td}] Data[L:{dl} D:{dd}]"
        
        if safety["mode_consistent"]:
            safety_msg = "OK"
        else:
            safety_msg = safety["messages"][0] if safety["messages"] else "Issues detected"
        
        return ToolResult(
            success=True,
            message=f"{trading_status} | {legs_status}",
            data={
                # Current active trading mode (CLI and docs expect "trading")
                "trading": {
                    "mode": trading["mode"],
                    "base_url": trading["base_url"],
                    "key_configured": trading["key_configured"],
                    "is_demo": trading["is_demo"],
                    "is_live": trading["is_live"],
                },
                # Legacy "data" key for CLI compatibility (shows LIVE data only)
                "data": {
                    "mode": "LIVE",
                    "base_url": data_live["base_url"],
                    "key_configured": data_live["key_configured"],
                    "key_source": data_live["key_source"],
                },
                # All 4 legs explicitly
                "trade_live": {
                    "base_url": trade_live["base_url"],
                    "key_configured": trade_live["key_configured"],
                    "key_source": trade_live["key_source"],
                },
                "trade_demo": {
                    "base_url": trade_demo["base_url"],
                    "key_configured": trade_demo["key_configured"],
                    "key_source": trade_demo["key_source"],
                },
                "data_live": {
                    "base_url": data_live["base_url"],
                    "key_configured": data_live["key_configured"],
                    "key_source": data_live["key_source"],
                    "purpose": data_live["purpose"],
                },
                "data_demo": {
                    "base_url": data_demo["base_url"],
                    "key_configured": data_demo["key_configured"],
                    "key_source": data_demo["key_source"],
                    "purpose": data_demo["purpose"],
                },
                # WebSocket
                "websocket": {
                    "mode": websocket["mode"],
                    "public_url": websocket["public_url"],
                    "private_url": websocket["private_url"],
                },
                # Safety
                "safety": {
                    "mode_consistent": safety["mode_consistent"],
                    "messages": safety["messages"],
                },
            },
            source="config",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Failed to get API environment: {str(e)}",
        )

