"""
Analytics & Results submenu for the CLI.

Handles backtest results viewing and analysis:
- List recent runs
- View run results
- View time-based returns (returns.json)
- Compare runs

All operations read from backtests/ artifact folder.
"""

import json
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt
from rich.text import Text

from src.cli.styles import CLIStyles, CLIColors, CLIIcons, BillArtWrapper

if TYPE_CHECKING:
    from trade_cli import TradeCLI

# Local console
console = Console()

# Default backtests directory
BACKTESTS_DIR = Path("backtests")


def backtest_analytics_menu(cli: "TradeCLI"):
    """Analytics & Results submenu."""
    from trade_cli import (
        clear_screen, print_header, get_choice, BACK,
    )

    while True:
        clear_screen()
        print_header()

        # Show analytics info header
        status_line = Text()
        status_line.append("Analytics & Results ", style=f"bold {CLIColors.NEON_GREEN}")
        status_line.append("│ ", style=CLIColors.DIM_TEXT)
        status_line.append("View and compare backtest results", style=CLIColors.DIM_TEXT)
        console.print(Panel(status_line, border_style=f"dim {CLIColors.NEON_GREEN}"))

        menu = CLIStyles.create_menu_table()

        # Results section
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.LEDGER} Results ---[/]", "")
        menu.add_row("1", "List Recent Runs", "Show recent backtest runs")
        menu.add_row("2", f"[bold {CLIColors.NEON_CYAN}]View Run Results[/]", f"[{CLIColors.NEON_CYAN}]Display metrics for a run[/]")
        menu.add_row("", "", "")

        # Time-based analytics
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.DATABASE} Time Analytics ---[/]", "")
        menu.add_row("3", f"[bold {CLIColors.NEON_GREEN}]View Time-Based Returns[/]", f"[{CLIColors.NEON_GREEN}]Daily/weekly/monthly returns[/]")
        menu.add_row("", "", "")

        # Comparison
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.TRADE} Compare ---[/]", "")
        menu.add_row("4", "Compare Two Runs", "Side-by-side metrics comparison")
        menu.add_row("", "", "")

        # Navigation
        menu.add_row("9", f"{CLIIcons.BACK} Back", "Return to backtest menu")

        BillArtWrapper.print_menu_top()
        console.print(CLIStyles.get_menu_panel(menu, "ANALYTICS & RESULTS"))
        BillArtWrapper.print_menu_bottom()

        choice = get_choice(valid_range=range(1, 10))
        if choice is BACK:
            return  # Go back to backtest menu

        if choice == 1:
            _list_recent_runs()
        elif choice == 2:
            _view_run_results()
        elif choice == 3:
            _view_time_based_returns()
        elif choice == 4:
            _compare_runs()
        elif choice == 9:
            return


def _scan_runs(limit: int = 20) -> list[dict]:
    """Scan backtests directory for recent runs."""
    runs = []

    if not BACKTESTS_DIR.exists():
        return runs

    # Find all result.json files
    for result_path in BACKTESTS_DIR.rglob("result.json"):
        try:
            with open(result_path, encoding="utf-8") as f:
                result = json.load(f)

            run_dir = result_path.parent

            runs.append({
                "run_id": result.get("run_id", run_dir.name),
                "play": result.get("system_id", "unknown"),
                "symbol": result.get("symbol", ""),
                "net_return_pct": result.get("metrics", {}).get("net_return_pct", 0),
                "total_trades": result.get("metrics", {}).get("total_trades", 0),
                "sharpe": result.get("metrics", {}).get("sharpe", 0),
                "max_dd_pct": result.get("metrics", {}).get("max_drawdown_pct", 0),
                "start_ts": result.get("start_ts", ""),
                "end_ts": result.get("end_ts", ""),
                "path": str(run_dir),
            })
        except Exception:
            continue

    # Sort by start_ts descending (most recent first)
    runs.sort(key=lambda x: x.get("start_ts", ""), reverse=True)

    return runs[:limit]


