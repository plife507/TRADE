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

Non-interactive smoke test modes:
  python trade_cli.py --smoke data            # Data builder smoke test only
  python trade_cli.py --smoke full            # Full CLI smoke test (data + trading + diagnostics)
  python trade_cli.py --smoke data_extensive  # Extensive data test (clean DB, gaps, fill, sync)
  python trade_cli.py --smoke backtest        # Backtest engine smoke test
  python trade_cli.py --smoke backtest --fresh-db  # Backtest with fresh DB
"""

import argparse
import os
import sys

# Rich imports (only what's still used directly in this file)
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.align import Align
from rich.text import Text

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config.config import get_config
from src.core.application import Application, get_application
from src.utils.logger import setup_logger, get_logger
from src.utils.cli_display import format_action_status, format_action_complete, get_action_label, format_data_result
from src.cli.menus import (
    data_menu as data_menu_handler,
    market_data_menu as market_data_menu_handler,
    orders_menu as orders_menu_handler,
    market_orders_menu as market_orders_menu_handler,
    limit_orders_menu as limit_orders_menu_handler,
    stop_orders_menu as stop_orders_menu_handler,
    manage_orders_menu as manage_orders_menu_handler,
    positions_menu as positions_menu_handler,
    account_menu as account_menu_handler,
    backtest_menu as backtest_menu_handler,
)
from src.cli.styles import CLIStyles, CLIColors, CLIIcons, BillArtWrapper, BillArtColors
# Import shared CLI utilities (canonical implementations)
from src.cli.utils import (
    console,
    BackCommand,
    BACK,
    is_exit_command,
    clear_screen,
    print_header,
    get_input,
    get_choice,
    get_float_input,
    get_int_input,
    TimeRangeSelection,
    select_time_range_cli,
    print_error_below_menu,
    run_tool_action,
    run_long_action,
    print_result,
    print_data_result,
    print_order_preview,
)
from src.cli.smoke_tests import (
    run_smoke_suite,
    run_data_builder_smoke,
    run_full_cli_smoke,
    run_extensive_data_smoke,
    run_comprehensive_order_smoke,
)
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
    # OHLCV query tools
    get_ohlcv_history_tool,
    # Sync to now tools
    sync_to_now_tool,
    sync_to_now_and_fill_gaps_tool,
    # Composite build tools
    build_symbol_history_tool,
)


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
        """Display main menu with $100 bill art styling."""
        while True:
            clear_screen()
            print_header()
            
            # Print decorative menu top border
            BillArtWrapper.print_menu_top()
            
            menu = CLIStyles.create_menu_table()
            
            # Use themed colors for menu items
            gold = BillArtColors.GOLD_BRIGHT if CLIStyles.use_art_wrapper else CLIColors.NEON_YELLOW
            green = BillArtColors.GREEN_BRIGHT if CLIStyles.use_art_wrapper else CLIColors.NEON_GREEN
            
            menu.add_row("1", f"{CLIIcons.WALLET} Account & Balance", "View balance, exposure, portfolio, transaction history")
            menu.add_row("2", f"{CLIIcons.CANDLE} Positions", "List, manage, close positions, set TP/SL, trailing stops")
            menu.add_row("3", f"{CLIIcons.TRADE} Orders", "Place market/limit/stop orders, manage open orders")
            menu.add_row("4", f"{CLIIcons.CHART_UP} Market Data", "Get prices, OHLCV, funding rates, orderbook, instruments")
            menu.add_row("5", f"{CLIIcons.MINING} Data Builder", "Build & manage historical data (DuckDB)")
            menu.add_row("6", f"{CLIIcons.TARGET} Backtest Engine", "Run strategy backtests, manage systems")
            menu.add_row("7", f"{CLIIcons.NETWORK} Connection Test", "Test API connectivity and rate limits")
            menu.add_row("8", f"{CLIIcons.SETTINGS} Health Check", "Comprehensive system health diagnostic")
            menu.add_row("9", f"[bold {gold}]{CLIIcons.PANIC} PANIC: Close All & Stop[/]", f"[{gold}]Emergency: Close all positions & cancel orders[/]")
            menu.add_row("10", f"{CLIIcons.QUIT} Exit", "Exit the CLI")
            
            # Use art-themed menu panel
            console.print(CLIStyles.get_menu_panel(menu, "MAIN MENU", is_main=True))
            
            # Print decorative menu bottom border
            BillArtWrapper.print_menu_bottom()
            
            # Themed tip text
            tip_color = BillArtColors.GREEN_MONEY if CLIStyles.use_art_wrapper else CLIColors.DIM_TEXT
            console.print(f"[{tip_color}]💡 Tip: Type 'back' or 'b' at any prompt to cancel and return to previous menu[/]")
            
            choice = get_choice(valid_range=range(1, 11))
            
            # Handle back command from main menu (same as exit)
            if choice is BACK:
                console.print(f"\n[yellow]Goodbye![/]")
                break
            
            try:
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
                    self.backtest_menu()
                elif choice == 7:
                    self.connection_test()
                elif choice == 8:
                    self.health_check()
                elif choice == 9:
                    self.panic_menu()
                elif choice == 10:
                    console.print(f"\n[yellow]Goodbye![/]")
                    break
            except KeyboardInterrupt:
                console.print("\n[yellow]Operation cancelled. Returning to main menu...[/]")
                Prompt.ask("\nPress Enter to continue")
            except Exception as e:
                print_error_below_menu(
                    f"An error occurred: {e}",
                    "The operation failed but you can try again or select another option."
                )
                Prompt.ask("\nPress Enter to continue")
    
    # ==================== ACCOUNT MENU ====================
    
    def account_menu(self):
        """Account menu. Delegates to src.cli.menus.account_menu."""
        account_menu_handler(self)
    
    # ==================== POSITIONS MENU ====================
    
    def positions_menu(self):
        """Positions menu. Delegates to src.cli.menus.positions_menu."""
        positions_menu_handler(self)
    
    # ==================== ORDERS MENU ====================
    
    def orders_menu(self):
        """Orders menu. Delegates to src.cli.menus.orders_menu."""
        orders_menu_handler(self)

    def market_orders_menu(self):
        """Market orders menu. Delegates to src.cli.menus.orders_menu."""
        market_orders_menu_handler(self)

    def limit_orders_menu(self):
        """Limit orders menu. Delegates to src.cli.menus.orders_menu."""
        limit_orders_menu_handler(self)

    def stop_orders_menu(self):
        """Stop orders menu. Delegates to src.cli.menus.orders_menu."""
        stop_orders_menu_handler(self)

    def manage_orders_menu(self):
        """Manage orders menu. Delegates to src.cli.menus.orders_menu."""
        manage_orders_menu_handler(self)
    
    # ==================== MARKET DATA MENU ====================
    
    def market_data_menu(self):
        """Market data menu. Delegates to src.cli.menus.market_data_menu."""
        market_data_menu_handler(self)
    
    # ==================== DATA MENU ====================
    
    def data_menu(self):
        """Historical data builder menu (DuckDB-only). Delegates to src.cli.menus.data_menu."""
        data_menu_handler(self)
    
    # ==================== BACKTEST MENU ====================
    
    def backtest_menu(self):
        """Backtest engine menu. Delegates to src.cli.menus.backtest_menu."""
        backtest_menu_handler(self)

    # ==================== CONNECTION TEST ====================
    
    def connection_test(self):
        """Run connection test."""
        clear_screen()
        print_header()
        
        try:
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
            
            result = run_tool_action("diagnostics.connection", test_connection_tool)
            print_data_result("diagnostics.connection", result)
            
            result = run_tool_action("diagnostics.server_time", get_server_time_offset_tool)
            print_data_result("diagnostics.server_time", result)
            
            result = run_tool_action("diagnostics.rate_limits", get_rate_limit_status_tool)
            print_data_result("diagnostics.rate_limits", result)
            
            # Symbol passed as parameter from user input
            symbol = get_input("\nTest ticker for symbol")
            if symbol is not BACK:
                result = run_tool_action("diagnostics.ticker", get_ticker_tool, symbol=symbol)
                print_data_result("diagnostics.ticker", result)
        except KeyboardInterrupt:
            console.print("\n[yellow]Test cancelled.[/]")
        except Exception as e:
            print_error_below_menu(f"Connection test failed: {e}", "Please check your network and API configuration.")
        
        Prompt.ask("\nPress Enter to continue")
    
    # ==================== HEALTH CHECK ====================
    
    def health_check(self):
        """Run full health check."""
        clear_screen()
        print_header()
        
        try:
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
            if symbol is not BACK:
                result = run_tool_action("diagnostics.health_check", exchange_health_check_tool, symbol=symbol)
                print_data_result("diagnostics.health_check", result)
                
                result = run_tool_action("diagnostics.websocket", get_websocket_status_tool)
                print_data_result("diagnostics.websocket", result)
        except KeyboardInterrupt:
            console.print("\n[yellow]Health check cancelled.[/]")
        except Exception as e:
            print_error_below_menu(f"Health check failed: {e}", "Please check your API configuration and network.")
        
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
            result = run_tool_action("panic.close_all", panic_close_all_tool, reason="Manual panic from CLI")
            print_data_result("panic.close_all", result)
        else:
            console.print(f"\n[bold green]Panic cancelled.[/]")
        
        Prompt.ask("\nPress Enter to continue")


# =============================================================================
# SMOKE TEST SUITE - Now imported from src.cli.smoke_tests
# =============================================================================
# See: src/cli/smoke_tests.py for run_smoke_suite, run_data_builder_smoke, run_full_cli_smoke


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
    
    # Print the big startup art with TRADE + BYBIT logos
    BillArtWrapper.print_startup_art()
    
    # Show current file-based config
    file_env = "DEMO" if file_is_demo else "LIVE"
    file_style = BillArtColors.GREEN_BRIGHT if file_is_demo else BillArtColors.GOLD_BRIGHT
    console.print(f"[{BillArtColors.GREEN_MONEY}]Default from config file:[/] [{file_style}]{file_env}[/] [{BillArtColors.GOLD_DARK}](TRADING_MODE={file_trading_mode})[/]")
    console.print()
    
    # Environment options table
    options = CLIStyles.create_menu_table()
    
    options.add_row(
        "1",
        f"[bold {BillArtColors.GREEN_BRIGHT}]💵 DEMO (Paper)[/]",
        f"[{BillArtColors.GREEN_MONEY}]Demo account (fake funds) - api-demo.bybit.com[/]"
    )
    options.add_row(
        "2",
        f"[bold {BillArtColors.GOLD_BRIGHT}]💰 LIVE (Real)[/]",
        f"[{BillArtColors.GOLD_DARK}]Live account (real funds) - api.bybit.com[/]"
    )
    options.add_row(
        "",
        "",
        ""
    )
    options.add_row(
        "q",
        f"[{BillArtColors.GREEN_MONEY}]Quit[/]",
        f"[{BillArtColors.GOLD_DARK}]Exit without starting[/]"
    )
    
    # Use art-styled menu panel
    console.print(CLIStyles.get_menu_panel(options, "SELECT ENVIRONMENT", is_main=True))
    
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
    
    # Print mini logo at top
    BillArtWrapper.print_mini_logo()
    console.print()
    
    # Warning panel with gold/money theme
    warning = Panel(
        Align.center(
            f"[bold {BillArtColors.GOLD_BRIGHT}]⚠️  WARNING: LIVE TRADING MODE ⚠️[/]\n\n"
            f"[{BillArtColors.GOLD_BRIGHT}]You are about to trade with REAL MONEY![/]\n\n"
            f"This session will:\n"
            f"  • Use [bold]api.bybit.com[/] (LIVE API)\n"
            f"  • Execute orders with [bold {BillArtColors.GOLD_BRIGHT}]REAL FUNDS[/]\n"
            f"  • Affect your [bold {BillArtColors.GOLD_BRIGHT}]REAL ACCOUNT BALANCE[/]"
        ),
        border_style=BillArtColors.GOLD_BRIGHT,
        title=f"[bold {BillArtColors.GOLD_BRIGHT}]💰 LIVE MODE 💰[/]",
        padding=(1, 4)
    )
    console.print(warning)
    
    # Show risk caps
    risk_table = Table(show_header=False, box=None, padding=(0, 2))
    risk_table.add_column("Setting", style=BillArtColors.GREEN_MONEY, width=25)
    risk_table.add_column("Value", style=f"bold {BillArtColors.GOLD_BRIGHT}", width=20)
    
    risk_table.add_row("Max Position Size:", f"${config.risk.max_position_size_usd:,.2f}")
    risk_table.add_row("Max Daily Loss:", f"${config.risk.max_daily_loss_usd:,.2f}")
    risk_table.add_row("Max Leverage:", f"{config.risk.max_leverage}x")
    risk_table.add_row("Min Balance Protection:", f"${config.risk.min_balance_usd:,.2f}")
    
    console.print(Panel(risk_table, title=f"[bold {BillArtColors.GOLD_BRIGHT}]💵 Current Risk Limits 💵[/]", border_style=BillArtColors.GOLD_DARK))
    
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


def parse_cli_args() -> argparse.Namespace:
    """
    Parse command-line arguments for trade_cli.
    
    Supports:
      --smoke data   Run data builder smoke test only
      --smoke full   Run full CLI smoke test (data + trading + diagnostics)
      
      backtest run   Run IdeaCard-based backtest (golden path)
      backtest preflight   Check data/config without running
      backtest data-fix    Fix data gaps/coverage
      backtest list        List available IdeaCards
    """
    parser = argparse.ArgumentParser(
        description="TRADE - Bybit Unified Trading Account CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python trade_cli.py                              # Interactive mode (default)
  python trade_cli.py --smoke data                 # Data builder smoke test
  python trade_cli.py --smoke full                 # Full CLI smoke test
  
  # IdeaCard-based backtest (golden path):
  python trade_cli.py backtest run --idea-card SOLUSDT_15m_ema_crossover
  python trade_cli.py backtest run --idea-card SOLUSDT_15m_ema_crossover --smoke
  python trade_cli.py backtest preflight --idea-card SOLUSDT_15m_ema_crossover
  python trade_cli.py backtest data-fix --idea-card SOLUSDT_15m_ema_crossover
  python trade_cli.py backtest list
        """
    )
    
    parser.add_argument(
        "--smoke",
        choices=["data", "full", "data_extensive", "orders", "live_check", "backtest"],
        default=None,
        help="Run non-interactive smoke test. 'data'/'full'/'data_extensive'/'orders'/'backtest' use DEMO. 'live_check' tests LIVE connectivity (opt-in, requires LIVE keys)."
    )
    
    parser.add_argument(
        "--fresh-db",
        action="store_true",
        default=False,
        help="For backtest smoke: wipe database before preparing data"
    )
    
    # Add subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # backtest subcommand with its own subcommands
    backtest_parser = subparsers.add_parser("backtest", help="IdeaCard-based backtest (golden path)")
    backtest_subparsers = backtest_parser.add_subparsers(dest="backtest_command", help="Backtest commands")
    
    # backtest run
    run_parser = backtest_subparsers.add_parser("run", help="Run an IdeaCard backtest")
    run_parser.add_argument("--idea-card", required=True, help="IdeaCard identifier (e.g., SOLUSDT_15m_ema_crossover)")
    run_parser.add_argument("--data-env", choices=["live", "demo"], default="live", help="Data environment (default: live)")
    run_parser.add_argument("--symbol", help="Override symbol (default: from IdeaCard)")
    run_parser.add_argument("--start", help="Window start (YYYY-MM-DD or YYYY-MM-DD HH:MM)")
    run_parser.add_argument("--end", help="Window end (YYYY-MM-DD or YYYY-MM-DD HH:MM)")
    run_parser.add_argument("--smoke", action="store_true", help="Smoke mode: fast wiring check with small window")
    run_parser.add_argument("--strict", action="store_true", default=True, help="Strict indicator access (default: True)")
    run_parser.add_argument("--no-strict", action="store_false", dest="strict", help="Disable strict indicator checks")
    run_parser.add_argument("--artifacts-dir", help="Override artifacts directory")
    run_parser.add_argument("--no-artifacts", action="store_true", help="Skip writing artifacts")
    run_parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")
    
    # backtest preflight
    preflight_parser = backtest_subparsers.add_parser("preflight", help="Run preflight check without executing")
    preflight_parser.add_argument("--idea-card", required=True, help="IdeaCard identifier")
    preflight_parser.add_argument("--data-env", choices=["live", "demo"], default="live", help="Data environment")
    preflight_parser.add_argument("--symbol", help="Override symbol")
    preflight_parser.add_argument("--start", help="Window start")
    preflight_parser.add_argument("--end", help="Window end")
    preflight_parser.add_argument("--fix-gaps", action="store_true", help="Auto-fix data gaps using existing tools")
    preflight_parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")
    
    # backtest indicators (NEW - indicator key discovery)
    indicators_parser = backtest_subparsers.add_parser("indicators", help="Discover indicator keys for an IdeaCard")
    indicators_parser.add_argument("--idea-card", required=True, help="IdeaCard identifier")
    indicators_parser.add_argument("--data-env", choices=["live", "demo"], default="live", help="Data environment")
    indicators_parser.add_argument("--symbol", help="Override symbol")
    indicators_parser.add_argument("--print-keys", action="store_true", default=True, help="Print all indicator keys")
    indicators_parser.add_argument("--compute", action="store_true", help="Actually compute indicators (requires --start/--end)")
    indicators_parser.add_argument("--start", help="Window start (for --compute)")
    indicators_parser.add_argument("--end", help="Window end (for --compute)")
    indicators_parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")
    
    # backtest data-fix
    datafix_parser = backtest_subparsers.add_parser("data-fix", help="Fix data for an IdeaCard")
    datafix_parser.add_argument("--idea-card", required=True, help="IdeaCard identifier")
    datafix_parser.add_argument("--data-env", choices=["live", "demo"], default="live", help="Data environment")
    datafix_parser.add_argument("--symbol", help="Override symbol")
    datafix_parser.add_argument("--start", help="Sync from this date")
    datafix_parser.add_argument("--sync-to-now", action="store_true", help="Sync data to current time")
    datafix_parser.add_argument("--fill-gaps", action="store_true", default=True, help="Fill gaps after sync")
    datafix_parser.add_argument("--heal", action="store_true", help="Run full heal after sync")
    datafix_parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")
    
    # backtest list
    list_parser = backtest_subparsers.add_parser("list", help="List available IdeaCards")
    list_parser.add_argument("--dir", dest="idea_cards_dir", help="Override IdeaCards directory")
    list_parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")
    
    # backtest idea-card-normalize (NEW - build-time validation)
    normalize_parser = backtest_subparsers.add_parser(
        "idea-card-normalize", 
        help="Validate and normalize an IdeaCard YAML (build-time)"
    )
    normalize_parser.add_argument("--idea-card", required=True, help="IdeaCard identifier")
    normalize_parser.add_argument("--dir", dest="idea_cards_dir", help="Override IdeaCards directory")
    normalize_parser.add_argument("--write", action="store_true", help="Write normalized YAML in-place")
    normalize_parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")
    
    # backtest audit-toolkit (NEW - indicator registry audit)
    audit_parser = backtest_subparsers.add_parser(
        "audit-toolkit",
        help="Audit indicator registry for consistency"
    )
    audit_parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")
    
    return parser.parse_args()


