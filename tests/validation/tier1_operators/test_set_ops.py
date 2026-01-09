"""
Tier 1: Set & Approximate Equality Operator Tests.

Tests:
- in: Set membership (discrete types only)
- approx_eq: Float equality with tolerance
"""

from __future__ import annotations

import time

from ..runner import TestResult


def run_tests() -> list[TestResult]:
    """Run all set/approx operator tests."""
    tests: list[TestResult] = []

    # 'in' operator tests
    tests.append(test_in_value_in_set())
    tests.append(test_in_value_not_in_set())
    tests.append(test_in_empty_set())

    # 'approx_eq' operator tests
    tests.append(test_approx_eq_within_tolerance())
    tests.append(test_approx_eq_outside_tolerance())
    tests.append(test_approx_eq_exact_match())

    return tests


def _eval_in(value: int | str, values: list) -> bool:
    """
    Evaluate 'in' operator.

    Returns True if value is in the set of values.
    Used for discrete types (int, enum, bool) - NOT floats.
    """
    return value in values


def _eval_approx_eq(value: float, target: float, tolerance: float) -> bool:
    """
    Evaluate 'approx_eq' operator.

    Returns True if |value - target| <= tolerance.
    Used for float equality where exact comparison is unreliable.
    """
    return abs(value - target) <= tolerance


# =============================================================================
# 'in' Operator Tests
# =============================================================================

def test_in_value_in_set() -> TestResult:
    """T1_060: in - Value in set (1 in [1,2,3]) -> True."""
    test_id = "T1_060"
    start = time.perf_counter()

    try:
        # Trend direction 1 (bullish) in allowed directions
        result = _eval_in(value=1, values=[1, -1])
        expected = True

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="in(1, [1,-1]) = True (bullish in allowed)",
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


def test_in_value_not_in_set() -> TestResult:
    """T1_061: in - Value not in set (0 in [1,-1]) -> False."""
    test_id = "T1_061"
    start = time.perf_counter()

    try:
        # Trend direction 0 (ranging) not in [bullish, bearish]
        result = _eval_in(value=0, values=[1, -1])
        expected = False

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="in(0, [1,-1]) = False (ranging not in trend set)",
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


def test_in_empty_set() -> TestResult:
    """T1_062: in - Empty set always False."""
    test_id = "T1_062"
    start = time.perf_counter()

    try:
        result = _eval_in(value=1, values=[])
        expected = False

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="in(1, []) = False (empty set)",
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


# =============================================================================
# 'approx_eq' Operator Tests
# =============================================================================

def test_approx_eq_within_tolerance() -> TestResult:
    """T1_063: approx_eq - Within tolerance (100.05 ≈ 100, tol=0.1) -> True."""
    test_id = "T1_063"
    start = time.perf_counter()

    try:
        # Price close to target within tolerance
        result = _eval_approx_eq(value=100.05, target=100.0, tolerance=0.1)
        expected = True

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="approx_eq(100.05, 100, tol=0.1) = True",
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


def test_approx_eq_outside_tolerance() -> TestResult:
    """T1_064: approx_eq - Outside tolerance (100.5 ≈ 100, tol=0.1) -> False."""
    test_id = "T1_064"
    start = time.perf_counter()

    try:
        # Price too far from target
        result = _eval_approx_eq(value=100.5, target=100.0, tolerance=0.1)
        expected = False

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="approx_eq(100.5, 100, tol=0.1) = False",
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


def test_approx_eq_exact_match() -> TestResult:
    """T1_065: approx_eq - Exact match (100 ≈ 100, tol=0.1) -> True."""
    test_id = "T1_065"
    start = time.perf_counter()

    try:
        # Exact match
        result = _eval_approx_eq(value=100.0, target=100.0, tolerance=0.1)
        expected = True

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="approx_eq(100, 100, tol=0.1) = True (exact)",
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
    print(f"Set/Approx tests: {passed}/{len(results)} passed")
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  {status}: {r.test_id} - {r.message}")
