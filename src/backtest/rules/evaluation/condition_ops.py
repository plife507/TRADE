"""
Condition evaluation for DSL expressions.

Handles Cond evaluation, crossover operators, and operator dispatch.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..dsl_nodes import (
    Cond,
    FeatureRef,
    ScalarValue,
    RangeValue,
    ListValue,
    ArithmeticExpr,
    CROSSOVER_OPERATORS,
)
from ..types import EvalResult, ReasonCode, RefValue
from ..eval import (
    eval_gt,
    eval_lt,
    eval_ge,
    eval_le,
    eval_eq,
    eval_neq,
    eval_between,
    eval_near_abs,
    eval_near_pct,
    eval_in,
)
from .resolve import (
    resolve_ref,
    resolve_lhs,
    evaluate_arithmetic,
    infer_value_type,
)

if TYPE_CHECKING:
    from ...runtime.snapshot_view import RuntimeSnapshotView


def dispatch_operator(
    op: str,
    lhs: RefValue,
    rhs: RefValue,
    tolerance: float | None,
) -> EvalResult:
    """
    Dispatch to the appropriate operator function.

    Args:
        op: Operator symbol (>, <, >=, <=, ==, !=, etc.)
        lhs: Resolved left-hand side
        rhs: Resolved right-hand side
        tolerance: For near_* operators

    Returns:
        EvalResult from operator
    """
    if op == ">":
        return eval_gt(lhs, rhs)
    elif op == "<":
        return eval_lt(lhs, rhs)
    elif op == ">=":
        return eval_ge(lhs, rhs)
    elif op == "<=":
        return eval_le(lhs, rhs)
    elif op == "==":
        return eval_eq(lhs, rhs)
    elif op == "!=":
        return eval_neq(lhs, rhs)
    elif op == "near_abs":
        if tolerance is None:
            return EvalResult.failure(
                ReasonCode.INVALID_TOLERANCE,
                "near_abs requires tolerance",
                lhs_path=lhs.path,
                operator=op,
            )
        return eval_near_abs(lhs, rhs, tolerance)
    elif op == "near_pct":
        if tolerance is None:
            return EvalResult.failure(
                ReasonCode.INVALID_TOLERANCE,
                "near_pct requires tolerance",
                lhs_path=lhs.path,
                operator=op,
            )
        return eval_near_pct(lhs, rhs, tolerance)
    else:
        return EvalResult.failure(
            ReasonCode.UNKNOWN_OPERATOR,
            f"Unknown operator: {op}",
            lhs_path=lhs.path,
            operator=op,
        )


def eval_crossover(
    cond: Cond,
    lhs_curr: RefValue,
    snapshot: "RuntimeSnapshotView",
) -> EvalResult:
    """
    Evaluate crossover operator (cross_above, cross_below).

    Requires previous bar values for both LHS and RHS.
    """
    # Crossover requires FeatureRef LHS (ArithmeticExpr doesn't support shifted)
    lhs = cond.lhs
    if not isinstance(lhs, FeatureRef):
        return EvalResult.failure(
            ReasonCode.INTERNAL_ERROR,
            "Crossover requires FeatureRef LHS, not ArithmeticExpr",
            lhs_path=str(lhs),
            operator=cond.op,
        )

    # Get previous LHS value
    lhs_prev_ref = lhs.shifted(1)
    lhs_prev = resolve_ref(lhs_prev_ref, snapshot)
    if lhs_prev.is_missing:
        return EvalResult.failure(
            ReasonCode.MISSING_PREV_VALUE,
            f"Previous LHS value is missing: {lhs.feature_id}",
            lhs_path=lhs.feature_id,
            operator=cond.op,
        )

    # Resolve current RHS
    if isinstance(cond.rhs, ScalarValue):
        rhs_curr = RefValue(
            value=cond.rhs.value,
            value_type=infer_value_type(cond.rhs.value),
            path="literal",
        )
        rhs_prev = rhs_curr  # Literal is same for prev bar
    elif isinstance(cond.rhs, FeatureRef):
        rhs_curr = resolve_ref(cond.rhs, snapshot)
        if rhs_curr.is_missing:
            return EvalResult.failure(
                ReasonCode.MISSING_RHS,
                f"RHS value is missing: {cond.rhs.feature_id}",
                lhs_path=lhs.feature_id,
                operator=cond.op,
            )
        # Get previous RHS value
        rhs_prev_ref = cond.rhs.shifted(1)
        rhs_prev = resolve_ref(rhs_prev_ref, snapshot)
        if rhs_prev.is_missing:
            return EvalResult.failure(
                ReasonCode.MISSING_PREV_VALUE,
                f"Previous RHS value is missing: {cond.rhs.feature_id}",
                lhs_path=lhs.feature_id,
                operator=cond.op,
            )
    else:
        return EvalResult.failure(
            ReasonCode.INTERNAL_ERROR,
            "Crossover requires scalar or feature reference RHS",
            lhs_path=lhs.feature_id,
            operator=cond.op,
        )

    # Evaluate crossover semantics:
    # cross_above: prev_lhs <= prev_rhs AND curr_lhs > curr_rhs
    # cross_below: prev_lhs >= prev_rhs AND curr_lhs < curr_rhs
    if cond.op == "cross_above":
        crossed = lhs_prev.value <= rhs_prev.value and lhs_curr.value > rhs_curr.value
    else:  # cross_below
        crossed = lhs_prev.value >= rhs_prev.value and lhs_curr.value < rhs_curr.value

    return EvalResult.success(
        crossed,
        lhs.feature_id,
        str(rhs_curr.value),
        cond.op,
    )


def eval_cond(cond: Cond, snapshot: "RuntimeSnapshotView") -> EvalResult:
    """
    Evaluate a single condition.

    Resolves LHS and RHS values and dispatches to appropriate operator.
    LHS can be FeatureRef or ArithmeticExpr.
    RHS can be FeatureRef, ScalarValue, RangeValue, ListValue, or ArithmeticExpr.
    """
    # Resolve LHS (FeatureRef or ArithmeticExpr)
    lhs = resolve_lhs(cond.lhs, snapshot)
    if lhs.is_missing:
        # Build appropriate error message
        if isinstance(cond.lhs, FeatureRef):
            lhs_path = cond.lhs.feature_id
            msg = f"LHS value is missing: {cond.lhs.feature_id}"
        else:
            lhs_path = "arithmetic"
            msg = "LHS arithmetic expression has missing value"
        return EvalResult.failure(
            ReasonCode.MISSING_LHS,
            msg,
            lhs_path=lhs_path,
            operator=cond.op,
        )

    # Get LHS path for error messages
    lhs_path = cond.lhs.feature_id if isinstance(cond.lhs, FeatureRef) else "arithmetic"

    # Handle crossover operators (only for FeatureRef LHS)
    if cond.op in CROSSOVER_OPERATORS:
        if not isinstance(cond.lhs, FeatureRef):
            return EvalResult.failure(
                ReasonCode.INTERNAL_ERROR,
                "Crossover operators require FeatureRef LHS, not arithmetic",
                lhs_path=lhs_path,
                operator=cond.op,
            )
        return eval_crossover(cond, lhs, snapshot)

    # Resolve RHS based on type
    if isinstance(cond.rhs, ScalarValue):
        rhs = RefValue(
            value=cond.rhs.value,
            value_type=infer_value_type(cond.rhs.value),
            path="literal",
        )
    elif isinstance(cond.rhs, FeatureRef):
        rhs = resolve_ref(cond.rhs, snapshot)
        if rhs.is_missing:
            return EvalResult.failure(
                ReasonCode.MISSING_RHS,
                f"RHS value is missing: {cond.rhs.feature_id}",
                lhs_path=lhs_path,
                operator=cond.op,
            )
    elif isinstance(cond.rhs, ArithmeticExpr):
        rhs = evaluate_arithmetic(cond.rhs, snapshot)
        if rhs.is_missing:
            return EvalResult.failure(
                ReasonCode.MISSING_RHS,
                "RHS arithmetic expression has missing value",
                lhs_path=lhs_path,
                operator=cond.op,
            )
    elif isinstance(cond.rhs, RangeValue):
        # Special handling for 'between'
        return eval_between(lhs, cond.rhs.low, cond.rhs.high)
    elif isinstance(cond.rhs, ListValue):
        # Special handling for 'in'
        return eval_in(lhs, cond.rhs.values)
    else:
        return EvalResult.failure(
            ReasonCode.INTERNAL_ERROR,
            f"Unknown RHS type: {type(cond.rhs).__name__}",
            lhs_path=lhs_path,
            operator=cond.op,
        )

    # Dispatch to operator
    return dispatch_operator(cond.op, lhs, rhs, cond.tolerance)