def _select_run(prompt_text: str = "Select run") -> str | None:
    """Show list of runs and let user select one."""
    runs = _scan_runs(limit=15)

    if not runs:
        console.print(f"[{CLIColors.NEON_YELLOW}]No backtest runs found in {BACKTESTS_DIR}[/]")
        return None

    # Display table
    table = Table(title="Recent Backtest Runs", show_header=True, header_style="bold")
    table.add_column("#", style="dim", width=3)
    table.add_column("Play", style=CLIColors.NEON_CYAN, max_width=25)
    table.add_column("Symbol", style=CLIColors.NEON_YELLOW)
    table.add_column("Return", justify="right")
    table.add_column("Trades", justify="right")
    table.add_column("Sharpe", justify="right")
    table.add_column("Max DD", justify="right")

    for i, run in enumerate(runs, 1):
        ret_pct = run["net_return_pct"]
        ret_style = CLIColors.NEON_GREEN if ret_pct >= 0 else CLIColors.NEON_RED
        table.add_row(
            str(i),
            run["play"][:25],
            run["symbol"],
            f"[{ret_style}]{ret_pct:.1f}%[/]",
            str(run["total_trades"]),
            f"{run['sharpe']:.2f}",
            f"{run['max_dd_pct']:.1f}%",
        )

    console.print(table)
    console.print()

    selection = Prompt.ask(
        f"[{CLIColors.NEON_CYAN}]{prompt_text} (number or 'q' to cancel)[/]"
    )

    if selection.lower() == 'q':
        return None

    try:
        idx = int(selection) - 1
        if 0 <= idx < len(runs):
            return runs[idx]["path"]
        else:
            console.print(f"[{CLIColors.NEON_RED}]Invalid selection[/]")
            return None
    except ValueError:
        console.print(f"[{CLIColors.NEON_RED}]Invalid selection[/]")
        return None


def _list_recent_runs():
    """List recent backtest runs."""
    console.print()
    console.print(f"[{CLIColors.NEON_CYAN}]Scanning for recent runs...[/]")

    runs = _scan_runs(limit=20)

    if not runs:
        console.print(f"[{CLIColors.NEON_YELLOW}]No backtest runs found in {BACKTESTS_DIR}[/]")
    else:
        console.print()

        table = Table(title=f"Recent Backtest Runs ({len(runs)} found)", show_header=True, header_style="bold")
        table.add_column("#", style="dim", width=3)
        table.add_column("Play", style=CLIColors.NEON_CYAN, max_width=30)
        table.add_column("Symbol", style=CLIColors.NEON_YELLOW)
        table.add_column("Return", justify="right")
        table.add_column("Trades", justify="right")
        table.add_column("Sharpe", justify="right")
        table.add_column("Max DD", justify="right")
        table.add_column("Period", style=CLIColors.DIM_TEXT)

        for i, run in enumerate(runs, 1):
            ret_pct = run["net_return_pct"]
            ret_style = CLIColors.NEON_GREEN if ret_pct >= 0 else CLIColors.NEON_RED

            # Format period
            start = run["start_ts"][:10] if run["start_ts"] else ""
            end = run["end_ts"][:10] if run["end_ts"] else ""
            period = f"{start} to {end}" if start else ""

            table.add_row(
                str(i),
                run["play"][:30],
                run["symbol"],
                f"[{ret_style}]{ret_pct:.1f}%[/]",
                str(run["total_trades"]),
                f"{run['sharpe']:.2f}",
                f"{run['max_dd_pct']:.1f}%",
                period,
            )

        console.print(table)

    console.print()
    Prompt.ask(f"[{CLIColors.DIM_TEXT}]Press Enter to continue[/]")


