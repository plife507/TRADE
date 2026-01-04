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
from rich.table import Table
from rich.prompt import Prompt
from rich.text import Text

from src.cli.styles import CLIStyles, CLIColors, CLIIcons, BillArtWrapper
from src.tools import (
    backtest_audit_toolkit_tool,
    backtest_audit_rollup_parity_tool,
    verify_artifact_parity_tool,
)
from src.tools.backtest_cli_wrapper import (
    backtest_math_parity_tool,
    backtest_audit_snapshot_plumbing_tool,
)

if TYPE_CHECKING:
    from trade_cli import TradeCLI

# Local console
console = Console()


def backtest_audits_menu(cli: "TradeCLI"):
    """Audits & Verification submenu."""
    from trade_cli import (
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
        menu.add_row("1", f"[bold {CLIColors.NEON_GREEN}]Toolkit Contract[/]", f"[{CLIColors.NEON_GREEN}]Validate indicator registry (42 indicators)[/]")
        menu.add_row("2", "Rollup Parity", "Validate 1m price feed accumulation")
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

        # Stage 4: Rule evaluation
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.BOT} Stage 4: Rules ---[/]", "")
        menu.add_row("6", "Rule Evaluation", "Validate compiled resolver + operator semantics")
        menu.add_row("7", "Structure Smoke", "Validate swing/trend detection + snapshot access")
        menu.add_row("", "", "")

        # Batch
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.TRADE} Batch ---[/]", "")
        menu.add_row("8", f"[bold {CLIColors.NEON_CYAN}]Run All Quick Audits[/]", f"[{CLIColors.NEON_CYAN}]Toolkit + Rollup + Rules + Structure[/]")
        menu.add_row("", "", "")

        # Navigation
        menu.add_row("9", f"{CLIIcons.BACK} Back", "Return to backtest menu")

        BillArtWrapper.print_menu_top()
        console.print(CLIStyles.get_menu_panel(menu, "AUDITS & VERIFICATION"))
        BillArtWrapper.print_menu_bottom()

        choice = get_choice(valid_range=range(1, 10))
        if choice is BACK:
            return  # Go back to backtest menu

        if choice == 1:
            _run_toolkit_audit()
        elif choice == 2:
            _run_rollup_audit()
        elif choice == 3:
            _run_math_parity_audit(cli)
        elif choice == 4:
            _run_snapshot_plumbing_audit(cli)
        elif choice == 5:
            _run_artifact_parity_check()
        elif choice == 6:
            _run_rules_smoke()
        elif choice == 7:
            _run_structure_smoke()
        elif choice == 8:
            _run_all_quick_audits()
        elif choice == 9:
            return


def _run_toolkit_audit():
    """Run toolkit contract audit."""
    from trade_cli import run_long_action

    console.print()
    console.print(f"[{CLIColors.DIM_TEXT}]Validates all 42 indicators produce exactly registry-declared outputs[/]")
    console.print()

    result = run_long_action("backtest.audit_toolkit", backtest_audit_toolkit_tool)

    if result.success:
        data = result.data or {}
        console.print(f"[{CLIColors.NEON_GREEN}]{CLIIcons.SUCCESS} {result.message}[/]")

        # Show summary
        console.print()
        console.print(f"  Indicators tested: {data.get('total_indicators', 0)}")
        console.print(f"  Passed: [{CLIColors.NEON_GREEN}]{data.get('passed_indicators', 0)}[/]")
        console.print(f"  Failed: [{CLIColors.NEON_RED}]{data.get('failed_indicators', 0)}[/]")
        console.print(f"  With extras dropped: {data.get('indicators_with_extras', 0)}")
    else:
        console.print(f"[{CLIColors.NEON_RED}]{CLIIcons.ERROR} Toolkit audit FAILED[/]")
        console.print(f"[{CLIColors.NEON_RED}]{result.error}[/]")

        # Show failures if available
        data = result.data or {}
        if "failures" in data:
            console.print()
            console.print(f"[{CLIColors.NEON_YELLOW}]Failures:[/]")
            for failure in data["failures"][:5]:  # Show first 5
                console.print(f"  - {failure}")

    console.print()
    Prompt.ask(f"[{CLIColors.DIM_TEXT}]Press Enter to continue[/]")


def _run_rollup_audit():
    """Run rollup parity audit."""
    from trade_cli import run_long_action

    console.print()
    console.print(f"[{CLIColors.DIM_TEXT}]Validates 1m price feed accumulation and zone touch detection[/]")
    console.print()

    result = run_long_action("backtest.audit_rollup", backtest_audit_rollup_parity_tool)

    if result.success:
        data = result.data or {}
        console.print(f"[{CLIColors.NEON_GREEN}]{CLIIcons.SUCCESS} {result.message}[/]")

        console.print()
        console.print(f"  Intervals tested: {data.get('n_intervals', 0)}")
        console.print(f"  Comparisons: {data.get('total_comparisons', 0)}")
        console.print(f"  Mismatches: {data.get('mismatches', 0)}")
    else:
        console.print(f"[{CLIColors.NEON_RED}]{CLIIcons.ERROR} Rollup audit FAILED: {result.error}[/]")

    console.print()
    Prompt.ask(f"[{CLIColors.DIM_TEXT}]Press Enter to continue[/]")


