"""Shared helpers for CLI subcommand handlers."""

from __future__ import annotations

import json

from typing import TYPE_CHECKING

from rich.panel import Panel
from rich.table import Table

from src.cli.utils import console, BACK

if TYPE_CHECKING:
    from datetime import datetime
    from src.tools.shared import ToolResult


def _json_result(result: ToolResult) -> int:
    """Print ToolResult as JSON and return exit code.

    Standard JSON envelope for --json-output mode:
    ``{"status": "pass"|"fail", "message": "...", "data": {...}}``
    """
    output = {
        "status": "pass" if result.success else "fail",
        "message": result.message if result.success else result.error,
        "data": result.data,
    }
    print(json.dumps(output, indent=2, default=str))
    return 0 if result.success else 1


def _print_result(result: ToolResult) -> int:
    """Print OK/FAIL status line for a ToolResult and return exit code."""
    if result.success:
        console.print(f"\n[bold green]OK {result.message}[/]")
        return 0
    else:
        console.print(f"\n[bold red]FAIL {result.error}[/]")
        return 1


def _parse_datetime(dt_str: str) -> datetime:
    """Parse datetime string from CLI."""
    from datetime import datetime

    for fmt in ["%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"]:
        try:
            return datetime.strptime(dt_str, fmt)
        except ValueError:
            continue

    raise ValueError(f"Cannot parse datetime: '{dt_str}'. Use YYYY-MM-DD or YYYY-MM-DD HH:MM")


def _print_preflight_diagnostics(diag: dict):
    """Print preflight diagnostics in a formatted way.

    Reads from PreflightReport.to_dict() structure:
    - play_id, window, overall_status, tf_results, coverage, etc.
    """
    table = Table(title="Preflight Diagnostics", show_header=False, box=None)
    table.add_column("Key", style="dim", width=25)
    table.add_column("Value", style="bold")

    play_id = diag.get("play_id", "N/A")
    overall_status = diag.get("overall_status", "N/A")

    tf_results = diag.get("tf_results", {})
    first_tf_result = next(iter(tf_results.values()), {}) if tf_results else {}
    symbol = first_tf_result.get("symbol", "N/A")
    exec_tf = first_tf_result.get("tf", "N/A")

    table.add_row("Play", play_id)
    table.add_row("Symbol", symbol)
    table.add_row("Exec TF", exec_tf)
    table.add_row("Status", overall_status)

    console.print(table)

    # Window info
    console.print("\n[bold]Window:[/]")
    window = diag.get("window", {})
    if window.get("start"):
        console.print(f"  Requested: {window['start']} -> {window.get('end', 'now')}")

    warmup_req = diag.get("computed_warmup_requirements", {})
    warmup_bars = warmup_req.get("warmup_bars_exec", 0) if warmup_req else 0
    if not warmup_bars and first_tf_result:
        req_range = first_tf_result.get("required_range", {})
        warmup_bars = req_range.get("warmup_bars", 0)
    console.print(f"  Warmup: {warmup_bars} bars")

    # Coverage from first TF result
    console.print("\n[bold]DB Coverage:[/]")
    coverage = first_tf_result.get("coverage", {})
    min_ts = coverage.get("min_ts")
    max_ts = coverage.get("max_ts")
    bar_count = coverage.get("bar_count", 0)

    if min_ts and max_ts:
        console.print(f"  Range: {min_ts} -> {max_ts}")
        console.print(f"  Bars: {bar_count:,}")
    else:
        console.print("  [yellow]No data found[/]")

    coverage_ok = coverage.get("ok", False)
    coverage_style = "green" if coverage_ok else "red"
    console.print(f"  Sufficient: [{coverage_style}]{'Yes' if coverage_ok else 'No'}[/]")

    if diag.get("error_code"):
        console.print(f"  [yellow]Error: {diag['error_code']}[/]")

    errors = first_tf_result.get("errors", [])
    if errors:
        console.print("\n[bold red]Validation Errors:[/]")
        for err in errors:
            console.print(f"  [red]- {err}[/]")

    warnings = first_tf_result.get("warnings", [])
    if warnings:
        console.print("\n[bold yellow]Warnings:[/]")
        for warn in warnings:
            console.print(f"  [yellow]- {warn}[/]")
