"""Account, position, and panic subcommand handlers for TRADE CLI."""

from __future__ import annotations

import json

from rich.panel import Panel
from rich.table import Table

from src.cli.utils import console


def handle_account_balance(args) -> int:
    """Handle `account balance` subcommand."""
    from src.tools.account_tools import get_account_balance_tool

    result = get_account_balance_tool()
    if not result.success:
        console.print(f"[red]Failed to get balance: {result.error}[/]")
        return 1

    if getattr(args, "json_output", False):
        console.print(json.dumps(result.data, indent=2))
    else:
        data = result.data or {}
        equity = data.get("equity", "N/A")
        available = data.get("available_balance", "N/A")
        wallet = data.get("wallet_balance", "N/A")
        console.print(f"[bold]Account Balance[/]")
        console.print(f"  Equity:    ${equity}")
        console.print(f"  Available: ${available}")
        console.print(f"  Wallet:    ${wallet}")
    return 0


def handle_account_exposure(args) -> int:
    """Handle `account exposure` subcommand."""
    from src.tools.account_tools import get_total_exposure_tool

    result = get_total_exposure_tool()
    if not result.success:
        console.print(f"[red]Failed to get exposure: {result.error}[/]")
        return 1

    if getattr(args, "json_output", False):
        console.print(json.dumps(result.data, indent=2))
    else:
        data = result.data or {}
        total = data.get("exposure_usd", "N/A")
        console.print(f"[bold]Total Exposure:[/] ${total}")
    return 0


def handle_account_info(args) -> int:
    """Handle `account info` subcommand."""
    from src.tools.account_tools import get_account_info_tool

    result = get_account_info_tool()
    if not result.success:
        console.print(f"[red]{result.error}[/]")
        return 1

    if getattr(args, "json_output", False):
        console.print(json.dumps(result.data, indent=2, default=str))
    else:
        data = result.data or {}
        console.print(f"[bold]Account Info[/]")
        console.print(f"  Margin mode: {data.get('margin_mode', 'N/A')}")
        console.print(f"  Unified:     {data.get('unified_margin_status', 'N/A')}")
    return 0


def handle_account_history(args) -> int:
    """Handle `account history` subcommand."""
    from src.tools.account_tools import get_order_history_tool

    symbol = getattr(args, "symbol", None)
    if symbol:
        symbol = symbol.upper()

    days = getattr(args, "days", None)
    window = f"{days}d" if days else "7d"
    start = getattr(args, "start", None)
    end = getattr(args, "end", None)

    if start and end:
        from datetime import datetime
        from calendar import timegm
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
        result = get_order_history_tool(
            start_ms=int(timegm(start_dt.timetuple()) * 1000),
            end_ms=int(timegm(end_dt.timetuple()) * 1000),
            symbol=symbol,
        )
    else:
        result = get_order_history_tool(window=window, symbol=symbol)

    return _print_json_or_message(args, result)


def handle_account_pnl(args) -> int:
    """Handle `account pnl` subcommand."""
    from src.tools.account_tools import get_closed_pnl_tool

    symbol = getattr(args, "symbol", None)
    if symbol:
        symbol = symbol.upper()

    days = getattr(args, "days", None)
    window = f"{days}d" if days else "7d"
    start = getattr(args, "start", None)
    end = getattr(args, "end", None)

    if start and end:
        from datetime import datetime
        from calendar import timegm
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
        result = get_closed_pnl_tool(
            start_ms=int(timegm(start_dt.timetuple()) * 1000),
            end_ms=int(timegm(end_dt.timetuple()) * 1000),
            symbol=symbol,
        )
    else:
        result = get_closed_pnl_tool(window=window, symbol=symbol)

    return _print_json_or_message(args, result)


