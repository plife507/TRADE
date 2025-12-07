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


def orders_menu(cli: "TradeCLI"):
    """Orders menu."""
    from trade_cli import (
        clear_screen, print_header, get_input, get_choice,
        run_tool_action, print_result
    )
    
    while True:
        clear_screen()
        print_header()
        
        # Show trading API status
        config = get_config()
        api_env = config.bybit.get_api_environment_summary()
        trading = api_env["trading"]
        api_status_line = Text()
        api_status_line.append("Trading API: ", style="dim")
        if trading["is_demo"]:
            api_status_line.append(f"{trading['mode']} ", style="bold green")
            api_status_line.append("(demo account - fake funds)", style="green")
        else:
            api_status_line.append(f"{trading['mode']} ", style="bold red")
            api_status_line.append("(live account - REAL FUNDS)", style="bold red")
        api_status_line.append(f" │ {trading['base_url']}", style="dim")
        console.print(Panel(api_status_line, border_style="dim yellow" if not trading["is_demo"] else "dim green"))
        
        menu = Table(show_header=False, box=None, padding=(0, 2))
        menu.add_column("Key", style="cyan bold", justify="right", width=4)
        menu.add_column("Action", style="bold", width=35)
        menu.add_column("Description", style="dim", width=40)
        
        menu.add_row("1", "Market Orders (Buy/Sell/TP/SL)", "Execute immediately at market price")
        menu.add_row("2", "Limit Orders", "Place limit buy/sell orders at specific price")
        menu.add_row("3", "Stop Orders (Conditional)", "Stop market/limit orders (trigger-based)")
        menu.add_row("4", "Manage Orders (List/Amend/Cancel)", "View, modify, or cancel open orders")
        menu.add_row("5", "Set Leverage", "Set leverage for a trading symbol")
        menu.add_row("6", "Cancel All Orders", "Cancel all open orders (optionally by symbol)")
        menu.add_row("7", "Back to Main Menu", "Return to main menu")
        
        console.print(Panel(Align.center(menu), title="[bold]ORDERS[/]", border_style="blue"))
        
        choice = get_choice(valid_range=range(1, 8))
        
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
            leverage = int(get_input("Leverage", "3"))
            result = run_tool_action("orders.set_leverage", set_leverage_tool, symbol, leverage, symbol=symbol, leverage=leverage)
            print_result(result)
            Prompt.ask("\nPress Enter to continue")
        elif choice == 6:
            symbol = get_input("Symbol (blank for all)", "")
            result = run_tool_action("orders.cancel_all", cancel_all_orders_tool, symbol=symbol if symbol else None, for_symbol=f" for {symbol}" if symbol else "")
            print_result(result)
            Prompt.ask("\nPress Enter to continue")
        elif choice == 7:
            break


