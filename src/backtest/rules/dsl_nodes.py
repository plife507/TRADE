"""
DSL AST Node Types for Play Expression Language.

This module defines the abstract syntax tree (AST) node types for the
vNext Play condition language. Nodes are frozen dataclasses for
immutability and hashability.

Node Categories:
- Value nodes: FeatureRef, ScalarValue, RangeValue
- Condition nodes: Cond
- Boolean expression nodes: AllExpr, AnyExpr, NotExpr
- Window operator nodes: HoldsFor, OccurredWithin, CountTrue

Type Hierarchy:
    Expr = AllExpr | AnyExpr | NotExpr | Cond | HoldsFor | OccurredWithin | CountTrue

Usage:
    # Simple condition: RSI > 50
    cond = Cond(
        lhs=FeatureRef(feature_id="rsi_14"),
        op="gt",
        rhs=ScalarValue(50.0)
    )

    # Nested expression: RSI > 50 AND (EMA fast > EMA slow OR trend up)
    expr = AllExpr((
        Cond(
            lhs=FeatureRef(feature_id="rsi_14"),
            op="gt",
            rhs=ScalarValue(50.0)
        ),
        AnyExpr((
            Cond(
                lhs=FeatureRef(feature_id="ema_fast"),
                op="gt",
                rhs=FeatureRef(feature_id="ema_slow")
            ),
            Cond(
                lhs=FeatureRef(feature_id="trend_1h", field="direction"),
                op="eq",
                rhs=ScalarValue(1)
            )
        ))
    ))
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from collections.abc import Callable
    from .types import FeatureOutputType

# =============================================================================
# Valid Operators
# =============================================================================
# All operators supported by the DSL expression evaluator.

COMPARISON_OPERATORS = frozenset({
    "gt",           # Greater than: lhs > rhs
    "gte",          # Greater than or equal: lhs >= rhs
    "lt",           # Less than: lhs < rhs
    "lte",          # Less than or equal: lhs <= rhs
    "eq",           # Equal (discrete types only): lhs == rhs
    "between",      # Range: low <= lhs <= high
    "near_abs",     # Near absolute: |lhs - rhs| <= tolerance
    "near_pct",     # Near percent: |lhs - rhs| / |rhs| <= tolerance
    "in",           # In set: lhs in [values]
})

CROSSOVER_OPERATORS = frozenset({
    "cross_above",  # Cross above: prev_lhs <= prev_rhs AND curr_lhs > curr_rhs
    "cross_below",  # Cross below: prev_lhs >= prev_rhs AND curr_lhs < curr_rhs
})

VALID_OPERATORS = COMPARISON_OPERATORS | CROSSOVER_OPERATORS

# Operators that require numeric types
NUMERIC_OPERATORS = frozenset({
    "gt", "gte", "lt", "lte", "between", "near_abs", "near_pct",
    "cross_above", "cross_below"
})

# Operators that require discrete types (INT, BOOL, ENUM)
DISCRETE_OPERATORS = frozenset({
    "eq", "in"
})

# Window operator limits
DEFAULT_MAX_WINDOW_BARS = 100
WINDOW_BARS_CEILING = 500


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


# RHS type for conditions
RhsValue = Union[FeatureRef, ScalarValue, RangeValue, ListValue]


# =============================================================================
# Condition Node
# =============================================================================

@dataclass(frozen=True)
class Cond:
    """
    A single condition comparing LHS to RHS via an operator.

    Attributes:
        lhs: Left-hand side (always a FeatureRef)
        op: Operator string (from VALID_OPERATORS)
        rhs: Right-hand side (FeatureRef, ScalarValue, RangeValue, or ListValue)
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
    """
    lhs: FeatureRef
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


# =============================================================================
# Boolean Expression Nodes
# =============================================================================

@dataclass(frozen=True)
class AllExpr:
    """
    AND expression: All children must be true.

    Short-circuit evaluation: First false result stops evaluation.

    Attributes:
        children: Tuple of child expressions (at least 2)

    Examples:
        AllExpr((cond1, cond2, cond3))  # cond1 AND cond2 AND cond3
    """
    children: tuple["Expr", ...]

    def __post_init__(self):
        """Validate children."""
        if len(self.children) < 1:
            raise ValueError("AllExpr: requires at least 1 child expression")

    def __repr__(self) -> str:
        if len(self.children) == 1:
            return repr(self.children[0])
        children_str = ", ".join(repr(c) for c in self.children)
        return f"All({children_str})"


@dataclass(frozen=True)
class AnyExpr:
    """
    OR expression: Any child must be true.

    Short-circuit evaluation: First true result stops evaluation.

    Attributes:
        children: Tuple of child expressions (at least 2)

    Examples:
        AnyExpr((cond1, cond2))  # cond1 OR cond2
    """
    children: tuple["Expr", ...]

    def __post_init__(self):
        """Validate children."""
        if len(self.children) < 1:
            raise ValueError("AnyExpr: requires at least 1 child expression")

    def __repr__(self) -> str:
        if len(self.children) == 1:
            return repr(self.children[0])
        children_str = ", ".join(repr(c) for c in self.children)
        return f"Any({children_str})"


@dataclass(frozen=True)
class NotExpr:
    """
    NOT expression: Negates the child expression.

    Attributes:
        child: The expression to negate

    Examples:
        NotExpr(cond)  # NOT cond
    """
    child: "Expr"

    def __repr__(self) -> str:
        return f"Not({self.child!r})"


# =============================================================================
# Window Operator Nodes (Series Only)
# =============================================================================

@dataclass(frozen=True)
class HoldsFor:
    """
    Window operator: Expression must be true for N consecutive bars.

    Checks that expr was true at offset 0, 1, 2, ..., bars-1.

    Attributes:
        bars: Number of consecutive bars (must be > 0, <= ceiling)
        expr: The expression to check

    Examples:
        # RSI > 50 for last 5 bars
        HoldsFor(
            bars=5,
            expr=Cond(
                lhs=FeatureRef(feature_id="rsi_14"),
                op="gt",
                rhs=ScalarValue(50.0)
            )
        )
    """
    bars: int
    expr: "Expr"

    def __post_init__(self):
        """Validate bars parameter."""
        if self.bars < 1:
            raise ValueError(f"HoldsFor: bars must be >= 1, got {self.bars}")
        if self.bars > WINDOW_BARS_CEILING:
            raise ValueError(
                f"HoldsFor: bars must be <= {WINDOW_BARS_CEILING}, got {self.bars}"
            )

    def __repr__(self) -> str:
        return f"HoldsFor({self.bars}, {self.expr!r})"


@dataclass(frozen=True)
class OccurredWithin:
    """
    Window operator: Expression was true at least once in last N bars.

    Checks offsets 0, 1, 2, ..., bars-1 for at least one true.

    Attributes:
        bars: Window size (must be > 0, <= ceiling)
        expr: The expression to check

    Examples:
        # EMA crossover occurred in last 3 bars
        OccurredWithin(
            bars=3,
            expr=Cond(
                lhs=FeatureRef(feature_id="ema_fast"),
                op="cross_above",
                rhs=FeatureRef(feature_id="ema_slow")
            )
        )
    """
    bars: int
    expr: "Expr"

    def __post_init__(self):
        """Validate bars parameter."""
        if self.bars < 1:
            raise ValueError(
                f"OccurredWithin: bars must be >= 1, got {self.bars}"
            )
        if self.bars > WINDOW_BARS_CEILING:
            raise ValueError(
                f"OccurredWithin: bars must be <= {WINDOW_BARS_CEILING}, "
                f"got {self.bars}"
            )

    def __repr__(self) -> str:
        return f"OccurredWithin({self.bars}, {self.expr!r})"


@dataclass(frozen=True)
class CountTrue:
    """
    Window operator: Expression must be true at least N times in last M bars.

    Counts how many times expr was true across offsets 0..bars-1.

    Attributes:
        bars: Window size (must be > 0, <= ceiling)
        min_true: Minimum true count required
        expr: The expression to check

    Examples:
        # RSI was overbought at least 3 times in last 10 bars
        CountTrue(
            bars=10,
            min_true=3,
            expr=Cond(
                lhs=FeatureRef(feature_id="rsi_14"),
                op="gt",
                rhs=ScalarValue(70.0)
            )
        )
    """
    bars: int
    min_true: int
    expr: "Expr"

    def __post_init__(self):
        """Validate parameters."""
        if self.bars < 1:
            raise ValueError(f"CountTrue: bars must be >= 1, got {self.bars}")
        if self.bars > WINDOW_BARS_CEILING:
            raise ValueError(
                f"CountTrue: bars must be <= {WINDOW_BARS_CEILING}, "
                f"got {self.bars}"
            )
        if self.min_true < 1:
            raise ValueError(
                f"CountTrue: min_true must be >= 1, got {self.min_true}"
            )
        if self.min_true > self.bars:
            raise ValueError(
                f"CountTrue: min_true ({self.min_true}) cannot exceed "
                f"bars ({self.bars})"
            )

    def __repr__(self) -> str:
        return f"CountTrue({self.bars}, min={self.min_true}, {self.expr!r})"


# =============================================================================
# Type Alias
# =============================================================================

# =============================================================================
# Setup Reference Node
# =============================================================================

@dataclass(frozen=True)
class SetupRef:
    """
    A reference to a Setup defined in configs/setups/.

    Setups are reusable market condition blocks that encapsulate
    common patterns (e.g., "RSI oversold", "EMA pullback").

    When evaluated, the Setup's condition is resolved and evaluated
    as if it were inlined at this position.

    Attributes:
        setup_id: The Setup ID to reference (e.g., "rsi_oversold")

    Examples:
        SetupRef(setup_id="rsi_oversold")
        SetupRef(setup_id="ema_pullback")

    YAML Syntax:
        - setup: rsi_oversold
        - all:
            - setup: rsi_oversold
            - setup: ema_pullback
    """
    setup_id: str

    def __post_init__(self):
        """Validate SetupRef parameters."""
        if not self.setup_id:
            raise ValueError("SetupRef: setup_id is required")

    def __repr__(self) -> str:
        return f"Setup({self.setup_id!r})"


# All expression types that can appear in a condition tree
Expr = AllExpr | AnyExpr | NotExpr | Cond | HoldsFor | OccurredWithin | CountTrue | SetupRef


# =============================================================================
# Utility Functions
# =============================================================================

def get_max_offset(expr: Expr) -> int:
    """
    Get the maximum offset referenced in an expression tree.

    Used for warmup computation. Cross_* operators implicitly use offset=1.

    Args:
        expr: Expression to analyze.

    Returns:
        Maximum offset value found.
    """
    if isinstance(expr, Cond):
        max_off = expr.lhs.offset
        if isinstance(expr.rhs, FeatureRef):
            max_off = max(max_off, expr.rhs.offset)
        # Cross operators implicitly need previous bar
        if expr.op in CROSSOVER_OPERATORS:
            max_off = max(max_off, 1)
        return max_off

    elif isinstance(expr, AllExpr):
        return max((get_max_offset(c) for c in expr.children), default=0)

    elif isinstance(expr, AnyExpr):
        return max((get_max_offset(c) for c in expr.children), default=0)

    elif isinstance(expr, NotExpr):
        return get_max_offset(expr.child)

    elif isinstance(expr, (HoldsFor, OccurredWithin)):
        # Window ops shift expr by 0..bars-1
        return get_max_offset(expr.expr) + expr.bars - 1

    elif isinstance(expr, CountTrue):
        return get_max_offset(expr.expr) + expr.bars - 1

    else:
        return 0


def validate_operator_type_compatibility(
    cond: Cond,
    lhs_output_type: "FeatureOutputType",
) -> list[str]:
    """
    Validate that an operator is compatible with the LHS output type.

    This is called at compile-time (Play loading) to catch type errors
    before runtime.

    Type compatibility rules:
    - FLOAT: CANNOT use eq/in (must use near_abs/near_pct for equality)
    - INT, BOOL, ENUM: CAN use eq/in (discrete types)
    - All numeric types: CAN use gt/gte/lt/lte/between/near_*/cross_*

    Args:
        cond: The Cond node to validate.
        lhs_output_type: The output type of the LHS feature.

    Returns:
        List of error messages (empty if valid).

    Examples:
        >>> from src.backtest.rules.types import FeatureOutputType
        >>> cond = Cond(FeatureRef("rsi_14"), "eq", ScalarValue(50.0))
        >>> validate_operator_type_compatibility(cond, FeatureOutputType.FLOAT)
        ["Operator 'eq' cannot be used with FLOAT type (feature: rsi_14). Use 'near_abs' or 'near_pct' for float equality."]
    """
    from .types import FeatureOutputType

    errors: list[str] = []

    # Check discrete operators (eq, in) against non-discrete types
    if cond.op in DISCRETE_OPERATORS:
        if not lhs_output_type.is_discrete():
            errors.append(
                f"Operator '{cond.op}' cannot be used with {lhs_output_type.name} type "
                f"(feature: {cond.lhs.feature_id}). "
                f"Use 'near_abs' or 'near_pct' for float equality."
            )

    # Check numeric operators against non-numeric types
    # Note: Currently all our types are numeric-compatible except ENUM for some operators
    # ENUM can use eq/in but not gt/lt/between/near_*
    if cond.op in NUMERIC_OPERATORS:
        if lhs_output_type == FeatureOutputType.ENUM:
            errors.append(
                f"Operator '{cond.op}' cannot be used with ENUM type "
                f"(feature: {cond.lhs.feature_id}). "
                f"Use 'eq' or 'in' for enum comparisons."
            )
        elif lhs_output_type == FeatureOutputType.BOOL:
            # Boolean can use some numeric operators (debatable)
            # For now, only allow eq for booleans
            if cond.op not in ("eq",):
                errors.append(
                    f"Operator '{cond.op}' cannot be used with BOOL type "
                    f"(feature: {cond.lhs.feature_id}). "
                    f"Use 'eq' for boolean comparisons."
                )

    return errors


def validate_expr_types(
    expr: Expr,
    get_output_type: "Callable[[str, str], FeatureOutputType]",
) -> list[str]:
    """
    Validate operator/type compatibility for all conditions in an expression tree.

    This recursively walks the expression tree and validates each Cond node
    against the feature output types provided by the get_output_type callback.

    Args:
        expr: Expression tree to validate.
        get_output_type: Callback that takes (feature_id, field) and returns
            FeatureOutputType. Typically registry.get_output_type.

    Returns:
        List of all error messages (empty if valid).

    Examples:
        >>> errors = validate_expr_types(expr, registry.get_output_type)
        >>> if errors:
        ...     raise ValueError("\\n".join(errors))
    """
    errors: list[str] = []

    def validate_recursive(e: Expr) -> None:
        if isinstance(e, Cond):
            try:
                lhs_type = get_output_type(e.lhs.feature_id, e.lhs.field)
                cond_errors = validate_operator_type_compatibility(e, lhs_type)
                errors.extend(cond_errors)
            except (KeyError, ValueError) as ex:
                # Feature not found or field not found - skip type validation
                # (other validation will catch missing features)
                pass

        elif isinstance(e, AllExpr):
            for child in e.children:
                validate_recursive(child)

        elif isinstance(e, AnyExpr):
            for child in e.children:
                validate_recursive(child)

        elif isinstance(e, NotExpr):
            validate_recursive(e.child)

        elif isinstance(e, (HoldsFor, OccurredWithin, CountTrue)):
            validate_recursive(e.expr)

    validate_recursive(expr)
    return errors


def get_referenced_features(expr: Expr) -> set[str]:
    """
    Get all feature IDs referenced in an expression tree.

    Args:
        expr: Expression to analyze.

    Returns:
        Set of feature IDs.
    """
    features: set[str] = set()

    def collect(e: Expr) -> None:
        if isinstance(e, Cond):
            features.add(e.lhs.feature_id)
            if isinstance(e.rhs, FeatureRef):
                features.add(e.rhs.feature_id)

        elif isinstance(e, AllExpr):
            for child in e.children:
                collect(child)

        elif isinstance(e, AnyExpr):
            for child in e.children:
                collect(child)

        elif isinstance(e, NotExpr):
            collect(e.child)

        elif isinstance(e, (HoldsFor, OccurredWithin, CountTrue)):
            collect(e.expr)

    collect(expr)
    return features


# =============================================================================
# Serialization Functions
# =============================================================================

def feature_ref_to_dict(ref: FeatureRef) -> dict:
    """Serialize a FeatureRef to dict."""
    result: dict = {"feature_id": ref.feature_id}
    if ref.field != "value":
        result["field"] = ref.field
    if ref.offset != 0:
        result["offset"] = ref.offset
    return result


def rhs_to_dict(rhs: RhsValue) -> dict | int | float | bool | str | list:
    """Serialize an RHS value to dict/primitive."""
    if isinstance(rhs, FeatureRef):
        return feature_ref_to_dict(rhs)
    elif isinstance(rhs, ScalarValue):
        return rhs.value
    elif isinstance(rhs, RangeValue):
        return {"low": rhs.low, "high": rhs.high}
    elif isinstance(rhs, ListValue):
        return list(rhs.values)
    else:
        raise ValueError(f"Unknown RHS type: {type(rhs)}")


def expr_to_dict(expr: Expr) -> dict:
    """
    Serialize an expression tree to dict format.

    The resulting dict can be serialized to YAML and parsed back
    by the dsl_parser module.

    Args:
        expr: Expression to serialize.

    Returns:
        Dict representation matching YAML schema.
    """
    if isinstance(expr, Cond):
        result: dict = {
            "lhs": feature_ref_to_dict(expr.lhs),
            "op": expr.op,
            "rhs": rhs_to_dict(expr.rhs),
        }
        if expr.tolerance is not None:
            result["tolerance"] = expr.tolerance
        return result

    elif isinstance(expr, AllExpr):
        return {"all": [expr_to_dict(c) for c in expr.children]}

    elif isinstance(expr, AnyExpr):
        return {"any": [expr_to_dict(c) for c in expr.children]}

    elif isinstance(expr, NotExpr):
        return {"not": expr_to_dict(expr.child)}

    elif isinstance(expr, HoldsFor):
        return {
            "holds_for": {
                "bars": expr.bars,
                "expr": expr_to_dict(expr.expr),
            }
        }

    elif isinstance(expr, OccurredWithin):
        return {
            "occurred_within": {
                "bars": expr.bars,
                "expr": expr_to_dict(expr.expr),
            }
        }

    elif isinstance(expr, CountTrue):
        return {
            "count_true": {
                "bars": expr.bars,
                "min_true": expr.min_true,
                "expr": expr_to_dict(expr.expr),
            }
        }

    else:
        raise ValueError(f"Unknown expression type: {type(expr)}")
