"""
DSL Utility Functions for Play Expression Language.

This module provides utility functions for working with DSL nodes:
- get_max_offset: Calculate maximum offset in expression tree
- validate_expr_types: Validate operator/type compatibility
- get_referenced_features: Extract all referenced feature IDs
- Serialization functions: Convert nodes to dict/list format
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .constants import (
    CROSSOVER_OPERATORS,
    NUMERIC_OPERATORS,
    DISCRETE_OPERATORS,
    ACTION_TF_MINUTES,
)
from .base import FeatureRef, ScalarValue, RangeValue, ListValue, ArithmeticExpr, RhsValue
from .condition import Cond
from .boolean import AllExpr, AnyExpr, NotExpr, SetupRef
from .windows import (
    HoldsFor, OccurredWithin, CountTrue,
    HoldsForDuration, OccurredWithinDuration, CountTrueDuration,
)
from .types import Expr

if TYPE_CHECKING:
    from collections.abc import Callable
    from ..types import FeatureOutputType


# =============================================================================
# Offset Analysis
# =============================================================================

def _get_arithmetic_max_offset(arith: ArithmeticExpr) -> int:
    """Get max offset from an ArithmeticExpr recursively."""
    max_off = 0
    # Check left operand
    if isinstance(arith.left, FeatureRef):
        max_off = max(max_off, arith.left.offset)
    elif isinstance(arith.left, ArithmeticExpr):
        max_off = max(max_off, _get_arithmetic_max_offset(arith.left))
    # Check right operand
    if isinstance(arith.right, FeatureRef):
        max_off = max(max_off, arith.right.offset)
    elif isinstance(arith.right, ArithmeticExpr):
        max_off = max(max_off, _get_arithmetic_max_offset(arith.right))
    return max_off


def get_max_offset(expr: Expr) -> int:
    """
    Get the maximum offset referenced in an expression tree.

    Used for warmup computation. Cross_* operators implicitly use offset=1.

    Args:
        expr: Expression to analyze.

    Returns:
        Maximum offset value found.
    """
    if isinstance(expr, Cond):
        # Get max offset from LHS (can be FeatureRef or ArithmeticExpr)
        if isinstance(expr.lhs, FeatureRef):
            max_off = expr.lhs.offset
        elif isinstance(expr.lhs, ArithmeticExpr):
            max_off = _get_arithmetic_max_offset(expr.lhs)
        else:
            max_off = 0
        # Check RHS
        if isinstance(expr.rhs, FeatureRef):
            max_off = max(max_off, expr.rhs.offset)
        elif isinstance(expr.rhs, ArithmeticExpr):
            max_off = max(max_off, _get_arithmetic_max_offset(expr.rhs))
        # Cross operators implicitly need previous bar
        if expr.op in CROSSOVER_OPERATORS:
            max_off = max(max_off, 1)
        return max_off

    elif isinstance(expr, AllExpr):
        return max((get_max_offset(c) for c in expr.children), default=0)

    elif isinstance(expr, AnyExpr):
        return max((get_max_offset(c) for c in expr.children), default=0)

    elif isinstance(expr, NotExpr):
        return get_max_offset(expr.child)

    elif isinstance(expr, (HoldsFor, OccurredWithin)):
        # Bar-based window ops shift expr by 0..bars-1
        return get_max_offset(expr.expr) + expr.bars - 1

    elif isinstance(expr, CountTrue):
        return get_max_offset(expr.expr) + expr.bars - 1

    elif isinstance(expr, (HoldsForDuration, OccurredWithinDuration)):
        # Duration-based window ops - convert to bars at 1m
        bars = expr.to_bars(ACTION_TF_MINUTES)
        return get_max_offset(expr.expr) + bars - 1

    elif isinstance(expr, CountTrueDuration):
        bars = expr.to_bars(ACTION_TF_MINUTES)
        return get_max_offset(expr.expr) + bars - 1

    else:
        return 0


# =============================================================================
# Type Validation
# =============================================================================

def validate_operator_type_compatibility(
    cond: Cond,
    lhs_output_type: "FeatureOutputType",
) -> list[str]:
    """
    Validate that an operator is compatible with the LHS output type.

    This is called at compile-time (Play loading) to catch type errors
    before runtime.

    Type compatibility rules:
    - FLOAT: CANNOT use eq/in (must use near_abs/near_pct for equality)
    - INT, BOOL, ENUM: CAN use eq/in (discrete types)
    - All numeric types: CAN use gt/gte/lt/lte/between/near_*/cross_*

    Args:
        cond: The Cond node to validate.
        lhs_output_type: The output type of the LHS feature.

    Returns:
        List of error messages (empty if valid).

    Examples:
        >>> from src.backtest.rules.types import FeatureOutputType
        >>> cond = Cond(FeatureRef("rsi_14"), "eq", ScalarValue(50.0))
        >>> validate_operator_type_compatibility(cond, FeatureOutputType.FLOAT)
        ["Operator 'eq' cannot be used with FLOAT type (feature: rsi_14). Use 'near_abs' or 'near_pct' for float equality."]
    """
    from ..types import FeatureOutputType

    errors: list[str] = []

    # Check discrete operators (eq, in) against non-discrete types
    if cond.op in DISCRETE_OPERATORS:
        if not lhs_output_type.is_discrete():
            errors.append(
                f"Operator '{cond.op}' cannot be used with {lhs_output_type.name} type "
                f"(feature: {cond.lhs.feature_id}). "
                f"Use 'near_abs' or 'near_pct' for float equality."
            )

    # Check numeric operators against non-numeric types
    # Note: Currently all our types are numeric-compatible except ENUM for some operators
    # ENUM can use eq/in but not gt/lt/between/near_*
    if cond.op in NUMERIC_OPERATORS:
        if lhs_output_type == FeatureOutputType.ENUM:
            errors.append(
                f"Operator '{cond.op}' cannot be used with ENUM type "
                f"(feature: {cond.lhs.feature_id}). "
                f"Use 'eq' or 'in' for enum comparisons."
            )
        elif lhs_output_type == FeatureOutputType.BOOL:
            # Boolean can use some numeric operators (debatable)
            # For now, only allow eq for booleans
            if cond.op not in ("eq",):
                errors.append(
                    f"Operator '{cond.op}' cannot be used with BOOL type "
                    f"(feature: {cond.lhs.feature_id}). "
                    f"Use 'eq' for boolean comparisons."
                )

    return errors


def validate_expr_types(
    expr: Expr,
    get_output_type: "Callable[[str, str], FeatureOutputType]",
) -> list[str]:
    """
    Validate operator/type compatibility for all conditions in an expression tree.

    This recursively walks the expression tree and validates each Cond node
    against the feature output types provided by the get_output_type callback.

    Args:
        expr: Expression tree to validate.
        get_output_type: Callback that takes (feature_id, field) and returns
            FeatureOutputType. Typically registry.get_output_type.

    Returns:
        List of all error messages (empty if valid).

    Examples:
        >>> errors = validate_expr_types(expr, registry.get_output_type)
        >>> if errors:
        ...     raise ValueError("\\n".join(errors))
    """
    errors: list[str] = []

    def validate_recursive(e: Expr) -> None:
        if isinstance(e, Cond):
            try:
                lhs_type = get_output_type(e.lhs.feature_id, e.lhs.field)
                cond_errors = validate_operator_type_compatibility(e, lhs_type)
                errors.extend(cond_errors)
            except (KeyError, ValueError):
                # Feature not found or field not found - skip type validation
                # (other validation will catch missing features)
                pass

        elif isinstance(e, AllExpr):
            for child in e.children:
                validate_recursive(child)

        elif isinstance(e, AnyExpr):
            for child in e.children:
                validate_recursive(child)

        elif isinstance(e, NotExpr):
            validate_recursive(e.child)

        elif isinstance(e, (HoldsFor, OccurredWithin, CountTrue)):
            validate_recursive(e.expr)

        elif isinstance(e, (HoldsForDuration, OccurredWithinDuration, CountTrueDuration)):
            validate_recursive(e.expr)

    validate_recursive(expr)
    return errors


# =============================================================================
# Feature Collection
# =============================================================================

def _collect_arithmetic_features(arith: ArithmeticExpr, features: set[str]) -> None:
    """Collect feature IDs from an ArithmeticExpr recursively."""
    if isinstance(arith.left, FeatureRef):
        features.add(arith.left.feature_id)
    elif isinstance(arith.left, ArithmeticExpr):
        _collect_arithmetic_features(arith.left, features)
    if isinstance(arith.right, FeatureRef):
        features.add(arith.right.feature_id)
    elif isinstance(arith.right, ArithmeticExpr):
        _collect_arithmetic_features(arith.right, features)


def get_referenced_features(expr: Expr) -> set[str]:
    """
    Get all feature IDs referenced in an expression tree.

    Args:
        expr: Expression to analyze.

    Returns:
        Set of feature IDs.
    """
    features: set[str] = set()

    def collect(e: Expr) -> None:
        if isinstance(e, Cond):
            # Collect from LHS (FeatureRef or ArithmeticExpr)
            if isinstance(e.lhs, FeatureRef):
                features.add(e.lhs.feature_id)
            elif isinstance(e.lhs, ArithmeticExpr):
                _collect_arithmetic_features(e.lhs, features)
            # Collect from RHS
            if isinstance(e.rhs, FeatureRef):
                features.add(e.rhs.feature_id)
            elif isinstance(e.rhs, ArithmeticExpr):
                _collect_arithmetic_features(e.rhs, features)

        elif isinstance(e, AllExpr):
            for child in e.children:
                collect(child)

        elif isinstance(e, AnyExpr):
            for child in e.children:
                collect(child)

        elif isinstance(e, NotExpr):
            collect(e.child)

        elif isinstance(e, (HoldsFor, OccurredWithin, CountTrue)):
            collect(e.expr)

        elif isinstance(e, (HoldsForDuration, OccurredWithinDuration, CountTrueDuration)):
            collect(e.expr)

    collect(expr)
    return features


# =============================================================================
# Serialization Functions
# =============================================================================

def feature_ref_to_dict(ref: FeatureRef) -> dict:
    """Serialize a FeatureRef to dict."""
    result: dict = {"feature_id": ref.feature_id}
    if ref.field != "value":
        result["field"] = ref.field
    if ref.offset != 0:
        result["offset"] = ref.offset
    return result


def arithmetic_to_list(arith: ArithmeticExpr) -> list:
    """
    Serialize an ArithmeticExpr to list format.

    Format: [left, op, right]
    Nested arithmetic: [[left, op, right], op, right]
    """
    # Serialize left operand
    if isinstance(arith.left, FeatureRef):
        left = arith.left.feature_id if arith.left.field == "value" and arith.left.offset == 0 else feature_ref_to_dict(arith.left)
    elif isinstance(arith.left, ScalarValue):
        left = arith.left.value
    elif isinstance(arith.left, ArithmeticExpr):
        left = arithmetic_to_list(arith.left)
    else:
        raise ValueError(f"Unknown arithmetic operand type: {type(arith.left)}")

    # Serialize right operand
    if isinstance(arith.right, FeatureRef):
        right = arith.right.feature_id if arith.right.field == "value" and arith.right.offset == 0 else feature_ref_to_dict(arith.right)
    elif isinstance(arith.right, ScalarValue):
        right = arith.right.value
    elif isinstance(arith.right, ArithmeticExpr):
        right = arithmetic_to_list(arith.right)
    else:
        raise ValueError(f"Unknown arithmetic operand type: {type(arith.right)}")

    return [left, arith.op, right]


def lhs_to_dict(lhs: FeatureRef | ArithmeticExpr) -> dict | list:
    """Serialize an LHS value (FeatureRef or ArithmeticExpr)."""
    if isinstance(lhs, FeatureRef):
        return feature_ref_to_dict(lhs)
    elif isinstance(lhs, ArithmeticExpr):
        return arithmetic_to_list(lhs)
    else:
        raise ValueError(f"Unknown LHS type: {type(lhs)}")


def rhs_to_dict(rhs: RhsValue) -> dict | int | float | bool | str | list:
    """Serialize an RHS value to dict/primitive."""
    if isinstance(rhs, FeatureRef):
        return feature_ref_to_dict(rhs)
    elif isinstance(rhs, ScalarValue):
        return rhs.value
    elif isinstance(rhs, RangeValue):
        return {"low": rhs.low, "high": rhs.high}
    elif isinstance(rhs, ListValue):
        return list(rhs.values)
    elif isinstance(rhs, ArithmeticExpr):
        return arithmetic_to_list(rhs)
    else:
        raise ValueError(f"Unknown RHS type: {type(rhs)}")


def expr_to_dict(expr: Expr) -> dict:
    """
    Serialize an expression tree to dict format.

    The resulting dict can be serialized to YAML and parsed back
    by the dsl_parser module.

    Args:
        expr: Expression to serialize.

    Returns:
        Dict representation matching YAML schema.
    """
    if isinstance(expr, Cond):
        result: dict = {
            "lhs": lhs_to_dict(expr.lhs),
            "op": expr.op,
            "rhs": rhs_to_dict(expr.rhs),
        }
        if expr.tolerance is not None:
            result["tolerance"] = expr.tolerance
        return result

    elif isinstance(expr, AllExpr):
        return {"all": [expr_to_dict(c) for c in expr.children]}

    elif isinstance(expr, AnyExpr):
        return {"any": [expr_to_dict(c) for c in expr.children]}

    elif isinstance(expr, NotExpr):
        return {"not": expr_to_dict(expr.child)}

    elif isinstance(expr, HoldsFor):
        inner: dict = {
            "bars": expr.bars,
            "expr": expr_to_dict(expr.expr),
        }
        if expr.anchor_tf is not None:
            inner["anchor_tf"] = expr.anchor_tf
        return {"holds_for": inner}

    elif isinstance(expr, OccurredWithin):
        inner = {
            "bars": expr.bars,
            "expr": expr_to_dict(expr.expr),
        }
        if expr.anchor_tf is not None:
            inner["anchor_tf"] = expr.anchor_tf
        return {"occurred_within": inner}

    elif isinstance(expr, CountTrue):
        inner = {
            "bars": expr.bars,
            "min_true": expr.min_true,
            "expr": expr_to_dict(expr.expr),
        }
        if expr.anchor_tf is not None:
            inner["anchor_tf"] = expr.anchor_tf
        return {"count_true": inner}

    elif isinstance(expr, HoldsForDuration):
        return {
            "holds_for_duration": {
                "duration": expr.duration,
                "expr": expr_to_dict(expr.expr),
            }
        }

    elif isinstance(expr, OccurredWithinDuration):
        return {
            "occurred_within_duration": {
                "duration": expr.duration,
                "expr": expr_to_dict(expr.expr),
            }
        }

    elif isinstance(expr, CountTrueDuration):
        return {
            "count_true_duration": {
                "duration": expr.duration,
                "min_true": expr.min_true,
                "expr": expr_to_dict(expr.expr),
            }
        }

    elif isinstance(expr, SetupRef):
        return {"setup": expr.setup_id}

    else:
        raise ValueError(f"Unknown expression type: {type(expr)}")


__all__ = [
    # Offset analysis
    "get_max_offset",
    # Type validation
    "validate_operator_type_compatibility",
    "validate_expr_types",
    # Feature collection
    "get_referenced_features",
    # Serialization
    "feature_ref_to_dict",
    "arithmetic_to_list",
    "lhs_to_dict",
    "rhs_to_dict",
    "expr_to_dict",
]
