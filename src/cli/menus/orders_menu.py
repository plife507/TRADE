"""
Orders menu for the CLI.

Flat 2-group structure: Place (unified order form + leverage) and Manage (list/amend/cancel).
"""

from typing import TYPE_CHECKING

from rich import box as rich_box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.text import Text

from src.config.config import get_config
from src.cli.styles import CLIStyles, CLIColors, CLIIcons, BillArtWrapper
from src.cli.utils import BackCommand
from src.tools import (
    set_leverage_tool,
    market_buy_tool,
    market_sell_tool,
    market_buy_with_tpsl_tool,
    market_sell_with_tpsl_tool,
    limit_buy_tool,
    limit_sell_tool,
    stop_market_buy_tool,
    stop_market_sell_tool,
    stop_limit_buy_tool,
    stop_limit_sell_tool,
    amend_order_tool,
    cancel_order_tool,
    get_open_orders_tool,
    cancel_all_orders_tool,
)

if TYPE_CHECKING:
    from trade_cli import TradeCLI

console = Console()


def _get_time_in_force_with_hints() -> str | BackCommand:
    """Display Time in Force options with descriptions and prompt for selection."""
    from src.cli.utils import get_input

    console.print()
    hints_table = Table(show_header=True, box=rich_box.ROUNDED, padding=(0, 2), border_style=CLIColors.BORDER)
    hints_table.add_column("Option", style=f"bold {CLIColors.NEON_CYAN}", width=12, justify="left")
    hints_table.add_column("Description", style="white", width=70, justify="left")

    hints_table.add_row("GTC", "Good Till Cancel - Order stays active until filled or cancelled")
    hints_table.add_row("IOC", "Immediate Or Cancel - Fill immediately, cancel remaining")
    hints_table.add_row("FOK", "Fill Or Kill - Fill completely or cancel entirely")
    hints_table.add_row("PostOnly", "Post Only - Maker order only, cancels if would be taker")

    console.print(Panel(
        hints_table,
        title=f"[bold {CLIColors.NEON_CYAN}]Time in Force Options[/]",
        border_style=CLIColors.NEON_CYAN,
    ))
    console.print()

    return get_input("Time in Force (GTC/IOC/FOK/PostOnly)", "GTC")