def handle_account_transactions(args) -> int:
    """Handle `account transactions` subcommand."""
    from src.tools.account_tools import get_transaction_log_tool

    days = getattr(args, "days", None)
    window = f"{days}d" if days else "7d"
    start = getattr(args, "start", None)
    end = getattr(args, "end", None)

    if start and end:
        from datetime import datetime
        from calendar import timegm
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
        result = get_transaction_log_tool(
            start_ms=int(timegm(start_dt.timetuple()) * 1000),
            end_ms=int(timegm(end_dt.timetuple()) * 1000),
        )
    else:
        result = get_transaction_log_tool(window=window)

    return _print_json_or_message(args, result)


def handle_account_collateral(args) -> int:
    """Handle `account collateral` subcommand."""
    from src.tools.account_tools import get_collateral_info_tool

    currency = getattr(args, "currency", None)
    result = get_collateral_info_tool(currency=currency)
    return _print_json_or_message(args, result)


def _print_json_or_message(args, result) -> int:
    """Print result as JSON or human-readable message."""
    if not result.success:
        console.print(f"[red]{result.error}[/]")
        return 1

    if getattr(args, "json_output", False):
        console.print(json.dumps(result.data, indent=2, default=str))
    else:
        console.print(f"[green]{result.message}[/]")
    return 0


def handle_position_list(args) -> int:
    """Handle `position list` subcommand."""
    from src.tools.position_tools import list_open_positions_tool

    result = list_open_positions_tool()
    if not result.success:
        console.print(f"[red]Failed to list positions: {result.error}[/]")
        return 1

    if getattr(args, "json_output", False):
        console.print(json.dumps(result.data, indent=2))
        return 0

    positions = (result.data or {}).get("positions", [])
    if not positions:
        console.print("[dim]No open positions.[/]")
        return 0

    table = Table(title="Open Positions")
    table.add_column("Symbol", style="cyan")
    table.add_column("Side", style="white")
    table.add_column("Size", justify="right")
    table.add_column("Entry", justify="right")
    table.add_column("Current", justify="right")
    table.add_column("PnL", justify="right")
    table.add_column("PnL %", justify="right")

    for pos in positions:
        pnl = float(pos.get("unrealized_pnl", 0))
        pnl_style = "green" if pnl >= 0 else "red"
        table.add_row(
            pos.get("symbol", "?"),
            pos.get("side", "?"),
            str(pos.get("size", "?")),
            f"${float(pos.get('entry_price', 0)):,.2f}",
            f"${float(pos.get('current_price', 0)):,.2f}",
            f"[{pnl_style}]${pnl:,.2f}[/]",
            f"[{pnl_style}]{float(pos.get('unrealized_pnl_percent', 0)):.2f}%[/]",
        )

    console.print(table)
    return 0


def handle_position_close(args) -> int:
    """Handle `position close SYMBOL` subcommand."""
    from src.tools.position_tools import close_position_tool

    symbol = args.symbol.upper()
    console.print(f"[yellow]Closing position for {symbol}...[/]")

    result = close_position_tool(symbol=symbol)
    if result.success:
        console.print(f"[green]Position closed for {symbol}.[/]")
        return 0
    else:
        console.print(f"[red]Failed to close position: {result.error}[/]")
        return 1


def handle_position_set_tp(args) -> int:
    """Handle `position set-tp` subcommand."""
    from src.tools.position_tools import set_take_profit_tool

    result = set_take_profit_tool(
        symbol=args.symbol.upper(),
        take_profit_price=args.price,
    )
    return _print_json_or_message(args, result)


def handle_position_set_sl(args) -> int:
    """Handle `position set-sl` subcommand."""
    from src.tools.position_tools import set_stop_loss_tool

    result = set_stop_loss_tool(
        symbol=args.symbol.upper(),
        stop_price=args.price,
    )
    return _print_json_or_message(args, result)


def handle_position_set_tpsl(args) -> int:
    """Handle `position set-tpsl` subcommand."""
    from src.tools.position_tools import set_position_tpsl_tool

    result = set_position_tpsl_tool(
        symbol=args.symbol.upper(),
        take_profit=getattr(args, "tp", None),
        stop_loss=getattr(args, "sl", None),
    )
    return _print_json_or_message(args, result)


