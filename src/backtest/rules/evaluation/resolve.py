"""
Value resolution for DSL expressions.

Handles resolving FeatureRef and ArithmeticExpr to RefValue.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from ..dsl_nodes import (
    FeatureRef,
    ScalarValue,
    ArithmeticExpr,
)
from ..types import RefValue, ValueType

if TYPE_CHECKING:
    from ...runtime.snapshot_view import RuntimeSnapshotView


def infer_value_type(value: Any) -> ValueType:
    """Infer ValueType from a Python value."""
    if value is None:
        return ValueType.MISSING
    if isinstance(value, bool):
        return ValueType.BOOL
    if isinstance(value, int):
        return ValueType.INT
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return ValueType.MISSING
        return ValueType.FLOAT
    if isinstance(value, str):
        return ValueType.STRING
    return ValueType.UNKNOWN


def resolve_ref(
    ref: FeatureRef, snapshot: "RuntimeSnapshotView"
) -> RefValue:
    """
    Resolve a FeatureRef to a RefValue using the snapshot.

    Uses declared type from registry to handle integer-like floats.
    For example, supertrend.direction is declared INT but stored as float64.

    Args:
        ref: FeatureRef to resolve
        snapshot: RuntimeSnapshotView providing values

    Returns:
        RefValue with resolved value and type
    """
    try:
        # Use snapshot's feature access API
        # The snapshot should provide: get_feature(feature_id, field, offset)
        value = snapshot.get_feature_value(
            feature_id=ref.feature_id,
            field=ref.field,
            offset=ref.offset,
        )

        # Look up declared type from registry for INT coercion
        declared_type = snapshot.get_feature_output_type(
            ref.feature_id, ref.field or "value"
        )

        path = f"{ref.feature_id}.{ref.field}"
        return RefValue.from_resolved_with_declared_type(value, path, declared_type)
    except (KeyError, AttributeError):
        # Return missing value if lookup fails
        return RefValue.missing(f"{ref.feature_id}.{ref.field}")


def evaluate_arithmetic(
    arith: ArithmeticExpr,
    snapshot: "RuntimeSnapshotView",
) -> RefValue:
    """
    Evaluate an arithmetic expression and return the computed value.

    Recursively evaluates nested arithmetic and resolves feature references.

    Args:
        arith: ArithmeticExpr to evaluate
        snapshot: RuntimeSnapshotView providing values

    Returns:
        RefValue with computed value or missing flag

    Semantics:
        - Division by zero returns None (is_missing=True)
        - INT op FLOAT -> FLOAT
        - Division always -> FLOAT
        - Missing operand -> missing result
    """
    # Resolve left operand
    if isinstance(arith.left, FeatureRef):
        left_val = resolve_ref(arith.left, snapshot)
    elif isinstance(arith.left, ScalarValue):
        left_val = RefValue(
            value=arith.left.value,
            value_type=infer_value_type(arith.left.value),
            path="literal",
        )
    elif isinstance(arith.left, ArithmeticExpr):
        left_val = evaluate_arithmetic(arith.left, snapshot)
    else:
        return RefValue.missing("arithmetic.left")

    if left_val.is_missing:
        return RefValue.missing("arithmetic.left")

    # Resolve right operand
    if isinstance(arith.right, FeatureRef):
        right_val = resolve_ref(arith.right, snapshot)
    elif isinstance(arith.right, ScalarValue):
        right_val = RefValue(
            value=arith.right.value,
            value_type=infer_value_type(arith.right.value),
            path="literal",
        )
    elif isinstance(arith.right, ArithmeticExpr):
        right_val = evaluate_arithmetic(arith.right, snapshot)
    else:
        return RefValue.missing("arithmetic.right")

    if right_val.is_missing:
        return RefValue.missing("arithmetic.right")

    # Apply operation
    left = left_val.value
    right = right_val.value

    try:
        if arith.op == "+":
            result = left + right
        elif arith.op == "-":
            result = left - right
        elif arith.op == "*":
            result = left * right
        elif arith.op == "/":
            if right == 0:
                return RefValue.missing("arithmetic.div_by_zero")
            result = left / right
        elif arith.op == "%":
            if right == 0:
                return RefValue.missing("arithmetic.mod_by_zero")
            result = left % right
        else:
            return RefValue.missing(f"arithmetic.unknown_op:{arith.op}")

        return RefValue(
            value=result,
            value_type=infer_value_type(result),
            path=f"({left_val.path}{arith.op}{right_val.path})",
        )
    except (TypeError, ZeroDivisionError):
        return RefValue.missing("arithmetic.error")


def resolve_lhs(
    lhs: FeatureRef | ArithmeticExpr,
    snapshot: "RuntimeSnapshotView",
) -> RefValue:
    """
    Resolve LHS value (FeatureRef or ArithmeticExpr).

    Args:
        lhs: LHS to resolve
        snapshot: RuntimeSnapshotView providing values

    Returns:
        RefValue with resolved value
    """
    if isinstance(lhs, FeatureRef):
        return resolve_ref(lhs, snapshot)
    elif isinstance(lhs, ArithmeticExpr):
        return evaluate_arithmetic(lhs, snapshot)
    else:
        return RefValue.missing("lhs.unknown_type")
