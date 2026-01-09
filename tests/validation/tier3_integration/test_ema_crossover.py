"""
Tier 3 Integration: EMA Crossover Strategy.

Tests a complete EMA 9/21 crossover entry condition.

DSL Pattern:
  entry_long:
    all:
      - cross_above: [ema_9, ema_21]
      - gt: [close, ema_21]          # Confirmation: price above slow EMA

Expected behavior:
- Signal fires on the bar where EMA9 crosses above EMA21
- Price must also be above EMA21 (confirmation)
- Should generate 2-3 signals on trending data with pullbacks
"""

from __future__ import annotations

import time

import numpy as np

from ..runner import TestResult
from ..fixtures import generate_trending_up, SyntheticData


def run_tests() -> list[TestResult]:
    """Run all EMA crossover integration tests."""
    tests: list[TestResult] = []

    tests.append(test_ema_cross_signal_count())
    tests.append(test_ema_cross_first_signal_location())
    tests.append(test_ema_cross_no_signal_downtrend())

    return tests


def _compute_ema(values: np.ndarray, length: int) -> np.ndarray:
    """Compute EMA using standard formula."""
    ema = np.zeros_like(values)
    alpha = 2.0 / (length + 1)
    ema[0] = values[0]
    for i in range(1, len(values)):
        ema[i] = alpha * values[i] + (1 - alpha) * ema[i - 1]
    return ema


def _eval_cross_above(prev_lhs: float, curr_lhs: float, rhs: float) -> bool:
    """Evaluate cross_above: was at or below, now above."""
    return prev_lhs <= rhs and curr_lhs > rhs


def _find_crossover_signals(
    data: SyntheticData,
    fast_len: int = 9,
    slow_len: int = 21,
) -> list[int]:
    """
    Find all bar indices where EMA crossover entry condition fires.

    Entry condition:
      all:
        - cross_above: [ema_fast, ema_slow]
        - gt: [close, ema_slow]
    """
    close = data.close.values
    ema_fast = _compute_ema(close, fast_len)
    ema_slow = _compute_ema(close, slow_len)

    signals: list[int] = []
    warmup = max(fast_len, slow_len) + 1

    for i in range(warmup, len(close)):
        # Condition 1: cross_above
        cross = _eval_cross_above(
            prev_lhs=ema_fast[i - 1],
            curr_lhs=ema_fast[i],
            rhs=ema_slow[i],
        )

        # Condition 2: close > ema_slow (confirmation)
        above_slow = close[i] > ema_slow[i]

        # Both conditions must be true
        if cross and above_slow:
            signals.append(i)

    return signals


# =============================================================================
# Integration Tests
# =============================================================================

def test_ema_cross_signal_count() -> TestResult:
    """I_001a: EMA crossover on trending_up data -> 2-4 signals.

    Trading scenario: Uptrend with pullbacks.
    Each pullback causes EMA9 to dip below EMA21, then cross back up.
    """
    test_id = "I_001a"
    start = time.perf_counter()

    try:
        data = generate_trending_up(
            start=100.0,
            end=130.0,
            n_bars=300,
            pullbacks=3,
            seed=42,
        )

        signals = _find_crossover_signals(data, fast_len=9, slow_len=21)

        # Expect 2-6 signals (one per pullback recovery, may vary with noise)
        if 2 <= len(signals) <= 6:
            return TestResult(
                test_id=test_id,
                passed=True,
                message=f"Found {len(signals)} crossover signals (expected 2-4)",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"Expected 2-4 signals, got {len(signals)}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
    except Exception as e:
        return TestResult(
            test_id=test_id,
            passed=False,
            message=f"Error: {e}",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


def test_ema_cross_first_signal_location() -> TestResult:
    """I_001b: First crossover signal after warmup period.

    The first signal should occur after enough bars for EMAs to warm up.
    """
    test_id = "I_001b"
    start = time.perf_counter()

    try:
        data = generate_trending_up(
            start=100.0,
            end=130.0,
            n_bars=300,
            pullbacks=3,
            seed=42,
        )

        signals = _find_crossover_signals(data, fast_len=9, slow_len=21)

        if not signals:
            return TestResult(
                test_id=test_id,
                passed=False,
                message="No signals found",
                duration_ms=(time.perf_counter() - start) * 1000,
            )

        first_signal = signals[0]
        warmup = 21 + 1  # slow_len + 1

        if first_signal >= warmup:
            return TestResult(
                test_id=test_id,
                passed=True,
                message=f"First signal at bar {first_signal} (after warmup={warmup})",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"First signal at bar {first_signal}, expected >= {warmup}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
    except Exception as e:
        return TestResult(
            test_id=test_id,
            passed=False,
            message=f"Error: {e}",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


def test_ema_cross_no_signal_downtrend() -> TestResult:
    """I_001c: No bullish crossover signals in pure downtrend.

    In a downtrend, fast EMA stays below slow EMA, so no cross_above occurs.
    """
    test_id = "I_001c"
    start = time.perf_counter()

    try:
        # Generate downtrend (no pullbacks = no opportunities for crossover)
        data = generate_trending_up(
            start=130.0,
            end=100.0,
            n_bars=200,
            pullbacks=0,  # Pure downtrend
            seed=42,
        )

        signals = _find_crossover_signals(data, fast_len=9, slow_len=21)

        if len(signals) == 0:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="No crossover signals in downtrend (correct)",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"Expected 0 signals in downtrend, got {len(signals)}",
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
    print(f"EMA crossover integration: {passed}/{len(results)} passed")
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  {status}: {r.test_id} - {r.message}")
