"""
Tier 1: Boolean Composition Operator Tests.

Tests the boolean logic operators that combine conditions:
- all: AND logic - all conditions must be True
- any: OR logic - at least one condition must be True
- not: Negation - inverts the condition result

These are fundamental to building complex trading rules from simple conditions.
"""

from __future__ import annotations

import time

from ..runner import TestResult


def run_tests() -> list[TestResult]:
    """Run all boolean composition tests."""
    tests: list[TestResult] = []

    # 'all' operator tests
    tests.append(test_all_true())
    tests.append(test_all_one_false())
    tests.append(test_all_empty())

    # 'any' operator tests
    tests.append(test_any_one_true())
    tests.append(test_any_all_false())
    tests.append(test_any_empty())

    # 'not' operator tests
    tests.append(test_not_true())
    tests.append(test_not_false())

    return tests


def _eval_all(conditions: list[bool]) -> bool:
    """
    Evaluate 'all' operator (AND logic).

    Returns True if ALL conditions are True.
    Empty list returns True (vacuous truth).

    Trading use: "Price above EMA AND RSI > 50 AND Volume spike"
    """
    return all(conditions)


def _eval_any(conditions: list[bool]) -> bool:
    """
    Evaluate 'any' operator (OR logic).

    Returns True if ANY condition is True.
    Empty list returns False.

    Trading use: "Exit on SL hit OR TP hit OR signal reversal"
    """
    return any(conditions)


def _eval_not(condition: bool) -> bool:
    """
    Evaluate 'not' operator (negation).

    Returns the opposite of the condition.

    Trading use: "NOT in downtrend" = uptrend or ranging
    """
    return not condition


# =============================================================================
# 'all' Operator Tests (AND Logic)
# =============================================================================

def test_all_true() -> TestResult:
    """T1_080: all - All conditions True -> True.

    Trading scenario: Entry requires ALL of:
    - Price > EMA 50 (trend filter)
    - RSI > 50 (momentum)
    - Volume > average (confirmation)
    """
    test_id = "T1_080"
    start = time.perf_counter()

    try:
        conditions = [
            True,   # price > ema_50
            True,   # rsi > 50
            True,   # volume > avg
        ]
        result = _eval_all(conditions)
        expected = True

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="all([T,T,T]) = True (all conditions met)",
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


def test_all_one_false() -> TestResult:
    """T1_081: all - One condition False -> False.

    Trading scenario: Entry blocked because RSI < 50.
    """
    test_id = "T1_081"
    start = time.perf_counter()

    try:
        conditions = [
            True,   # price > ema_50
            False,  # rsi > 50 (FAILED)
            True,   # volume > avg
        ]
        result = _eval_all(conditions)
        expected = False

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="all([T,F,T]) = False (one condition failed)",
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


def test_all_empty() -> TestResult:
    """T1_082: all - Empty list -> True (vacuous truth).

    Note: This is Python's all([]) behavior. An empty "all" block
    should typically be a schema error, but mathematically it's True.
    """
    test_id = "T1_082"
    start = time.perf_counter()

    try:
        conditions: list[bool] = []
        result = _eval_all(conditions)
        expected = True  # Vacuous truth

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="all([]) = True (vacuous truth)",
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
# 'any' Operator Tests (OR Logic)
# =============================================================================

def test_any_one_true() -> TestResult:
    """T1_083: any - One condition True -> True.

    Trading scenario: Exit on ANY of:
    - Stop loss hit
    - Take profit hit
    - Signal reversal
    """
    test_id = "T1_083"
    start = time.perf_counter()

    try:
        conditions = [
            False,  # stop loss hit
            True,   # take profit hit (TRIGGERED)
            False,  # signal reversal
        ]
        result = _eval_any(conditions)
        expected = True

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="any([F,T,F]) = True (one trigger hit)",
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


def test_any_all_false() -> TestResult:
    """T1_084: any - All conditions False -> False.

    Trading scenario: No exit trigger hit, stay in position.
    """
    test_id = "T1_084"
    start = time.perf_counter()

    try:
        conditions = [
            False,  # stop loss hit
            False,  # take profit hit
            False,  # signal reversal
        ]
        result = _eval_any(conditions)
        expected = False

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="any([F,F,F]) = False (no triggers)",
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


def test_any_empty() -> TestResult:
    """T1_085: any - Empty list -> False.

    Note: This is Python's any([]) behavior.
    """
    test_id = "T1_085"
    start = time.perf_counter()

    try:
        conditions: list[bool] = []
        result = _eval_any(conditions)
        expected = False

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="any([]) = False (no conditions)",
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
# 'not' Operator Tests (Negation)
# =============================================================================

def test_not_true() -> TestResult:
    """T1_086: not - Negate True -> False.

    Trading scenario: "NOT in_position" when in_position=True -> False
    """
    test_id = "T1_086"
    start = time.perf_counter()

    try:
        result = _eval_not(True)
        expected = False

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="not(True) = False",
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


def test_not_false() -> TestResult:
    """T1_087: not - Negate False -> True.

    Trading scenario: "NOT downtrend" when trend=-1 -> allows entry
    Actually: "NOT (trend == -1)" when trend != -1 -> True
    """
    test_id = "T1_087"
    start = time.perf_counter()

    try:
        result = _eval_not(False)
        expected = True

        if result == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="not(False) = True",
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
    print(f"Boolean composition tests: {passed}/{len(results)} passed")
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  {status}: {r.test_id} - {r.message}")
