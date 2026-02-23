"""Order subcommand handlers for TRADE CLI.

Provides non-interactive CLI access to all order operations:
- market/limit/stop/stop-limit buy and sell
- order listing, amending, cancelling
- leverage setting
- batch orders
"""

from __future__ import annotations

import json

from src.cli.utils import console


def handle_order_buy(args) -> int:
    """Handle `order buy` subcommand — place a buy order."""
    symbol = args.symbol.upper()
    amount = args.amount
    order_type = args.type
    price = getattr(args, "price", None)
    trigger = getattr(args, "trigger", None)
    tp = getattr(args, "tp", None)
    sl = getattr(args, "sl", None)
    tif = getattr(args, "tif", "GTC")
    reduce_only = getattr(args, "reduce_only", False)

    if order_type == "market":
        if tp or sl:
            from src.tools.order_tools import market_buy_with_tpsl_tool
            result = market_buy_with_tpsl_tool(
                symbol=symbol, usd_amount=amount,
                take_profit=tp, stop_loss=sl,
            )
        else:
            from src.tools.order_tools import market_buy_tool
            result = market_buy_tool(symbol=symbol, usd_amount=amount)

    elif order_type == "limit":
        if not price:
            console.print("[red]--price is required for limit orders[/]")
            return 1
        from src.tools.order_tools import limit_buy_tool
        result = limit_buy_tool(
            symbol=symbol, usd_amount=amount, price=price,
            time_in_force=tif, reduce_only=reduce_only,
        )

    elif order_type == "stop":
        if not trigger:
            console.print("[red]--trigger is required for stop orders[/]")
            return 1
        from src.tools.order_tools import stop_market_buy_tool
        result = stop_market_buy_tool(
            symbol=symbol, usd_amount=amount, trigger_price=trigger,
            reduce_only=reduce_only,
        )

    elif order_type == "stop-limit":
        if not trigger or not price:
            console.print("[red]--trigger and --price are required for stop-limit orders[/]")
            return 1
        from src.tools.order_tools import stop_limit_buy_tool
        result = stop_limit_buy_tool(
            symbol=symbol, usd_amount=amount,
            trigger_price=trigger, limit_price=price,
            time_in_force=tif, reduce_only=reduce_only,
        )
    else:
        console.print(f"[red]Unknown order type: {order_type}[/]")
        return 1

    return _print_order_result(args, result)


def handle_order_sell(args) -> int:
    """Handle `order sell` subcommand — place a sell order."""
    symbol = args.symbol.upper()
    amount = args.amount
    order_type = args.type
    price = getattr(args, "price", None)
    trigger = getattr(args, "trigger", None)
    tp = getattr(args, "tp", None)
    sl = getattr(args, "sl", None)
    tif = getattr(args, "tif", "GTC")
    reduce_only = getattr(args, "reduce_only", False)

    if order_type == "market":
        if tp or sl:
            from src.tools.order_tools import market_sell_with_tpsl_tool
            result = market_sell_with_tpsl_tool(
                symbol=symbol, usd_amount=amount,
                take_profit=tp, stop_loss=sl,
            )
        else:
            from src.tools.order_tools import market_sell_tool
            result = market_sell_tool(symbol=symbol, usd_amount=amount)

    elif order_type == "limit":
        if not price:
            console.print("[red]--price is required for limit orders[/]")
            return 1
        from src.tools.order_tools import limit_sell_tool
        result = limit_sell_tool(
            symbol=symbol, usd_amount=amount, price=price,
            time_in_force=tif, reduce_only=reduce_only,
        )

    elif order_type == "stop":
        if not trigger:
            console.print("[red]--trigger is required for stop orders[/]")
            return 1
        from src.tools.order_tools import stop_market_sell_tool
        result = stop_market_sell_tool(
            symbol=symbol, usd_amount=amount, trigger_price=trigger,
            reduce_only=reduce_only,
        )

    elif order_type == "stop-limit":
        if not trigger or not price:
            console.print("[red]--trigger and --price are required for stop-limit orders[/]")
            return 1
        from src.tools.order_tools import stop_limit_sell_tool
        result = stop_limit_sell_tool(
            symbol=symbol, usd_amount=amount,
            trigger_price=trigger, limit_price=price,
            time_in_force=tif, reduce_only=reduce_only,
        )
    else:
        console.print(f"[red]Unknown order type: {order_type}[/]")
        return 1

    return _print_order_result(args, result)


