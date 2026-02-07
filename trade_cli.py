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

Non-interactive smoke test modes:
  python trade_cli.py --smoke data            # Data builder smoke test only
  python trade_cli.py --smoke full            # Full CLI smoke test (data + trading + diagnostics)
  python trade_cli.py --smoke data_extensive  # Extensive data test (clean DB, gaps, fill, sync)
  python trade_cli.py --smoke backtest        # Backtest engine smoke test
  python trade_cli.py --smoke backtest --fresh-db  # Backtest with fresh DB

Debug mode (hash-traced logging):
  python trade_cli.py --debug                 # Enable debug logging for interactive mode
  python trade_cli.py --debug backtest run --play V_100  # Debug a specific backtest
"""

import os
import sys

# Rich imports (only what's still used directly in this file)
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.align import Align

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

# Subcommand handlers (extracted to src/cli/subcommands.py)
from src.cli.subcommands import (
    handle_backtest_run,
    handle_backtest_preflight,
    handle_backtest_indicators,
    handle_backtest_data_fix,
    handle_backtest_list,
    handle_backtest_normalize,
    handle_backtest_normalize_batch,
    handle_backtest_verify_suite,
    handle_backtest_audit_toolkit,
    handle_backtest_audit_incremental_parity,
    handle_backtest_audit_structure_parity,
    handle_backtest_metadata_smoke,
    handle_backtest_mark_price_smoke,
    handle_backtest_structure_smoke,
    handle_backtest_math_parity,
    handle_backtest_audit_snapshot_plumbing,
    handle_backtest_verify_determinism,
    handle_backtest_metrics_audit,
    handle_backtest_audit_rollup,
    handle_viz_serve,
    handle_viz_open,
    handle_play_run,
    handle_play_status,
    handle_play_stop,
    handle_qa_audit,
    handle_test_indicators,
    handle_test_parity,
    handle_test_live_parity,
    handle_test_agent,
)

# Argparse setup (extracted to src/cli/argparser.py)
from src.cli.argparser import setup_argparse


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
            console.print(f"[{tip_color}]Tip: Type 'back' or 'b' at any prompt to cancel and return to previous menu[/]")

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

    # ==================== MENU DELEGATES ====================

    def account_menu(self):
        """Account menu. Delegates to src.cli.menus.account_menu."""
        account_menu_handler(self)

    def positions_menu(self):
        """Positions menu. Delegates to src.cli.menus.positions_menu."""
        positions_menu_handler(self)

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

    def market_data_menu(self):
        """Market data menu. Delegates to src.cli.menus.market_data_menu."""
        market_data_menu_handler(self)

    def data_menu(self):
        """Historical data builder menu (DuckDB-only). Delegates to src.cli.menus.data_menu."""
        data_menu_handler(self)

    def backtest_menu(self):
        """Backtest engine menu. Delegates to src.cli.menus.backtest_menu."""
        backtest_menu_handler(self)

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
                    "V" if trading["key_configured"] else "X"
                )
                env_table.add_row(
                    "Data REST",
                    f"[green]{data_api['mode']}[/]",
                    data_api["base_url"],
                    "V" if data_api["key_configured"] else "Warning: public"
                )
                env_table.add_row(
                    "WebSocket",
                    f"[{trading_style}]{ws['mode']}[/]",
                    ws["public_url"],
                    "V enabled" if ws.get("enabled") else "- disabled"
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
                    "V" if trading["key_configured"] else "X"
                )
                env_table.add_row(
                    "Data REST",
                    f"[green]{data_api['mode']}[/]",
                    data_api["base_url"],
                    "V" if data_api["key_configured"] else "Warning: public"
                )
                env_table.add_row(
                    "WebSocket",
                    f"[{trading_style}]{ws['mode']}[/]",
                    ws["public_url"],
                    "V enabled" if ws.get("enabled") else "- disabled"
                )
                console.print(env_table)

                # Safety check
                if safety["mode_consistent"]:
                    console.print("[green]V Mode consistency: OK[/]")
                else:
                    console.print("[yellow]Warning: Mode consistency warnings:[/]")
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
                "[bold red]PANIC MODE[/]\n\n"
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
# STARTUP HELPERS
# =============================================================================

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
        f"[bold {BillArtColors.GREEN_BRIGHT}]DEMO (Paper)[/]",
        f"[{BillArtColors.GREEN_MONEY}]Demo account (fake funds) - api-demo.bybit.com[/]"
    )
    options.add_row(
        "2",
        f"[bold {BillArtColors.GOLD_BRIGHT}]LIVE (Real)[/]",
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
        console.print("\n[bold green]DEMO (Paper) mode selected[/]")
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
            f"[bold {BillArtColors.GOLD_BRIGHT}]WARNING: LIVE TRADING MODE[/]\n\n"
            f"[{BillArtColors.GOLD_BRIGHT}]You are about to trade with REAL MONEY![/]\n\n"
            f"This session will:\n"
            f"  - Use [bold]api.bybit.com[/] (LIVE API)\n"
            f"  - Execute orders with [bold {BillArtColors.GOLD_BRIGHT}]REAL FUNDS[/]\n"
            f"  - Affect your [bold {BillArtColors.GOLD_BRIGHT}]REAL ACCOUNT BALANCE[/]"
        ),
        border_style=BillArtColors.GOLD_BRIGHT,
        title=f"[bold {BillArtColors.GOLD_BRIGHT}]LIVE MODE[/]",
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

    console.print(Panel(risk_table, title=f"[bold {BillArtColors.GOLD_BRIGHT}]Current Risk Limits[/]", border_style=BillArtColors.GOLD_DARK))

    # First confirmation
    console.print("\n[bold]First confirmation:[/]")
    confirm1 = Confirm.ask("[yellow]Do you understand that this will use REAL MONEY?[/]", default=False)

    if not confirm1:
        console.print("\n[green]Cancelled - using DEMO (Paper) mode[/]")
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
        console.print("\n[bold red]LIVE (Real) MODE ACTIVATED[/]")
        console.print("[red]Trading on Bybit live account (REAL FUNDS, real API orders)[/]")
        console.print("[dim]REST: api.bybit.com | WebSocket: stream.bybit.com[/]")
        Prompt.ask("\n[dim]Press Enter to continue in LIVE mode[/]")
        return True
    else:
        console.print("\n[green]LIVE mode cancelled - using DEMO (Paper) mode[/]")
        config.bybit.use_demo = True
        config.trading.mode = "paper"
        Prompt.ask("\n[dim]Press Enter to continue in DEMO mode[/]")
        return True


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def main():
    """
    Main entry point for trade_cli.

    Handles two modes:
    - Interactive: No args -> main menu loop
    - Non-interactive: --smoke or backtest subcommand -> run and exit
    """
    # Parse CLI arguments FIRST (before any config or logging)
    args = setup_argparse()

    # Enable debug mode if --debug flag is set
    if getattr(args, "debug", False):
        from src.utils.debug import enable_debug
        enable_debug(True)
        import os as _os
        _os.environ["TRADE_DEBUG"] = "1"

    # Setup logging
    setup_logger()

    # ===== BACKTEST SUBCOMMANDS =====
    if args.command == "backtest":
        config = get_config()

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
        elif args.backtest_command == "audit-incremental-parity":
            sys.exit(handle_backtest_audit_incremental_parity(args))
        elif args.backtest_command == "audit-structure-parity":
            sys.exit(handle_backtest_audit_structure_parity(args))
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
            console.print("[yellow]Usage: trade_cli.py backtest {run|preflight|indicators|data-fix|list|play-normalize|play-normalize-batch|verify-suite|audit-toolkit|audit-incremental-parity|audit-structure-parity|metadata-smoke|mark-price-smoke|structure-smoke|math-parity|audit-snapshot-plumbing|verify-determinism|metrics-audit|audit-rollup} --help[/]")
            sys.exit(1)

    # ===== VIZ SUBCOMMANDS =====
    if args.command == "viz":
        if args.viz_command == "serve":
            sys.exit(handle_viz_serve(args))
        elif args.viz_command == "open":
            sys.exit(handle_viz_open(args))
        else:
            console.print("[yellow]Usage: trade_cli.py viz {serve|open} --help[/]")
            sys.exit(1)

    # ===== PLAY SUBCOMMANDS =====
    if args.command == "play":
        if args.play_command == "run":
            sys.exit(handle_play_run(args))
        elif args.play_command == "status":
            sys.exit(handle_play_status(args))
        elif args.play_command == "stop":
            sys.exit(handle_play_stop(args))
        else:
            console.print("[yellow]Usage: trade_cli.py play {run|status|stop} --help[/]")
            sys.exit(1)

    # ===== QA SUBCOMMANDS =====
    if args.command == "qa":
        if args.qa_command == "audit":
            sys.exit(handle_qa_audit(args))
        else:
            console.print("[yellow]Usage: trade_cli.py qa {audit} --help[/]")
            sys.exit(1)

    # ===== TEST SUBCOMMANDS =====
    if args.command == "test":
        if args.test_command == "indicators":
            sys.exit(handle_test_indicators(args))
        elif args.test_command == "parity":
            sys.exit(handle_test_parity(args))
        elif args.test_command == "live-parity":
            sys.exit(handle_test_live_parity(args))
        elif args.test_command == "agent":
            sys.exit(handle_test_agent(args))
        else:
            console.print("[yellow]Usage: trade_cli.py test {indicators|parity|live-parity|agent} --help[/]")
            sys.exit(1)

    # ===== SMOKE TEST MODE =====
    if args.smoke:
        config = get_config()

        # Special case: live_check uses LIVE credentials (opt-in, dangerous)
        if args.smoke == "live_check":
            console.print(Panel(
                "[bold red]LIVE CHECK SMOKE TEST[/]\n"
                "[red]This test uses LIVE API credentials (REAL MONEY account)[/]\n"
                "[dim]Testing connectivity, balance, and limited order placement[/]",
                border_style="red"
            ))
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
                exit_code = run_extensive_data_smoke()
            elif args.smoke == "orders":
                exit_code = run_comprehensive_order_smoke()
            elif args.smoke == "live_check":
                from src.cli.smoke_tests import run_live_check_smoke
                exit_code = run_live_check_smoke()
            elif args.smoke == "backtest":
                from src.cli.smoke_tests import run_backtest_smoke
                exit_code = run_backtest_smoke(fresh_db=args.fresh_db)
            elif args.smoke == "forge":
                from src.cli.smoke_tests import run_forge_smoke
                exit_code = run_forge_smoke()
            elif args.smoke == "qa":
                from src.cli.smoke_tests import run_qa_audit_smoke
                exit_code = run_qa_audit_smoke()
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
    if not select_trading_environment():
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
