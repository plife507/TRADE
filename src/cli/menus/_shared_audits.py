"""
Shared audit runner functions used by both Forge and Backtest Audits menus.

Extracts the common toolkit and rollup audit implementations so both menus
call the same code path.
"""

from rich.console import Console
from rich.prompt import Prompt

from src.cli.styles import CLIColors, CLIIcons
from src.tools import (
    backtest_audit_toolkit_tool,
    backtest_audit_rollup_parity_tool,
)

console = Console()


def run_toolkit_audit() -> None:
    """Run toolkit contract audit (indicator registry validation)."""
    from src.cli.utils import run_long_action

    console.print()
    console.print(f"[{CLIColors.DIM_TEXT}]Validates all 42 indicators produce exactly registry-declared outputs[/]")
    console.print()

    result = run_long_action("backtest.audit_toolkit", backtest_audit_toolkit_tool)

    if result.success:
        data = result.data or {}
        console.print(f"[{CLIColors.NEON_GREEN}]{CLIIcons.SUCCESS} {result.message}[/]")

        console.print()
        console.print(f"  Indicators tested: {data.get('total_indicators', 0)}")
        console.print(f"  Passed: [{CLIColors.NEON_GREEN}]{data.get('passed_indicators', 0)}[/]")
        console.print(f"  Failed: [{CLIColors.NEON_RED}]{data.get('failed_indicators', 0)}[/]")
        console.print(f"  With extras dropped: {data.get('indicators_with_extras', 0)}")
    else:
        console.print(f"[{CLIColors.NEON_RED}]{CLIIcons.ERROR} Toolkit audit FAILED[/]")
        console.print(f"[{CLIColors.NEON_RED}]{result.error}[/]")

        data = result.data or {}
        if "failures" in data:
            console.print()
            console.print(f"[{CLIColors.NEON_YELLOW}]Failures:[/]")
            for failure in data["failures"][:5]:
                console.print(f"  - {failure}")

    console.print()
    Prompt.ask(f"[{CLIColors.DIM_TEXT}]Press Enter to continue[/]")


def run_rollup_audit() -> None:
    """Run rollup parity audit (1m price feed accumulation validation)."""
    from src.cli.utils import run_long_action

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
