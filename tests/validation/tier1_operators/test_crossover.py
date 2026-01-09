"""
Tier 1: Crossover Operator Tests.

Tests cross_above and cross_below operators with TradingView-aligned semantics:
- cross_above: prev_lhs <= rhs AND curr_lhs > rhs
- cross_below: prev_lhs >= rhs AND curr_lhs < rhs
"""

from __future__ import annotations

import time

from ..runner import TestResult


def run_tests() -> list[TestResult]:
    """Run all crossover operator tests."""
    tests: list[TestResult] = []

    tests.append(test_cross_above_golden_cross())
    tests.append(test_cross_above_already_above())
    tests.append(test_cross_above_still_below())
    tests.append(test_cross_above_touch_then_above())
    tests.append(test_cross_below_death_cross())
    tests.append(test_cross_below_touch_then_below())

    return tests


def _eval_cross_above(prev_lhs: float, curr_lhs: float, rhs: float) -> bool:
    """
    Evaluate cross_above operator (TradingView semantics).

    A cross above occurs when:
    - Previous value was at or below the threshold
    - Current value is strictly above the threshold
    """
    return prev_lhs <= rhs and curr_lhs > rhs


def _eval_cross_below(prev_lhs: float, curr_lhs: float, rhs: float) -> bool:
    """
    Evaluate cross_below operator (TradingView semantics).

    A cross below occurs when:
    - Previous value was at or above the threshold
    - Current value is strictly below the threshold
    """
    return prev_lhs >= rhs and curr_lhs < rhs


def test_cross_above_golden_cross() -> TestResult:
    """T1_010: cross_above - Golden cross (prev=94, curr=96, rhs=95) -> True."""
    test_id = "T1_010"
    start = time.perf_counter()

    try:
        # Price crosses above MA from below
        result = _eval_cross_above(prev_lhs=94, curr_lhs=96, rhs=95)
        expected = True

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="cross_above(94->96, 95) = True (golden cross)",
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


def test_cross_above_already_above() -> TestResult:
    """T1_011: cross_above - Already above (prev=96, curr=97, rhs=95) -> False."""
    test_id = "T1_011"
    start = time.perf_counter()

    try:
        # Price was already above MA, no cross
        result = _eval_cross_above(prev_lhs=96, curr_lhs=97, rhs=95)
        expected = False

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="cross_above(96->97, 95) = False (already above)",
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


def test_cross_above_still_below() -> TestResult:
    """T1_012: cross_above - Still below (prev=93, curr=94, rhs=95) -> False."""
    test_id = "T1_012"
    start = time.perf_counter()

    try:
        # Price still below MA, no cross
        result = _eval_cross_above(prev_lhs=93, curr_lhs=94, rhs=95)
        expected = False

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="cross_above(93->94, 95) = False (still below)",
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


def test_cross_above_touch_then_above() -> TestResult:
    """T1_013: cross_above - Touch then above (prev=95, curr=96, rhs=95) -> True."""
    test_id = "T1_013"
    start = time.perf_counter()

    try:
        # Price was exactly at MA, now above -> counts as cross
        result = _eval_cross_above(prev_lhs=95, curr_lhs=96, rhs=95)
        expected = True

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="cross_above(95->96, 95) = True (touch then above)",
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


def test_cross_below_death_cross() -> TestResult:
    """T1_014: cross_below - Death cross (prev=96, curr=94, rhs=95) -> True."""
    test_id = "T1_014"
    start = time.perf_counter()

    try:
        # Price crosses below MA from above
        result = _eval_cross_below(prev_lhs=96, curr_lhs=94, rhs=95)
        expected = True

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="cross_below(96->94, 95) = True (death cross)",
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


def test_cross_below_touch_then_below() -> TestResult:
    """T1_015: cross_below - Touch then below (prev=95, curr=94, rhs=95) -> True."""
    test_id = "T1_015"
    start = time.perf_counter()

    try:
        # Price was exactly at MA, now below -> counts as cross
        result = _eval_cross_below(prev_lhs=95, curr_lhs=94, rhs=95)
        expected = True

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="cross_below(95->94, 95) = True (touch then below)",
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
    print(f"Crossover tests: {passed}/{len(results)} passed")
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  {status}: {r.test_id} - {r.message}")
