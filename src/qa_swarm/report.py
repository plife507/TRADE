"""
Report Generation - Formats QA audit results for output.

Supports multiple output formats:
- Rich console output with colors and tables
- JSON structured output
- Markdown export for documentation
"""

import json
from datetime import datetime
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .types import (
    Severity,
    FindingCategory,
    Finding,
    AgentReport,
    AggregatedReport,
)


# Severity colors for Rich console
SEVERITY_COLORS = {
    Severity.CRITICAL: "bold red",
    Severity.HIGH: "red",
    Severity.MEDIUM: "yellow",
    Severity.LOW: "dim",
}

# Category display names
CATEGORY_NAMES = {
    FindingCategory.SECURITY: "Security",
    FindingCategory.TYPE_SAFETY: "Type Safety",
    FindingCategory.ERROR_HANDLING: "Error Handling",
    FindingCategory.CONCURRENCY: "Concurrency",
    FindingCategory.BUSINESS_LOGIC: "Business Logic",
    FindingCategory.API_CONTRACT: "API Contract",
    FindingCategory.DOCUMENTATION: "Documentation",
    FindingCategory.DEAD_CODE: "Dead Code",
}


def format_report_rich(
    report: AggregatedReport,
    console: Console | None = None,
    verbose: bool = False,
    max_findings: int = 50,
) -> None:
    """
    Format and print report using Rich console.

    Args:
        report: The aggregated report to display
        console: Rich console instance (default: create new)
        verbose: Show all details including code snippets
        max_findings: Maximum findings to show (default: 50)
    """
    if console is None:
        console = Console()

    # Header
    status_color = "green" if report.pass_status else "red"
    status_text = "PASS" if report.pass_status else "FAIL"

    console.print()
    console.print(Panel(
        f"[bold {status_color}]QA AUDIT REPORT - {status_text}[/]",
        border_style=status_color,
    ))

    # Summary stats
    console.print(f"\n[bold]Summary:[/] {report.summary}")
    console.print(f"[dim]Timestamp: {report.timestamp.isoformat()}[/]")
    console.print(f"[dim]Files scanned: {report.total_files_scanned}[/]")
    console.print(f"[dim]Execution time: {report.execution_time_ms}ms[/]")

    # Severity breakdown table
    console.print("\n[bold]Findings by Severity:[/]")
    severity_table = Table(show_header=True, header_style="bold")
    severity_table.add_column("Severity", width=12)
    severity_table.add_column("Count", justify="right", width=8)

    for severity in Severity:
        count = report.findings_by_severity.get(severity.value, 0)
        color = SEVERITY_COLORS[severity]
        severity_table.add_row(
            Text(severity.value, style=color),
            str(count),
        )

    console.print(severity_table)

    # Category breakdown table
    console.print("\n[bold]Findings by Category:[/]")
    category_table = Table(show_header=True, header_style="bold")
    category_table.add_column("Category", width=20)
    category_table.add_column("Count", justify="right", width=8)

    for category in FindingCategory:
        count = report.findings_by_category.get(category.value, 0)
        if count > 0:
            category_table.add_row(
                CATEGORY_NAMES[category],
                str(count),
            )

    console.print(category_table)

    # Agent status table
    console.print("\n[bold]Agent Status:[/]")
    agent_table = Table(show_header=True, header_style="bold")
    agent_table.add_column("Agent", width=25)
    agent_table.add_column("Status", width=10)
    agent_table.add_column("Files", justify="right", width=8)
    agent_table.add_column("Findings", justify="right", width=10)
    agent_table.add_column("Time (ms)", justify="right", width=10)

    for agent_report in report.agent_reports:
        status = "[green]OK[/]" if agent_report.success else f"[red]FAIL[/]"
        agent_table.add_row(
            agent_report.agent_name,
            status,
            str(agent_report.files_scanned),
            str(agent_report.finding_count),
            str(agent_report.execution_time_ms),
        )

    console.print(agent_table)

    # Findings list
    findings_to_show = report.prioritized_findings[:max_findings]
    if findings_to_show:
        console.print(f"\n[bold]Top {len(findings_to_show)} Findings:[/]")

        for finding in findings_to_show:
            _print_finding(console, finding, verbose)

    if len(report.prioritized_findings) > max_findings:
        remaining = len(report.prioritized_findings) - max_findings
        console.print(f"\n[dim]... and {remaining} more findings not shown[/]")

    # Footer
    console.print()
    console.print(Panel(
        f"[bold]Total: {report.total_findings} findings | "
        f"Pass: {report.pass_status}[/]",
        border_style=status_color,
    ))


