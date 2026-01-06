"""
Forge submenu for the CLI.

The Forge is the development environment for Plays:
- Validate single Plays
- Batch validate directories
- Run audits
- Promote Plays to production

Architecture: CLI calls tools/validation, which call pure functions.
"""

from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt
from rich.text import Text

from src.cli.styles import CLIStyles, CLIColors, CLIIcons

if TYPE_CHECKING:
    from trade_cli import TradeCLI

console = Console()


def forge_menu(cli: "TradeCLI"):
    """Forge development environment submenu."""
    from trade_cli import (
        clear_screen, print_header, get_input, get_choice, BACK,
        print_error_below_menu,
    )

    while True:
        clear_screen()
        print_header()

        # Show Forge info header
        status_line = Text()
        status_line.append("The Forge ", style=f"bold {CLIColors.NEON_CYAN}")
        status_line.append("| ", style=CLIColors.DIM_TEXT)
        status_line.append("Play development & validation environment", style=CLIColors.DIM_TEXT)
        console.print(Panel(status_line, border_style=f"dim {CLIColors.NEON_CYAN}"))

        menu = CLIStyles.create_menu_table()

        # Validation section
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- Validation ---[/]", "")
        menu.add_row("1", "Validate Play", "Validate a single Play YAML")
        menu.add_row("2", f"[bold {CLIColors.NEON_GREEN}]Validate Batch[/]", f"[{CLIColors.NEON_GREEN}]Validate all Plays in directory[/]")
        menu.add_row("3", "Validate All", "Validate all Play directories")
        menu.add_row("", "", "")

        # Audit section
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- Audits ---[/]", "")
        menu.add_row("4", "Toolkit Audit", "Validate indicator registry")
        menu.add_row("5", "Rollup Audit", "Validate price rollup parity")
        menu.add_row("", "", "")

        # Stress Tests section
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- Stress Tests ---[/]", "")
        menu.add_row("6", f"[bold {CLIColors.NEON_GREEN}]Stress Test Suite[/]", f"[{CLIColors.NEON_GREEN}]Full validation + backtest pipeline[/]")
        menu.add_row("", "", "")

        # Navigation
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- Navigation ---[/]", "")
        menu.add_row("0", "Back", "Return to main menu")

        console.print(menu)

        choice = get_choice(["0", "1", "2", "3", "4", "5", "6"])

        if choice == BACK or choice == "0":
            break

        elif choice == "1":
            _validate_single_play()

        elif choice == "2":
            _validate_batch()

        elif choice == "3":
            _validate_all()

        elif choice == "4":
            _run_toolkit_audit()

        elif choice == "5":
            _run_rollup_audit()

        elif choice == "6":
            _run_stress_test()


def _validate_single_play():
    """Validate a single Play."""
    from src.forge.validation import validate_play_file, format_validation_report
    from src.backtest.play import PLAYS_DIR

    console.print()
    play_id = Prompt.ask(
        f"[{CLIColors.NEON_CYAN}]Enter Play ID or path[/]",
        default="V_100_blocks_basic"
    )

    # Try to resolve path
    if "/" in play_id or "\\" in play_id or play_id.endswith(".yml"):
        path = play_id
    else:
        # Look in standard locations
        from pathlib import Path
        possible_paths = [
            PLAYS_DIR / f"{play_id}.yml",
            PLAYS_DIR / "_validation" / f"{play_id}.yml",
            PLAYS_DIR / "_trading" / f"{play_id}.yml",
        ]
        path = None
        for p in possible_paths:
            if p.exists():
                path = p
                break
        if path is None:
            path = PLAYS_DIR / f"{play_id}.yml"

    console.print(f"\n[{CLIColors.DIM_TEXT}]Validating: {path}[/]\n")

    result = validate_play_file(path)

    if result.is_valid:
        console.print(f"[bold {CLIColors.NEON_GREEN}]PASS[/] {result.play_id}")
    else:
        console.print(f"[bold {CLIColors.SELL_RED}]FAIL[/] {result.play_id}")
        console.print(format_validation_report(result))

    Prompt.ask("\n[dim]Press Enter to continue[/]")


def _validate_batch():
    """Validate all Plays in a directory."""
    from src.forge.validation import validate_batch, format_batch_report
    from src.backtest.play import PLAYS_DIR

    console.print()
    default_dir = str(PLAYS_DIR / "_validation")
    directory = Prompt.ask(
        f"[{CLIColors.NEON_CYAN}]Enter directory path[/]",
        default=default_dir
    )

    console.print(f"\n[{CLIColors.DIM_TEXT}]Validating directory: {directory}[/]\n")

    result = validate_batch(directory)

    console.print(format_batch_report(result, verbose=False, show_passed=True))

    Prompt.ask("\n[dim]Press Enter to continue[/]")