# =============================================================================
# BACKTEST SUBCOMMAND HANDLERS
# =============================================================================

def _parse_datetime(dt_str: str) -> "datetime":
    """Parse datetime string from CLI."""
    from datetime import datetime
    
    # Try various formats
    for fmt in ["%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"]:
        try:
            return datetime.strptime(dt_str, fmt)
        except ValueError:
            continue
    
    raise ValueError(f"Cannot parse datetime: '{dt_str}'. Use YYYY-MM-DD or YYYY-MM-DD HH:MM")


def handle_backtest_run(args) -> int:
    """Handle `backtest run` subcommand."""
    import json
    from pathlib import Path
    from src.tools.backtest_cli_wrapper import backtest_run_idea_card_tool
    
    # Parse dates
    start = _parse_datetime(args.start) if args.start else None
    end = _parse_datetime(args.end) if args.end else None
    artifacts_dir = Path(args.artifacts_dir) if args.artifacts_dir else None
    
    if not args.json_output:
        console.print(Panel(
            f"[bold cyan]BACKTEST RUN[/]\n"
            f"IdeaCard: {args.idea_card}\n"
            f"DataEnv: {args.data_env} | Smoke: {args.smoke} | Strict: {args.strict}",
            border_style="cyan"
        ))
    
    result = backtest_run_idea_card_tool(
        idea_card_id=args.idea_card,
        env=args.data_env,
        symbol=args.symbol,
        start=start,
        end=end,
        smoke=args.smoke,
        strict=args.strict,
        write_artifacts=not args.no_artifacts,
        artifacts_dir=artifacts_dir,
    )
    
    # JSON output mode
    if args.json_output:
        output = {
            "status": "pass" if result.success else "fail",
            "message": result.message if result.success else result.error,
            "data": result.data,
        }
        print(json.dumps(output, indent=2, default=str))
        return 0 if result.success else 1
    
    # Print diagnostics
    if result.data and "preflight" in result.data:
        preflight = result.data["preflight"]
        _print_preflight_diagnostics(preflight)
    
    if result.success:
        console.print(f"\n[bold green]OK {result.message}[/]")
        if result.data and "artifact_dir" in result.data:
            console.print(f"[dim]Artifacts: {result.data['artifact_dir']}[/]")
        return 0
    else:
        console.print(f"\n[bold red]FAIL {result.error}[/]")
        return 1


