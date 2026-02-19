"""Account, position, and panic subcommand handlers for TRADE CLI."""

from __future__ import annotations

from rich.panel import Panel
from rich.table import Table

from src.cli.utils import console


def handle_account_balance(args) -> int:
    """Handle `account balance` subcommand."""
    import json
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
    import json
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


def handle_position_list(args) -> int:
    """Handle `position list` subcommand."""
    import json
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