def _validate_all():
    """Validate all Play directories."""
    from src.forge.validation import validate_batch, format_summary_line
    from src.backtest.play import PLAYS_DIR
    from pathlib import Path

    console.print()
    console.print(f"[{CLIColors.DIM_TEXT}]Validating all Play directories...[/]\n")

    # Find all subdirectories with .yml files
    all_results = []
    directories = [
        PLAYS_DIR / "_validation",
        PLAYS_DIR / "_trading",
        PLAYS_DIR,  # Root plays directory
    ]

    for dir_path in directories:
        if dir_path.exists():
            result = validate_batch(dir_path, recursive=False)
            if result.total > 0:
                all_results.append(result)
                status = f"[{CLIColors.NEON_GREEN}]PASS[/]" if result.all_passed else f"[{CLIColors.SELL_RED}]FAIL[/]"
                console.print(f"  {status} {result.passed}/{result.total} - {dir_path.name}/")

    # Summary
    total_plays = sum(r.total for r in all_results)
    total_passed = sum(r.passed for r in all_results)
    total_failed = sum(r.failed_count for r in all_results)

    console.print()
    if total_failed == 0:
        console.print(f"[bold {CLIColors.NEON_GREEN}]ALL PASSED[/]: {total_passed}/{total_plays} Plays validated")
    else:
        console.print(f"[bold {CLIColors.SELL_RED}]FAILED[/]: {total_failed}/{total_plays} Plays have errors")

    Prompt.ask("\n[dim]Press Enter to continue[/]")


def _run_toolkit_audit():
    """Run the toolkit contract audit."""
    from src.tools.backtest_audit_tools import backtest_audit_toolkit_tool

    console.print()
    console.print(f"[{CLIColors.DIM_TEXT}]Running toolkit contract audit...[/]\n")

    result = backtest_audit_toolkit_tool()

    if result.success:
        console.print(f"[bold {CLIColors.NEON_GREEN}]PASS[/] {result.message}")
    else:
        console.print(f"[bold {CLIColors.SELL_RED}]FAIL[/] {result.error}")

    Prompt.ask("\n[dim]Press Enter to continue[/]")


def _run_rollup_audit():
    """Run the rollup parity audit."""
    from src.tools.backtest_audit_tools import backtest_audit_rollup_parity_tool

    console.print()
    console.print(f"[{CLIColors.DIM_TEXT}]Running rollup parity audit...[/]\n")

    result = backtest_audit_rollup_parity_tool()

    if result.success:
        console.print(f"[bold {CLIColors.NEON_GREEN}]PASS[/] {result.message}")
    else:
        console.print(f"[bold {CLIColors.SELL_RED}]FAIL[/] {result.error}")

    Prompt.ask("\n[dim]Press Enter to continue[/]")


def _run_stress_test():
    """Run the full stress test suite."""
    from src.tools.forge_stress_test_tools import forge_stress_test_tool

    console.print()
    console.print(f"[bold {CLIColors.NEON_CYAN}]Stress Test Suite[/]")
    console.print(f"[{CLIColors.DIM_TEXT}]Full validation + backtest pipeline with hash tracing[/]\n")

    # Options
    skip_audits = Prompt.ask(
        f"[{CLIColors.DIM_TEXT}]Skip audits?[/]",
        choices=["y", "n"],
        default="n"
    ) == "y"

    skip_backtest = Prompt.ask(
        f"[{CLIColors.DIM_TEXT}]Skip backtest?[/]",
        choices=["y", "n"],
        default="n"
    ) == "y"

    console.print(f"\n[{CLIColors.DIM_TEXT}]Running stress test suite...[/]\n")

    result = forge_stress_test_tool(
        skip_audits=skip_audits,
        skip_backtest=skip_backtest,
    )

    if result.success:
        console.print(f"[bold {CLIColors.NEON_GREEN}]PASS[/] {result.message}")

        # Show step results
        if result.data and "steps" in result.data:
            console.print()
            for step in result.data["steps"]:
                status = f"[{CLIColors.NEON_GREEN}]PASS[/]" if step["passed"] else f"[{CLIColors.SELL_RED}]FAIL[/]"
                hash_info = ""
                if step.get("output_hash"):
                    hash_info = f" [{CLIColors.DIM_TEXT}]{step['output_hash'][:8]}[/]"
                console.print(f"  {status} {step['step_name']}{hash_info} ({step['duration_seconds']:.2f}s)")

        # Show hash chain
        if result.data and "hash_chain" in result.data:
            console.print(f"\n[{CLIColors.DIM_TEXT}]Hash Chain:[/]")
            for h in result.data["hash_chain"]:
                console.print(f"  [{CLIColors.NEON_CYAN}]{h}[/]")
    else:
        console.print(f"[bold {CLIColors.SELL_RED}]FAIL[/] {result.error}")

        # Show step results on failure
        if result.data and "steps" in result.data:
            console.print()
            for step in result.data["steps"]:
                status = f"[{CLIColors.NEON_GREEN}]PASS[/]" if step["passed"] else f"[{CLIColors.SELL_RED}]FAIL[/]"
                console.print(f"  {status} {step['step_name']} ({step['duration_seconds']:.2f}s)")
                if not step["passed"] and step.get("message"):
                    console.print(f"      [{CLIColors.SELL_RED}]{step['message']}[/]")

    Prompt.ask("\n[dim]Press Enter to continue[/]")