def _place_order() -> None:
    """Unified order placement: type -> side -> symbol -> amount -> conditional fields -> preview -> execute."""
    from src.cli.utils import (
        get_input, get_float_input, get_int_input,
        run_tool_action, print_data_result, print_order_preview, BACK,
        get_symbol_input,
    )

    # 1. Order type
    console.print(f"\n[bold {CLIColors.NEON_CYAN}]Order Type:[/]")
    console.print(f"  1) Market")
    console.print(f"  2) Limit")
    console.print(f"  3) Stop Market")
    console.print(f"  4) Stop Limit")
    type_input = get_input("Order type [1-4]", "1")
    if isinstance(type_input, BackCommand):
        return
    try:
        order_type = int(type_input)
    except ValueError:
        console.print("[red]Invalid order type.[/]")
        Prompt.ask("\nPress Enter to continue")
        return
    if order_type not in (1, 2, 3, 4):
        console.print("[red]Invalid order type.[/]")
        Prompt.ask("\nPress Enter to continue")
        return

    type_labels = {1: "Market", 2: "Limit", 3: "Stop Market", 4: "Stop Limit"}
    type_label = type_labels[order_type]

    # 2. Side
    console.print(f"\n[bold {CLIColors.NEON_CYAN}]Side:[/]")
    console.print(f"  1) Buy (Long)")
    console.print(f"  2) Sell (Short)")
    side_input = get_input("Side [1-2]", "1")
    if isinstance(side_input, BackCommand):
        return
    try:
        side = int(side_input)
    except ValueError:
        console.print("[red]Invalid side.[/]")
        Prompt.ask("\nPress Enter to continue")
        return
    if side not in (1, 2):
        console.print("[red]Invalid side.[/]")
        Prompt.ask("\nPress Enter to continue")
        return

    side_label = "Buy" if side == 1 else "Sell"

    # 3. Symbol
    symbol = get_symbol_input("Symbol")
    if isinstance(symbol, BackCommand):
        return
    assert isinstance(symbol, str)

    # 4. USD amount
    usd = get_float_input("USD Amount")
    if isinstance(usd, BackCommand) or usd is None:
        Prompt.ask("\nPress Enter to continue")
        return
    assert isinstance(usd, float)

    # 5. Conditional fields
    limit_price: float | None = None
    trigger_price: float | None = None
    trigger_direction: int | None = None
    tif: str | None = None
    reduce_only: bool = False
    tp_val: float | None = None
    sl_val: float | None = None

    # Limit / Stop-Limit: limit price, TIF, reduce-only
    if order_type in (2, 4):
        lp = get_float_input("Limit Price")
        if isinstance(lp, BackCommand) or lp is None:
            Prompt.ask("\nPress Enter to continue")
            return
        assert isinstance(lp, float)
        limit_price = lp

        tif_result = _get_time_in_force_with_hints()
        if isinstance(tif_result, BackCommand):
            return
        assert isinstance(tif_result, str)
        tif = tif_result

        reduce_only = Confirm.ask("Reduce Only?", default=False)

    # Stop-Market / Stop-Limit: trigger price, trigger direction
    if order_type in (3, 4):
        tp = get_float_input("Trigger Price")
        if isinstance(tp, BackCommand) or tp is None:
            Prompt.ask("\nPress Enter to continue")
            return
        assert isinstance(tp, float)
        trigger_price = tp

        default_dir = "1" if side == 1 else "2"
        td = get_int_input("Trigger Direction (1=Rise, 2=Fall)", default_dir)
        if isinstance(td, BackCommand) or td is None:
            Prompt.ask("\nPress Enter to continue")
            return
        assert isinstance(td, int)
        trigger_direction = td

    # 6. Optional TP/SL (market orders only)
    if order_type == 1:
        tp_str = get_input("Take Profit Price (blank to skip)", "")
        if isinstance(tp_str, BackCommand):
            return
        assert isinstance(tp_str, str)
        sl_str = get_input("Stop Loss Price (blank to skip)", "")
        if isinstance(sl_str, BackCommand):
            return
        assert isinstance(sl_str, str)
        tp_val = float(tp_str) if tp_str else None
        sl_val = float(sl_str) if sl_str else None

    # 7. Build preview kwargs
    preview_label = type_label
    if order_type == 1 and (tp_val or sl_val):
        preview_label = f"Market {side_label} + TP/SL"
    else:
        preview_label = f"{type_label} {side_label}"

    preview_kwargs: dict[str, object] = {}
    if limit_price is not None:
        preview_kwargs["price"] = limit_price
    if trigger_price is not None:
        preview_kwargs["trigger_price"] = trigger_price
        preview_kwargs["condition"] = "Rises to" if trigger_direction == 1 else "Falls to"
    if tif is not None:
        preview_kwargs["tif"] = tif
    if reduce_only:
        preview_kwargs["reduce_only"] = reduce_only
    if tp_val is not None:
        preview_kwargs["take_profit"] = str(tp_val)
    if sl_val is not None:
        preview_kwargs["stop_loss"] = str(sl_val)

    print_order_preview(preview_label, symbol, side_label, usd, **preview_kwargs)  # type: ignore[arg-type]

    # 8. Confirm + execute
    if not Confirm.ask("Confirm execution?"):
        console.print("[yellow]Cancelled[/]")
        Prompt.ask("\nPress Enter to continue")
        return

    # Route to correct tool
    if order_type == 1:  # Market
        if tp_val or sl_val:
            tool_fn = market_buy_with_tpsl_tool if side == 1 else market_sell_with_tpsl_tool
            action = "orders.market_buy_tpsl" if side == 1 else "orders.market_sell_tpsl"
            result = run_tool_action(action, tool_fn, symbol, usd, take_profit=tp_val, stop_loss=sl_val)
        else:
            tool_fn = market_buy_tool if side == 1 else market_sell_tool
            action = "orders.market_buy" if side == 1 else "orders.market_sell"
            result = run_tool_action(action, tool_fn, symbol, usd)
    elif order_type == 2:  # Limit
        tool_fn = limit_buy_tool if side == 1 else limit_sell_tool
        action = "orders.limit_buy" if side == 1 else "orders.limit_sell"
        assert limit_price is not None
        assert tif is not None
        result = run_tool_action(action, tool_fn, symbol, usd, limit_price, time_in_force=tif, reduce_only=reduce_only)
    elif order_type == 3:  # Stop Market
        tool_fn = stop_market_buy_tool if side == 1 else stop_market_sell_tool
        action = "orders.stop_market_buy" if side == 1 else "orders.stop_market_sell"
        assert trigger_price is not None
        assert trigger_direction is not None
        result = run_tool_action(action, tool_fn, symbol, usd, trigger_price, trigger_direction=trigger_direction)
    elif order_type == 4:  # Stop Limit
        tool_fn = stop_limit_buy_tool if side == 1 else stop_limit_sell_tool
        action = "orders.stop_limit_buy" if side == 1 else "orders.stop_limit_sell"
        assert trigger_price is not None
        assert limit_price is not None
        assert trigger_direction is not None
        result = run_tool_action(action, tool_fn, symbol, usd, trigger_price, limit_price, trigger_direction=trigger_direction)
    else:
        return

    print_data_result(action, result)
    Prompt.ask("\nPress Enter to continue")