def handle_order_list(args) -> int:
    """Handle `order list` subcommand."""
    from src.tools.order_tools import get_open_orders_tool

    symbol = getattr(args, "symbol", None)
    if symbol:
        symbol = symbol.upper()
    order_filter = getattr(args, "filter", None)
    limit = getattr(args, "limit", 50)

    result = get_open_orders_tool(
        symbol=symbol, order_filter=order_filter, limit=limit,
    )

    if not result.success:
        console.print(f"[red]{result.error}[/]")
        return 1

    if getattr(args, "json_output", False):
        console.print(json.dumps(result.data, indent=2))
        return 0

    orders = (result.data or {}).get("orders", [])
    if not orders:
        console.print("[dim]No open orders.[/]")
        return 0

    from rich.table import Table
    table = Table(title=f"Open Orders ({len(orders)})")
    table.add_column("ID", style="dim", max_width=12)
    table.add_column("Symbol", style="cyan")
    table.add_column("Side")
    table.add_column("Type")
    table.add_column("Qty", justify="right")
    table.add_column("Price", justify="right")
    table.add_column("Trigger", justify="right")
    table.add_column("Status")

    for o in orders:
        side_style = "green" if o.get("side") == "Buy" else "red"
        table.add_row(
            str(o.get("order_id", ""))[:12],
            o.get("symbol", "?"),
            f"[{side_style}]{o.get('side', '?')}[/]",
            o.get("order_type", "?"),
            str(o.get("qty", "")),
            f"${float(o.get('price', 0)):,.2f}" if o.get("price") else "-",
            f"${float(o.get('trigger_price', 0)):,.2f}" if o.get("trigger_price") else "-",
            o.get("status", "?"),
        )

    console.print(table)
    return 0


def handle_order_amend(args) -> int:
    """Handle `order amend` subcommand."""
    from src.tools.order_tools import amend_order_tool

    result = amend_order_tool(
        symbol=args.symbol.upper(),
        order_id=getattr(args, "order_id", None),
        qty=getattr(args, "qty", None),
        price=getattr(args, "price", None),
        take_profit=getattr(args, "tp", None),
        stop_loss=getattr(args, "sl", None),
    )
    return _print_order_result(args, result)


def handle_order_cancel(args) -> int:
    """Handle `order cancel` subcommand."""
    from src.tools.order_tools import cancel_order_tool

    result = cancel_order_tool(
        symbol=args.symbol.upper(),
        order_id=args.order_id,
    )
    return _print_order_result(args, result)


def handle_order_cancel_all(args) -> int:
    """Handle `order cancel-all` subcommand."""
    from src.tools.order_tools import cancel_all_orders_tool

    symbol = getattr(args, "symbol", None)
    if symbol:
        symbol = symbol.upper()

    result = cancel_all_orders_tool(symbol=symbol)
    return _print_order_result(args, result)


def handle_order_leverage(args) -> int:
    """Handle `order leverage` subcommand."""
    from src.tools.order_tools import set_leverage_tool

    result = set_leverage_tool(
        symbol=args.symbol.upper(),
        leverage=args.leverage,
    )
    return _print_order_result(args, result)


def handle_order_batch(args) -> int:
    """Handle `order batch` subcommand — read orders from JSON file."""
    import pathlib

    file_path = pathlib.Path(args.file)
    if not file_path.exists():
        console.print(f"[red]File not found: {file_path}[/]")
        return 1

    try:
        orders = json.loads(file_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        console.print(f"[red]Failed to read orders file: {e}[/]")
        return 1

    if not isinstance(orders, list):
        console.print("[red]Orders file must contain a JSON array[/]")
        return 1

    from src.tools.order_tools import batch_market_orders_tool
    result = batch_market_orders_tool(orders=orders)
    return _print_order_result(args, result)


# ---------- helpers ----------

def _print_order_result(args, result) -> int:
    """Print order result as JSON or human-readable."""
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
