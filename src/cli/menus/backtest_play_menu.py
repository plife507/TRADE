"""
Play Backtest submenu for the CLI.

Handles Play-based backtesting operations (Golden Path):
- List and select Plays
- Run preflight checks
- Execute backtests
- Data fix/sync
- View indicators
- Normalize/validate Plays

All operations call tools - no direct engine access from CLI.
"""

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.text import Text

from src.cli.styles import CLIStyles, CLIColors, CLIIcons, BillArtWrapper
from src.tools import (
    backtest_list_plays_tool,
    backtest_preflight_play_tool,
    backtest_run_play_tool,
    backtest_data_fix_tool,
    backtest_indicators_tool,
)
from src.tools.backtest_cli_wrapper import (
    backtest_play_normalize_tool,
)

if TYPE_CHECKING:
    from trade_cli import TradeCLI

# Local console
console = Console()


def backtest_play_menu(cli: "TradeCLI"):
    """Play backtest submenu."""
    from trade_cli import (
        clear_screen, print_header, get_input, get_choice, BACK,
        print_error_below_menu, run_tool_action, run_long_action,
        print_data_result,
    )

    while True:
        clear_screen()
        print_header()

        # Show Play info header
        status_line = Text()
        status_line.append("Play Backtests ", style=f"bold {CLIColors.NEON_CYAN}")
        status_line.append("│ ", style=CLIColors.DIM_TEXT)
        status_line.append("YAML-driven strategy backtesting (Golden Path)", style=CLIColors.DIM_TEXT)
        console.print(Panel(status_line, border_style=f"dim {CLIColors.NEON_CYAN}"))

        menu = CLIStyles.create_menu_table()

        # List section
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.LEDGER} Plays ---[/]", "")
        menu.add_row("1", "List Plays", "View all available Play configs")
        menu.add_row("", "", "")

        # Execution section
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.TRADE} Execute ---[/]", "")
        menu.add_row("2", f"[bold {CLIColors.NEON_GREEN}]Run Backtest[/]", f"[{CLIColors.NEON_GREEN}]Execute Play backtest[/]")
        menu.add_row("3", "Preflight Check", "Validate data coverage before running")
        menu.add_row("4", "Data Fix", "Sync and heal data for Play")
        menu.add_row("", "", "")

        # Inspection section
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.BOT} Inspect ---[/]", "")
        menu.add_row("5", "View Indicators", "Show declared indicators for Play")
        menu.add_row("6", "Normalize Play", "Validate and normalize YAML structure")
        menu.add_row("", "", "")

        # Navigation
        menu.add_row("9", f"{CLIIcons.BACK} Back", "Return to backtest menu")

        BillArtWrapper.print_menu_top()
        console.print(CLIStyles.get_menu_panel(menu, "PLAY BACKTESTS"))
        BillArtWrapper.print_menu_bottom()

        choice = get_choice(valid_range=range(1, 10))
        if choice is BACK:
            return  # Go back to backtest menu

        if choice == 1:
            _list_plays(cli)
        elif choice == 2:
            _run_ideacard_backtest(cli)
        elif choice == 3:
            _preflight_check(cli)
        elif choice == 4:
            _data_fix(cli)
        elif choice == 5:
            _view_indicators(cli)
        elif choice == 6:
            _normalize_ideacard(cli)
        elif choice == 9:
            return


