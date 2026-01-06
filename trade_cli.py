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
    forge_menu as forge_menu_handler,
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
            menu.add_row("7", f"{CLIIcons.FIRE} The Forge", "Play development, validation, audits")
            menu.add_row("8", f"{CLIIcons.NETWORK} Connection Test", "Test API connectivity and rate limits")
            menu.add_row("9", f"{CLIIcons.SETTINGS} Health Check", "Comprehensive system health diagnostic")
            menu.add_row("10", f"[bold {gold}]{CLIIcons.PANIC} PANIC: Close All & Stop[/]", f"[{gold}]Emergency: Close all positions & cancel orders[/]")
            menu.add_row("11", f"{CLIIcons.QUIT} Exit", "Exit the CLI")
            
            # Use art-themed menu panel
            console.print(CLIStyles.get_menu_panel(menu, "MAIN MENU", is_main=True))
            
            # Print decorative menu bottom border
            BillArtWrapper.print_menu_bottom()
            
            # Themed tip text
            tip_color = BillArtColors.GREEN_MONEY if CLIStyles.use_art_wrapper else CLIColors.DIM_TEXT
            console.print(f"[{tip_color}]💡 Tip: Type 'back' or 'b' at any prompt to cancel and return to previous menu[/]")
            
            choice = get_choice(valid_range=range(1, 12))

            # Handle back/exit command from main menu
            if choice is BACK:
                console.print(f"\n[yellow]Goodbye![/]")
                break

            # Route to appropriate menu handler
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
                    self.forge_menu()
                elif choice == 8:
                    self.connection_test()
                elif choice == 9:
                    self.health_check()
                elif choice == 10:
                    self.panic_menu()
                elif choice == 11:
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

    # ==================== FORGE MENU ====================

    def forge_menu(self):
        """The Forge - Play development environment. Delegates to src.cli.menus.forge_menu."""
        forge_menu_handler(self)

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
    
    risk_table.add_row("Max Position Size:", f"${config.risk.max_position_size_usdt:,.2f}")
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
      
      backtest run   Run Play-based backtest (golden path)
      backtest preflight   Check data/config without running
      backtest data-fix    Fix data gaps/coverage
      backtest list        List available Plays
    """
    parser = argparse.ArgumentParser(
        description="TRADE - Bybit Unified Trading Account CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python trade_cli.py                              # Interactive mode (default)
  python trade_cli.py --smoke data                 # Data builder smoke test
  python trade_cli.py --smoke full                 # Full CLI smoke test
  
  # Play-based backtest (golden path):
  python trade_cli.py backtest run --play SOLUSDT_15m_ema_crossover
  python trade_cli.py backtest run --play SOLUSDT_15m_ema_crossover --smoke
  python trade_cli.py backtest preflight --play SOLUSDT_15m_ema_crossover
  python trade_cli.py backtest data-fix --play SOLUSDT_15m_ema_crossover
  python trade_cli.py backtest list
        """
    )
    
    parser.add_argument(
        "--smoke",
        choices=["data", "full", "data_extensive", "orders", "live_check", "backtest", "forge"],
        default=None,
        help="Run non-interactive smoke test. 'data'/'full'/'data_extensive'/'orders'/'backtest'/'forge' use DEMO. 'live_check' tests LIVE connectivity (opt-in, requires LIVE keys)."
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
    backtest_parser = subparsers.add_parser("backtest", help="Play-based backtest (golden path)")
    backtest_subparsers = backtest_parser.add_subparsers(dest="backtest_command", help="Backtest commands")
    
    # backtest run
    run_parser = backtest_subparsers.add_parser("run", help="Run an Play backtest")
    run_parser.add_argument("--play", required=True, help="Play identifier (e.g., SOLUSDT_15m_ema_crossover)")
    run_parser.add_argument("--dir", dest="plays_dir", help="Override Play directory")
    run_parser.add_argument("--data-env", choices=["live", "demo"], default="live", help="Data environment (default: live)")
    run_parser.add_argument("--symbol", help="Override symbol (default: from Play)")
    run_parser.add_argument("--start", help="Window start (YYYY-MM-DD or YYYY-MM-DD HH:MM)")
    run_parser.add_argument("--end", help="Window end (YYYY-MM-DD or YYYY-MM-DD HH:MM)")
    run_parser.add_argument("--smoke", action="store_true", help="Smoke mode: fast wiring check with small window")
    run_parser.add_argument("--strict", action="store_true", default=True, help="Strict indicator access (default: True)")
    run_parser.add_argument("--no-strict", action="store_false", dest="strict", help="Disable strict indicator checks")
    run_parser.add_argument("--artifacts-dir", help="Override artifacts directory")
    run_parser.add_argument("--no-artifacts", action="store_true", help="Skip writing artifacts")
    run_parser.add_argument("--emit-snapshots", action="store_true", help="Emit snapshot artifacts (OHLCV + computed indicators)")
    run_parser.add_argument("--fix-gaps", action="store_true", default=True, help="Auto-fetch missing data (default: True)")
    run_parser.add_argument("--no-fix-gaps", action="store_false", dest="fix_gaps", help="Disable auto-fetch of missing data")
    run_parser.add_argument("--validate", action="store_true", default=True, help="Validate artifacts after run (default: True)")
    run_parser.add_argument("--no-validate", action="store_false", dest="validate", help="Skip artifact validation (faster, less safe)")
    run_parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")
    
    # backtest preflight
    preflight_parser = backtest_subparsers.add_parser("preflight", help="Run preflight check without executing")
    preflight_parser.add_argument("--play", required=True, help="Play identifier")
    preflight_parser.add_argument("--data-env", choices=["live", "demo"], default="live", help="Data environment")
    preflight_parser.add_argument("--symbol", help="Override symbol")
    preflight_parser.add_argument("--start", help="Window start")
    preflight_parser.add_argument("--end", help="Window end")
    preflight_parser.add_argument("--fix-gaps", action="store_true", help="Auto-fix data gaps using existing tools")
    preflight_parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")
    
    # backtest indicators (NEW - indicator key discovery)
    indicators_parser = backtest_subparsers.add_parser("indicators", help="Discover indicator keys for an Play")
    indicators_parser.add_argument("--play", help="Play identifier (required unless --audit-math-from-snapshots)")
    indicators_parser.add_argument("--data-env", choices=["live", "demo"], default="live", help="Data environment")
    indicators_parser.add_argument("--symbol", help="Override symbol")
    indicators_parser.add_argument("--print-keys", action="store_true", default=True, help="Print all indicator keys")
    indicators_parser.add_argument("--compute", action="store_true", help="Actually compute indicators (requires --start/--end)")
    indicators_parser.add_argument("--start", help="Window start (for --compute)")
    indicators_parser.add_argument("--end", help="Window end (for --compute)")
    indicators_parser.add_argument("--audit-math-from-snapshots", action="store_true", help="Audit math parity using snapshot artifacts")
    indicators_parser.add_argument("--run-dir", help="Run directory for --audit-math-from-snapshots")
    indicators_parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")

    # Make --play required unless audit mode
    def validate_indicators_args(args):
        if not args.audit_math_from_snapshots and not args.play:
            indicators_parser.error("--play is required unless --audit-math-from-snapshots is used")
        if args.audit_math_from_snapshots and not args.run_dir:
            indicators_parser.error("--run-dir is required when using --audit-math-from-snapshots")

    # Store validator for later use
    indicators_parser._validate = validate_indicators_args
    
    # backtest data-fix
    datafix_parser = backtest_subparsers.add_parser("data-fix", help="Fix data for an Play")
    datafix_parser.add_argument("--play", required=True, help="Play identifier")
    datafix_parser.add_argument("--data-env", choices=["live", "demo"], default="live", help="Data environment")
    datafix_parser.add_argument("--symbol", help="Override symbol")
    datafix_parser.add_argument("--start", help="Sync from this date")
    datafix_parser.add_argument("--sync-to-now", action="store_true", help="Sync data to current time")
    datafix_parser.add_argument("--fill-gaps", action="store_true", default=True, help="Fill gaps after sync")
    datafix_parser.add_argument("--heal", action="store_true", help="Run full heal after sync")
    datafix_parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")
    
    # backtest list
    list_parser = backtest_subparsers.add_parser("list", help="List available Plays")
    list_parser.add_argument("--dir", dest="plays_dir", help="Override Plays directory")
    list_parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")
    
    # backtest play-normalize (NEW - build-time validation)
    normalize_parser = backtest_subparsers.add_parser(
        "play-normalize",
        help="Validate and normalize an Play YAML (build-time)"
    )
    normalize_parser.add_argument("--play", required=True, help="Play identifier")
    normalize_parser.add_argument("--dir", dest="plays_dir", help="Override Plays directory")
    normalize_parser.add_argument("--write", action="store_true", help="Write normalized YAML in-place")
    normalize_parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")

    # backtest play-normalize-batch (NEW - batch normalization)
    batch_normalize_parser = backtest_subparsers.add_parser(
        "play-normalize-batch",
        help="Batch validate and normalize all Plays in a directory"
    )
    batch_normalize_parser.add_argument("--dir", dest="plays_dir", required=True, help="Directory containing Play YAML files")
    batch_normalize_parser.add_argument("--write", action="store_true", help="Write normalized YAML in-place")
    batch_normalize_parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")

    # backtest verify-suite (NEW - global verification suite)
    verify_suite_parser = backtest_subparsers.add_parser(
        "verify-suite",
        help="Run global indicator & strategy verification suite or artifact parity check"
    )
    # Standard verification mode (Play directory)
    verify_suite_parser.add_argument("--dir", dest="plays_dir", help="Directory containing verification Play YAML files")
    verify_suite_parser.add_argument("--data-env", choices=["live", "demo"], default="live", help="Data environment")
    verify_suite_parser.add_argument("--start", help="Fixed window start (YYYY-MM-DD)")
    verify_suite_parser.add_argument("--end", help="Fixed window end (YYYY-MM-DD)")
    verify_suite_parser.add_argument("--strict", action="store_true", default=True, help="Strict indicator access")
    verify_suite_parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")
    verify_suite_parser.add_argument("--skip-toolkit-audit", action="store_true", help="Skip Gate 1 toolkit contract audit")
    # Phase 3.1: CSV vs Parquet parity verification mode
    verify_suite_parser.add_argument("--compare-csv-parquet", action="store_true", help="Verify CSV vs Parquet artifact parity")
    verify_suite_parser.add_argument("--play", dest="parity_play", help="Play ID for parity check")
    verify_suite_parser.add_argument("--symbol", dest="parity_symbol", help="Symbol for parity check")
    verify_suite_parser.add_argument("--run", dest="parity_run", help="Run ID (e.g., run-001 or 'latest')")
    
    # backtest audit-toolkit (NEW - indicator registry audit)
    audit_parser = backtest_subparsers.add_parser(
        "audit-toolkit",
        help="Run toolkit contract audit over all registry indicators"
    )
    audit_parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")
    audit_parser.add_argument("--sample-bars", type=int, default=2000, help="Number of synthetic OHLCV bars (default: 2000)")
    audit_parser.add_argument("--seed", type=int, default=1337, help="Random seed for synthetic data (default: 1337)")
    audit_parser.add_argument("--fail-on-extras", action="store_true", help="Treat extras as failures")
    audit_parser.add_argument("--strict", action="store_true", default=True, help="Fail on any contract breach")
    
    # backtest metadata-smoke (Indicator Metadata v1 smoke test)
    metadata_parser = backtest_subparsers.add_parser(
        "metadata-smoke",
        help="Run Indicator Metadata v1 smoke test (validates metadata capture and export)"
    )
    metadata_parser.add_argument("--symbol", default="BTCUSDT", help="Symbol for synthetic data (default: BTCUSDT)")
    metadata_parser.add_argument("--tf", default="15m", help="Timeframe (default: 15m)")
    metadata_parser.add_argument("--sample-bars", type=int, default=2000, help="Number of synthetic bars (default: 2000)")
    metadata_parser.add_argument("--seed", type=int, default=1337, help="Random seed for reproducibility (default: 1337)")
    metadata_parser.add_argument("--export", dest="export_path", default="artifacts/indicator_metadata.jsonl", help="Export path (default: artifacts/indicator_metadata.jsonl)")
    metadata_parser.add_argument("--format", dest="export_format", choices=["jsonl", "json", "csv"], default="jsonl", help="Export format (default: jsonl)")

    # backtest mark-price-smoke (Mark Price Engine smoke test)
    mark_price_parser = backtest_subparsers.add_parser(
        "mark-price-smoke",
        help="Run Mark Price Engine smoke test (validates MarkPriceEngine and snapshot.get())"
    )
    mark_price_parser.add_argument("--sample-bars", type=int, default=500, help="Number of synthetic bars (default: 500)")
    mark_price_parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility (default: 42)")

    # backtest structure-smoke (Market Structure smoke test)
    structure_parser = backtest_subparsers.add_parser(
        "structure-smoke",
        help="Run Market Structure smoke test (validates SwingDetector and TrendClassifier)"
    )
    structure_parser.add_argument("--sample-bars", type=int, default=500, help="Number of synthetic bars (default: 500)")
    structure_parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility (default: 42)")

    # backtest math-parity (contract audit + in-memory math parity)
    math_parity_parser = backtest_subparsers.add_parser(
        "math-parity",
        help="Validate indicator math parity (contract + in-memory comparison)"
    )
    math_parity_parser.add_argument("--play", required=True, help="Path to Play YAML for parity audit")
    math_parity_parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    math_parity_parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    math_parity_parser.add_argument("--output-dir", help="Output directory for diff reports (optional)")
    math_parity_parser.add_argument("--contract-sample-bars", type=int, default=2000, help="Synthetic bars for contract audit (default: 2000)")
    math_parity_parser.add_argument("--contract-seed", type=int, default=1337, help="Random seed for contract audit (default: 1337)")
    math_parity_parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")
    
    # backtest audit-snapshot-plumbing (Phase 4 snapshot plumbing parity)
    plumbing_parser = backtest_subparsers.add_parser(
        "audit-snapshot-plumbing",
        help="Run Phase 4 snapshot plumbing parity audit"
    )
    plumbing_parser.add_argument("--play", required=True, help="Play identifier or path")
    plumbing_parser.add_argument("--symbol", help="Override symbol (optional, inferred from Play)")
    plumbing_parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    plumbing_parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    plumbing_parser.add_argument("--max-samples", type=int, default=2000, help="Max exec samples (default: 2000)")
    plumbing_parser.add_argument("--tolerance", type=float, default=1e-12, help="Tolerance for float comparison (default: 1e-12)")
    plumbing_parser.add_argument("--strict", action="store_true", default=True, help="Stop at first mismatch (default: True)")
    plumbing_parser.add_argument("--no-strict", action="store_false", dest="strict", help="Continue after mismatches")
    plumbing_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")
    
    # backtest verify-determinism (Phase 3 - hash-based determinism verification)
    determinism_parser = backtest_subparsers.add_parser(
        "verify-determinism",
        help="Verify backtest determinism by comparing run hashes"
    )
    determinism_parser.add_argument("--run-a", required=False, help="Path to first run's artifact folder")
    determinism_parser.add_argument("--run-b", required=False, help="Path to second run's artifact folder (for compare mode)")
    determinism_parser.add_argument("--re-run", action="store_true", help="Re-run the Play and compare to existing run")
    determinism_parser.add_argument("--fix-gaps", action="store_true", default=False, help="Allow data sync during re-run")
    determinism_parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")
    
    # backtest metrics-audit
    metrics_audit_parser = backtest_subparsers.add_parser(
        "metrics-audit",
        help="Validate financial metrics calculation (drawdown, Calmar, TF handling)"
    )
    metrics_audit_parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")

    # backtest audit-rollup (1m rollup parity audit)
    rollup_parser = backtest_subparsers.add_parser(
        "audit-rollup",
        help="Run 1m rollup parity audit (ExecRollupBucket + snapshot accessors)"
    )
    rollup_parser.add_argument("--intervals", type=int, default=10, help="Number of exec intervals to test (default: 10)")
    rollup_parser.add_argument("--quotes", type=int, default=15, help="Quotes per interval (default: 15)")
    rollup_parser.add_argument("--seed", type=int, default=1337, help="Random seed (default: 1337)")
    rollup_parser.add_argument("--tolerance", type=float, default=1e-10, help="Tolerance (default: 1e-10)")
    rollup_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # ===== VIZ SUBCOMMAND =====
    # Backtest visualization server
    viz_parser = subparsers.add_parser("viz", help="Backtest visualization server")
    viz_subparsers = viz_parser.add_subparsers(dest="viz_command", help="Visualization commands")

    # viz serve
    serve_parser = viz_subparsers.add_parser("serve", help="Start visualization server")
    serve_parser.add_argument("--port", type=int, default=8765, help="Server port (default: 8765)")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    serve_parser.add_argument("--no-browser", action="store_true", help="Don't open browser")
    serve_parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")

    # viz open
    open_parser = viz_subparsers.add_parser("open", help="Open browser to running server")
    open_parser.add_argument("--port", type=int, default=8765, help="Server port (default: 8765)")

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
    from src.tools.backtest_cli_wrapper import backtest_run_play_tool
    
    # Parse dates
    start = _parse_datetime(args.start) if args.start else None
    end = _parse_datetime(args.end) if args.end else None
    artifacts_dir = Path(args.artifacts_dir) if args.artifacts_dir else None
    plays_dir = Path(args.plays_dir) if args.plays_dir else None

    if not args.json_output:
        console.print(Panel(
            f"[bold cyan]BACKTEST RUN[/]\n"
            f"Play: {args.play}\n"
            f"DataEnv: {args.data_env} | Smoke: {args.smoke} | Strict: {args.strict}",
            border_style="cyan"
        ))

    result = backtest_run_play_tool(
        play_id=args.play,
        env=args.data_env,
        symbol=args.symbol,
        start=start,
        end=end,
        smoke=args.smoke,
        strict=args.strict,
        write_artifacts=not args.no_artifacts,
        artifacts_dir=artifacts_dir,
        plays_dir=plays_dir,
        emit_snapshots=args.emit_snapshots,
        fix_gaps=args.fix_gaps,
        validate_artifacts_after=args.validate,
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
    from src.tools.backtest_cli_wrapper import backtest_preflight_play_tool, backtest_data_fix_tool
    
    # Parse dates
    start = _parse_datetime(args.start) if args.start else None
    end = _parse_datetime(args.end) if args.end else None
    
    if not args.json_output:
        console.print(Panel(
            f"[bold cyan]BACKTEST PREFLIGHT[/]\n"
            f"Play: {args.play} | DataEnv: {args.data_env}",
            border_style="cyan"
        ))
    
    # Pass fix_gaps to the tool - it handles auto-sync internally
    if args.fix_gaps and not args.json_output:
        console.print("[dim]Auto-sync enabled: will fetch missing data if needed[/]")
    
    result = backtest_preflight_play_tool(
        play_id=args.play,
        env=args.data_env,
        symbol=args.symbol,
        start=start,
        end=end,
        fix_gaps=args.fix_gaps,
    )
    
    # JSON output mode
    if args.json_output:
        output = {
            "status": "pass" if result.success else "fail",
            "message": result.message if result.success else result.error,
            "checks": {
                "play_valid": result.data.get("play_valid") if result.data else None,
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
    from pathlib import Path

    # Validate arguments
    if hasattr(args, '_validate'):
        args._validate(args)

    # Handle audit mode
    if args.audit_math_from_snapshots:
        from src.tools.backtest_cli_wrapper import backtest_audit_math_from_snapshots_tool

        if not args.run_dir:
            console.print("[red]Error: --run-dir is required for --audit-math-from-snapshots[/]")
            return 1

        run_dir = Path(args.run_dir)

        if not args.json_output:
            console.print(Panel(
                f"[bold cyan]INDICATOR MATH AUDIT[/]\n"
                f"Run Dir: {args.run_dir}",
                border_style="cyan"
            ))

        result = backtest_audit_math_from_snapshots_tool(run_dir=run_dir)

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
                summary = result.data.get("summary", {})
                console.print(f"\n[dim]Overall: {summary.get('passed_columns', 0)}/{summary.get('total_columns', 0)} columns passed[/]")
                console.print(f"[dim]Max diff: {summary.get('max_abs_diff', 0):.2e}[/]")
                console.print(f"[dim]Mean diff: {summary.get('mean_abs_diff', 0):.2e}[/]")

                # Show per-column results
                if result.data.get("column_results"):
                    console.print(f"\n[bold]Column Results:[/]")
                    for col_result in result.data["column_results"]:
                        status = "[green]PASS[/]" if col_result["passed"] else "[red]FAIL[/]"
                        console.print(f"  {col_result['column']}: {status} "
                                    f"(max_diff={col_result['max_abs_diff']:.2e}, "
                                    f"mean_diff={col_result['mean_abs_diff']:.2e})")
        else:
            console.print(f"\n[bold red]FAIL {result.error}[/]")
            if result.data and result.data.get("error_details"):
                console.print(result.data["error_details"])
        return 0 if result.success else 1

    # Original indicator discovery mode
    from src.tools.backtest_cli_wrapper import backtest_indicators_tool

    # Parse dates
    start = _parse_datetime(args.start) if args.start else None
    end = _parse_datetime(args.end) if args.end else None

    if not args.json_output:
        console.print(Panel(
            f"[bold cyan]BACKTEST INDICATORS[/]\n"
            f"Play: {args.play} | DataEnv: {args.data_env}",
            border_style="cyan"
        ))

    result = backtest_indicators_tool(
        play_id=args.play,
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
        console.print(f"Play: {data.get('play_id')}")
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
            f"Play: {args.play} | DataEnv: {args.data_env}\n"
            f"Sync to now: {args.sync_to_now} | Fill gaps: {args.fill_gaps} | Heal: {args.heal}",
            border_style="cyan"
        ))
    
    result = backtest_data_fix_tool(
        play_id=args.play,
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
    from src.tools.backtest_cli_wrapper import backtest_list_plays_tool
    
    plays_dir = Path(args.plays_dir) if args.plays_dir else None
    
    result = backtest_list_plays_tool(plays_dir=plays_dir)
    
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
        console.print(f"\n[bold cyan]Available Plays:[/]")
        console.print(f"[dim]Directory: {result.data['directory']}[/]\n")
        
        for card_id in result.data["plays"]:
            console.print(f"  - {card_id}")
        
        console.print(f"\n[dim]Total: {len(result.data['plays'])} Plays[/]")
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
    """Handle `backtest play-normalize` subcommand."""
    import json
    from pathlib import Path
    from src.tools.backtest_cli_wrapper import backtest_play_normalize_tool

    plays_dir = Path(args.plays_dir) if args.plays_dir else None

    if not args.json_output:
        console.print(Panel(
            f"[bold cyan]PLAY NORMALIZE[/]\n"
            f"Play: {args.play} | Write: {args.write}",
            border_style="cyan"
        ))

    result = backtest_play_normalize_tool(
        play_id=args.play,
        plays_dir=plays_dir,
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


def _handle_parity_verification(args, verify_artifact_parity_tool) -> int:
    """Handle CSV ↔ Parquet artifact parity verification (Phase 3.1)."""
    import json
    
    # Validate required args
    if not getattr(args, 'parity_play', None):
        console.print("[red]Error: --play is required for parity verification[/]")
        return 1
    if not getattr(args, 'parity_symbol', None):
        console.print("[red]Error: --symbol is required for parity verification[/]")
        return 1
    
    play_id = args.parity_play
    symbol = args.parity_symbol.upper()
    run_id = getattr(args, 'parity_run', None)
    if run_id and run_id.lower() == 'latest':
        run_id = None  # None means latest
    
    if not getattr(args, 'json_output', False):
        console.print(Panel(
            f"[bold cyan]CSV ↔ PARQUET PARITY VERIFICATION[/]\n"
            f"Play: {play_id}\n"
            f"Symbol: {symbol}\n"
            f"Run: {run_id or 'latest'}",
            border_style="cyan"
        ))
    
    result = verify_artifact_parity_tool(
        play_id=play_id,
        symbol=symbol,
        run_id=run_id,
    )
    
    # JSON output mode
    if getattr(args, 'json_output', False):
        output = {
            "command": "verify-suite",
            "mode": "compare-csv-parquet",
            "success": result.success,
            "message": result.message if result.success else result.error,
            "data": result.data,
        }
        print(json.dumps(output, indent=2))
        return 0 if result.success else 1
    
    # Human-readable output
    if result.success:
        console.print(f"\n[bold green]✓ PARITY PASSED[/] {result.message}")
        if result.data:
            for ar in result.data.get("artifact_results", []):
                icon = "✓" if ar.get("passed") else "✗"
                console.print(f"  {icon} {ar.get('artifact_name')}: {'PASS' if ar.get('passed') else 'FAIL'}")
        return 0
    else:
        console.print(f"\n[bold red]✗ PARITY FAILED[/] {result.error}")
        if result.data:
            for ar in result.data.get("artifact_results", []):
                icon = "✓" if ar.get("passed") else "✗"
                status = "PASS" if ar.get("passed") else "FAIL"
                console.print(f"  {icon} {ar.get('artifact_name')}: {status}")
                for err in ar.get("errors", []):
                    console.print(f"      - {err}")
        return 1


def handle_backtest_verify_suite(args) -> int:
    """Handle `backtest verify-suite` subcommand - global verification suite or parity check."""
    import json
    from pathlib import Path
    from src.tools.backtest_cli_wrapper import (
        backtest_play_normalize_batch_tool,
        backtest_run_play_tool,
        backtest_audit_math_from_snapshots_tool,
        backtest_audit_toolkit_tool,
        verify_artifact_parity_tool,
    )

    # =====================================================================
    # Phase 3.1: CSV ↔ Parquet Parity Verification Mode
    # =====================================================================
    if getattr(args, 'compare_csv_parquet', False):
        return _handle_parity_verification(args, verify_artifact_parity_tool)
    
    # =====================================================================
    # Standard Verification Suite Mode
    # =====================================================================
    if not args.plays_dir:
        console.print("[red]Error: --dir is required for verification suite mode[/]")
        console.print("[dim]Use --compare-csv-parquet for artifact parity mode[/]")
        return 1
    
    if not args.start or not args.end:
        console.print("[red]Error: --start and --end are required for verification suite mode[/]")
        return 1

    plays_dir = Path(args.plays_dir)
    start = _parse_datetime(args.start)
    end = _parse_datetime(args.end)
    skip_toolkit_audit = getattr(args, 'skip_toolkit_audit', False)

    if not args.json_output:
        console.print(Panel(
            f"[bold cyan]GLOBAL VERIFICATION SUITE[/]\n"
            f"Directory: {args.plays_dir}\n"
            f"Window: {args.start} -> {args.end}\n"
            f"DataEnv: {args.data_env} | Strict: {args.strict}\n"
            f"Toolkit Audit: {'SKIPPED' if skip_toolkit_audit else 'ENABLED (Gate 1)'}",
            border_style="cyan"
        ))

    suite_results = {
        "suite_config": {
            "plays_dir": str(plays_dir),
            "data_env": args.data_env,
            "window_start": args.start,
            "window_end": args.end,
            "strict": args.strict,
            "skip_toolkit_audit": skip_toolkit_audit,
        },
        "phases": {},
        "summary": {},
    }

    # =====================================================================
    # PHASE 0 (Gate 1): Toolkit Contract Audit (unless skipped)
    # =====================================================================
    if not skip_toolkit_audit:
        console.print("\n[bold]Phase 0 (Gate 1): Toolkit Contract Audit[/]")
        
        toolkit_result = backtest_audit_toolkit_tool(
            sample_bars=2000,
            seed=1337,
            fail_on_extras=False,
            strict=True,
        )
        
        suite_results["phases"]["toolkit_audit"] = {
            "success": toolkit_result.success,
            "message": toolkit_result.message if toolkit_result.success else toolkit_result.error,
            "data": toolkit_result.data,
        }
        
        if not toolkit_result.success:
            console.print(f"[red]FAIL Toolkit audit failed: {toolkit_result.error}[/]")
            if args.json_output:
                suite_results["summary"] = {"overall_success": False, "failure_phase": "toolkit_audit"}
                print(json.dumps(suite_results, indent=2, default=str))
            return 1
        
        console.print(f"[green]PASS Toolkit audit: {toolkit_result.message}[/]")
    else:
        console.print("\n[dim]Phase 0 (Gate 1): Toolkit Contract Audit - SKIPPED[/]")
        suite_results["phases"]["toolkit_audit"] = {"skipped": True}

    # =====================================================================
    # PHASE 1: Batch normalize all cards
    # =====================================================================
    console.print("\n[bold]Phase 1: Batch Normalization[/]")

    normalize_result = backtest_play_normalize_batch_tool(
        plays_dir=plays_dir,
        write_in_place=True,  # Always write for verification
    )

    suite_results["phases"]["normalization"] = {
        "success": normalize_result.success,
        "message": normalize_result.message if normalize_result.success else normalize_result.error,
        "data": normalize_result.data,
    }

    if not normalize_result.success:
        console.print(f"[red]FAIL Normalization failed: {normalize_result.error}[/]")
        if args.json_output:
            suite_results["summary"] = {"overall_success": False, "failure_phase": "normalization"}
            print(json.dumps(suite_results, indent=2, default=str))
        return 1

    console.print(f"[green]PASS Normalization successful: {normalize_result.data['summary']['passed']}/{normalize_result.data['summary']['total_cards']} cards[/]")

    # =====================================================================
    # PHASE 2: Run backtests with snapshot emission
    # =====================================================================
    console.print("\n[bold]Phase 2: Backtest Runs with Snapshots[/]")

    backtest_results = []
    failed_backtests = []

    play_ids = normalize_result.data["results"]
    for card_result in play_ids:
        if not card_result["success"]:
            continue  # Skip cards that failed normalization

        play_id = card_result["play_id"]
        console.print(f"  Running {play_id}...")

        run_result = backtest_run_play_tool(
            play_id=play_id,
            env=args.data_env,
            start=start,
            end=end,
            smoke=False,
            strict=args.strict,
            write_artifacts=False,  # Skip regular artifacts to avoid noise
            plays_dir=plays_dir,
            emit_snapshots=True,  # Always emit snapshots for verification
        )

        backtest_result = {
            "play_id": play_id,
            "success": run_result.success,
            "message": run_result.message if run_result.success else run_result.error,
            "run_dir": run_result.data.get("artifact_dir") if run_result.data else None,
        }

        if run_result.success:
            console.print(f"    [green]PASS {play_id}: {run_result.message}[/]")
        else:
            console.print(f"    [red]FAIL {play_id}: {run_result.error}[/]")
            failed_backtests.append(play_id)

        backtest_results.append(backtest_result)

    suite_results["phases"]["backtests"] = {
        "results": backtest_results,
        "total_cards": len(backtest_results),
        "successful_runs": len(backtest_results) - len(failed_backtests),
        "failed_runs": len(failed_backtests),
    }

    if failed_backtests:
        console.print(f"[red]FAIL Backtests failed: {len(failed_backtests)}/{len(backtest_results)} cards[/]")
        if args.json_output:
            suite_results["summary"] = {"overall_success": False, "failure_phase": "backtests"}
            print(json.dumps(suite_results, indent=2, default=str))
        return 1

        console.print(f"[green]PASS Backtests successful: {len(backtest_results)}/{len(backtest_results)} cards[/]")

    # =====================================================================
    # PHASE 3: Math parity audits
    # =====================================================================
    console.print("\n[bold]Phase 3: Math Parity Audits[/]")

    audit_results = []
    failed_audits = []

    for backtest_result in backtest_results:
        play_id = backtest_result["play_id"]
        run_dir = backtest_result["run_dir"]

        if not run_dir:
            console.print(f"  [red]FAIL {play_id}: No run directory[/]")
            failed_audits.append(play_id)
            continue

        console.print(f"  Auditing {play_id}...")

        audit_result = backtest_audit_math_from_snapshots_tool(run_dir=Path(run_dir))

        audit_summary = {
            "play_id": play_id,
            "success": audit_result.success,
            "message": audit_result.message if audit_result.success else audit_result.error,
            "run_dir": run_dir,
        }

        if audit_result.success and audit_result.data:
            summary = audit_result.data.get("summary", {})
            audit_summary.update({
                "total_columns": summary.get("total_columns", 0),
                "passed_columns": summary.get("passed_columns", 0),
                "failed_columns": summary.get("failed_columns", 0),
                "max_abs_diff": summary.get("max_abs_diff", 0),
                "mean_abs_diff": summary.get("mean_abs_diff", 0),
            })

            if audit_result.success:
                console.print(f"    [green]PASS {play_id}: {summary.get('passed_columns', 0)}/{summary.get('total_columns', 0)} columns passed[/]")
            else:
                console.print(f"    [red]FAIL {play_id}: {summary.get('failed_columns', 0)}/{summary.get('total_columns', 0)} columns failed[/]")
                failed_audits.append(play_id)
        else:
            console.print(f"    [red]FAIL {play_id}: {audit_result.error}[/]")
            failed_audits.append(play_id)

        audit_results.append(audit_summary)

    suite_results["phases"]["audits"] = {
        "results": audit_results,
        "total_cards": len(audit_results),
        "successful_audits": len(audit_results) - len(failed_audits),
        "failed_audits": len(failed_audits),
    }

    # =====================================================================
    # FINAL SUMMARY
    # =====================================================================
    overall_success = len(failed_audits) == 0

    suite_results["summary"] = {
        "overall_success": overall_success,
        "total_cards": len(backtest_results),
        "normalization_passed": suite_results["phases"]["normalization"]["success"],
        "backtests_passed": len(failed_backtests) == 0,
        "audits_passed": len(failed_audits) == 0,
        "failed_cards": failed_audits,
    }

    if not args.json_output:
        console.print(f"\n[bold]Suite Summary:[/]")
        console.print(f"  Total cards: {len(backtest_results)}")
        console.print(f"  Normalization: {'PASS' if suite_results['summary']['normalization_passed'] else 'FAIL'}")
        console.print(f"  Backtests: {'PASS' if suite_results['summary']['backtests_passed'] else 'FAIL'} ({len(backtest_results) - len(failed_backtests)}/{len(backtest_results)})")
        console.print(f"  Audits: {'PASS' if suite_results['summary']['audits_passed'] else 'FAIL'} ({len(audit_results) - len(failed_audits)}/{len(audit_results)})")

        if overall_success:
            console.print(f"\n[bold green]GLOBAL VERIFICATION SUITE PASSED![/]")
            console.print("All indicators compute correctly and match pandas_ta exactly.")
        else:
            console.print(f"\n[bold red]GLOBAL VERIFICATION SUITE FAILED[/]")
            if failed_audits:
                console.print(f"Failed cards: {', '.join(failed_audits)}")
    else:
        print(json.dumps(suite_results, indent=2, default=str))

    return 0 if overall_success else 1


def handle_backtest_normalize_batch(args) -> int:
    """Handle `backtest play-normalize-batch` subcommand."""
    import json
    from pathlib import Path
    from src.tools.backtest_cli_wrapper import backtest_play_normalize_batch_tool

    plays_dir = Path(args.plays_dir)

    if not args.json_output:
        console.print(Panel(
            f"[bold cyan]PLAY NORMALIZE BATCH[/]\n"
            f"Directory: {args.plays_dir} | Write: {args.write}",
            border_style="cyan"
        ))

    result = backtest_play_normalize_batch_tool(
        plays_dir=plays_dir,
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
            summary = result.data.get("summary", {})
            console.print(f"\n[dim]Processed: {summary.get('total_cards', 0)} cards[/]")
            console.print(f"[dim]Passed: {summary.get('passed', 0)}[/]")
            console.print(f"[dim]Failed: {summary.get('failed', 0)}[/]")
            if summary.get("failed", 0) > 0:
                console.print(f"\n[yellow]Failed cards:[/]")
                for card_result in result.data.get("results", []):
                    if not card_result.get("success"):
                        console.print(f"  [red]• {card_result.get('play_id')}: {card_result.get('error', 'Unknown error')}[/]")
        return 0
    else:
        console.print(f"\n[bold red]FAIL {result.error}[/]")
        if result.data and result.data.get("error_details"):
            console.print(result.data["error_details"])
        return 1


def handle_backtest_audit_toolkit(args) -> int:
    """Handle `backtest audit-toolkit` subcommand - Gate 1 toolkit contract audit."""
    import json
    from src.tools.backtest_cli_wrapper import backtest_audit_toolkit_tool
    
    if not args.json_output:
        console.print(Panel(
            f"[bold cyan]TOOLKIT CONTRACT AUDIT (Gate 1)[/]\n"
            f"Sample: {args.sample_bars} bars | Seed: {args.seed}\n"
            f"Strict: {args.strict} | Fail on extras: {args.fail_on_extras}",
            border_style="cyan"
        ))
    
    result = backtest_audit_toolkit_tool(
        sample_bars=args.sample_bars,
        seed=args.seed,
        fail_on_extras=args.fail_on_extras,
        strict=args.strict,
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
        console.print(f"\n[bold green]PASS {result.message}[/]")
        if result.data:
            console.print(f"[dim]Total indicators: {result.data.get('total_indicators', 0)}[/]")
            console.print(f"[dim]Passed: {result.data.get('passed_indicators', 0)}[/]")
            console.print(f"[dim]With extras dropped: {result.data.get('indicators_with_extras', 0)}[/]")
        return 0
    else:
        console.print(f"\n[bold red]FAIL {result.error}[/]")
        if result.data and result.data.get("indicator_results"):
            console.print("\n[bold]Failed Indicators:[/]")
            for r in result.data["indicator_results"]:
                if not r["passed"]:
                    console.print(f"  [red]- {r['indicator_type']}: missing={r['missing_outputs']}, collisions={r['collisions']}, error={r['error_message']}[/]")
        return 1


def handle_backtest_math_parity(args) -> int:
    """Handle `backtest math-parity` subcommand - indicator math parity audit."""
    import json
    from src.tools.backtest_cli_wrapper import backtest_math_parity_tool
    
    if not args.json_output:
        console.print(Panel(
            f"[bold cyan]MATH PARITY AUDIT[/]\n"
            f"Play: {args.play}\n"
            f"Window: {args.start} -> {args.end}\n"
            f"Contract audit: {args.contract_sample_bars} bars, seed={args.contract_seed}",
            border_style="cyan"
        ))
    
    result = backtest_math_parity_tool(
        play=args.play,
        start_date=args.start,
        end_date=args.end,
        output_dir=args.output_dir,
        contract_sample_bars=args.contract_sample_bars,
        contract_seed=args.contract_seed,
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
        console.print(f"\n[bold green]PASS {result.message}[/]")
        if result.data:
            contract_data = result.data.get("contract_audit", {})
            parity_data = result.data.get("parity_audit", {})
            console.print(f"[dim]Contract: {contract_data.get('passed', 0)}/{contract_data.get('total', 0)} indicators[/]")
            if parity_data and parity_data.get("summary"):
                summary = parity_data["summary"]
                console.print(f"[dim]Parity: {summary.get('passed_columns', 0)}/{summary.get('total_columns', 0)} columns[/]")
        return 0
    else:
        console.print(f"\n[bold red]FAIL {result.error}[/]")
        if result.data:
            contract_data = result.data.get("contract_audit", {})
            parity_data = result.data.get("parity_audit", {})
            if contract_data:
                console.print(f"[dim]Contract: {contract_data.get('passed', 0)}/{contract_data.get('total', 0)}[/]")
            if parity_data and parity_data.get("summary"):
                summary = parity_data["summary"]
                console.print(f"[dim]Parity: {summary.get('passed_columns', 0)}/{summary.get('total_columns', 0)}, max_diff={summary.get('max_abs_diff', 0):.2e}[/]")
        return 1


def handle_backtest_metadata_smoke(args) -> int:
    """Handle `backtest metadata-smoke` subcommand - Indicator Metadata v1 smoke test."""
    from src.cli.smoke_tests import run_metadata_smoke

    return run_metadata_smoke(
        symbol=args.symbol,
        tf=args.tf,
        sample_bars=args.sample_bars,
        seed=args.seed,
        export_path=args.export_path,
        export_format=args.export_format,
    )


def handle_backtest_mark_price_smoke(args) -> int:
    """Handle `backtest mark-price-smoke` subcommand - Mark Price Engine smoke test."""
    from src.cli.smoke_tests import run_mark_price_smoke

    return run_mark_price_smoke(
        sample_bars=args.sample_bars,
        seed=args.seed,
    )


def handle_backtest_structure_smoke(args) -> int:
    """Handle `backtest structure-smoke` subcommand - Market Structure smoke test."""
    from src.cli.smoke_tests import run_structure_smoke

    return run_structure_smoke(
        sample_bars=args.sample_bars,
        seed=args.seed,
    )


def handle_backtest_audit_snapshot_plumbing(args) -> int:
    """Handle `backtest audit-snapshot-plumbing` subcommand - Phase 4 plumbing parity."""
    import json
    from src.tools.backtest_cli_wrapper import backtest_audit_snapshot_plumbing_tool
    
    if not args.json_output:
        console.print(Panel(
            f"[bold cyan]PHASE 4: SNAPSHOT PLUMBING PARITY AUDIT[/]\n"
            f"Play: {args.play}\n"
            f"Window: {args.start} -> {args.end}\n"
            f"Max samples: {args.max_samples} | Tolerance: {args.tolerance:.0e} | Strict: {args.strict}",
            border_style="cyan"
        ))
    
    result = backtest_audit_snapshot_plumbing_tool(
        play_id=args.play,
        start_date=args.start,
        end_date=args.end,
        symbol=args.symbol,
        max_samples=args.max_samples,
        tolerance=args.tolerance,
        strict=args.strict,
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
        console.print(f"\n[bold green]✓ PASS[/] {result.message}")
        if result.data:
            console.print(f"[dim]  Samples: {result.data.get('total_samples', 0)}[/]")
            console.print(f"[dim]  Comparisons: {result.data.get('total_comparisons', 0)}[/]")
            console.print(f"[dim]  Max samples reached: {result.data.get('max_samples_reached', False)}[/]")
            console.print(f"[dim]  Runtime: {result.data.get('runtime_seconds', 0):.1f}s[/]")
        return 0
    else:
        console.print(f"\n[bold red]✗ FAIL[/] {result.error}")
        if result.data and result.data.get("first_mismatch"):
            mismatch = result.data["first_mismatch"]
            console.print(f"\n[bold]First mismatch:[/]")
            console.print(f"  ts_close: {mismatch.get('ts_close')}")
            console.print(f"  tf_role: {mismatch.get('tf_role')}")
            console.print(f"  key: {mismatch.get('key')}")
            console.print(f"  offset: {mismatch.get('offset')}")
            console.print(f"  observed: {mismatch.get('observed')}")
            console.print(f"  expected: {mismatch.get('expected')}")
            console.print(f"  abs_diff: {mismatch.get('abs_diff')}")
            console.print(f"  tolerance: {mismatch.get('tolerance')}")
            console.print(f"  exec_idx: {mismatch.get('exec_idx')}")
            console.print(f"  htf_idx: {mismatch.get('htf_idx')}")
            console.print(f"  target_idx: {mismatch.get('target_idx')}")
        return 1


def handle_backtest_audit_rollup(args) -> int:
    """Handle `backtest audit-rollup` subcommand - 1m rollup parity audit."""
    import json
    from src.tools.backtest_cli_wrapper import backtest_audit_rollup_parity_tool

    if not args.json_output:
        console.print(Panel(
            f"[bold cyan]ROLLUP PARITY AUDIT (1m Price Feed)[/]\n"
            f"Intervals: {args.intervals} | Quotes/interval: {args.quotes}\n"
            f"Seed: {args.seed} | Tolerance: {args.tolerance:.0e}",
            border_style="cyan"
        ))

    result = backtest_audit_rollup_parity_tool(
        n_intervals=args.intervals,
        quotes_per_interval=args.quotes,
        seed=args.seed,
        tolerance=args.tolerance,
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
        console.print(f"\nPASS {result.message}")
        if result.data:
            console.print(f"  Total intervals: {result.data.get('total_intervals', 0)}")
            console.print(f"  Total comparisons: {result.data.get('total_comparisons', 0)}")
            console.print(f"  Bucket tests: {'PASS' if result.data.get('bucket_tests_passed') else 'FAIL'}")
            console.print(f"  Accessor tests: {'PASS' if result.data.get('accessor_tests_passed') else 'FAIL'}")
        return 0
    else:
        console.print(f"\nFAIL {result.error}")
        if result.data:
            console.print(f"  Failed intervals: {result.data.get('failed_intervals', 0)}")
            console.print(f"  Failed comparisons: {result.data.get('failed_comparisons', 0)}")
        return 1


def handle_backtest_verify_determinism(args) -> int:
    """Handle `backtest verify-determinism` subcommand - Phase 3 hash-based verification."""
    import json
    from pathlib import Path
    from src.backtest.artifacts.determinism import compare_runs, verify_determinism_rerun
    
    if not args.json_output:
        console.print(Panel(
            "[bold cyan]DETERMINISM VERIFICATION[/]\n"
            "Compares backtest run hashes to verify determinism.",
            title="Backtest Audit",
            border_style="cyan"
        ))
    
    # Validate arguments
    if args.re_run:
        # Re-run mode: need --run-a
        if not args.run_a:
            console.print("[red]Error: --re-run requires --run-a (path to existing run)[/]")
            return 1
        
        run_path = Path(args.run_a)
        if not run_path.exists():
            console.print(f"[red]Error: Run path does not exist: {run_path}[/]")
            return 1
        
        if not args.json_output:
            console.print(f"[cyan]Re-running Play from: {run_path}[/]")
        
        result = verify_determinism_rerun(
            run_path=run_path,
            fix_gaps=args.fix_gaps,
        )
    else:
        # Compare mode: need both --run-a and --run-b
        if not args.run_a or not args.run_b:
            console.print("[red]Error: Compare mode requires both --run-a and --run-b[/]")
            return 1
        
        run_a = Path(args.run_a)
        run_b = Path(args.run_b)
        
        if not run_a.exists():
            console.print(f"[red]Error: Run A path does not exist: {run_a}[/]")
            return 1
        if not run_b.exists():
            console.print(f"[red]Error: Run B path does not exist: {run_b}[/]")
            return 1
        
        if not args.json_output:
            console.print(f"[cyan]Comparing runs:[/]")
            console.print(f"  A: {run_a}")
            console.print(f"  B: {run_b}")
        
        result = compare_runs(run_a, run_b)
    
    # Output results
    if args.json_output:
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.passed else 1
    
    result.print_report()
    return 0 if result.passed else 1


def handle_backtest_metrics_audit(args) -> int:
    """
    Handle `backtest metrics-audit` subcommand.
    
    Runs embedded test scenarios to validate financial metrics calculations:
    - Drawdown: max_dd_abs and max_dd_pct tracked independently
    - Calmar: uses CAGR, not arithmetic return
    - TF: unknown timeframes raise errors in strict mode
    - Edge cases: proper handling of zero/inf scenarios
    
    This is CLI validation - no pytest files per project rules.
    """
    import json
    from src.backtest.metrics import (
        _compute_drawdown_metrics,
        _compute_cagr,
        _compute_calmar,
        get_bars_per_year,
        normalize_tf_string,
    )
    from src.backtest.types import EquityPoint
    from datetime import datetime
    
    results = []
    all_passed = True
    
    if not args.json_output:
        console.print(Panel(
            "[bold cyan]METRICS AUDIT[/]\n"
            "Validating financial metrics calculations",
            title="Backtest Metrics",
            border_style="cyan"
        ))
    
    # =========================================================================
    # TEST 1: Drawdown Independent Maxima
    # =========================================================================
    test_name = "Drawdown Independent Maxima"
    try:
        # Scenario: Peak 10 → equity 1 (dd_pct=0.90), then Peak 1000 → equity 900 (dd_abs=100)
        # max_dd_abs should be 100, max_dd_pct should be 0.90 (tracked independently)
        equity_curve = [
            EquityPoint(timestamp=datetime(2024, 1, 1, 0, 0), equity=10.0),
            EquityPoint(timestamp=datetime(2024, 1, 1, 1, 0), equity=1.0),   # dd_pct=0.90
            EquityPoint(timestamp=datetime(2024, 1, 1, 2, 0), equity=1000.0),
            EquityPoint(timestamp=datetime(2024, 1, 1, 3, 0), equity=900.0),  # dd_abs=100
        ]
        
        max_dd_abs, max_dd_pct, _ = _compute_drawdown_metrics(equity_curve)
        
        # Assertions
        abs_correct = abs(max_dd_abs - 100.0) < 0.01
        pct_correct = abs(max_dd_pct - 0.90) < 0.01  # Now decimal, not percentage
        
        passed = abs_correct and pct_correct
        detail = f"max_dd_abs={max_dd_abs:.2f} (expected 100), max_dd_pct={max_dd_pct:.4f} (expected 0.90)"
        
        results.append({
            "test": test_name,
            "passed": passed,
            "detail": detail,
        })
        if not passed:
            all_passed = False
        
        if not args.json_output:
            status = "[green]PASS[/]" if passed else "[red]FAIL[/]"
            console.print(f"  {status} {test_name}")
            console.print(f"       {detail}")
    
    except Exception as e:
        results.append({"test": test_name, "passed": False, "detail": str(e)})
        all_passed = False
        if not args.json_output:
            console.print(f"  [red]FAIL[/] {test_name}: {e}")
    
    # =========================================================================
    # TEST 2: CAGR Calculation
    # =========================================================================
    test_name = "CAGR Geometric Formula"
    try:
        # E0=10000, E1=12100 over exactly 1 year (365 daily bars)
        # CAGR = (12100/10000)^(1/1) - 1 = 0.21 (21%)
        cagr = _compute_cagr(
            initial_equity=10000.0,
            final_equity=12100.0,
            total_bars=365,
            bars_per_year=365,
        )
        
        expected_cagr = 0.21
        passed = abs(cagr - expected_cagr) < 0.01
        detail = f"CAGR={cagr:.4f} (expected {expected_cagr})"
        
        results.append({
            "test": test_name,
            "passed": passed,
            "detail": detail,
        })
        if not passed:
            all_passed = False
        
        if not args.json_output:
            status = "[green]PASS[/]" if passed else "[red]FAIL[/]"
            console.print(f"  {status} {test_name}")
            console.print(f"       {detail}")
    
    except Exception as e:
        results.append({"test": test_name, "passed": False, "detail": str(e)})
        all_passed = False
        if not args.json_output:
            console.print(f"  [red]FAIL[/] {test_name}: {e}")
    
    # =========================================================================
    # TEST 3: Calmar Uses CAGR
    # =========================================================================
    test_name = "Calmar Uses CAGR"
    try:
        # Same as above: CAGR=0.21, max_dd=0.10 (decimal) → Calmar=2.1
        calmar = _compute_calmar(
            initial_equity=10000.0,
            final_equity=12100.0,
            max_dd_pct_decimal=0.10,
            total_bars=365,
            tf="1d",
            strict_tf=True,
        )
        
        expected_calmar = 2.1
        passed = abs(calmar - expected_calmar) < 0.1
        detail = f"Calmar={calmar:.2f} (expected ~{expected_calmar})"
        
        results.append({
            "test": test_name,
            "passed": passed,
            "detail": detail,
        })
        if not passed:
            all_passed = False
        
        if not args.json_output:
            status = "[green]PASS[/]" if passed else "[red]FAIL[/]"
            console.print(f"  {status} {test_name}")
            console.print(f"       {detail}")
    
    except Exception as e:
        results.append({"test": test_name, "passed": False, "detail": str(e)})
        all_passed = False
        if not args.json_output:
            console.print(f"  [red]FAIL[/] {test_name}: {e}")
    
    # =========================================================================
    # TEST 4: TF Strict Mode
    # =========================================================================
    test_name = "TF Strict Mode (Unknown TF Raises)"
    try:
        try:
            _ = get_bars_per_year("unknown_tf", strict=True)
            passed = False
            detail = "Expected ValueError for unknown TF, but none raised"
        except ValueError as e:
            passed = True
            detail = f"Correctly raised ValueError: {str(e)[:60]}..."
        
        results.append({
            "test": test_name,
            "passed": passed,
            "detail": detail,
        })
        if not passed:
            all_passed = False
        
        if not args.json_output:
            status = "[green]PASS[/]" if passed else "[red]FAIL[/]"
            console.print(f"  {status} {test_name}")
            console.print(f"       {detail}")
    
    except Exception as e:
        results.append({"test": test_name, "passed": False, "detail": str(e)})
        all_passed = False
        if not args.json_output:
            console.print(f"  [red]FAIL[/] {test_name}: {e}")
    
    # =========================================================================
    # TEST 5: TF Normalization
    # =========================================================================
    test_name = "TF Normalization (Bybit formats)"
    try:
        # Test Bybit numeric formats
        test_cases = [
            ("60", "1h"),
            ("240", "4h"),
            ("D", "1d"),
            ("1h", "1h"),  # Already normalized
        ]
        
        all_correct = True
        details = []
        for input_tf, expected in test_cases:
            normalized = normalize_tf_string(input_tf)
            if normalized != expected:
                all_correct = False
                details.append(f"{input_tf}->{normalized} (expected {expected})")
            else:
                details.append(f"{input_tf}->{normalized} OK")
        
        passed = all_correct
        detail = ", ".join(details)
        
        results.append({
            "test": test_name,
            "passed": passed,
            "detail": detail,
        })
        if not passed:
            all_passed = False
        
        if not args.json_output:
            status = "[green]PASS[/]" if passed else "[red]FAIL[/]"
            console.print(f"  {status} {test_name}")
            console.print(f"       {detail}")
    
    except Exception as e:
        results.append({"test": test_name, "passed": False, "detail": str(e)})
        all_passed = False
        if not args.json_output:
            console.print(f"  [red]FAIL[/] {test_name}: {e}")
    
    # =========================================================================
    # TEST 6: Edge Case - Zero Max DD (Calmar capped)
    # =========================================================================
    test_name = "Edge Case: Zero Max DD (Calmar capped)"
    try:
        calmar = _compute_calmar(
            initial_equity=10000.0,
            final_equity=12100.0,
            max_dd_pct_decimal=0.0,  # No drawdown
            total_bars=365,
            tf="1d",
            strict_tf=True,
        )
        
        passed = calmar == 100.0  # Should be capped at 100
        detail = f"Calmar={calmar} (expected 100.0 when no DD)"
        
        results.append({
            "test": test_name,
            "passed": passed,
            "detail": detail,
        })
        if not passed:
            all_passed = False
        
        if not args.json_output:
            status = "[green]PASS[/]" if passed else "[red]FAIL[/]"
            console.print(f"  {status} {test_name}")
            console.print(f"       {detail}")
    
    except Exception as e:
        results.append({"test": test_name, "passed": False, "detail": str(e)})
        all_passed = False
        if not args.json_output:
            console.print(f"  [red]FAIL[/] {test_name}: {e}")
    
    # =========================================================================
    # SUMMARY
    # =========================================================================
    passed_count = sum(1 for r in results if r["passed"])
    total_count = len(results)
    
    if args.json_output:
        output = {
            "passed": all_passed,
            "summary": f"{passed_count}/{total_count} tests passed",
            "tests": results,
        }
        print(json.dumps(output, indent=2))
    else:
        console.print(f"\n[bold]Summary: {passed_count}/{total_count} tests passed[/]")
        if all_passed:
            console.print("[bold green]OK All metrics audit tests PASSED[/]")
        else:
            console.print("[bold red]FAIL Some metrics audit tests FAILED[/]")
    
    return 0 if all_passed else 1


# =============================================================================
# VIZ SUBCOMMAND HANDLERS
# =============================================================================

def handle_viz_serve(args) -> int:
    """Handle `viz serve` subcommand - start visualization server."""
    try:
        from src.viz.server import run_server

        console.print(Panel(
            f"[bold cyan]BACKTEST VISUALIZATION SERVER[/]\n"
            f"Host: {args.host}:{args.port}\n"
            f"Auto-reload: {args.reload}",
            border_style="cyan"
        ))

        run_server(
            host=args.host,
            port=args.port,
            open_browser=not args.no_browser,
            reload=args.reload,
        )
        return 0
    except ImportError as e:
        console.print(f"[red]Error: Missing dependencies for visualization server[/]")
        console.print(f"[dim]Run: pip install fastapi uvicorn[/]")
        console.print(f"[dim]Details: {e}[/]")
        return 1
    except Exception as e:
        console.print(f"[red]Error starting server: {e}[/]")
        return 1


def handle_viz_open(args) -> int:
    """Handle `viz open` subcommand - open browser to running server."""
    import webbrowser

    url = f"http://127.0.0.1:{args.port}"
    console.print(f"Opening browser to: {url}")
    webbrowser.open(url)
    return 0


def main():
    """
    Main entry point for trade_cli.

    Handles two modes:
    - Interactive: No args -> main menu loop
    - Non-interactive: --smoke or backtest subcommand -> run and exit
    """
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
        elif args.backtest_command == "play-normalize":
            sys.exit(handle_backtest_normalize(args))
        elif args.backtest_command == "play-normalize-batch":
            sys.exit(handle_backtest_normalize_batch(args))
        elif args.backtest_command == "verify-suite":
            sys.exit(handle_backtest_verify_suite(args))
        elif args.backtest_command == "audit-toolkit":
            sys.exit(handle_backtest_audit_toolkit(args))
        elif args.backtest_command == "metadata-smoke":
            sys.exit(handle_backtest_metadata_smoke(args))
        elif args.backtest_command == "mark-price-smoke":
            sys.exit(handle_backtest_mark_price_smoke(args))
        elif args.backtest_command == "structure-smoke":
            sys.exit(handle_backtest_structure_smoke(args))
        elif args.backtest_command == "math-parity":
            sys.exit(handle_backtest_math_parity(args))
        elif args.backtest_command == "audit-snapshot-plumbing":
            sys.exit(handle_backtest_audit_snapshot_plumbing(args))
        elif args.backtest_command == "verify-determinism":
            sys.exit(handle_backtest_verify_determinism(args))
        elif args.backtest_command == "metrics-audit":
            sys.exit(handle_backtest_metrics_audit(args))
        elif args.backtest_command == "audit-rollup":
            sys.exit(handle_backtest_audit_rollup(args))
        else:
            console.print("[yellow]Usage: trade_cli.py backtest {run|preflight|indicators|data-fix|list|play-normalize|play-normalize-batch|verify-suite|audit-toolkit|metadata-smoke|mark-price-smoke|structure-smoke|math-parity|audit-snapshot-plumbing|verify-determinism|metrics-audit|audit-rollup} --help[/]")
            sys.exit(1)

    # ===== VIZ SUBCOMMANDS =====
    # Handle `viz serve/open` subcommands
    if args.command == "viz":
        if args.viz_command == "serve":
            sys.exit(handle_viz_serve(args))
        elif args.viz_command == "open":
            sys.exit(handle_viz_open(args))
        else:
            console.print("[yellow]Usage: trade_cli.py viz {serve|open} --help[/]")
            sys.exit(1)

    # ===== SMOKE TEST MODE =====
    # Non-interactive smoke tests - run and exit with status code
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
            elif args.smoke == "forge":
                # Forge plumbing and verification smoke test
                from src.cli.smoke_tests import run_forge_smoke
                exit_code = run_forge_smoke()
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