def handle_backtest_preflight(args) -> int:
    """Handle `backtest preflight` subcommand."""
    import json
    from src.tools.backtest_cli_wrapper import backtest_preflight_idea_card_tool, backtest_data_fix_tool
    
    # Parse dates
    start = _parse_datetime(args.start) if args.start else None
    end = _parse_datetime(args.end) if args.end else None
    
    if not args.json_output:
        console.print(Panel(
            f"[bold cyan]BACKTEST PREFLIGHT[/]\n"
            f"IdeaCard: {args.idea_card} | DataEnv: {args.data_env}",
            border_style="cyan"
        ))
    
    result = backtest_preflight_idea_card_tool(
        idea_card_id=args.idea_card,
        env=args.data_env,
        symbol=args.symbol,
        start=start,
        end=end,
    )
    
    # Auto-fix gaps if requested
    if args.fix_gaps and not result.success and result.data and result.data.get("coverage_issue"):
        if not args.json_output:
            console.print("\n[yellow]Attempting to fix data gaps...[/]")
        fix_result = backtest_data_fix_tool(
            idea_card_id=args.idea_card,
            env=args.data_env,
            symbol=args.symbol,
            sync_to_now=True,
            fill_gaps=True,
        )
        if fix_result.success:
            if not args.json_output:
                console.print("[green]Data fix completed, re-running preflight...[/]")
            # Re-run preflight
            result = backtest_preflight_idea_card_tool(
                idea_card_id=args.idea_card,
                env=args.data_env,
                symbol=args.symbol,
                start=start,
                end=end,
            )
    
    # JSON output mode
    if args.json_output:
        output = {
            "status": "pass" if result.success else "fail",
            "message": result.message if result.success else result.error,
            "checks": {
                "idea_card_valid": result.data.get("idea_card_valid") if result.data else None,
                "has_sufficient_coverage": result.data.get("has_sufficient_coverage") if result.data else None,
            },
            "data": result.data,
            "recommended_fix": result.data.get("coverage_issue") if result.data and not result.success else None,
        }
        print(json.dumps(output, indent=2, default=str))
        return 0 if result.success else 1
    
    # Print diagnostics
    if result.data:
        _print_preflight_diagnostics(result.data)
    
    if result.success:
        console.print(f"\n[bold green]OK {result.message}[/]")
        return 0
    else:
        console.print(f"\n[bold red]FAIL {result.error}[/]")
        return 1