def _select_play(prompt_text: str = "Select Play") -> str | None:
    """
    Show numbered list of Plays and let user select by number.

    Returns:
        Selected play_id or None if cancelled
    """
    result = backtest_list_plays_tool()

    if not result.success or not result.data:
        console.print(f"[{CLIColors.NEON_RED}]Error loading Plays: {result.error}[/]")
        return None

    cards = result.data.get("plays", [])

    if not cards:
        console.print(f"[{CLIColors.NEON_YELLOW}]No Plays found in configs/plays/[/]")
        return None

    # Display numbered list
    table = Table(title="Available Plays", show_header=True, header_style="bold")
    table.add_column("#", style="dim", width=4)
    table.add_column("Play ID", style=CLIColors.NEON_CYAN)

    for i, card_id in enumerate(cards, 1):
        table.add_row(str(i), card_id)

    console.print(table)
    console.print()

    # Get selection
    selection = Prompt.ask(
        f"[{CLIColors.NEON_CYAN}]{prompt_text} (number or 'q' to cancel)[/]"
    )

    if selection.lower() == 'q':
        return None

    try:
        idx = int(selection) - 1
        if 0 <= idx < len(cards):
            return cards[idx]
        else:
            console.print(f"[{CLIColors.NEON_RED}]Invalid selection[/]")
            return None
    except ValueError:
        # Try direct ID match
        if selection in cards:
            return selection
        console.print(f"[{CLIColors.NEON_RED}]Invalid selection: {selection}[/]")
        return None


def _get_date_range() -> tuple:
    """
    Prompt user for start and end dates.

    Returns:
        Tuple of (start_date, end_date) as datetime objects, or (None, None) if cancelled
    """
    console.print()
    console.print(f"[{CLIColors.DIM_TEXT}]Enter date range (YYYY-MM-DD format)[/]")
    console.print(f"[{CLIColors.DIM_TEXT}]Press Enter for defaults: 30 days ago to today[/]")

    # Default dates
    default_end = datetime.now()
    default_start = default_end - timedelta(days=30)

    start_str = Prompt.ask(
        f"[{CLIColors.NEON_CYAN}]Start date[/]",
        default=default_start.strftime("%Y-%m-%d")
    )

    end_str = Prompt.ask(
        f"[{CLIColors.NEON_CYAN}]End date[/]",
        default=default_end.strftime("%Y-%m-%d")
    )

    try:
        start_date = datetime.strptime(start_str, "%Y-%m-%d")
        end_date = datetime.strptime(end_str, "%Y-%m-%d")
        return start_date, end_date
    except ValueError as e:
        console.print(f"[{CLIColors.NEON_RED}]Invalid date format: {e}[/]")
        return None, None


def _list_plays(cli: "TradeCLI"):
    """List all available Plays."""
    from trade_cli import run_tool_action, print_data_result

    console.print()
    console.print(f"[{CLIColors.NEON_CYAN}]Loading Plays...[/]")

    result = backtest_list_plays_tool()

    if result.success:
        cards = result.data.get("plays", [])
        directory = result.data.get("directory", "")

        console.print()
        console.print(f"[{CLIColors.NEON_GREEN}]Found {len(cards)} Plays in {directory}[/]")
        console.print()

        if cards:
            table = Table(show_header=True, header_style="bold")
            table.add_column("#", style="dim", width=4)
            table.add_column("Play ID", style=CLIColors.NEON_CYAN)

            for i, card_id in enumerate(cards, 1):
                table.add_row(str(i), card_id)

            console.print(table)
    else:
        console.print(f"[{CLIColors.NEON_RED}]Error: {result.error}[/]")

    console.print()
    Prompt.ask(f"[{CLIColors.DIM_TEXT}]Press Enter to continue[/]")


