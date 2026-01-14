"""Tier 2: Structure math tests."""

from ..runner import TierResult, TierName, TestResult
import time


def run_all_structure_tests() -> TierResult:
    """Run all structure tests and return combined result."""
    from . import (
        test_swing,
        test_fibonacci,
        test_zone,
        test_trend,
        test_rolling,
        test_derived_zone,
    )

    all_tests: list[TestResult] = []
    start = time.perf_counter()

    # Swing detection (T2_001-004)
    all_tests.extend(test_swing.run_tests())

    # Fibonacci levels (T2_010-015)
    all_tests.extend(test_fibonacci.run_tests())

    # Zone detection (T2_020-023)
    all_tests.extend(test_zone.run_tests())

    # Trend classification (T2_030-033)
    all_tests.extend(test_trend.run_tests())

    # Rolling window (T2_040-042)
    all_tests.extend(test_rolling.run_tests())

    # Derived zones (T2_050-053)
    all_tests.extend(test_derived_zone.run_tests())

    duration_ms = (time.perf_counter() - start) * 1000
    passed = all(t.passed for t in all_tests)

    return TierResult(
        tier=TierName.TIER2,
        passed=passed,
        tests=all_tests,
        duration_ms=duration_ms,
    )


__all__ = ["run_all_structure_tests"]
