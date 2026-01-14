"""
Tier 1: Duration Operator Tests.

Tests duration parsing for window operators (e.g., "30m" -> 30 bars).
"""

from __future__ import annotations

import time

from ..runner import TestResult


def run_tests() -> list[TestResult]:
    """Run all duration operator tests."""
    tests: list[TestResult] = []

    tests.append(test_duration_30m())
    tests.append(test_duration_1h())
    tests.append(test_duration_24h_ceiling())
    tests.append(test_duration_exceeds_ceiling())

    return tests


# Maximum allowed duration in minutes (24 hours = 1440 minutes)
MAX_DURATION_MINUTES = 1440


def _duration_to_bars(duration: str) -> int:
    """
    Parse duration string to bar count (1m granularity).

    Supports: "Nm" (minutes), "Nh" (hours), "Nd" (days).
    Ceiling: 24h (1440 bars).

    Raises:
        ValueError: If duration exceeds ceiling or is invalid.
    """
    duration = duration.lower().strip()

    if duration.endswith("m"):
        minutes = int(duration[:-1])
    elif duration.endswith("h"):
        minutes = int(duration[:-1]) * 60
    elif duration.endswith("d"):
        minutes = int(duration[:-1]) * 1440
    else:
        raise ValueError(f"Invalid duration format: {duration}")

    if minutes > MAX_DURATION_MINUTES:
        raise ValueError(
            f"Duration {duration} ({minutes} min) exceeds ceiling of {MAX_DURATION_MINUTES} min (24h)"
        )

    return minutes


def test_duration_30m() -> TestResult:
    """T1_050: "30m" -> 30 bars."""
    test_id = "T1_050"
    start = time.perf_counter()

    try:
        result = _duration_to_bars("30m")
        expected = 30

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="duration('30m') = 30 bars",
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


def test_duration_1h() -> TestResult:
    """T1_051: "1h" -> 60 bars."""
    test_id = "T1_051"
    start = time.perf_counter()

    try:
        result = _duration_to_bars("1h")
        expected = 60

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="duration('1h') = 60 bars",
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


def test_duration_24h_ceiling() -> TestResult:
    """T1_052: "24h" -> 1440 bars (ceiling)."""
    test_id = "T1_052"
    start = time.perf_counter()

    try:
        result = _duration_to_bars("24h")
        expected = 1440

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="duration('24h') = 1440 bars (ceiling)",
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


def test_duration_exceeds_ceiling() -> TestResult:
    """T1_053: "25h" -> ERROR (exceeds ceiling)."""
    test_id = "T1_053"
    start = time.perf_counter()

    try:
        try:
            _duration_to_bars("25h")
            return TestResult(
                test_id=test_id,
                passed=False,
                message="Expected ValueError for 25h (exceeds ceiling)",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        except ValueError as e:
            if "exceeds ceiling" in str(e):
                return TestResult(
                    test_id=test_id,
                    passed=True,
                    message="duration('25h') correctly raises ValueError (exceeds ceiling)",
                    duration_ms=(time.perf_counter() - start) * 1000,
                )
            else:
                return TestResult(
                    test_id=test_id,
                    passed=False,
                    message=f"Wrong error message: {e}",
                    duration_ms=(time.perf_counter() - start) * 1000,
                )
    except Exception as e:
        return TestResult(
            test_id=test_id,
            passed=False,
            message=f"Unexpected error: {e}",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


if __name__ == "__main__":
    results = run_tests()
    passed = sum(1 for r in results if r.passed)
    print(f"Duration tests: {passed}/{len(results)} passed")
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  {status}: {r.test_id} - {r.message}")
