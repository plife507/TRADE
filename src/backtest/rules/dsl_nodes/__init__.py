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

# Constants
from .constants import (
    ARITHMETIC_OPERATORS,
    COMPARISON_OPERATORS,
    CROSSOVER_OPERATORS,
    VALID_OPERATORS,
    NUMERIC_OPERATORS,
    DISCRETE_OPERATORS,
    DEFAULT_MAX_WINDOW_BARS,
    WINDOW_BARS_CEILING,
    DURATION_PATTERN,
    WINDOW_DURATION_CEILING_MINUTES,
    ACTION_TF_MINUTES,
)

# Base value nodes
from .base import (
    FeatureRef,
    ScalarValue,
    RangeValue,
    ListValue,
    ArithmeticExpr,
    ArithmeticOperand,
    RhsValue,
)

# Condition node
from .condition import Cond

# Boolean expression nodes
from .boolean import (
    AllExpr,
    AnyExpr,
    NotExpr,
    SetupRef,
)

# Window operator nodes and duration utilities
from .windows import (
    parse_duration_to_minutes,
    duration_to_bars,
    HoldsFor,
    OccurredWithin,
    CountTrue,
    HoldsForDuration,
    OccurredWithinDuration,
    CountTrueDuration,
    BarWindowExpr,
    DurationWindowExpr,
    WindowExpr,
)

# Type aliases
from .types import Expr

# Utility functions
from .utils import (
    get_max_offset,
    validate_operator_type_compatibility,
    validate_expr_types,
    get_referenced_features,
    feature_ref_to_dict,
    arithmetic_to_list,
    lhs_to_dict,
    rhs_to_dict,
    expr_to_dict,
)


__all__ = [
    # Constants
    "ARITHMETIC_OPERATORS",
    "COMPARISON_OPERATORS",
    "CROSSOVER_OPERATORS",
    "VALID_OPERATORS",
    "NUMERIC_OPERATORS",
    "DISCRETE_OPERATORS",
    "DEFAULT_MAX_WINDOW_BARS",
    "WINDOW_BARS_CEILING",
    "DURATION_PATTERN",
    "WINDOW_DURATION_CEILING_MINUTES",
    "ACTION_TF_MINUTES",
    # Base value nodes
    "FeatureRef",
    "ScalarValue",
    "RangeValue",
    "ListValue",
    "ArithmeticExpr",
    "ArithmeticOperand",
    "RhsValue",
    # Condition node
    "Cond",
    # Boolean expression nodes
    "AllExpr",
    "AnyExpr",
    "NotExpr",
    "SetupRef",
    # Duration utilities
    "parse_duration_to_minutes",
    "duration_to_bars",
    # Window operator nodes
    "HoldsFor",
    "OccurredWithin",
    "CountTrue",
    "HoldsForDuration",
    "OccurredWithinDuration",
    "CountTrueDuration",
    "BarWindowExpr",
    "DurationWindowExpr",
    "WindowExpr",
    # Type aliases
    "Expr",
    # Utility functions
    "get_max_offset",
    "validate_operator_type_compatibility",
    "validate_expr_types",
    "get_referenced_features",
    "feature_ref_to_dict",
    "arithmetic_to_list",
    "lhs_to_dict",
    "rhs_to_dict",
    "expr_to_dict",
]
