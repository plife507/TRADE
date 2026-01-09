"""
Tier 2: Fibonacci Level Tests.

Tests Fibonacci retracement and extension calculations used for
identifying potential support/resistance and target levels.

Key Fibonacci ratios:
- 0.0 (0%): Start of move
- 0.236 (23.6%): Shallow retracement
- 0.382 (38.2%): Moderate retracement
- 0.5 (50%): Midpoint
- 0.618 (61.8%): Golden ratio retracement
- 0.786 (78.6%): Deep retracement
- 1.0 (100%): End of move
- 1.618 (161.8%): First extension target
"""

from __future__ import annotations

import time

from ..runner import TestResult


def run_tests() -> list[TestResult]:
    """Run all Fibonacci level tests."""
    tests: list[TestResult] = []

    # Retracement tests
    tests.append(test_fib_retracement_0())
    tests.append(test_fib_retracement_50())
    tests.append(test_fib_retracement_618())
    tests.append(test_fib_retracement_100())

    # Extension tests
    tests.append(test_fib_extension_up())
    tests.append(test_fib_extension_down())

    return tests


def _calc_fib_retracement(
    high: float,
    low: float,
    ratio: float,
) -> float:
    """
    Calculate Fibonacci retracement level.

    For an uptrend (measuring retracement from high):
    - level = high - (high - low) * ratio

    ratio=0.0 -> high (no retracement)
    ratio=0.5 -> midpoint
    ratio=1.0 -> low (full retracement)
    """
    return high - (high - low) * ratio


def _calc_fib_extension(
    high: float,
    low: float,
    ratio: float,
    direction: int,
) -> float:
    """
    Calculate Fibonacci extension level.

    direction=1 (uptrend extension from high):
    - level = high + (high - low) * (ratio - 1.0)

    direction=-1 (downtrend extension from low):
    - level = low - (high - low) * (ratio - 1.0)

    Common extension: 1.618 (161.8% of the move)
    """
    move = high - low
    extension = move * (ratio - 1.0)

    if direction == 1:
        return high + extension
    else:
        return low - extension


# =============================================================================
# Fibonacci Retracement Tests
# =============================================================================

def test_fib_retracement_0() -> TestResult:
    """T2_010: Retracement 0.0 (high=100, low=80) -> 100.

    0% retracement = price at the high (no pullback yet).
    """
    test_id = "T2_010"
    start = time.perf_counter()

    try:
        level = _calc_fib_retracement(high=100.0, low=80.0, ratio=0.0)
        expected = 100.0

        if abs(level - expected) < 0.001:
            return TestResult(
                test_id=test_id,
                passed=True,
                message=f"Fib 0.0 retracement = {level}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"Expected {expected}, got {level}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
    except Exception as e:
        return TestResult(
            test_id=test_id,
            passed=False,
            message=f"Error: {e}",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


def test_fib_retracement_50() -> TestResult:
    """T2_011: Retracement 0.5 (high=100, low=80) -> 90 (midpoint).

    50% retracement = price at the midpoint of the move.
    """
    test_id = "T2_011"
    start = time.perf_counter()

    try:
        level = _calc_fib_retracement(high=100.0, low=80.0, ratio=0.5)
        expected = 90.0

        if abs(level - expected) < 0.001:
            return TestResult(
                test_id=test_id,
                passed=True,
                message=f"Fib 0.5 retracement = {level}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"Expected {expected}, got {level}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
    except Exception as e:
        return TestResult(
            test_id=test_id,
            passed=False,
            message=f"Error: {e}",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


def test_fib_retracement_618() -> TestResult:
    """T2_012: Retracement 0.618 (high=100, low=80) -> 87.64.

    61.8% retracement = golden ratio level.
    100 - (100 - 80) * 0.618 = 100 - 12.36 = 87.64
    """
    test_id = "T2_012"
    start = time.perf_counter()

    try:
        level = _calc_fib_retracement(high=100.0, low=80.0, ratio=0.618)
        expected = 87.64

        if abs(level - expected) < 0.01:
            return TestResult(
                test_id=test_id,
                passed=True,
                message=f"Fib 0.618 retracement = {level:.2f}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"Expected {expected}, got {level}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
    except Exception as e:
        return TestResult(
            test_id=test_id,
            passed=False,
            message=f"Error: {e}",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


def test_fib_retracement_100() -> TestResult:
    """T2_013: Retracement 1.0 (high=100, low=80) -> 80.

    100% retracement = full retrace back to the low.
    """
    test_id = "T2_013"
    start = time.perf_counter()

    try:
        level = _calc_fib_retracement(high=100.0, low=80.0, ratio=1.0)
        expected = 80.0

        if abs(level - expected) < 0.001:
            return TestResult(
                test_id=test_id,
                passed=True,
                message=f"Fib 1.0 retracement = {level}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"Expected {expected}, got {level}",
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
# Fibonacci Extension Tests
# =============================================================================

def test_fib_extension_up() -> TestResult:
    """T2_014: Extension up 1.618 (high=100, low=80) -> 112.36.

    Uptrend extension: where price might go after breaking the high.
    100 + (100 - 80) * (1.618 - 1.0) = 100 + 20 * 0.618 = 112.36
    """
    test_id = "T2_014"
    start = time.perf_counter()

    try:
        level = _calc_fib_extension(high=100.0, low=80.0, ratio=1.618, direction=1)
        expected = 112.36

        if abs(level - expected) < 0.01:
            return TestResult(
                test_id=test_id,
                passed=True,
                message=f"Fib 1.618 extension up = {level:.2f}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"Expected {expected}, got {level}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
    except Exception as e:
        return TestResult(
            test_id=test_id,
            passed=False,
            message=f"Error: {e}",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


def test_fib_extension_down() -> TestResult:
    """T2_015: Extension down 1.618 (high=100, low=80) -> 67.64.

    Downtrend extension: where price might go after breaking the low.
    80 - (100 - 80) * (1.618 - 1.0) = 80 - 20 * 0.618 = 67.64
    """
    test_id = "T2_015"
    start = time.perf_counter()

    try:
        level = _calc_fib_extension(high=100.0, low=80.0, ratio=1.618, direction=-1)
        expected = 67.64

        if abs(level - expected) < 0.01:
            return TestResult(
                test_id=test_id,
                passed=True,
                message=f"Fib 1.618 extension down = {level:.2f}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"Expected {expected}, got {level}",
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
    print(f"Fibonacci level tests: {passed}/{len(results)} passed")
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  {status}: {r.test_id} - {r.message}")
