"""
Account menu for the CLI.

Handles all account-related operations:
- Balance and exposure views
- Account info and portfolio snapshots
- Order and PnL history
- Unified account operations (collateral, borrow, margin mode)
"""

from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt
from rich.align import Align

from src.tools import (
    get_account_balance_tool,
    get_total_exposure_tool,
    get_account_info_tool,
    get_portfolio_snapshot_tool,
    get_order_history_tool,
    get_closed_pnl_tool,
    get_transaction_log_tool,
    get_collateral_info_tool,
    set_collateral_coin_tool,
    get_borrow_history_tool,
    get_coin_greeks_tool,
    set_account_margin_mode_tool,
    get_transferable_amount_tool,
)

if TYPE_CHECKING:
    from trade_cli import TradeCLI

# Local console
console = Console()


def account_menu(cli: "TradeCLI"):
    """Account and balance menu."""
    from trade_cli import (
        clear_screen, print_header, get_input, get_choice,
        print_error_below_menu, run_tool_action, print_result,
        select_time_range_cli, BACK
    )
    
    while True:
        clear_screen()
        print_header()
        
        menu = Table(show_header=False, box=None, padding=(0, 2))
        menu.add_column("Key", style="cyan bold", justify="right", width=4)
        menu.add_column("Action", style="bold", width=30)
        menu.add_column("Description", style="dim", width=45)
        
        menu.add_row("1", "View Balance", "Current account balance (USDT, BTC, etc.)")
        menu.add_row("2", "View Exposure", "Total position exposure and margin used")
        menu.add_row("3", "Account Info", "Account details, margin mode, risk limits")
        menu.add_row("4", "Portfolio Snapshot", "Complete portfolio with positions & PnL")
        menu.add_row("5", "Order History", "Recent orders [dim](select time range, max 7d)[/]")
        menu.add_row("6", "Closed PnL", "Realized PnL [dim](select time range, max 7d)[/]")
        menu.add_row("", "", "")
        menu.add_row("", "[dim]--- Unified Account ---[/]", "")
        menu.add_row("7", "Transaction Log", "Transactions [dim](select time range, max 7d)[/]")
        menu.add_row("8", "Collateral Info", "Collateral coins and their settings")
        menu.add_row("9", "Set Collateral Coin", "Enable/disable coins as collateral")
        menu.add_row("10", "Borrow History", "Borrow records [dim](select time range, max 30d)[/]")
        menu.add_row("11", "Coin Greeks (Options)", "Options Greeks for base coins")
        menu.add_row("12", "Set Margin Mode", "Switch between Regular/Portfolio margin")
        menu.add_row("13", "Transferable Amount", "Amount available to transfer out")
        menu.add_row("14", "Back to Main Menu", "Return to main menu")
        
        console.print(Panel(Align.center(menu), title="[bold]ACCOUNT & BALANCE[/]", border_style="blue"))
        
        choice = get_choice(valid_range=range(1, 15))
        
        # Handle back command from menu choice
        if choice is BACK:
            break
        
        if choice == 1:
            result = run_tool_action("account.view_balance", get_account_balance_tool)
            print_result(result)
            Prompt.ask("\nPress Enter to continue")
        elif choice == 2:
            result = run_tool_action("account.view_exposure", get_total_exposure_tool)
            print_result(result)
            Prompt.ask("\nPress Enter to continue")
        elif choice == 3:
            result = run_tool_action("account.info", get_account_info_tool)
            print_result(result)
            Prompt.ask("\nPress Enter to continue")
        elif choice == 4:
            result = run_tool_action("account.portfolio", get_portfolio_snapshot_tool)
            print_result(result)
            Prompt.ask("\nPress Enter to continue")
        elif choice == 5:
            # Order History - requires time range (max 7 days)
            time_selection = select_time_range_cli(max_days=7, default="7d", endpoint_name="order history")
            if time_selection.is_back:
                continue
            symbol = get_input("Symbol (blank for all)", "")
            if symbol is BACK:
                continue
            limit_input = get_input("Limit (1-50)", "50")
            if limit_input is BACK:
                continue
            try:
                limit = int(limit_input)
                result = run_tool_action(
                    "account.order_history", get_order_history_tool,
                    window=time_selection.window,
                    start_ms=time_selection.start_ms,
                    end_ms=time_selection.end_ms,
                    symbol=symbol if symbol else None,
                    limit=limit
                )
                print_result(result)
            except ValueError:
                print_error_below_menu(f"'{limit_input}' is not a valid number")
            Prompt.ask("\nPress Enter to continue")
        elif choice == 6:
            # Closed PnL - requires time range (max 7 days)
            time_selection = select_time_range_cli(max_days=7, default="7d", endpoint_name="closed PnL")
            if time_selection.is_back:
                continue
            symbol = get_input("Symbol (blank for all)", "")
            if symbol is BACK:
                continue
            limit_input = get_input("Limit (1-50)", "50")
            if limit_input is BACK:
                continue
            try:
                limit = int(limit_input)
                result = run_tool_action(
                    "account.closed_pnl", get_closed_pnl_tool,
                    window=time_selection.window,
                    start_ms=time_selection.start_ms,
                    end_ms=time_selection.end_ms,
                    symbol=symbol if symbol else None,
                    limit=limit
                )
                print_result(result)
            except ValueError:
                print_error_below_menu(f"'{limit_input}' is not a valid number")
            Prompt.ask("\nPress Enter to continue")
        elif choice == 7:
            # Transaction Log - requires time range (max 7 days)
            time_selection = select_time_range_cli(max_days=7, default="7d", endpoint_name="transaction log")
            if time_selection.is_back:
                continue
            category = get_input("Category (spot/linear/option, blank for all)", "")
            if category is BACK:
                continue
            currency = get_input("Currency (blank for all)", "")
            if currency is BACK:
                continue
            log_type = get_input("Type (TRADE/SETTLEMENT/TRANSFER_IN/etc, blank for all)", "")
            if log_type is BACK:
                continue
            limit_input = get_input("Limit (1-50)", "50")
            if limit_input is BACK:
                continue
            try:
                limit = int(limit_input)
                result = run_tool_action(
                    "account.transaction_log", get_transaction_log_tool,
                    window=time_selection.window,
                    start_ms=time_selection.start_ms,
                    end_ms=time_selection.end_ms,
                    category=category if category else None,
                    currency=currency if currency else None,
                    log_type=log_type if log_type else None,
                    limit=limit
                )
                print_result(result)
            except ValueError:
                print_error_below_menu(f"'{limit_input}' is not a valid number")
            Prompt.ask("\nPress Enter to continue")
        elif choice == 8:
            currency = get_input("Currency (blank for all)", "")
            result = run_tool_action("account.collateral_info", get_collateral_info_tool, currency=currency if currency else None)
            print_result(result)
            Prompt.ask("\nPress Enter to continue")
        elif choice == 9:
            coin = get_input("Coin (e.g., BTC, ETH, USDT)")
            action = get_input("Enable as collateral? (yes/no)", "yes")
            enabled = action.lower() in ("yes", "y", "true", "1")
            result = run_tool_action("account.set_collateral", set_collateral_coin_tool, coin, enabled, coin=coin)
            print_result(result)
            Prompt.ask("\nPress Enter to continue")
        elif choice == 10:
            # Borrow History - requires time range (max 30 days)
            time_selection = select_time_range_cli(max_days=30, default="30d", endpoint_name="borrow history")
            if time_selection.is_back:
                continue
            currency = get_input("Currency (blank for all)", "")
            if currency is BACK:
                continue
            limit_input = get_input("Limit (1-50)", "50")
            if limit_input is BACK:
                continue
            try:
                limit = int(limit_input)
                result = run_tool_action(
                    "account.borrow_history", get_borrow_history_tool,
                    window=time_selection.window,
                    start_ms=time_selection.start_ms,
                    end_ms=time_selection.end_ms,
                    currency=currency if currency else None,
                    limit=limit
                )
                print_result(result)
            except ValueError:
                print_error_below_menu(f"'{limit_input}' is not a valid number")
            Prompt.ask("\nPress Enter to continue")
        elif choice == 11:
            base_coin = get_input("Base coin (BTC/ETH, blank for all)", "")
            result = run_tool_action("account.coin_greeks", get_coin_greeks_tool, base_coin=base_coin if base_coin else None)
            print_result(result)
            Prompt.ask("\nPress Enter to continue")
        elif choice == 12:
            console.print("\n[bold]Margin modes:[/]")
            console.print("  1. Regular Margin (default)")
            console.print("  2. Portfolio Margin")
            mode_choice = get_input("Select mode", "1")
            portfolio_margin = mode_choice == "2"
            result = run_tool_action("account.set_margin_mode", set_account_margin_mode_tool, portfolio_margin)
            print_result(result)
            Prompt.ask("\nPress Enter to continue")
        elif choice == 13:
            coin = get_input("Coin (e.g., USDT, BTC)")
            result = run_tool_action("account.transferable", get_transferable_amount_tool, coin, coin=coin)
            print_result(result)
            Prompt.ask("\nPress Enter to continue")
        elif choice == 14:
            break

