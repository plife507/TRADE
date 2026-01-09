"""Tier 4: Strategy smoke tests - full strategy simulation with synthetic data."""

from ..runner import TierResult, TierName, TestResult
import time


def run_all_smoke_tests() -> TierResult:
    """Run all smoke tests and return combined result."""
    from . import (
        test_ema_crossover_smoke,
        test_rsi_mean_reversion_smoke,
        test_breakout_volume_smoke,
        test_mtf_trend_smoke,
    )

    all_tests: list[TestResult] = []
    start = time.perf_counter()

    # S_001: EMA Crossover Smoke
    all_tests.extend(test_ema_crossover_smoke.run_tests())

    # S_002: RSI Mean Reversion Smoke
    all_tests.extend(test_rsi_mean_reversion_smoke.run_tests())

    # S_003: Breakout + Volume Smoke
    all_tests.extend(test_breakout_volume_smoke.run_tests())

    # S_004: MTF Trend Smoke
    all_tests.extend(test_mtf_trend_smoke.run_tests())

    duration_ms = (time.perf_counter() - start) * 1000
    passed = all(t.passed for t in all_tests)

    return TierResult(
        tier=TierName.TIER4,
        passed=passed,
        tests=all_tests,
        duration_ms=duration_ms,
    )


__all__ = ["run_all_smoke_tests"]
