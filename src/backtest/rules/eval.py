"""
Operator implementations for rule evaluation.

Strict type contracts:
- gt, lt, ge, le: NUMERIC only (int or float)
- eq: BOOL, INT, or ENUM only (NO float - use approx_eq)
- approx_eq: FLOAT only, requires tolerance

Every evaluation returns EvalResult with ReasonCode.
"""

from collections.abc import Callable
from typing import Any

from .types import EvalResult, ReasonCode, RefValue, ValueType
from .compile import CompiledRef


def _check_numeric(lhs: RefValue, rhs: RefValue, op: str) -> EvalResult | None:
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
            ReasonCode.MISSING_LHS,
            f"LHS value is missing (None/NaN)",
            lhs_path=lhs.path,
            rhs_repr=str(rhs.value),
            operator=op,
        )

    if rhs.is_missing:
        return EvalResult.failure(
            ReasonCode.MISSING_RHS,
            f"RHS value is missing (None/NaN)",
            lhs_path=lhs.path,
            rhs_repr=str(rhs.value),
            operator=op,
        )

    if not lhs.is_numeric:
        return EvalResult.failure(
            ReasonCode.TYPE_MISMATCH,
            f"Operator '{op}' requires numeric LHS, got {lhs.value_type.name}",
            lhs_path=lhs.path,
            rhs_repr=str(rhs.value),
            operator=op,
        )

    if not rhs.is_numeric:
        return EvalResult.failure(
            ReasonCode.TYPE_MISMATCH,
            f"Operator '{op}' requires numeric RHS, got {rhs.value_type.name}",
            lhs_path=lhs.path,
            rhs_repr=str(rhs.value),
            operator=op,
        )

    return None


def eval_gt(lhs: RefValue, rhs: RefValue) -> EvalResult:
    """Evaluate lhs > rhs (numeric only)."""
    check = _check_numeric(lhs, rhs, ">")
    if check:
        return check

    result = lhs.value > rhs.value
    return EvalResult.success(result, lhs.path, str(rhs.value), ">")


def eval_lt(lhs: RefValue, rhs: RefValue) -> EvalResult:
    """Evaluate lhs < rhs (numeric only)."""
    check = _check_numeric(lhs, rhs, "<")
    if check:
        return check

    result = lhs.value < rhs.value
    return EvalResult.success(result, lhs.path, str(rhs.value), "<")


def eval_ge(lhs: RefValue, rhs: RefValue) -> EvalResult:
    """Evaluate lhs >= rhs (numeric only)."""
    check = _check_numeric(lhs, rhs, ">=")
    if check:
        return check

    result = lhs.value >= rhs.value
    return EvalResult.success(result, lhs.path, str(rhs.value), ">=")


def eval_le(lhs: RefValue, rhs: RefValue) -> EvalResult:
    """Evaluate lhs <= rhs (numeric only)."""
    check = _check_numeric(lhs, rhs, "<=")
    if check:
        return check

    result = lhs.value <= rhs.value
    return EvalResult.success(result, lhs.path, str(rhs.value), "<=")


def eval_eq(lhs: RefValue, rhs: RefValue) -> EvalResult:
    """
    Evaluate lhs == rhs (bool, int, enum only - NOT float).

    Float equality is rejected - use approx_eq with tolerance.
    """
    op = "=="

    if lhs.is_missing:
        return EvalResult.failure(
            ReasonCode.MISSING_LHS,
            "LHS value is missing (None/NaN)",
            lhs_path=lhs.path,
            rhs_repr=str(rhs.value),
            operator=op,
        )

    if rhs.is_missing:
        return EvalResult.failure(
            ReasonCode.MISSING_RHS,
            "RHS value is missing (None/NaN)",
            lhs_path=lhs.path,
            rhs_repr=str(rhs.value),
            operator=op,
        )

    # Reject float equality - must use approx_eq
    if lhs.value_type == ValueType.FLOAT or rhs.value_type == ValueType.FLOAT:
        return EvalResult.failure(
            ReasonCode.FLOAT_EQUALITY,
            "Float equality not allowed with '=='. Use 'near_abs' or 'near_pct' with tolerance",
            lhs_path=lhs.path,
            rhs_repr=str(rhs.value),
            operator=op,
        )

    # Allow: bool, int, enum (normalized to int), string (enum token)
    allowed = (ValueType.BOOL, ValueType.INT, ValueType.ENUM, ValueType.STRING)
    if lhs.value_type not in allowed:
        return EvalResult.failure(
            ReasonCode.TYPE_MISMATCH,
            f"Operator '==' requires bool/int/enum, got {lhs.value_type.name}",
            lhs_path=lhs.path,
            rhs_repr=str(rhs.value),
            operator=op,
        )

    # Case-insensitive comparison for string/enum values
    # Structures may output lowercase ("bullish") while DSL uses uppercase ("BULLISH")
    lhs_val = lhs.value
    rhs_val = rhs.value
    if isinstance(lhs_val, str) and isinstance(rhs_val, str):
        result = lhs_val.upper() == rhs_val.upper()
    else:
        result = lhs_val == rhs_val
    return EvalResult.success(result, lhs.path, str(rhs.value), "==")


