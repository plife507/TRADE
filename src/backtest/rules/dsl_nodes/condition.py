"""
DSL Condition Node for Play Expression Language.

This module defines the Cond class for single comparisons.
"""

from __future__ import annotations

from dataclasses import dataclass

from .constants import VALID_OPERATORS
from .base import FeatureRef, RangeValue, ListValue, ArithmeticExpr, RhsValue


# =============================================================================
# Condition Node
# =============================================================================

@dataclass(frozen=True)
class Cond:
    """
    A single condition comparing LHS to RHS via an operator.

    Attributes:
        lhs: Left-hand side (FeatureRef or ArithmeticExpr)
        op: Operator string (from VALID_OPERATORS)
        rhs: Right-hand side (FeatureRef, ScalarValue, RangeValue, ListValue, or ArithmeticExpr)
        tolerance: Tolerance for near_abs/near_pct operators

    Examples:
        # RSI > 50
        Cond(
            lhs=FeatureRef(feature_id="rsi_14"),
            op="gt",
            rhs=ScalarValue(50.0)
        )

        # EMA fast > EMA slow
        Cond(
            lhs=FeatureRef(feature_id="ema_fast"),
            op="gt",
            rhs=FeatureRef(feature_id="ema_slow")
        )

        # RSI between 30 and 70
        Cond(
            lhs=FeatureRef(feature_id="rsi_14"),
            op="between",
            rhs=RangeValue(low=30.0, high=70.0)
        )

        # Price near 0.618 fib level (within 0.5%)
        Cond(
            lhs=FeatureRef(feature_id="mark_price"),
            op="near_pct",
            rhs=FeatureRef(feature_id="fib", field="level_0.618"),
            tolerance=0.005
        )

        # Arithmetic: ema_9 - ema_21 > 100
        Cond(
            lhs=ArithmeticExpr(
                left=FeatureRef(feature_id="ema_9"),
                op="-",
                right=FeatureRef(feature_id="ema_21"),
            ),
            op="gt",
            rhs=ScalarValue(100.0)
        )
    """
    lhs: FeatureRef | ArithmeticExpr
    op: str
    rhs: RhsValue
    tolerance: float | None = None

    def __post_init__(self):
        """Validate condition parameters."""
        if self.op not in VALID_OPERATORS:
            raise ValueError(
                f"Cond: unknown operator '{self.op}'. "
                f"Valid operators: {sorted(VALID_OPERATORS)}"
            )

        # Validate tolerance for near_* operators
        if self.op in ("near_abs", "near_pct"):
            if self.tolerance is None:
                raise ValueError(
                    f"Cond: operator '{self.op}' requires a tolerance value"
                )
            if self.tolerance < 0:
                raise ValueError(
                    f"Cond: tolerance must be >= 0, got {self.tolerance}"
                )

        # Validate RHS type for specific operators
        if self.op == "between" and not isinstance(self.rhs, RangeValue):
            raise ValueError(
                f"Cond: operator 'between' requires RangeValue, "
                f"got {type(self.rhs).__name__}"
            )

        if self.op == "in" and not isinstance(self.rhs, ListValue):
            raise ValueError(
                f"Cond: operator 'in' requires ListValue, "
                f"got {type(self.rhs).__name__}"
            )

    def __repr__(self) -> str:
        if self.tolerance is not None:
            return f"Cond({self.lhs} {self.op} {self.rhs}, tol={self.tolerance})"
        return f"Cond({self.lhs} {self.op} {self.rhs})"


__all__ = [
    "Cond",
]