def handle_position_trailing(args) -> int:
    """Handle `position trailing` subcommand."""
    from src.tools.position_tools import set_trailing_stop_tool

    result = set_trailing_stop_tool(
        symbol=args.symbol.upper(),
        trailing_distance=args.distance,
        active_price=getattr(args, "active_price", None),
    )
    return _print_json_or_message(args, result)


def handle_position_partial_close(args) -> int:
    """Handle `position partial-close` subcommand."""
    from src.tools.order_tools import partial_close_position_tool

    result = partial_close_position_tool(
        symbol=args.symbol.upper(),
        close_percent=args.percent,
        price=getattr(args, "price", None),
    )
    return _print_json_or_message(args, result)


def handle_position_margin(args) -> int:
    """Handle `position margin` subcommand."""
    from src.tools.position_config_tools import switch_margin_mode_tool

    mode = args.mode
    isolated = mode == "isolated"
    result = switch_margin_mode_tool(
        symbol=args.symbol.upper(),
        isolated=isolated,
    )
    return _print_json_or_message(args, result)


def handle_position_risk_limit(args) -> int:
    """Handle `position risk-limit` subcommand."""
    from src.tools.position_config_tools import set_risk_limit_tool

    result = set_risk_limit_tool(
        symbol=args.symbol.upper(),
        risk_id=args.id,
    )
    return _print_json_or_message(args, result)


def handle_position_detail(args) -> int:
    """Handle `position detail` subcommand."""
    from src.tools.position_tools import get_position_detail_tool

    result = get_position_detail_tool(symbol=args.symbol.upper())

    if not result.success:
        console.print(f"[red]{result.error}[/]")
        return 1

    if getattr(args, "json_output", False):
        console.print(json.dumps(result.data, indent=2, default=str))
        return 0

    data = result.data or {}
    console.print(f"[bold]{data.get('symbol', '?')} Position Detail[/]")
    console.print(f"  Side:       {data.get('side', '?')}")
    console.print(f"  Size:       {data.get('size', '?')} ({data.get('size_usdt', 0):,.2f} USD)")
    console.print(f"  Entry:      ${float(data.get('entry_price', 0)):,.2f}")
    console.print(f"  Current:    ${float(data.get('current_price', 0)):,.2f}")
    pnl = float(data.get("unrealized_pnl", 0))
    pnl_pct = float(data.get("unrealized_pnl_percent", 0))
    pnl_style = "green" if pnl >= 0 else "red"
    console.print(f"  PnL:        [{pnl_style}]${pnl:,.2f} ({pnl_pct:.2f}%)[/]")
    console.print(f"  Leverage:   {data.get('leverage', '?')}x")
    console.print(f"  Liq price:  {data.get('liquidation_price', 'N/A')}")
    console.print(f"  TP:         {data.get('take_profit', 'None')}")
    console.print(f"  SL:         {data.get('stop_loss', 'None')}")
    console.print(f"  Trailing:   {data.get('trailing_stop', 'None')}")
    return 0


def handle_panic(args) -> int:
    """Handle `panic` subcommand - emergency close all."""
    if not getattr(args, "confirm", False):
        console.print(Panel(
            "[bold red]EMERGENCY PANIC CLOSE[/]\n"
            "[red]This will cancel ALL orders and close ALL positions immediately.[/]\n"
            "[dim]Add --confirm to proceed.[/]",
            border_style="red"
        ))
        return 1

    from src.tools.position_tools import panic_close_all_tool

    console.print("[bold red]PANIC: Closing all positions and cancelling all orders...[/]")
    result = panic_close_all_tool(reason="CLI panic command")
    if result.success:
        console.print("[green]All positions closed, all orders cancelled.[/]")
        return 0
    else:
        console.print(f"[red]Panic close encountered errors: {result.error}[/]")
        return 1
