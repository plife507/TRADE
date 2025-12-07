#!/usr/bin/env python3
"""
TRADE - Trading Bot CLI

Menu-driven CLI for the TRADE trading bot.
This is a PURE SHELL - it only:
- Gets user input
- Calls tool functions
- Prints results

NO business logic lives here. All operations go through src/tools/*.
All symbols, amounts, and parameters are passed from user input.

Strategies, backtesting, and runners will be added in Phase 2.
"""

import os
import sys
from typing import Optional, Dict, Any, List
from datetime import datetime

# Rich imports
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, IntPrompt, Confirm
from rich.tree import Tree
from rich.align import Align
from rich import print as rprint
from rich.style import Style
from rich.text import Text

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config.config import get_config
from src.core.application import Application, get_application
from src.utils.logger import setup_logger, get_logger
from src.tools import (
    # Shared types
    ToolResult,
    # Position tools
    list_open_positions_tool,
    get_position_detail_tool,
    close_position_tool,
    panic_close_all_tool,
    set_stop_loss_tool,
    set_take_profit_tool,
    set_position_tpsl_tool,
    # Position configuration tools
    set_risk_limit_tool,
    get_risk_limits_tool,
    set_tp_sl_mode_tool,
    set_auto_add_margin_tool,
    modify_position_margin_tool,
    switch_margin_mode_tool,
    switch_position_mode_tool,
    # Account tools
    get_account_balance_tool,
    get_total_exposure_tool,
    get_account_info_tool,
    get_portfolio_snapshot_tool,
    get_order_history_tool,
    get_closed_pnl_tool,
    # Unified account tools
    get_transaction_log_tool,
    get_collateral_info_tool,
    set_collateral_coin_tool,
    get_borrow_history_tool,
    get_coin_greeks_tool,
    set_account_margin_mode_tool,
    get_transferable_amount_tool,
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
    partial_close_position_tool,
    cancel_all_orders_tool,
    # Diagnostics tools
    test_connection_tool,
    get_server_time_offset_tool,
    get_rate_limit_status_tool,
    get_ticker_tool,
    get_websocket_status_tool,
    exchange_health_check_tool,
    get_api_environment_tool,
    # Market data tools
    get_price_tool,
    get_ohlcv_tool,
    get_funding_rate_tool,
    get_open_interest_tool,
    get_orderbook_tool,
    get_instruments_tool,
    run_market_data_tests_tool,
    # Data tools
    get_database_stats_tool,
    list_cached_symbols_tool,
    get_symbol_status_tool,
    get_symbol_summary_tool,
    get_symbol_timeframe_ranges_tool,
    sync_symbols_tool,
    sync_range_tool,
    fill_gaps_tool,
    heal_data_tool,
    delete_symbol_tool,
    cleanup_empty_symbols_tool,
    vacuum_database_tool,
    # Funding & Open Interest tools
    sync_funding_tool,
    get_funding_history_tool,
    sync_open_interest_tool,
    get_open_interest_history_tool,
    # Sync to now tools
    sync_to_now_tool,
    sync_to_now_and_fill_gaps_tool,
    # Composite build tools
    build_symbol_history_tool,
)


# Global Console
console = Console()


class BackCommand:
    """Sentinel class to represent 'back' command."""
    pass


BACK = BackCommand()


def is_exit_command(value: str) -> bool:
    """Check if input is an exit command."""
    if not isinstance(value, str):
        return False
    exit_commands = ["back", "b", "q", "quit", "exit", "x"]
    return value.lower().strip() in exit_commands


