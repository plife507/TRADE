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

from .dsl_nodes import (
    Expr, Cond, AllExpr, AnyExpr, NotExpr,
    HoldsFor, OccurredWithin, CountTrue,
    FeatureRef, ScalarValue, RangeValue, ListValue, RhsValue,
    CROSSOVER_OPERATORS, DEFAULT_MAX_WINDOW_BARS,
)
from .types import EvalResult, ReasonCode, RefValue, ValueType
from .eval import (
    eval_gt, eval_lt, eval_ge, eval_le, eval_eq,
    eval_between, eval_near_abs, eval_near_pct, eval_in,
    eval_cross_above, eval_cross_below,
)

if TYPE_CHECKING:
    from ..runtime.snapshot import RuntimeSnapshotView


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
            return self._eval_cond(expr, snapshot)
        elif isinstance(expr, AllExpr):
            return self._eval_all(expr, snapshot)
        elif isinstance(expr, AnyExpr):
            return self._eval_any(expr, snapshot)
        elif isinstance(expr, NotExpr):
            return self._eval_not(expr, snapshot)
        elif isinstance(expr, HoldsFor):
            return self._eval_holds_for(expr, snapshot)
        elif isinstance(expr, OccurredWithin):
            return self._eval_occurred_within(expr, snapshot)
        elif isinstance(expr, CountTrue):
            return self._eval_count_true(expr, snapshot)
        else:
            return EvalResult.failure(
                ReasonCode.INTERNAL_ERROR,
                f"Unknown expression type: {type(expr).__name__}",
            )

    def _eval_all(self, expr: AllExpr, snapshot: "RuntimeSnapshotView") -> EvalResult:
        """
        Evaluate AllExpr (AND) with short-circuit.

        Returns False on first failing child.
        """
        for child in expr.children:
            result = self.evaluate(child, snapshot)
            if not result.ok:
                return result  # Short-circuit: first failure wins
        # All passed
        return EvalResult.success(True, "all", "", "all")

    def _eval_any(self, expr: AnyExpr, snapshot: "RuntimeSnapshotView") -> EvalResult:
        """
        Evaluate AnyExpr (OR) with short-circuit.

        Returns True on first passing child.
        """
        last_failure: EvalResult | None = None
        for child in expr.children:
            result = self.evaluate(child, snapshot)
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

    def _eval_not(self, expr: NotExpr, snapshot: "RuntimeSnapshotView") -> EvalResult:
        """
        Evaluate NotExpr (negation).

        Inverts the result of the child expression.
        """
        result = self.evaluate(expr.child, snapshot)
        if result.reason != ReasonCode.OK:
            # Propagate errors unchanged
            return result
        # Invert the result
        return EvalResult.success(not result.ok, result.lhs_path, result.rhs_repr, "not")

    def _eval_cond(self, cond: Cond, snapshot: "RuntimeSnapshotView") -> EvalResult:
        """
        Evaluate a single condition.

        Resolves LHS and RHS values and dispatches to appropriate operator.
        """
        # Resolve LHS
        lhs = self._resolve_ref(cond.lhs, snapshot)
        if lhs.is_missing:
            return EvalResult.failure(
                ReasonCode.MISSING_LHS,
                f"LHS value is missing: {cond.lhs.feature_id}",
                lhs_path=cond.lhs.feature_id,
                operator=cond.op,
            )

        # Handle crossover operators
        if cond.op in CROSSOVER_OPERATORS:
            return self._eval_crossover(cond, lhs, snapshot)

        # Resolve RHS based on type
        if isinstance(cond.rhs, ScalarValue):
            rhs = RefValue(
                value=cond.rhs.value,
                value_type=self._infer_value_type(cond.rhs.value),
                path="literal",
            )
        elif isinstance(cond.rhs, FeatureRef):
            rhs = self._resolve_ref(cond.rhs, snapshot)
            if rhs.is_missing:
                return EvalResult.failure(
                    ReasonCode.MISSING_RHS,
                    f"RHS value is missing: {cond.rhs.feature_id}",
                    lhs_path=cond.lhs.feature_id,
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
                lhs_path=cond.lhs.feature_id,
                operator=cond.op,
            )

        # Dispatch to operator
        return self._dispatch_operator(cond.op, lhs, rhs, cond.tolerance)

    def _eval_crossover(
        self,
        cond: Cond,
        lhs_curr: RefValue,
        snapshot: "RuntimeSnapshotView",
    ) -> EvalResult:
        """
        Evaluate crossover operator (cross_above, cross_below).

        Requires previous bar values for both LHS and RHS.
        """
        # Get previous LHS value
        lhs_prev_ref = cond.lhs.shifted(1)
        lhs_prev = self._resolve_ref(lhs_prev_ref, snapshot)
        if lhs_prev.is_missing:
            return EvalResult.failure(
                ReasonCode.MISSING_PREV_VALUE,
                f"Previous LHS value is missing: {cond.lhs.feature_id}",
                lhs_path=cond.lhs.feature_id,
                operator=cond.op,
            )

        # Resolve current RHS
        if isinstance(cond.rhs, ScalarValue):
            rhs_curr = RefValue(
                value=cond.rhs.value,
                value_type=self._infer_value_type(cond.rhs.value),
                path="literal",
            )
            rhs_prev = rhs_curr  # Literal is same for prev bar
        elif isinstance(cond.rhs, FeatureRef):
            rhs_curr = self._resolve_ref(cond.rhs, snapshot)
            if rhs_curr.is_missing:
                return EvalResult.failure(
                    ReasonCode.MISSING_RHS,
                    f"RHS value is missing: {cond.rhs.feature_id}",
                    lhs_path=cond.lhs.feature_id,
                    operator=cond.op,
                )
            # Get previous RHS value
            rhs_prev_ref = cond.rhs.shifted(1)
            rhs_prev = self._resolve_ref(rhs_prev_ref, snapshot)
            if rhs_prev.is_missing:
                return EvalResult.failure(
                    ReasonCode.MISSING_PREV_VALUE,
                    f"Previous RHS value is missing: {cond.rhs.feature_id}",
                    lhs_path=cond.lhs.feature_id,
                    operator=cond.op,
                )
        else:
            return EvalResult.failure(
                ReasonCode.INTERNAL_ERROR,
                f"Crossover requires scalar or feature reference RHS",
                lhs_path=cond.lhs.feature_id,
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
            cond.lhs.feature_id,
            str(rhs_curr.value),
            cond.op,
        )

    def _dispatch_operator(
        self,
        op: str,
        lhs: RefValue,
        rhs: RefValue,
        tolerance: float | None,
    ) -> EvalResult:
        """
        Dispatch to the appropriate operator function.

        Args:
            op: Operator name
            lhs: Resolved left-hand side
            rhs: Resolved right-hand side
            tolerance: For near_* operators

        Returns:
            EvalResult from operator
        """
        if op == "gt":
            return eval_gt(lhs, rhs)
        elif op == "lt":
            return eval_lt(lhs, rhs)
        elif op in ("ge", "gte"):
            return eval_ge(lhs, rhs)
        elif op in ("le", "lte"):
            return eval_le(lhs, rhs)
        elif op == "eq":
            return eval_eq(lhs, rhs)
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

    def _eval_holds_for(
        self, expr: HoldsFor, snapshot: "RuntimeSnapshotView"
    ) -> EvalResult:
        """
        Evaluate HoldsFor: expression must be true for N consecutive bars.

        Checks bars 0, 1, 2, ..., bars-1 (current to past).
        """
        for offset in range(expr.bars):
            shifted_expr = self._shift_expr(expr.expr, offset)
            result = self.evaluate(shifted_expr, snapshot)
            if not result.ok:
                return EvalResult.failure(
                    ReasonCode.OK,
                    f"HoldsFor failed at offset {offset}",
                    lhs_path=result.lhs_path,
                    operator="holds_for",
                )
        return EvalResult.success(True, "holds_for", str(expr.bars), "holds_for")

    def _eval_occurred_within(
        self, expr: OccurredWithin, snapshot: "RuntimeSnapshotView"
    ) -> EvalResult:
        """
        Evaluate OccurredWithin: expression was true at least once in last N bars.

        Checks bars 0, 1, 2, ..., bars-1 (current to past).
        """
        for offset in range(expr.bars):
            shifted_expr = self._shift_expr(expr.expr, offset)
            result = self.evaluate(shifted_expr, snapshot)
            if result.ok:
                return EvalResult.success(
                    True, "occurred_within", str(expr.bars), "occurred_within"
                )
        return EvalResult.failure(
            ReasonCode.OK,
            f"Expression did not occur within {expr.bars} bars",
            operator="occurred_within",
        )

    def _eval_count_true(
        self, expr: CountTrue, snapshot: "RuntimeSnapshotView"
    ) -> EvalResult:
        """
        Evaluate CountTrue: expression must be true at least N times in M bars.

        Counts true occurrences across bars 0, 1, 2, ..., bars-1.
        """
        count = 0
        for offset in range(expr.bars):
            shifted_expr = self._shift_expr(expr.expr, offset)
            result = self.evaluate(shifted_expr, snapshot)
            if result.ok:
                count += 1
                if count >= expr.min_true:
                    # Early exit once threshold met
                    return EvalResult.success(
                        True,
                        "count_true",
                        f"{count}/{expr.bars} >= {expr.min_true}",
                        "count_true",
                    )
        # Check final count
        if count >= expr.min_true:
            return EvalResult.success(
                True,
                "count_true",
                f"{count}/{expr.bars} >= {expr.min_true}",
                "count_true",
            )
        return EvalResult.failure(
            ReasonCode.OK,
            f"Expression was true {count} times, needed {expr.min_true}",
            operator="count_true",
        )

    def _shift_expr(self, expr: Expr, offset: int) -> Expr:
        """
        Create a new expression with all FeatureRefs shifted by offset.

        Used for window operator evaluation.
        """
        if offset == 0:
            return expr

        if isinstance(expr, Cond):
            new_lhs = expr.lhs.shifted(offset)
            if isinstance(expr.rhs, FeatureRef):
                new_rhs = expr.rhs.shifted(offset)
            else:
                new_rhs = expr.rhs
            return Cond(lhs=new_lhs, op=expr.op, rhs=new_rhs, tolerance=expr.tolerance)

        elif isinstance(expr, AllExpr):
            return AllExpr(tuple(self._shift_expr(c, offset) for c in expr.children))

        elif isinstance(expr, AnyExpr):
            return AnyExpr(tuple(self._shift_expr(c, offset) for c in expr.children))

        elif isinstance(expr, NotExpr):
            return NotExpr(self._shift_expr(expr.child, offset))

        elif isinstance(expr, HoldsFor):
            return HoldsFor(bars=expr.bars, expr=self._shift_expr(expr.expr, offset))

        elif isinstance(expr, OccurredWithin):
            return OccurredWithin(bars=expr.bars, expr=self._shift_expr(expr.expr, offset))

        elif isinstance(expr, CountTrue):
            return CountTrue(
                bars=expr.bars,
                min_true=expr.min_true,
                expr=self._shift_expr(expr.expr, offset),
            )

        else:
            return expr

    def _resolve_ref(
        self, ref: FeatureRef, snapshot: "RuntimeSnapshotView"
    ) -> RefValue:
        """
        Resolve a FeatureRef to a RefValue using the snapshot.

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
            return RefValue.from_resolved(value, f"{ref.feature_id}.{ref.field}")
        except (KeyError, AttributeError) as e:
            # Return missing value if lookup fails
            return RefValue.missing(f"{ref.feature_id}.{ref.field}")

    def _infer_value_type(self, value: Any) -> ValueType:
        """Infer ValueType from a Python value."""
        if value is None:
            return ValueType.MISSING
        if isinstance(value, bool):
            return ValueType.BOOL
        if isinstance(value, int):
            return ValueType.INT
        if isinstance(value, float):
            import math
            if math.isnan(value):
                return ValueType.MISSING
            return ValueType.FLOAT
        if isinstance(value, str):
            return ValueType.STRING
        return ValueType.UNKNOWN


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