def market_orders_menu(cli: "TradeCLI"):
    """Market orders menu."""
    from trade_cli import (
        clear_screen, print_header, get_input, get_choice,
        run_tool_action, print_result, print_order_preview
    )
    
    while True:
        clear_screen()
        print_header()
        
        menu = Table(show_header=False, box=None, padding=(0, 2))
        menu.add_column("Key", style="cyan bold", justify="right", width=4)
        menu.add_column("Action", style="bold", width=30)
        menu.add_column("Description", style="dim", width=45)
        
        menu.add_row("1", "Market Buy", "Open long position at current market price")
        menu.add_row("2", "Market Sell", "Open short position at current market price")
        menu.add_row("3", "Market Buy with TP/SL", "Buy + set take profit & stop loss")
        menu.add_row("4", "Market Sell with TP/SL", "Sell + set take profit & stop loss")
        menu.add_row("5", "Back to Orders Menu", "Return to orders menu")
        
        console.print(Panel(Align.center(menu), title="[bold]MARKET ORDERS[/]", border_style="blue"))
        
        choice = get_choice(valid_range=range(1, 6))
        
        if choice == 1:
            symbol = get_input("Symbol")
            usd = float(get_input("USD Amount"))
            print_order_preview("Market Buy", symbol, "Buy", usd)
            if Confirm.ask("Confirm execution?"):
                result = run_tool_action("orders.market_buy", market_buy_tool, symbol, usd, symbol=symbol, usd_amount=usd)
                print_result(result)
            else:
                console.print("[yellow]Cancelled[/]")
            Prompt.ask("\nPress Enter to continue")
        elif choice == 2:
            symbol = get_input("Symbol")
            usd = float(get_input("USD Amount"))
            print_order_preview("Market Sell", symbol, "Sell", usd)
            if Confirm.ask("Confirm execution?"):
                result = run_tool_action("orders.market_sell", market_sell_tool, symbol, usd, symbol=symbol, usd_amount=usd)
                print_result(result)
            else:
                console.print("[yellow]Cancelled[/]")
            Prompt.ask("\nPress Enter to continue")
        elif choice == 3:
            symbol = get_input("Symbol")
            usd = float(get_input("USD Amount"))
            tp = get_input("Take Profit Price (blank to skip)", "")
            sl = get_input("Stop Loss Price (blank to skip)", "")
            print_order_preview("Market Buy + TP/SL", symbol, "Buy", usd, 
                              take_profit=tp, stop_loss=sl)
            if Confirm.ask("Confirm execution?"):
                result = run_tool_action(
                    "orders.market_buy_tpsl", market_buy_with_tpsl_tool,
                    symbol, usd,
                    take_profit=float(tp) if tp else None,
                    stop_loss=float(sl) if sl else None,
                    symbol=symbol, usd_amount=usd
                )
                print_result(result)
            else:
                console.print("[yellow]Cancelled[/]")
            Prompt.ask("\nPress Enter to continue")
        elif choice == 4:
            symbol = get_input("Symbol")
            usd = float(get_input("USD Amount"))
            tp = get_input("Take Profit Price (blank to skip)", "")
            sl = get_input("Stop Loss Price (blank to skip)", "")
            print_order_preview("Market Sell + TP/SL", symbol, "Sell", usd,
                              take_profit=tp, stop_loss=sl)
            if Confirm.ask("Confirm execution?"):
                result = run_tool_action(
                    "orders.market_sell_tpsl", market_sell_with_tpsl_tool,
                    symbol, usd,
                    take_profit=float(tp) if tp else None,
                    stop_loss=float(sl) if sl else None,
                    symbol=symbol, usd_amount=usd
                )
                print_result(result)
            else:
                console.print("[yellow]Cancelled[/]")
            Prompt.ask("\nPress Enter to continue")
        elif choice == 5:
            break


def limit_orders_menu(cli: "TradeCLI"):
    """Limit orders menu."""
    from trade_cli import (
        clear_screen, print_header, get_input, get_choice,
        run_tool_action, print_result, print_order_preview
    )
    
    while True:
        clear_screen()
        print_header()
        
        menu = Table(show_header=False, box=None, padding=(0, 2))
        menu.add_column("Key", style="cyan bold", justify="right", width=4)
        menu.add_column("Action", style="bold", width=30)
        menu.add_column("Description", style="dim", width=45)
        
        menu.add_row("1", "Limit Buy", "Place limit buy order at specified price")
        menu.add_row("2", "Limit Sell", "Place limit sell order at specified price")
        menu.add_row("3", "Back to Orders Menu", "Return to orders menu")
        
        console.print(Panel(Align.center(menu), title="[bold]LIMIT ORDERS[/]", border_style="blue"))
        
        choice = get_choice(valid_range=range(1, 4))
        
        if choice == 1:
            symbol = get_input("Symbol")
            usd = float(get_input("USD Amount"))
            price = float(get_input("Limit Price"))
            tif = get_input("Time in Force (GTC/IOC/FOK/PostOnly)", "GTC")
            reduce_only = Confirm.ask("Reduce Only?", default=False)
            
            print_order_preview("Limit Buy", symbol, "Buy", usd, price=price, 
                              tif=tif, reduce_only=reduce_only)
            
            if Confirm.ask("Confirm execution?"):
                result = run_tool_action("orders.limit_buy", limit_buy_tool, symbol, usd, price, time_in_force=tif, reduce_only=reduce_only, symbol=symbol, usd_amount=usd, price=price)
                print_result(result)
            else:
                console.print("[yellow]Cancelled[/]")
            Prompt.ask("\nPress Enter to continue")
        elif choice == 2:
            symbol = get_input("Symbol")
            usd = float(get_input("USD Amount"))
            price = float(get_input("Limit Price"))
            tif = get_input("Time in Force (GTC/IOC/FOK/PostOnly)", "GTC")
            reduce_only = Confirm.ask("Reduce Only?", default=False)
            
            print_order_preview("Limit Sell", symbol, "Sell", usd, price=price,
                              tif=tif, reduce_only=reduce_only)
            
            if Confirm.ask("Confirm execution?"):
                result = run_tool_action("orders.limit_sell", limit_sell_tool, symbol, usd, price, time_in_force=tif, reduce_only=reduce_only, symbol=symbol, usd_amount=usd, price=price)
                print_result(result)
            else:
                console.print("[yellow]Cancelled[/]")
            Prompt.ask("\nPress Enter to continue")
        elif choice == 3:
            break


