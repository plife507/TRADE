"""
Tier 2: Rolling Window Tests.

Tests rolling window aggregations used throughout structure detection.

Rolling windows maintain a fixed-size window of values and compute
aggregations like min/max efficiently. These are fundamental building
blocks for swing detection, zone tracking, and level identification.
"""

from __future__ import annotations

import time
from typing import Literal

from ..runner import TestResult


def run_tests() -> list[TestResult]:
    """Run all rolling window tests."""
    tests: list[TestResult] = []

    tests.append(test_rolling_min_full())
    tests.append(test_rolling_max_full())
    tests.append(test_rolling_min_partial())

    return tests


def _rolling_aggregate(
    values: list[float],
    size: int,
    mode: Literal["min", "max"],
) -> float:
    """
    Compute rolling window aggregate.

    Takes the last `size` values and returns min or max.
    If fewer values than size, uses all available values.
    """
    window = values[-size:] if len(values) >= size else values
    if mode == "min":
        return min(window)
    else:
        return max(window)


# =============================================================================
# Rolling Window Tests
# =============================================================================

def test_rolling_min_full() -> TestResult:
    """T2_040: min mode, size=5 [10,8,12,7,9] -> 7.

    Trading scenario: Finding the lowest low in the last 5 bars.
    Used for swing low detection and support identification.
    """
    test_id = "T2_040"
    start = time.perf_counter()

    try:
        values = [10.0, 8.0, 12.0, 7.0, 9.0]
        result = _rolling_aggregate(values, size=5, mode="min")
        expected = 7.0

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message=f"rolling_min(5) = {result}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"Expected {expected}, got {result}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
    except Exception as e:
        return TestResult(
            test_id=test_id,
            passed=False,
            message=f"Error: {e}",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


def test_rolling_max_full() -> TestResult:
    """T2_041: max mode, size=5 [10,8,12,7,9] -> 12.

    Trading scenario: Finding the highest high in the last 5 bars.
    Used for swing high detection and resistance identification.
    """
    test_id = "T2_041"
    start = time.perf_counter()

    try:
        values = [10.0, 8.0, 12.0, 7.0, 9.0]
        result = _rolling_aggregate(values, size=5, mode="max")
        expected = 12.0

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message=f"rolling_max(5) = {result}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"Expected {expected}, got {result}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
    except Exception as e:
        return TestResult(
            test_id=test_id,
            passed=False,
            message=f"Error: {e}",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


def test_rolling_min_partial() -> TestResult:
    """T2_042: min mode, size=3 (last 3 of [10,8,12,7,9]) -> 7.

    Trading scenario: Shorter lookback window.
    Last 3 values are [12, 7, 9], min is 7.
    """
    test_id = "T2_042"
    start = time.perf_counter()

    try:
        values = [10.0, 8.0, 12.0, 7.0, 9.0]
        result = _rolling_aggregate(values, size=3, mode="min")
        expected = 7.0

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message=f"rolling_min(3) of last 3 = {result}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"Expected {expected}, got {result}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
    except Exception as e:
        return TestResult(
            test_id=test_id,
            passed=False,
            message=f"Error: {e}",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


if __name__ == "__main__":
    results = run_tests()
    passed = sum(1 for r in results if r.passed)
    print(f"Rolling window tests: {passed}/{len(results)} passed")
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  {status}: {r.test_id} - {r.message}")
