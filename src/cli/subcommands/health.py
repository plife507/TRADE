"""Health & diagnostics subcommand handlers for TRADE CLI.

Provides non-interactive CLI access to system health checks:
- exchange health check, connection test, rate limits, WebSocket status, API environment
"""

from __future__ import annotations

import json

from src.cli.utils import console


def handle_health_check(args) -> int:
    """Handle `health check` subcommand."""
    from src.tools.diagnostics_tools import exchange_health_check_tool

    symbol = getattr(args, "symbol", "BTCUSDT")
    result = exchange_health_check_tool(symbol=symbol)

    if not result.success and not result.data:
        console.print(f"[red]{result.error}[/]")
        return 1

    if getattr(args, "json_output", False):
        output = {
            "status": "pass" if result.success else "fail",
            "message": result.message,
            "data": result.data,
        }
        console.print(json.dumps(output, indent=2, default=str))
        return 0 if result.success else 1

    data = result.data or {}
    tests = data.get("tests", {})
    console.print(f"[bold]Health Check: {data.get('passed_count', 0)}/{data.get('total_count', 0)} passed[/]")
    for name, test in tests.items():
        icon = "[green]PASS[/]" if test.get("passed") else "[red]FAIL[/]"
        console.print(f"  {icon} {name}: {test.get('message', '')}")
    return 0 if result.success else 1


def handle_health_connection(args) -> int:
    """Handle `health connection` subcommand."""
    from src.tools.diagnostics_tools import test_connection_tool

    result = test_connection_tool()
    return _print_health_result(args, result)


def handle_health_rate_limit(args) -> int:
    """Handle `health rate-limit` subcommand."""
    from src.tools.diagnostics_tools import get_rate_limit_status_tool

    result = get_rate_limit_status_tool()
    return _print_health_result(args, result)


def handle_health_ws(args) -> int:
    """Handle `health ws` subcommand."""
    from src.tools.diagnostics_tools import get_websocket_status_tool

    result = get_websocket_status_tool()
    return _print_health_result(args, result)


def handle_health_environment(args) -> int:
    """Handle `health environment` subcommand."""
    from src.tools.diagnostics_tools import get_api_environment_tool

    result = get_api_environment_tool()
    return _print_health_result(args, result)


# ---------- helpers ----------

def _print_health_result(args, result) -> int:
    """Print health result as JSON or human-readable."""
    if getattr(args, "json_output", False):
        output = {
            "status": "pass" if result.success else "fail",
            "message": result.message if result.success else result.error,
            "data": result.data,
        }
        console.print(json.dumps(output, indent=2, default=str))
    else:
        if result.success:
            console.print(f"[green]{result.message}[/]")
        else:
            console.print(f"[red]{result.error or result.message}[/]")
    return 0 if result.success else 1
