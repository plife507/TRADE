"""
Data query sub-menu for Data Builder.

Handles data query operations:
- Query OHLCV
- Query Funding
- Query Open Interest
"""

from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

from src.cli.styles import CLIStyles, CLIColors, CLIIcons, BillArtWrapper
from src.config.constants import DataEnv
from src.tools import (
    get_ohlcv_history_tool,
    get_funding_history_tool,
    get_open_interest_history_tool,
)

if TYPE_CHECKING:
    from trade_cli import TradeCLI

# Local console
console = Console()


def data_query_menu(cli: "TradeCLI", data_env: DataEnv) -> None:
    """Data query sub-menu."""
    from src.cli.utils import (
        clear_screen, print_header, get_input, get_choice, BACK,
        print_error_below_menu, run_tool_action, print_data_result,
        get_symbol_input,
    )

    while True:
        clear_screen()
        print_header()

        # Sub-menu header
        status_line = Text()
        status_line.append("Query Data ", style=f"bold {CLIColors.NEON_MAGENTA}")
        status_line.append(f"({data_env.upper()}) ", style=f"bold {CLIColors.NEON_GREEN if data_env == 'live' else CLIColors.NEON_CYAN}")
        status_line.append("| ", style=CLIColors.DIM_TEXT)
        status_line.append("OHLCV, Funding, Open Interest queries", style=CLIColors.DIM_TEXT)
        console.print(Panel(status_line, border_style=f"dim {CLIColors.NEON_MAGENTA}"))

        menu = CLIStyles.create_menu_table()

        menu.add_row("1", f"[bold {CLIColors.NEON_MAGENTA}]Query OHLCV[/]", f"[{CLIColors.NEON_MAGENTA}]View cached candles (period or custom range)[/]")
        menu.add_row("2", f"[bold {CLIColors.NEON_MAGENTA}]Query Funding[/]", f"[{CLIColors.NEON_MAGENTA}]View cached funding rates[/]")
        menu.add_row("3", f"[bold {CLIColors.NEON_MAGENTA}]Query Open Interest[/]", f"[{CLIColors.NEON_MAGENTA}]View cached open interest[/]")
        menu.add_row("", "", "")
        menu.add_row("4", f"{CLIIcons.BACK} Back", "Return to data menu")

        BillArtWrapper.print_menu_top()
        console.print(CLIStyles.get_menu_panel(menu, f"QUERY DATA ({data_env.upper()})"))
        BillArtWrapper.print_menu_bottom()

        choice = get_choice(valid_range=range(1, 5))
        if choice is BACK:
            return

        if choice == 1:
            # Query OHLCV History
            symbol = get_symbol_input("Symbol")
            if symbol is BACK:
                continue
            assert isinstance(symbol, str)
            if not symbol:
                print_error_below_menu("Symbol is required")
                Prompt.ask("\nPress Enter to continue")
                continue

            timeframe = get_input("Timeframe (1m, 5m, 15m, 1h, 4h, D)", "1h")
            if timeframe is BACK:
                continue
            assert isinstance(timeframe, str)

            console.print("\n[bold cyan]Select data range:[/]")
            console.print("  1) Use period (e.g., 1M = last month)")
            console.print("  2) Custom date range")
            range_choice = get_input("Choice", "1")

            if range_choice == "2":
                start_str = get_input("Start date (YYYY-MM-DD)")
                if start_str is BACK:
                    continue
                end_str = get_input("End date (YYYY-MM-DD, blank for now)", "")
                if end_str is BACK:
                    continue

                result = run_tool_action(
                    "data.query_ohlcv", get_ohlcv_history_tool,
                    symbol=symbol.upper(), timeframe=timeframe,
                    start=start_str, end=end_str if end_str else None, env=data_env
                )
            else:
                period = get_input("Period (1D, 1W, 1M, 3M, 6M)", "1M")
                if period is BACK:
                    continue
                result = run_tool_action(
                    "data.query_ohlcv", get_ohlcv_history_tool,
                    symbol=symbol.upper(), timeframe=timeframe, period=period, env=data_env
                )

            # Show summary for large results
            if result.success and result.data:
                count = result.data.get("count", 0)
                if count > 20:
                    console.print(f"\n[dim]Showing summary ({count:,} candles total)[/]")
                    tr = result.data.get("time_range", {})
                    console.print(f"[dim]Range: {tr.get('first_candle', 'N/A')} to {tr.get('last_candle', 'N/A')}[/]")
                    console.print(f"\n[green]  {result.message}[/]")
                else:
                    print_data_result("data.query_ohlcv", result)
            else:
                print_data_result("data.query_ohlcv", result)
            Prompt.ask("\nPress Enter to continue")

        elif choice == 2:
            # Query Funding History
            symbol = get_symbol_input("Symbol")
            if symbol is BACK:
                continue
            assert isinstance(symbol, str)
            if not symbol:
                print_error_below_menu("Symbol is required")
                Prompt.ask("\nPress Enter to continue")
                continue

            console.print("\n[bold cyan]Select data range:[/]")
            console.print("  1) Use period (e.g., 1M = last month)")
            console.print("  2) Custom date range")
            range_choice = get_input("Choice", "1")

            if range_choice == "2":
                start_str = get_input("Start date (YYYY-MM-DD)")
                if start_str is BACK:
                    continue
                end_str = get_input("End date (YYYY-MM-DD, blank for now)", "")
                if end_str is BACK:
                    continue

                result = run_tool_action(
                    "data.query_funding", get_funding_history_tool,
                    symbol=symbol.upper(),
                    start=start_str, end=end_str if end_str else None, env=data_env
                )
            else:
                period = get_input("Period (1M, 3M, 6M, 1Y)", "1M")
                if period is BACK:
                    continue
                result = run_tool_action(
                    "data.query_funding", get_funding_history_tool,
                    symbol=symbol.upper(), period=period, env=data_env
                )

            # Show summary for large results
            if result.success and result.data:
                count = result.data.get("count", 0)
                if count > 20:
                    console.print(f"\n[dim]Showing summary ({count:,} records total)[/]")
                    tr = result.data.get("time_range", {})
                    console.print(f"[dim]Range: {tr.get('first_record', 'N/A')} to {tr.get('last_record', 'N/A')}[/]")
                    console.print(f"\n[green]  {result.message}[/]")
                else:
                    print_data_result("data.query_funding", result)
            else:
                print_data_result("data.query_funding", result)
            Prompt.ask("\nPress Enter to continue")

        elif choice == 3:
            # Query Open Interest History
            symbol = get_symbol_input("Symbol")
            if symbol is BACK:
                continue
            assert isinstance(symbol, str)
            if not symbol:
                print_error_below_menu("Symbol is required")
                Prompt.ask("\nPress Enter to continue")
                continue

            console.print("\n[bold cyan]Select data range:[/]")
            console.print("  1) Use period (e.g., 1M = last month)")
            console.print("  2) Custom date range")
            range_choice = get_input("Choice", "1")

            if range_choice == "2":
                start_str = get_input("Start date (YYYY-MM-DD)")
                if start_str is BACK:
                    continue
                end_str = get_input("End date (YYYY-MM-DD, blank for now)", "")
                if end_str is BACK:
                    continue

                result = run_tool_action(
                    "data.query_oi", get_open_interest_history_tool,
                    symbol=symbol.upper(),
                    start=start_str, end=end_str if end_str else None, env=data_env
                )
            else:
                period = get_input("Period (1M, 3M, 6M, 1Y)", "1M")
                if period is BACK:
                    continue
                result = run_tool_action(
                    "data.query_oi", get_open_interest_history_tool,
                    symbol=symbol.upper(), period=period, env=data_env
                )

            # Show summary for large results
            if result.success and result.data:
                count = result.data.get("count", 0)
                if count > 20:
                    console.print(f"\n[dim]Showing summary ({count:,} records total)[/]")
                    tr = result.data.get("time_range", {})
                    console.print(f"[dim]Range: {tr.get('first_record', 'N/A')} to {tr.get('last_record', 'N/A')}[/]")
                    console.print(f"\n[green]  {result.message}[/]")
                else:
                    print_data_result("data.query_oi", result)
            else:
                print_data_result("data.query_oi", result)
            Prompt.ask("\nPress Enter to continue")

        elif choice == 4:
            return
