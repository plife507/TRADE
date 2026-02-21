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
    backtest_preflight_play_tool,
    backtest_run_play_tool,
    backtest_data_fix_tool,
    backtest_indicators_tool,
)
from src.tools.backtest_play_normalize_tools import (
    backtest_play_normalize_tool,
)

if TYPE_CHECKING:
    from trade_cli import TradeCLI

# Local console
console = Console()


def backtest_play_menu(cli: "TradeCLI"):
    """Play backtest submenu."""
    from src.cli.utils import (
        clear_screen, print_header, get_choice, BACK,
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
            _run_play_backtest(cli)
        elif choice == 3:
            _preflight_check(cli)
        elif choice == 4:
            _data_fix(cli)
        elif choice == 5:
            _view_indicators(cli)
        elif choice == 6:
            _normalize_play(cli)
        elif choice == 9:
            return


def _select_play(prompt_text: str = "Select Play") -> str | None:
    """Interactive play selection with directory browsing and metadata preview.

    Flow: pick folder -> pick play from table with metadata -> confirm.
    Validation plays are excluded from browsing.

    Returns:
        Selected play_id or None if cancelled
    """
    from src.backtest.play import list_play_dirs, peek_play_yaml

    while True:
        groups = list_play_dirs(exclude_validation=True)
        if not groups:
            console.print(f"[{CLIColors.NEON_YELLOW}]No Plays found in plays/[/]")
            return None

        folder_keys = sorted(groups.keys(), key=lambda k: ("" if k == "." else k))
        total = sum(len(v) for v in groups.values())

        console.print()
        table = Table(
            title=f"{prompt_text} -- Pick a folder ({total} plays)",
            show_header=True, header_style="bold", padding=(0, 1),
        )
        table.add_column("#", style="dim", width=4)
        table.add_column("Folder", style=CLIColors.NEON_CYAN)
        table.add_column("Plays", justify="right", style=CLIColors.NEON_GREEN)

        for i, key in enumerate(folder_keys, 1):
            label = "plays/ (root)" if key == "." else f"plays/{key}/"
            table.add_row(str(i), label, str(len(groups[key])))

        console.print(table)
        console.print()

        selection = Prompt.ask(
            f"[{CLIColors.NEON_CYAN}]Folder number (or 'q' to cancel)[/]"
        )
        if selection.lower() in ("q", "b", "back"):
            return None

        try:
            idx = int(selection)
            if not (1 <= idx <= len(folder_keys)):
                console.print(f"[{CLIColors.NEON_RED}]Invalid number. Must be 1-{len(folder_keys)}.[/]")
                continue
        except ValueError:
            console.print(f"[{CLIColors.NEON_RED}]Enter a number.[/]")
            continue

        folder_key = folder_keys[idx - 1]
        paths = groups[folder_key]

        # Show plays in the chosen folder with metadata columns
        selected = _select_play_from_folder(folder_key, paths)
        if selected is None:
            continue  # Back to folder selection

        return selected


def _select_play_from_folder(folder_key: str, paths: list) -> str | None:
    """Show plays inside a folder with metadata. Returns play_id or None (back)."""
    from src.backtest.play import peek_play_yaml

    folder_label = "plays/ (root)" if folder_key == "." else f"plays/{folder_key}/"

    while True:
        console.print()
        table = Table(
            title=f"{folder_label} ({len(paths)} plays)",
            show_header=True, header_style="bold", padding=(0, 1),
        )
        table.add_column("#", style="dim", width=4)
        table.add_column("Play ID", style=CLIColors.NEON_CYAN, min_width=28)
        table.add_column("Symbol", style=CLIColors.NEON_YELLOW, width=10)
        table.add_column("TF", style=CLIColors.NEON_GREEN, width=5)
        table.add_column("Dir", width=10)
        table.add_column("Description", style=CLIColors.DIM_TEXT, max_width=40)

        infos = [peek_play_yaml(p) for p in paths]
        for i, info in enumerate(infos, 1):
            dir_style = (
                CLIColors.NEON_GREEN if info.direction == "long"
                else CLIColors.NEON_RED if info.direction == "short"
                else CLIColors.NEON_YELLOW
            )
            table.add_row(
                str(i),
                info.id,
                info.symbol,
                info.exec_tf,
                f"[{dir_style}]{info.direction}[/]",
                info.description[:40] if info.description else "",
            )

        console.print(table)
        console.print()

        selection = Prompt.ask(
            f"[{CLIColors.NEON_CYAN}]Play number (or 'b' for back)[/]"
        )
        if selection.lower() in ("b", "back", "q"):
            return None

        try:
            idx = int(selection)
            if 1 <= idx <= len(paths):
                return infos[idx - 1].id
            console.print(f"[{CLIColors.NEON_RED}]Invalid number. Must be 1-{len(paths)}.[/]")
        except ValueError:
            # Try direct name match
            for info in infos:
                if info.id == selection.strip():
                    return info.id
            console.print(f"[{CLIColors.NEON_RED}]No match. Enter a number or exact play name.[/]")


def _get_date_range() -> tuple[datetime | None, datetime | None]:
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
    """List all available Plays grouped by directory with metadata."""
    from src.backtest.play import list_play_dirs, peek_play_yaml

    console.print()
    console.print(f"[{CLIColors.NEON_CYAN}]Loading Plays...[/]")

    groups = list_play_dirs(exclude_validation=True)
    if not groups:
        console.print(f"[{CLIColors.NEON_YELLOW}]No Plays found in plays/[/]")
        Prompt.ask(f"[{CLIColors.DIM_TEXT}]Press Enter to continue[/]")
        return

    total = sum(len(v) for v in groups.values())
    console.print(f"\n[{CLIColors.NEON_GREEN}]Found {total} Plays (validation excluded)[/]\n")

    for folder_key in sorted(groups.keys(), key=lambda k: ("" if k == "." else k)):
        paths = groups[folder_key]
        folder_label = "plays/ (root)" if folder_key == "." else f"plays/{folder_key}/"

        table = Table(
            title=folder_label, show_header=True, header_style="bold", padding=(0, 1),
        )
        table.add_column("Play ID", style=CLIColors.NEON_CYAN, min_width=28)
        table.add_column("Symbol", style=CLIColors.NEON_YELLOW, width=10)
        table.add_column("TF", style=CLIColors.NEON_GREEN, width=5)
        table.add_column("Dir", width=10)
        table.add_column("Description", style=CLIColors.DIM_TEXT, max_width=44)

        for p in paths:
            info = peek_play_yaml(p)
            dir_style = (
                CLIColors.NEON_GREEN if info.direction == "long"
                else CLIColors.NEON_RED if info.direction == "short"
                else CLIColors.NEON_YELLOW
            )
            table.add_row(
                info.id,
                info.symbol,
                info.exec_tf,
                f"[{dir_style}]{info.direction}[/]",
                info.description[:44] if info.description else "",
            )

        console.print(table)
        console.print()

    Prompt.ask(f"[{CLIColors.DIM_TEXT}]Press Enter to continue[/]")


def _run_play_backtest(cli: "TradeCLI"):
    """Run a full Play backtest."""
    from src.cli.utils import run_long_action

    console.print()

    # Select Play
    play_id = _select_play("Select Play to run")
    if not play_id:
        return

    # Get date range
    start_date, end_date = _get_date_range()
    if start_date is None or end_date is None:
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
    from src.cli.utils import run_long_action

    console.print()

    # Select Play
    play_id = _select_play("Select Play for preflight")
    if not play_id:
        return

    # Get date range
    start_date, end_date = _get_date_range()
    if start_date is None or end_date is None:
        return

    # Ask about auto-fix
    sync = Confirm.ask(
        f"[{CLIColors.NEON_YELLOW}]Auto-sync missing data if found?[/]",
        default=False
    )

    console.print()
    result = run_long_action(
        "backtest.preflight",
        backtest_preflight_play_tool,
        play_id=play_id,
        start=start_date,
        end=end_date,
        sync=sync,
    )

    console.print()
    if result.success:
        data = result.data or {}
        status = data.get("overall_status", "unknown")

        if status == "passed":
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
    from src.cli.utils import run_long_action

    console.print()

    # Select Play
    play_id = _select_play("Select Play for data fix")
    if not play_id:
        return

    # Get date range
    start_date, end_date = _get_date_range()
    if start_date is None or end_date is None:
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
        for role in ["exec", "high_tf", "med_tf"]:
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


def _normalize_play(cli: "TradeCLI"):
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