def stop_orders_menu(cli: "TradeCLI"):
    """Stop orders menu."""
    from trade_cli import (
        clear_screen, print_header, get_input, get_choice,
        run_tool_action, print_result, print_order_preview
    )
    
    while True:
        clear_screen()
        print_header()
        
        menu = Table(show_header=False, box=None, padding=(0, 2))
        menu.add_column("Key", style="cyan bold", justify="right", width=4)
        menu.add_column("Action", style="bold", width=30)
        menu.add_column("Description", style="dim", width=45)
        
        menu.add_row("1", "Stop Market Buy", "Buy when price rises/falls to trigger")
        menu.add_row("2", "Stop Market Sell", "Sell when price rises/falls to trigger")
        menu.add_row("3", "Stop Limit Buy", "Limit buy triggered at stop price")
        menu.add_row("4", "Stop Limit Sell", "Limit sell triggered at stop price")
        menu.add_row("5", "Back to Orders Menu", "Return to orders menu")
        
        console.print(Panel(Align.center(menu), title="[bold]STOP/CONDITIONAL ORDERS[/]", border_style="blue"))
        
        choice = get_choice(valid_range=range(1, 6))
        
        if choice == 1:
            symbol = get_input("Symbol")
            usd = float(get_input("USD Amount"))
            trigger = float(get_input("Trigger Price"))
            direction = int(get_input("Trigger Direction (1=Rise, 2=Fall)", "1"))
            
            print_order_preview("Stop Market Buy", symbol, "Buy", usd, 
                              trigger_price=trigger, 
                              condition="Rises to" if direction==1 else "Falls to")
            
            if Confirm.ask("Confirm execution?"):
                result = run_tool_action("orders.stop_market_buy", stop_market_buy_tool, symbol, usd, trigger, trigger_direction=direction, symbol=symbol, trigger=trigger)
                print_result(result)
            else:
                console.print("[yellow]Cancelled[/]")
            Prompt.ask("\nPress Enter to continue")
        elif choice == 2:
            symbol = get_input("Symbol")
            usd = float(get_input("USD Amount"))
            trigger = float(get_input("Trigger Price"))
            direction = int(get_input("Trigger Direction (1=Rise, 2=Fall)", "2"))
            
            print_order_preview("Stop Market Sell", symbol, "Sell", usd,
                              trigger_price=trigger,
                              condition="Rises to" if direction==1 else "Falls to")
            
            if Confirm.ask("Confirm execution?"):
                result = run_tool_action("orders.stop_market_sell", stop_market_sell_tool, symbol, usd, trigger, trigger_direction=direction, symbol=symbol, trigger=trigger)
                print_result(result)
            else:
                console.print("[yellow]Cancelled[/]")
            Prompt.ask("\nPress Enter to continue")
        elif choice == 3:
            symbol = get_input("Symbol")
            usd = float(get_input("USD Amount"))
            trigger = float(get_input("Trigger Price"))
            limit = float(get_input("Limit Price"))
            direction = int(get_input("Trigger Direction (1=Rise, 2=Fall)", "1"))
            
            print_order_preview("Stop Limit Buy", symbol, "Buy", usd, price=limit,
                              trigger_price=trigger,
                              condition="Rises to" if direction==1 else "Falls to")
            
            if Confirm.ask("Confirm execution?"):
                result = run_tool_action("orders.stop_limit_buy", stop_limit_buy_tool, symbol, usd, trigger, limit, trigger_direction=direction, symbol=symbol, trigger=trigger, limit=limit)
                print_result(result)
            else:
                console.print("[yellow]Cancelled[/]")
            Prompt.ask("\nPress Enter to continue")
        elif choice == 4:
            symbol = get_input("Symbol")
            usd = float(get_input("USD Amount"))
            trigger = float(get_input("Trigger Price"))
            limit = float(get_input("Limit Price"))
            direction = int(get_input("Trigger Direction (1=Rise, 2=Fall)", "2"))
            
            print_order_preview("Stop Limit Sell", symbol, "Sell", usd, price=limit,
                              trigger_price=trigger,
                              condition="Rises to" if direction==1 else "Falls to")
            
            if Confirm.ask("Confirm execution?"):
                result = run_tool_action("orders.stop_limit_sell", stop_limit_sell_tool, symbol, usd, trigger, limit, trigger_direction=direction, symbol=symbol, trigger=trigger, limit=limit)
                print_result(result)
            else:
                console.print("[yellow]Cancelled[/]")
            Prompt.ask("\nPress Enter to continue")
        elif choice == 5:
            break


