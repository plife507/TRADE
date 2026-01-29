"""
QA Orchestration Agent Swarm - Multi-agent code quality evaluation.

Provides production-grade QA orchestration using parallel specialist agents
to evaluate code readiness across security, type safety, error handling,
concurrency, business logic, API contracts, documentation, and dead code.

Usage:
    from src.qa_swarm import run_qa_audit, QAAuditConfig

    # Full audit
    report = await run_qa_audit()

    # Audit specific paths
    config = QAAuditConfig(paths=["src/core/"])
    report = await run_qa_audit(config)

    # Filter by severity
    config = QAAuditConfig(min_severity=Severity.HIGH)
    report = await run_qa_audit(config)
"""

from .types import (
    Severity,
    FindingCategory,
    Finding,
    AgentReport,
    AggregatedReport,
    QAAuditConfig,
)
from .orchestrator import run_qa_audit, run_qa_audit_sync, QAOrchestrator
from .report import (
    format_report_rich,
    format_report_json,
    format_report_markdown,
    format_summary_line,
    save_report,
)

__all__ = [
    # Types
    "Severity",
    "FindingCategory",
    "Finding",
    "AgentReport",
    "AggregatedReport",
    "QAAuditConfig",
    # Orchestrator
    "run_qa_audit",
    "run_qa_audit_sync",
    "QAOrchestrator",
    # Report formatting
    "format_report_rich",
    "format_report_json",
    "format_report_markdown",
    "format_summary_line",
    "save_report",
]
