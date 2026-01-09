"""
Tier 2: Swing Detection Tests.

Tests the swing high/low detection algorithm that identifies
local price extremes used for structure analysis.

Swing detection uses left/right confirmation bars:
- Swing High: Bar where high > all bars within left/right window
- Swing Low: Bar where low < all bars within left/right window

These are foundational for trend classification and zone derivation.
"""

from __future__ import annotations

import time

from ..runner import TestResult


def run_tests() -> list[TestResult]:
    """Run all swing detection tests."""
    tests: list[TestResult] = []

    tests.append(test_swing_high_clear())
    tests.append(test_swing_low_clear())
    tests.append(test_swing_high_equal_rejected())
    tests.append(test_swing_delayed_confirmation())

    return tests


def _detect_swing_high(
    highs: list[float],
    left: int = 2,
    right: int = 2,
) -> list[tuple[int, float]]:
    """
    Detect swing highs in price series.

    A swing high at index i requires:
    - highs[i] > all highs in [i-left, i-1]
    - highs[i] > all highs in [i+1, i+right]

    Returns list of (bar_index, high_level) tuples.
    """
    swings: list[tuple[int, float]] = []
    n = len(highs)

    for i in range(left, n - right):
        is_swing = True
        pivot = highs[i]

        # Check left side (must be strictly greater)
        for j in range(i - left, i):
            if highs[j] >= pivot:
                is_swing = False
                break

        if not is_swing:
            continue

        # Check right side (must be strictly greater)
        for j in range(i + 1, i + right + 1):
            if highs[j] >= pivot:
                is_swing = False
                break

        if is_swing:
            swings.append((i, pivot))

    return swings


def _detect_swing_low(
    lows: list[float],
    left: int = 2,
    right: int = 2,
) -> list[tuple[int, float]]:
    """
    Detect swing lows in price series.

    A swing low at index i requires:
    - lows[i] < all lows in [i-left, i-1]
    - lows[i] < all lows in [i+1, i+right]

    Returns list of (bar_index, low_level) tuples.
    """
    swings: list[tuple[int, float]] = []
    n = len(lows)

    for i in range(left, n - right):
        is_swing = True
        pivot = lows[i]

        # Check left side (must be strictly less)
        for j in range(i - left, i):
            if lows[j] <= pivot:
                is_swing = False
                break

        if not is_swing:
            continue

        # Check right side (must be strictly less)
        for j in range(i + 1, i + right + 1):
            if lows[j] <= pivot:
                is_swing = False
                break

        if is_swing:
            swings.append((i, pivot))

    return swings


# =============================================================================
# Swing High Tests
# =============================================================================

def test_swing_high_clear() -> TestResult:
    """T2_001: Clear swing high [100,105,110,105,100] -> high_level=110.

    Trading scenario: Price makes clear peak, confirmed by lower bars on both sides.
    """
    test_id = "T2_001"
    start = time.perf_counter()

    try:
        highs = [100.0, 105.0, 110.0, 105.0, 100.0]
        swings = _detect_swing_high(highs, left=2, right=2)

        # Should find one swing high at index 2 with value 110
        if len(swings) == 1 and swings[0] == (2, 110.0):
            return TestResult(
                test_id=test_id,
                passed=True,
                message="Swing high at bar 2, level=110.0",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"Expected [(2, 110.0)], got {swings}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
    except Exception as e:
        return TestResult(
            test_id=test_id,
            passed=False,
            message=f"Error: {e}",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


def test_swing_low_clear() -> TestResult:
    """T2_002: Clear swing low [50,45,40,45,50] -> low_level=40.

    Trading scenario: Price makes clear trough, confirmed by higher bars on both sides.
    """
    test_id = "T2_002"
    start = time.perf_counter()

    try:
        lows = [50.0, 45.0, 40.0, 45.0, 50.0]
        swings = _detect_swing_low(lows, left=2, right=2)

        # Should find one swing low at index 2 with value 40
        if len(swings) == 1 and swings[0] == (2, 40.0):
            return TestResult(
                test_id=test_id,
                passed=True,
                message="Swing low at bar 2, level=40.0",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"Expected [(2, 40.0)], got {swings}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
    except Exception as e:
        return TestResult(
            test_id=test_id,
            passed=False,
            message=f"Error: {e}",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


def test_swing_high_equal_rejected() -> TestResult:
    """T2_003: Equal highs [100,110,110,100] -> No swing (strictly greater required).

    Trading scenario: Double top pattern - no single dominant high.
    The swing detection requires STRICTLY greater, not equal.
    """
    test_id = "T2_003"
    start = time.perf_counter()

    try:
        # With left=1, right=1, check index 1 and 2
        # Index 1: 110, left has 100 (ok), right has 110 (equal, fails)
        # Index 2: 110, left has 110 (equal, fails)
        highs = [100.0, 110.0, 110.0, 100.0]
        swings = _detect_swing_high(highs, left=1, right=1)

        if len(swings) == 0:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="No swing high (equal bars rejected)",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"Expected no swings, got {swings}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
    except Exception as e:
        return TestResult(
            test_id=test_id,
            passed=False,
            message=f"Error: {e}",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


def test_swing_delayed_confirmation() -> TestResult:
    """T2_004: Delayed confirmation (right=2) -> Confirmed at bar+right.

    Trading scenario: With right=2 confirmation bars, the swing is only
    confirmed 2 bars AFTER the actual high. This is the lookahead-safe
    behavior - we only know it's a swing high once we have confirmation.

    Data: [100, 105, 115, 110, 105, 100]
    Swing high at index 2 (115), confirmed when we have bars 3 and 4.
    """
    test_id = "T2_004"
    start = time.perf_counter()

    try:
        highs = [100.0, 105.0, 115.0, 110.0, 105.0, 100.0]
        swings = _detect_swing_high(highs, left=2, right=2)

        # Swing at index 2, but only detectable after seeing index 4
        # The bar_index returned is the pivot bar (2), but detection
        # happens at bar 4 (pivot + right)
        if len(swings) == 1 and swings[0][0] == 2:
            confirmation_bar = swings[0][0] + 2  # right=2
            return TestResult(
                test_id=test_id,
                passed=True,
                message=f"Swing at bar 2, confirmed at bar {confirmation_bar}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"Expected swing at bar 2, got {swings}",
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
    print(f"Swing detection tests: {passed}/{len(results)} passed")
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  {status}: {r.test_id} - {r.message}")
