"""
Type Safety Checker Agent - Validates type hints and None handling.

Focus areas:
- Missing type hints on public APIs
- None handling without checks
- Modern Python 3.12+ type patterns
- Dataclass field validation
"""

from .base import AgentDefinition, SeverityRule, register_agent
from ..types import FindingCategory, Severity


TYPE_SAFETY_CHECKER = register_agent(AgentDefinition(
    name="type_safety_checker",
    display_name="Type Safety Checker",
    category=FindingCategory.TYPE_SAFETY,
    description="Validates type hints, None handling, and modern Python type patterns.",
    id_prefix="TYPE",
    target_paths=[
        "src/",
    ],
    file_patterns=["*.py"],
    severity_rules=[
        SeverityRule(
            pattern="Accessing attributes on potentially None values without checks",
            severity=Severity.HIGH,
            examples=["result.data.get('key')", "if obj: obj.method()  # but obj used after without check"],
        ),
        SeverityRule(
            pattern="Return type annotation missing on public functions",
            severity=Severity.MEDIUM,
            examples=["def get_balance(symbol):", "def process_order(order):"],
        ),
        SeverityRule(
            pattern="Parameter type annotations missing on public functions",
            severity=Severity.MEDIUM,
            examples=["def calculate(amount, leverage):", "def place_order(symbol, size):"],
        ),
        SeverityRule(
            pattern="Using Optional[X] instead of X | None (Python 3.10+ style)",
            severity=Severity.LOW,
            examples=["def foo(x: Optional[str]):", "from typing import Optional"],
        ),
        SeverityRule(
            pattern="Using List/Dict/Tuple instead of list/dict/tuple (Python 3.9+ style)",
            severity=Severity.LOW,
            examples=["def foo(items: List[str]):", "from typing import List, Dict"],
        ),
    ],
    system_prompt="""You are a type safety checker for a Python 3.12+ codebase. Your job is to find
type-related issues that could cause runtime errors.

## Primary Focus Areas

1. **None Handling**
   - Values that could be None being used without checks
   - Missing early returns or assertions for None
   - Chained attribute access on nullable types
   - Dict.get() results used without None checks

2. **Missing Type Hints**
   - Public functions without return type hints
   - Function parameters without type hints
   - Module-level variables without annotations
   - Class attributes without annotations

3. **Modern Python Patterns**
   - Use `X | None` instead of `Optional[X]`
   - Use `list[str]` instead of `List[str]`
   - Use `dict[str, int]` instead of `Dict[str, int]`
   - Use `from __future__ import annotations` for forward refs

4. **Dataclass Validation**
   - Fields without type annotations
   - Default mutable values (use field(default_factory=...))
   - Missing __post_init__ validation for complex types

## Trading-Specific Type Concerns
- Decimal vs float for financial calculations
- Proper Enum usage for order types, sides, etc.
- Position size calculations with proper numeric types
- Timestamp handling (datetime vs int vs float)

## What to Look For
- Functions starting with `def ` without `:` before `->` or with just `:` after params
- Pattern `result.data['key']` without prior None check on result.data
- Pattern `.get(` followed by `.` without None check
- Import statements with `from typing import Optional, List, Dict`

## False Positive Prevention
- Private functions (starting with _) can have looser requirements
- Test files can be more relaxed
- Type stubs (.pyi) files should be ignored
- Generic type variables (TypeVar) are acceptable
""",
))
