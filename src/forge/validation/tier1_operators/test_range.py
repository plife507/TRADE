"""
Tier 1: Range/Tolerance Operator Tests.

Tests between, near_abs, and near_pct operators.
"""

from __future__ import annotations

import time

from ..runner import TestResult


def run_tests() -> list[TestResult]:
    """Run all range operator tests."""
    tests: list[TestResult] = []

    tests.append(test_between_in_range())
    tests.append(test_between_at_boundary())
    tests.append(test_between_outside())
    tests.append(test_near_abs_within())
    tests.append(test_near_abs_outside())
    tests.append(test_near_pct_within())

    return tests


def _eval_between(value: float, low: float, high: float) -> bool:
    """
    Evaluate between operator.

    Returns True if low <= value <= high (inclusive boundaries).
    """
    return low <= value <= high


def _eval_near_abs(value: float, target: float, tolerance: float) -> bool:
    """
    Evaluate near_abs operator.

    Returns True if abs(value - target) <= tolerance.
    """
    return abs(value - target) <= tolerance


def _eval_near_pct(value: float, target: float, tolerance_pct: float) -> bool:
    """
    Evaluate near_pct operator.

    Returns True if abs(value - target) / target <= tolerance_pct / 100.
    """
    if target == 0:
        return value == 0
    return abs(value - target) / abs(target) <= tolerance_pct / 100


def test_between_in_range() -> TestResult:
    """T1_020: between - In range (100 in [95,105]) -> True."""
    test_id = "T1_020"
    start = time.perf_counter()

    try:
        result = _eval_between(value=100, low=95, high=105)
        expected = True

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="between(100, [95,105]) = True (in range)",
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


def test_between_at_boundary() -> TestResult:
    """T1_021: between - At boundary (95 in [95,105]) -> True."""
    test_id = "T1_021"
    start = time.perf_counter()

    try:
        result = _eval_between(value=95, low=95, high=105)
        expected = True

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="between(95, [95,105]) = True (at boundary)",
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


def test_between_outside() -> TestResult:
    """T1_022: between - Outside (110 in [95,105]) -> False."""
    test_id = "T1_022"
    start = time.perf_counter()

    try:
        result = _eval_between(value=110, low=95, high=105)
        expected = False

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="between(110, [95,105]) = False (outside)",
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


def test_near_abs_within() -> TestResult:
    """T1_023: near_abs - Within tol (100 vs 101, tol=2) -> True."""
    test_id = "T1_023"
    start = time.perf_counter()

    try:
        result = _eval_near_abs(value=100, target=101, tolerance=2)
        expected = True

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="near_abs(100, 101, tol=2) = True (within tolerance)",
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


def test_near_abs_outside() -> TestResult:
    """T1_024: near_abs - Outside tol (100 vs 105, tol=2) -> False."""
    test_id = "T1_024"
    start = time.perf_counter()

    try:
        result = _eval_near_abs(value=100, target=105, tolerance=2)
        expected = False

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="near_abs(100, 105, tol=2) = False (outside tolerance)",
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


def test_near_pct_within() -> TestResult:
    """T1_025: near_pct - Within 1% (100 vs 100.5) -> True."""
    test_id = "T1_025"
    start = time.perf_counter()

    try:
        # 0.5% difference, tolerance is 1%
        result = _eval_near_pct(value=100, target=100.5, tolerance_pct=1.0)
        expected = True

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="near_pct(100, 100.5, tol=1%) = True (within 1%)",
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
    print(f"Range tests: {passed}/{len(results)} passed")
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  {status}: {r.test_id} - {r.message}")
