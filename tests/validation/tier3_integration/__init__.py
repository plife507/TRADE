"""Tier 3: Integration tests - end-to-end signal generation with composed DSL conditions."""

from ..runner import TierResult, TierName, TestResult
import time


def run_all_integration_tests() -> TierResult:
    """Run all integration tests and return combined result."""
    from . import (
        test_ema_crossover,
        test_rsi_momentum,
        test_fib_entry,
        test_mtf_trend,
    )

    all_tests: list[TestResult] = []
    start = time.perf_counter()

    # I_001: EMA Crossover Strategy
    all_tests.extend(test_ema_crossover.run_tests())

    # I_002: RSI Momentum Strategy
    all_tests.extend(test_rsi_momentum.run_tests())

    # I_003: Fibonacci Entry Strategy
    all_tests.extend(test_fib_entry.run_tests())

    # I_004: Multi-TF Trend Strategy
    all_tests.extend(test_mtf_trend.run_tests())

    duration_ms = (time.perf_counter() - start) * 1000
    passed = all(t.passed for t in all_tests)

    return TierResult(
        tier=TierName.TIER3,
        passed=passed,
        tests=all_tests,
        duration_ms=duration_ms,
    )


__all__ = ["run_all_integration_tests"]
