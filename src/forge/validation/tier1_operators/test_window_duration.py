"""
Tier 1: Duration-Based Window Operator Tests.

Tests window operators that use duration strings ("30m", "1h") instead of bar counts.
Duration is converted to 1m bars (e.g., "30m" = 30 bars at 1m granularity).

Operators:
- holds_for_duration: ALL bars in duration window must satisfy condition
- occurred_within_duration: ANY bar in duration window satisfies condition
- count_true_duration: At least N bars in duration window satisfy condition
"""

from __future__ import annotations

import time

from ..runner import TestResult


def run_tests() -> list[TestResult]:
    """Run all duration-based window operator tests."""
    tests: list[TestResult] = []

    tests.append(test_holds_for_duration_30m())
    tests.append(test_holds_for_duration_1h())
    tests.append(test_occurred_within_duration_30m())
    tests.append(test_occurred_within_duration_with_anchor())
    tests.append(test_count_true_duration_30m())
    tests.append(test_count_true_duration_threshold())

    return tests


def _duration_to_bars(duration: str) -> int:
    """
    Convert duration string to bar count (1m granularity).

    "30m" -> 30 bars
    "1h" -> 60 bars
    "4h" -> 240 bars
    """
    duration = duration.lower().strip()
    if duration.endswith("m"):
        return int(duration[:-1])
    elif duration.endswith("h"):
        return int(duration[:-1]) * 60
    else:
        raise ValueError(f"Invalid duration: {duration}")


def _eval_holds_for_duration(values: list[bool], duration: str) -> bool:
    """
    Evaluate holds_for_duration operator.

    Returns True if ALL bars in the duration window are True.
    Duration is converted to 1m bars.
    """
    bars = _duration_to_bars(duration)
    if len(values) < bars:
        return False
    return all(values[-bars:])


def _eval_occurred_within_duration(values: list[bool], duration: str) -> bool:
    """
    Evaluate occurred_within_duration operator.

    Returns True if ANY bar in the duration window is True.
    """
    bars = _duration_to_bars(duration)
    if len(values) < bars:
        return any(values)
    return any(values[-bars:])


def _eval_count_true_duration(values: list[bool], duration: str, threshold: int) -> bool:
    """
    Evaluate count_true_duration operator.

    Returns True if at least `threshold` bars in duration window are True.
    """
    bars = _duration_to_bars(duration)
    if len(values) < bars:
        return sum(values) >= threshold
    return sum(values[-bars:]) >= threshold


# =============================================================================
# holds_for_duration Tests
# =============================================================================

def test_holds_for_duration_30m() -> TestResult:
    """T1_070: holds_for_duration - RSI > 50 for "30m" (30 bars all True) -> True."""
    test_id = "T1_070"
    start = time.perf_counter()

    try:
        # 30 bars of RSI > 50
        values = [True] * 30
        result = _eval_holds_for_duration(values, "30m")
        expected = True

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="holds_for_duration([T]*30, '30m') = True",
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


def test_holds_for_duration_1h() -> TestResult:
    """T1_071: holds_for_duration - "1h" = 60 bars, one False -> False."""
    test_id = "T1_071"
    start = time.perf_counter()

    try:
        # 60 bars with one False in the middle
        values = [True] * 30 + [False] + [True] * 29
        result = _eval_holds_for_duration(values, "1h")
        expected = False

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="holds_for_duration([T..F..T], '1h') = False (one dip)",
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
# occurred_within_duration Tests
# =============================================================================

def test_occurred_within_duration_30m() -> TestResult:
    """T1_072: occurred_within_duration - Volume spike in "30m" window -> True."""
    test_id = "T1_072"
    start = time.perf_counter()

    try:
        # 30 bars with one spike at bar 15
        values = [False] * 15 + [True] + [False] * 14
        result = _eval_occurred_within_duration(values, "30m")
        expected = True

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="occurred_within_duration([F..T..F], '30m') = True",
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


def test_occurred_within_duration_with_anchor() -> TestResult:
    """T1_073: occurred_within_duration - No spike in window -> False."""
    test_id = "T1_073"
    start = time.perf_counter()

    try:
        # 30 bars with no True values
        values = [False] * 30
        result = _eval_occurred_within_duration(values, "30m")
        expected = False

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="occurred_within_duration([F]*30, '30m') = False",
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
# count_true_duration Tests
# =============================================================================

def test_count_true_duration_30m() -> TestResult:
    """T1_074: count_true_duration - 20/30 bullish bars, threshold=15 -> True."""
    test_id = "T1_074"
    start = time.perf_counter()

    try:
        # 20 True, 10 False in 30m window
        values = [True] * 20 + [False] * 10
        result = _eval_count_true_duration(values, "30m", threshold=15)
        expected = True

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="count_true_duration(20/30, '30m', thresh=15) = True",
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


def test_count_true_duration_threshold() -> TestResult:
    """T1_075: count_true_duration - 10/30 bullish bars, threshold=15 -> False."""
    test_id = "T1_075"
    start = time.perf_counter()

    try:
        # 10 True, 20 False - below threshold
        values = [True] * 10 + [False] * 20
        result = _eval_count_true_duration(values, "30m", threshold=15)
        expected = False

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="count_true_duration(10/30, '30m', thresh=15) = False",
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
    print(f"Duration window tests: {passed}/{len(results)} passed")
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  {status}: {r.test_id} - {r.message}")
