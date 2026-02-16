"""
Custom sync sub-menu for Data Builder.

Handles individual sync operations:
- Sync OHLCV by Period
- Sync OHLCV by Date Range
- Sync Funding Rates
- Sync Open Interest
"""

from datetime import datetime
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

from src.cli.styles import CLIStyles, CLIColors, CLIIcons, BillArtWrapper
from src.config.constants import DataEnv
from src.tools import (
    sync_symbols_tool,
    sync_range_tool,
    sync_funding_tool,
    sync_open_interest_tool,
)

if TYPE_CHECKING:
    from trade_cli import TradeCLI

# Local console
console = Console()


def data_sync_menu(cli: "TradeCLI", data_env: DataEnv) -> None:
    """Custom sync sub-menu for individual data operations."""
    from src.cli.utils import (
        clear_screen, print_header, get_input, get_choice, BACK,
        print_error_below_menu, run_long_action, print_data_result,
        get_symbols_input,
    )

    while True:
        clear_screen()
        print_header()

        # Sub-menu header
        status_line = Text()
        status_line.append("Custom Sync ", style=f"bold {CLIColors.NEON_CYAN}")
        status_line.append(f"({data_env.upper()}) ", style=f"bold {CLIColors.NEON_GREEN if data_env == 'live' else CLIColors.NEON_CYAN}")
        status_line.append("| ", style=CLIColors.DIM_TEXT)
        status_line.append("Individual OHLCV, Funding, OI sync", style=CLIColors.DIM_TEXT)
        console.print(Panel(status_line, border_style=f"dim {CLIColors.NEON_CYAN}"))

        menu = CLIStyles.create_menu_table()

        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.NETWORK} OHLCV ---[/]", "")
        menu.add_row("1", "Sync OHLCV by Period", "Sync candles for a time period (1D, 1M, etc.)")
        menu.add_row("2", "Sync OHLCV by Date Range", "Sync candles for specific date range")
        menu.add_row("", "", "")
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.LEDGER} Supplemental ---[/]", "")
        menu.add_row("3", "Sync Funding Rates", "Sync funding rate history")
        menu.add_row("4", "Sync Open Interest", "Sync open interest history")
        menu.add_row("", "", "")
        menu.add_row("5", f"{CLIIcons.BACK} Back", "Return to data menu")

        BillArtWrapper.print_menu_top()
        console.print(CLIStyles.get_menu_panel(menu, f"CUSTOM SYNC ({data_env.upper()})"))
        BillArtWrapper.print_menu_bottom()

        choice = get_choice(valid_range=range(1, 6))
        if choice is BACK:
            return

        if choice == 1:
            # Sync OHLCV by Period
            symbols = get_symbols_input("Symbol(s)")
            if symbols is BACK:
                continue
            period = get_input("Period (1D, 1W, 1M, 3M, 6M, 1Y)", "1M")
            if period is BACK:
                continue
            assert isinstance(period, str)
            timeframes_input = get_input("Timeframes (comma-separated, blank for all)", "")
            if timeframes_input is BACK:
                continue
            assert isinstance(timeframes_input, str)
            timeframes = [t.strip() for t in timeframes_input.split(",")] if timeframes_input else None

            result = run_long_action(
                "data.sync_ohlcv_period", sync_symbols_tool,
                symbols, period=period, timeframes=timeframes, env=data_env
            )
            print_data_result("data.sync_ohlcv_period", result)
            Prompt.ask("\nPress Enter to continue")

        elif choice == 2:
            # Sync OHLCV by Date Range
            symbols = get_symbols_input("Symbol(s)")
            if symbols is BACK:
                continue
            start_str = get_input("Start Date (YYYY-MM-DD)")
            if start_str is BACK:
                continue
            assert isinstance(start_str, str)
            end_str = get_input("End Date (YYYY-MM-DD)", datetime.now().strftime("%Y-%m-%d"))
            if end_str is BACK:
                continue
            assert isinstance(end_str, str)
            timeframes_input = get_input("Timeframes (comma-separated, blank for all)", "")
            if timeframes_input is BACK:
                continue
            assert isinstance(timeframes_input, str)
            timeframes = [t.strip() for t in timeframes_input.split(",")] if timeframes_input else None

            try:
                start_dt = datetime.strptime(start_str, "%Y-%m-%d")
                end_dt = datetime.strptime(end_str, "%Y-%m-%d")
            except ValueError:
                print_error_below_menu("Invalid date format. Use YYYY-MM-DD.")
                Prompt.ask("\nPress Enter to continue")
                continue

            result = run_long_action(
                "data.sync_ohlcv_range", sync_range_tool,
                symbols, start=start_dt, end=end_dt, timeframes=timeframes, env=data_env
            )
            print_data_result("data.sync_ohlcv_range", result)
            Prompt.ask("\nPress Enter to continue")

        elif choice == 3:
            # Sync Funding Rates
            symbols = get_symbols_input("Symbol(s)")
            if symbols is BACK:
                continue
            period = get_input("Period (1M, 3M, 6M, 1Y)", "3M")

            result = run_long_action(
                "data.sync_funding", sync_funding_tool,
                symbols, period=period, env=data_env
            )
            print_data_result("data.sync_funding", result)
            Prompt.ask("\nPress Enter to continue")

        elif choice == 4:
            # Sync Open Interest
            symbols = get_symbols_input("Symbol(s)")
            if symbols is BACK:
                continue
            period = get_input("Period (1D, 1W, 1M, 3M)", "1M")
            interval = get_input("Interval (5min, 15min, 30min, 1h, 4h, D)", "1h")

            result = run_long_action(
                "data.sync_open_interest", sync_open_interest_tool,
                symbols, period=period, interval=interval, env=data_env
            )
            print_data_result("data.sync_open_interest", result)
            Prompt.ask("\nPress Enter to continue")

        elif choice == 5:
            return
