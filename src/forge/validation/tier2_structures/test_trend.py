"""
Tier 2: Trend Classification Tests.

Tests trend direction classification based on swing point sequences.

Trend classification rules (Higher Highs/Higher Lows pattern):
- Uptrend (direction=1): HH + HL (higher highs AND higher lows)
- Downtrend (direction=-1): LH + LL (lower highs AND lower lows)
- Ranging (direction=0): Mixed pattern (HH+LL or LH+HL)

This is the foundation of market structure analysis.
"""

from __future__ import annotations

import time

from ..runner import TestResult


def run_tests() -> list[TestResult]:
    """Run all trend classification tests."""
    tests: list[TestResult] = []

    tests.append(test_trend_uptrend())
    tests.append(test_trend_downtrend())
    tests.append(test_trend_ranging_hh_ll())
    tests.append(test_trend_ranging_lh_hl())

    return tests


def _classify_trend(
    prev_high: float,
    curr_high: float,
    prev_low: float,
    curr_low: float,
) -> int:
    """
    Classify trend based on swing point comparison.

    Compares current swing high/low to previous swing high/low.

    Returns:
        1: Uptrend (HH + HL)
        -1: Downtrend (LH + LL)
        0: Ranging (mixed pattern)
    """
    is_higher_high = curr_high > prev_high
    is_higher_low = curr_low > prev_low
    is_lower_high = curr_high < prev_high
    is_lower_low = curr_low < prev_low

    # Uptrend: Higher Highs AND Higher Lows
    if is_higher_high and is_higher_low:
        return 1

    # Downtrend: Lower Highs AND Lower Lows
    if is_lower_high and is_lower_low:
        return -1

    # Ranging: Any mixed pattern
    return 0


# =============================================================================
# Trend Classification Tests
# =============================================================================

def test_trend_uptrend() -> TestResult:
    """T2_030: HH, HL sequence -> direction=1 (uptrend).

    Trading scenario: Price making higher highs and higher lows.
    Classic uptrend structure - favor long positions.

    prev_high=100, curr_high=110 (HH)
    prev_low=90, curr_low=95 (HL)
    """
    test_id = "T2_030"
    start = time.perf_counter()

    try:
        direction = _classify_trend(
            prev_high=100.0,
            curr_high=110.0,
            prev_low=90.0,
            curr_low=95.0,
        )
        expected = 1

        if direction == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="HH + HL = Uptrend (direction=1)",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"Expected {expected}, got {direction}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
    except Exception as e:
        return TestResult(
            test_id=test_id,
            passed=False,
            message=f"Error: {e}",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


def test_trend_downtrend() -> TestResult:
    """T2_031: LH, LL sequence -> direction=-1 (downtrend).

    Trading scenario: Price making lower highs and lower lows.
    Classic downtrend structure - favor short positions.

    prev_high=100, curr_high=95 (LH)
    prev_low=80, curr_low=75 (LL)
    """
    test_id = "T2_031"
    start = time.perf_counter()

    try:
        direction = _classify_trend(
            prev_high=100.0,
            curr_high=95.0,
            prev_low=80.0,
            curr_low=75.0,
        )
        expected = -1

        if direction == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="LH + LL = Downtrend (direction=-1)",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"Expected {expected}, got {direction}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
    except Exception as e:
        return TestResult(
            test_id=test_id,
            passed=False,
            message=f"Error: {e}",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


def test_trend_ranging_hh_ll() -> TestResult:
    """T2_032: HH, LL sequence -> direction=0 (ranging).

    Trading scenario: Price making higher high but lower low.
    Expanding range - no clear directional bias.

    prev_high=100, curr_high=105 (HH)
    prev_low=90, curr_low=85 (LL)
    """
    test_id = "T2_032"
    start = time.perf_counter()

    try:
        direction = _classify_trend(
            prev_high=100.0,
            curr_high=105.0,
            prev_low=90.0,
            curr_low=85.0,
        )
        expected = 0

        if direction == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="HH + LL = Ranging (direction=0)",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"Expected {expected}, got {direction}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
    except Exception as e:
        return TestResult(
            test_id=test_id,
            passed=False,
            message=f"Error: {e}",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


def test_trend_ranging_lh_hl() -> TestResult:
    """T2_033: LH, HL sequence -> direction=0 (ranging).

    Trading scenario: Price making lower high but higher low.
    Contracting range (consolidation) - no clear directional bias.

    prev_high=100, curr_high=98 (LH)
    prev_low=90, curr_low=92 (HL)
    """
    test_id = "T2_033"
    start = time.perf_counter()

    try:
        direction = _classify_trend(
            prev_high=100.0,
            curr_high=98.0,
            prev_low=90.0,
            curr_low=92.0,
        )
        expected = 0

        if direction == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="LH + HL = Ranging (direction=0)",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"Expected {expected}, got {direction}",
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
    print(f"Trend classification tests: {passed}/{len(results)} passed")
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  {status}: {r.test_id} - {r.message}")
