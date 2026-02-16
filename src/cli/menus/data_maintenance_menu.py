"""
Data maintenance sub-menu for Data Builder.

Handles maintenance operations:
- Fill Gaps
- Heal Data
- Delete Symbol
- Delete ALL Data
- Cleanup Empty Symbols
- Vacuum Database
- Run Extensive Data Test
"""

from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.text import Text

from src.cli.styles import CLIStyles, CLIColors, CLIIcons, BillArtWrapper
from src.config.constants import DataEnv
from src.tools import (
    sync_data_tool,
    heal_data_tool,
    delete_symbol_tool,
    delete_all_data_tool,
    cleanup_empty_symbols_tool,
    vacuum_database_tool,
)

if TYPE_CHECKING:
    from trade_cli import TradeCLI

# Local console
console = Console()


def data_maintenance_menu(cli: "TradeCLI", data_env: DataEnv) -> None:
    """Data maintenance sub-menu."""
    from src.cli.utils import (
        clear_screen, print_header, get_input, get_choice, BACK,
        run_tool_action, print_data_result,
        get_symbol_input,
    )

    while True:
        clear_screen()
        print_header()

        # Sub-menu header
        status_line = Text()
        status_line.append("Maintenance ", style=f"bold {CLIColors.NEON_YELLOW}")
        status_line.append(f"({data_env.upper()}) ", style=f"bold {CLIColors.NEON_GREEN if data_env == 'live' else CLIColors.NEON_CYAN}")
        status_line.append("| ", style=CLIColors.DIM_TEXT)
        status_line.append("Fill gaps, heal, delete, vacuum", style=CLIColors.DIM_TEXT)
        console.print(Panel(status_line, border_style=f"dim {CLIColors.NEON_YELLOW}"))

        menu = CLIStyles.create_menu_table()

        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.SETTINGS} Repair ---[/]", "")
        menu.add_row("1", "Fill Gaps", "Detect and fill missing candles in data")
        menu.add_row("2", "Heal Data", "Comprehensive data integrity check & repair")
        menu.add_row("", "", "")
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.PANIC} Destructive ---[/]", "")
        menu.add_row("3", f"[{CLIColors.NEON_RED}]{CLIIcons.ERROR} Delete Symbol[/]", f"[{CLIColors.NEON_RED}]Delete all data for a symbol[/]")
        menu.add_row("4", f"[bold {CLIColors.NEON_RED}]{CLIIcons.PANIC} Delete ALL Data[/]", f"[{CLIColors.NEON_RED}]Delete EVERYTHING (OHLCV, funding, OI)[/]")
        menu.add_row("", "", "")
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.DATABASE} Cleanup ---[/]", "")
        menu.add_row("5", "Cleanup Empty Symbols", "Remove symbols with no data")
        menu.add_row("6", "Vacuum Database", "Reclaim disk space after deletions")
        menu.add_row("", "", "")
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.TARGET} Testing ---[/]", "")
        menu.add_row("7", f"[bold {CLIColors.NEON_YELLOW}]{CLIIcons.TARGET} Run Extensive Data Test[/]", f"[{CLIColors.NEON_YELLOW}]Full smoke test of all data tools[/]")
        menu.add_row("", "", "")
        menu.add_row("8", f"{CLIIcons.BACK} Back", "Return to data menu")

        BillArtWrapper.print_menu_top()
        console.print(CLIStyles.get_menu_panel(menu, f"MAINTENANCE ({data_env.upper()})"))
        BillArtWrapper.print_menu_bottom()

        choice = get_choice(valid_range=range(1, 9))
        if choice is BACK:
            return

        if choice == 1:
            # Fill Gaps
            symbol = get_symbol_input("Symbol (blank for all)")
            timeframe = get_input("Timeframe (blank for all)", "")

            result = run_tool_action(
                "data.sync_data", sync_data_tool,
                symbol=symbol if symbol else None,
                timeframe=timeframe if timeframe else None,
                env=data_env
            )
            print_data_result("data.sync_data", result)
            Prompt.ask("\nPress Enter to continue")

        elif choice == 2:
            # Heal Data
            symbol = get_symbol_input("Symbol (blank for all)")

            result = run_tool_action(
                "data.heal", heal_data_tool,
                symbol=symbol if symbol else None,
                env=data_env
            )
            print_data_result("data.heal", result)
            Prompt.ask("\nPress Enter to continue")

        elif choice == 3:
            # Delete Symbol
            symbol = get_symbol_input("Symbol to DELETE")
            if symbol is BACK:
                continue
            assert isinstance(symbol, str)
            if symbol:
                env_label = data_env.upper()
                if Confirm.ask(f"[bold red]Delete ALL data for {symbol.upper()} in {env_label} env?[/]"):
                    result = run_tool_action("data.delete_symbol", delete_symbol_tool, symbol, env=data_env)
                    print_data_result("data.delete_symbol", result)
                else:
                    console.print("[yellow]Cancelled.[/]")
            else:
                console.print("[yellow]No symbol provided.[/]")
            Prompt.ask("\nPress Enter to continue")

        elif choice == 4:
            # Delete ALL Data
            env_label = data_env.upper()
            console.print(f"\n[bold red]WARNING: This will delete ALL historical data in {env_label} env![/]")
            console.print("[red]This includes: OHLCV candles, funding rates, and open interest data.[/]")
            console.print("[red]This action CANNOT be undone.[/]")
            if Confirm.ask(f"\n[bold red]Are you ABSOLUTELY sure you want to delete ALL {env_label} data?[/]"):
                if Confirm.ask("[bold red]Type YES to confirm deletion[/]", default=False):
                    result = run_tool_action("data.delete_all", delete_all_data_tool, env=data_env)
                    print_data_result("data.delete_all", result)
                else:
                    console.print("[yellow]Cancelled.[/]")
            else:
                console.print("[yellow]Cancelled.[/]")
            Prompt.ask("\nPress Enter to continue")

        elif choice == 5:
            # Cleanup Empty Symbols
            result = run_tool_action("data.cleanup_empty", cleanup_empty_symbols_tool, env=data_env)
            print_data_result("data.cleanup_empty", result)
            Prompt.ask("\nPress Enter to continue")

        elif choice == 6:
            # Vacuum Database
            result = run_tool_action("data.vacuum", vacuum_database_tool, env=data_env)
            print_data_result("data.vacuum", result)
            Prompt.ask("\nPress Enter to continue")

        elif choice == 7:
            # Run Extensive Data Test
            from src.cli.smoke_tests import run_extensive_data_smoke
            console.print(f"\n[bold yellow]Running Extensive Data Smoke Test ({data_env.upper()} env)...[/]")
            console.print("[dim]This will test all data tools with real API calls.[/]")
            if Confirm.ask("\nProceed with extensive data test?"):
                run_extensive_data_smoke(env=data_env)
            else:
                console.print("[yellow]Cancelled.[/]")
            Prompt.ask("\nPress Enter to continue")

        elif choice == 8:
            return