def _run_math_parity_audit(cli: "TradeCLI"):
    """Run math parity audit for an Play."""
    from trade_cli import run_long_action
    from src.cli.menus.backtest_play_menu import _select_play, _get_date_range

    console.print()

    # Select Play
    play_id = _select_play("Select Play for math parity audit")
    if not play_id:
        return

    # Get date range
    start_date, end_date = _get_date_range()
    if start_date is None:
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
    from trade_cli import run_long_action
    from src.cli.menus.backtest_play_menu import _select_play, _get_date_range

    console.print()

    # Select Play
    play_id = _select_play("Select Play for snapshot plumbing audit")
    if not play_id:
        return

    # Get date range
    start_date, end_date = _get_date_range()
    if start_date is None:
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


def _run_rules_smoke():
    """Run rule evaluation smoke test (Stage 4)."""
    from rich.prompt import Prompt
    from src.cli.smoke_tests import run_rules_smoke

    console.print()
    console.print(f"[{CLIColors.NEON_CYAN}]Rule Evaluation Smoke Test (Stage 4)[/]")
    console.print(f"[{CLIColors.DIM_TEXT}]Validates compiled resolver + operator semantics[/]")
    console.print()

    failures = run_rules_smoke()

    if failures == 0:
        console.print(f"\n[{CLIColors.NEON_GREEN}]{CLIIcons.SUCCESS} Rule evaluation smoke PASSED[/]")
    else:
        console.print(f"\n[{CLIColors.NEON_RED}]{CLIIcons.ERROR} Rule evaluation smoke FAILED: {failures} failure(s)[/]")

    console.print()
    Prompt.ask(f"[{CLIColors.DIM_TEXT}]Press Enter to continue[/]")


def _run_structure_smoke():
    """Run market structure smoke test (Stage 2)."""
    from rich.prompt import Prompt
    from src.cli.smoke_tests import run_structure_smoke

    console.print()
    console.print(f"[{CLIColors.NEON_CYAN}]Market Structure Smoke Test (Stage 2)[/]")
    console.print(f"[{CLIColors.DIM_TEXT}]Validates swing/trend detection + snapshot.get() access[/]")
    console.print()

    failures = run_structure_smoke()

    if failures == 0:
        console.print(f"\n[{CLIColors.NEON_GREEN}]{CLIIcons.SUCCESS} Structure smoke PASSED[/]")
    else:
        console.print(f"\n[{CLIColors.NEON_RED}]{CLIIcons.ERROR} Structure smoke FAILED: {failures} failure(s)[/]")

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
    from src.cli.smoke_tests import run_rules_smoke, run_structure_smoke

    console.print()
    console.print(f"[bold {CLIColors.NEON_CYAN}]Running All Quick Audits[/]")
    console.print(f"[{CLIColors.DIM_TEXT}]These audits use synthetic data and don't require an Play[/]")
    console.print()

    all_passed = True
    total_failures = 0

    # Toolkit audit
    console.print(f"[{CLIColors.NEON_CYAN}]1/4 Toolkit Contract Audit...[/]")
    toolkit_result = backtest_audit_toolkit_tool()
    if toolkit_result.success:
        console.print(f"    [{CLIColors.NEON_GREEN}]{CLIIcons.SUCCESS} PASSED[/]")
    else:
        console.print(f"    [{CLIColors.NEON_RED}]{CLIIcons.ERROR} FAILED: {toolkit_result.error}[/]")
        all_passed = False

    # Rollup audit
    console.print(f"[{CLIColors.NEON_CYAN}]2/4 Rollup Parity Audit...[/]")
    rollup_result = backtest_audit_rollup_parity_tool()
    if rollup_result.success:
        console.print(f"    [{CLIColors.NEON_GREEN}]{CLIIcons.SUCCESS} PASSED[/]")
    else:
        console.print(f"    [{CLIColors.NEON_RED}]{CLIIcons.ERROR} FAILED: {rollup_result.error}[/]")
        all_passed = False

    # Rules smoke (Stage 4)
    console.print(f"[{CLIColors.NEON_CYAN}]3/4 Rule Evaluation Smoke (Stage 4)...[/]")
    rules_failures = run_rules_smoke()
    total_failures += rules_failures
    if rules_failures == 0:
        console.print(f"    [{CLIColors.NEON_GREEN}]{CLIIcons.SUCCESS} PASSED[/]")
    else:
        console.print(f"    [{CLIColors.NEON_RED}]{CLIIcons.ERROR} FAILED: {rules_failures} failure(s)[/]")
        all_passed = False

    # Structure smoke (Stage 2)
    console.print(f"[{CLIColors.NEON_CYAN}]4/4 Market Structure Smoke (Stage 2)...[/]")
    structure_failures = run_structure_smoke()
    total_failures += structure_failures
    if structure_failures == 0:
        console.print(f"    [{CLIColors.NEON_GREEN}]{CLIIcons.SUCCESS} PASSED[/]")
    else:
        console.print(f"    [{CLIColors.NEON_RED}]{CLIIcons.ERROR} FAILED: {structure_failures} failure(s)[/]")
        all_passed = False

    # Summary
    console.print()
    if all_passed:
        console.print(f"[bold {CLIColors.NEON_GREEN}]{CLIIcons.SUCCESS} All quick audits PASSED[/]")
    else:
        console.print(f"[bold {CLIColors.NEON_RED}]{CLIIcons.ERROR} Some audits FAILED ({total_failures} total failures)[/]")

    console.print()
    Prompt.ask(f"[{CLIColors.DIM_TEXT}]Press Enter to continue[/]")