def handle_backtest_indicators(args) -> int:
    """Handle `backtest indicators` subcommand."""
    import json
    from src.tools.backtest_cli_wrapper import backtest_indicators_tool
    
    # Parse dates
    start = _parse_datetime(args.start) if args.start else None
    end = _parse_datetime(args.end) if args.end else None
    
    if not args.json_output:
        console.print(Panel(
            f"[bold cyan]BACKTEST INDICATORS[/]\n"
            f"IdeaCard: {args.idea_card} | DataEnv: {args.data_env}",
            border_style="cyan"
        ))
    
    result = backtest_indicators_tool(
        idea_card_id=args.idea_card,
        data_env=args.data_env,
        symbol=args.symbol,
        start=start,
        end=end,
        compute_values=args.compute,
    )
    
    # JSON output mode
    if args.json_output:
        output = {
            "status": "pass" if result.success else "fail",
            "message": result.message if result.success else result.error,
            "data": result.data,
        }
        print(json.dumps(output, indent=2, default=str))
        return 0 if result.success else 1
    
    if result.success and result.data:
        data = result.data
        console.print(f"\n[bold]Indicator Key Discovery[/]")
        console.print(f"IdeaCard: {data.get('idea_card_id')}")
        console.print(f"Symbol: {data.get('symbol')}")
        console.print(f"Exec TF: {data.get('exec_tf')}")
        if data.get('htf'):
            console.print(f"HTF: {data.get('htf')}")
        if data.get('mtf'):
            console.print(f"MTF: {data.get('mtf')}")
        
        console.print(f"\n[bold]Declared Keys (from FeatureSpec output_key):[/]")
        for role, keys in data.get("declared_keys_by_role", {}).items():
            console.print(f"  {role}: {keys}")
        
        console.print(f"\n[bold]Expanded Keys (actual column names, including multi-output):[/]")
        for role, keys in data.get("expanded_keys_by_role", {}).items():
            console.print(f"  {role}: {keys}")
        
        if data.get("computed_info"):
            console.print(f"\n[bold]Computed Info:[/]")
            for role, info in data["computed_info"].items():
                if "error" in info:
                    console.print(f"  {role}: [red]{info['error']}[/]")
                else:
                    console.print(f"  {role} ({info.get('tf')}):")
                    console.print(f"    Data rows: {info.get('data_rows')}")
                    console.print(f"    First valid bar: {info.get('first_valid_bar')}")
                    console.print(f"    Computed columns: {info.get('computed_columns')}")
        
        console.print(f"\n[bold green]OK {result.message}[/]")
        return 0
    else:
        console.print(f"\n[bold red]FAIL {result.error}[/]")
        return 1


