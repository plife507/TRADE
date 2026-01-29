"""
Base Agent Definition - Structure for specialist QA agents.

Each agent is a dataclass containing:
- Metadata (name, description, category)
- System prompt (detailed instructions)
- Target paths and file patterns
- Severity rules for classification
"""

from dataclasses import dataclass, field
from typing import Any

from ..types import FindingCategory, Severity


@dataclass
class SeverityRule:
    """
    Rule for classifying finding severity.

    Attributes:
        pattern: Description of the pattern to match
        severity: Severity level to assign
        examples: Example issues that match this pattern
    """
    pattern: str
    severity: Severity
    examples: list[str] = field(default_factory=list)


@dataclass
class AgentDefinition:
    """
    Definition for a specialist QA agent.

    Attributes:
        name: Unique identifier (e.g., "security_auditor")
        display_name: Human-readable name
        category: Finding category this agent covers
        description: What this agent checks for
        system_prompt: Detailed instructions for the agent
        target_paths: Default paths to analyze
        file_patterns: Glob patterns for files to examine
        severity_rules: Rules for classifying findings
        id_prefix: Prefix for finding IDs (e.g., "SEC")
    """
    name: str
    display_name: str
    category: FindingCategory
    description: str
    system_prompt: str
    target_paths: list[str]
    file_patterns: list[str]
    severity_rules: list[SeverityRule]
    id_prefix: str

    def get_full_prompt(self, paths: list[str] | None = None) -> str:
        """
        Generate the full prompt for this agent.

        Args:
            paths: Override paths to analyze (default: use target_paths)

        Returns:
            Complete prompt string for the agent
        """
        analyze_paths = paths or self.target_paths
        paths_str = ", ".join(analyze_paths)

        return f"""# {self.display_name}

## Your Role
{self.description}

## Focus Areas
{self.system_prompt}

## Paths to Analyze
{paths_str}

## File Patterns
{", ".join(self.file_patterns)}

## Output Format
For each finding, provide:
1. **ID**: {self.id_prefix}-XXX (sequential number)
2. **Severity**: {", ".join(s.value for s in Severity)}
3. **Title**: One-line summary
4. **File**: Absolute path
5. **Line**: Line number if applicable
6. **Description**: Full explanation
7. **Code Snippet**: Relevant code (if applicable)
8. **Recommendation**: How to fix

## Severity Classification
{self._format_severity_rules()}

## Important Notes
- Be thorough but avoid false positives
- Only report actual issues, not style preferences
- Include enough context for another developer to understand and fix
- Prioritize issues that could cause runtime failures or security vulnerabilities
"""

    def _format_severity_rules(self) -> str:
        """Format severity rules as markdown."""
        lines = []
        for rule in self.severity_rules:
            examples = ", ".join(rule.examples) if rule.examples else "N/A"
            lines.append(f"- **{rule.severity.value}**: {rule.pattern}")
            if rule.examples:
                lines.append(f"  - Examples: {examples}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "category": self.category.value,
            "description": self.description,
            "target_paths": self.target_paths,
            "file_patterns": self.file_patterns,
            "id_prefix": self.id_prefix,
        }


# Global registry of all agent definitions
AGENT_REGISTRY: dict[str, AgentDefinition] = {}


def register_agent(agent: AgentDefinition) -> AgentDefinition:
    """Register an agent definition in the global registry."""
    AGENT_REGISTRY[agent.name] = agent
    return agent
