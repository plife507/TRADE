"""
Expression shifting for window operators.

Handles shifting FeatureRefs by offset for historical lookback.
"""

from __future__ import annotations

from ..dsl_nodes import (
    Expr,
    Cond,
    AllExpr,
    AnyExpr,
    NotExpr,
    HoldsFor,
    OccurredWithin,
    CountTrue,
    HoldsForDuration,
    OccurredWithinDuration,
    CountTrueDuration,
    SetupRef,
    FeatureRef,
    ArithmeticExpr,
)


def shift_arithmetic(arith: ArithmeticExpr, offset: int) -> ArithmeticExpr:
    """
    Shift all FeatureRefs in an ArithmeticExpr by offset.
    """
    # Shift left operand
    if isinstance(arith.left, FeatureRef):
        new_left = arith.left.shifted(offset)
    elif isinstance(arith.left, ArithmeticExpr):
        new_left = shift_arithmetic(arith.left, offset)
    else:
        new_left = arith.left  # ScalarValue doesn't shift

    # Shift right operand
    if isinstance(arith.right, FeatureRef):
        new_right = arith.right.shifted(offset)
    elif isinstance(arith.right, ArithmeticExpr):
        new_right = shift_arithmetic(arith.right, offset)
    else:
        new_right = arith.right  # ScalarValue doesn't shift

    return ArithmeticExpr(left=new_left, op=arith.op, right=new_right)


def shift_expr(expr: Expr, offset: int) -> Expr:
    """
    Create a new expression with all FeatureRefs shifted by offset.

    Used for window operator evaluation.
    """
    if offset == 0:
        return expr

    if isinstance(expr, Cond):
        # Shift LHS (FeatureRef or ArithmeticExpr)
        if isinstance(expr.lhs, FeatureRef):
            new_lhs = expr.lhs.shifted(offset)
        elif isinstance(expr.lhs, ArithmeticExpr):
            new_lhs = shift_arithmetic(expr.lhs, offset)
        else:
            new_lhs = expr.lhs

        # Shift RHS (FeatureRef or ArithmeticExpr)
        if isinstance(expr.rhs, FeatureRef):
            new_rhs = expr.rhs.shifted(offset)
        elif isinstance(expr.rhs, ArithmeticExpr):
            new_rhs = shift_arithmetic(expr.rhs, offset)
        else:
            new_rhs = expr.rhs

        return Cond(lhs=new_lhs, op=expr.op, rhs=new_rhs, tolerance=expr.tolerance)

    elif isinstance(expr, AllExpr):
        return AllExpr(tuple(shift_expr(c, offset) for c in expr.children))

    elif isinstance(expr, AnyExpr):
        return AnyExpr(tuple(shift_expr(c, offset) for c in expr.children))

    elif isinstance(expr, NotExpr):
        return NotExpr(shift_expr(expr.child, offset))

    elif isinstance(expr, HoldsFor):
        return HoldsFor(
            bars=expr.bars,
            expr=shift_expr(expr.expr, offset),
            anchor_tf=expr.anchor_tf,
        )

    elif isinstance(expr, OccurredWithin):
        return OccurredWithin(
            bars=expr.bars,
            expr=shift_expr(expr.expr, offset),
            anchor_tf=expr.anchor_tf,
        )

    elif isinstance(expr, CountTrue):
        return CountTrue(
            bars=expr.bars,
            min_true=expr.min_true,
            expr=shift_expr(expr.expr, offset),
            anchor_tf=expr.anchor_tf,
        )

    elif isinstance(expr, HoldsForDuration):
        return HoldsForDuration(
            duration=expr.duration,
            expr=shift_expr(expr.expr, offset),
        )

    elif isinstance(expr, OccurredWithinDuration):
        return OccurredWithinDuration(
            duration=expr.duration,
            expr=shift_expr(expr.expr, offset),
        )

    elif isinstance(expr, CountTrueDuration):
        return CountTrueDuration(
            duration=expr.duration,
            min_true=expr.min_true,
            expr=shift_expr(expr.expr, offset),
        )

    elif isinstance(expr, SetupRef):
        # SetupRef cannot be shifted - the setup's condition will be
        # evaluated as-is. This may need revision if setups should
        # support historical lookback.
        return expr

    else:
        return expr
