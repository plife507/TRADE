"""
Tier 0: Syntax & Parse Tests.

Tests that Play YAML files parse correctly and validation catches errors.
"""

import time
from typing import Any

from ..test_runner import TierResult, TierName, TestResult


def run_all() -> TierResult:
    """Run all Tier 0 parse tests."""
    tests: list[TestResult] = []
    start = time.perf_counter()

    tests.append(test_valid_minimal_play())
    tests.append(test_missing_required_field())
    tests.append(test_invalid_operator())
    tests.append(test_invalid_feature_ref())
    tests.append(test_invalid_anchor_tf())
    tests.append(test_invalid_duration())

    duration_ms = (time.perf_counter() - start) * 1000
    passed = all(t.passed for t in tests)

    return TierResult(
        tier=TierName.TIER0,
        passed=passed,
        tests=tests,
        duration_ms=duration_ms,
    )


def test_valid_minimal_play() -> TestResult:
    """T0_001: Valid minimal Play parses successfully."""
    test_id = "T0_001"
    start = time.perf_counter()

    try:
        from src.backtest.play import Play

        # Minimal valid Play config
        config: dict[str, Any] = {
            "id": "test_minimal",
            "version": "3.0.0",
            "symbol": "BTCUSDT",
            "tf": "15m",
            "features": [
                {
                    "id": "ema_9",
                    "tf": "15m",
                    "type": "indicator",
                    "indicator_type": "ema",
                    "params": {"length": 9},
                }
            ],
            "actions": [
                {
                    "id": "entry",
                    "cases": [
                        {
                            "when": {
                                "lhs": {"feature_id": "ema_9"},
                                "op": ">",
                                "rhs": 100,
                            },
                            "emit": [{"action": "entry_long"}],
                        }
                    ],
                }
            ],
            "account": {
                "starting_equity_usdt": 10000,
                "max_leverage": 10,
            },
        }

        play = Play.from_dict(config)
        assert play.id == "test_minimal"
        assert "BTCUSDT" in play.symbol_universe

        return TestResult(
            test_id=test_id,
            passed=True,
            message="Valid minimal Play parsed successfully",
            duration_ms=(time.perf_counter() - start) * 1000,
        )

    except Exception as e:
        return TestResult(
            test_id=test_id,
            passed=False,
            message=f"Failed to parse valid Play: {e}",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


def test_missing_required_field() -> TestResult:
    """T0_002: Missing required field fails with clear error."""
    test_id = "T0_002"
    start = time.perf_counter()

    try:
        from src.backtest.play import Play

        # Missing 'id' field
        config: dict[str, Any] = {
            "version": "3.0.0",
            "symbol": "BTCUSDT",
            "tf": "15m",
            "features": [],
            "actions": [],
        }

        try:
            Play.from_dict(config)
            return TestResult(
                test_id=test_id,
                passed=False,
                message="Expected error for missing 'id' field, but parse succeeded",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        except (KeyError, ValueError, TypeError) as e:
            return TestResult(
                test_id=test_id,
                passed=True,
                message=f"Correctly failed on missing field: {type(e).__name__}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )

    except Exception as e:
        return TestResult(
            test_id=test_id,
            passed=False,
            message=f"Unexpected error: {e}",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


def test_invalid_operator() -> TestResult:
    """T0_003: Invalid operator name fails validation."""
    test_id = "T0_003"
    start = time.perf_counter()

    try:
        from src.backtest.rules.registry import validate_operator

        # Test invalid operator
        error = validate_operator("invalid_op")
        if error is not None:
            return TestResult(
                test_id=test_id,
                passed=True,
                message=f"Correctly rejected invalid operator: {error[:50]}...",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message="Invalid operator was accepted",
                duration_ms=(time.perf_counter() - start) * 1000,
            )

    except Exception as e:
        return TestResult(
            test_id=test_id,
            passed=False,
            message=f"Unexpected error: {e}",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


def test_invalid_feature_ref() -> TestResult:
    """T0_004: Invalid feature_id reference fails."""
    test_id = "T0_004"
    start = time.perf_counter()

    try:
        from src.backtest.feature_registry import FeatureRegistry

        registry = FeatureRegistry(execution_tf="15m")

        try:
            # Try to get non-existent feature
            registry.get("nonexistent_feature")
            return TestResult(
                test_id=test_id,
                passed=False,
                message="Expected KeyError for invalid feature_id",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        except KeyError:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="Correctly raised KeyError for invalid feature_id",
                duration_ms=(time.perf_counter() - start) * 1000,
            )

    except Exception as e:
        return TestResult(
            test_id=test_id,
            passed=False,
            message=f"Unexpected error: {e}",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


def test_invalid_anchor_tf() -> TestResult:
    """T0_005: Invalid anchor_tf value fails."""
    test_id = "T0_005"
    start = time.perf_counter()

    try:
        from src.backtest.runtime.timeframe import tf_minutes

        try:
            # Invalid timeframe
            tf_minutes("invalid_tf")
            return TestResult(
                test_id=test_id,
                passed=False,
                message="Expected error for invalid anchor_tf",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        except (ValueError, KeyError) as e:
            return TestResult(
                test_id=test_id,
                passed=True,
                message=f"Correctly rejected invalid anchor_tf: {type(e).__name__}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )

    except Exception as e:
        return TestResult(
            test_id=test_id,
            passed=False,
            message=f"Unexpected error: {e}",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


def test_invalid_duration() -> TestResult:
    """T0_006: Invalid duration format fails."""
    test_id = "T0_006"
    start = time.perf_counter()

    try:
        from src.backtest.rules.dsl_nodes import duration_to_bars

        try:
            # Invalid duration format
            duration_to_bars("invalid")
            return TestResult(
                test_id=test_id,
                passed=False,
                message="Expected error for invalid duration format",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        except ValueError:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="Correctly rejected invalid duration format",
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
    result = run_all()
    print(f"Tier 0: {'PASS' if result.passed else 'FAIL'}")
    print(f"  Tests: {result.passed_count}/{result.total_count}")
    for test in result.tests:
        status = "PASS" if test.passed else "FAIL"
        print(f"  {status}: {test.test_id} - {test.message}")