def _print_finding(console: Console, finding: Finding, verbose: bool) -> None:
    """Print a single finding."""
    color = SEVERITY_COLORS[finding.severity]

    # Header line
    console.print(
        f"\n[{color}][{finding.severity.value}][/] "
        f"[bold]{finding.id}[/]: {finding.title}"
    )

    # Location
    loc = finding.file_path
    if finding.line_number:
        loc += f":{finding.line_number}"
    console.print(f"  [dim]Location: {loc}[/]")

    if verbose:
        # Description
        console.print(f"  [dim]Description:[/] {finding.description}")

        # Code snippet
        if finding.code_snippet:
            console.print(f"  [dim]Code:[/] {finding.code_snippet}")

        # Recommendation
        if finding.recommendation:
            console.print(f"  [dim]Fix:[/] {finding.recommendation}")


def format_report_json(report: AggregatedReport, indent: int = 2) -> str:
    """
    Format report as JSON string.

    Args:
        report: The aggregated report
        indent: JSON indentation (default: 2)

    Returns:
        JSON string
    """
    return json.dumps(report.to_dict(), indent=indent, default=str)


def format_report_markdown(
    report: AggregatedReport,
    max_findings: int = 100,
) -> str:
    """
    Format report as Markdown.

    Args:
        report: The aggregated report
        max_findings: Maximum findings to include

    Returns:
        Markdown string
    """
    lines: list[str] = []

    # Header
    status = "PASS" if report.pass_status else "FAIL"
    lines.append(f"# QA Audit Report - {status}")
    lines.append("")
    lines.append(f"**Generated:** {report.timestamp.isoformat()}")
    lines.append(f"**Files Scanned:** {report.total_files_scanned}")
    lines.append(f"**Total Findings:** {report.total_findings}")
    lines.append(f"**Execution Time:** {report.execution_time_ms}ms")
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append("")
    lines.append(report.summary)
    lines.append("")

    # Severity breakdown
    lines.append("## Findings by Severity")
    lines.append("")
    lines.append("| Severity | Count |")
    lines.append("|----------|-------|")
    for severity in Severity:
        count = report.findings_by_severity.get(severity.value, 0)
        lines.append(f"| {severity.value} | {count} |")
    lines.append("")

    # Category breakdown
    lines.append("## Findings by Category")
    lines.append("")
    lines.append("| Category | Count |")
    lines.append("|----------|-------|")
    for category in FindingCategory:
        count = report.findings_by_category.get(category.value, 0)
        if count > 0:
            lines.append(f"| {CATEGORY_NAMES[category]} | {count} |")
    lines.append("")

    # Agent status
    lines.append("## Agent Status")
    lines.append("")
    lines.append("| Agent | Status | Files | Findings | Time (ms) |")
    lines.append("|-------|--------|-------|----------|-----------|")
    for agent_report in report.agent_reports:
        status = "OK" if agent_report.success else "FAIL"
        lines.append(
            f"| {agent_report.agent_name} | {status} | "
            f"{agent_report.files_scanned} | {agent_report.finding_count} | "
            f"{agent_report.execution_time_ms} |"
        )
    lines.append("")

    # Findings
    findings_to_show = report.prioritized_findings[:max_findings]
    if findings_to_show:
        lines.append("## Findings")
        lines.append("")

        for finding in findings_to_show:
            lines.append(f"### {finding.id}: {finding.title}")
            lines.append("")
            lines.append(f"- **Severity:** {finding.severity.value}")
            lines.append(f"- **Category:** {CATEGORY_NAMES[finding.category]}")
            loc = finding.file_path
            if finding.line_number:
                loc += f":{finding.line_number}"
            lines.append(f"- **Location:** `{loc}`")
            lines.append("")
            lines.append(finding.description)
            lines.append("")

            if finding.code_snippet:
                lines.append("**Code:**")
                lines.append("```python")
                lines.append(finding.code_snippet)
                lines.append("```")
                lines.append("")

            if finding.recommendation:
                lines.append(f"**Recommendation:** {finding.recommendation}")
                lines.append("")

    if len(report.prioritized_findings) > max_findings:
        remaining = len(report.prioritized_findings) - max_findings
        lines.append(f"*... and {remaining} more findings not shown*")
        lines.append("")

    return "\n".join(lines)


def format_summary_line(report: AggregatedReport) -> str:
    """
    Format a single-line summary.

    Args:
        report: The aggregated report

    Returns:
        Single line summary string
    """
    status = "PASS" if report.pass_status else "FAIL"
    critical = report.findings_by_severity.get("CRITICAL", 0)
    high = report.findings_by_severity.get("HIGH", 0)

    parts = [f"[{status}]", f"{report.total_findings} findings"]

    if critical > 0:
        parts.append(f"{critical} critical")
    if high > 0:
        parts.append(f"{high} high")

    parts.append(f"({report.execution_time_ms}ms)")

    return " | ".join(parts)


def save_report(
    report: AggregatedReport,
    output_path: str,
    format: str = "json",
) -> None:
    """
    Save report to a file.

    Args:
        report: The aggregated report
        output_path: Path to save the report
        format: Output format (json, markdown, md)
    """
    if format == "json":
        content = format_report_json(report)
    elif format in ("markdown", "md"):
        content = format_report_markdown(report)
    else:
        raise ValueError(f"Unknown format: {format}")

    with open(output_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
