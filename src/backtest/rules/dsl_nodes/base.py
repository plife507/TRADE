"""
DSL Base Node Types for Play Expression Language.

This module defines the foundational AST node types:
- FeatureRef: Reference to a feature field
- ScalarValue: Literal scalar value
- RangeValue: Range for 'between' operator
- ListValue: List for 'in' operator
- ArithmeticExpr: Inline arithmetic expressions
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from .constants import ARITHMETIC_OPERATORS


# =============================================================================
# Value Nodes
# =============================================================================

@dataclass(frozen=True)
class FeatureRef:
    """
    A reference to a feature field at a specific bar offset.

    Attributes:
        feature_id: The feature ID to reference (e.g., "ema_fast", "swing_1h")
        field: The field name for multi-output features (default: "value")
        offset: Bar offset (0=current, 1=previous, etc.)

    Examples:
        FeatureRef(feature_id="rsi_14")              # Current RSI value
        FeatureRef(feature_id="rsi_14", offset=1)    # Previous bar RSI
        FeatureRef(feature_id="macd_1h", field="signal")  # MACD signal line
        FeatureRef(feature_id="swing_1h", field="high_level")  # Swing high
    """
    feature_id: str
    field: str = "value"
    offset: int = 0

    def __post_init__(self):
        """Validate FeatureRef parameters."""
        if not self.feature_id:
            raise ValueError("FeatureRef: feature_id is required")
        if self.offset < 0:
            raise ValueError(
                f"FeatureRef: offset must be >= 0, got {self.offset}"
            )

    def shifted(self, additional_offset: int) -> "FeatureRef":
        """Return a new FeatureRef with additional offset."""
        return FeatureRef(
            feature_id=self.feature_id,
            field=self.field,
            offset=self.offset + additional_offset
        )

    def __repr__(self) -> str:
        if self.offset == 0 and self.field == "value":
            return f"Ref({self.feature_id!r})"
        elif self.offset == 0:
            return f"Ref({self.feature_id!r}, field={self.field!r})"
        elif self.field == "value":
            return f"Ref({self.feature_id!r}, offset={self.offset})"
        else:
            return f"Ref({self.feature_id!r}, field={self.field!r}, offset={self.offset})"


@dataclass(frozen=True)
class ScalarValue:
    """
    A literal scalar value (number, bool, or string).

    Attributes:
        value: The literal value (int, float, bool, or str)

    Examples:
        ScalarValue(50.0)    # Float threshold
        ScalarValue(1)       # Integer (trend direction)
        ScalarValue(True)    # Boolean
        ScalarValue("UP")    # Enum token
    """
    value: int | float | bool | str

    def __repr__(self) -> str:
        return f"Scalar({self.value!r})"


@dataclass(frozen=True)
class RangeValue:
    """
    A range value for the 'between' operator.

    Attributes:
        low: Lower bound (inclusive)
        high: Upper bound (inclusive)

    Semantics: low <= value <= high

    Examples:
        RangeValue(low=30.0, high=70.0)  # RSI neutral zone
        RangeValue(low=0.3, high=0.7)    # Fibonacci range
    """
    low: float
    high: float

    def __post_init__(self):
        """Validate range bounds."""
        if self.low > self.high:
            raise ValueError(
                f"RangeValue: low ({self.low}) must be <= high ({self.high})"
            )

    def __repr__(self) -> str:
        return f"Range({self.low}, {self.high})"


@dataclass(frozen=True)
class ListValue:
    """
    A list of values for the 'in' operator.

    Attributes:
        values: Tuple of allowed values (frozen for immutability)

    Examples:
        ListValue((1, -1))           # Trend direction: up or down
        ListValue(("active", "pending"))  # Zone states
    """
    values: tuple[int | float | bool | str, ...]

    def __post_init__(self):
        """Validate list is not empty."""
        if not self.values:
            raise ValueError("ListValue: values cannot be empty")

    def __repr__(self) -> str:
        return f"List({list(self.values)})"


# =============================================================================
# Arithmetic Expression Node
# =============================================================================

@dataclass(frozen=True)
class ArithmeticExpr:
    """
    An arithmetic expression for inline computations.

    Supports binary operations between two operands:
    - Two features: ema_9 - ema_21
    - Feature and scalar: rsi_14 - 50
    - Nested arithmetic: (ema_9 - ema_21) / atr_14

    Attributes:
        left: Left operand (FeatureRef, ScalarValue, or nested ArithmeticExpr)
        op: Arithmetic operator (+, -, *, /, %)
        right: Right operand (FeatureRef, ScalarValue, or nested ArithmeticExpr)

    Semantics:
        - Division by zero returns None (triggers MISSING_LHS/RHS)
        - Type coercion: INT op FLOAT -> FLOAT
        - Division always -> FLOAT

    YAML Syntax:
        # Basic: ema_9 - ema_21
        lhs: ["ema_9", "-", "ema_21"]

        # Nested: (ema_9 - ema_21) / atr_14
        lhs: [["ema_9", "-", "ema_21"], "/", "atr_14"]

        # Feature and scalar: close - 100
        lhs: ["close", "-", 100]

    Examples:
        # ema_9 - ema_21 > 100
        ArithmeticExpr(
            left=FeatureRef(feature_id="ema_9"),
            op="-",
            right=FeatureRef(feature_id="ema_21"),
        )

        # Nested: (ema_9 - ema_21) / atr_14
        ArithmeticExpr(
            left=ArithmeticExpr(
                left=FeatureRef(feature_id="ema_9"),
                op="-",
                right=FeatureRef(feature_id="ema_21"),
            ),
            op="/",
            right=FeatureRef(feature_id="atr_14"),
        )
    """
    left: "FeatureRef | ScalarValue | ArithmeticExpr"
    op: str
    right: "FeatureRef | ScalarValue | ArithmeticExpr"

    def __post_init__(self):
        """Validate arithmetic expression."""
        if self.op not in ARITHMETIC_OPERATORS:
            raise ValueError(
                f"ArithmeticExpr: unknown operator '{self.op}'. "
                f"Valid operators: {sorted(ARITHMETIC_OPERATORS)}"
            )

    def __repr__(self) -> str:
        return f"Arith({self.left!r} {self.op} {self.right!r})"


# Arithmetic operand type (for recursive definitions)
ArithmeticOperand = FeatureRef | ScalarValue | ArithmeticExpr


# RHS type for conditions (now includes ArithmeticExpr)
RhsValue = Union[FeatureRef, ScalarValue, RangeValue, ListValue, ArithmeticExpr]


__all__ = [
    "FeatureRef",
    "ScalarValue",
    "RangeValue",
    "ListValue",
    "ArithmeticExpr",
    "ArithmeticOperand",
    "RhsValue",
]
