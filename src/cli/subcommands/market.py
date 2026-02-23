"""Market data subcommand handlers for TRADE CLI.

Provides non-interactive CLI access to live market data:
- price, ohlcv, funding, open interest, orderbook, instruments
"""

from __future__ import annotations

import json

from src.cli.utils import console


def handle_market_price(args) -> int:
    """Handle `market price` subcommand."""
    from src.tools.market_data_tools import get_price_tool

    result = get_price_tool(symbol=args.symbol.upper())

    if not result.success:
        console.print(f"[red]{result.error}[/]")
        return 1

    if getattr(args, "json_output", False):
        console.print(json.dumps(result.data, indent=2, default=str))
    else:
        console.print(f"[bold]{result.message}[/]")
    return 0


def handle_market_ohlcv(args) -> int:
    """Handle `market ohlcv` subcommand."""
    from src.tools.market_data_tools import get_ohlcv_tool

    result = get_ohlcv_tool(
        symbol=args.symbol.upper(),
        interval=getattr(args, "tf", "15"),
        limit=getattr(args, "limit", 100),
    )

    if not result.success:
        console.print(f"[red]{result.error}[/]")
        return 1

    if getattr(args, "json_output", False):
        console.print(json.dumps(result.data, indent=2, default=str))
    else:
        console.print(f"[green]{result.message}[/]")
    return 0


def handle_market_funding(args) -> int:
    """Handle `market funding` subcommand."""
    from src.tools.market_data_tools import get_funding_rate_tool

    result = get_funding_rate_tool(symbol=args.symbol.upper())

    if not result.success:
        console.print(f"[red]{result.error}[/]")
        return 1

    if getattr(args, "json_output", False):
        console.print(json.dumps(result.data, indent=2, default=str))
    else:
        console.print(f"[bold]{result.message}[/]")
    return 0


def handle_market_oi(args) -> int:
    """Handle `market oi` subcommand."""
    from src.tools.market_data_tools import get_open_interest_tool

    result = get_open_interest_tool(symbol=args.symbol.upper())

    if not result.success:
        console.print(f"[red]{result.error}[/]")
        return 1

    if getattr(args, "json_output", False):
        console.print(json.dumps(result.data, indent=2, default=str))
    else:
        console.print(f"[bold]{result.message}[/]")
    return 0


def handle_market_orderbook(args) -> int:
    """Handle `market orderbook` subcommand."""
    from src.tools.market_data_tools import get_orderbook_tool

    depth = getattr(args, "depth", 25)
    result = get_orderbook_tool(symbol=args.symbol.upper(), limit=depth)

    if not result.success:
        console.print(f"[red]{result.error}[/]")
        return 1

    if getattr(args, "json_output", False):
        console.print(json.dumps(result.data, indent=2, default=str))
        return 0

    data = result.data or {}
    best_bid = data.get("best_bid")
    best_ask = data.get("best_ask")
    spread = data.get("spread")

    console.print(f"[bold]{args.symbol.upper()} Orderbook[/]")
    if best_bid:
        console.print(f"  Best bid: ${best_bid:,.2f}")
    if best_ask:
        console.print(f"  Best ask: ${best_ask:,.2f}")
    if spread is not None:
        console.print(f"  Spread:   ${spread:,.4f}")
    console.print(f"  Depth: {data.get('bid_count', 0)} bids, {data.get('ask_count', 0)} asks")
    return 0


def handle_market_instruments(args) -> int:
    """Handle `market instruments` subcommand."""
    from src.tools.market_data_tools import get_instruments_tool

    symbol = getattr(args, "symbol", None)
    if symbol:
        symbol = symbol.upper()

    result = get_instruments_tool(symbol=symbol)

    if not result.success:
        console.print(f"[red]{result.error}[/]")
        return 1

    if getattr(args, "json_output", False):
        console.print(json.dumps(result.data, indent=2, default=str))
    else:
        console.print(f"[green]{result.message}[/]")
    return 0
