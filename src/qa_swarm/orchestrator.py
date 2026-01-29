"""
QA Orchestrator - Coordinates parallel specialist agents and merges results.

The orchestrator:
1. Launches all agents in parallel (or sequentially)
2. Collects and deduplicates findings
3. Prioritizes by severity + financial impact
4. Generates executive summary
"""

import asyncio
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .types import (
    Severity,
    FindingCategory,
    Finding,
    AgentReport,
    AggregatedReport,
    QAAuditConfig,
    compute_finding_priority,
)
from .agents.base import AGENT_REGISTRY, AgentDefinition


# Type alias for agent runner function
AgentRunner = Callable[[AgentDefinition, list[str], int], AgentReport]

# Patterns to search for - defined as constants to avoid security scanner false positives
# These are DETECTION patterns, not actual credentials
_SECURITY_PATTERNS = [
    ("api_key =", Severity.CRITICAL, "Potential hardcoded API key"),
    ("_secret =", Severity.CRITICAL, "Potential hardcoded secret"),
    ("yaml.load(", Severity.HIGH, "Unsafe YAML loading"),
    ("shell=True", Severity.HIGH, "Shell injection risk"),
    ("os.system(", Severity.HIGH, "Command injection risk"),
]


class QAOrchestrator:
    """
    Orchestrates parallel QA agent execution.

    The orchestrator manages the lifecycle of specialist agents:
    1. Filters agents by requested categories
    2. Runs agents in parallel or sequentially
    3. Collects results with timeout handling
    4. Deduplicates findings across agents
    5. Prioritizes and aggregates results
    """

    def __init__(
        self,
        config: QAAuditConfig | None = None,
        agent_runner: AgentRunner | None = None,
    ):
        """
        Initialize the orchestrator.

        Args:
            config: Audit configuration (default: standard config)
            agent_runner: Custom function to run agents (for testing/mocking)
        """
        self.config = config or QAAuditConfig()
        self.agent_runner = agent_runner or self._default_agent_runner

    def get_agents_to_run(self) -> list[AgentDefinition]:
        """Get list of agents to run based on config."""
        all_agents = list(AGENT_REGISTRY.values())

        if self.config.categories:
            category_set = set(self.config.categories)
            return [a for a in all_agents if a.category in category_set]

        return all_agents

    async def run_async(self) -> AggregatedReport:
        """
        Run the QA audit asynchronously.

        Returns:
            AggregatedReport with all findings
        """
        start_time = time.time()
        agents = self.get_agents_to_run()

        if self.config.parallel:
            agent_reports = await self._run_agents_parallel(agents)
        else:
            agent_reports = await self._run_agents_sequential(agents)

        # Aggregate results
        report = self._aggregate_reports(agent_reports, start_time)
        return report

    def run_sync(self) -> AggregatedReport:
        """
        Run the QA audit synchronously.

        Returns:
            AggregatedReport with all findings
        """
        return asyncio.run(self.run_async())

    async def _run_agents_parallel(
        self,
        agents: list[AgentDefinition],
    ) -> list[AgentReport]:
        """Run all agents in parallel with timeout."""
        tasks = []
        for agent in agents:
            task = asyncio.create_task(
                self._run_single_agent(agent),
                name=agent.name,
            )
            tasks.append(task)

        # Wait for all with timeout
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=self.config.timeout_seconds * len(agents),
            )
        except asyncio.TimeoutError:
            # Cancel remaining tasks
            for task in tasks:
                if not task.done():
                    task.cancel()
            results = [
                task.result() if task.done() and not task.cancelled()
                else self._timeout_report(agents[i])
                for i, task in enumerate(tasks)
            ]

        # Convert exceptions to error reports
        reports = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                reports.append(self._error_report(agents[i], str(result)))
            elif isinstance(result, AgentReport):
                reports.append(result)
            else:
                reports.append(self._error_report(agents[i], f"Unexpected result: {result}"))

        return reports

    async def _run_agents_sequential(
        self,
        agents: list[AgentDefinition],
    ) -> list[AgentReport]:
        """Run all agents sequentially."""
        reports = []
        for agent in agents:
            try:
                report = await asyncio.wait_for(
                    self._run_single_agent(agent),
                    timeout=self.config.timeout_seconds,
                )
                reports.append(report)
            except asyncio.TimeoutError:
                reports.append(self._timeout_report(agent))
            except Exception as e:
                reports.append(self._error_report(agent, str(e)))
        return reports

    async def _run_single_agent(self, agent: AgentDefinition) -> AgentReport:
        """Run a single agent and return its report."""
        # Run in executor to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.agent_runner,
            agent,
            self.config.paths,
            self.config.max_findings_per_agent,
        )

    def _default_agent_runner(
        self,
        agent: AgentDefinition,
        paths: list[str],
        max_findings: int,
    ) -> AgentReport:
        """
        Default agent runner that performs static analysis.

        This is a synchronous function that analyzes code files.
        For LLM-based analysis, replace this with a custom runner.
        """
        start_time = time.time()
        findings: list[Finding] = []
        files_scanned = 0

        try:
            # Scan files matching agent's patterns
            for path_str in paths:
                path = Path(path_str)
                if not path.exists():
                    continue

                for pattern in agent.file_patterns:
                    if path.is_file():
                        files = [path] if path.match(pattern) else []
                    else:
                        files = list(path.rglob(pattern))

                    for file_path in files:
                        files_scanned += 1
                        file_findings = self._analyze_file(agent, file_path)
                        findings.extend(file_findings)

                        if len(findings) >= max_findings:
                            break

                    if len(findings) >= max_findings:
                        break
                if len(findings) >= max_findings:
                    break

            # Limit findings
            findings = findings[:max_findings]

            execution_time = int((time.time() - start_time) * 1000)
            return AgentReport(
                agent_name=agent.name,
                category=agent.category,
                findings=findings,
                files_scanned=files_scanned,
                execution_time_ms=execution_time,
            )

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            return AgentReport(
                agent_name=agent.name,
                category=agent.category,
                files_scanned=files_scanned,
                execution_time_ms=execution_time,
                error_message=str(e),
            )

    def _analyze_file(
        self,
        agent: AgentDefinition,
        file_path: Path,
    ) -> list[Finding]:
        """
        Analyze a single file using pattern matching.

        This is a basic static analysis implementation.
        For more sophisticated analysis, use an LLM-based agent runner.
        """
        findings = []
        finding_id = 1

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            lines = content.split("\n")
        except Exception:
            return findings

        # Pattern-based analysis based on agent category
        patterns = self._get_patterns_for_agent(agent)

        for line_num, line in enumerate(lines, 1):
            for pattern, severity, title_template in patterns:
                if pattern.lower() in line.lower():
                    findings.append(Finding(
                        id=f"{agent.id_prefix}-{finding_id:03d}",
                        category=agent.category,
                        severity=severity,
                        title=title_template,
                        description=f"Found pattern '{pattern}' indicating potential issue",
                        file_path=str(file_path.absolute()),
                        line_number=line_num,
                        code_snippet=line.strip()[:200] if self.config.include_snippets else None,
                        recommendation=f"Review this line for {agent.display_name.lower()} concerns",
                    ))
                    finding_id += 1

        return findings

    def _get_patterns_for_agent(
        self,
        agent: AgentDefinition,
    ) -> list[tuple[str, Severity, str]]:
        """Get search patterns for an agent's category."""
        # Basic pattern matching for each category
        # Note: Security patterns are for DETECTION of potential issues
        patterns: dict[FindingCategory, list[tuple[str, Severity, str]]] = {
            FindingCategory.SECURITY: _SECURITY_PATTERNS,
            FindingCategory.TYPE_SAFETY: [
                ("Optional[", Severity.LOW, "Use X | None instead of Optional[X]"),
                ("List[", Severity.LOW, "Use list[] instead of List[]"),
                ("Dict[", Severity.LOW, "Use dict[] instead of Dict[]"),
            ],
            FindingCategory.ERROR_HANDLING: [
                ("except:", Severity.MEDIUM, "Bare except clause"),
                ("except Exception:", Severity.MEDIUM, "Overly broad exception"),
                ("pass", Severity.LOW, "Potential silent failure (check context)"),
            ],
            FindingCategory.CONCURRENCY: [
                ("threading.Thread", Severity.MEDIUM, "Thread usage - verify thread safety"),
                ("time.sleep(", Severity.LOW, "Blocking sleep (check if in async)"),
            ],
            FindingCategory.BUSINESS_LOGIC: [
                ("/ leverage", Severity.MEDIUM, "Leverage calculation - verify correctness"),
                ("* leverage", Severity.MEDIUM, "Leverage calculation - verify correctness"),
            ],
            FindingCategory.API_CONTRACT: [
                ("['result']", Severity.MEDIUM, "Direct dict access - use .get()"),
                ('["result"]', Severity.MEDIUM, "Direct dict access - use .get()"),
            ],
            FindingCategory.DOCUMENTATION: [
                ("# TODO", Severity.LOW, "TODO item found"),
                ("# FIXME", Severity.MEDIUM, "FIXME item found"),
                ("# HACK", Severity.MEDIUM, "HACK item found"),
            ],
            FindingCategory.DEAD_CODE: [
                ("# def ", Severity.LOW, "Commented-out function definition"),
                ("# class ", Severity.LOW, "Commented-out class definition"),
            ],
        }

        return patterns.get(agent.category, [])

    def _timeout_report(self, agent: AgentDefinition) -> AgentReport:
        """Create a report for a timed-out agent."""
        return AgentReport(
            agent_name=agent.name,
            category=agent.category,
            error_message=f"Agent timed out after {self.config.timeout_seconds} seconds",
        )

    def _error_report(self, agent: AgentDefinition, error: str) -> AgentReport:
        """Create a report for a failed agent."""
        return AgentReport(
            agent_name=agent.name,
            category=agent.category,
            error_message=error,
        )

    def _aggregate_reports(
        self,
        reports: list[AgentReport],
        start_time: float,
    ) -> AggregatedReport:
        """Aggregate all agent reports into a single report."""
        # Collect all findings
        all_findings: list[Finding] = []
        for report in reports:
            all_findings.extend(report.findings)

        # Deduplicate by location
        seen_locations: set[str] = set()
        unique_findings: list[Finding] = []
        for finding in all_findings:
            location_key = finding.location_key()
            if location_key not in seen_locations:
                seen_locations.add(location_key)
                unique_findings.append(finding)

        # Filter by minimum severity
        filtered_findings = [
            f for f in unique_findings
            if f.severity >= self.config.min_severity
        ]

        # Sort by priority (highest first)
        prioritized = sorted(
            filtered_findings,
            key=compute_finding_priority,
            reverse=True,
        )

        # Count by severity
        by_severity: dict[str, int] = {s.value: 0 for s in Severity}
        for finding in prioritized:
            by_severity[finding.severity.value] += 1

        # Count by category
        by_category: dict[str, int] = {c.value: 0 for c in FindingCategory}
        for finding in prioritized:
            by_category[finding.category.value] += 1

        # Calculate totals
        total_files = sum(r.files_scanned for r in reports)
        execution_time = int((time.time() - start_time) * 1000)

        # Generate summary
        summary = self._generate_summary(prioritized, by_severity, reports)

        return AggregatedReport(
            timestamp=datetime.now(timezone.utc),
            total_files_scanned=total_files,
            total_findings=len(prioritized),
            findings_by_severity=by_severity,
            findings_by_category=by_category,
            prioritized_findings=prioritized,
            agent_reports=reports,
            execution_time_ms=execution_time,
            summary=summary,
            config=self.config,
        )

    def _generate_summary(
        self,
        findings: list[Finding],
        by_severity: dict[str, int],
        reports: list[AgentReport],
    ) -> str:
        """Generate an executive summary paragraph."""
        total = len(findings)
        critical = by_severity.get("CRITICAL", 0)
        high = by_severity.get("HIGH", 0)
        medium = by_severity.get("MEDIUM", 0)
        low = by_severity.get("LOW", 0)

        failed_agents = [r for r in reports if not r.success]

        if total == 0 and not failed_agents:
            return "No issues found. The codebase passes all QA checks."

        parts = [f"Found {total} issue(s) across the codebase."]

        if critical > 0:
            parts.append(f"{critical} CRITICAL issue(s) require immediate attention.")
        if high > 0:
            parts.append(f"{high} HIGH severity issue(s) should be addressed soon.")
        if medium > 0:
            parts.append(f"{medium} MEDIUM severity issue(s) for review.")
        if low > 0:
            parts.append(f"{low} LOW severity items noted.")

        if failed_agents:
            names = [a.agent_name for a in failed_agents]
            parts.append(f"Warning: {len(failed_agents)} agent(s) failed: {', '.join(names)}.")

        # Add top priority areas
        if findings:
            top_categories = sorted(
                [(c, count) for c, count in by_severity.items() if count > 0],
                key=lambda x: ["CRITICAL", "HIGH", "MEDIUM", "LOW"].index(x[0]),
            )
            if top_categories:
                parts.append(f"Priority areas: {top_categories[0][0]} issues.")

        return " ".join(parts)


async def run_qa_audit(config: QAAuditConfig | None = None) -> AggregatedReport:
    """
    Run a QA audit with the given configuration.

    This is the main entry point for the QA swarm.

    Args:
        config: Audit configuration (default: standard config)

    Returns:
        AggregatedReport with all findings

    Example:
        # Full audit
        report = await run_qa_audit()

        # Audit specific paths
        config = QAAuditConfig(paths=["src/core/"])
        report = await run_qa_audit(config)
    """
    orchestrator = QAOrchestrator(config)
    return await orchestrator.run_async()


def run_qa_audit_sync(config: QAAuditConfig | None = None) -> AggregatedReport:
    """
    Run a QA audit synchronously.

    Convenience wrapper for non-async contexts.

    Args:
        config: Audit configuration (default: standard config)

    Returns:
        AggregatedReport with all findings
    """
    orchestrator = QAOrchestrator(config)
    return orchestrator.run_sync()
