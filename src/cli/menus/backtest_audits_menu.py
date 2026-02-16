"""
Audits & Verification submenu for the CLI.

Handles all audit and verification operations:
- Toolkit contract audit (indicator registry validation)
- Math parity audit (indicator computation validation)
- Snapshot plumbing audit (data flow validation)
- Rollup parity audit (1m price feed validation)
- Artifact parity check (output validation)

All operations call tools - no direct engine access from CLI.
"""

from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

from src.cli.styles import CLIStyles, CLIColors, CLIIcons, BillArtWrapper
from src.tools import (
    backtest_audit_toolkit_tool,
    backtest_audit_rollup_parity_tool,
    verify_artifact_parity_tool,
)
from src.tools.backtest_audit_tools import (
    backtest_math_parity_tool,
    backtest_audit_snapshot_plumbing_tool,
)

if TYPE_CHECKING:
    from trade_cli import TradeCLI

# Local console
console = Console()


def backtest_audits_menu(cli: "TradeCLI"):
    """Audits & Verification submenu."""
    from src.cli.utils import (
        clear_screen, print_header, get_choice, BACK,
    )

    while True:
        clear_screen()
        print_header()

        # Show audits info header
        status_line = Text()
        status_line.append("Audits & Verification ", style=f"bold {CLIColors.NEON_YELLOW}")
        status_line.append("│ ", style=CLIColors.DIM_TEXT)
        status_line.append("Validate indicators, math, plumbing, artifacts", style=CLIColors.DIM_TEXT)
        console.print(Panel(status_line, border_style=f"dim {CLIColors.NEON_YELLOW}"))

        menu = CLIStyles.create_menu_table()

        # Quick audits (no Play needed)
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.BOT} Quick Audits ---[/]", "")
        menu.add_row("1", f"[bold {CLIColors.NEON_GREEN}]Toolkit Contract[/]", f"[{CLIColors.NEON_GREEN}]Validate indicator registry (42 indicators)[/] [{CLIColors.DIM_TEXT}](also in Forge)[/]")
        menu.add_row("2", "Rollup Parity", f"Validate 1m price feed accumulation [{CLIColors.DIM_TEXT}](also in Forge)[/]")
        menu.add_row("", "", "")

        # Play audits (require Play selection)
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.LEDGER} Play Audits ---[/]", "")
        menu.add_row("3", "Math Parity", "Validate indicator computation for Play")
        menu.add_row("4", "Snapshot Plumbing", "Validate data flow in snapshot system")
        menu.add_row("", "", "")

        # Artifact verification
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.DATABASE} Artifact Checks ---[/]", "")
        menu.add_row("5", "Artifact Parity", "Verify run artifacts integrity")
        menu.add_row("", "", "")

        # Batch
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.TRADE} Batch ---[/]", "")
        menu.add_row("6", f"[bold {CLIColors.NEON_CYAN}]Run All Quick Audits[/]", f"[{CLIColors.NEON_CYAN}]Toolkit + Rollup[/]")
        menu.add_row("", "", "")

        # Navigation
        menu.add_row("7", f"{CLIIcons.BACK} Back", "Return to backtest menu")

        BillArtWrapper.print_menu_top()
        console.print(CLIStyles.get_menu_panel(menu, "AUDITS & VERIFICATION"))
        BillArtWrapper.print_menu_bottom()

        choice = get_choice(valid_range=range(1, 8))
        if choice is BACK:
            return  # Go back to backtest menu

        if choice == 1:
            from src.cli.menus._shared_audits import run_toolkit_audit
            run_toolkit_audit()
        elif choice == 2:
            from src.cli.menus._shared_audits import run_rollup_audit
            run_rollup_audit()
        elif choice == 3:
            _run_math_parity_audit(cli)
        elif choice == 4:
            _run_snapshot_plumbing_audit(cli)
        elif choice == 5:
            _run_artifact_parity_check()
        elif choice == 6:
            _run_all_quick_audits()
        elif choice == 7:
            return


def _run_math_parity_audit(cli: "TradeCLI"):
    """Run math parity audit for an Play."""
    from src.cli.utils import run_long_action
    from src.cli.menus.backtest_play_menu import _select_play, _get_date_range

    console.print()

    # Select Play
    play_id = _select_play("Select Play for math parity audit")
    if not play_id:
        return

    # Get date range
    start_date, end_date = _get_date_range()
    if start_date is None or end_date is None:
        return

    console.print()
    console.print(f"[{CLIColors.DIM_TEXT}]Validates indicator computation: contract + in-memory parity[/]")
    console.print()

    result = run_long_action(
        "backtest.audit_math_parity",
        backtest_math_parity_tool,
        play=play_id,
        start_date=start_date.strftime("%Y-%m-%d"),
        end_date=end_date.strftime("%Y-%m-%d"),
    )

    if result.success:
        data = result.data or {}
        console.print(f"[{CLIColors.NEON_GREEN}]{CLIIcons.SUCCESS} Math parity audit PASSED[/]")

        # Show contract results
        contract = data.get("contract_audit", {})
        console.print()
        console.print(f"  Contract audit: {contract.get('passed', 0)}/{contract.get('total', 0)} passed")

        # Show parity results
        parity = data.get("parity_audit", {})
        if parity:
            console.print(f"  Parity audit: {parity.get('total_comparisons', 0)} comparisons, {parity.get('mismatches', 0)} mismatches")
    else:
        console.print(f"[{CLIColors.NEON_RED}]{CLIIcons.ERROR} Math parity audit FAILED: {result.error}[/]")

    console.print()
    Prompt.ask(f"[{CLIColors.DIM_TEXT}]Press Enter to continue[/]")