def handle_backtest_data_fix(args) -> int:
    """Handle `backtest data-fix` subcommand."""
    import json
    from src.tools.backtest_cli_wrapper import backtest_data_fix_tool
    
    # Parse dates
    start = _parse_datetime(args.start) if args.start else None
    
    if not args.json_output:
        console.print(Panel(
            f"[bold cyan]BACKTEST DATA FIX[/]\n"
            f"IdeaCard: {args.idea_card} | DataEnv: {args.data_env}\n"
            f"Sync to now: {args.sync_to_now} | Fill gaps: {args.fill_gaps} | Heal: {args.heal}",
            border_style="cyan"
        ))
    
    result = backtest_data_fix_tool(
        idea_card_id=args.idea_card,
        env=args.data_env,
        symbol=args.symbol,
        start=start,
        sync_to_now=args.sync_to_now,
        fill_gaps=args.fill_gaps,
        heal=args.heal,
    )
    
    # JSON output mode
    if args.json_output:
        output = {
            "status": "pass" if result.success else "fail",
            "message": result.message if result.success else result.error,
            "data": result.data,
        }
        print(json.dumps(output, indent=2, default=str))
        return 0 if result.success else 1
    
    if result.success:
        console.print(f"\n[bold green]OK {result.message}[/]")
        if result.data and "operations" in result.data:
            for op in result.data["operations"]:
                status = "OK" if op["success"] else "FAIL"
                console.print(f"  {status} {op['name']}: {op['message']}")
        return 0
    else:
        console.print(f"\n[bold red]FAIL {result.error}[/]")
        return 1


