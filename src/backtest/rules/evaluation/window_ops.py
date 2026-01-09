"""
Window operators for DSL expressions.

Handles HoldsFor, OccurredWithin, CountTrue and their duration variants.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from ..dsl_nodes import (
    Expr,
    HoldsFor,
    OccurredWithin,
    CountTrue,
    HoldsForDuration,
    OccurredWithinDuration,
    CountTrueDuration,
    ACTION_TF_MINUTES,
)
from ...runtime.timeframe import tf_minutes
from ..types import EvalResult, ReasonCode
from .shift_ops import shift_expr

if TYPE_CHECKING:
    from ...runtime.snapshot import RuntimeSnapshotView


class ExprEvaluatorProtocol(Protocol):
    """Protocol for expression evaluator to avoid circular imports."""

    def evaluate(self, expr: Expr, snapshot: "RuntimeSnapshotView") -> EvalResult: ...


def eval_holds_for(
    expr: HoldsFor,
    snapshot: "RuntimeSnapshotView",
    evaluator: ExprEvaluatorProtocol,
) -> EvalResult:
    """
    Evaluate HoldsFor: expression must be true for N consecutive bars.

    Checks bars 0, 1, 2, ..., bars-1 (current to past).
    If anchor_tf is specified, offsets are scaled to anchor_tf granularity.
    """
    # Compute offset scale based on anchor_tf (default: 1m)
    offset_scale = 1
    if expr.anchor_tf:
        anchor_tf_mins = tf_minutes(expr.anchor_tf)
        offset_scale = anchor_tf_mins // ACTION_TF_MINUTES

    for i in range(expr.bars):
        # Scale offset to action TF (1m) bars
        offset = i * offset_scale
        shifted_expr = shift_expr(expr.expr, offset)
        result = evaluator.evaluate(shifted_expr, snapshot)
        if not result.ok:
            return EvalResult.failure(
                ReasonCode.OK,
                f"HoldsFor failed at offset {i} (1m offset={offset})",
                lhs_path=result.lhs_path,
                operator="holds_for",
            )
    return EvalResult.success(True, "holds_for", str(expr.bars), "holds_for")


def eval_occurred_within(
    expr: OccurredWithin,
    snapshot: "RuntimeSnapshotView",
    evaluator: ExprEvaluatorProtocol,
) -> EvalResult:
    """
    Evaluate OccurredWithin: expression was true at least once in last N bars.

    Checks bars 0, 1, 2, ..., bars-1 (current to past).
    If anchor_tf is specified, offsets are scaled to anchor_tf granularity.
    """
    # Compute offset scale based on anchor_tf (default: 1m)
    offset_scale = 1
    if expr.anchor_tf:
        anchor_tf_mins = tf_minutes(expr.anchor_tf)
        offset_scale = anchor_tf_mins // ACTION_TF_MINUTES

    for i in range(expr.bars):
        # Scale offset to action TF (1m) bars
        offset = i * offset_scale
        shifted_expr = shift_expr(expr.expr, offset)
        result = evaluator.evaluate(shifted_expr, snapshot)
        if result.ok:
            return EvalResult.success(
                True, "occurred_within", str(expr.bars), "occurred_within"
            )
    return EvalResult.failure(
        ReasonCode.OK,
        f"Expression did not occur within {expr.bars} bars",
        operator="occurred_within",
    )


def eval_count_true(
    expr: CountTrue,
    snapshot: "RuntimeSnapshotView",
    evaluator: ExprEvaluatorProtocol,
) -> EvalResult:
    """
    Evaluate CountTrue: expression must be true at least N times in M bars.

    Counts true occurrences across bars 0, 1, 2, ..., bars-1.
    If anchor_tf is specified, offsets are scaled to anchor_tf granularity.
    """
    # Compute offset scale based on anchor_tf (default: 1m)
    offset_scale = 1
    if expr.anchor_tf:
        anchor_tf_mins = tf_minutes(expr.anchor_tf)
        offset_scale = anchor_tf_mins // ACTION_TF_MINUTES

    count = 0
    for i in range(expr.bars):
        # Scale offset to action TF (1m) bars
        offset = i * offset_scale
        shifted_expr = shift_expr(expr.expr, offset)
        result = evaluator.evaluate(shifted_expr, snapshot)
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


def eval_holds_for_duration(
    expr: HoldsForDuration,
    snapshot: "RuntimeSnapshotView",
    evaluator: ExprEvaluatorProtocol,
) -> EvalResult:
    """
    Evaluate HoldsForDuration: expression must be true for specified duration.

    Converts duration to 1m bars and evaluates like HoldsFor.
    """
    bars = expr.to_bars(ACTION_TF_MINUTES)
    for offset in range(bars):
        shifted_expr = shift_expr(expr.expr, offset)
        result = evaluator.evaluate(shifted_expr, snapshot)
        if not result.ok:
            return EvalResult.failure(
                ReasonCode.OK,
                f"HoldsForDuration({expr.duration}) failed at offset {offset}",
                lhs_path=result.lhs_path,
                operator="holds_for_duration",
            )
    return EvalResult.success(
        True, "holds_for_duration", expr.duration, "holds_for_duration"
    )


def eval_occurred_within_duration(
    expr: OccurredWithinDuration,
    snapshot: "RuntimeSnapshotView",
    evaluator: ExprEvaluatorProtocol,
) -> EvalResult:
    """
    Evaluate OccurredWithinDuration: expression was true at least once in duration.

    Converts duration to 1m bars and evaluates like OccurredWithin.
    """
    bars = expr.to_bars(ACTION_TF_MINUTES)
    for offset in range(bars):
        shifted_expr = shift_expr(expr.expr, offset)
        result = evaluator.evaluate(shifted_expr, snapshot)
        if result.ok:
            return EvalResult.success(
                True,
                "occurred_within_duration",
                expr.duration,
                "occurred_within_duration",
            )
    return EvalResult.failure(
        ReasonCode.OK,
        f"Expression did not occur within {expr.duration}",
        operator="occurred_within_duration",
    )


def eval_count_true_duration(
    expr: CountTrueDuration,
    snapshot: "RuntimeSnapshotView",
    evaluator: ExprEvaluatorProtocol,
) -> EvalResult:
    """
    Evaluate CountTrueDuration: expression must be true at least N times in duration.

    Converts duration to 1m bars and evaluates like CountTrue.
    """
    bars = expr.to_bars(ACTION_TF_MINUTES)
    count = 0
    for offset in range(bars):
        shifted_expr = shift_expr(expr.expr, offset)
        result = evaluator.evaluate(shifted_expr, snapshot)
        if result.ok:
            count += 1
            if count >= expr.min_true:
                return EvalResult.success(
                    True,
                    "count_true_duration",
                    f"{count}/{expr.duration} >= {expr.min_true}",
                    "count_true_duration",
                )
    if count >= expr.min_true:
        return EvalResult.success(
            True,
            "count_true_duration",
            f"{count}/{expr.duration} >= {expr.min_true}",
            "count_true_duration",
        )
    return EvalResult.failure(
        ReasonCode.OK,
        f"Expression was true {count} times in {expr.duration}, needed {expr.min_true}",
        operator="count_true_duration",
    )
