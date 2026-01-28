"""
Signal evaluation module for unified engine.

This module provides signal evaluation infrastructure for PlayEngine.
The key abstraction is SubLoopEvaluator which handles 1m granularity
evaluation within exec bars.

Usage:
    from src.engine.signal import SubLoopEvaluator, SubLoopContext

Architecture:
    SubLoopEvaluator is engine-agnostic. It takes:
    - SubLoopContext: Engine-specific callbacks for snapshot building
    - QuoteFeed: 1m price data
    - exec_tf: Execution timeframe

    Engines implement SubLoopContext protocol to provide:
    - build_snapshot_1m(): Build snapshot with 1m prices
    - evaluate_signal(): Evaluate strategy and return signal
    - should_skip_entry(): Check if entries are disabled
"""

from .subloop import (
    SubLoopContext,
    SubLoopEvaluator,
    SubLoopResult,
)

__all__ = [
    "SubLoopContext",
    "SubLoopEvaluator",
    "SubLoopResult",
]
