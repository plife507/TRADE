"""
DSL Expression Evaluator for Play vNext.

Evaluates AST expression trees against a RuntimeSnapshotView.
Supports nested boolean logic, window operators, and type-safe operators.

Key Features:
- Short-circuit evaluation for AllExpr/AnyExpr
- Window operators (HoldsFor, OccurredWithin, CountTrue)
- Offset handling for bar lookback
- Type-safe operator dispatch

Usage:
    evaluator = ExprEvaluator()
    result = evaluator.evaluate(expr, snapshot)
    # result is EvalResult with ok=True/False and reason code
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..dsl_nodes import (
    Expr,
    Cond,
    AllExpr,
    AnyExpr,
    NotExpr,
    HoldsFor,
    OccurredWithin,
    CountTrue,
    SetupRef,
    HoldsForDuration,
    OccurredWithinDuration,
    CountTrueDuration,
    FeatureRef,
    DEFAULT_MAX_WINDOW_BARS,
)
from ..types import EvalResult, ReasonCode

from .boolean_ops import eval_all, eval_any, eval_not
from .condition_ops import eval_cond
from .window_ops import (
    eval_holds_for,
    eval_occurred_within,
    eval_count_true,
    eval_holds_for_duration,
    eval_occurred_within_duration,
    eval_count_true_duration,
)
from .setups import eval_setup_ref
from .resolve import resolve_ref

if TYPE_CHECKING:
    from ...runtime.snapshot_view import RuntimeSnapshotView


class ExprEvaluator:
    """
    Evaluates DSL expression trees against a snapshot.

    Thread-safe and stateless - can be reused across evaluations.

    Attributes:
        max_window_bars: Maximum bars for window operators (default 100)

    Example:
        evaluator = ExprEvaluator(max_window_bars=100)

        # Simple condition
        cond = Cond(
            lhs=FeatureRef(feature_id="rsi_14"),
            op="gt",
            rhs=ScalarValue(50.0)
        )
        result = evaluator.evaluate(cond, snapshot)

        # Nested expression
        expr = AllExpr((cond1, AnyExpr((cond2, cond3))))
        result = evaluator.evaluate(expr, snapshot)
    """

    def __init__(self, max_window_bars: int = DEFAULT_MAX_WINDOW_BARS):
        """
        Initialize evaluator.

        Args:
            max_window_bars: Maximum bars for window operators.
        """
        self._max_window = max_window_bars
        # Cache for parsed setup expressions: setup_id -> Expr
        self._setup_expr_cache: dict[str, Expr] = {}
        # Stack to detect circular setup references (for recursion guard)
        self._setup_eval_stack: set[str] = set()

    def evaluate(self, expr: Expr, snapshot: "RuntimeSnapshotView") -> EvalResult:
        """
        Evaluate an expression tree against a snapshot.

        Args:
            expr: The expression to evaluate.
            snapshot: RuntimeSnapshotView providing feature values.

        Returns:
            EvalResult with ok=True/False and reason code.
        """
        if isinstance(expr, Cond):
            return eval_cond(expr, snapshot)
        elif isinstance(expr, AllExpr):
            return eval_all(expr, snapshot, self)
        elif isinstance(expr, AnyExpr):
            return eval_any(expr, snapshot, self)
        elif isinstance(expr, NotExpr):
            return eval_not(expr, snapshot, self)
        elif isinstance(expr, HoldsFor):
            return eval_holds_for(expr, snapshot, self)
        elif isinstance(expr, OccurredWithin):
            return eval_occurred_within(expr, snapshot, self)
        elif isinstance(expr, CountTrue):
            return eval_count_true(expr, snapshot, self)
        elif isinstance(expr, HoldsForDuration):
            return eval_holds_for_duration(expr, snapshot, self)
        elif isinstance(expr, OccurredWithinDuration):
            return eval_occurred_within_duration(expr, snapshot, self)
        elif isinstance(expr, CountTrueDuration):
            return eval_count_true_duration(expr, snapshot, self)
        elif isinstance(expr, SetupRef):
            return eval_setup_ref(
                expr,
                snapshot,
                self,
                self._setup_expr_cache,
                self._setup_eval_stack,
            )
        else:
            return EvalResult.failure(
                ReasonCode.INTERNAL_ERROR,
                f"Unknown expression type: {type(expr).__name__}",
            )

    def resolve_metadata(
        self,
        metadata: dict[str, Any],
        snapshot: "RuntimeSnapshotView",
    ) -> dict[str, Any]:
        """
        Resolve feature references in metadata to actual values.

        Allows dynamic metadata like:
            metadata:
              price: {feature_id: "swing", field: "low_level"}

        which resolves to:
            metadata:
              price: 45000.0  # actual swing low value

        FAIL LOUD: Raises ValueError if any feature reference cannot be resolved.
        No fallbacks, no None defaults.

        Args:
            metadata: Dict with potential feature references
            snapshot: RuntimeSnapshotView providing values

        Returns:
            Dict with all feature references resolved to values

        Raises:
            ValueError: If any feature reference cannot be resolved
        """
        if not metadata:
            return {}

        resolved: dict[str, Any] = {}
        for key, value in metadata.items():
            if isinstance(value, dict) and "feature_id" in value:
                # It's a feature reference - resolve it
                ref = FeatureRef(
                    feature_id=value["feature_id"],
                    field=value.get("field", "value"),
                    offset=value.get("offset", 0),
                )
                ref_value = resolve_ref(ref, snapshot)
                if ref_value.is_missing:
                    raise ValueError(
                        f"Dynamic metadata '{key}' references missing feature: "
                        f"{ref.feature_id}.{ref.field}"
                    )
                resolved[key] = ref_value.value
            else:
                # Pass through non-reference values
                resolved[key] = value
        return resolved


def evaluate_expression(
    expr: Expr,
    snapshot: "RuntimeSnapshotView",
    max_window_bars: int = DEFAULT_MAX_WINDOW_BARS,
) -> EvalResult:
    """
    Convenience function to evaluate an expression.

    Args:
        expr: The expression to evaluate.
        snapshot: RuntimeSnapshotView providing feature values.
        max_window_bars: Maximum bars for window operators.

    Returns:
        EvalResult with evaluation outcome.
    """
    evaluator = ExprEvaluator(max_window_bars=max_window_bars)
    return evaluator.evaluate(expr, snapshot)
