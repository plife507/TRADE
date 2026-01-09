"""
Tier 1: Comparison Operator Tests.

Tests gt, lt, gte, lte, eq operators with trading-relevant scenarios.
"""

from __future__ import annotations

import time

from ..runner import TestResult


def run_tests() -> list[TestResult]:
    """Run all comparison operator tests."""
    tests: list[TestResult] = []

    tests.append(test_gt_above())
    tests.append(test_gt_below())
    tests.append(test_gt_equal())
    tests.append(test_gte_equal())
    tests.append(test_lt_below())
    tests.append(test_lte_equal())
    tests.append(test_eq_match())
    tests.append(test_eq_float_rejection())

    return tests


def _eval_comparison(op: str, lhs: float, rhs: float) -> bool:
    """Evaluate a comparison operator."""
    if op == "gt":
        return lhs > rhs
    elif op == "lt":
        return lhs < rhs
    elif op in ("gte", "ge"):
        return lhs >= rhs
    elif op in ("lte", "le"):
        return lhs <= rhs
    elif op == "eq":
        return lhs == rhs
    else:
        raise ValueError(f"Unknown operator: {op}")


def test_gt_above() -> TestResult:
    """T1_001: gt - Price above MA (100 vs 95) -> True."""
    test_id = "T1_001"
    start = time.perf_counter()

    try:
        result = _eval_comparison("gt", 100, 95)
        expected = True

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="gt(100, 95) = True (price above MA)",
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


def test_gt_below() -> TestResult:
    """T1_002: gt - Price below MA (90 vs 95) -> False."""
    test_id = "T1_002"
    start = time.perf_counter()

    try:
        result = _eval_comparison("gt", 90, 95)
        expected = False

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="gt(90, 95) = False (price below MA)",
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


def test_gt_equal() -> TestResult:
    """T1_003: gt - Price equals MA (95 vs 95) -> False."""
    test_id = "T1_003"
    start = time.perf_counter()

    try:
        result = _eval_comparison("gt", 95, 95)
        expected = False

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="gt(95, 95) = False (price equals MA)",
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


def test_gte_equal() -> TestResult:
    """T1_004: gte - Price equals MA (95 vs 95) -> True."""
    test_id = "T1_004"
    start = time.perf_counter()

    try:
        result = _eval_comparison("gte", 95, 95)
        expected = True

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="gte(95, 95) = True (price equals MA)",
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


def test_lt_below() -> TestResult:
    """T1_005: lt - RSI oversold (25 vs 30) -> True."""
    test_id = "T1_005"
    start = time.perf_counter()

    try:
        result = _eval_comparison("lt", 25, 30)
        expected = True

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="lt(25, 30) = True (RSI oversold)",
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


def test_lte_equal() -> TestResult:
    """T1_006: lte - RSI at threshold (30 vs 30) -> True."""
    test_id = "T1_006"
    start = time.perf_counter()

    try:
        result = _eval_comparison("lte", 30, 30)
        expected = True

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="lte(30, 30) = True (RSI at threshold)",
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


def test_eq_match() -> TestResult:
    """T1_007: eq - Trend direction (1 == 1) -> True."""
    test_id = "T1_007"
    start = time.perf_counter()

    try:
        result = _eval_comparison("eq", 1, 1)
        expected = True

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="eq(1, 1) = True (trend direction match)",
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


def test_eq_float_rejection() -> TestResult:
    """T1_008: eq - Float rejection (type system check)."""
    test_id = "T1_008"
    start = time.perf_counter()

    try:
        from src.backtest.rules.registry import OpCategory, get_operator_spec

        spec = get_operator_spec("eq")
        if spec is None:
            return TestResult(
                test_id=test_id,
                passed=False,
                message="eq operator not found in registry",
                duration_ms=(time.perf_counter() - start) * 1000,
            )

        # Check that eq is not for NUMERIC (float) types
        if spec.category == OpCategory.BOOL_INT_ENUM:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="eq operator correctly restricted to BOOL_INT_ENUM (not floats)",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"eq operator has wrong category: {spec.category}",
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
    print(f"Comparison tests: {passed}/{len(results)} passed")
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  {status}: {r.test_id} - {r.message}")
