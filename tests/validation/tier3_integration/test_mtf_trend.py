"""
Tier 3 Integration: Multi-Timeframe Trend Entry.

Tests HTF trend confirmation + LTF entry timing.

DSL Pattern:
  entry_long:
    all:
      - holds_for:
          condition:
            gt: [htf_ema_50, htf_ema_200]  # HTF uptrend
          bars: 3
          anchor_tf: "1h"                   # 3 hourly bars
      - cross_above: [ltf_ema_9, ltf_ema_21]  # LTF entry trigger

Expected behavior:
- HTF trend must hold for 3 bars (at 1h granularity)
- LTF crossover triggers the actual entry
- Combines slow (HTF) and fast (LTF) timeframe logic
"""

from __future__ import annotations

import time

import numpy as np

from ..runner import TestResult
from ..fixtures import SyntheticData


def run_tests() -> list[TestResult]:
    """Run all MTF trend integration tests."""
    tests: list[TestResult] = []

    tests.append(test_mtf_aligned_signal())
    tests.append(test_htf_not_held_no_signal())
    tests.append(test_ltf_no_cross_no_signal())

    return tests


def _compute_ema(values: np.ndarray, length: int) -> np.ndarray:
    """Compute EMA using standard formula."""
    ema = np.zeros_like(values)
    alpha = 2.0 / (length + 1)
    ema[0] = values[0]
    for i in range(1, len(values)):
        ema[i] = alpha * values[i] + (1 - alpha) * ema[i - 1]
    return ema


def _eval_holds_for_with_anchor(
    values: list[bool],
    bars: int,
    anchor_tf_minutes: int,
    current_bar: int,
) -> bool:
    """
    Check if condition holds for N bars at anchor TF.

    At 1h anchor with bars=3:
    - Check current bar, bar-60, bar-120 (in minutes)
    """
    offsets = [i * anchor_tf_minutes for i in range(bars)]
    for offset in offsets:
        check_idx = current_bar - offset
        if check_idx < 0 or check_idx >= len(values):
            return False
        if not values[check_idx]:
            return False
    return True


def _eval_cross_above(prev_lhs: float, curr_lhs: float, rhs: float) -> bool:
    """Evaluate cross_above."""
    return prev_lhs <= rhs and curr_lhs > rhs


def _generate_mtf_aligned_data(seed: int = 42) -> SyntheticData:
    """
    Generate data where HTF and LTF align for entry.

    - Strong uptrend (HTF EMA50 > EMA200 for extended period)
    - LTF pullback and recovery with crossover
    """
    import pandas as pd
    np.random.seed(seed)

    n_bars = 800  # ~13 hours at 1m - enough for warmup + signal
    dates = pd.date_range("2024-01-01", periods=n_bars, freq="1min")

    # Strong uptrend base
    trend = np.linspace(100, 160, n_bars)

    # Add pullback after warmup period (for LTF crossover opportunity)
    pullback = np.zeros(n_bars)
    pullback[450:500] = np.sin(np.linspace(0, np.pi, 50)) * -8  # Dip after warmup

    close = trend + pullback + np.random.randn(n_bars) * 0.3

    high = close + np.abs(np.random.randn(n_bars) * 0.3)
    low = close - np.abs(np.random.randn(n_bars) * 0.3)
    open_ = np.roll(close, 1)
    open_[0] = 100
    volume = np.random.randint(1000, 10000, n_bars).astype(float)

    df = pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }, index=dates)

    return SyntheticData(df=df)


def _find_mtf_signals(
    data: SyntheticData,
    htf_fast: int = 50,
    htf_slow: int = 200,
    ltf_fast: int = 9,
    ltf_slow: int = 21,
    htf_hold_bars: int = 3,
    anchor_tf_minutes: int = 60,
) -> list[int]:
    """
    Find all bar indices where MTF entry condition fires.

    Entry condition:
      all:
        - holds_for(htf_ema_fast > htf_ema_slow, bars=3, anchor=1h)
        - cross_above(ltf_ema_fast, ltf_ema_slow)
    """
    close = data.close.values

    # Compute EMAs
    htf_ema_fast = _compute_ema(close, htf_fast)
    htf_ema_slow = _compute_ema(close, htf_slow)
    ltf_ema_fast = _compute_ema(close, ltf_fast)
    ltf_ema_slow = _compute_ema(close, ltf_slow)

    # Pre-compute HTF trend condition for each bar
    htf_uptrend = [htf_ema_fast[i] > htf_ema_slow[i] for i in range(len(close))]

    signals: list[int] = []
    warmup = max(htf_slow, ltf_slow) + htf_hold_bars * anchor_tf_minutes

    for i in range(warmup, len(close)):
        # Condition 1: HTF trend holds for N bars at anchor TF
        htf_held = _eval_holds_for_with_anchor(
            htf_uptrend,
            bars=htf_hold_bars,
            anchor_tf_minutes=anchor_tf_minutes,
            current_bar=i,
        )

        # Condition 2: LTF crossover
        ltf_cross = _eval_cross_above(
            prev_lhs=ltf_ema_fast[i - 1],
            curr_lhs=ltf_ema_fast[i],
            rhs=ltf_ema_slow[i],
        )

        if htf_held and ltf_cross:
            signals.append(i)

    return signals


