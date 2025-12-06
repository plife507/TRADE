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
    sync_symbols_tool,
    sync_range_tool,
    fill_gaps_tool,
    vacuum_database_tool,
)


# Global Console
console = Console()


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
        
    panel = Panel(
        Align.center(grid),
        title=title,
        border_style="cyan",
        subtitle=f"[dim]v1.0[/dim]"
    )
    console.print(panel)
    if warning_panel:
        console.print(Align.center(warning_panel))


def get_input(prompt: str, default: str = "") -> str:
    """Get user input with optional default."""
    return Prompt.ask(f"[cyan]{prompt}[/]", default=default if default else None, show_default=bool(default))


def get_choice(valid_range: range = None) -> int:
    """Get numeric choice from user."""
    while True:
        choice = IntPrompt.ask("\n[bold cyan]Enter choice[/]")
        if valid_range and choice not in valid_range:
            console.print(f"[red]Invalid choice. Please enter a number between {valid_range.start} and {valid_range.stop-1}.[/]")
            continue
        return choice


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
            menu.add_column("Key", style="cyan bold", justify="right")
            menu.add_column("Action")
            
            menu.add_row("1", "Account & Balance")
            menu.add_row("2", "Positions")
            menu.add_row("3", "Orders")
            menu.add_row("4", "Market Data")
            menu.add_row("5", "Historical Data")
            menu.add_row("6", "Connection Test")
            menu.add_row("7", "Health Check")
            menu.add_row("8", "[bold red]PANIC: Close All & Stop[/]")
            menu.add_row("9", "Exit")
            
            console.print(Panel(Align.center(menu), title="[bold]MAIN MENU[/]", border_style="blue"))
            
            choice = get_choice(valid_range=range(1, 10))
            
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
            menu.add_column("Key", style="cyan bold", justify="right")
            menu.add_column("Action")
            
            menu.add_row("1", "View Balance")
            menu.add_row("2", "View Exposure")
            menu.add_row("3", "Account Info")
            menu.add_row("4", "Portfolio Snapshot")
            menu.add_row("5", "Order History")
            menu.add_row("6", "Closed PnL")
            menu.add_row("", "")
            menu.add_row("", "[dim]--- Unified Account ---[/]")
            menu.add_row("7", "Transaction Log")
            menu.add_row("8", "Collateral Info")
            menu.add_row("9", "Set Collateral Coin")
            menu.add_row("10", "Borrow History")
            menu.add_row("11", "Coin Greeks (Options)")
            menu.add_row("12", "Set Margin Mode")
            menu.add_row("13", "Transferable Amount")
            menu.add_row("14", "Back to Main Menu")
            
            console.print(Panel(Align.center(menu), title="[bold]ACCOUNT & BALANCE[/]", border_style="blue"))
            
            choice = get_choice(valid_range=range(1, 15))
            
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
                symbol = get_input("Symbol (blank for all)", "")
                limit = int(get_input("Limit", "20"))
                result = get_order_history_tool(symbol=symbol if symbol else None, limit=limit)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 6:
                symbol = get_input("Symbol (blank for all)", "")
                limit = int(get_input("Limit", "20"))
                result = get_closed_pnl_tool(symbol=symbol if symbol else None, limit=limit)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 7:
                category = get_input("Category (spot/linear/option, blank for all)", "")
                currency = get_input("Currency (blank for all)", "")
                log_type = get_input("Type (TRADE/SETTLEMENT/TRANSFER_IN/etc, blank for all)", "")
                limit = int(get_input("Limit", "20"))
                result = get_transaction_log_tool(
                    category=category if category else None,
                    currency=currency if currency else None,
                    log_type=log_type if log_type else None,
                    limit=limit,
                )
                print_result(result)
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
                currency = get_input("Currency (blank for all)", "")
                limit = int(get_input("Limit", "20"))
                result = get_borrow_history_tool(currency=currency if currency else None, limit=limit)
                print_result(result)
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
            
            menu = Table(show_header=False, box=None, padding=(0, 2))
            menu.add_column("Key", style="cyan bold", justify="right")
            menu.add_column("Action")
            
            menu.add_row("1", "List Open Positions")
            menu.add_row("2", "Position Detail")
            menu.add_row("3", "Set Stop Loss")
            menu.add_row("4", "Set Take Profit")
            menu.add_row("5", "Set TP/SL Together")
            menu.add_row("6", "Partial Close")
            menu.add_row("7", "[red]Close Position[/]")
            menu.add_row("8", "[bold red]Close All Positions[/]")
            menu.add_row("", "")
            menu.add_row("", "[dim]--- Position Config ---[/]")
            menu.add_row("9", "View Risk Limits")
            menu.add_row("10", "Set Risk Limit")
            menu.add_row("11", "Set TP/SL Mode")
            menu.add_row("12", "Switch Margin Mode")
            menu.add_row("13", "Auto-Add Margin")
            menu.add_row("14", "Modify Position Margin")
            menu.add_row("15", "Switch Position Mode")
            menu.add_row("16", "Back to Main Menu")
            
            console.print(Panel(Align.center(menu), title="[bold]POSITIONS[/]", border_style="blue"))
            
            choice = get_choice(valid_range=range(1, 17))
            
            if choice == 1:
                result = list_open_positions_tool()
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 2:
                symbol = get_input("Symbol")
                result = get_position_detail_tool(symbol)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 3:
                symbol = get_input("Symbol")
                price = float(get_input("Stop Loss Price"))
                result = set_stop_loss_tool(symbol, price)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 4:
                symbol = get_input("Symbol")
                price = float(get_input("Take Profit Price"))
                result = set_take_profit_tool(symbol, price)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 5:
                symbol = get_input("Symbol")
                tp = get_input("Take Profit Price (blank to skip)", "")
                sl = get_input("Stop Loss Price (blank to skip)", "")
                result = set_position_tpsl_tool(
                    symbol,
                    take_profit=float(tp) if tp else None,
                    stop_loss=float(sl) if sl else None
                )
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 6:
                symbol = get_input("Symbol")
                percent = float(get_input("Close Percentage (0-100)", "50"))
                price = get_input("Limit Price (blank for Market)", "")
                result = partial_close_position_tool(
                    symbol, 
                    percent, 
                    price=float(price) if price else None
                )
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 7:
                symbol = get_input("Symbol")
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
                symbol = get_input("Symbol")
                result = get_risk_limits_tool(symbol)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 10:
                symbol = get_input("Symbol")
                # First show available risk limits
                limits_result = get_risk_limits_tool(symbol)
                if limits_result.success and limits_result.data:
                    console.print("\n[bold cyan]Available Risk Limits:[/]")
                    rl_table = Table(show_header=True, header_style="bold magenta")
                    rl_table.add_column("ID")
                    rl_table.add_column("Max Position Value")
                    
                    for rl in limits_result.data.get("risk_limits", [])[:10]:
                        rl_table.add_row(
                            str(rl.get('id')), 
                            f"${float(rl.get('riskLimitValue', 0)):,.0f}"
                        )
                    console.print(rl_table)
                    
                risk_id = int(get_input("Risk Limit ID"))
                result = set_risk_limit_tool(symbol, risk_id)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 11:
                symbol = get_input("Symbol")
                console.print("\n[bold]TP/SL Modes:[/]")
                console.print("  1. Full - TP/SL applies to entire position")
                console.print("  2. Partial - TP/SL applies to specified qty")
                mode_choice = get_input("Select mode", "1")
                full_mode = mode_choice == "1"
                result = set_tp_sl_mode_tool(symbol, full_mode)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 12:
                symbol = get_input("Symbol")
                console.print("\n[bold]Margin Modes:[/]")
                console.print("  1. Cross margin")
                console.print("  2. Isolated margin")
                mode_choice = get_input("Select mode", "1")
                isolated = mode_choice == "2"
                leverage = get_input("Leverage (blank to keep current)", "")
                lev_value = int(leverage) if leverage else None
                result = switch_margin_mode_tool(symbol, isolated, lev_value)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 13:
                symbol = get_input("Symbol")
                enabled = Confirm.ask("Enable auto-add margin?")
                result = set_auto_add_margin_tool(symbol, enabled)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 14:
                symbol = get_input("Symbol")
                margin = float(get_input("Margin amount (positive to add, negative to reduce)"))
                result = modify_position_margin_tool(symbol, margin)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 15:
                console.print("\n[bold]Position Modes:[/]")
                console.print("  1. One-way (can only hold Buy OR Sell)")
                console.print("  2. Hedge (can hold both Buy AND Sell)")
                mode_choice = get_input("Select mode", "1")
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
            
            menu = Table(show_header=False, box=None, padding=(0, 2))
            menu.add_column("Key", style="cyan bold", justify="right")
            menu.add_column("Action")
            
            menu.add_row("1", "Market Orders (Buy/Sell/TP/SL)")
            menu.add_row("2", "Limit Orders")
            menu.add_row("3", "Stop Orders (Conditional)")
            menu.add_row("4", "Manage Orders (List/Amend/Cancel)")
            menu.add_row("5", "Set Leverage")
            menu.add_row("6", "Cancel All Orders")
            menu.add_row("7", "Back to Main Menu")
            
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
            menu.add_column("Key", style="cyan bold", justify="right")
            menu.add_column("Action")
            
            menu.add_row("1", "Market Buy")
            menu.add_row("2", "Market Sell")
            menu.add_row("3", "Market Buy with TP/SL")
            menu.add_row("4", "Market Sell with TP/SL")
            menu.add_row("5", "Back to Orders Menu")
            
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
            menu.add_column("Key", style="cyan bold", justify="right")
            menu.add_column("Action")
            
            menu.add_row("1", "Limit Buy")
            menu.add_row("2", "Limit Sell")
            menu.add_row("3", "Back to Orders Menu")
            
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
            menu.add_column("Key", style="cyan bold", justify="right")
            menu.add_column("Action")
            
            menu.add_row("1", "Stop Market Buy")
            menu.add_row("2", "Stop Market Sell")
            menu.add_row("3", "Stop Limit Buy")
            menu.add_row("4", "Stop Limit Sell")
            menu.add_row("5", "Back to Orders Menu")
            
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
            menu.add_column("Key", style="cyan bold", justify="right")
            menu.add_column("Action")
            
            menu.add_row("1", "List Open Orders")
            menu.add_row("2", "Amend Order")
            menu.add_row("3", "Cancel Order")
            menu.add_row("4", "Back to Orders Menu")
            
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
            
            menu = Table(show_header=False, box=None, padding=(0, 2))
            menu.add_column("Key", style="cyan bold", justify="right")
            menu.add_column("Action")
            
            menu.add_row("1", "Get Price")
            menu.add_row("2", "Get OHLCV")
            menu.add_row("3", "Get Funding Rate")
            menu.add_row("4", "Get Open Interest")
            menu.add_row("5", "Get Orderbook")
            menu.add_row("6", "Get Instruments")
            menu.add_row("7", "Run Market Data Tests")
            menu.add_row("8", "Back to Main Menu")
            
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
        """Historical data menu."""
        while True:
            clear_screen()
            print_header()
            
            menu = Table(show_header=False, box=None, padding=(0, 2))
            menu.add_column("Key", style="cyan bold", justify="right")
            menu.add_column("Action")
            
            menu.add_row("1", "Database Stats")
            menu.add_row("2", "List Cached Symbols")
            menu.add_row("3", "Symbol Status")
            menu.add_row("4", "Sync Symbol Data")
            menu.add_row("5", "Sync Date Range")
            menu.add_row("6", "Fill Gaps")
            menu.add_row("7", "Vacuum Database")
            menu.add_row("8", "Back to Main Menu")
            
            console.print(Panel(Align.center(menu), title="[bold]HISTORICAL DATA (DuckDB)[/]", border_style="blue"))
            
            choice = get_choice(valid_range=range(1, 9))
            
            if choice == 1:
                result = get_database_stats_tool()
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 2:
                result = list_cached_symbols_tool()
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 3:
                symbol = get_input("Symbol")
                result = get_symbol_status_tool(symbol)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 4:
                symbol = get_input("Symbol")
                timeframe = get_input("Timeframe", "15")
                days = int(get_input("Days to sync", "30"))
                result = sync_symbols_tool([symbol], timeframe, days)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 5:
                symbol = get_input("Symbol")
                timeframe = get_input("Timeframe", "15")
                start = get_input("Start Date (YYYY-MM-DD)")
                end = get_input("End Date (YYYY-MM-DD)", datetime.now().strftime("%Y-%m-%d"))
                result = sync_range_tool(symbol, timeframe, start, end)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 6:
                symbol = get_input("Symbol")
                timeframe = get_input("Timeframe", "15")
                result = fill_gaps_tool(symbol, timeframe)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 7:
                result = vacuum_database_tool()
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 8:
                break
    
    # ==================== CONNECTION TEST ====================
    
    def connection_test(self):
        """Run connection test."""
        clear_screen()
        print_header()
        
        console.print(Panel("Running Connectivity Diagnostic...", title="[bold]CONNECTION TEST[/]", border_style="blue"))
        
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
        
        symbol = get_input("Symbol to test")
        
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


def main():
    """Main entry point."""
    # Setup logging
    setup_logger()
    
    # Initialize application lifecycle
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