def manage_orders_menu(cli: "TradeCLI"):
    """Manage existing orders."""
    from trade_cli import (
        clear_screen, print_header, get_input, get_choice,
        run_tool_action, print_result
    )
    
    while True:
        clear_screen()
        print_header()
        
        menu = Table(show_header=False, box=None, padding=(0, 2))
        menu.add_column("Key", style="cyan bold", justify="right", width=4)
        menu.add_column("Action", style="bold", width=30)
        menu.add_column("Description", style="dim", width=45)
        
        menu.add_row("1", "List Open Orders", "View all open orders (optionally by symbol)")
        menu.add_row("2", "Amend Order", "Modify order (qty, price, TP/SL)")
        menu.add_row("3", "Cancel Order", "Cancel a specific order by ID")
        menu.add_row("4", "Back to Orders Menu", "Return to orders menu")
        
        console.print(Panel(Align.center(menu), title="[bold]MANAGE ORDERS[/]", border_style="blue"))
        
        choice = get_choice(valid_range=range(1, 5))
        
        if choice == 1:
            symbol = get_input("Symbol (blank for all)", "")
            result = run_tool_action("orders.list", get_open_orders_tool, symbol=symbol if symbol else None, for_symbol=f" for {symbol}" if symbol else "")
            print_result(result)
            Prompt.ask("\nPress Enter to continue")
        elif choice == 2:
            symbol = get_input("Symbol")
            order_id = get_input("Order ID")
            
            console.print("\n[dim]Leave blank to keep unchanged[/]")
            new_qty = get_input("New Quantity (blank to keep)", "")
            new_price = get_input("New Price (blank to keep)", "")
            new_tp = get_input("New Take Profit (blank to keep)", "")
            new_sl = get_input("New Stop Loss (blank to keep)", "")
            
            result = run_tool_action(
                "orders.amend", amend_order_tool,
                symbol, order_id,
                qty=float(new_qty) if new_qty else None,
                price=float(new_price) if new_price else None,
                take_profit=float(new_tp) if new_tp else None,
                stop_loss=float(new_sl) if new_sl else None,
                symbol=symbol, order_id=order_id
            )
            print_result(result)
            Prompt.ask("\nPress Enter to continue")
        elif choice == 3:
            symbol = get_input("Symbol")
            order_id = get_input("Order ID")
            if Confirm.ask(f"Cancel order {order_id}?"):
                result = run_tool_action("orders.cancel", cancel_order_tool, symbol, order_id, symbol=symbol, order_id=order_id)
                print_result(result)
            else:
                console.print("[yellow]Cancelled[/]")
            Prompt.ask("\nPress Enter to continue")
        elif choice == 4:
            break