def orders_menu(cli: "TradeCLI") -> None:
    """Orders menu -- flat 2-group layout: Place + Manage."""
    from src.cli.utils import (
        clear_screen, print_header, get_input, get_choice, get_int_input,
        run_tool_action, print_data_result, print_error_below_menu, BACK,
        get_symbol_input,
    )

    while True:
        clear_screen()
        print_header()

        # Trading API status banner
        config = get_config()
        api_env = config.bybit.get_api_environment_summary()
        trading = api_env["trading"]
        api_status_line = Text()
        api_status_line.append("Trading API: ", style=CLIColors.DIM_TEXT)
        if trading["is_demo"]:
            api_status_line.append(f"{trading['mode']} ", style=f"bold {CLIColors.NEON_GREEN}")
            api_status_line.append("(demo account - fake funds)", style=CLIColors.NEON_GREEN)
        else:
            api_status_line.append(f"{trading['mode']} ", style=f"bold {CLIColors.NEON_RED}")
            api_status_line.append("(live account - REAL FUNDS)", style=f"bold {CLIColors.NEON_RED}")
        api_status_line.append(f" | {trading['base_url']}", style=CLIColors.DIM_TEXT)
        border = f"dim {CLIColors.NEON_GREEN}" if trading["is_demo"] else f"dim {CLIColors.NEON_YELLOW}"
        console.print(Panel(api_status_line, border_style=border))

        menu = CLIStyles.create_menu_table()

        # --- Place ---
        menu.add_row("1", f"{CLIIcons.TRADE} Place Order", "Unified order placement (market/limit/stop)")
        menu.add_row("2", f"{CLIIcons.LIQUIDITY} Set Leverage", "Set leverage for a trading symbol")
        # --- Manage ---
        menu.add_row("3", f"{CLIIcons.LEDGER} List Open Orders", "View all open orders")
        menu.add_row("4", f"{CLIIcons.SETTINGS} Amend Order", "Modify order qty/price/TP/SL")
        menu.add_row("5", f"{CLIIcons.ERROR} Cancel Order", "Cancel a specific order by ID")
        menu.add_row("6", f"{CLIIcons.ERROR} Cancel All Orders", "Cancel all open orders")
        # --- Navigation ---
        menu.add_row("7", f"{CLIIcons.BACK} Back to Main Menu", "Return to main menu")

        BillArtWrapper.print_menu_top()
        console.print(CLIStyles.get_menu_panel(menu, "ORDERS"))
        BillArtWrapper.print_menu_bottom()

        choice = get_choice(valid_range=range(1, 8))
        if choice is BACK:
            break

        try:
            if choice == 1:
                _place_order()

            elif choice == 2:
                # Set Leverage
                symbol = get_symbol_input("Symbol")
                if symbol is BACK:
                    continue
                assert isinstance(symbol, str)
                leverage = get_int_input("Leverage", "3")
                if leverage is BACK or leverage is None:
                    Prompt.ask("\nPress Enter to continue")
                    continue
                result = run_tool_action("orders.set_leverage", set_leverage_tool, symbol, leverage)
                print_data_result("orders.set_leverage", result)
                Prompt.ask("\nPress Enter to continue")

            elif choice == 3:
                # List Open Orders
                symbol = get_symbol_input("Symbol (blank for all)")
                if symbol is BACK:
                    continue
                assert isinstance(symbol, str)
                result = run_tool_action("orders.list", get_open_orders_tool, symbol=symbol if symbol else None)
                print_data_result("orders.list", result)
                Prompt.ask("\nPress Enter to continue")

            elif choice == 4:
                # Amend Order
                symbol = get_symbol_input("Symbol")
                if symbol is BACK:
                    continue
                assert isinstance(symbol, str)
                order_id = get_input("Order ID")
                if order_id is BACK:
                    continue
                assert isinstance(order_id, str)

                console.print("\n[dim]Leave blank to keep unchanged[/]")
                new_qty = get_input("New Quantity (blank to keep)", "")
                if new_qty is BACK:
                    continue
                assert isinstance(new_qty, str)
                new_price = get_input("New Price (blank to keep)", "")
                if new_price is BACK:
                    continue
                assert isinstance(new_price, str)
                new_tp = get_input("New Take Profit (blank to keep)", "")
                if new_tp is BACK:
                    continue
                assert isinstance(new_tp, str)
                new_sl = get_input("New Stop Loss (blank to keep)", "")
                if new_sl is BACK:
                    continue
                assert isinstance(new_sl, str)

                qty_val = float(new_qty) if new_qty else None
                price_val = float(new_price) if new_price else None
                tp_val = float(new_tp) if new_tp else None
                sl_val = float(new_sl) if new_sl else None

                result = run_tool_action(
                    "orders.amend", amend_order_tool,
                    symbol, order_id,
                    qty=qty_val, price=price_val,
                    take_profit=tp_val, stop_loss=sl_val,
                )
                print_data_result("orders.amend", result)
                Prompt.ask("\nPress Enter to continue")

            elif choice == 5:
                # Cancel Order
                symbol = get_symbol_input("Symbol")
                if symbol is BACK:
                    continue
                assert isinstance(symbol, str)
                order_id = get_input("Order ID")
                if order_id is BACK:
                    continue
                assert isinstance(order_id, str)
                if Confirm.ask(f"Cancel order {order_id}?"):
                    result = run_tool_action("orders.cancel", cancel_order_tool, symbol, order_id)
                    print_data_result("orders.cancel", result)
                else:
                    console.print("[yellow]Cancelled[/]")
                Prompt.ask("\nPress Enter to continue")

            elif choice == 6:
                # Cancel All Orders
                symbol = get_symbol_input("Symbol (blank for all)")
                if symbol is BACK:
                    continue
                assert isinstance(symbol, str)
                result = run_tool_action("orders.cancel_all", cancel_all_orders_tool, symbol=symbol if symbol else None)
                print_data_result("orders.cancel_all", result)
                Prompt.ask("\nPress Enter to continue")

            elif choice == 7:
                break

        except ValueError as e:
            print_error_below_menu(f"Invalid input: {e}", "Please check your input and try again.")
            Prompt.ask("\nPress Enter to continue")
        except Exception as e:
            print_error_below_menu(f"Operation failed: {e}", "An unexpected error occurred. Please try again.")
            Prompt.ask("\nPress Enter to continue")