def handle_backtest_list(args) -> int:
    """Handle `backtest list` subcommand."""
    import json
    from pathlib import Path
    from src.tools.backtest_cli_wrapper import backtest_list_idea_cards_tool
    
    idea_cards_dir = Path(args.idea_cards_dir) if args.idea_cards_dir else None
    
    result = backtest_list_idea_cards_tool(idea_cards_dir=idea_cards_dir)
    
    # JSON output mode
    if args.json_output:
        output = {
            "status": "pass" if result.success else "fail",
            "message": result.message if result.success else result.error,
            "data": result.data,
        }
        print(json.dumps(output, indent=2, default=str))
        return 0 if result.success else 1
    
    if result.success:
        console.print(f"\n[bold cyan]Available IdeaCards:[/]")
        console.print(f"[dim]Directory: {result.data['directory']}[/]\n")
        
        for card_id in result.data["idea_cards"]:
            console.print(f"  - {card_id}")
        
        console.print(f"\n[dim]Total: {len(result.data['idea_cards'])} IdeaCards[/]")
        return 0
    else:
        console.print(f"\n[bold red]FAIL {result.error}[/]")
        return 1


def _print_preflight_diagnostics(diag: dict):
    """Print preflight diagnostics in a formatted way."""
    table = Table(title="Preflight Diagnostics", show_header=False, box=None)
    table.add_column("Key", style="dim", width=25)
    table.add_column("Value", style="bold")
    
    table.add_row("Environment", diag.get("env", "N/A"))
    table.add_row("Database", diag.get("db_path", "N/A"))
    table.add_row("OHLCV Table", diag.get("ohlcv_table", "N/A"))
    table.add_row("Symbol", diag.get("symbol", "N/A"))
    table.add_row("Exec TF", diag.get("exec_tf", "N/A"))
    
    if diag.get("htf"):
        table.add_row("HTF", diag["htf"])
    if diag.get("mtf"):
        table.add_row("MTF", diag["mtf"])
    
    console.print(table)
    
    # Window info
    console.print("\n[bold]Window:[/]")
    if diag.get("requested_start"):
        console.print(f"  Requested: {diag['requested_start']} -> {diag.get('requested_end', 'now')}")
    if diag.get("effective_start"):
        console.print(f"  Effective (with warmup): {diag['effective_start']} -> {diag.get('effective_end', 'now')}")
    console.print(f"  Warmup: {diag.get('warmup_bars', 0)} bars ({diag.get('warmup_span_minutes', 0)} minutes)")
    
    # Coverage
    console.print("\n[bold]DB Coverage:[/]")
    if diag.get("db_earliest") and diag.get("db_latest"):
        console.print(f"  Range: {diag['db_earliest']} -> {diag['db_latest']}")
        console.print(f"  Bars: {diag.get('db_bar_count', 0):,}")
    else:
        console.print("  [yellow]No data found[/]")
    
    coverage_ok = diag.get("has_sufficient_coverage", False)
    coverage_style = "green" if coverage_ok else "red"
    console.print(f"  Sufficient: [{coverage_style}]{'Yes' if coverage_ok else 'No'}[/]")
    
    if diag.get("coverage_issue"):
        console.print(f"  [yellow]Issue: {diag['coverage_issue']}[/]")
    
    # Indicator keys
    console.print("\n[bold]Declared Indicator Keys:[/]")
    exec_keys = diag.get("declared_keys_exec", [])
    htf_keys = diag.get("declared_keys_htf", [])
    mtf_keys = diag.get("declared_keys_mtf", [])
    
    console.print(f"  exec: {exec_keys or '(none)'}")
    if htf_keys:
        console.print(f"  htf: {htf_keys}")
    if mtf_keys:
        console.print(f"  mtf: {mtf_keys}")
    
    # Validation
    if diag.get("validation_errors"):
        console.print("\n[bold red]Validation Errors:[/]")
        for err in diag["validation_errors"]:
            console.print(f"  [red]• {err}[/]")


