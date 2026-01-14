"""Tier 1: Operator unit tests."""

from ..runner import TierResult, TierName, TestResult
import time


def run_all_operator_tests() -> TierResult:
    """Run all operator tests and return combined result."""
    from . import (
        # Layer 1: Basic operators
        test_comparison,
        test_crossover,
        test_range,
        test_window,
        test_anchor_tf,
        test_duration,
        # Layer 2: Additional operators
        test_set_ops,
        test_window_duration,
        test_boolean,
    )

    all_tests: list[TestResult] = []
    start = time.perf_counter()

    # Layer 1: Basic operators
    all_tests.extend(test_comparison.run_tests())
    all_tests.extend(test_crossover.run_tests())
    all_tests.extend(test_range.run_tests())
    all_tests.extend(test_window.run_tests())
    all_tests.extend(test_anchor_tf.run_tests())
    all_tests.extend(test_duration.run_tests())

    # Layer 2: Additional operators
    all_tests.extend(test_set_ops.run_tests())
    all_tests.extend(test_window_duration.run_tests())
    all_tests.extend(test_boolean.run_tests())

    duration_ms = (time.perf_counter() - start) * 1000
    passed = all(t.passed for t in all_tests)

    return TierResult(
        tier=TierName.TIER1,
        passed=passed,
        tests=all_tests,
        duration_ms=duration_ms,
    )


__all__ = ["run_all_operator_tests"]
