"""
Rule evaluation type definitions.

Enums and dataclasses for condition evaluation with strict typing.
"""

from dataclasses import dataclass
from enum import IntEnum, auto
from typing import Any

# Re-export FeatureOutputType from canonical location
from src.structures.types import FeatureOutputType


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

    # Condition failures (NOT an error - condition simply not met)
    CONDITION_FAILED = auto()  # Boolean condition not met (any(), etc.)
    WINDOW_CONDITION_FAILED = auto()  # Window operator condition not met (HoldsFor, OccurredWithin, etc.)

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
            # Check for NaN and infinity
            import math
            if math.isnan(value) or math.isinf(value):
                return cls.MISSING
            return cls.FLOAT
        if isinstance(value, str):
            return cls.STRING
        return cls.UNKNOWN


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
    def from_resolved_with_declared_type(
        cls,
        value: Any,
        path: str,
        declared_type: "FeatureOutputType | None",
    ) -> "RefValue":
        """
        Create RefValue with declared type consideration.

        If the registry declares a field as INT but the runtime value is
        an integer-like float (1.0, -1.0), treat it as INT. This handles
        pandas/numpy storing integer columns as float64.

        Args:
            value: The resolved value
            path: Path for error messages
            declared_type: FeatureOutputType from registry (or None)

        Returns:
            RefValue with appropriate type
        """
        import math

        # Get runtime type
        runtime_type = ValueType.from_value(value)

        # Check for INT coercion: declared INT + runtime FLOAT + value is integer-like
        if (
            declared_type is not None
            and declared_type == FeatureOutputType.INT
            and runtime_type == ValueType.FLOAT
            and isinstance(value, float)
            and not math.isnan(value)
            and not math.isinf(value)
            and value == int(value)  # e.g., 1.0, -1.0, 2.0
        ):
            # Coerce to INT
            return cls(
                value=int(value),
                value_type=ValueType.INT,
                path=path,
            )

        # Default: use runtime type
        return cls(
            value=value,
            value_type=runtime_type,
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


@dataclass
class CaseTrace:
    """Trace of a single case evaluation within a block."""
    case_index: int
    matched: bool
    cond_results: list[EvalResult]

    def summary(self) -> str:
        """One-line summary of condition results."""
        parts: list[str] = []
        for r in self.cond_results:
            lhs = r.lhs_path or "?"
            op = r.operator or "?"
            rhs = r.rhs_repr or "?"
            status = "PASS" if r.ok else "FAIL"
            parts.append(f"{lhs} {op} {rhs} = {status}")
        return ", ".join(parts)


@dataclass
class BlockTrace:
    """Trace of a single block evaluation."""
    block_id: str
    case_traces: list[CaseTrace]
    matched_case: int | None  # index of matched case, or None
    emitted_actions: list[str]


@dataclass
class EvaluationTrace:
    """Full trace of strategy block execution for verbose logging."""
    block_traces: list[BlockTrace]

    def format_lines(self) -> list[str]:
        """Format trace as human-readable log lines (no prefix — caller adds it)."""
        lines: list[str] = []
        for bt in self.block_traces:
            if bt.matched_case is not None:
                mc = bt.case_traces[bt.matched_case]
                actions = ", ".join(bt.emitted_actions)
                lines.append(
                    f"SIGNAL TRACE: {bt.block_id} case[{mc.case_index}]: "
                    f"{mc.summary()} -> {actions}"
                )
            else:
                if bt.case_traces:
                    fc = bt.case_traces[0]
                    fail_parts: list[str] = []
                    for i, r in enumerate(fc.cond_results):
                        if not r.ok:
                            lhs = r.lhs_path or "?"
                            op = r.operator or "?"
                            rhs = r.rhs_repr or "?"
                            fail_parts.append(f"cond[{i}]: {lhs} {op} {rhs} = FAIL")
                            break
                    fail_str = ", ".join(fail_parts) if fail_parts else "all conditions failed"
                    lines.append(
                        f"NO SIGNAL: {bt.block_id} case[0] FAILED at {fail_str}"
                    )
        return lines