def handle_backtest_normalize(args) -> int:
    """Handle `backtest idea-card-normalize` subcommand."""
    import json
    from pathlib import Path
    from src.tools.backtest_cli_wrapper import backtest_idea_card_normalize_tool
    
    idea_cards_dir = Path(args.idea_cards_dir) if args.idea_cards_dir else None
    
    if not args.json_output:
        console.print(Panel(
            f"[bold cyan]IDEACARD NORMALIZE[/]\n"
            f"IdeaCard: {args.idea_card} | Write: {args.write}",
            border_style="cyan"
        ))
    
    result = backtest_idea_card_normalize_tool(
        idea_card_id=args.idea_card,
        idea_cards_dir=idea_cards_dir,
        write_in_place=args.write,
    )
    
    # JSON output mode
    if args.json_output:
        output = {
            "status": "pass" if result.success else "fail",
            "message": result.message if result.success else result.error,
            "data": result.data,
        }
        print(json.dumps(output, indent=2, default=str))
        return 0 if result.success else 1
    
    if result.success:
        console.print(f"\n[bold green]OK {result.message}[/]")
        if result.data:
            if result.data.get("written"):
                console.print(f"[dim]Written to: {result.data.get('yaml_path')}[/]")
            if result.data.get("warnings"):
                for w in result.data["warnings"]:
                    console.print(f"[yellow]⚠ {w}[/]")
        return 0
    else:
        console.print(f"\n[bold red]FAIL {result.error}[/]")
        if result.data and result.data.get("error_details"):
            console.print(result.data["error_details"])
        return 1


def handle_backtest_audit_toolkit(args) -> int:
    """Handle `backtest audit-toolkit` subcommand."""
    import json
    from src.tools.backtest_cli_wrapper import backtest_audit_toolkit_tool
    
    if not args.json_output:
        console.print(Panel(
            "[bold cyan]INDICATOR TOOLKIT AUDIT[/]\n"
            "Checking indicator registry consistency...",
            border_style="cyan"
        ))
    
    result = backtest_audit_toolkit_tool()
    
    # JSON output mode
    if args.json_output:
        output = {
            "status": "pass" if result.success else "fail",
            "message": result.message if result.success else result.error,
            "data": result.data,
        }
        print(json.dumps(output, indent=2, default=str))
        return 0 if result.success else 1
    
    if result.success:
        console.print(f"\n[bold green]OK {result.message}[/]")
        if result.data:
            console.print(f"[dim]Supported indicators: {len(result.data.get('supported_indicators', []))}[/]")
            console.print(f"[dim]Single-output: {result.data.get('single_output_count', 0)}[/]")
            console.print(f"[dim]Multi-output: {result.data.get('multi_output_count', 0)}[/]")
        return 0
    else:
        console.print(f"\n[bold red]FAIL {result.error}[/]")
        if result.data and result.data.get("issues"):
            console.print("\n[bold]Issues Found:[/]")
            for issue in result.data["issues"]:
                console.print(f"  [red]• [{issue['type']}] {issue['indicator']}: {issue['message']}[/]")
        return 1


