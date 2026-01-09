"""
DSL Expression Evaluator - Re-export module.

This module re-exports from src.backtest.rules.evaluation for backward compatibility.
The implementation has been split into focused modules under evaluation/.

Usage unchanged:
    from src.backtest.rules.dsl_eval import ExprEvaluator, evaluate_expression
"""

from .evaluation import ExprEvaluator, evaluate_expression
from .dsl_nodes import DEFAULT_MAX_WINDOW_BARS

__all__ = [
    "ExprEvaluator",
    "evaluate_expression",
    "DEFAULT_MAX_WINDOW_BARS",
]