def eval_neq(lhs: RefValue, rhs: RefValue) -> EvalResult:
    """
    Evaluate lhs != rhs (bool, int, enum only - NOT float).

    Float inequality is rejected - use near_abs/near_pct with tolerance.
    """
    op = "!="

    if lhs.is_missing:
        return EvalResult.failure(
            ReasonCode.MISSING_LHS,
            "LHS value is missing (None/NaN)",
            lhs_path=lhs.path,
            rhs_repr=str(rhs.value),
            operator=op,
        )

    if rhs.is_missing:
        return EvalResult.failure(
            ReasonCode.MISSING_RHS,
            "RHS value is missing (None/NaN)",
            lhs_path=lhs.path,
            rhs_repr=str(rhs.value),
            operator=op,
        )

    # Reject float inequality - must use near_* operators
    if lhs.value_type == ValueType.FLOAT or rhs.value_type == ValueType.FLOAT:
        return EvalResult.failure(
            ReasonCode.FLOAT_EQUALITY,
            "Float inequality not allowed with '!='. Use 'near_abs' or 'near_pct' with tolerance",
            lhs_path=lhs.path,
            rhs_repr=str(rhs.value),
            operator=op,
        )

    # Allow: bool, int, enum (normalized to int), string (enum token)
    allowed = (ValueType.BOOL, ValueType.INT, ValueType.ENUM, ValueType.STRING)
    if lhs.value_type not in allowed:
        return EvalResult.failure(
            ReasonCode.TYPE_MISMATCH,
            f"Operator '!=' requires bool/int/enum, got {lhs.value_type.name}",
            lhs_path=lhs.path,
            rhs_repr=str(rhs.value),
            operator=op,
        )

    # Case-insensitive comparison for string/enum values
    # Structures may output lowercase ("bullish") while DSL uses uppercase ("BULLISH")
    lhs_val = lhs.value
    rhs_val = rhs.value
    if isinstance(lhs_val, str) and isinstance(rhs_val, str):
        result = lhs_val.upper() != rhs_val.upper()
    else:
        result = lhs_val != rhs_val
    return EvalResult.success(result, lhs.path, str(rhs.value), "!=")


