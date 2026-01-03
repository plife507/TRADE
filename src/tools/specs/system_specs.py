"""
System/diagnostics tool specifications.

NO LEGACY FALLBACKS - Forward coding only.
"""


def get_imports():
    """Return dict of function_name -> import path."""
    from .. import (
        get_api_environment_tool,
        test_connection_tool,
        get_server_time_offset_tool,
        get_rate_limit_status_tool,
        get_websocket_status_tool,
        exchange_health_check_tool,
        is_healthy_for_trading_tool,
    )
    return {
        "get_api_environment": get_api_environment_tool,
        "test_connection": test_connection_tool,
        "get_server_time_offset": get_server_time_offset_tool,
        "get_rate_limit_status": get_rate_limit_status_tool,
        "get_websocket_status": get_websocket_status_tool,
        "exchange_health_check": exchange_health_check_tool,
        "is_healthy_for_trading": is_healthy_for_trading_tool,
    }


SPECS = [
    {
        "name": "get_api_environment",
        "description": "Get API environment info (trading mode, data mode, URLs, key status)",
        "category": "system.info",
        "parameters": {},
        "required": [],
    },
    {
        "name": "test_connection",
        "description": "Test exchange connection and return status",
        "category": "system.diagnostics",
        "parameters": {},
        "required": [],
    },
    {
        "name": "get_server_time_offset",
        "description": "Get time offset between local machine and exchange server",
        "category": "system.diagnostics",
        "parameters": {},
        "required": [],
    },
    {
        "name": "get_rate_limit_status",
        "description": "Get current rate limit status from exchange",
        "category": "system.diagnostics",
        "parameters": {},
        "required": [],
    },
    {
        "name": "get_websocket_status",
        "description": "Get detailed WebSocket connection status",
        "category": "system.diagnostics",
        "parameters": {},
        "required": [],
    },
    {
        "name": "exchange_health_check",
        "description": "Run comprehensive health check on exchange connection",
        "category": "system.diagnostics",
        "parameters": {
            "symbol": {"type": "string", "description": "Symbol to use for public API tests"},
        },
        "required": ["symbol"],
    },
    {
        "name": "is_healthy_for_trading",
        "description": "Quick health check for agents before trading",
        "category": "system.diagnostics",
        "parameters": {},
        "required": [],
    },
]
