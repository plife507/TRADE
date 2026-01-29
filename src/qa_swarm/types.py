"""
QA Swarm Types - Data structures for findings, reports, and configuration.

All types use modern Python 3.12+ patterns:
- Dataclasses with slots for efficiency
- Type hints throughout
- X | None instead of Optional[X]
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import hashlib
import json


class Severity(str, Enum):
    """Finding severity levels, ordered from most to least severe."""
    CRITICAL = "CRITICAL"  # Security holes, fund safety, data loss
    HIGH = "HIGH"          # Bugs likely to cause failures
    MEDIUM = "MEDIUM"      # Code quality, potential bugs
    LOW = "LOW"            # Style, minor improvements

    def __lt__(self, other: "Severity") -> bool:
        order = [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]
        return order.index(self) < order.index(other)

    def __le__(self, other: "Severity") -> bool:
        return self == other or self < other


class FindingCategory(str, Enum):
    """Categories of findings, each corresponding to a specialist agent."""
    SECURITY = "security"
    TYPE_SAFETY = "type_safety"
    ERROR_HANDLING = "error_handling"
    CONCURRENCY = "concurrency"
    BUSINESS_LOGIC = "business_logic"
    API_CONTRACT = "api_contract"
    DOCUMENTATION = "documentation"
    DEAD_CODE = "dead_code"


@dataclass(slots=True)
class Finding:
    """
    A single finding from a QA agent.

    Attributes:
        id: Unique identifier (e.g., "SEC-001", "TYPE-042")
        category: Which specialist found this
        severity: Impact level
        title: Short description (one line)
        description: Full explanation of the issue
        file_path: Absolute path to the file
        line_number: Line number if known
        code_snippet: Relevant code context
        recommendation: How to fix the issue
        effort_estimate: trivial, small, medium, large
    """
    id: str
    category: FindingCategory
    severity: Severity
    title: str
    description: str
    file_path: str
    line_number: int | None = None
    code_snippet: str | None = None
    recommendation: str | None = None
    effort_estimate: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "category": self.category.value,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "code_snippet": self.code_snippet,
            "recommendation": self.recommendation,
            "effort_estimate": self.effort_estimate,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Finding":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            category=FindingCategory(data["category"]),
            severity=Severity(data["severity"]),
            title=data["title"],
            description=data["description"],
            file_path=data["file_path"],
            line_number=data.get("line_number"),
            code_snippet=data.get("code_snippet"),
            recommendation=data.get("recommendation"),
            effort_estimate=data.get("effort_estimate"),
        )

    def location_key(self) -> str:
        """Generate a key for deduplication based on location."""
        return f"{self.file_path}:{self.line_number or 0}:{self.title}"


@dataclass(slots=True)
class AgentReport:
    """
    Report from a single specialist agent.

    Attributes:
        agent_name: Name of the agent (e.g., "security_auditor")
        category: Finding category this agent covers
        findings: List of findings from this agent
        files_scanned: Number of files examined
        execution_time_ms: How long the agent took
        error_message: Error if agent failed
    """
    agent_name: str
    category: FindingCategory
    findings: list[Finding] = field(default_factory=list)
    files_scanned: int = 0
    execution_time_ms: int = 0
    error_message: str | None = None

    @property
    def success(self) -> bool:
        """True if agent completed without error."""
        return self.error_message is None

    @property
    def finding_count(self) -> int:
        """Total number of findings."""
        return len(self.findings)

    def findings_by_severity(self) -> dict[str, int]:
        """Count findings by severity level."""
        counts = {s.value: 0 for s in Severity}
        for finding in self.findings:
            counts[finding.severity.value] += 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "agent_name": self.agent_name,
            "category": self.category.value,
            "findings": [f.to_dict() for f in self.findings],
            "files_scanned": self.files_scanned,
            "execution_time_ms": self.execution_time_ms,
            "error_message": self.error_message,
            "success": self.success,
            "finding_count": self.finding_count,
        }


@dataclass(slots=True)
class AggregatedReport:
    """
    Final aggregated report from all agents.

    Attributes:
        timestamp: When the audit was run
        total_files_scanned: Sum of files examined across agents
        total_findings: Total number of findings
        findings_by_severity: Count per severity level
        findings_by_category: Count per category
        prioritized_findings: All findings sorted by priority
        agent_reports: Individual reports from each agent
        execution_time_ms: Total wall-clock time
        summary: Executive summary paragraph
        config: Configuration used for this audit
    """
    timestamp: datetime
    total_files_scanned: int
    total_findings: int
    findings_by_severity: dict[str, int]
    findings_by_category: dict[str, int]
    prioritized_findings: list[Finding]
    agent_reports: list[AgentReport]
    execution_time_ms: int
    summary: str
    config: "QAAuditConfig | None" = None

    @property
    def has_critical(self) -> bool:
        """True if any critical findings exist."""
        return self.findings_by_severity.get("CRITICAL", 0) > 0

    @property
    def has_high(self) -> bool:
        """True if any high-severity findings exist."""
        return self.findings_by_severity.get("HIGH", 0) > 0

    @property
    def pass_status(self) -> bool:
        """True if audit passes (no critical or high findings)."""
        return not self.has_critical and not self.has_high

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "total_files_scanned": self.total_files_scanned,
            "total_findings": self.total_findings,
            "findings_by_severity": self.findings_by_severity,
            "findings_by_category": self.findings_by_category,
            "prioritized_findings": [f.to_dict() for f in self.prioritized_findings],
            "agent_reports": [r.to_dict() for r in self.agent_reports],
            "execution_time_ms": self.execution_time_ms,
            "summary": self.summary,
            "pass_status": self.pass_status,
            "config": self.config.to_dict() if self.config else None,
        }

    def compute_hash(self) -> str:
        """Compute a hash of the report for caching/comparison."""
        data = {
            "timestamp": self.timestamp.isoformat(),
            "total_findings": self.total_findings,
            "findings": [f.to_dict() for f in self.prioritized_findings],
        }
        serialized = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()[:12]


@dataclass
class QAAuditConfig:
    """
    Configuration for a QA audit run.

    Attributes:
        paths: Specific paths to audit (default: full codebase)
        min_severity: Minimum severity to report (default: LOW)
        categories: Categories to run (default: all)
        parallel: Run agents in parallel (default: True)
        timeout_seconds: Timeout per agent (default: 300)
        max_findings_per_agent: Limit findings per agent (default: 100)
        include_snippets: Include code snippets in findings (default: True)
    """
    paths: list[str] = field(default_factory=lambda: ["src/"])
    min_severity: Severity = Severity.LOW
    categories: list[FindingCategory] | None = None
    parallel: bool = True
    timeout_seconds: int = 300
    max_findings_per_agent: int = 100
    include_snippets: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "paths": self.paths,
            "min_severity": self.min_severity.value,
            "categories": [c.value for c in self.categories] if self.categories else None,
            "parallel": self.parallel,
            "timeout_seconds": self.timeout_seconds,
            "max_findings_per_agent": self.max_findings_per_agent,
            "include_snippets": self.include_snippets,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QAAuditConfig":
        """Create from dictionary."""
        categories = None
        if data.get("categories"):
            categories = [FindingCategory(c) for c in data["categories"]]
        return cls(
            paths=data.get("paths", ["src/"]),
            min_severity=Severity(data.get("min_severity", "LOW")),
            categories=categories,
            parallel=data.get("parallel", True),
            timeout_seconds=data.get("timeout_seconds", 300),
            max_findings_per_agent=data.get("max_findings_per_agent", 100),
            include_snippets=data.get("include_snippets", True),
        )


# Priority scoring weights for sorting findings
SEVERITY_WEIGHTS = {
    Severity.CRITICAL: 1000,
    Severity.HIGH: 100,
    Severity.MEDIUM: 10,
    Severity.LOW: 1,
}

# Financial impact multipliers for certain categories
FINANCIAL_IMPACT_CATEGORIES = {
    FindingCategory.SECURITY: 2.0,      # Security issues have high financial impact
    FindingCategory.BUSINESS_LOGIC: 2.0, # Business logic bugs affect trades
    FindingCategory.CONCURRENCY: 1.5,   # Race conditions can cause losses
    FindingCategory.API_CONTRACT: 1.5,  # API issues affect order execution
}


def compute_finding_priority(finding: Finding) -> float:
    """
    Compute a priority score for sorting findings.

    Higher scores = more urgent.
    """
    base_score = SEVERITY_WEIGHTS[finding.severity]
    multiplier = FINANCIAL_IMPACT_CATEGORIES.get(finding.category, 1.0)
    return base_score * multiplier
