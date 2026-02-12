"""
Boolean operators for DSL expressions.

Handles AllExpr, AnyExpr, NotExpr evaluation with short-circuit semantics.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..dsl_nodes import (
    AllExpr,
    AnyExpr,
    NotExpr,
)
from ..types import EvalResult, ReasonCode
from .protocols import ExprEvaluatorProtocol

if TYPE_CHECKING:
    from ...runtime.snapshot_view import RuntimeSnapshotView


def eval_all(
    expr: AllExpr,
    snapshot: "RuntimeSnapshotView",
    evaluator: ExprEvaluatorProtocol,
) -> EvalResult:
    """
    Evaluate AllExpr (AND) with short-circuit.

    Returns False on first failing child.
    """
    for child in expr.children:
        result = evaluator.evaluate(child, snapshot)
        if not result.ok:
            return result  # Short-circuit: first failure wins
    # All passed
    return EvalResult.success(True, "all", "", "all")


def eval_any(
    expr: AnyExpr,
    snapshot: "RuntimeSnapshotView",
    evaluator: ExprEvaluatorProtocol,
) -> EvalResult:
    """
    Evaluate AnyExpr (OR) with short-circuit.

    Returns True on first passing child.
    """
    last_failure: EvalResult | None = None
    for child in expr.children:
        result = evaluator.evaluate(child, snapshot)
        if result.ok:
            return result  # Short-circuit: first success wins
        last_failure = result
    # None passed - return last failure (or generic failure)
    if last_failure:
        return last_failure
    return EvalResult.failure(
        ReasonCode.CONDITION_FAILED,
        "No conditions in any() were true",
        operator="any",
    )


# Reason codes that represent true errors (missing data, type issues, internal).
# These should propagate through NOT unchanged — they are NOT invertible.
_ERROR_REASONS = frozenset({
    ReasonCode.MISSING_VALUE,
    ReasonCode.MISSING_LHS,
    ReasonCode.MISSING_RHS,
    ReasonCode.MISSING_PREV_VALUE,
    ReasonCode.TYPE_MISMATCH,
    ReasonCode.FLOAT_EQUALITY,
    ReasonCode.UNKNOWN_OPERATOR,
    ReasonCode.UNSUPPORTED_OPERATOR,
    ReasonCode.INVALID_TOLERANCE,
    ReasonCode.INVALID_PATH,
    ReasonCode.UNKNOWN_NAMESPACE,
    ReasonCode.UNKNOWN_FIELD,
    ReasonCode.INTERNAL_ERROR,
})


def eval_not(
    expr: NotExpr,
    snapshot: "RuntimeSnapshotView",
    evaluator: ExprEvaluatorProtocol,
) -> EvalResult:
    """
    Evaluate NotExpr (negation).

    Inverts the result of the child expression.

    Semantics:
    - OK (clean evaluation): invert ok value (NOT true = false, NOT false = true)
    - CONDITION_FAILED / WINDOW_CONDITION_FAILED: these are normal "not met"
      results from any()/holds_for()/occurred_within()/count_true(), so NOT
      should invert them to true.
    - True errors (MISSING_*, TYPE_MISMATCH, INTERNAL_ERROR, etc.): propagate
      unchanged — cannot meaningfully invert missing data or type errors.
    """
    result = evaluator.evaluate(expr.child, snapshot)
    if result.reason in _ERROR_REASONS:
        # True errors: propagate unchanged
        return result
    # OK, CONDITION_FAILED, WINDOW_CONDITION_FAILED: invert the result
    return EvalResult.success(not result.ok, result.lhs_path or "", result.rhs_repr or "", "not")