def _run_ideacard_backtest(cli: "TradeCLI"):
    """Run a full Play backtest."""
    from trade_cli import run_long_action

    console.print()

    # Select Play
    play_id = _select_play("Select Play to run")
    if not play_id:
        return

    # Get date range
    start_date, end_date = _get_date_range()
    if start_date is None:
        return

    # Confirm
    console.print()
    console.print(f"[{CLIColors.NEON_CYAN}]Running backtest:[/]")
    console.print(f"  Play: [{CLIColors.NEON_GREEN}]{play_id}[/]")
    console.print(f"  Window: {start_date.date()} to {end_date.date()}")
    console.print()

    if not Confirm.ask(f"[{CLIColors.NEON_YELLOW}]Proceed with backtest?[/]"):
        return

    # Run backtest with progress indicator
    console.print()
    result = run_long_action(
        "backtest.run",
        backtest_run_play_tool,
        play_id=play_id,
        start=start_date,
        end=end_date,
    )

    console.print()
    if result.success:
        console.print(f"[{CLIColors.NEON_GREEN}]{CLIIcons.SUCCESS} Backtest completed successfully![/]")

        data = result.data or {}

        # Show key metrics
        if "metrics" in data:
            metrics = data["metrics"]
            console.print()
            console.print(f"[bold]Results Summary:[/]")

            metrics_table = Table(show_header=False, box=None)
            metrics_table.add_column("Metric", style=CLIColors.DIM_TEXT)
            metrics_table.add_column("Value", style=CLIColors.NEON_GREEN)

            metrics_table.add_row("Net PnL", f"${metrics.get('net_profit', 0):.2f}")
            metrics_table.add_row("Return", f"{metrics.get('net_return_pct', 0):.2f}%")
            metrics_table.add_row("Total Trades", str(metrics.get('total_trades', 0)))
            metrics_table.add_row("Win Rate", f"{metrics.get('win_rate', 0):.1f}%")
            metrics_table.add_row("Sharpe", f"{metrics.get('sharpe', 0):.2f}")
            metrics_table.add_row("Max Drawdown", f"{metrics.get('max_drawdown_pct', 0):.2f}%")

            console.print(metrics_table)

        # Show artifact path
        if "run_folder" in data:
            console.print()
            console.print(f"[{CLIColors.DIM_TEXT}]Artifacts: {data['run_folder']}[/]")
    else:
        console.print(f"[{CLIColors.NEON_RED}]{CLIIcons.ERROR} Backtest failed: {result.error}[/]")

    console.print()
    Prompt.ask(f"[{CLIColors.DIM_TEXT}]Press Enter to continue[/]")


def _preflight_check(cli: "TradeCLI"):
    """Run preflight check for an Play."""
    from trade_cli import run_long_action

    console.print()

    # Select Play
    play_id = _select_play("Select Play for preflight")
    if not play_id:
        return

    # Get date range
    start_date, end_date = _get_date_range()
    if start_date is None:
        return

    # Ask about auto-fix
    fix_gaps = Confirm.ask(
        f"[{CLIColors.NEON_YELLOW}]Auto-fix missing data if found?[/]",
        default=False
    )

    console.print()
    result = run_long_action(
        "backtest.preflight",
        backtest_preflight_play_tool,
        play_id=play_id,
        start=start_date,
        end=end_date,
        fix_gaps=fix_gaps,
    )

    console.print()
    if result.success:
        data = result.data or {}
        status = data.get("status", "unknown")

        if status == "pass":
            console.print(f"[{CLIColors.NEON_GREEN}]{CLIIcons.SUCCESS} Preflight PASSED[/]")
        else:
            console.print(f"[{CLIColors.NEON_RED}]{CLIIcons.ERROR} Preflight FAILED[/]")

        # Show coverage info
        if "coverage" in data:
            coverage = data["coverage"]
            console.print()
            console.print(f"[bold]Data Coverage:[/]")
            for tf, cov_info in coverage.items():
                pct = cov_info.get("coverage_pct", 0)
                style = CLIColors.NEON_GREEN if pct >= 95 else CLIColors.NEON_YELLOW if pct >= 80 else CLIColors.NEON_RED
                console.print(f"  {tf}: [{style}]{pct:.1f}%[/]")

        # Show issues
        if "issues" in data and data["issues"]:
            console.print()
            console.print(f"[{CLIColors.NEON_YELLOW}]Issues:[/]")
            for issue in data["issues"]:
                console.print(f"  - {issue}")
    else:
        console.print(f"[{CLIColors.NEON_RED}]Preflight error: {result.error}[/]")

    console.print()
    Prompt.ask(f"[{CLIColors.DIM_TEXT}]Press Enter to continue[/]")


