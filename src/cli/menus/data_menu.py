"""
Data builder menu for the CLI.

Top-level menu with 9 items delegating to 4 sub-menus:
- Quick Actions: Build Full History, Sync Forward, Sync Forward + Gaps
- Browse: Custom Sync, Database Info, Query Data
- Maintenance: Fill gaps, heal, delete, vacuum, testing
- Settings: Toggle LIVE/DEMO environment

Data Environment Selection:
- LIVE: Canonical historical data for backtesting (api.bybit.com)
- DEMO: Demo-only history for demo validation (api-demo.bybit.com)
"""

from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

from src.config.config import get_config
from src.config.constants import DataEnv, DEFAULT_DATA_ENV
from src.cli.styles import CLIStyles, CLIColors, CLIIcons, BillArtWrapper
from src.cli.utils import BackCommand
from src.tools import (
    sync_to_now_tool,
    sync_forward_tool,
    build_symbol_history_tool,
)

if TYPE_CHECKING:
    from trade_cli import TradeCLI

# Local console
console = Console()


def data_menu(cli: "TradeCLI"):
    """Historical data builder menu (DuckDB-only)."""
    from src.cli.utils import (
        clear_screen, print_header, get_input, get_choice,
        print_error_below_menu, run_long_action,
        print_data_result, BACK,
        get_symbols_input,
    )

    # Current data environment (LIVE or DEMO) - persists during menu session
    data_env: DataEnv = DEFAULT_DATA_ENV

    while True:
        clear_screen()
        print_header()

        # Show data environment status
        config = get_config()
        env_summary = config.bybit.get_api_environment_summary()

        # Get status for current selected data env
        if data_env == "live":
            env_info = env_summary["data_live"]
            env_color = CLIColors.NEON_GREEN
            env_label = "LIVE (Canonical Backtest Data)"
        else:
            env_info = env_summary["data_demo"]
            env_color = CLIColors.NEON_CYAN
            env_label = "DEMO (Demo Validation Data)"

        key_status = "Key Configured" if env_info["key_configured"] else "No Key"
        key_color = CLIColors.NEON_GREEN if env_info["key_configured"] else CLIColors.NEON_YELLOW

        api_status_line = Text()
        api_status_line.append("Data Env: ", style=CLIColors.DIM_TEXT)
        api_status_line.append(f"{data_env.upper()} ", style=f"bold {env_color}")
        api_status_line.append(f"({env_info['base_url']})", style=CLIColors.DIM_TEXT)
        api_status_line.append(" | ", style=CLIColors.DIM_TEXT)
        api_status_line.append(key_status, style=key_color)
        api_status_line.append(" | ", style=CLIColors.DIM_TEXT)
        api_status_line.append(env_label, style=f"italic {CLIColors.DIM_TEXT}")
        console.print(Panel(api_status_line, border_style=f"dim {env_color}"))

        menu = CLIStyles.create_menu_table()

        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.MINING} Quick Actions ---[/]", "")
        menu.add_row("1", f"[bold {CLIColors.NEON_GREEN}]Build Full History[/]", f"[{CLIColors.NEON_GREEN}]Full sync: OHLCV + Funding + OI[/]")
        menu.add_row("2", f"[bold {CLIColors.NEON_CYAN}]Sync Forward[/]", f"[{CLIColors.NEON_CYAN}]Fetch new candles to now[/]")
        menu.add_row("3", f"[bold {CLIColors.NEON_CYAN}]Sync Forward + Gaps[/]", f"[{CLIColors.NEON_CYAN}]Sync new + backfill gaps[/]")
        menu.add_row("", "", "")
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.LEDGER} Browse ---[/]", "")
        menu.add_row("4", "Custom Sync", "Individual: OHLCV, Funding, OI")
        menu.add_row("5", "Database Info", "Stats, symbols, coverage")
        menu.add_row("6", "Query Data", "OHLCV, Funding, Open Interest queries")
        menu.add_row("", "", "")
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.SETTINGS} Maintenance ---[/]", "")
        menu.add_row("7", "Maintenance", "Fill gaps, heal, delete, vacuum")
        menu.add_row("", "", "")
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.EXCHANGE} Settings ---[/]", "")
        toggle_label = f"[bold {CLIColors.NEON_CYAN}]Switch to DEMO[/]" if data_env == "live" else f"[bold {CLIColors.NEON_GREEN}]Switch to LIVE[/]"
        toggle_desc = f"[{CLIColors.NEON_CYAN}]Use demo API for data[/]" if data_env == "live" else f"[{CLIColors.NEON_GREEN}]Use live API for data[/]"
        menu.add_row("8", toggle_label, toggle_desc)
        menu.add_row("", "", "")
        menu.add_row("9", f"{CLIIcons.BACK} Back to Main Menu", "Return to main menu")

        BillArtWrapper.print_menu_top()
        console.print(CLIStyles.get_menu_panel(menu, f"DATA BUILDER ({data_env.upper()})"))
        BillArtWrapper.print_menu_bottom()

        choice = get_choice(valid_range=range(1, 10))
        if choice is BACK:
            break  # Go back to main menu

        if choice == 1:
            # Build Full History (OHLCV + Funding + OI)
            symbols = get_symbols_input("Symbol(s) to build")
            if symbols is BACK:
                continue
            if not symbols:
                print_error_below_menu("No symbols provided.")
                Prompt.ask("\nPress Enter to continue")
                continue

            period = get_input("Period (1D, 1W, 1M, 3M, 6M, 1Y)", "1M")
            if period is BACK:
                continue
            assert isinstance(period, str)
            timeframes_input = get_input("OHLCV Timeframes (comma-separated, blank for all)", "")
            if timeframes_input is BACK:
                continue
            assert isinstance(timeframes_input, str)
            timeframes = [t.strip() for t in timeframes_input.split(",")] if timeframes_input else None
            oi_interval = get_input("Open Interest Interval (5min, 15min, 30min, 1h, 4h, D)", "1h")
            if oi_interval is BACK:
                continue
            assert isinstance(oi_interval, str)

            result = run_long_action(
                "data.build_full_history", build_symbol_history_tool,
                symbols, period=period, timeframes=timeframes, oi_interval=oi_interval, env=data_env
            )
            print_data_result("data.build_full_history", result)
            Prompt.ask("\nPress Enter to continue")

        elif choice == 2:
            # Sync Forward to Now (new candles only)
            symbols = get_symbols_input("Symbol(s) to sync forward")
            if symbols is BACK:
                continue
            if not symbols:
                print_error_below_menu("No symbols provided.")
                Prompt.ask("\nPress Enter to continue")
                continue

            timeframes_input = get_input("Timeframes (comma-separated, blank for all)", "")
            if timeframes_input is BACK:
                continue
            assert isinstance(timeframes_input, str)
            timeframes = [t.strip() for t in timeframes_input.split(",")] if timeframes_input else None

            result = run_long_action(
                "data.sync_to_now", sync_to_now_tool,
                symbols, timeframes=timeframes, env=data_env
            )
            print_data_result("data.sync_to_now", result)
            Prompt.ask("\nPress Enter to continue")

        elif choice == 3:
            # Sync Forward + Fill Gaps (complete)
            symbols = get_symbols_input("Symbol(s) to sync and heal")
            if symbols is BACK:
                continue
            if not symbols:
                print_error_below_menu("No symbols provided.")
                Prompt.ask("\nPress Enter to continue")
                continue

            timeframes_input = get_input("Timeframes (comma-separated, blank for all)", "")
            if timeframes_input is BACK:
                continue
            assert isinstance(timeframes_input, str)
            timeframes = [t.strip() for t in timeframes_input.split(",")] if timeframes_input else None

            result = run_long_action(
                "data.sync_forward", sync_forward_tool,
                symbols, timeframes=timeframes, env=data_env
            )
            print_data_result("data.sync_forward", result)
            Prompt.ask("\nPress Enter to continue")

        elif choice == 4:
            # Custom Sync sub-menu
            from src.cli.menus.data_sync_menu import data_sync_menu
            data_sync_menu(cli, data_env)

        elif choice == 5:
            # Database Info sub-menu
            from src.cli.menus.data_info_menu import data_info_menu
            data_info_menu(cli, data_env)

        elif choice == 6:
            # Query Data sub-menu
            from src.cli.menus.data_query_menu import data_query_menu
            data_query_menu(cli, data_env)

        elif choice == 7:
            # Maintenance sub-menu
            from src.cli.menus.data_maintenance_menu import data_maintenance_menu
            data_maintenance_menu(cli, data_env)

        elif choice == 8:
            # Toggle Data Environment
            if data_env == "live":
                data_env = "demo"
                console.print("\n[bold cyan]Switched to DEMO data environment[/]")
                console.print("[dim]Now using api-demo.bybit.com for data operations[/]")
            else:
                data_env = "live"
                console.print("\n[bold green]Switched to LIVE data environment[/]")
                console.print("[dim]Now using api.bybit.com for data operations[/]")
            Prompt.ask("\nPress Enter to continue")

        elif choice == 9:
            break
