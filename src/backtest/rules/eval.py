"""
Operator implementations for rule evaluation.

Strict type contracts:
- gt, lt, ge, le: NUMERIC only (int or float)
- eq: BOOL, INT, or ENUM only (NO float - use approx_eq)
- approx_eq: FLOAT only, requires tolerance
- and, or, not: BOOL only

Every evaluation returns EvalResult with ReasonCode.
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Callable, Dict, Optional, Union
import math

from .types import EvalResult, ReasonCode, RefValue, ValueType
from .compile import CompiledRef


class Operator(str, Enum):
    """
    Supported comparison operators.

    Type contracts enforced at evaluation time.
    """

    # Numeric comparisons (int or float)
    GT = "gt"  # Greater than
    LT = "lt"  # Less than
    GE = "ge"  # Greater than or equal (also: gte)
    LE = "le"  # Less than or equal (also: lte)

    # Equality (bool, int, enum - NOT float)
    EQ = "eq"  # Exact equality

    # Float equality (requires tolerance)
    APPROX_EQ = "approx_eq"  # Approximate equality with tolerance

    # Logical (bool only)
    AND = "and"
    OR = "or"
    NOT = "not"


# Operator aliases (for backward compat with existing IdeaCards)
OPERATOR_ALIASES = {
    "gte": Operator.GE,
    "lte": Operator.LE,
}


def _check_numeric(lhs: RefValue, rhs: RefValue, op: str) -> Optional[EvalResult]:
    """
    Check if both values are numeric. Returns failure EvalResult if not.

    Args:
        lhs: Left-hand side value
        rhs: Right-hand side value
        op: Operator name for error messages

    Returns:
        EvalResult if type check failed, None if both are numeric
    """
    if lhs.is_missing:
        return EvalResult.failure(
            ReasonCode.R_MISSING_LHS,
            f"LHS value is missing (None/NaN)",
            lhs_path=lhs.path,
            rhs_repr=str(rhs.value),
            operator=op,
        )

    if rhs.is_missing:
        return EvalResult.failure(
            ReasonCode.R_MISSING_RHS,
            f"RHS value is missing (None/NaN)",
            lhs_path=lhs.path,
            rhs_repr=str(rhs.value),
            operator=op,
        )

    if not lhs.is_numeric:
        return EvalResult.failure(
            ReasonCode.R_TYPE_MISMATCH,
            f"Operator '{op}' requires numeric LHS, got {lhs.value_type.name}",
            lhs_path=lhs.path,
            rhs_repr=str(rhs.value),
            operator=op,
        )

    if not rhs.is_numeric:
        return EvalResult.failure(
            ReasonCode.R_TYPE_MISMATCH,
            f"Operator '{op}' requires numeric RHS, got {rhs.value_type.name}",
            lhs_path=lhs.path,
            rhs_repr=str(rhs.value),
            operator=op,
        )

    return None


def eval_gt(lhs: RefValue, rhs: RefValue) -> EvalResult:
    """Evaluate lhs > rhs (numeric only)."""
    check = _check_numeric(lhs, rhs, "gt")
    if check:
        return check

    result = lhs.value > rhs.value
    return EvalResult.success(result, lhs.path, str(rhs.value), "gt")


def eval_lt(lhs: RefValue, rhs: RefValue) -> EvalResult:
    """Evaluate lhs < rhs (numeric only)."""
    check = _check_numeric(lhs, rhs, "lt")
    if check:
        return check

    result = lhs.value < rhs.value
    return EvalResult.success(result, lhs.path, str(rhs.value), "lt")


def eval_ge(lhs: RefValue, rhs: RefValue) -> EvalResult:
    """Evaluate lhs >= rhs (numeric only)."""
    check = _check_numeric(lhs, rhs, "ge")
    if check:
        return check

    result = lhs.value >= rhs.value
    return EvalResult.success(result, lhs.path, str(rhs.value), "ge")


def eval_le(lhs: RefValue, rhs: RefValue) -> EvalResult:
    """Evaluate lhs <= rhs (numeric only)."""
    check = _check_numeric(lhs, rhs, "le")
    if check:
        return check

    result = lhs.value <= rhs.value
    return EvalResult.success(result, lhs.path, str(rhs.value), "le")


def eval_eq(lhs: RefValue, rhs: RefValue) -> EvalResult:
    """
    Evaluate lhs == rhs (bool, int, enum only - NOT float).

    Float equality is rejected - use approx_eq with tolerance.
    """
    op = "eq"

    if lhs.is_missing:
        return EvalResult.failure(
            ReasonCode.R_MISSING_LHS,
            "LHS value is missing (None/NaN)",
            lhs_path=lhs.path,
            rhs_repr=str(rhs.value),
            operator=op,
        )

    if rhs.is_missing:
        return EvalResult.failure(
            ReasonCode.R_MISSING_RHS,
            "RHS value is missing (None/NaN)",
            lhs_path=lhs.path,
            rhs_repr=str(rhs.value),
            operator=op,
        )

    # Reject float equality - must use approx_eq
    if lhs.value_type == ValueType.FLOAT or rhs.value_type == ValueType.FLOAT:
        return EvalResult.failure(
            ReasonCode.R_FLOAT_EQUALITY,
            "Float equality not allowed with 'eq'. Use 'approx_eq' with tolerance",
            lhs_path=lhs.path,
            rhs_repr=str(rhs.value),
            operator=op,
        )

    # Allow: bool, int, enum (normalized to int), string (enum token)
    allowed = (ValueType.BOOL, ValueType.INT, ValueType.ENUM, ValueType.STRING)
    if lhs.value_type not in allowed:
        return EvalResult.failure(
            ReasonCode.R_TYPE_MISMATCH,
            f"Operator 'eq' requires bool/int/enum, got {lhs.value_type.name}",
            lhs_path=lhs.path,
            rhs_repr=str(rhs.value),
            operator=op,
        )

    result = lhs.value == rhs.value
    return EvalResult.success(result, lhs.path, str(rhs.value), "eq")


def eval_approx_eq(
    lhs: RefValue,
    rhs: RefValue,
    tolerance: Optional[float] = None,
    relative: bool = False,
) -> EvalResult:
    """
    Evaluate approximate equality for floats.

    Args:
        lhs: Left-hand side value
        rhs: Right-hand side value
        tolerance: Absolute tolerance (required)
        relative: If True, tolerance is relative (percentage)

    Returns:
        EvalResult with comparison outcome
    """
    op = "approx_eq"

    if tolerance is None:
        return EvalResult.failure(
            ReasonCode.R_INVALID_TOLERANCE,
            "approx_eq requires 'tolerance' parameter",
            lhs_path=lhs.path,
            rhs_repr=str(rhs.value),
            operator=op,
        )

    if tolerance < 0:
        return EvalResult.failure(
            ReasonCode.R_INVALID_TOLERANCE,
            f"Tolerance must be non-negative, got {tolerance}",
            lhs_path=lhs.path,
            rhs_repr=str(rhs.value),
            operator=op,
        )

    check = _check_numeric(lhs, rhs, "approx_eq")
    if check:
        return check

    if relative:
        # Relative tolerance: |lhs - rhs| / max(|lhs|, |rhs|) <= tolerance
        max_abs = max(abs(lhs.value), abs(rhs.value))
        if max_abs == 0:
            result = abs(lhs.value - rhs.value) == 0
        else:
            result = abs(lhs.value - rhs.value) / max_abs <= tolerance
    else:
        # Absolute tolerance: |lhs - rhs| <= tolerance
        result = abs(lhs.value - rhs.value) <= tolerance

    return EvalResult.success(result, lhs.path, str(rhs.value), "approx_eq")


# Operator dispatch table
OPERATORS: Dict[str, Callable] = {
    "gt": eval_gt,
    "lt": eval_lt,
    "ge": eval_ge,
    "le": eval_le,
    "gte": eval_ge,  # Alias
    "lte": eval_le,  # Alias
    "eq": eval_eq,
    "approx_eq": eval_approx_eq,
}


def evaluate_condition(
    lhs_ref: CompiledRef,
    operator: str,
    rhs_ref: CompiledRef,
    snapshot,
    tolerance: Optional[float] = None,
    relative_tolerance: bool = False,
) -> EvalResult:
    """
    Evaluate a compiled condition against a snapshot.

    Args:
        lhs_ref: Compiled left-hand side reference
        operator: Operator name ("gt", "lt", "eq", etc.)
        rhs_ref: Compiled right-hand side reference
        snapshot: RuntimeSnapshotView instance
        tolerance: For approx_eq, the tolerance value
        relative_tolerance: For approx_eq, whether tolerance is relative

    Returns:
        EvalResult with evaluation outcome and reason code
    """
    # Normalize operator
    op = operator.lower()

    # Check for unknown operator
    if op not in OPERATORS:
        return EvalResult.failure(
            ReasonCode.R_UNKNOWN_OPERATOR,
            f"Unknown operator '{operator}'",
            lhs_path=lhs_ref.path,
            rhs_repr=rhs_ref.path,
            operator=operator,
        )

    # Resolve references
    lhs = lhs_ref.resolve(snapshot)
    rhs = rhs_ref.resolve(snapshot)

    # Dispatch to operator
    if op == "approx_eq":
        return eval_approx_eq(lhs, rhs, tolerance, relative_tolerance)
    else:
        return OPERATORS[op](lhs, rhs)


def evaluate_condition_dict(
    condition: Dict[str, Any],
    snapshot,
) -> EvalResult:
    """
    Evaluate a condition dict (with pre-compiled refs) against a snapshot.

    This is the main entry point for IdeaCard signal evaluation.

    Args:
        condition: Dict with 'lhs_ref', 'rhs_ref', 'operator' keys
        snapshot: RuntimeSnapshotView instance

    Returns:
        EvalResult with evaluation outcome
    """
    lhs_ref = condition.get("lhs_ref")
    rhs_ref = condition.get("rhs_ref")
    operator = condition.get("operator", "")

    if not isinstance(lhs_ref, CompiledRef):
        return EvalResult.failure(
            ReasonCode.R_INTERNAL_ERROR,
            "Condition missing compiled lhs_ref. Was it normalized?",
        )

    if not isinstance(rhs_ref, CompiledRef):
        return EvalResult.failure(
            ReasonCode.R_INTERNAL_ERROR,
            "Condition missing compiled rhs_ref. Was it normalized?",
        )

    # Extract tolerance for approx_eq
    tolerance = condition.get("tolerance")
    relative = condition.get("relative_tolerance", False)

    return evaluate_condition(
        lhs_ref,
        operator,
        rhs_ref,
        snapshot,
        tolerance=tolerance,
        relative_tolerance=relative,
    )