def eval_approx_eq(
    lhs: RefValue,
    rhs: RefValue,
    tolerance: float | None = None,
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
            ReasonCode.INVALID_TOLERANCE,
            "approx_eq requires 'tolerance' parameter",
            lhs_path=lhs.path,
            rhs_repr=str(rhs.value),
            operator=op,
        )

    if tolerance < 0:
        return EvalResult.failure(
            ReasonCode.INVALID_TOLERANCE,
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


def eval_between(lhs: RefValue, low: float, high: float) -> EvalResult:
    """
    Evaluate low <= lhs <= high (numeric only).

    Args:
        lhs: Left-hand side value
        low: Lower bound (inclusive)
        high: Upper bound (inclusive)

    Returns:
        EvalResult with comparison outcome
    """
    op = "between"

    if lhs.is_missing:
        return EvalResult.failure(
            ReasonCode.MISSING_LHS,
            "LHS value is missing (None/NaN)",
            lhs_path=lhs.path,
            rhs_repr=f"[{low}, {high}]",
            operator=op,
        )

    if not lhs.is_numeric:
        return EvalResult.failure(
            ReasonCode.TYPE_MISMATCH,
            f"Operator 'between' requires numeric LHS, got {lhs.value_type.name}",
            lhs_path=lhs.path,
            rhs_repr=f"[{low}, {high}]",
            operator=op,
        )

    result = low <= lhs.value <= high
    return EvalResult.success(result, lhs.path, f"[{low}, {high}]", op)


def eval_near_abs(lhs: RefValue, rhs: RefValue, tolerance: float) -> EvalResult:
    """
    Evaluate |lhs - rhs| <= tolerance (absolute tolerance).

    Args:
        lhs: Left-hand side value
        rhs: Right-hand side value
        tolerance: Absolute tolerance

    Returns:
        EvalResult with comparison outcome
    """
    op = "near_abs"

    if tolerance < 0:
        return EvalResult.failure(
            ReasonCode.INVALID_TOLERANCE,
            f"Tolerance must be non-negative, got {tolerance}",
            lhs_path=lhs.path,
            rhs_repr=str(rhs.value),
            operator=op,
        )

    check = _check_numeric(lhs, rhs, op)
    if check:
        return check

    result = abs(lhs.value - rhs.value) <= tolerance
    return EvalResult.success(result, lhs.path, f"{rhs.value} ± {tolerance}", op)


def eval_near_pct(lhs: RefValue, rhs: RefValue, tolerance: float) -> EvalResult:
    """
    Evaluate |lhs - rhs| / |rhs| <= tolerance (percentage tolerance).

    Args:
        lhs: Left-hand side value
        rhs: Right-hand side value
        tolerance: Relative tolerance (0.01 = 1%)

    Returns:
        EvalResult with comparison outcome
    """
    op = "near_pct"

    if tolerance < 0:
        return EvalResult.failure(
            ReasonCode.INVALID_TOLERANCE,
            f"Tolerance must be non-negative, got {tolerance}",
            lhs_path=lhs.path,
            rhs_repr=str(rhs.value),
            operator=op,
        )

    check = _check_numeric(lhs, rhs, op)
    if check:
        return check

    # Division by zero: cannot compute percentage when reference is zero
    if rhs.value == 0:
        return EvalResult.failure(
            ReasonCode.INVALID_TOLERANCE,
            f"Cannot compute percentage with zero reference (rhs=0)",
            lhs_path=lhs.path,
            rhs_repr="0",
            operator=op,
        )

    result = abs(lhs.value - rhs.value) / abs(rhs.value) <= tolerance

    pct_str = f"{tolerance * 100:.2f}%"
    return EvalResult.success(result, lhs.path, f"{rhs.value} ± {pct_str}", op)


def eval_in(lhs: RefValue, values: tuple) -> EvalResult:
    """
    Evaluate lhs in values (discrete types only - bool/int/enum/string).

    Args:
        lhs: Left-hand side value
        values: Tuple of allowed values

    Returns:
        EvalResult with comparison outcome
    """
    op = "in"

    if lhs.is_missing:
        return EvalResult.failure(
            ReasonCode.MISSING_LHS,
            "LHS value is missing (None/NaN)",
            lhs_path=lhs.path,
            rhs_repr=str(list(values)),
            operator=op,
        )

    # Reject float - same as eq
    if lhs.value_type == ValueType.FLOAT:
        return EvalResult.failure(
            ReasonCode.FLOAT_EQUALITY,
            "Float not allowed with 'in'. Use numeric range operators instead",
            lhs_path=lhs.path,
            rhs_repr=str(list(values)),
            operator=op,
        )

    # Allow: bool, int, enum, string
    allowed = (ValueType.BOOL, ValueType.INT, ValueType.ENUM, ValueType.STRING)
    if lhs.value_type not in allowed:
        return EvalResult.failure(
            ReasonCode.TYPE_MISMATCH,
            f"Operator 'in' requires bool/int/enum/string, got {lhs.value_type.name}",
            lhs_path=lhs.path,
            rhs_repr=str(list(values)),
            operator=op,
        )

    result = lhs.value in values
    return EvalResult.success(result, lhs.path, str(list(values)), op)


def eval_cross_above(
    lhs_curr: RefValue,
    lhs_prev: RefValue,
    rhs: RefValue,
) -> EvalResult:
    """
    Evaluate cross_above: LHS crosses above RHS.

    Definition (TradingView standard): prev_lhs <= rhs AND curr_lhs > rhs
    Was at or below threshold, now strictly above.

    Args:
        lhs_curr: Current bar LHS value
        lhs_prev: Previous bar LHS value
        rhs: Right-hand side value (threshold or indicator)

    Returns:
        EvalResult: True if cross above occurred
    """
    op = "cross_above"

    # Check current bar values
    check = _check_numeric(lhs_curr, rhs, op)
    if check:
        return check

    # Check previous bar value
    if lhs_prev.is_missing:
        return EvalResult.failure(
            ReasonCode.MISSING_PREV_VALUE,
            "Previous bar value missing for cross_above",
            lhs_path=lhs_curr.path,
            rhs_repr=str(rhs.value),
            operator=op,
        )

    if not lhs_prev.is_numeric:
        return EvalResult.failure(
            ReasonCode.TYPE_MISMATCH,
            f"Previous value must be numeric, got {lhs_prev.value_type.name}",
            lhs_path=lhs_curr.path,
            rhs_repr=str(rhs.value),
            operator=op,
        )

    # cross_above (TradingView): prev <= rhs AND curr > rhs
    result = lhs_prev.value <= rhs.value and lhs_curr.value > rhs.value
    return EvalResult.success(result, lhs_curr.path, str(rhs.value), op)


def eval_cross_below(
    lhs_curr: RefValue,
    lhs_prev: RefValue,
    rhs: RefValue,
) -> EvalResult:
    """
    Evaluate cross_below: LHS crosses below RHS.

    Definition (TradingView standard): prev_lhs >= rhs AND curr_lhs < rhs
    Was at or above threshold, now strictly below.

    Args:
        lhs_curr: Current bar LHS value
        lhs_prev: Previous bar LHS value
        rhs: Right-hand side value (threshold or indicator)

    Returns:
        EvalResult: True if cross below occurred
    """
    op = "cross_below"

    # Check current bar values
    check = _check_numeric(lhs_curr, rhs, op)
    if check:
        return check

    # Check previous bar value
    if lhs_prev.is_missing:
        return EvalResult.failure(
            ReasonCode.MISSING_PREV_VALUE,
            "Previous bar value missing for cross_below",
            lhs_path=lhs_curr.path,
            rhs_repr=str(rhs.value),
            operator=op,
        )

    if not lhs_prev.is_numeric:
        return EvalResult.failure(
            ReasonCode.TYPE_MISMATCH,
            f"Previous value must be numeric, got {lhs_prev.value_type.name}",
            lhs_path=lhs_curr.path,
            rhs_repr=str(rhs.value),
            operator=op,
        )

    # cross_below (TradingView): prev >= rhs AND curr < rhs
    result = lhs_prev.value >= rhs.value and lhs_curr.value < rhs.value
    return EvalResult.success(result, lhs_curr.path, str(rhs.value), op)


# Operator dispatch table
# Note: between, near_abs, near_pct, in, cross_above, cross_below
# are handled separately due to different call signatures
# SYMBOLS are the canonical form (refactored 2026-01-09)
OPERATORS: dict[str, Callable] = {
    ">": eval_gt,
    "<": eval_lt,
    ">=": eval_ge,
    "<=": eval_le,
    "==": eval_eq,
    "!=": eval_neq,
    "approx_eq": eval_approx_eq,
}

# Operators with special signatures (not in OPERATORS dispatch table)
# - between: (lhs, low, high)
# - near_abs: (lhs, rhs, tolerance)
# - near_pct: (lhs, rhs, tolerance)
# - in: (lhs, values)
# - cross_above/cross_below: (lhs_curr, lhs_prev, rhs)


def evaluate_condition(
    lhs_ref: CompiledRef,
    operator: str,
    rhs_ref: CompiledRef,
    snapshot,
    tolerance: float | None = None,
    relative_tolerance: bool = False,
) -> EvalResult:
    """
    Legacy: Evaluate a compiled condition against a snapshot.

    .. deprecated::
        This function is legacy. The production hot path uses
        ExprEvaluator (src/backtest/rules/evaluation/). Retained
        only for smoke tests and backward compatibility.

    Args:
        lhs_ref: Compiled left-hand side reference
        operator: Operator symbol (">", "<", ">=", "<=", "==", "!=", etc.)
        rhs_ref: Compiled right-hand side reference
        snapshot: RuntimeSnapshotView instance
        tolerance: For approx_eq, the tolerance value
        relative_tolerance: For approx_eq, whether tolerance is relative

    Returns:
        EvalResult with evaluation outcome and reason code
    """
    import warnings
    warnings.warn(
        "evaluate_condition() is legacy. Use ExprEvaluator for production code.",
        DeprecationWarning,
        stacklevel=2,
    )
    # Normalize operator
    op = operator.lower()

    # Handle crossover operators (need previous bar value)
    if op in ("cross_above", "cross_below"):
        # Resolve current values
        lhs_curr = lhs_ref.resolve(snapshot)
        rhs = rhs_ref.resolve(snapshot)

        # Get previous bar LHS value using offset resolution
        prev_value = snapshot.get_with_offset(lhs_ref.path, offset=1)
        lhs_prev = RefValue.from_resolved(prev_value, f"{lhs_ref.path}[prev]")

        if op == "cross_above":
            return eval_cross_above(lhs_curr, lhs_prev, rhs)
        else:
            return eval_cross_below(lhs_curr, lhs_prev, rhs)

    # Check for unknown operator
    if op not in OPERATORS:
        return EvalResult.failure(
            ReasonCode.UNKNOWN_OPERATOR,
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
    condition: dict[str, Any],
    snapshot,
) -> EvalResult:
    """
    Evaluate a condition dict (with pre-compiled refs) against a snapshot.

    This is the main entry point for Play signal evaluation.

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
            ReasonCode.INTERNAL_ERROR,
            "Condition missing compiled lhs_ref. Was it normalized?",
        )

    if not isinstance(rhs_ref, CompiledRef):
        return EvalResult.failure(
            ReasonCode.INTERNAL_ERROR,
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
