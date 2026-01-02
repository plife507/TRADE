"""
Operator Registry - Single source of truth for operator semantics.

Stage 4c: All operator rules defined here. Used by:
- Compile-time validation (reject unsupported operators)
- Runtime evaluation dispatch

Design:
- Each operator has explicit requirements
- Unsupported operators fail at compile time, never reach hot loop
- Adding new operators requires updating this registry
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import FrozenSet, Optional, Set


class OpCategory(Enum):
    """Operator input type categories."""
    NUMERIC = auto()      # int or float
    NUMERIC_ONLY = auto() # int or float, no enum/bool
    BOOL_INT_ENUM = auto() # bool, int, or enum (NOT float)
    FLOAT_ONLY = auto()   # float only (for approx_eq)


@dataclass(frozen=True)
class OperatorSpec:
    """
    Specification for a single operator.

    Attributes:
        name: Canonical operator name (e.g., "gt", "eq")
        supported: Whether this operator is implemented
        category: Allowed input type category
        needs_tolerance: Whether tolerance parameter is required
        needs_prev_value: Whether previous bar value is needed (crossover)
        error_if_unsupported: Error message for unsupported operators
    """
    name: str
    supported: bool
    category: OpCategory
    needs_tolerance: bool = False
    needs_prev_value: bool = False
    error_if_unsupported: Optional[str] = None


# =============================================================================
# OPERATOR REGISTRY - Single Source of Truth
# =============================================================================

OPERATOR_REGISTRY = {
    # Numeric comparisons (int or float)
    "gt": OperatorSpec(
        name="gt",
        supported=True,
        category=OpCategory.NUMERIC,
    ),
    "lt": OperatorSpec(
        name="lt",
        supported=True,
        category=OpCategory.NUMERIC,
    ),
    "ge": OperatorSpec(
        name="ge",
        supported=True,
        category=OpCategory.NUMERIC,
    ),
    "gte": OperatorSpec(  # Alias for ge
        name="ge",
        supported=True,
        category=OpCategory.NUMERIC,
    ),
    "le": OperatorSpec(
        name="le",
        supported=True,
        category=OpCategory.NUMERIC,
    ),
    "lte": OperatorSpec(  # Alias for le
        name="le",
        supported=True,
        category=OpCategory.NUMERIC,
    ),

    # Equality (bool, int, enum - NOT float)
    "eq": OperatorSpec(
        name="eq",
        supported=True,
        category=OpCategory.BOOL_INT_ENUM,
    ),

    # Approximate equality (float only, requires tolerance)
    "approx_eq": OperatorSpec(
        name="approx_eq",
        supported=True,
        category=OpCategory.FLOAT_ONLY,
        needs_tolerance=True,
    ),

    # Crossover operators - BANNED in Stage 4c
    "cross_above": OperatorSpec(
        name="cross_above",
        supported=False,
        category=OpCategory.NUMERIC,
        needs_prev_value=True,
        error_if_unsupported=(
            "Operator 'cross_above' is not supported in compiled evaluation (Stage 4c). "
            "Rewrite using derived indicator features (e.g., 'rsi_crossed_30') or wait for Stage 5."
        ),
    ),
    "cross_below": OperatorSpec(
        name="cross_below",
        supported=False,
        category=OpCategory.NUMERIC,
        needs_prev_value=True,
        error_if_unsupported=(
            "Operator 'cross_below' is not supported in compiled evaluation (Stage 4c). "
            "Rewrite using derived indicator features (e.g., 'rsi_crossed_70') or wait for Stage 5."
        ),
    ),
}

# Canonical names only (excludes aliases)
SUPPORTED_OPERATORS: FrozenSet[str] = frozenset(
    spec.name for spec in OPERATOR_REGISTRY.values() if spec.supported
)

# All known operator names (including aliases)
ALL_OPERATORS: FrozenSet[str] = frozenset(OPERATOR_REGISTRY.keys())


def get_operator_spec(operator: str) -> Optional[OperatorSpec]:
    """
    Get operator specification from registry.

    Args:
        operator: Operator name (case-insensitive)

    Returns:
        OperatorSpec if known, None if unknown
    """
    return OPERATOR_REGISTRY.get(operator.lower())


def is_operator_supported(operator: str) -> bool:
    """Check if operator is supported for compiled evaluation."""
    spec = get_operator_spec(operator)
    return spec is not None and spec.supported


def validate_operator(operator: str) -> Optional[str]:
    """
    Validate operator at compile time.

    Args:
        operator: Operator name

    Returns:
        Error message if invalid, None if valid
    """
    op = operator.lower()
    spec = get_operator_spec(op)

    if spec is None:
        return (
            f"Unknown operator '{operator}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_OPERATORS))}"
        )

    if not spec.supported:
        return spec.error_if_unsupported or f"Operator '{operator}' is not supported"

    return None


def get_canonical_operator(operator: str) -> Optional[str]:
    """
    Get canonical operator name (resolves aliases).

    Args:
        operator: Operator name (may be alias)

    Returns:
        Canonical name if valid, None if unknown
    """
    spec = get_operator_spec(operator)
    return spec.name if spec else None
