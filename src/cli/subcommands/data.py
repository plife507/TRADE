"""Data subcommand handlers for TRADE CLI.

Provides non-interactive CLI access to DuckDB historical data operations:
- sync, info, symbols, status, summary, query, heal, vacuum, delete
"""

from __future__ import annotations

import json
from datetime import datetime

from src.cli.utils import console


def _parse_period_to_code(period_str: str) -> str:
    """Convert user-friendly period (30d, 3M, 1Y) to store period code."""
    s = period_str.strip().lower()
    if s.endswith("d"):
        days = int(s[:-1])
        if days <= 1:
            return "1D"
        elif days <= 7:
            return "1W"
        elif days <= 30:
            return "1M"
        elif days <= 90:
            return "3M"
        elif days <= 180:
            return "6M"
        else:
            return "1Y"
    elif s.endswith("m"):
        months = int(s[:-1])
        if months <= 1:
            return "1M"
        elif months <= 3:
            return "3M"
        elif months <= 6:
            return "6M"
        else:
            return "1Y"
    elif s.endswith("y"):
        return "1Y"
    return s.upper()


def handle_data_sync(args) -> int:
    """Handle `data sync` subcommand."""
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if not symbols:
        console.print("[red]No symbols provided[/]")
        return 1

    start = getattr(args, "start", None)
    end = getattr(args, "end", None)

    if start and end:
        from src.tools.data_tools import sync_range_tool
        result = sync_range_tool(
            symbols=symbols,
            start=datetime.fromisoformat(start),
            end=datetime.fromisoformat(end),
        )
    else:
        from src.tools.data_tools import sync_symbols_tool
        period_code = _parse_period_to_code(getattr(args, "period", "30d"))
        result = sync_symbols_tool(symbols=symbols, period=period_code)

    if getattr(args, "heal", False) and result.success:
        from src.tools.data_tools import heal_data_tool
        for sym in symbols:
            heal_result = heal_data_tool(symbol=sym)
            if not heal_result.success:
                console.print(f"[yellow]Heal warning for {sym}: {heal_result.error}[/]")

    return _print_data_result(args, result)


def handle_data_info(args) -> int:
    """Handle `data info` subcommand."""
    from src.tools.data_tools import get_database_stats_tool
    result = get_database_stats_tool()
    return _print_data_result(args, result)


def handle_data_symbols(args) -> int:
    """Handle `data symbols` subcommand."""
    from src.tools.data_tools import list_cached_symbols_tool
    result = list_cached_symbols_tool()

    if not result.success:
        console.print(f"[red]{result.error}[/]")
        return 1

    if getattr(args, "json_output", False):
        console.print(json.dumps(result.data, indent=2, default=str))
        return 0

    symbols = (result.data or {}).get("symbols", [])
    if not symbols:
        console.print("[dim]No cached symbols.[/]")
        return 0

    console.print(f"[bold]Cached Symbols ({len(symbols)}):[/]")
    for sym in symbols:
        console.print(f"  {sym}")
    return 0


def handle_data_status(args) -> int:
    """Handle `data status` subcommand."""
    from src.tools.data_tools import get_symbol_status_tool
    result = get_symbol_status_tool(symbol=args.symbol.upper())
    return _print_data_result(args, result)


def handle_data_summary(args) -> int:
    """Handle `data summary` subcommand."""
    from src.tools.data_tools import get_symbol_summary_tool
    result = get_symbol_summary_tool()
    return _print_data_result(args, result)


def handle_data_query(args) -> int:
    """Handle `data query` subcommand."""
    from src.tools.data_tools import get_ohlcv_history_tool
    result = get_ohlcv_history_tool(
        symbol=args.symbol.upper(),
        timeframe=getattr(args, "tf", "1m"),
        period=getattr(args, "period", None),
        start=getattr(args, "start", None),
        end=getattr(args, "end", None),
        limit=getattr(args, "limit", None),
    )
    return _print_data_result(args, result)


def handle_data_heal(args) -> int:
    """Handle `data heal` subcommand."""
    from src.tools.data_tools import heal_data_tool
    symbol = getattr(args, "symbol", None)
    if symbol:
        symbol = symbol.upper()
    result = heal_data_tool(symbol=symbol)
    return _print_data_result(args, result)


def handle_data_vacuum(args) -> int:
    """Handle `data vacuum` subcommand."""
    from src.tools.data_tools import vacuum_database_tool
    result = vacuum_database_tool()
    return _print_data_result(args, result)


def handle_data_delete(args) -> int:
    """Handle `data delete` subcommand."""
    from src.tools.data_tools import delete_symbol_tool
    result = delete_symbol_tool(symbol=args.symbol.upper())
    return _print_data_result(args, result)


# ---------- helpers ----------

def _print_data_result(args, result) -> int:
    """Print data result as JSON or human-readable."""
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
            console.print(f"[red]{result.error}[/]")
    return 0 if result.success else 1