def main():
    """Main entry point."""
    # Parse CLI arguments FIRST (before any config or logging)
    args = parse_cli_args()
    
    # Setup logging
    setup_logger()
    
    # ===== BACKTEST SUBCOMMANDS =====
    # Handle `backtest run/preflight/data-fix/list` subcommands
    if args.command == "backtest":
        config = get_config()
        # Force demo for data env (backtest uses data API, not trading)
        # But keep data env as specified
        
        if args.backtest_command == "run":
            sys.exit(handle_backtest_run(args))
        elif args.backtest_command == "preflight":
            sys.exit(handle_backtest_preflight(args))
        elif args.backtest_command == "indicators":
            sys.exit(handle_backtest_indicators(args))
        elif args.backtest_command == "data-fix":
            sys.exit(handle_backtest_data_fix(args))
        elif args.backtest_command == "list":
            sys.exit(handle_backtest_list(args))
        elif args.backtest_command == "idea-card-normalize":
            sys.exit(handle_backtest_normalize(args))
        elif args.backtest_command == "audit-toolkit":
            sys.exit(handle_backtest_audit_toolkit(args))
        else:
            console.print("[yellow]Usage: trade_cli.py backtest {run|preflight|indicators|data-fix|list|idea-card-normalize|audit-toolkit} --help[/]")
            sys.exit(1)
    
    # ===== SMOKE TEST MODE =====
    # If --smoke is specified, run non-interactive smoke tests
    if args.smoke:
        config = get_config()
        
        # Special case: live_check uses LIVE credentials (opt-in, dangerous)
        if args.smoke == "live_check":
            console.print(Panel(
                "[bold red]⚠️  LIVE CHECK SMOKE TEST ⚠️[/]\n"
                "[red]This test uses LIVE API credentials (REAL MONEY account)[/]\n"
                "[dim]Testing connectivity, balance, and limited order placement[/]",
                border_style="red"
            ))
            # Don't force DEMO - use configured mode (should be LIVE for this test)
            # If BYBIT_USE_DEMO=false in env, this uses LIVE
        else:
            # SAFETY: Force DEMO mode for all other smoke tests
            config.bybit.use_demo = True
            config.trading.mode = "paper"
            
            console.print(Panel(
                f"[bold cyan]SMOKE TEST MODE: {args.smoke.upper()}[/]\n"
                "[dim]Forcing DEMO/PAPER mode for safety[/]",
                border_style="cyan"
            ))
        
        # Initialize application lifecycle
        app = get_application()
        
        if not app.initialize():
            console.print(f"\n[bold red]Application initialization failed![/]")
            print_error_below_menu(str(app.get_status().error))
            sys.exit(1)
        
        # Start application (including WebSocket if enabled)
        if not app.start():
            console.print(f"\n[bold yellow]Warning: Application start had issues[/]")
            console.print(f"[yellow]Continuing with REST API fallback...[/]")
        
        try:
            # Run the appropriate smoke suite
            if args.smoke == "data_extensive":
                # Extensive data test with clean database
                exit_code = run_extensive_data_smoke()
            elif args.smoke == "orders":
                # Comprehensive order type testing
                exit_code = run_comprehensive_order_smoke()
            elif args.smoke == "live_check":
                # LIVE connectivity and limited order test
                from src.cli.smoke_tests import run_live_check_smoke
                exit_code = run_live_check_smoke()
            elif args.smoke == "backtest":
                # Backtest engine smoke test
                from src.cli.smoke_tests import run_backtest_smoke
                exit_code = run_backtest_smoke(fresh_db=args.fresh_db)
            else:
                exit_code = run_smoke_suite(args.smoke, app, config)
            sys.exit(exit_code)
        except KeyboardInterrupt:
            console.print(f"\n[yellow]Smoke test interrupted.[/]")
            sys.exit(130)
        except Exception as e:
            console.print(f"\n[bold red]Smoke test failed with error:[/] {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        finally:
            app.stop()
            console.print(f"[dim]Smoke test complete.[/]")
    
    # ===== INTERACTIVE MODE (default) =====
    # This modifies config.bybit.use_demo and config.trading.mode in memory
    # for this session only, without changing api_keys.env
    if not select_trading_environment():
        # User chose to quit
        return
    
    # Initialize application lifecycle (uses modified config)
    app = get_application()
    
    if not app.initialize():
        console.print(f"\n[bold red]Application initialization failed![/]")
        print_error_below_menu(str(app.get_status().error))
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
        print_error_below_menu(str(e))
        raise
    finally:
        # Graceful shutdown
        app.stop()
        console.print(f"[dim]Goodbye![/]")


if __name__ == "__main__":
    main()
