"""
Positions menu for the CLI.

Handles all position management operations:
- List and view positions
- Set TP/SL
- Partial and full closes
- Position configuration (margin mode, risk limits, etc.)
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
    list_open_positions_tool,
    get_position_detail_tool,
    close_position_tool,
    panic_close_all_tool,
    set_stop_loss_tool,
    set_take_profit_tool,
    set_position_tpsl_tool,
    partial_close_position_tool,
    set_risk_limit_tool,
    get_risk_limits_tool,
    set_tp_sl_mode_tool,
    set_auto_add_margin_tool,
    modify_position_margin_tool,
    switch_margin_mode_tool,
    switch_position_mode_tool,
)

if TYPE_CHECKING:
    from trade_cli import TradeCLI

# Local console
console = Console()


def positions_menu(cli: "TradeCLI"):
    """Positions management menu."""
    from trade_cli import (
        clear_screen, print_header, get_input, get_choice,
        print_error_below_menu, run_tool_action, print_result, BACK
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
        menu.add_column("Action", style="bold", width=30)
        menu.add_column("Description", style="dim", width=45)
        
        menu.add_row("1", "List Open Positions", "Show all open positions with PnL, size, entry price")
        menu.add_row("2", "Position Detail", "Input: Symbol (e.g. BTCUSDT) → Shows detailed position info")
        menu.add_row("3", "Set Stop Loss", "Input: Symbol, Price → Sets stop loss order")
        menu.add_row("4", "Set Take Profit", "Input: Symbol, Price → Sets take profit order")
        menu.add_row("5", "Set TP/SL Together", "Input: Symbol, TP price, SL price → Sets both at once")
        menu.add_row("6", "Partial Close", "Input: Symbol, % (0-100), Limit price (optional) → Closes portion")
        menu.add_row("7", "[red]Close Position[/]", "[red]Input: Symbol → Closes entire position at market[/]")
        menu.add_row("8", "[bold red]Close All Positions[/]", "[bold red]Emergency: Closes ALL positions[/]")
        menu.add_row("", "", "")
        menu.add_row("", "[dim]--- Position Config ---[/]", "")
        menu.add_row("9", "View Risk Limits", "Input: Symbol → Shows available risk limit tiers (IDs & max values)")
        menu.add_row("10", "Set Risk Limit", "Input: Symbol → Shows tiers, then enter Risk Limit ID (integer)")
        menu.add_row("11", "Set TP/SL Mode", "Input: Symbol → Choose Full (entire) or Partial (specified qty)")
        menu.add_row("12", "Switch Margin Mode", "Input: Symbol → Choose Cross (shared) or Isolated (per position)")
        menu.add_row("13", "Auto-Add Margin", "Input: Symbol → Enable/disable auto-add margin when needed")
        menu.add_row("14", "Modify Position Margin", "Input: Symbol, Amount → Positive=add, Negative=reduce")
        menu.add_row("15", "Switch Position Mode", "Choose One-way (Buy OR Sell) or Hedge (Buy AND Sell)")
        menu.add_row("16", "Back to Main Menu", "Return to main menu")
        
        console.print(Panel(Align.center(menu), title="[bold]POSITIONS[/]", border_style="blue"))
        console.print("[dim]💡 Tip: Type 'back' or 'b' at any prompt to cancel and return to menu[/]")
        
        choice = get_choice(valid_range=range(1, 17))
        
        # Handle back command from menu choice
        if choice is BACK:
            break
        
        if choice == 1:
            result = run_tool_action("positions.list", list_open_positions_tool)
            print_result(result)
            Prompt.ask("\nPress Enter to continue")
        elif choice == 2:
            symbol = get_input("Symbol (e.g. BTCUSDT, SOLUSDT, ETHUSDT)")
            if symbol is BACK:
                continue
            result = run_tool_action("positions.detail", get_position_detail_tool, symbol, symbol=symbol)
            print_result(result)
            Prompt.ask("\nPress Enter to continue")
        elif choice == 3:
            symbol = get_input("Symbol (e.g. BTCUSDT)")
            if symbol is BACK:
                continue
            price_input = get_input("Stop Loss Price (USD, e.g. 85000.50)")
            if price_input is BACK:
                continue
            try:
                price = float(price_input)
                result = run_tool_action("positions.set_stop_loss", set_stop_loss_tool, symbol, price, symbol=symbol, price=price)
                print_result(result)
            except ValueError:
                print_error_below_menu(f"'{price_input}' is not a valid number")
            Prompt.ask("\nPress Enter to continue")
        elif choice == 4:
            symbol = get_input("Symbol (e.g. BTCUSDT)")
            if symbol is BACK:
                continue
            price_input = get_input("Take Profit Price (USD, e.g. 95000.00)")
            if price_input is BACK:
                continue
            try:
                price = float(price_input)
                result = run_tool_action("positions.set_take_profit", set_take_profit_tool, symbol, price, symbol=symbol, price=price)
                print_result(result)
            except ValueError:
                print_error_below_menu(f"'{price_input}' is not a valid number")
            Prompt.ask("\nPress Enter to continue")
        elif choice == 5:
            symbol = get_input("Symbol (e.g. BTCUSDT)")
            if symbol is BACK:
                continue
            console.print("[dim]Leave blank to skip either TP or SL[/]")
            tp = get_input("Take Profit Price (USD, blank to skip)", "")
            if tp is BACK:
                continue
            sl = get_input("Stop Loss Price (USD, blank to skip)", "")
            if sl is BACK:
                continue
            try:
                result = run_tool_action(
                    "positions.set_tpsl", set_position_tpsl_tool, symbol,
                    take_profit=float(tp) if tp else None,
                    stop_loss=float(sl) if sl else None,
                    symbol=symbol
                )
                print_result(result)
            except ValueError as e:
                print_error_below_menu(f"Invalid price format - {e}")
            Prompt.ask("\nPress Enter to continue")
        elif choice == 6:
            symbol = get_input("Symbol (e.g. BTCUSDT)")
            if symbol is BACK:
                continue
            percent_input = get_input("Close Percentage (0-100, e.g. 50 for 50%)", "50")
            if percent_input is BACK:
                continue
            price = get_input("Limit Price (USD, blank for Market order)", "")
            if price is BACK:
                continue
            try:
                percent = float(percent_input)
                if percent < 0 or percent > 100:
                    print_error_below_menu("Percentage must be between 0 and 100")
                else:
                    result = run_tool_action(
                        "positions.partial_close", partial_close_position_tool,
                        symbol, percent, price=float(price) if price else None,
                        symbol=symbol, percent=percent
                    )
                    print_result(result)
            except ValueError:
                print_error_below_menu(f"'{percent_input}' is not a valid number")
            Prompt.ask("\nPress Enter to continue")
        elif choice == 7:
            symbol = get_input("Symbol")
            if symbol is BACK:
                continue
            if Confirm.ask(f"[yellow]Close entire {symbol} position?[/]"):
                result = run_tool_action("positions.close", close_position_tool, symbol, symbol=symbol)
                print_result(result)
            else:
                console.print("[yellow]Cancelled.[/]")
            Prompt.ask("\nPress Enter to continue")
        elif choice == 8:
            if Confirm.ask("[bold red]Are you sure you want to CLOSE ALL POSITIONS?[/]"):
                result = run_tool_action("positions.close_all", panic_close_all_tool, reason="User requested close all")
                print_result(result)
            else:
                console.print("[yellow]Cancelled.[/]")
            Prompt.ask("\nPress Enter to continue")
        elif choice == 9:
            symbol = get_input("Symbol (e.g. BTCUSDT, SOLUSDT)")
            if symbol is BACK:
                continue
            result = run_tool_action("positions.risk_limits", get_risk_limits_tool, symbol, symbol=symbol)
            if result.success and result.data:
                console.print(f"\n[bold cyan]Available Risk Limit Tiers for {symbol}:[/]")
                rl_table = Table(show_header=True, header_style="bold magenta")
                rl_table.add_column("Risk Limit ID", style="cyan")
                rl_table.add_column("Max Position Value (USD)", justify="right")
                rl_table.add_column("Maintenance Margin Rate", justify="right")
                
                for rl in result.data.get("risk_limits", []):
                    rl_table.add_row(
                        str(rl.get('id')), 
                        f"${float(rl.get('riskLimitValue', 0)):,.0f}",
                        f"{float(rl.get('maintenanceMarginRate', 0)):.2%}" if rl.get('maintenanceMarginRate') else "N/A"
                    )
                console.print(rl_table)
                console.print(f"\n[dim]Use option 10 to set a risk limit by entering the Risk Limit ID number[/]")
            print_result(result)
            Prompt.ask("\nPress Enter to continue")
        elif choice == 10:
            symbol = get_input("Symbol (e.g. BTCUSDT, SOLUSDT)")
            if symbol is BACK:
                continue
            # First show available risk limits
            limits_result = run_tool_action("positions.risk_limits", get_risk_limits_tool, symbol, symbol=symbol)
            if limits_result.success and limits_result.data:
                console.print(f"\n[bold cyan]Available Risk Limit Tiers for {symbol}:[/]")
                rl_table = Table(show_header=True, header_style="bold magenta")
                rl_table.add_column("Risk Limit ID", style="cyan")
                rl_table.add_column("Max Position Value (USD)", justify="right")
                
                for rl in limits_result.data.get("risk_limits", [])[:10]:
                    rl_table.add_row(
                        str(rl.get('id')), 
                        f"${float(rl.get('riskLimitValue', 0)):,.0f}"
                    )
                console.print(rl_table)
                console.print(f"\n[yellow]Enter the Risk Limit ID number (integer) from the table above[/]")
                
            risk_id_input = get_input("Risk Limit ID (integer number)", "")
            if risk_id_input is BACK:
                continue
            if not risk_id_input:
                console.print("[yellow]Cancelled - no risk limit ID provided[/]")
            else:
                try:
                    risk_id = int(risk_id_input)
                    result = run_tool_action("positions.set_risk_limit", set_risk_limit_tool, symbol, risk_id, symbol=symbol, risk_id=risk_id)
                    print_result(result)
                except ValueError:
                    print_error_below_menu(f"'{risk_id_input}' is not a valid integer. Please enter a number.")
            Prompt.ask("\nPress Enter to continue")
        elif choice == 11:
            symbol = get_input("Symbol (e.g. BTCUSDT)")
            if symbol is BACK:
                continue
            console.print("\n[bold]TP/SL Modes:[/]")
            console.print("  [cyan]1[/]. Full - TP/SL applies to entire position (default)")
            console.print("  [cyan]2[/]. Partial - TP/SL applies to specified quantity only")
            mode_choice = get_input("Select mode (1 or 2)", "1")
            if mode_choice is BACK:
                continue
            full_mode = mode_choice == "1"
            result = run_tool_action("positions.set_tpsl_mode", set_tp_sl_mode_tool, symbol, full_mode, symbol=symbol)
            print_result(result)
            Prompt.ask("\nPress Enter to continue")
        elif choice == 12:
            symbol = get_input("Symbol (e.g. BTCUSDT)")
            if symbol is BACK:
                continue
            console.print("\n[bold]Margin Modes:[/]")
            console.print("  [cyan]1[/]. Cross margin - Shares margin across all positions")
            console.print("  [cyan]2[/]. Isolated margin - Separate margin per position")
            mode_choice = get_input("Select mode (1 or 2)", "1")
            if mode_choice is BACK:
                continue
            isolated = mode_choice == "2"
            leverage_input = get_input("Leverage (1-100, blank to keep current)", "")
            if leverage_input is BACK:
                continue
            try:
                lev_value = int(leverage_input) if leverage_input else None
                if lev_value and (lev_value < 1 or lev_value > 100):
                    print_error_below_menu("Leverage must be between 1 and 100")
                    lev_value = None
                result = run_tool_action("positions.switch_margin_mode", switch_margin_mode_tool, symbol, isolated, lev_value, symbol=symbol)
                print_result(result)
            except ValueError:
                print_error_below_menu(f"'{leverage_input}' is not a valid integer")
            Prompt.ask("\nPress Enter to continue")
        elif choice == 13:
            symbol = get_input("Symbol (e.g. BTCUSDT)")
            if symbol is BACK:
                continue
            console.print("\n[yellow]Auto-add margin automatically adds margin when position is at risk[/]")
            enabled = Confirm.ask("Enable auto-add margin?", default=False)
            result = run_tool_action("positions.auto_add_margin", set_auto_add_margin_tool, symbol, enabled, symbol=symbol)
            print_result(result)
            Prompt.ask("\nPress Enter to continue")
        elif choice == 14:
            symbol = get_input("Symbol (e.g. BTCUSDT)")
            if symbol is BACK:
                continue
            console.print("\n[yellow]Enter positive amount to ADD margin, negative to REDUCE margin[/]")
            margin_input = get_input("Margin amount (USD, e.g. 100 or -50)", "")
            if margin_input is BACK:
                continue
            try:
                margin = float(margin_input)
                result = run_tool_action("positions.modify_margin", modify_position_margin_tool, symbol, margin, symbol=symbol)
                print_result(result)
            except ValueError:
                print_error_below_menu(f"'{margin_input}' is not a valid number")
            Prompt.ask("\nPress Enter to continue")
        elif choice == 15:
            console.print("\n[bold]Position Modes:[/]")
            console.print("  [cyan]1[/]. One-way mode - Can only hold Buy OR Sell (not both)")
            console.print("  [cyan]2[/]. Hedge mode - Can hold both Buy AND Sell simultaneously")
            console.print("\n[yellow]Note: This affects ALL positions, not just one symbol[/]")
            mode_choice = get_input("Select mode (1 or 2)", "1")
            if mode_choice is BACK:
                continue
            hedge_mode = mode_choice == "2"
            result = run_tool_action("positions.switch_mode", switch_position_mode_tool, hedge_mode)
            print_result(result)
            Prompt.ask("\nPress Enter to continue")
        elif choice == 16:
            break

