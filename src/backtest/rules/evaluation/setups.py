"""
Setup reference evaluation for DSL expressions.

Handles SetupRef with caching and circular reference detection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..dsl_nodes import Expr, SetupRef
from ..types import EvalResult, ReasonCode
from .protocols import ExprEvaluatorProtocol

if TYPE_CHECKING:
    from ...runtime.snapshot import RuntimeSnapshotView


def eval_setup_ref(
    expr: SetupRef,
    snapshot: "RuntimeSnapshotView",
    evaluator: ExprEvaluatorProtocol,
    setup_expr_cache: dict[str, Expr],
    setup_eval_stack: set[str],
) -> EvalResult:
    """
    Evaluate a SetupRef by loading and evaluating the setup's condition.

    The setup's condition expression is cached after first load.
    Includes recursion guard to detect circular references.

    Args:
        expr: SetupRef to evaluate
        snapshot: RuntimeSnapshotView providing values
        evaluator: ExprEvaluator for recursive evaluation
        setup_expr_cache: Cache for parsed setup expressions
        setup_eval_stack: Stack to detect circular references
    """
    setup_id = expr.setup_id

    # Recursion guard: detect circular setup references
    if setup_id in setup_eval_stack:
        return EvalResult.failure(
            ReasonCode.INTERNAL_ERROR,
            f"Circular setup reference detected: {setup_id}",
            operator="setup",
        )

    # Check cache first
    if setup_id not in setup_expr_cache:
        # SetupRef evaluation is not currently supported
        # The src.forge.setups module was removed during cleanup
        # TODO: Re-implement SetupRef if needed, or remove SetupRef from DSL
        return EvalResult.failure(
            ReasonCode.INTERNAL_ERROR,
            f"SetupRef evaluation not supported: '{setup_id}'. "
            "Define conditions inline in Play actions instead.",
            operator="setup",
        )

    # Evaluate the cached expression with recursion tracking
    cached_expr = setup_expr_cache[setup_id]
    setup_eval_stack.add(setup_id)
    try:
        result = evaluator.evaluate(cached_expr, snapshot)
    finally:
        setup_eval_stack.discard(setup_id)

    # Wrap the result to indicate it came from a setup
    if result.ok:
        return EvalResult.success(
            True,
            f"setup:{setup_id}",
            result.rhs_repr,
            "setup",
        )
    else:
        return EvalResult.failure(
            result.reason,
            f"Setup '{setup_id}' condition failed: {result.message}",
            lhs_path=f"setup:{setup_id}",
            operator="setup",
        )