def _data_fix(cli: "TradeCLI"):
    """Run data fix/sync for an Play."""
    from trade_cli import run_long_action

    console.print()

    # Select Play
    play_id = _select_play("Select Play for data fix")
    if not play_id:
        return

    # Get date range
    start_date, end_date = _get_date_range()
    if start_date is None:
        return

    console.print()
    result = run_long_action(
        "backtest.data_fix",
        backtest_data_fix_tool,
        play_id=play_id,
        start=start_date,
        end=end_date,
    )

    console.print()
    if result.success:
        console.print(f"[{CLIColors.NEON_GREEN}]{CLIIcons.SUCCESS} Data fix completed![/]")

        data = result.data or {}
        if "operations" in data:
            console.print()
            console.print(f"[bold]Operations performed:[/]")
            for op in data["operations"]:
                console.print(f"  - {op}")
    else:
        console.print(f"[{CLIColors.NEON_RED}]Data fix error: {result.error}[/]")

    console.print()
    Prompt.ask(f"[{CLIColors.DIM_TEXT}]Press Enter to continue[/]")


def _view_indicators(cli: "TradeCLI"):
    """View indicators for an Play."""
    console.print()

    # Select Play
    play_id = _select_play("Select Play to inspect")
    if not play_id:
        return

    console.print()
    console.print(f"[{CLIColors.NEON_CYAN}]Loading indicators...[/]")

    result = backtest_indicators_tool(play_id=play_id)

    console.print()
    if result.success:
        data = result.data or {}

        console.print(f"[{CLIColors.NEON_GREEN}]Indicators for {play_id}:[/]")
        console.print()

        # Show by timeframe role
        for role in ["exec", "htf", "mtf"]:
            key = f"{role}_indicators"
            if key in data and data[key]:
                console.print(f"[bold]{role.upper()} Timeframe:[/]")
                for ind in data[key]:
                    console.print(f"  - {ind}")
                console.print()
    else:
        console.print(f"[{CLIColors.NEON_RED}]Error: {result.error}[/]")

    console.print()
    Prompt.ask(f"[{CLIColors.DIM_TEXT}]Press Enter to continue[/]")


def _normalize_ideacard(cli: "TradeCLI"):
    """Normalize and validate an Play YAML."""
    console.print()

    # Select Play
    play_id = _select_play("Select Play to normalize")
    if not play_id:
        return

    # Ask about write
    write_in_place = Confirm.ask(
        f"[{CLIColors.NEON_YELLOW}]Write normalized YAML back to file?[/]",
        default=False
    )

    console.print()
    console.print(f"[{CLIColors.NEON_CYAN}]Normalizing Play...[/]")

    result = backtest_play_normalize_tool(
        play_id=play_id,
        write_in_place=write_in_place,
    )

    console.print()
    if result.success:
        console.print(f"[{CLIColors.NEON_GREEN}]{CLIIcons.SUCCESS} Play is valid![/]")

        data = result.data or {}
        if "warnings" in data and data["warnings"]:
            console.print()
            console.print(f"[{CLIColors.NEON_YELLOW}]Warnings:[/]")
            for warning in data["warnings"]:
                console.print(f"  - {warning}")

        if write_in_place:
            console.print(f"[{CLIColors.NEON_GREEN}]YAML updated in place.[/]")
    else:
        console.print(f"[{CLIColors.NEON_RED}]{CLIIcons.ERROR} Validation failed: {result.error}[/]")

        data = result.data or {}
        if "errors" in data:
            console.print()
            for error in data["errors"]:
                console.print(f"  - {error}")

    console.print()
    Prompt.ask(f"[{CLIColors.DIM_TEXT}]Press Enter to continue[/]")
