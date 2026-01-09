"""
Boolean operators for DSL expressions.

Handles AllExpr, AnyExpr, NotExpr evaluation with short-circuit semantics.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from ..dsl_nodes import (
    Expr,
    AllExpr,
    AnyExpr,
    NotExpr,
)
from ..types import EvalResult, ReasonCode

if TYPE_CHECKING:
    from ...runtime.snapshot import RuntimeSnapshotView


class ExprEvaluatorProtocol(Protocol):
    """Protocol for expression evaluator to avoid circular imports."""

    def evaluate(self, expr: Expr, snapshot: "RuntimeSnapshotView") -> EvalResult: ...


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
        ReasonCode.OK,
        "No conditions in any() were true",
        operator="any",
    )


def eval_not(
    expr: NotExpr,
    snapshot: "RuntimeSnapshotView",
    evaluator: ExprEvaluatorProtocol,
) -> EvalResult:
    """
    Evaluate NotExpr (negation).

    Inverts the result of the child expression.
    """
    result = evaluator.evaluate(expr.child, snapshot)
    if result.reason != ReasonCode.OK:
        # Propagate errors unchanged
        return result
    # Invert the result
    return EvalResult.success(not result.ok, result.lhs_path, result.rhs_repr, "not")
