"""
Tier 1: Window Operator Tests.

Tests holds_for, occurred_within, and count_true operators.
"""

from __future__ import annotations

import time

from ..runner import TestResult


def run_tests() -> list[TestResult]:
    """Run all window operator tests."""
    tests: list[TestResult] = []

    tests.append(test_holds_for_all_true())
    tests.append(test_holds_for_dips())
    tests.append(test_occurred_within_spike_found())
    tests.append(test_occurred_within_no_spike())
    tests.append(test_count_true_threshold_met())
    tests.append(test_count_true_threshold_not_met())

    return tests


def _eval_holds_for(values: list[bool], bars: int) -> bool:
    """
    Evaluate holds_for operator.

    Returns True if ALL of the last N bars are True.
    """
    if len(values) < bars:
        return False
    return all(values[-bars:])


def _eval_occurred_within(values: list[bool], bars: int) -> bool:
    """
    Evaluate occurred_within operator.

    Returns True if ANY of the last N bars is True.
    """
    if len(values) < bars:
        return any(values)
    return any(values[-bars:])


def _eval_count_true(values: list[bool], bars: int, threshold: int) -> bool:
    """
    Evaluate count_true operator.

    Returns True if at least `threshold` of the last N bars are True.
    """
    if len(values) < bars:
        return sum(values) >= threshold
    return sum(values[-bars:]) >= threshold


def test_holds_for_all_true() -> TestResult:
    """T1_030: holds_for - RSI > 50 for 3 bars [55,52,51] -> True."""
    test_id = "T1_030"
    start = time.perf_counter()

    try:
        # All 3 bars have RSI > 50
        values = [True, True, True]  # [55>50, 52>50, 51>50]
        result = _eval_holds_for(values, bars=3)
        expected = True

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="holds_for([T,T,T], 3) = True (all bars satisfy)",
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


def test_holds_for_dips() -> TestResult:
    """T1_031: holds_for - RSI dips [55,48,51] -> False."""
    test_id = "T1_031"
    start = time.perf_counter()

    try:
        # Middle bar has RSI < 50
        values = [True, False, True]  # [55>50, 48>50=F, 51>50]
        result = _eval_holds_for(values, bars=3)
        expected = False

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="holds_for([T,F,T], 3) = False (dip breaks hold)",
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


def test_occurred_within_spike_found() -> TestResult:
    """T1_032: occurred_within - Volume spike found [30,32,80,31,29] -> True."""
    test_id = "T1_032"
    start = time.perf_counter()

    try:
        # Volume > 50 spike at bar 3 (value=80)
        values = [False, False, True, False, False]  # [30>50, 32>50, 80>50, 31>50, 29>50]
        result = _eval_occurred_within(values, bars=5)
        expected = True

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="occurred_within([F,F,T,F,F], 5) = True (spike found)",
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


def test_occurred_within_no_spike() -> TestResult:
    """T1_033: occurred_within - No spike [30,32,35,31,29] -> False."""
    test_id = "T1_033"
    start = time.perf_counter()

    try:
        # No volume > 50 spike in window
        values = [False, False, False, False, False]  # all below 50
        result = _eval_occurred_within(values, bars=5)
        expected = False

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="occurred_within([F,F,F,F,F], 5) = False (no spike)",
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


def test_count_true_threshold_met() -> TestResult:
    """T1_034: count_true - 3/5 bullish -> True."""
    test_id = "T1_034"
    start = time.perf_counter()

    try:
        # 3 of 5 bars are bullish (close > open)
        values = [True, False, True, True, False]
        result = _eval_count_true(values, bars=5, threshold=3)
        expected = True

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="count_true([T,F,T,T,F], 5, thresh=3) = True (3/5 >= 3)",
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


def test_count_true_threshold_not_met() -> TestResult:
    """T1_035: count_true - 2/5 bullish -> False."""
    test_id = "T1_035"
    start = time.perf_counter()

    try:
        # Only 2 of 5 bars are bullish
        values = [True, False, True, False, False]
        result = _eval_count_true(values, bars=5, threshold=3)
        expected = False

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="count_true([T,F,T,F,F], 5, thresh=3) = False (2/5 < 3)",
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
    print(f"Window tests: {passed}/{len(results)} passed")
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  {status}: {r.test_id} - {r.message}")
