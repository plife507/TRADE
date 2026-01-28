"""
DSL Constants for Play Expression Language.

This module defines all constant values used by the DSL node types:
- Operator sets (arithmetic, comparison, crossover)
- Window limits
- Duration parsing patterns
"""

from __future__ import annotations

import re

# Import constants from runtime.timeframe
from ...runtime.timeframe import WINDOW_DURATION_CEILING_MINUTES, ACTION_TF_MINUTES

# =============================================================================
# Arithmetic Operators
# =============================================================================
# Operators for inline arithmetic expressions.

ARITHMETIC_OPERATORS = frozenset({
    "+",            # Addition: a + b
    "-",            # Subtraction: a - b
    "*",            # Multiplication: a * b
    "/",            # Division: a / b (div by zero -> None)
    "%",            # Modulo: a % b (int only)
})

# =============================================================================
# Valid Operators
# =============================================================================
# All operators supported by the DSL expression evaluator.
# SYMBOLS are the canonical form (refactored 2026-01-09).

COMPARISON_OPERATORS = frozenset({
    ">",            # Greater than: lhs > rhs
    ">=",           # Greater than or equal: lhs >= rhs
    "<",            # Less than: lhs < rhs
    "<=",           # Less than or equal: lhs <= rhs
    "==",           # Equal (discrete types only): lhs == rhs
    "!=",           # Not equal (discrete types only): lhs != rhs
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
    ">", ">=", "<", "<=", "between", "near_abs", "near_pct",
    "cross_above", "cross_below"
})

# Operators that require discrete types (INT, BOOL, ENUM)
DISCRETE_OPERATORS = frozenset({
    "==", "!=", "in"
})

# Window operator limits (bar-based)
# Used by HoldsFor, OccurredWithin, CountTrue operators
DEFAULT_MAX_WINDOW_BARS = 100   # Default lookback if not specified in DSL
WINDOW_BARS_CEILING = 500       # Hard limit to prevent excessive memory/CPU usage

# Duration parsing regex (matches "5m", "30m", "1h", "4h", "1d", etc.)
DURATION_PATTERN = re.compile(r"^(\d+)(m|h|d)$")

# Re-export imported constants for convenience
__all__ = [
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
]
