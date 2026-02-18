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

Subcommands:
  python trade_cli.py validate quick|standard|full|pre-live|exchange
  python trade_cli.py backtest run --play X
  python trade_cli.py debug math-parity|snapshot-plumbing|determinism|metrics
  python trade_cli.py play run --play X --mode demo

Debug mode (hash-traced logging):
  python trade_cli.py --debug                 # Enable debug logging for interactive mode
  python trade_cli.py --debug backtest run --play V_100  # Debug a specific backtest
"""

import os
import sys

# Windows: force UTF-8 for Rich Unicode art (bill art, icons, etc.)
if sys.platform == "win32":
    import io
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    if isinstance(sys.stderr, io.TextIOWrapper):
        sys.stderr.reconfigure(encoding="utf-8")

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
from src.cli.menus import (
    data_menu as data_menu_handler,
    market_data_menu as market_data_menu_handler,
    orders_menu as orders_menu_handler,
    positions_menu as positions_menu_handler,
    account_menu as account_menu_handler,
    backtest_menu as backtest_menu_handler,
    forge_menu as forge_menu_handler,
    plays_menu as plays_menu_handler,
)
from src.cli.styles import CLIStyles, CLIColors, CLIIcons, BillArtWrapper, BillArtColors
# Import shared CLI utilities (canonical implementations)
from src.cli.utils import (
    console,
    BACK,
    clear_screen,
    print_header,
    get_input,
    get_choice,
    print_error_below_menu,
    run_tool_action,
    print_data_result,
    get_symbol_input,
    get_running_plays_summary,
)
from src.tools import (
    panic_close_all_tool,
    # Diagnostics tools (used in connection_test and health_check)
    test_connection_tool,
    get_server_time_offset_tool,
    get_rate_limit_status_tool,
    get_ticker_tool,
    get_websocket_status_tool,
    exchange_health_check_tool,
    get_api_environment_tool,
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
    handle_debug_math_parity,
    handle_debug_snapshot_plumbing,
    handle_debug_determinism,
    handle_debug_metrics,
    handle_play_run,
    handle_play_status,
    handle_play_stop,
    handle_account_balance,
    handle_account_exposure,
    handle_position_list,
    handle_position_close,
    handle_panic,
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
        self._connected: bool = False
        self._app: Application | None = None

    # ==================== CONNECTION MANAGEMENT ====================

    def connect_to_exchange(self) -> bool:
        """
        Interactive exchange connection flow.

        Shows DEMO/LIVE selection, double-confirms LIVE mode,
        initializes and starts the Application.

        Returns:
            True on successful connection, False on cancel/failure.
        """
        # If already connected, stop existing connection first
        if self._connected and self._app:
            self._app.stop()
            self._connected = False
            self._app = None

        config = self.config

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
        options.add_row("", "", "")
        options.add_row(
            "q",
            f"[{BillArtColors.GREEN_MONEY}]Cancel[/]",
            f"[{BillArtColors.GOLD_DARK}]Return to main menu[/]"
        )

        # Use art-styled menu panel
        console.print(CLIStyles.get_menu_panel(options, "SELECT ENVIRONMENT", is_main=True))

        # Default suggestion based on config file
        default_choice = "1" if file_is_demo else "2"
        choice = Prompt.ask(
            "\n[cyan]Enter choice[/]",
            choices=["1", "2", "q", "Q"],
            default=default_choice
        )

        if choice.lower() == "q":
            return False

        if choice == "1":
            # DEMO/PAPER mode - demo account with fake funds
            config.bybit.use_demo = True
            config.trading.mode = "paper"
            console.print("\n[bold green]DEMO (Paper) mode selected[/]")
            console.print("[dim]Trading on Bybit demo account (fake funds, real API orders)[/]")
            console.print("[dim]REST: api-demo.bybit.com | WebSocket: stream-demo.bybit.com[/]")
            console.print("[dim]Data operations use LIVE API for accuracy[/]")
        elif choice == "2":
            # LIVE mode - requires double confirmation
            if not self._confirm_live_mode():
                return self._connected  # May have fallen back to DEMO
        else:
            return False

        # Initialize application lifecycle
        return self._start_application()

    def _confirm_live_mode(self) -> bool:
        """
        Double confirmation for LIVE trading mode.

        Returns:
            True if user confirmed (LIVE or fell back to DEMO), False to cancel entirely.
        """
        config = self.config
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
            return self._start_application()

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
            return self._start_application()
        else:
            console.print("\n[green]LIVE mode cancelled - using DEMO (Paper) mode[/]")
            config.bybit.use_demo = True
            config.trading.mode = "paper"
            Prompt.ask("\n[dim]Press Enter to continue in DEMO mode[/]")
            return self._start_application()

    def _start_application(self) -> bool:
        """Initialize and start the Application. Sets self._connected on success."""
        app = get_application()

        if not app.initialize():
            console.print("\n[bold red]Application initialization failed![/]")
            error = app.get_status().error
            if error:
                print_error_below_menu(str(error))
            Prompt.ask("\nPress Enter to continue")
            return False

        # Start application (including WebSocket if enabled)
        if not app.start():
            console.print("\n[bold yellow]Warning: Application start had issues[/]")
            console.print("[yellow]Continuing with REST API fallback...[/]")

        # Show WebSocket status
        status = app.get_status()
        if status.websocket_connected:
            console.print(f"[green]WebSocket connected[/] [dim](public: {status.websocket_public}, private: {status.websocket_private})[/]")
        elif app.config.websocket.enable_websocket and app.config.websocket.auto_start:
            console.print("[yellow]WebSocket not connected - using REST API[/]")

        Prompt.ask("\n[dim]Press Enter to continue[/]")

        self._app = app
        self._connected = True
        return True

    def _ensure_connected(self) -> bool:
        """Guard for exchange-dependent menu items."""
        if self._connected:
            return True
        console.print("\n[yellow]Not connected to exchange. Use 'Connect to Exchange' first.[/]")
        Prompt.ask("\nPress Enter to continue")
        return False

    def shutdown(self):
        """Graceful shutdown - stop the application if connected."""
        if self._app:
            self._app.stop()

    # ==================== MAIN MENU ====================

    def main_menu(self):
        """Display main menu with $100 bill art styling. Two states: disconnected / connected."""
        while True:
            clear_screen()
            print_header(connected=self._connected)

            if self._connected:
                exited = self._main_menu_connected()
            else:
                exited = self._main_menu_disconnected()

            if exited:
                break

    def _main_menu_disconnected(self) -> bool:
        """
        Disconnected main menu (7 items).

        Returns True if user chose Exit.
        """
        # Print decorative menu top border
        BillArtWrapper.print_menu_top()

        menu = CLIStyles.create_menu_table()

        menu.add_row("", "[bold dim]--- Offline ---[/]", "")
        menu.add_row("1", f"{CLIIcons.MINING} Data Builder", "Build & manage historical data (DuckDB)")
        menu.add_row("2", f"{CLIIcons.TARGET} Backtest Engine", "Run strategy backtests, manage systems")
        menu.add_row("3", f"{CLIIcons.FIRE} The Forge", "Play development, validation, audits")
        menu.add_row("4", f"{CLIIcons.SETTINGS} Validate", "Run validation suite (quick)")
        menu.add_row("", "[bold dim]--- Exchange ---[/]", "")
        menu.add_row("5", f"{CLIIcons.NETWORK} Connect to Exchange", "Select DEMO/LIVE and connect")
        menu.add_row("", "[bold dim]--- System ---[/]", "")
        menu.add_row("6", f"{CLIIcons.SETTINGS} Health Check", "Comprehensive system health diagnostic")
        menu.add_row("7", f"{CLIIcons.QUIT} Exit", "Exit the CLI")

        console.print(CLIStyles.get_menu_panel(menu, "MAIN MENU", is_main=True))

        # Print decorative menu bottom border
        BillArtWrapper.print_menu_bottom()

        # Themed tip text
        tip_color = BillArtColors.GREEN_MONEY if CLIStyles.use_art_wrapper else CLIColors.DIM_TEXT
        console.print(f"[{tip_color}]Tip: Type 'back' or 'b' at any prompt to cancel and return to previous menu[/]")

        choice = get_choice(valid_range=range(1, 8))

        if choice is BACK:
            return True

        try:
            if choice == 1:
                self.data_menu()
            elif choice == 2:
                self.backtest_menu()
            elif choice == 3:
                self.forge_menu()
            elif choice == 4:
                self.validate_quick()
            elif choice == 5:
                self.connect_to_exchange()
            elif choice == 6:
                self.health_check()
            elif choice == 7:
                return True
        except KeyboardInterrupt:
            console.print("\n[yellow]Operation cancelled. Returning to main menu...[/]")
            Prompt.ask("\nPress Enter to continue")
        except Exception as e:
            print_error_below_menu(
                f"An error occurred: {e}",
                "The operation failed but you can try again or select another option."
            )
            Prompt.ask("\nPress Enter to continue")

        return False

    def _main_menu_connected(self) -> bool:
        """
        Connected main menu (11 items for DEMO, 12 for LIVE).

        Returns True if user chose Exit.
        """
        is_demo = self.config.bybit.use_demo
        mode_label = "DEMO" if is_demo else "LIVE"
        mode_color = "green" if is_demo else "red"

        # Print decorative menu top border
        BillArtWrapper.print_menu_top()

        # Show running plays in header area
        plays_summary = get_running_plays_summary()
        if plays_summary:
            console.print(f"  [dim]Running:[/] {plays_summary}")

        menu = CLIStyles.create_menu_table()

        gold = BillArtColors.GOLD_BRIGHT if CLIStyles.use_art_wrapper else CLIColors.NEON_YELLOW

        menu.add_row("", "[bold dim]--- Trading ---[/]", "")
        menu.add_row("1", f"{CLIIcons.WALLET} Account & Balance", "View balance, exposure, portfolio, transaction history")
        menu.add_row("2", f"{CLIIcons.CANDLE} Positions", "List, manage, close positions, set TP/SL, trailing stops")
        menu.add_row("3", f"{CLIIcons.TRADE} Orders", "Place market/limit/stop orders, manage open orders")
        menu.add_row("4", f"{CLIIcons.CHART_UP} Market Data", "Get prices, OHLCV, funding rates, orderbook, instruments")
        menu.add_row("5", f"{CLIIcons.FIRE} Plays", "Run, monitor, stop plays (demo/live)")
        menu.add_row("", "[bold dim]--- Strategy ---[/]", "")
        menu.add_row("6", f"{CLIIcons.MINING} Data Builder", "Build & manage historical data (DuckDB)")
        menu.add_row("7", f"{CLIIcons.TARGET} Backtest Engine", "Run strategy backtests, manage systems")
        menu.add_row("8", f"{CLIIcons.FIRE} The Forge", "Play development, validation, audits")
        menu.add_row("", "[bold dim]--- System ---[/]", "")
        menu.add_row("9", f"{CLIIcons.NETWORK} Connection Test", "Test API connectivity and rate limits")
        menu.add_row("10", f"{CLIIcons.SETTINGS} Health Check", "Comprehensive system health diagnostic")
        menu.add_row("11", f"{CLIIcons.SETTINGS} Switch DEMO/LIVE", "Disconnect and reconnect to different environment")

        if not is_demo:
            menu.add_row("12", f"[bold {gold}]{CLIIcons.PANIC} PANIC: Close All & Stop[/]", f"[{gold}]Emergency: Close all positions & cancel orders[/]")
            menu.add_row("13", f"{CLIIcons.QUIT} Exit", "Exit the CLI")
            max_choice = 13
        else:
            menu.add_row("12", f"{CLIIcons.QUIT} Exit", "Exit the CLI")
            max_choice = 12

        title = f"MAIN MENU ([{mode_color}]{mode_label}[/])"
        console.print(CLIStyles.get_menu_panel(menu, title, is_main=True))

        # Print decorative menu bottom border
        BillArtWrapper.print_menu_bottom()

        # Themed tip text
        tip_color = BillArtColors.GREEN_MONEY if CLIStyles.use_art_wrapper else CLIColors.DIM_TEXT
        console.print(f"[{tip_color}]Tip: Type 'back' or 'b' at any prompt to cancel and return to previous menu[/]")

        choice = get_choice(valid_range=range(1, max_choice + 1))

        if choice is BACK:
            return True

        try:
            if choice == 1:
                if self._ensure_connected():
                    self.account_menu()
            elif choice == 2:
                if self._ensure_connected():
                    self.positions_menu()
            elif choice == 3:
                if self._ensure_connected():
                    self.orders_menu()
            elif choice == 4:
                if self._ensure_connected():
                    self.market_data_menu()
            elif choice == 5:
                if self._ensure_connected():
                    self.plays_menu()
            elif choice == 6:
                self.data_menu()
            elif choice == 7:
                self.backtest_menu()
            elif choice == 8:
                self.forge_menu()
            elif choice == 9:
                self.connection_test()
            elif choice == 10:
                self.health_check()
            elif choice == 11:
                self.connect_to_exchange()  # Handles disconnect + reconnect
            elif not is_demo and choice == 12:
                self.panic_menu()
            elif (not is_demo and choice == 13) or (is_demo and choice == 12):
                return True
        except KeyboardInterrupt:
            console.print("\n[yellow]Operation cancelled. Returning to main menu...[/]")
            Prompt.ask("\nPress Enter to continue")
        except Exception as e:
            print_error_below_menu(
                f"An error occurred: {e}",
                "The operation failed but you can try again or select another option."
            )
            Prompt.ask("\nPress Enter to continue")

        return False

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

    def plays_menu(self):
        """Plays lifecycle menu - run, monitor, stop plays. Delegates to src.cli.menus.plays_menu."""
        plays_menu_handler(self)

    # ==================== VALIDATE (QUICK) ====================

    def validate_quick(self):
        """Run quick validation suite."""
        clear_screen()
        print_header()

        try:
            from src.cli.validate import run_validation, Tier
            console.print(Panel("Running Quick Validation...", title="[bold]VALIDATE[/]", border_style="blue"))
            run_validation(tier=Tier.QUICK, fail_fast=True)
        except KeyboardInterrupt:
            console.print("\n[yellow]Validation cancelled.[/]")
        except Exception as e:
            print_error_below_menu(f"Validation failed: {e}")

        Prompt.ask("\nPress Enter to continue")

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
            if api_result.success and api_result.data is not None:
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
            symbol = get_symbol_input("Test ticker for symbol")
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
            if api_result.success and api_result.data is not None:
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

            symbol = get_symbol_input("Symbol to test")
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
# MAIN ENTRY POINT
# =============================================================================

def main():
    """
    Main entry point for trade_cli.

    Handles two modes:
    - Interactive: No args -> main menu loop (NO connection at startup)
    - Non-interactive: subcommand (backtest, debug, validate, play, etc.) -> run and exit
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
        else:
            console.print("[yellow]Usage: trade_cli.py backtest {run|preflight|indicators|data-fix|list|play-normalize|play-normalize-batch} --help[/]")
            sys.exit(1)

    # ===== DEBUG SUBCOMMANDS =====
    if args.command == "debug":
        if args.debug_command == "math-parity":
            sys.exit(handle_debug_math_parity(args))
        elif args.debug_command == "snapshot-plumbing":
            sys.exit(handle_debug_snapshot_plumbing(args))
        elif args.debug_command == "determinism":
            sys.exit(handle_debug_determinism(args))
        elif args.debug_command == "metrics":
            sys.exit(handle_debug_metrics(args))
        else:
            console.print("[yellow]Usage: trade_cli.py debug {math-parity|snapshot-plumbing|determinism|metrics} --help[/]")
            sys.exit(1)

    # ===== PLAY SUBCOMMANDS =====
    if args.command == "play":
        if args.play_command == "run":
            sys.exit(handle_play_run(args))
        elif args.play_command == "status":
            sys.exit(handle_play_status(args))
        elif args.play_command == "stop":
            sys.exit(handle_play_stop(args))
        elif args.play_command == "watch":
            from src.cli.subcommands import handle_play_watch
            sys.exit(handle_play_watch(args))
        elif args.play_command == "logs":
            from src.cli.subcommands import handle_play_logs
            sys.exit(handle_play_logs(args))
        elif args.play_command == "pause":
            from src.cli.subcommands import handle_play_pause
            sys.exit(handle_play_pause(args))
        elif args.play_command == "resume":
            from src.cli.subcommands import handle_play_resume
            sys.exit(handle_play_resume(args))
        else:
            console.print("[yellow]Usage: trade_cli.py play {run|status|stop|watch|logs|pause|resume} --help[/]")
            sys.exit(1)

    # ===== VALIDATE SUBCOMMAND =====
    if args.command == "validate":
        from src.cli.validate import run_validation, Tier
        tier = Tier(args.tier)
        sys.exit(run_validation(
            tier=tier,
            play_id=getattr(args, "play", None),
            fail_fast=not getattr(args, "no_fail_fast", False),
            json_output=getattr(args, "json_output", False),
            max_workers=getattr(args, "workers", None),
            module_name=getattr(args, "module", None),
        ))

    # ===== ACCOUNT SUBCOMMANDS =====
    if args.command == "account":
        if args.account_command == "balance":
            sys.exit(handle_account_balance(args))
        elif args.account_command == "exposure":
            sys.exit(handle_account_exposure(args))
        else:
            console.print("[dim]Usage: account [balance|exposure][/]")
            sys.exit(1)

    # ===== POSITION SUBCOMMANDS =====
    if args.command == "position":
        if args.position_command == "list":
            sys.exit(handle_position_list(args))
        elif args.position_command == "close":
            sys.exit(handle_position_close(args))
        else:
            console.print("[dim]Usage: position [list|close][/]")
            sys.exit(1)

    # ===== PANIC SUBCOMMAND =====
    if args.command == "panic":
        sys.exit(handle_panic(args))

    # ===== INTERACTIVE MODE (default) - no connection at startup =====
    cli = TradeCLI()
    try:
        cli.main_menu()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted. Shutting down...[/]")
    except Exception as e:
        print_error_below_menu(str(e))
        raise
    finally:
        cli.shutdown()
        console.print("[dim]Goodbye![/]")

    # pybit WebSocket threads are non-daemon and may keep Python alive
    # after main() returns. Force exit to return to shell promptly.
    os._exit(0)


if __name__ == "__main__":
    main()