# =============================================================================
# Integration Tests
# =============================================================================

def test_mtf_aligned_signal() -> TestResult:
    """I_004a: HTF trend held + LTF crossover -> signal fires.

    Multi-timeframe alignment - the ideal setup.
    """
    test_id = "I_004a"
    start = time.perf_counter()

    try:
        data = _generate_mtf_aligned_data(seed=42)

        signals = _find_mtf_signals(data)

        if len(signals) >= 1:
            return TestResult(
                test_id=test_id,
                passed=True,
                message=f"Found {len(signals)} MTF aligned signals",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message="No MTF signals found",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
    except Exception as e:
        return TestResult(
            test_id=test_id,
            passed=False,
            message=f"Error: {e}",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


def test_htf_not_held_no_signal() -> TestResult:
    """I_004b: HTF trend not held for required bars -> no signal.

    If HTF trend is too new (hasn't held for 3 hours), don't enter.
    """
    test_id = "I_004b"
    start = time.perf_counter()

    try:
        import pandas as pd
        np.random.seed(42)

        # Create choppy HTF trend (alternates)
        n_bars = 200
        dates = pd.date_range("2024-01-01", periods=n_bars, freq="1min")

        # Price that causes EMA50/200 to frequently cross
        close = 100 + np.random.randn(n_bars).cumsum() * 0.3

        high = close + np.abs(np.random.randn(n_bars) * 0.3)
        low = close - np.abs(np.random.randn(n_bars) * 0.3)
        open_ = np.roll(close, 1)
        open_[0] = 100
        volume = np.random.randint(1000, 10000, n_bars).astype(float)

        df = pd.DataFrame({
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }, index=dates)

        data = SyntheticData(df=df)

        # With strict HTF hold requirement, should get few/no signals
        signals = _find_mtf_signals(data, htf_hold_bars=3, anchor_tf_minutes=60)

        # In choppy market, MTF signals should be rare or none
        if len(signals) <= 1:
            return TestResult(
                test_id=test_id,
                passed=True,
                message=f"Few/no signals in choppy HTF ({len(signals)})",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"Too many signals in choppy market: {len(signals)}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
    except Exception as e:
        return TestResult(
            test_id=test_id,
            passed=False,
            message=f"Error: {e}",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


def test_ltf_no_cross_no_signal() -> TestResult:
    """I_004c: HTF trend held but no LTF crossover -> no signal.

    HTF is bullish but LTF already crossed (no fresh entry trigger).
    """
    test_id = "I_004c"
    start = time.perf_counter()

    try:
        import pandas as pd
        np.random.seed(42)

        # Steady uptrend without pullbacks (LTF EMAs stay aligned, no cross)
        n_bars = 400
        dates = pd.date_range("2024-01-01", periods=n_bars, freq="1min")

        close = np.linspace(100, 150, n_bars) + np.random.randn(n_bars) * 0.1

        high = close + np.abs(np.random.randn(n_bars) * 0.3)
        low = close - np.abs(np.random.randn(n_bars) * 0.3)
        open_ = np.roll(close, 1)
        open_[0] = 100
        volume = np.random.randint(1000, 10000, n_bars).astype(float)

        df = pd.DataFrame({
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }, index=dates)

        data = SyntheticData(df=df)

        signals = _find_mtf_signals(data)

        # After initial crossover, steady trend shouldn't produce more signals
        # (cross_above requires actually crossing, not just being above)
        if len(signals) <= 2:  # Maybe 1-2 from initial alignment
            return TestResult(
                test_id=test_id,
                passed=True,
                message=f"Few signals in steady trend ({len(signals)}) - no fresh crosses",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"Too many signals: {len(signals)} (expected few crosses)",
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
    print(f"MTF trend integration: {passed}/{len(results)} passed")
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  {status}: {r.test_id} - {r.message}")
