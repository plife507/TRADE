"""
QA Audit Smoke Test - Quick validation of QA swarm functionality.

Runs a limited audit on critical paths to verify the QA system is working.
"""

from rich.console import Console
from rich.panel import Panel

console = Console()


def run_qa_audit_smoke() -> int:
    """
    Run QA audit smoke test.

    Quick validation that:
    1. QA swarm module loads correctly
    2. Agents can be instantiated
    3. Audit can run on a small subset of files
    4. Report generation works

    Returns:
        Exit code: 0 for success, non-zero for failure
    """
    console.print(Panel(
        "[bold]QA AUDIT SMOKE TEST[/]\n"
        "[dim]Quick validation of QA swarm functionality[/]",
        border_style="cyan"
    ))

    failures = 0

    # Test 1: Module import
    console.print("\n[bold cyan]1. Module Import[/]")
    try:
        from src.qa_swarm import (
            run_qa_audit_sync,
            QAAuditConfig,
            Severity,
            FindingCategory,
            format_report_rich,
            format_summary_line,
        )
        from src.qa_swarm.agents import AGENT_REGISTRY
        console.print(f"  [green]OK[/] Imported QA swarm module")
        console.print(f"  [dim]Registered agents: {len(AGENT_REGISTRY)}[/]")
    except Exception as e:
        console.print(f"  [red]FAIL[/] Import failed: {e}")
        failures += 1
        return failures

    # Test 2: Agent registry
    console.print("\n[bold cyan]2. Agent Registry[/]")
    expected_agents = [
        "security_auditor",
        "type_safety_checker",
        "error_handler_reviewer",
        "concurrency_auditor",
        "business_logic_validator",
        "api_contract_checker",
        "documentation_auditor",
        "dead_code_detector",
    ]
    for agent_name in expected_agents:
        if agent_name in AGENT_REGISTRY:
            console.print(f"  [green]OK[/] {agent_name}")
        else:
            console.print(f"  [red]FAIL[/] {agent_name} not registered")
            failures += 1

    # Test 3: Quick audit on limited path
    console.print("\n[bold cyan]3. Quick Audit (src/qa_swarm only)[/]")
    try:
        config = QAAuditConfig(
            paths=["src/qa_swarm/"],
            min_severity=Severity.LOW,
            categories=[FindingCategory.TYPE_SAFETY, FindingCategory.DOCUMENTATION],
            parallel=True,
            timeout_seconds=60,
            max_findings_per_agent=10,
        )
        report = run_qa_audit_sync(config)

        console.print(f"  [green]OK[/] Audit completed")
        console.print(f"  [dim]Files scanned: {report.total_files_scanned}[/]")
        console.print(f"  [dim]Findings: {report.total_findings}[/]")
        console.print(f"  [dim]Execution time: {report.execution_time_ms}ms[/]")

        # Check agent reports
        successful_agents = sum(1 for r in report.agent_reports if r.success)
        console.print(f"  [dim]Successful agents: {successful_agents}/{len(report.agent_reports)}[/]")

    except Exception as e:
        console.print(f"  [red]FAIL[/] Audit failed: {e}")
        failures += 1

    # Test 4: Report formatting
    console.print("\n[bold cyan]4. Report Formatting[/]")
    try:
        summary = format_summary_line(report)
        console.print(f"  [green]OK[/] Summary: {summary}")
    except Exception as e:
        console.print(f"  [red]FAIL[/] Report formatting failed: {e}")
        failures += 1

    # Summary
    console.print(f"\n[bold]QA Audit Smoke Test Complete[/]")
    console.print(f"  Total failures: {failures}")

    return failures