def _view_run_results():
    """View detailed results for a run."""
    console.print()

    run_path = _select_run("Select run to view")
    if not run_path:
        return

    result_file = Path(run_path) / "result.json"
    if not result_file.exists():
        console.print(f"[{CLIColors.NEON_RED}]result.json not found in {run_path}[/]")
        Prompt.ask(f"[{CLIColors.DIM_TEXT}]Press Enter to continue[/]")
        return

    with open(result_file, encoding="utf-8") as f:
        result = json.load(f)

    metrics = result.get("metrics", {})

    console.print()
    console.print(f"[bold {CLIColors.NEON_GREEN}]Run Results: {result.get('system_id', 'Unknown')}[/]")
    console.print(f"[{CLIColors.DIM_TEXT}]Run ID: {result.get('run_id', 'N/A')}[/]")
    console.print()

    # Equity metrics
    console.print(f"[bold {CLIColors.NEON_YELLOW}]Equity[/]")
    table = Table(show_header=False, box=None)
    table.add_column("Metric", style=CLIColors.DIM_TEXT, width=25)
    table.add_column("Value", style=CLIColors.NEON_GREEN)
    table.add_row("Initial Equity", f"${metrics.get('initial_equity', 0):,.2f}")
    table.add_row("Final Equity", f"${metrics.get('final_equity', 0):,.2f}")
    table.add_row("Net Profit", f"${metrics.get('net_profit', 0):,.2f}")
    table.add_row("Net Return", f"{metrics.get('net_return_pct', 0):.2f}%")
    console.print(table)

    # Trade metrics
    console.print()
    console.print(f"[bold {CLIColors.NEON_YELLOW}]Trade Statistics[/]")
    table = Table(show_header=False, box=None)
    table.add_column("Metric", style=CLIColors.DIM_TEXT, width=25)
    table.add_column("Value", style=CLIColors.NEON_CYAN)
    table.add_row("Total Trades", str(metrics.get('total_trades', 0)))
    table.add_row("Win Rate", f"{metrics.get('win_rate', 0):.1f}%")
    table.add_row("Profit Factor", f"{metrics.get('profit_factor', 0):.2f}")
    table.add_row("Expectancy", f"${metrics.get('expectancy_usdt', 0):.2f}")
    table.add_row("Avg Win", f"${metrics.get('avg_win_usdt', 0):.2f}")
    table.add_row("Avg Loss", f"${metrics.get('avg_loss_usdt', 0):.2f}")
    console.print(table)

    # Risk metrics
    console.print()
    console.print(f"[bold {CLIColors.NEON_YELLOW}]Risk Metrics[/]")
    table = Table(show_header=False, box=None)
    table.add_column("Metric", style=CLIColors.DIM_TEXT, width=25)
    table.add_column("Value", style=CLIColors.NEON_MAGENTA)
    table.add_row("Sharpe", f"{metrics.get('sharpe', 0):.2f}")
    table.add_row("Sortino", f"{metrics.get('sortino', 0):.2f}")
    table.add_row("Calmar", f"{metrics.get('calmar', 0):.2f}")
    table.add_row("Max Drawdown", f"{metrics.get('max_drawdown_pct', 0):.2f}%")
    table.add_row("Max DD Duration", f"{metrics.get('max_drawdown_duration_bars', 0)} bars")
    console.print(table)

    console.print()
    console.print(f"[{CLIColors.DIM_TEXT}]Path: {run_path}[/]")

    console.print()
    Prompt.ask(f"[{CLIColors.DIM_TEXT}]Press Enter to continue[/]")


def _view_time_based_returns():
    """View time-based returns for a run."""
    console.print()

    run_path = _select_run("Select run for time-based returns")
    if not run_path:
        return

    returns_file = Path(run_path) / "returns.json"
    if not returns_file.exists():
        console.print(f"[{CLIColors.NEON_YELLOW}]returns.json not found - this run predates Phase 4 analytics[/]")
        console.print(f"[{CLIColors.DIM_TEXT}]Re-run the backtest to generate time-based returns[/]")
        Prompt.ask(f"[{CLIColors.DIM_TEXT}]Press Enter to continue[/]")
        return

    with open(returns_file, encoding="utf-8") as f:
        returns = json.load(f)

    console.print()
    console.print(f"[bold {CLIColors.NEON_GREEN}]Time-Based Returns[/]")
    console.print(f"[{CLIColors.DIM_TEXT}]Path: {run_path}[/]")
    console.print()

    # Best/Worst summary
    console.print(f"[bold {CLIColors.NEON_YELLOW}]Best/Worst Periods[/]")
    table = Table(show_header=True, header_style="bold")
    table.add_column("Period", style=CLIColors.DIM_TEXT)
    table.add_column("Best", style=CLIColors.NEON_GREEN)
    table.add_column("Worst", style=CLIColors.NEON_RED)

    best_day = returns.get("best_day")
    worst_day = returns.get("worst_day")
    best_week = returns.get("best_week")
    worst_week = returns.get("worst_week")
    best_month = returns.get("best_month")
    worst_month = returns.get("worst_month")

    table.add_row(
        "Day",
        f"{best_day[0]}: {best_day[1]:.2f}%" if best_day else "N/A",
        f"{worst_day[0]}: {worst_day[1]:.2f}%" if worst_day else "N/A",
    )
    table.add_row(
        "Week",
        f"{best_week[0]}: {best_week[1]:.2f}%" if best_week else "N/A",
        f"{worst_week[0]}: {worst_week[1]:.2f}%" if worst_week else "N/A",
    )
    table.add_row(
        "Month",
        f"{best_month[0]}: {best_month[1]:.2f}%" if best_month else "N/A",
        f"{worst_month[0]}: {worst_month[1]:.2f}%" if worst_month else "N/A",
    )
    console.print(table)

    # Monthly returns
    monthly = returns.get("monthly_returns", {})
    if monthly:
        console.print()
        console.print(f"[bold {CLIColors.NEON_YELLOW}]Monthly Returns[/]")
        table = Table(show_header=True, header_style="bold")
        table.add_column("Month", style=CLIColors.DIM_TEXT)
        table.add_column("Return", justify="right")

        for month, ret in sorted(monthly.items()):
            style = CLIColors.NEON_GREEN if ret >= 0 else CLIColors.NEON_RED
            table.add_row(month, f"[{style}]{ret:.2f}%[/]")

        console.print(table)

    # Daily count
    daily = returns.get("daily_returns", {})
    weekly = returns.get("weekly_returns", {})
    console.print()
    console.print(f"[{CLIColors.DIM_TEXT}]Total: {len(daily)} days, {len(weekly)} weeks, {len(monthly)} months[/]")

    console.print()
    Prompt.ask(f"[{CLIColors.DIM_TEXT}]Press Enter to continue[/]")


