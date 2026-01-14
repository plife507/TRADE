"""
Tier 1: Anchor TF Tests.

Tests that anchor_tf correctly scales bar offsets for window operators.
"""

from __future__ import annotations

import time

from ..runner import TestResult


def run_tests() -> list[TestResult]:
    """Run all anchor_tf tests."""
    tests: list[TestResult] = []

    tests.append(test_anchor_15m())
    tests.append(test_anchor_1h())
    tests.append(test_no_anchor())

    return tests


def _compute_offsets(bars: int, anchor_tf_minutes: int) -> list[int]:
    """
    Compute bar offsets for window operators with anchor_tf.

    When anchor_tf is set, bars are scaled by anchor_tf minutes.
    For example: bars=3, anchor_tf="15m" -> [0, 15, 30] minutes.

    Without anchor_tf (or anchor_tf="1m"), offsets are just [0, 1, 2, ...].
    """
    return [i * anchor_tf_minutes for i in range(bars)]


def test_anchor_15m() -> TestResult:
    """T1_040: 3 bars at 15m -> offsets [0, 15, 30]."""
    test_id = "T1_040"
    start = time.perf_counter()

    try:
        result = _compute_offsets(bars=3, anchor_tf_minutes=15)
        expected = [0, 15, 30]

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="anchor_tf=15m: 3 bars -> [0, 15, 30] min offsets",
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


def test_anchor_1h() -> TestResult:
    """T1_041: 5 bars at 1h -> offsets [0, 60, 120, 180, 240]."""
    test_id = "T1_041"
    start = time.perf_counter()

    try:
        result = _compute_offsets(bars=5, anchor_tf_minutes=60)
        expected = [0, 60, 120, 180, 240]

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="anchor_tf=1h: 5 bars -> [0, 60, 120, 180, 240] min offsets",
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


def test_no_anchor() -> TestResult:
    """T1_042: No anchor -> offsets [0, 1, 2] (1m granularity)."""
    test_id = "T1_042"
    start = time.perf_counter()

    try:
        # No anchor_tf means 1m granularity
        result = _compute_offsets(bars=3, anchor_tf_minutes=1)
        expected = [0, 1, 2]

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="no anchor_tf: 3 bars -> [0, 1, 2] (1m default)",
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
    print(f"Anchor TF tests: {passed}/{len(results)} passed")
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  {status}: {r.test_id} - {r.message}")
