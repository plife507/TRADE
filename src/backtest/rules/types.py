"""
Rule evaluation type definitions.

Enums and dataclasses for condition evaluation with strict typing.
"""

from dataclasses import dataclass
from enum import IntEnum, auto
from typing import Any


class ReasonCode(IntEnum):
    """
    Reason codes for condition evaluation outcomes.

    Every evaluation returns a ReasonCode to explain why it succeeded or failed.
    These are machine-readable for logging/debugging.
    """

    # Success
    OK = 0  # Condition evaluated successfully to true/false

    # Missing data
    MISSING_VALUE = auto()  # Referenced value is None/NaN
    MISSING_LHS = auto()  # Left-hand side reference not found
    MISSING_RHS = auto()  # Right-hand side reference not found
    MISSING_PREV_VALUE = auto()  # Previous bar value needed but unavailable (crossover)

    # Type errors
    TYPE_MISMATCH = auto()  # LHS/RHS types incompatible for operator
    FLOAT_EQUALITY = auto()  # Attempted float == without approx_eq

    # Operator errors
    UNKNOWN_OPERATOR = auto()  # Operator not recognized
    UNSUPPORTED_OPERATOR = auto()  # Operator known but not supported (Stage 4c)
    INVALID_TOLERANCE = auto()  # approx_eq missing/invalid tolerance

    # Path errors
    INVALID_PATH = auto()  # Path syntax invalid
    UNKNOWN_NAMESPACE = auto()  # Path namespace not recognized
    UNKNOWN_FIELD = auto()  # Field not found in namespace

    # Internal
    INTERNAL_ERROR = auto()  # Unexpected internal error


class ValueType(IntEnum):
    """
    Value types for type checking in operators.

    Used to enforce operator type contracts:
    - Numeric comparisons (gt, lt, ge, le) require NUMERIC
    - Equality (eq) requires BOOL, INT, or ENUM (not FLOAT)
    - Float equality requires approx_eq with tolerance
    """

    UNKNOWN = 0
    NUMERIC = auto()  # int or float (for gt, lt, ge, le, approx_eq)
    INT = auto()  # int only (for eq)
    FLOAT = auto()  # float only (for approx_eq, NOT eq)
    BOOL = auto()  # bool only (for eq)
    ENUM = auto()  # enum token (normalized to int, for eq)
    STRING = auto()  # string (not allowed in numeric ops)
    MISSING = auto()  # None or NaN

    @classmethod
    def from_value(cls, value: Any) -> "ValueType":
        """
        Determine ValueType from a Python value.

        Args:
            value: Any Python value

        Returns:
            Appropriate ValueType enum
        """
        if value is None:
            return cls.MISSING
        if isinstance(value, bool):
            return cls.BOOL
        if isinstance(value, int):
            return cls.INT
        if isinstance(value, float):
            # Check for NaN
            import math
            if math.isnan(value):
                return cls.MISSING
            return cls.FLOAT
        if isinstance(value, str):
            return cls.STRING
        return cls.UNKNOWN


class FeatureOutputType(IntEnum):
    """
    Compile-time output type declarations for feature fields.

    Used to validate operator compatibility at Play load time:
    - FLOAT: Numeric, but eq requires near_abs/near_pct (no exact equality)
    - INT: Discrete integer, eq/in allowed
    - BOOL: Boolean, eq allowed
    - ENUM: String enum token (e.g., "UP", "DOWN"), eq/in allowed

    Examples:
        - rsi.value → FLOAT
        - trend.direction → INT (1, -1, 0)
        - zone.state → ENUM ("active", "broken", "none")
        - swing.high_idx → INT
    """

    FLOAT = auto()   # Numeric float (use near_* for equality)
    INT = auto()     # Discrete integer (eq/in allowed)
    BOOL = auto()    # Boolean (eq allowed)
    ENUM = auto()    # String enum token (eq/in allowed)

    def is_numeric(self) -> bool:
        """Check if type supports numeric operators (gt, lt, between, near_*)."""
        return self in (FeatureOutputType.FLOAT, FeatureOutputType.INT)

    def is_discrete(self) -> bool:
        """Check if type supports discrete operators (eq, in)."""
        return self in (FeatureOutputType.INT, FeatureOutputType.BOOL, FeatureOutputType.ENUM)

    def allows_eq(self) -> bool:
        """Check if type allows exact equality (eq operator)."""
        # FLOAT disallowed - must use near_abs or near_pct
        return self.is_discrete()

    def allows_near(self) -> bool:
        """Check if type allows near_abs/near_pct operators."""
        return self.is_numeric()


@dataclass(frozen=True)
class RefValue:
    """
    A resolved reference value with type information.

    Wraps the raw value with its type for operator validation.
    """

    value: Any  # The actual value (int, float, bool, None)
    value_type: ValueType  # Type classification
    path: str  # Original path for error messages

    @property
    def is_missing(self) -> bool:
        """Check if value is missing (None or NaN)."""
        return self.value_type == ValueType.MISSING

    @property
    def is_numeric(self) -> bool:
        """Check if value is numeric (int or float)."""
        return self.value_type in (ValueType.INT, ValueType.FLOAT, ValueType.NUMERIC)

    @classmethod
    def from_resolved(cls, value: Any, path: str) -> "RefValue":
        """Create RefValue from a resolved value."""
        return cls(
            value=value,
            value_type=ValueType.from_value(value),
            path=path,
        )

    @classmethod
    def missing(cls, path: str) -> "RefValue":
        """Create a missing RefValue."""
        return cls(
            value=None,
            value_type=ValueType.MISSING,
            path=path,
        )


@dataclass(frozen=True)
class EvalResult:
    """
    Result of a condition evaluation.

    Contains:
    - ok: Whether condition evaluated to true
    - reason: Why it evaluated this way
    - debug: Structured debug info for logging
    """

    ok: bool  # True if condition is satisfied
    reason: ReasonCode  # Reason code explaining outcome
    lhs_path: str | None = None  # Left-hand side path
    rhs_repr: str | None = None  # Right-hand side representation
    operator: str | None = None  # Operator used
    message: str | None = None  # Human-readable explanation

    @classmethod
    def success(
        cls,
        ok: bool,
        lhs_path: str,
        rhs_repr: str,
        operator: str,
    ) -> "EvalResult":
        """Create a successful evaluation result."""
        return cls(
            ok=ok,
            reason=ReasonCode.OK,
            lhs_path=lhs_path,
            rhs_repr=rhs_repr,
            operator=operator,
        )

    @classmethod
    def failure(
        cls,
        reason: ReasonCode,
        message: str,
        lhs_path: str | None = None,
        rhs_repr: str | None = None,
        operator: str | None = None,
    ) -> "EvalResult":
        """Create a failure result (condition not met or error)."""
        return cls(
            ok=False,
            reason=reason,
            lhs_path=lhs_path,
            rhs_repr=rhs_repr,
            operator=operator,
            message=message,
        )

    def to_dict(self) -> dict:
        """Convert to dict for logging/serialization."""
        return {
            "ok": self.ok,
            "reason": self.reason.name,
            "lhs_path": self.lhs_path,
            "rhs_repr": self.rhs_repr,
            "operator": self.operator,
            "message": self.message,
        }
