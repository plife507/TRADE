"""
Database info sub-menu for Data Builder.

Handles database inspection operations:
- Database Stats
- List Cached Symbols
- Symbol Aggregate Status
- Symbol Summary (Overview)
- Symbol Timeframe Ranges
"""

from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

from src.cli.styles import CLIStyles, CLIColors, CLIIcons, BillArtWrapper
from src.config.constants import DataEnv
from src.tools import (
    get_database_stats_tool,
    list_cached_symbols_tool,
    get_symbol_status_tool,
    get_symbol_summary_tool,
    get_symbol_timeframe_ranges_tool,
)

if TYPE_CHECKING:
    from trade_cli import TradeCLI

# Local console
console = Console()


def data_info_menu(cli: "TradeCLI", data_env: DataEnv) -> None:
    """Database info sub-menu."""
    from src.cli.utils import (
        clear_screen, print_header, get_choice, BACK,
        run_tool_action, print_data_result,
        get_symbol_input,
    )

    while True:
        clear_screen()
        print_header()

        # Sub-menu header
        status_line = Text()
        status_line.append("Database Info ", style=f"bold {CLIColors.NEON_CYAN}")
        status_line.append(f"({data_env.upper()}) ", style=f"bold {CLIColors.NEON_GREEN if data_env == 'live' else CLIColors.NEON_CYAN}")
        status_line.append("| ", style=CLIColors.DIM_TEXT)
        status_line.append("Stats, symbols, coverage", style=CLIColors.DIM_TEXT)
        console.print(Panel(status_line, border_style=f"dim {CLIColors.NEON_CYAN}"))

        menu = CLIStyles.create_menu_table()

        menu.add_row("1", "Database Stats", "Database size, symbol count, total candles")
        menu.add_row("2", "List Cached Symbols", "All symbols with data in database")
        menu.add_row("3", "Symbol Aggregate Status", "Per-symbol totals (candles, gaps, timeframes)")
        menu.add_row("4", "Symbol Summary (Overview)", "High-level summary per symbol")
        menu.add_row("5", "Symbol Timeframe Ranges", "Detailed per-symbol/timeframe date ranges")
        menu.add_row("", "", "")
        menu.add_row("6", f"{CLIIcons.BACK} Back", "Return to data menu")

        BillArtWrapper.print_menu_top()
        console.print(CLIStyles.get_menu_panel(menu, f"DATABASE INFO ({data_env.upper()})"))
        BillArtWrapper.print_menu_bottom()

        choice = get_choice(valid_range=range(1, 7))
        if choice is BACK:
            return

        if choice == 1:
            # Database Stats
            result = run_tool_action("data.stats", get_database_stats_tool, env=data_env)
            print_data_result("data.stats", result)
            Prompt.ask("\nPress Enter to continue")

        elif choice == 2:
            # List Cached Symbols
            result = run_tool_action("data.list_symbols", list_cached_symbols_tool, env=data_env)
            print_data_result("data.list_symbols", result)
            Prompt.ask("\nPress Enter to continue")

        elif choice == 3:
            # Symbol Aggregate Status
            symbol = get_symbol_input("Symbol (blank for all)")
            result = run_tool_action("data.symbol_status", get_symbol_status_tool, symbol if symbol else None, env=data_env)
            print_data_result("data.symbol_status", result)
            Prompt.ask("\nPress Enter to continue")

        elif choice == 4:
            # Symbol Summary (Overview)
            result = run_tool_action("data.symbol_summary", get_symbol_summary_tool, env=data_env)
            print_data_result("data.symbol_summary", result)
            Prompt.ask("\nPress Enter to continue")

        elif choice == 5:
            # Symbol Timeframe Ranges (Detailed)
            symbol = get_symbol_input("Symbol (blank for all)")
            result = run_tool_action("data.timeframe_ranges", get_symbol_timeframe_ranges_tool, symbol if symbol else None, env=data_env)
            print_data_result("data.timeframe_ranges", result)
            Prompt.ask("\nPress Enter to continue")

        elif choice == 6:
            return
