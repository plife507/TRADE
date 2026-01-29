"""
QA Specialist Agents - Definitions for parallel code analysis.

Each agent is defined by:
- Name and description
- System prompt with focus areas
- Target paths to analyze
- Severity classification rules
"""

from .base import AgentDefinition, AGENT_REGISTRY
from .security_auditor import SECURITY_AUDITOR
from .type_safety_checker import TYPE_SAFETY_CHECKER
from .error_handler_reviewer import ERROR_HANDLER_REVIEWER
from .concurrency_auditor import CONCURRENCY_AUDITOR
from .business_logic_validator import BUSINESS_LOGIC_VALIDATOR
from .api_contract_checker import API_CONTRACT_CHECKER
from .documentation_auditor import DOCUMENTATION_AUDITOR
from .dead_code_detector import DEAD_CODE_DETECTOR

__all__ = [
    "AgentDefinition",
    "AGENT_REGISTRY",
    "SECURITY_AUDITOR",
    "TYPE_SAFETY_CHECKER",
    "ERROR_HANDLER_REVIEWER",
    "CONCURRENCY_AUDITOR",
    "BUSINESS_LOGIC_VALIDATOR",
    "API_CONTRACT_CHECKER",
    "DOCUMENTATION_AUDITOR",
    "DEAD_CODE_DETECTOR",
]
