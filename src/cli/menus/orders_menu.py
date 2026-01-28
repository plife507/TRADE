"""
Orders menu for the CLI.

Handles all order-related operations:
- Market orders (buy/sell with or without TP/SL)
- Limit orders
- Stop orders (conditional)
- Order management (list/amend/cancel)
- Leverage settings
"""

from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.align import Align
from rich.text import Text

from src.config.config import get_config
from src.cli.styles import CLIStyles, CLIColors, CLIIcons, BillArtWrapper
from src.tools import (
    # Order tools
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

# Local console
console = Console()


def _get_time_in_force_with_hints() -> str:
    """
    Display Time in Force options with descriptions and prompt for selection.
    
    Returns:
        Selected Time in Force value (GTC, IOC, FOK, or PostOnly)
    """
    console.print()
    hints_table = Table(show_header=True, box="rounded", padding=(0, 2), border_style=CLIColors.BORDER)
    hints_table.add_column("Option", style=f"bold {CLIColors.NEON_CYAN}", width=12, justify="left")
    hints_table.add_column("Description", style="white", width=70, justify="left")
    
    hints_table.add_row("GTC", "Good Till Cancel - Order stays active until filled or cancelled")
    hints_table.add_row("IOC", "Immediate Or Cancel - Fill immediately, cancel remaining")
    hints_table.add_row("FOK", "Fill Or Kill - Fill completely or cancel entirely")
    hints_table.add_row("PostOnly", "Post Only - Maker order only, cancels if would be taker")
    
    console.print(Panel(hints_table, title=f"[bold {CLIColors.NEON_CYAN}]Time in Force Options[/]", border_style=CLIColors.NEON_CYAN))
    console.print()
    
    from trade_cli import get_input
    return get_input("Time in Force (GTC/IOC/FOK/PostOnly)", "GTC")


def orders_menu(cli: "TradeCLI"):
    """Orders menu."""
    from trade_cli import (
        clear_screen, print_header, get_input, get_choice,
        run_tool_action, print_result, print_data_result, print_error_below_menu, BACK
    )
    from src.cli.utils import get_int_input
    
    while True:
        clear_screen()
        print_header()
        
        # Show trading API status
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
        api_status_line.append(f" │ {trading['base_url']}", style=CLIColors.DIM_TEXT)
        console.print(Panel(api_status_line, border_style=f"dim {CLIColors.NEON_YELLOW}" if not trading["is_demo"] else f"dim {CLIColors.NEON_GREEN}"))
        
        menu = CLIStyles.create_menu_table()
        
        menu.add_row("1", f"{CLIIcons.TRADE} Market Orders (Buy/Sell/TP/SL)", "Execute immediately at market price")
        menu.add_row("2", f"{CLIIcons.LIMIT} Limit Orders", "Place limit buy/sell orders at specific price")
        menu.add_row("3", f"{CLIIcons.STOP} Stop Orders (Conditional)", "Stop market/limit orders (trigger-based)")
        menu.add_row("4", f"{CLIIcons.SETTINGS} Manage Orders (List/Amend/Cancel)", "View, modify, or cancel open orders")
        menu.add_row("5", f"{CLIIcons.LIQUIDITY} Set Leverage", "Set leverage for a trading symbol")
        menu.add_row("6", f"{CLIIcons.ERROR} Cancel All Orders", "Cancel all open orders (optionally by symbol)")
        menu.add_row("7", f"{CLIIcons.BACK} Back to Main Menu", "Return to main menu")
        
        BillArtWrapper.print_menu_top()
        console.print(CLIStyles.get_menu_panel(menu, "ORDERS"))
        BillArtWrapper.print_menu_bottom()
        
        choice = get_choice(valid_range=range(1, 8))
        if choice is BACK:
            break
        
        try:
            if choice == 1:
                market_orders_menu(cli)
            elif choice == 2:
                limit_orders_menu(cli)
            elif choice == 3:
                stop_orders_menu(cli)
            elif choice == 4:
                manage_orders_menu(cli)
            elif choice == 5:
                symbol = get_input("Symbol")
                if symbol is BACK:
                    continue
                leverage = get_int_input("Leverage", "3")
                if leverage is BACK or leverage is None:
                    Prompt.ask("\nPress Enter to continue")
                    continue
                result = run_tool_action("orders.set_leverage", set_leverage_tool, symbol, leverage)
                print_data_result("orders.set_leverage", result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 6:
                symbol = get_input("Symbol (blank for all)", "")
                if symbol is BACK:
                    continue
                result = run_tool_action("orders.cancel_all", cancel_all_orders_tool, symbol=symbol if symbol else None)
                print_data_result("orders.cancel_all", result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 7:
                break
        except Exception as e:
            print_error_below_menu(f"Operation failed: {e}", "An unexpected error occurred. Please try again.")
            Prompt.ask("\nPress Enter to continue")


def market_orders_menu(cli: "TradeCLI"):
    """Market orders menu."""
    from trade_cli import (
        clear_screen, print_header, get_input, get_choice,
        run_tool_action, print_result, print_data_result, print_order_preview, print_error_below_menu, BACK
    )
    from src.cli.utils import get_float_input
    
    while True:
        clear_screen()
        print_header()
        
        menu = CLIStyles.create_menu_table()
        
        menu.add_row("1", f"{CLIIcons.TRADE} Market Buy", "Open long position at current market price")
        menu.add_row("2", f"{CLIIcons.CHART_DOWN} Market Sell", "Open short position at current market price")
        menu.add_row("3", f"{CLIIcons.STOP} Market Buy with TP/SL", "Buy + set take profit & stop loss")
        menu.add_row("4", f"{CLIIcons.STOP} Market Sell with TP/SL", "Sell + set take profit & stop loss")
        menu.add_row("5", f"{CLIIcons.BACK} Back to Orders Menu", "Return to orders menu")
        
        BillArtWrapper.print_menu_top()
        console.print(CLIStyles.get_menu_panel(menu, "MARKET ORDERS"))
        BillArtWrapper.print_menu_bottom()
        
        choice = get_choice(valid_range=range(1, 6))
        if choice is BACK:
            break
        
        try:
            if choice == 1:
                symbol = get_input("Symbol")
                if symbol is BACK:
                    continue
                usd = get_float_input("USD Amount")
                if usd is BACK or usd is None:
                    Prompt.ask("\nPress Enter to continue")
                    continue
                print_order_preview("Market Buy", symbol, "Buy", usd)
                if Confirm.ask("Confirm execution?"):
                    result = run_tool_action("orders.market_buy", market_buy_tool, symbol, usd)
                    print_data_result("orders.market_buy", result)
                else:
                    console.print("[yellow]Cancelled[/]")
                Prompt.ask("\nPress Enter to continue")
            elif choice == 2:
                symbol = get_input("Symbol")
                if symbol is BACK:
                    continue
                usd = get_float_input("USD Amount")
                if usd is BACK or usd is None:
                    Prompt.ask("\nPress Enter to continue")
                    continue
                print_order_preview("Market Sell", symbol, "Sell", usd)
                if Confirm.ask("Confirm execution?"):
                    result = run_tool_action("orders.market_sell", market_sell_tool, symbol, usd)
                    print_data_result("orders.market_sell", result)
                else:
                    console.print("[yellow]Cancelled[/]")
                Prompt.ask("\nPress Enter to continue")
            elif choice == 3:
                symbol = get_input("Symbol")
                if symbol is BACK:
                    continue
                usd = get_float_input("USD Amount")
                if usd is BACK or usd is None:
                    Prompt.ask("\nPress Enter to continue")
                    continue
                tp = get_input("Take Profit Price (blank to skip)", "")
                if tp is BACK:
                    continue
                sl = get_input("Stop Loss Price (blank to skip)", "")
                if sl is BACK:
                    continue
                # Parse TP/SL safely
                tp_val = float(tp) if tp else None
                sl_val = float(sl) if sl else None
                print_order_preview("Market Buy + TP/SL", symbol, "Buy", usd, 
                                  take_profit=tp, stop_loss=sl)
                if Confirm.ask("Confirm execution?"):
                    result = run_tool_action(
                        "orders.market_buy_tpsl", market_buy_with_tpsl_tool,
                        symbol, usd,
                        take_profit=tp_val,
                        stop_loss=sl_val
                    )
                    print_data_result("orders.market_buy", result)
                else:
                    console.print("[yellow]Cancelled[/]")
                Prompt.ask("\nPress Enter to continue")
            elif choice == 4:
                symbol = get_input("Symbol")
                if symbol is BACK:
                    continue
                usd = get_float_input("USD Amount")
                if usd is BACK or usd is None:
                    Prompt.ask("\nPress Enter to continue")
                    continue
                tp = get_input("Take Profit Price (blank to skip)", "")
                if tp is BACK:
                    continue
                sl = get_input("Stop Loss Price (blank to skip)", "")
                if sl is BACK:
                    continue
                # Parse TP/SL safely
                tp_val = float(tp) if tp else None
                sl_val = float(sl) if sl else None
                print_order_preview("Market Sell + TP/SL", symbol, "Sell", usd,
                                  take_profit=tp, stop_loss=sl)
                if Confirm.ask("Confirm execution?"):
                    result = run_tool_action(
                        "orders.market_sell_tpsl", market_sell_with_tpsl_tool,
                        symbol, usd,
                        take_profit=tp_val,
                        stop_loss=sl_val
                    )
                    print_data_result("orders.market_sell", result)
                else:
                    console.print("[yellow]Cancelled[/]")
                Prompt.ask("\nPress Enter to continue")
            elif choice == 5:
                break
        except ValueError as e:
            print_error_below_menu(f"Invalid input: {e}", "Please check your input and try again.")
            Prompt.ask("\nPress Enter to continue")
        except Exception as e:
            print_error_below_menu(f"Operation failed: {e}", "An unexpected error occurred. Please try again.")
            Prompt.ask("\nPress Enter to continue")


def limit_orders_menu(cli: "TradeCLI"):
    """Limit orders menu."""
    from trade_cli import (
        clear_screen, print_header, get_input, get_choice,
        run_tool_action, print_result, print_data_result, print_order_preview, print_error_below_menu, BACK
    )
    from src.cli.utils import get_float_input
    
    while True:
        clear_screen()
        print_header()
        
        menu = CLIStyles.create_menu_table()
        
        menu.add_row("1", f"{CLIIcons.LIMIT} Limit Buy", "Place limit buy order at specified price")
        menu.add_row("2", f"{CLIIcons.LIMIT} Limit Sell", "Place limit sell order at specified price")
        menu.add_row("3", f"{CLIIcons.BACK} Back to Orders Menu", "Return to orders menu")
        
        BillArtWrapper.print_menu_top()
        console.print(CLIStyles.get_menu_panel(menu, "LIMIT ORDERS"))
        BillArtWrapper.print_menu_bottom()
        
        choice = get_choice(valid_range=range(1, 4))
        if choice is BACK:
            break
        
        try:
            if choice == 1:
                symbol = get_input("Symbol")
                if symbol is BACK:
                    continue
                usd = get_float_input("USD Amount")
                if usd is BACK or usd is None:
                    Prompt.ask("\nPress Enter to continue")
                    continue
                price = get_float_input("Limit Price")
                if price is BACK or price is None:
                    Prompt.ask("\nPress Enter to continue")
                    continue
                tif = _get_time_in_force_with_hints()
                if tif is BACK:
                    continue
                reduce_only = Confirm.ask("Reduce Only?", default=False)
                
                print_order_preview("Limit Buy", symbol, "Buy", usd, price=price, 
                                  tif=tif, reduce_only=reduce_only)
                
                if Confirm.ask("Confirm execution?"):
                    result = run_tool_action("orders.limit_buy", limit_buy_tool, symbol, usd, price, time_in_force=tif, reduce_only=reduce_only)
                    print_data_result("orders.limit_buy", result)
                else:
                    console.print("[yellow]Cancelled[/]")
                Prompt.ask("\nPress Enter to continue")
            elif choice == 2:
                symbol = get_input("Symbol")
                if symbol is BACK:
                    continue
                usd = get_float_input("USD Amount")
                if usd is BACK or usd is None:
                    Prompt.ask("\nPress Enter to continue")
                    continue
                price = get_float_input("Limit Price")
                if price is BACK or price is None:
                    Prompt.ask("\nPress Enter to continue")
                    continue
                tif = _get_time_in_force_with_hints()
                if tif is BACK:
                    continue
                reduce_only = Confirm.ask("Reduce Only?", default=False)
                
                print_order_preview("Limit Sell", symbol, "Sell", usd, price=price,
                                  tif=tif, reduce_only=reduce_only)
                
                if Confirm.ask("Confirm execution?"):
                    result = run_tool_action("orders.limit_sell", limit_sell_tool, symbol, usd, price, time_in_force=tif, reduce_only=reduce_only)
                    print_data_result("orders.limit_sell", result)
                else:
                    console.print("[yellow]Cancelled[/]")
                Prompt.ask("\nPress Enter to continue")
            elif choice == 3:
                break
        except ValueError as e:
            print_error_below_menu(f"Invalid input: {e}", "Please check your input and try again.")
            Prompt.ask("\nPress Enter to continue")
        except Exception as e:
            print_error_below_menu(f"Operation failed: {e}", "An unexpected error occurred. Please try again.")
            Prompt.ask("\nPress Enter to continue")


def stop_orders_menu(cli: "TradeCLI"):
    """Stop orders menu."""
    from trade_cli import (
        clear_screen, print_header, get_input, get_choice,
        run_tool_action, print_result, print_data_result, print_order_preview, print_error_below_menu, BACK
    )
    from src.cli.utils import get_float_input, get_int_input
    
    while True:
        clear_screen()
        print_header()
        
        menu = CLIStyles.create_menu_table()
        
        menu.add_row("1", f"{CLIIcons.STOP} Stop Market Buy", "Buy when price rises/falls to trigger")
        menu.add_row("2", f"{CLIIcons.STOP} Stop Market Sell", "Sell when price rises/falls to trigger")
        menu.add_row("3", f"{CLIIcons.LIMIT} Stop Limit Buy", "Limit buy triggered at stop price")
        menu.add_row("4", f"{CLIIcons.LIMIT} Stop Limit Sell", "Limit sell triggered at stop price")
        menu.add_row("5", f"{CLIIcons.BACK} Back to Orders Menu", "Return to orders menu")
        
        BillArtWrapper.print_menu_top()
        console.print(CLIStyles.get_menu_panel(menu, "STOP/CONDITIONAL ORDERS"))
        BillArtWrapper.print_menu_bottom()
        
        choice = get_choice(valid_range=range(1, 6))
        if choice is BACK:
            break
        
        try:
            if choice == 1:
                symbol = get_input("Symbol")
                if symbol is BACK:
                    continue
                usd = get_float_input("USD Amount")
                if usd is BACK or usd is None:
                    Prompt.ask("\nPress Enter to continue")
                    continue
                trigger = get_float_input("Trigger Price")
                if trigger is BACK or trigger is None:
                    Prompt.ask("\nPress Enter to continue")
                    continue
                direction = get_int_input("Trigger Direction (1=Rise, 2=Fall)", "1")
                if direction is BACK or direction is None:
                    Prompt.ask("\nPress Enter to continue")
                    continue
                
                print_order_preview("Stop Market Buy", symbol, "Buy", usd, 
                                  trigger_price=trigger, 
                                  condition="Rises to" if direction==1 else "Falls to")
                
                if Confirm.ask("Confirm execution?"):
                    result = run_tool_action("orders.stop_market_buy", stop_market_buy_tool, symbol, usd, trigger, trigger_direction=direction)
                    print_data_result("orders.stop_market_buy", result)
                else:
                    console.print("[yellow]Cancelled[/]")
                Prompt.ask("\nPress Enter to continue")
            elif choice == 2:
                symbol = get_input("Symbol")
                if symbol is BACK:
                    continue
                usd = get_float_input("USD Amount")
                if usd is BACK or usd is None:
                    Prompt.ask("\nPress Enter to continue")
                    continue
                trigger = get_float_input("Trigger Price")
                if trigger is BACK or trigger is None:
                    Prompt.ask("\nPress Enter to continue")
                    continue
                direction = get_int_input("Trigger Direction (1=Rise, 2=Fall)", "2")
                if direction is BACK or direction is None:
                    Prompt.ask("\nPress Enter to continue")
                    continue
                
                print_order_preview("Stop Market Sell", symbol, "Sell", usd,
                                  trigger_price=trigger,
                                  condition="Rises to" if direction==1 else "Falls to")
                
                if Confirm.ask("Confirm execution?"):
                    result = run_tool_action("orders.stop_market_sell", stop_market_sell_tool, symbol, usd, trigger, trigger_direction=direction)
                    print_data_result("orders.stop_market_sell", result)
                else:
                    console.print("[yellow]Cancelled[/]")
                Prompt.ask("\nPress Enter to continue")
            elif choice == 3:
                symbol = get_input("Symbol")
                if symbol is BACK:
                    continue
                usd = get_float_input("USD Amount")
                if usd is BACK or usd is None:
                    Prompt.ask("\nPress Enter to continue")
                    continue
                trigger = get_float_input("Trigger Price")
                if trigger is BACK or trigger is None:
                    Prompt.ask("\nPress Enter to continue")
                    continue
                limit = get_float_input("Limit Price")
                if limit is BACK or limit is None:
                    Prompt.ask("\nPress Enter to continue")
                    continue
                direction = get_int_input("Trigger Direction (1=Rise, 2=Fall)", "1")
                if direction is BACK or direction is None:
                    Prompt.ask("\nPress Enter to continue")
                    continue
                
                print_order_preview("Stop Limit Buy", symbol, "Buy", usd, price=limit,
                                  trigger_price=trigger,
                                  condition="Rises to" if direction==1 else "Falls to")
                
                if Confirm.ask("Confirm execution?"):
                    result = run_tool_action("orders.stop_limit_buy", stop_limit_buy_tool, symbol, usd, trigger, limit, trigger_direction=direction)
                    print_data_result("orders.stop_limit_buy", result)
                else:
                    console.print("[yellow]Cancelled[/]")
                Prompt.ask("\nPress Enter to continue")
            elif choice == 4:
                symbol = get_input("Symbol")
                if symbol is BACK:
                    continue
                usd = get_float_input("USD Amount")
                if usd is BACK or usd is None:
                    Prompt.ask("\nPress Enter to continue")
                    continue
                trigger = get_float_input("Trigger Price")
                if trigger is BACK or trigger is None:
                    Prompt.ask("\nPress Enter to continue")
                    continue
                limit = get_float_input("Limit Price")
                if limit is BACK or limit is None:
                    Prompt.ask("\nPress Enter to continue")
                    continue
                direction = get_int_input("Trigger Direction (1=Rise, 2=Fall)", "2")
                if direction is BACK or direction is None:
                    Prompt.ask("\nPress Enter to continue")
                    continue
                
                print_order_preview("Stop Limit Sell", symbol, "Sell", usd, price=limit,
                                  trigger_price=trigger,
                                  condition="Rises to" if direction==1 else "Falls to")
                
                if Confirm.ask("Confirm execution?"):
                    result = run_tool_action("orders.stop_limit_sell", stop_limit_sell_tool, symbol, usd, trigger, limit, trigger_direction=direction)
                    print_data_result("orders.stop_limit_sell", result)
                else:
                    console.print("[yellow]Cancelled[/]")
                Prompt.ask("\nPress Enter to continue")
            elif choice == 5:
                break
        except ValueError as e:
            print_error_below_menu(f"Invalid input: {e}", "Please check your input and try again.")
            Prompt.ask("\nPress Enter to continue")
        except Exception as e:
            print_error_below_menu(f"Operation failed: {e}", "An unexpected error occurred. Please try again.")
            Prompt.ask("\nPress Enter to continue")


def manage_orders_menu(cli: "TradeCLI"):
    """Manage existing orders."""
    from trade_cli import (
        clear_screen, print_header, get_input, get_choice,
        run_tool_action, print_result, print_data_result, print_error_below_menu, BACK
    )
    
    while True:
        clear_screen()
        print_header()
        
        menu = CLIStyles.create_menu_table()
        
        menu.add_row("1", f"{CLIIcons.LEDGER} List Open Orders", "View all open orders (optionally by symbol)")
        menu.add_row("2", f"{CLIIcons.SETTINGS} Amend Order", "Modify order (qty, price, TP/SL)")
        menu.add_row("3", f"{CLIIcons.ERROR} Cancel Order", "Cancel a specific order by ID")
        menu.add_row("4", f"{CLIIcons.BACK} Back to Orders Menu", "Return to orders menu")
        
        BillArtWrapper.print_menu_top()
        console.print(CLIStyles.get_menu_panel(menu, "MANAGE ORDERS"))
        BillArtWrapper.print_menu_bottom()
        
        choice = get_choice(valid_range=range(1, 5))
        if choice is BACK:
            break
        
        try:
            if choice == 1:
                symbol = get_input("Symbol (blank for all)", "")
                if symbol is BACK:
                    continue
                result = run_tool_action("orders.list", get_open_orders_tool, symbol=symbol if symbol else None)
                print_data_result("orders.list", result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 2:
                symbol = get_input("Symbol")
                if symbol is BACK:
                    continue
                order_id = get_input("Order ID")
                if order_id is BACK:
                    continue
                
                console.print("\n[dim]Leave blank to keep unchanged[/]")
                new_qty = get_input("New Quantity (blank to keep)", "")
                if new_qty is BACK:
                    continue
                new_price = get_input("New Price (blank to keep)", "")
                if new_price is BACK:
                    continue
                new_tp = get_input("New Take Profit (blank to keep)", "")
                if new_tp is BACK:
                    continue
                new_sl = get_input("New Stop Loss (blank to keep)", "")
                if new_sl is BACK:
                    continue
                
                # Parse numeric values safely
                qty_val = float(new_qty) if new_qty else None
                price_val = float(new_price) if new_price else None
                tp_val = float(new_tp) if new_tp else None
                sl_val = float(new_sl) if new_sl else None
                
                result = run_tool_action(
                    "orders.amend", amend_order_tool,
                    symbol, order_id,
                    qty=qty_val,
                    price=price_val,
                    take_profit=tp_val,
                    stop_loss=sl_val
                )
                print_data_result("orders.amend", result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 3:
                symbol = get_input("Symbol")
                if symbol is BACK:
                    continue
                order_id = get_input("Order ID")
                if order_id is BACK:
                    continue
                if Confirm.ask(f"Cancel order {order_id}?"):
                    result = run_tool_action("orders.cancel", cancel_order_tool, symbol, order_id)
                    print_data_result("orders.cancel", result)
                else:
                    console.print("[yellow]Cancelled[/]")
                Prompt.ask("\nPress Enter to continue")
            elif choice == 4:
                break
        except ValueError as e:
            print_error_below_menu(f"Invalid input: {e}", "Please check your input and try again.")
            Prompt.ask("\nPress Enter to continue")
        except Exception as e:
            print_error_below_menu(f"Operation failed: {e}", "An unexpected error occurred. Please try again.")
            Prompt.ask("\nPress Enter to continue")

