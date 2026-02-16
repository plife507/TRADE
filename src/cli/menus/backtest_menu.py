"""
Backtest menu for the CLI.

Handles all backtesting operations through Play-based workflow:
- Play management and execution
- Audits and verification
- Analytics and results
- Data preparation

All operations call tools - no direct engine access from CLI.
Play-only: SystemConfig is not supported.
"""

from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt
from rich.text import Text

from src.cli.styles import CLIStyles, CLIColors, CLIIcons, BillArtWrapper
from src.cli.menus.backtest_play_menu import backtest_play_menu
from src.cli.menus.backtest_audits_menu import backtest_audits_menu
from src.cli.menus.backtest_analytics_menu import backtest_analytics_menu

if TYPE_CHECKING:
    from trade_cli import TradeCLI

# Local console
console = Console()


def backtest_menu(cli: "TradeCLI"):
    """Backtest menu - Play-based workflow."""
    from trade_cli import (
        clear_screen, print_header, get_choice, BACK,
    )

    while True:
        clear_screen()
        print_header()

        # Show backtest info header
        status_line = Text()
        status_line.append("Backtest Engine ", style=f"bold {CLIColors.NEON_MAGENTA}")
        status_line.append("│ ", style=CLIColors.DIM_TEXT)
        status_line.append("Play-driven strategy backtesting", style=CLIColors.DIM_TEXT)
        console.print(Panel(status_line, border_style=f"dim {CLIColors.NEON_MAGENTA}"))

        menu = CLIStyles.create_menu_table()

        # Play section
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.BOT} Backtesting ---[/]", "")
        menu.add_row("1", f"[bold {CLIColors.NEON_CYAN}]Play Backtests[/]", f"[{CLIColors.NEON_CYAN}]Run, preflight, data fix, indicators[/]")
        menu.add_row("", "", "")

        # Audits section (Phase 2 - placeholder)
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.LEDGER} Verification ---[/]", "")
        menu.add_row("2", "Audits & Verification", "Toolkit, math parity, plumbing audits")
        menu.add_row("", "", "")

        # Analytics section (Phase 3 - placeholder)
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.DATABASE} Results ---[/]", "")
        menu.add_row("3", "Analytics & Results", "View runs, returns, compare")
        menu.add_row("", "", "")

        # Navigation
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- Navigation ---[/]", "")
        menu.add_row("4", "The Forge", "Play development & validation environment")
        menu.add_row("9", f"{CLIIcons.BACK} Back to Main Menu", "Return to main menu")

        BillArtWrapper.print_menu_top()
        console.print(CLIStyles.get_menu_panel(menu, "BACKTEST ENGINE"))
        BillArtWrapper.print_menu_bottom()

        choice = get_choice(valid_range=range(1, 10))
        if choice is BACK:
            return  # Go back to main menu

        if choice == 1:
            # Play Backtests submenu
            backtest_play_menu(cli)

        elif choice == 2:
            # Audits & Verification submenu
            backtest_audits_menu(cli)

        elif choice == 3:
            # Analytics & Results submenu
            backtest_analytics_menu(cli)

        elif choice == 4:
            from src.cli.menus.forge_menu import forge_menu
            forge_menu(cli)

        elif choice == 9:
            return