def clear_screen():
    """Clear terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')


def print_header():
    """Print CLI header with clear environment indication."""
    config = get_config()
    
    # API mode (Demo vs Live)
    is_demo = config.bybit.use_demo
    mode_str = "DEMO" if is_demo else "LIVE"
    mode_style = "bold green" if is_demo else "bold red"
    
    # Trading mode (paper vs real)
    trading_mode = config.trading.mode
    trade_style = "bold yellow" if trading_mode == "paper" else "bold red"
    
    # Account type
    account_type = "UNIFIED"
    
    # Get API environment summary for extended info
    api_env = config.bybit.get_api_environment_summary()
    trading_url = api_env["trading"]["base_url"]
    data_url = api_env["data"]["base_url"]
    
    grid = Table.grid(expand=True)
    grid.add_column(justify="center", ratio=1)
    grid.add_column(justify="center", ratio=1)
    grid.add_column(justify="center", ratio=1)
    
    grid.add_row(
        f"[{mode_style}]▶ {mode_str} Account[/]",
        f"Trading: [{trade_style}]{trading_mode.upper()}[/]",
        f"[cyan]{account_type}[/]"
    )
    
    # Warning for live mode
    warning_panel = None
    if not is_demo:
        warning_panel = Panel(
            "[bold red]⚠  CAUTION: Connected to LIVE account - REAL MONEY ⚠[/]",
            border_style="red",
            expand=False
        )

    title = Text("TRADE - Bybit Unified Trading Account", style="bold cyan")
    content = [grid]
    if warning_panel:
        content.append(warning_panel)
    
    # Build subtitle with API environment info + session indicator
    subtitle_text = f"[dim]REST: {mode_str}({trading_url}) | DATA: LIVE({data_url}) | Session Mode | v1.0[/dim]"
        
    panel = Panel(
        Align.center(grid),
        title=title,
        border_style="cyan" if is_demo else "red",
        subtitle=subtitle_text
    )
    console.print(panel)
    if warning_panel:
        console.print(Align.center(warning_panel))


def get_input(prompt: str, default: str = "") -> str:
    """
    Get user input with optional default.
    
    Supports exit commands: back, b, q, quit, exit, x
    Returns BACK sentinel if exit command detected.
    """
    hint = "[dim](or 'back'/'b' to cancel)[/]"
    try:
        user_input = Prompt.ask(f"[cyan]{prompt}[/] {hint}", default=default if default else None, show_default=bool(default))
        
        if is_exit_command(user_input):
            return BACK
        return user_input
    except (EOFError, KeyboardInterrupt):
        # User pressed Ctrl+C or closed terminal
        console.print("\n[yellow]Cancelled.[/]")
        return BACK


def get_choice(valid_range: range = None) -> int:
    """
    Get numeric choice from user.
    
    Supports exit commands: back, b, q, quit, exit, x
    Returns BACK sentinel if exit command detected.
    """
    while True:
        try:
            choice_input = Prompt.ask("\n[bold cyan]Enter choice[/] [dim](or 'back'/'b' to go back)[/]")
            
            # Check for exit commands
            if is_exit_command(choice_input):
                return BACK
            
            # Try to parse as integer
            choice = int(choice_input)
            
            if valid_range and choice not in valid_range:
                console.print(f"[red]Invalid choice. Please enter a number between {valid_range.start} and {valid_range.stop-1}.[/]")
                continue
            return choice
        except (EOFError, KeyboardInterrupt):
            # User pressed Ctrl+C or closed terminal
            console.print("\n[yellow]Cancelled.[/]")
            return BACK
        except ValueError:
            console.print(f"[red]Invalid input. Please enter a number or 'back'/'b' to go back.[/]")
            continue


def get_time_window(
    max_days: int = 7,
    default: str = "24h",
    include_custom: bool = True,
) -> str:
    """
    Prompt user to select a time window for history queries.
    
    Args:
        max_days: Maximum allowed days (7 for most, 30 for borrow history)
        default: Default window if user just presses Enter
        include_custom: Whether to include custom date option
    
    Returns:
        Window string like "24h", "7d", "30d" or BACK sentinel
    """
    console.print("\n[bold cyan]Select time range:[/]")
    console.print("  1) Last 24 hours")
    console.print("  2) Last 7 days")
    if max_days >= 30:
        console.print("  3) Last 30 days")
        max_option = 3
    else:
        max_option = 2
    
    if include_custom:
        console.print(f"  {max_option + 1}) Custom (coming soon)")
    
    console.print(f"\n[dim]Default: {default}. Max: {max_days} days.[/]")
    
    choice_input = get_input(f"Time range [1-{max_option}]", "1")
    if choice_input is BACK:
        return BACK
    
    window_map = {
        "1": "24h",
        "2": "7d",
        "3": "30d" if max_days >= 30 else "7d",
    }
    
    return window_map.get(choice_input, default)


def print_result(result: ToolResult):
    """Print a ToolResult in a formatted way."""
    if result.success:
        console.print(Panel(f"[bold green]✓ {result.message}[/]", border_style="green"))
        
        if result.data:
            if isinstance(result.data, list):
                # Determine if list of objects or simple list
                if result.data and isinstance(result.data[0], dict):
                    # Table for list of dicts
                    table = Table(show_header=True, header_style="bold magenta")
                    keys = result.data[0].keys()
                    for key in keys:
                        table.add_column(str(key))
                    
                    for item in result.data[:20]:  # Limit rows
                        row_vals = [str(item.get(k, "")) for k in keys]
                        table.add_row(*row_vals)
                    
                    console.print(table)
                    if len(result.data) > 20:
                        console.print(f"[dim]... and {len(result.data) - 20} more items[/]")
                else:
                    # Simple list
                    for item in result.data:
                        console.print(f"  • {item}")
            
            elif isinstance(result.data, dict):
                # Tree view for dictionary
                tree = Tree("[bold cyan]Result Data[/]")
                
                def add_dict_to_tree(d, parent):
                    for k, v in d.items():
                        if isinstance(v, dict):
                            branch = parent.add(f"[yellow]{k}[/]")
                            add_dict_to_tree(v, branch)
                        elif isinstance(v, list):
                            branch = parent.add(f"[yellow]{k}[/]")
                            for item in v[:10]:
                                branch.add(str(item))
                            if len(v) > 10:
                                branch.add(f"[dim]... {len(v)-10} more[/]")
                        else:
                            parent.add(f"[cyan]{k}:[/] {v}")
                
                add_dict_to_tree(result.data, tree)
                console.print(tree)
            else:
                console.print(f"[cyan]Data:[/] {result.data}")
    else:
        console.print(Panel(f"[bold red]✗ Error: {result.error}[/]", border_style="red"))


def print_order_preview(order_type: str, symbol: str, side: str, qty_usd: float, price: float = None, **kwargs):
    """Print a preview panel for an order."""
    grid = Table.grid(expand=True, padding=(0, 2))
    grid.add_column(justify="right", style="cyan")
    grid.add_column(justify="left", style="bold white")
    
    grid.add_row("Type:", order_type)
    grid.add_row("Symbol:", symbol)
    side_style = "green" if side.lower() == "buy" else "red"
    grid.add_row("Side:", f"[{side_style}]{side.upper()}[/]")
    grid.add_row("Amount:", f"${qty_usd:,.2f}")
    
    if price:
        grid.add_row("Price:", f"${price:,.2f}")
        
    for k, v in kwargs.items():
        if v is not None:
            grid.add_row(f"{k.replace('_', ' ').title()}:", str(v))
            
    panel = Panel(
        Align.center(grid),
        title="[bold yellow]Order Preview[/]",
        border_style="yellow",
        subtitle="[dim]Press Enter to execute, Ctrl+C to cancel[/]"
    )
    console.print(panel)


import logging

class TradeCLI:
    """
    Main CLI class.
    
    This is a PURE SHELL - no business logic, no direct exchange calls.
    All operations go through tool functions from src/tools/*.
    """
    
    def __init__(self):
        """Initialize CLI - only config and logger needed."""
        self.config = get_config()
        self.logger = get_logger()
        
    # ==================== MAIN MENU ====================
    
    def main_menu(self):
        """Display main menu."""
        while True:
            clear_screen()
            print_header()
            
            menu = Table(show_header=False, box=None, padding=(0, 2))
            menu.add_column("Key", style="cyan bold", justify="right", width=4)
            menu.add_column("Action", style="bold", width=25)
            menu.add_column("Description", style="dim", width=50)
            
            menu.add_row("1", "Account & Balance", "View balance, exposure, portfolio, transaction history")
            menu.add_row("2", "Positions", "List, manage, close positions, set TP/SL, trailing stops")
            menu.add_row("3", "Orders", "Place market/limit/stop orders, manage open orders")
            menu.add_row("4", "Market Data", "Get prices, OHLCV, funding rates, orderbook, instruments")
            menu.add_row("5", "Data Builder", "Build & manage historical data (DuckDB)")
            menu.add_row("6", "Connection Test", "Test API connectivity and rate limits")
            menu.add_row("7", "Health Check", "Comprehensive system health diagnostic")
            menu.add_row("8", "[bold red]PANIC: Close All & Stop[/]", "[red]Emergency: Close all positions & cancel orders[/]")
            menu.add_row("9", "Exit", "Exit the CLI")
            
            console.print(Panel(Align.center(menu), title="[bold]MAIN MENU[/]", border_style="blue"))
            console.print("[dim]💡 Tip: Type 'back' or 'b' at any prompt to cancel and return to previous menu[/]")
            
            choice = get_choice(valid_range=range(1, 10))
            
            # Handle back command from main menu (same as exit)
            if choice is BACK:
                console.print(f"\n[yellow]Goodbye![/]")
                break
            
            if choice == 1:
                self.account_menu()
            elif choice == 2:
                self.positions_menu()
            elif choice == 3:
                self.orders_menu()
            elif choice == 4:
                self.market_data_menu()
            elif choice == 5:
                self.data_menu()
            elif choice == 6:
                self.connection_test()
            elif choice == 7:
                self.health_check()
            elif choice == 8:
                self.panic_menu()
            elif choice == 9:
                console.print(f"\n[yellow]Goodbye![/]")
                break
    
    # ==================== ACCOUNT MENU ====================
    
    def account_menu(self):
        """Account and balance menu."""
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
                result = get_account_balance_tool()
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 2:
                result = get_total_exposure_tool()
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 3:
                result = get_account_info_tool()
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 4:
                result = get_portfolio_snapshot_tool()
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 5:
                # Order History - requires time range (max 7 days)
                window = get_time_window(max_days=7, default="7d")
                if window is BACK:
                    continue
                symbol = get_input("Symbol (blank for all)", "")
                if symbol is BACK:
                    continue
                limit_input = get_input("Limit (1-50)", "50")
                if limit_input is BACK:
                    continue
                try:
                    limit = int(limit_input)
                    result = get_order_history_tool(
                        window=window,
                        symbol=symbol if symbol else None,
                        limit=limit,
                    )
                    print_result(result)
                except ValueError:
                    console.print(f"[red]Error: '{limit_input}' is not a valid number[/]")
                Prompt.ask("\nPress Enter to continue")
            elif choice == 6:
                # Closed PnL - requires time range (max 7 days)
                window = get_time_window(max_days=7, default="7d")
                if window is BACK:
                    continue
                symbol = get_input("Symbol (blank for all)", "")
                if symbol is BACK:
                    continue
                limit_input = get_input("Limit (1-50)", "50")
                if limit_input is BACK:
                    continue
                try:
                    limit = int(limit_input)
                    result = get_closed_pnl_tool(
                        window=window,
                        symbol=symbol if symbol else None,
                        limit=limit,
                    )
                    print_result(result)
                except ValueError:
                    console.print(f"[red]Error: '{limit_input}' is not a valid number[/]")
                Prompt.ask("\nPress Enter to continue")
            elif choice == 7:
                # Transaction Log - requires time range (max 7 days)
                window = get_time_window(max_days=7, default="7d")
                if window is BACK:
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
                    result = get_transaction_log_tool(
                        window=window,
                        category=category if category else None,
                        currency=currency if currency else None,
                        log_type=log_type if log_type else None,
                        limit=limit,
                    )
                    print_result(result)
                except ValueError:
                    console.print(f"[red]Error: '{limit_input}' is not a valid number[/]")
                Prompt.ask("\nPress Enter to continue")
            elif choice == 8:
                currency = get_input("Currency (blank for all)", "")
                result = get_collateral_info_tool(currency=currency if currency else None)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 9:
                coin = get_input("Coin (e.g., BTC, ETH, USDT)")
                action = get_input("Enable as collateral? (yes/no)", "yes")
                enabled = action.lower() in ("yes", "y", "true", "1")
                result = set_collateral_coin_tool(coin, enabled)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 10:
                # Borrow History - requires time range (max 30 days)
                window = get_time_window(max_days=30, default="30d")
                if window is BACK:
                    continue
                currency = get_input("Currency (blank for all)", "")
                if currency is BACK:
                    continue
                limit_input = get_input("Limit (1-50)", "50")
                if limit_input is BACK:
                    continue
                try:
                    limit = int(limit_input)
                    result = get_borrow_history_tool(
                        window=window,
                        currency=currency if currency else None,
                        limit=limit,
                    )
                    print_result(result)
                except ValueError:
                    console.print(f"[red]Error: '{limit_input}' is not a valid number[/]")
                Prompt.ask("\nPress Enter to continue")
            elif choice == 11:
                base_coin = get_input("Base coin (BTC/ETH, blank for all)", "")
                result = get_coin_greeks_tool(base_coin=base_coin if base_coin else None)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 12:
                console.print("\n[bold]Margin modes:[/]")
                console.print("  1. Regular Margin (default)")
                console.print("  2. Portfolio Margin")
                mode_choice = get_input("Select mode", "1")
                portfolio_margin = mode_choice == "2"
                result = set_account_margin_mode_tool(portfolio_margin)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 13:
                coin = get_input("Coin (e.g., USDT, BTC)")
                result = get_transferable_amount_tool(coin)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 14:
                break
    
    # ==================== POSITIONS MENU ====================
    
    def positions_menu(self):
        """Positions management menu."""
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
                result = list_open_positions_tool()
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 2:
                symbol = get_input("Symbol (e.g. BTCUSDT, SOLUSDT, ETHUSDT)")
                if symbol is BACK:
                    continue
                result = get_position_detail_tool(symbol)
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
                    result = set_stop_loss_tool(symbol, price)
                    print_result(result)
                except ValueError:
                    console.print(f"[red]Error: '{price_input}' is not a valid number[/]")
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
                    result = set_take_profit_tool(symbol, price)
                    print_result(result)
                except ValueError:
                    console.print(f"[red]Error: '{price_input}' is not a valid number[/]")
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
                    result = set_position_tpsl_tool(
                        symbol,
                        take_profit=float(tp) if tp else None,
                        stop_loss=float(sl) if sl else None
                    )
                    print_result(result)
                except ValueError as e:
                    console.print(f"[red]Error: Invalid price format - {e}[/]")
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
                        console.print("[red]Error: Percentage must be between 0 and 100[/]")
                    else:
                        result = partial_close_position_tool(
                            symbol, 
                            percent, 
                            price=float(price) if price else None
                        )
                        print_result(result)
                except ValueError:
                    console.print(f"[red]Error: '{percent_input}' is not a valid number[/]")
                Prompt.ask("\nPress Enter to continue")
            elif choice == 7:
                symbol = get_input("Symbol")
                if symbol is BACK:
                    continue
                if Confirm.ask(f"[yellow]Close entire {symbol} position?[/]"):
                    result = close_position_tool(symbol)
                    print_result(result)
                else:
                    console.print("[yellow]Cancelled.[/]")
                Prompt.ask("\nPress Enter to continue")
            elif choice == 8:
                if Confirm.ask("[bold red]Are you sure you want to CLOSE ALL POSITIONS?[/]"):
                    result = panic_close_all_tool(reason="User requested close all")
                    print_result(result)
                else:
                    console.print("[yellow]Cancelled.[/]")
                Prompt.ask("\nPress Enter to continue")
            elif choice == 9:
                symbol = get_input("Symbol (e.g. BTCUSDT, SOLUSDT)")
                if symbol is BACK:
                    continue
                console.print(f"\n[dim]Fetching risk limit tiers for {symbol}...[/]")
                result = get_risk_limits_tool(symbol)
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
                console.print(f"\n[dim]Fetching available risk limit tiers...[/]")
                # First show available risk limits
                limits_result = get_risk_limits_tool(symbol)
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
                        console.print(f"\n[dim]Setting risk limit ID {risk_id} for {symbol}...[/]")
                        result = set_risk_limit_tool(symbol, risk_id)
                        print_result(result)
                    except ValueError:
                        console.print(f"[red]Error: '{risk_id_input}' is not a valid integer. Please enter a number.[/]")
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
                result = set_tp_sl_mode_tool(symbol, full_mode)
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
                        console.print("[red]Error: Leverage must be between 1 and 100[/]")
                        lev_value = None
                    result = switch_margin_mode_tool(symbol, isolated, lev_value)
                    print_result(result)
                except ValueError:
                    console.print(f"[red]Error: '{leverage_input}' is not a valid integer[/]")
                Prompt.ask("\nPress Enter to continue")
            elif choice == 13:
                symbol = get_input("Symbol (e.g. BTCUSDT)")
                if symbol is BACK:
                    continue
                console.print("\n[yellow]Auto-add margin automatically adds margin when position is at risk[/]")
                enabled = Confirm.ask("Enable auto-add margin?", default=False)
                result = set_auto_add_margin_tool(symbol, enabled)
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
                    result = modify_position_margin_tool(symbol, margin)
                    print_result(result)
                except ValueError:
                    console.print(f"[red]Error: '{margin_input}' is not a valid number[/]")
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
                result = switch_position_mode_tool(hedge_mode)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 16:
                break
    
    # ==================== ORDERS MENU ====================
    
    def orders_menu(self):
        """Orders menu."""
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
                self.market_orders_menu()
            elif choice == 2:
                self.limit_orders_menu()
            elif choice == 3:
                self.stop_orders_menu()
            elif choice == 4:
                self.manage_orders_menu()
            elif choice == 5:
                symbol = get_input("Symbol")
                leverage = int(get_input("Leverage", "3"))
                result = set_leverage_tool(symbol, leverage)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 6:
                symbol = get_input("Symbol (blank for all)", "")
                result = cancel_all_orders_tool(symbol=symbol if symbol else None)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 7:
                break

    def market_orders_menu(self):
        """Market orders menu."""
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
                    result = market_buy_tool(symbol, usd)
                    print_result(result)
                else:
                    console.print("[yellow]Cancelled[/]")
                Prompt.ask("\nPress Enter to continue")
            elif choice == 2:
                symbol = get_input("Symbol")
                usd = float(get_input("USD Amount"))
                print_order_preview("Market Sell", symbol, "Sell", usd)
                if Confirm.ask("Confirm execution?"):
                    result = market_sell_tool(symbol, usd)
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
                    result = market_buy_with_tpsl_tool(
                        symbol, usd,
                        take_profit=float(tp) if tp else None,
                        stop_loss=float(sl) if sl else None
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
                    result = market_sell_with_tpsl_tool(
                        symbol, usd,
                        take_profit=float(tp) if tp else None,
                        stop_loss=float(sl) if sl else None
                    )
                    print_result(result)
                else:
                    console.print("[yellow]Cancelled[/]")
                Prompt.ask("\nPress Enter to continue")
            elif choice == 5:
                break

    def limit_orders_menu(self):
        """Limit orders menu."""
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
                    result = limit_buy_tool(symbol, usd, price, time_in_force=tif, reduce_only=reduce_only)
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
                    result = limit_sell_tool(symbol, usd, price, time_in_force=tif, reduce_only=reduce_only)
                    print_result(result)
                else:
                    console.print("[yellow]Cancelled[/]")
                Prompt.ask("\nPress Enter to continue")
            elif choice == 3:
                break

    def stop_orders_menu(self):
        """Stop orders menu."""
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
                    result = stop_market_buy_tool(symbol, usd, trigger, trigger_direction=direction)
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
                    result = stop_market_sell_tool(symbol, usd, trigger, trigger_direction=direction)
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
                    result = stop_limit_buy_tool(symbol, usd, trigger, limit, trigger_direction=direction)
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
                    result = stop_limit_sell_tool(symbol, usd, trigger, limit, trigger_direction=direction)
                    print_result(result)
                else:
                    console.print("[yellow]Cancelled[/]")
                Prompt.ask("\nPress Enter to continue")
            elif choice == 5:
                break

    def manage_orders_menu(self):
        """Manage existing orders."""
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
                result = get_open_orders_tool(symbol=symbol if symbol else None)
                
                if result.success and result.data and result.data.get("orders"):
                    orders = result.data["orders"]
                    table = Table(title=f"Open Orders ({len(orders)})", show_header=True, header_style="bold magenta")
                    table.add_column("ID")
                    table.add_column("Symbol")
                    table.add_column("Side")
                    table.add_column("Type")
                    table.add_column("Qty")
                    table.add_column("Price")
                    table.add_column("Status")
                    
                    for o in orders:
                        side_style = "green" if o['side'].lower() == "buy" else "red"
                        table.add_row(
                            o['order_id'][-6:], # Short ID
                            o['symbol'],
                            f"[{side_style}]{o['side']}[/]",
                            o['order_type'],
                            str(o['qty']),
                            str(o['price']),
                            o['status']
                        )
                    console.print(table)
                else:
                    print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 2:
                symbol = get_input("Symbol")
                order_id = get_input("Order ID (or Order Link ID)")
                
                console.print("[dim]Leave blank to keep current value[/]")
                new_qty = get_input("New Qty", "")
                new_price = get_input("New Price", "")
                new_tp = get_input("New TP", "")
                new_sl = get_input("New SL", "")
                
                result = amend_order_tool(
                    symbol, 
                    order_id=order_id,
                    qty=float(new_qty) if new_qty else None,
                    price=float(new_price) if new_price else None,
                    take_profit=float(new_tp) if new_tp else None,
                    stop_loss=float(new_sl) if new_sl else None
                )
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 3:
                symbol = get_input("Symbol")
                order_id = get_input("Order ID (or Order Link ID)")
                result = cancel_order_tool(symbol, order_id=order_id)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 4:
                break
    
    # ==================== MARKET DATA MENU ====================
    
    def market_data_menu(self):
        """Market data menu."""
        while True:
            clear_screen()
            print_header()
            
            # Show market data API source info
            config = get_config()
            data_env = config.bybit.get_api_environment_summary()["data"]
            key_status = "✓ Authenticated" if data_env["key_configured"] else "⚠ Public Only"
            api_status_line = Text()
            api_status_line.append("Market Data Source: ", style="dim")
            api_status_line.append(f"{data_env['mode']} ", style="bold green")
            api_status_line.append(f"({data_env['base_url']})", style="dim")
            api_status_line.append(" │ ", style="dim")
            if data_env["key_configured"]:
                api_status_line.append(key_status, style="green")
            else:
                api_status_line.append(key_status, style="yellow")
            console.print(Panel(api_status_line, border_style="dim blue"))
            
            menu = Table(show_header=False, box=None, padding=(0, 2))
            menu.add_column("Key", style="cyan bold", justify="right", width=4)
            menu.add_column("Action", style="bold", width=30)
            menu.add_column("Description", style="dim", width=45)
            
            menu.add_row("1", "Get Price", "Current market price for a symbol")
            menu.add_row("2", "Get OHLCV", "Candlestick data (Open, High, Low, Close, Volume)")
            menu.add_row("3", "Get Funding Rate", "Current funding rate for perpetual futures")
            menu.add_row("4", "Get Open Interest", "Current open interest for a symbol")
            menu.add_row("5", "Get Orderbook", "Order book depth (bids/asks)")
            menu.add_row("6", "Get Instruments", "Symbol info (contract size, tick size, etc.)")
            menu.add_row("7", "Run Market Data Tests", "Test all market data endpoints")
            menu.add_row("8", "Back to Main Menu", "Return to main menu")
            
            console.print(Panel(Align.center(menu), title="[bold]MARKET DATA[/]", border_style="blue"))
            
            choice = get_choice(valid_range=range(1, 9))
            
            if choice == 1:
                symbol = get_input("Symbol")
                result = get_price_tool(symbol)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 2:
                symbol = get_input("Symbol")
                interval = get_input("Interval", "15")
                limit = int(get_input("Limit", "100"))
                result = get_ohlcv_tool(symbol, interval, limit)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 3:
                symbol = get_input("Symbol")
                result = get_funding_rate_tool(symbol)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 4:
                symbol = get_input("Symbol")
                result = get_open_interest_tool(symbol)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 5:
                symbol = get_input("Symbol")
                limit = int(get_input("Depth Limit", "25"))
                result = get_orderbook_tool(symbol, limit)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 6:
                result = get_instruments_tool()
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 7:
                symbol = get_input("Symbol")
                result = run_market_data_tests_tool(symbol)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 8:
                break
    
    # ==================== DATA MENU ====================
    
    def data_menu(self):
        """Historical data builder menu (DuckDB-only)."""
        while True:
            clear_screen()
            print_header()
            
            # Show data API source info
            config = get_config()
            data_env = config.bybit.get_api_environment_summary()["data"]
            key_status = "✓ Configured" if data_env["key_configured"] else "✗ Public Only"
            api_status_line = Text()
            api_status_line.append("Data Source: ", style="dim")
            api_status_line.append(f"{data_env['mode']} ", style="bold green")
            api_status_line.append(f"({data_env['base_url']})", style="dim")
            api_status_line.append(" │ API Key: ", style="dim")
            if data_env["key_configured"]:
                api_status_line.append(key_status, style="green")
            else:
                api_status_line.append(key_status, style="yellow")
            console.print(Panel(api_status_line, border_style="dim blue"))
            
            menu = Table(show_header=False, box=None, padding=(0, 2))
            menu.add_column("Key", style="cyan bold", justify="right", width=4)
            menu.add_column("Action", style="bold", width=35)
            menu.add_column("Description", style="dim", width=40)
            
            menu.add_row("", "[dim]--- Database Info ---[/]", "")
            menu.add_row("1", "Database Stats", "Database size, symbol count, total candles")
            menu.add_row("2", "List Cached Symbols", "All symbols with data in database")
            menu.add_row("3", "Symbol Aggregate Status", "Per-symbol totals (candles, gaps, timeframes)")
            menu.add_row("4", "Symbol Summary (Overview)", "High-level summary per symbol")
            menu.add_row("5", "Symbol Timeframe Ranges", "Detailed per-symbol/timeframe date ranges")
            menu.add_row("", "", "")
            menu.add_row("", "[dim]--- Build Data ---[/]", "")
            menu.add_row("6", "[bold green]Build Full History[/]", "[green]Sync OHLCV + Funding + OI for symbols[/]")
            menu.add_row("7", "[bold cyan]Sync Forward to Now[/]", "[cyan]Fetch only new candles (no backfill)[/]")
            menu.add_row("8", "[bold cyan]Sync Forward + Fill Gaps[/]", "[cyan]Sync new + backfill gaps in history[/]")
            menu.add_row("", "", "")
            menu.add_row("", "[dim]--- Sync Data (Individual) ---[/]", "")
            menu.add_row("9", "Sync OHLCV by Period", "Sync candles for a time period (1D, 1M, etc.)")
            menu.add_row("10", "Sync OHLCV by Date Range", "Sync candles for specific date range")
            menu.add_row("11", "Sync Funding Rates", "Sync funding rate history")
            menu.add_row("12", "Sync Open Interest", "Sync open interest history")
            menu.add_row("", "", "")
            menu.add_row("", "[dim]--- Maintenance ---[/]", "")
            menu.add_row("13", "Fill Gaps", "Detect and fill missing candles in data")
            menu.add_row("14", "Heal Data", "Comprehensive data integrity check & repair")
            menu.add_row("15", "[red]Delete Symbol[/]", "[red]Delete all data for a symbol[/]")
            menu.add_row("16", "Cleanup Empty Symbols", "Remove symbols with no data")
            menu.add_row("17", "Vacuum Database", "Reclaim disk space after deletions")
            menu.add_row("", "", "")
            menu.add_row("18", "Back to Main Menu", "Return to main menu")
            
            console.print(Panel(Align.center(menu), title="[bold]DATA BUILDER (DuckDB)[/]", border_style="blue"))
            
            choice = get_choice(valid_range=range(1, 19))
            
            if choice == 1:
                # Database Stats
                result = get_database_stats_tool()
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            
            elif choice == 2:
                # List Cached Symbols
                result = list_cached_symbols_tool()
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            
            elif choice == 3:
                # Symbol Aggregate Status
                symbol = get_input("Symbol (blank for all)", "")
                result = get_symbol_status_tool(symbol if symbol else None)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            
            elif choice == 4:
                # Symbol Summary (Overview)
                result = get_symbol_summary_tool()
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            
            elif choice == 5:
                # Symbol Timeframe Ranges (Detailed)
                symbol = get_input("Symbol (blank for all)", "")
                result = get_symbol_timeframe_ranges_tool(symbol if symbol else None)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            
            elif choice == 6:
                # Build Full History (OHLCV + Funding + OI)
                symbol = get_input("Symbol(s) to build (comma-separated)")
                symbols = [s.strip().upper() for s in symbol.split(",") if s.strip()]
                if not symbols:
                    console.print("[red]No symbols provided.[/]")
                    Prompt.ask("\nPress Enter to continue")
                    continue
                
                period = get_input("Period (1D, 1W, 1M, 3M, 6M, 1Y)", "1M")
                timeframes_input = get_input("OHLCV Timeframes (comma-separated, blank for all)", "")
                timeframes = [t.strip() for t in timeframes_input.split(",")] if timeframes_input else None
                oi_interval = get_input("Open Interest Interval (5min, 15min, 30min, 1h, 4h, 1d)", "1h")
                
                console.print(f"\n[dim]Building full history for {symbols} ({period})...[/]")
                console.print(f"[dim]This will sync OHLCV candles, funding rates, and open interest.[/]")
                with console.status("[bold green]Building historical data...[/]"):
                    result = build_symbol_history_tool(
                        symbols,
                        period=period,
                        timeframes=timeframes,
                        oi_interval=oi_interval,
                    )
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            
            elif choice == 7:
                # Sync Forward to Now (new candles only)
                symbol = get_input("Symbol(s) to sync forward (comma-separated)")
                symbols = [s.strip().upper() for s in symbol.split(",") if s.strip()]
                if not symbols:
                    console.print("[red]No symbols provided.[/]")
                    Prompt.ask("\nPress Enter to continue")
                    continue
                
                timeframes_input = get_input("Timeframes (comma-separated, blank for all)", "")
                timeframes = [t.strip() for t in timeframes_input.split(",")] if timeframes_input else None
                
                console.print(f"\n[dim]Syncing {symbols} forward to now (new candles only)...[/]")
                with console.status("[bold green]Syncing forward...[/]"):
                    result = sync_to_now_tool(symbols, timeframes=timeframes)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            
            elif choice == 8:
                # Sync Forward + Fill Gaps (complete)
                symbol = get_input("Symbol(s) to sync and heal (comma-separated)")
                symbols = [s.strip().upper() for s in symbol.split(",") if s.strip()]
                if not symbols:
                    console.print("[red]No symbols provided.[/]")
                    Prompt.ask("\nPress Enter to continue")
                    continue
                
                timeframes_input = get_input("Timeframes (comma-separated, blank for all)", "")
                timeframes = [t.strip() for t in timeframes_input.split(",")] if timeframes_input else None
                
                console.print(f"\n[dim]Syncing {symbols} forward and filling gaps...[/]")
                console.print(f"[dim]This will fetch new candles AND repair any gaps in history.[/]")
                with console.status("[bold green]Syncing and healing data...[/]"):
                    result = sync_to_now_and_fill_gaps_tool(symbols, timeframes=timeframes)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            
            elif choice == 9:
                # Sync OHLCV by Period
                symbol = get_input("Symbol (comma-separated for multiple)")
                symbols = [s.strip().upper() for s in symbol.split(",")]
                period = get_input("Period (1D, 1W, 1M, 3M, 6M, 1Y)", "1M")
                timeframes_input = get_input("Timeframes (comma-separated, blank for all)", "")
                timeframes = [t.strip() for t in timeframes_input.split(",")] if timeframes_input else None
                
                console.print(f"\n[dim]Syncing {symbols} for {period}...[/]")
                with console.status("[bold green]Syncing data...[/]"):
                    result = sync_symbols_tool(symbols, period=period, timeframes=timeframes)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            
            elif choice == 10:
                # Sync OHLCV by Date Range
                symbol = get_input("Symbol (comma-separated for multiple)")
                symbols = [s.strip().upper() for s in symbol.split(",")]
                start_str = get_input("Start Date (YYYY-MM-DD)")
                end_str = get_input("End Date (YYYY-MM-DD)", datetime.now().strftime("%Y-%m-%d"))
                timeframes_input = get_input("Timeframes (comma-separated, blank for all)", "")
                timeframes = [t.strip() for t in timeframes_input.split(",")] if timeframes_input else None
                
                try:
                    start_dt = datetime.strptime(start_str, "%Y-%m-%d")
                    end_dt = datetime.strptime(end_str, "%Y-%m-%d")
                except ValueError:
                    console.print("[red]Invalid date format. Use YYYY-MM-DD.[/]")
                    Prompt.ask("\nPress Enter to continue")
                    continue
                
                console.print(f"\n[dim]Syncing {symbols} from {start_str} to {end_str}...[/]")
                with console.status("[bold green]Syncing data...[/]"):
                    result = sync_range_tool(symbols, start=start_dt, end=end_dt, timeframes=timeframes)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            
            elif choice == 11:
                # Sync Funding Rates
                symbol = get_input("Symbol (comma-separated for multiple)")
                symbols = [s.strip().upper() for s in symbol.split(",")]
                period = get_input("Period (1M, 3M, 6M, 1Y)", "3M")
                
                console.print(f"\n[dim]Syncing funding rates for {symbols}...[/]")
                with console.status("[bold green]Syncing funding rates...[/]"):
                    result = sync_funding_tool(symbols, period=period)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            
            elif choice == 12:
                # Sync Open Interest
                symbol = get_input("Symbol (comma-separated for multiple)")
                symbols = [s.strip().upper() for s in symbol.split(",")]
                period = get_input("Period (1D, 1W, 1M, 3M)", "1M")
                interval = get_input("Interval (5min, 15min, 30min, 1h, 4h, 1d)", "1h")
                
                console.print(f"\n[dim]Syncing open interest for {symbols}...[/]")
                with console.status("[bold green]Syncing open interest...[/]"):
                    result = sync_open_interest_tool(symbols, period=period, interval=interval)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            
            elif choice == 13:
                # Fill Gaps
                symbol = get_input("Symbol (blank for all)", "")
                timeframe = get_input("Timeframe (blank for all)", "")
                
                console.print(f"\n[dim]Scanning and filling gaps...[/]")
                result = fill_gaps_tool(
                    symbol=symbol if symbol else None,
                    timeframe=timeframe if timeframe else None,
                )
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            
            elif choice == 14:
                # Heal Data
                symbol = get_input("Symbol (blank for all)", "")
                
                console.print(f"\n[dim]Running data integrity check and repair...[/]")
                result = heal_data_tool(symbol=symbol if symbol else None)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            
            elif choice == 15:
                # Delete Symbol
                symbol = get_input("Symbol to DELETE")
                if symbol:
                    if Confirm.ask(f"[bold red]Delete ALL data for {symbol.upper()}?[/]"):
                        result = delete_symbol_tool(symbol)
                        print_result(result)
                    else:
                        console.print("[yellow]Cancelled.[/]")
                else:
                    console.print("[yellow]No symbol provided.[/]")
                Prompt.ask("\nPress Enter to continue")
            
            elif choice == 16:
                # Cleanup Empty Symbols
                console.print(f"\n[dim]Cleaning up invalid/empty symbols...[/]")
                result = cleanup_empty_symbols_tool()
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            
            elif choice == 17:
                # Vacuum Database
                console.print(f"\n[dim]Vacuuming database...[/]")
                result = vacuum_database_tool()
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            
            elif choice == 18:
                break
    
    # ==================== CONNECTION TEST ====================
    
    def connection_test(self):
        """Run connection test."""
        clear_screen()
        print_header()
        
        console.print(Panel("Running Connectivity Diagnostic...", title="[bold]CONNECTION TEST[/]", border_style="blue"))
        
        # Show API environment first
        console.print("\n[bold]API Environment:[/]")
        api_result = get_api_environment_tool()
        if api_result.success:
            data = api_result.data
            trading = data["trading"]
            data_api = data["data"]
            ws = data["websocket"]
            
            env_table = Table(show_header=False, box=None)
            env_table.add_column("Type", style="dim")
            env_table.add_column("Mode", style="bold")
            env_table.add_column("URL", style="dim")
            env_table.add_column("Key", style="dim")
            
            trading_style = "green" if trading["is_demo"] else "red"
            env_table.add_row(
                "Trading REST",
                f"[{trading_style}]{trading['mode']}[/]",
                trading["base_url"],
                "✓" if trading["key_configured"] else "✗"
            )
            env_table.add_row(
                "Data REST",
                f"[green]{data_api['mode']}[/]",
                data_api["base_url"],
                "✓" if data_api["key_configured"] else "⚠ public"
            )
            env_table.add_row(
                "WebSocket",
                f"[{trading_style}]{ws['mode']}[/]",
                ws["public_url"],
                "✓ enabled" if ws.get("enabled") else "○ disabled"
            )
            console.print(env_table)
        
        console.print("\n[dim]Testing connection to Bybit...[/]")
        with console.status("[bold green]Connecting to Bybit API...[/]"):
            result = test_connection_tool()
        print_result(result)
        
        console.print("\n[dim]Checking server time offset...[/]")
        result = get_server_time_offset_tool()
        print_result(result)
        
        console.print("\n[dim]Checking rate limit status...[/]")
        result = get_rate_limit_status_tool()
        print_result(result)
        
        # Symbol passed as parameter from user input
        symbol = get_input("\nTest ticker for symbol")
        result = get_ticker_tool(symbol)
        print_result(result)
        
        Prompt.ask("\nPress Enter to continue")
    
    # ==================== HEALTH CHECK ====================
    
    def health_check(self):
        """Run full health check."""
        clear_screen()
        print_header()
        
        console.print(Panel("System Health Diagnostic", title="[bold]HEALTH CHECK[/]", border_style="blue"))
        
        # Show API environment first
        console.print("\n[bold]API Environment:[/]")
        api_result = get_api_environment_tool()
        if api_result.success:
            data = api_result.data
            trading = data["trading"]
            data_api = data["data"]
            ws = data["websocket"]
            safety = data["safety"]
            
            env_table = Table(show_header=False, box=None)
            env_table.add_column("Type", style="dim")
            env_table.add_column("Mode", style="bold")
            env_table.add_column("URL", style="dim")
            env_table.add_column("Key", style="dim")
            
            trading_style = "green" if trading["is_demo"] else "red"
            env_table.add_row(
                "Trading REST",
                f"[{trading_style}]{trading['mode']}[/]",
                trading["base_url"],
                "✓" if trading["key_configured"] else "✗"
            )
            env_table.add_row(
                "Data REST",
                f"[green]{data_api['mode']}[/]",
                data_api["base_url"],
                "✓" if data_api["key_configured"] else "⚠ public"
            )
            env_table.add_row(
                "WebSocket",
                f"[{trading_style}]{ws['mode']}[/]",
                ws["public_url"],
                "✓ enabled" if ws.get("enabled") else "○ disabled"
            )
            console.print(env_table)
            
            # Safety check
            if safety["mode_consistent"]:
                console.print("[green]✓ Mode consistency: OK[/]")
            else:
                console.print("[yellow]⚠ Mode consistency warnings:[/]")
                for msg in safety["messages"]:
                    console.print(f"  [dim]{msg}[/]")
        
        symbol = get_input("\nSymbol to test")
        
        console.print("\n[dim]Running exchange health check...[/]")
        with console.status("[bold green]Running diagnostics...[/]"):
            result = exchange_health_check_tool(symbol)
        print_result(result)
        
        console.print("\n[dim]Checking WebSocket status...[/]")
        result = get_websocket_status_tool()
        print_result(result)
        
        Prompt.ask("\nPress Enter to continue")
    
    # ==================== PANIC ====================
    
    def panic_menu(self):
        """Panic close all positions."""
        clear_screen()
        print_header()
        
        panel = Panel(
            Align.center(
                "[bold red]⚠️  PANIC MODE ⚠️[/]\n\n"
                "This will:\n"
                "  1. Cancel ALL open orders\n"
                "  2. Close ALL positions at market"
            ),
            border_style="red",
            padding=(1, 2)
        )
        console.print(panel)
        
        confirm = get_input("Type 'PANIC' to confirm", "")
        
        if confirm == "PANIC":
            console.print(f"\n[bold yellow]Executing panic...[/]")
            with console.status("[bold red]CLOSING EVERYTHING...[/]"):
                result = panic_close_all_tool(reason="Manual panic from CLI")
            print_result(result)
        else:
            console.print(f"\n[bold green]Panic cancelled.[/]")
        
        Prompt.ask("\nPress Enter to continue")


def select_trading_environment() -> bool:
    """
    Interactive trading environment selector at CLI startup.
    
    Allows user to choose between DEMO (safe) and LIVE (real money) trading
    for this session only. Does NOT modify api_keys.env.
    
    Returns:
        True if environment was successfully configured, False to exit.
    """
    config = get_config()
    
    # Get current config from file
    file_is_demo = config.bybit.use_demo
    file_trading_mode = config.trading.mode
    
    clear_screen()
    
    # Title panel
    title = Panel(
        Align.center(
            "[bold cyan]TRADE - Trading Environment Selector[/]\n"
            "[dim]Choose your trading environment for this session[/]"
        ),
        border_style="cyan",
        padding=(1, 2)
    )
    console.print(title)
    
    # Show current file-based config
    file_env = "DEMO" if file_is_demo else "LIVE"
    file_style = "green" if file_is_demo else "red"
    console.print(f"\n[dim]Default from config file:[/] [{file_style}]{file_env}[/] (TRADING_MODE={file_trading_mode})")
    console.print()
    
    # Environment options table
    options = Table(show_header=False, box=None, padding=(0, 2))
    options.add_column("Key", style="cyan bold", justify="center", width=6)
    options.add_column("Environment", style="bold", width=25)
    options.add_column("Description", style="dim", width=45)
    
    options.add_row(
        "1",
        "[bold green]DEMO (Paper)[/]",
        "Demo account (fake funds) - api-demo.bybit.com"
    )
    options.add_row(
        "2",
        "[bold red]LIVE (Real)[/]",
        "Live account (real funds) - api.bybit.com"
    )
    options.add_row(
        "",
        "",
        ""
    )
    options.add_row(
        "q",
        "[dim]Quit[/]",
        "Exit without starting"
    )
    
    console.print(Panel(options, title="[bold]Select Environment[/]", border_style="blue"))
    
    # Default suggestion based on config file
    default_choice = "1" if file_is_demo else "2"
    choice = Prompt.ask(
        f"\n[cyan]Enter choice[/]",
        choices=["1", "2", "q", "Q"],
        default=default_choice
    )
    
    if choice.lower() == "q":
        console.print("\n[yellow]Exiting...[/]")
        return False
    
    if choice == "1":
        # DEMO/PAPER mode - demo account with fake funds
        config.bybit.use_demo = True
        config.trading.mode = "paper"
        console.print("\n[bold green]✓ DEMO (Paper) mode selected[/]")
        console.print("[dim]Trading on Bybit demo account (fake funds, real API orders)[/]")
        console.print("[dim]REST: api-demo.bybit.com | WebSocket: stream-demo.bybit.com[/]")
        console.print("[dim]Data operations use LIVE API for accuracy[/]")
        Prompt.ask("\n[dim]Press Enter to continue[/]")
        return True
    
    elif choice == "2":
        # LIVE mode - requires double confirmation
        return _confirm_live_mode(config)
    
    return False


def _confirm_live_mode(config) -> bool:
    """
    Double confirmation for LIVE trading mode.
    
    Returns:
        True if user confirmed LIVE mode, False to fall back to DEMO.
    """
    clear_screen()
    
    # Warning panel
    warning = Panel(
        Align.center(
            "[bold red]⚠️  WARNING: LIVE TRADING MODE ⚠️[/]\n\n"
            "[red]You are about to trade with REAL MONEY![/]\n\n"
            "This session will:\n"
            "  • Use [bold]api.bybit.com[/] (LIVE API)\n"
            "  • Execute orders with [bold red]REAL FUNDS[/]\n"
            "  • Affect your [bold red]REAL ACCOUNT BALANCE[/]"
        ),
        border_style="red",
        title="[bold red]LIVE MODE[/]",
        padding=(1, 4)
    )
    console.print(warning)
    
    # Show risk caps
    risk_table = Table(show_header=False, box=None, padding=(0, 2))
    risk_table.add_column("Setting", style="dim", width=25)
    risk_table.add_column("Value", style="bold yellow", width=20)
    
    risk_table.add_row("Max Position Size:", f"${config.risk.max_position_size_usd:,.2f}")
    risk_table.add_row("Max Daily Loss:", f"${config.risk.max_daily_loss_usd:,.2f}")
    risk_table.add_row("Max Leverage:", f"{config.risk.max_leverage}x")
    risk_table.add_row("Min Balance Protection:", f"${config.risk.min_balance_usd:,.2f}")
    
    console.print(Panel(risk_table, title="[bold yellow]Current Risk Limits[/]", border_style="yellow"))
    
    # First confirmation
    console.print("\n[bold]First confirmation:[/]")
    confirm1 = Confirm.ask("[yellow]Do you understand that this will use REAL MONEY?[/]", default=False)
    
    if not confirm1:
        console.print("\n[green]✓ Cancelled - using DEMO (Paper) mode[/]")
        config.bybit.use_demo = True
        config.trading.mode = "paper"
        Prompt.ask("\n[dim]Press Enter to continue in DEMO mode[/]")
        return True
    
    # Second confirmation - type LIVE
    console.print("\n[bold]Second confirmation:[/]")
    console.print("[dim]Type 'LIVE' (exactly) to confirm, or anything else to cancel:[/]")
    confirm2 = Prompt.ask("[red]Confirm LIVE mode[/]")
    
    if confirm2 == "LIVE":
        config.bybit.use_demo = False
        config.trading.mode = "real"
        console.print("\n[bold red]⚠️  LIVE (Real) MODE ACTIVATED[/]")
        console.print("[red]Trading on Bybit live account (REAL FUNDS, real API orders)[/]")
        console.print("[dim]REST: api.bybit.com | WebSocket: stream.bybit.com[/]")
        Prompt.ask("\n[dim]Press Enter to continue in LIVE mode[/]")
        return True
    else:
        console.print("\n[green]✓ LIVE mode cancelled - using DEMO (Paper) mode[/]")
        config.bybit.use_demo = True
        config.trading.mode = "paper"
        Prompt.ask("\n[dim]Press Enter to continue in DEMO mode[/]")
        return True


def main():
    """Main entry point."""
    # Setup logging
    setup_logger()
    
    # ===== TRADING ENVIRONMENT SELECTOR (before Application init) =====
    # This modifies config.bybit.use_demo and config.trading.mode in memory
    # for this session only, without changing api_keys.env
    if not select_trading_environment():
        # User chose to quit
        return
    
    # Initialize application lifecycle (uses modified config)
    app = get_application()
    
    if not app.initialize():
        console.print(f"\n[bold red]Application initialization failed![/]")
        console.print(f"[red]Error: {app.get_status().error}[/]")
        return
    
    # Start application (including WebSocket if enabled)
    if not app.start():
        console.print(f"\n[bold yellow]Warning: Application start had issues[/]")
        console.print(f"[yellow]Continuing with REST API fallback...[/]")
    
    # Show WebSocket status
    status = app.get_status()
    if status.websocket_connected:
        console.print(f"[green]WebSocket connected[/] [dim](public: {status.websocket_public}, private: {status.websocket_private})[/]")
    elif app.config.websocket.enable_websocket and app.config.websocket.auto_start:
        console.print(f"[yellow]WebSocket not connected - using REST API[/]")
    
    # Create and run CLI
    cli = TradeCLI()
    
    try:
        cli.main_menu()
    except KeyboardInterrupt:
        console.print(f"\n[yellow]Interrupted. Shutting down...[/]")
    except Exception as e:
        console.print(f"\n[bold red]Error: {e}[/]")
        raise
    finally:
        # Graceful shutdown
        app.stop()
        console.print(f"[dim]Goodbye![/]")


if __name__ == "__main__":
    main()
