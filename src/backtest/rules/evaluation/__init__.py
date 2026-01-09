"""
DSL Expression Evaluation Package.

This package provides the expression evaluator for DSL conditions.
Split from the monolithic dsl_eval.py into focused modules:

- core.py: ExprEvaluator class and main evaluate() dispatch
- boolean_ops.py: AllExpr, AnyExpr, NotExpr evaluation
- condition_ops.py: Cond evaluation, crossover, operator dispatch
- window_ops.py: HoldsFor, OccurredWithin, CountTrue and duration variants
- shift_ops.py: Expression shifting for historical lookback
- resolve.py: FeatureRef and ArithmeticExpr value resolution
- setups.py: SetupRef evaluation with caching

Usage:
    from src.backtest.rules.evaluation import ExprEvaluator, evaluate_expression

    evaluator = ExprEvaluator()
    result = evaluator.evaluate(expr, snapshot)
"""

from .core import ExprEvaluator, evaluate_expression

__all__ = [
    "ExprEvaluator",
    "evaluate_expression",
]