def _compare_runs():
    """Compare two runs side by side."""
    console.print()
    console.print(f"[{CLIColors.NEON_CYAN}]Select first run to compare[/]")

    run1_path = _select_run("Select first run")
    if not run1_path:
        return

    console.print()
    console.print(f"[{CLIColors.NEON_CYAN}]Select second run to compare[/]")

    run2_path = _select_run("Select second run")
    if not run2_path:
        return

    # Load both results
    try:
        with open(Path(run1_path) / "result.json", encoding="utf-8") as f:
            result1 = json.load(f)
        with open(Path(run2_path) / "result.json", encoding="utf-8") as f:
            result2 = json.load(f)
    except Exception as e:
        console.print(f"[{CLIColors.NEON_RED}]Error loading results: {e}[/]")
        Prompt.ask(f"[{CLIColors.DIM_TEXT}]Press Enter to continue[/]")
        return

    m1 = result1.get("metrics", {})
    m2 = result2.get("metrics", {})

    console.print()
    console.print(f"[bold {CLIColors.NEON_GREEN}]Run Comparison[/]")

    # Comparison table
    table = Table(show_header=True, header_style="bold")
    table.add_column("Metric", style=CLIColors.DIM_TEXT, width=20)
    table.add_column(result1.get("system_id", "Run 1")[:20], style=CLIColors.NEON_CYAN, justify="right")
    table.add_column(result2.get("system_id", "Run 2")[:20], style=CLIColors.NEON_YELLOW, justify="right")
    table.add_column("Diff", justify="right")

    def add_comparison_row(name: str, key: str, fmt: str = ".2f", suffix: str = ""):
        v1 = m1.get(key, 0)
        v2 = m2.get(key, 0)
        diff = v2 - v1
        diff_style = CLIColors.NEON_GREEN if diff > 0 else CLIColors.NEON_RED if diff < 0 else CLIColors.DIM_TEXT
        table.add_row(
            name,
            f"{v1:{fmt}}{suffix}",
            f"{v2:{fmt}}{suffix}",
            f"[{diff_style}]{diff:+{fmt}}{suffix}[/]",
        )

    add_comparison_row("Net Return", "net_return_pct", ".2f", "%")
    add_comparison_row("Total Trades", "total_trades", "d", "")
    add_comparison_row("Win Rate", "win_rate", ".1f", "%")
    add_comparison_row("Profit Factor", "profit_factor", ".2f", "")
    add_comparison_row("Sharpe", "sharpe", ".2f", "")
    add_comparison_row("Sortino", "sortino", ".2f", "")
    add_comparison_row("Max Drawdown", "max_drawdown_pct", ".2f", "%")
    add_comparison_row("Expectancy", "expectancy_usdt", ".2f", "")

    console.print(table)

    console.print()
    Prompt.ask(f"[{CLIColors.DIM_TEXT}]Press Enter to continue[/]")