def _run_snapshot_plumbing_audit(cli: "TradeCLI"):
    """Run snapshot plumbing audit for an Play."""
    from src.cli.utils import run_long_action
    from src.cli.menus.backtest_play_menu import _select_play, _get_date_range

    console.print()

    # Select Play
    play_id = _select_play("Select Play for snapshot plumbing audit")
    if not play_id:
        return

    # Get date range
    start_date, end_date = _get_date_range()
    if start_date is None or end_date is None:
        return

    console.print()
    console.print(f"[{CLIColors.DIM_TEXT}]Validates RuntimeSnapshotView.get_feature() data flow[/]")
    console.print()

    result = run_long_action(
        "backtest.audit_snapshot_plumbing",
        backtest_audit_snapshot_plumbing_tool,
        play_id=play_id,
        start_date=start_date.strftime("%Y-%m-%d"),
        end_date=end_date.strftime("%Y-%m-%d"),
    )

    if result.success:
        data = result.data or {}
        console.print(f"[{CLIColors.NEON_GREEN}]{CLIIcons.SUCCESS} {result.message}[/]")

        console.print()
        console.print(f"  Samples: {data.get('total_samples', 0)}")
        console.print(f"  Comparisons: {data.get('total_comparisons', 0)}")
        console.print(f"  Runtime: {data.get('runtime_seconds', 0):.1f}s")
    else:
        console.print(f"[{CLIColors.NEON_RED}]{CLIIcons.ERROR} Snapshot plumbing audit FAILED: {result.error}[/]")

    console.print()
    Prompt.ask(f"[{CLIColors.DIM_TEXT}]Press Enter to continue[/]")


def _run_artifact_parity_check():
    """Run artifact parity verification."""
    from pathlib import Path

    console.print()
    console.print(f"[{CLIColors.NEON_CYAN}]Artifact Parity Check[/]")
    console.print(f"[{CLIColors.DIM_TEXT}]Enter the path to a backtest run folder to verify artifacts[/]")
    console.print()

    run_path = Prompt.ask(f"[{CLIColors.NEON_CYAN}]Run folder path[/]")

    if not run_path:
        return

    run_dir = Path(run_path)
    if not run_dir.exists():
        console.print(f"[{CLIColors.NEON_RED}]Path does not exist: {run_path}[/]")
        Prompt.ask(f"[{CLIColors.DIM_TEXT}]Press Enter to continue[/]")
        return

    console.print()
    console.print(f"[{CLIColors.NEON_CYAN}]Verifying artifacts in {run_dir}...[/]")

    result = verify_artifact_parity_tool(run_dir=run_dir)

    if result.success:
        console.print(f"[{CLIColors.NEON_GREEN}]{CLIIcons.SUCCESS} {result.message}[/]")
    else:
        console.print(f"[{CLIColors.NEON_RED}]{CLIIcons.ERROR} Artifact parity FAILED: {result.error}[/]")

    console.print()
    Prompt.ask(f"[{CLIColors.DIM_TEXT}]Press Enter to continue[/]")


def _run_all_quick_audits():
    """Run all quick audits (no Play/data needed)."""
    console.print()
    console.print(f"[bold {CLIColors.NEON_CYAN}]Running All Quick Audits[/]")
    console.print(f"[{CLIColors.DIM_TEXT}]These audits use synthetic data and don't require a Play[/]")
    console.print(f"[{CLIColors.DIM_TEXT}]For full validation use: python trade_cli.py validate standard[/]")
    console.print()

    all_passed = True

    # Toolkit audit
    console.print(f"[{CLIColors.NEON_CYAN}]1/2 Toolkit Contract Audit...[/]")
    toolkit_result = backtest_audit_toolkit_tool()
    if toolkit_result.success:
        console.print(f"    [{CLIColors.NEON_GREEN}]{CLIIcons.SUCCESS} PASSED[/]")
    else:
        console.print(f"    [{CLIColors.NEON_RED}]{CLIIcons.ERROR} FAILED: {toolkit_result.error}[/]")
        all_passed = False

    # Rollup audit
    console.print(f"[{CLIColors.NEON_CYAN}]2/2 Rollup Parity Audit...[/]")
    rollup_result = backtest_audit_rollup_parity_tool()
    if rollup_result.success:
        console.print(f"    [{CLIColors.NEON_GREEN}]{CLIIcons.SUCCESS} PASSED[/]")
    else:
        console.print(f"    [{CLIColors.NEON_RED}]{CLIIcons.ERROR} FAILED: {rollup_result.error}[/]")
        all_passed = False

    # Summary
    console.print()
    if all_passed:
        console.print(f"[bold {CLIColors.NEON_GREEN}]{CLIIcons.SUCCESS} All quick audits PASSED[/]")
    else:
        console.print(f"[bold {CLIColors.NEON_RED}]{CLIIcons.ERROR} Some audits FAILED[/]")

    console.print()
    Prompt.ask(f"[{CLIColors.DIM_TEXT}]Press Enter to continue[/]")
