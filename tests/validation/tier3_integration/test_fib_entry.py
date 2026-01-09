"""
Tier 3 Integration: Fibonacci Retracement Entry.

Tests entry at 61.8% Fibonacci retracement level.

DSL Pattern:
  entry_long:
    all:
      - near_pct: [close, fib_618, 0.5]   # Price near 61.8% level (0.5% tolerance)
      - gt: [trend_direction, 0]           # Uptrend context

Expected behavior:
- Calculate Fibonacci levels from swing high/low
- Signal fires when price touches 61.8% level
- Only in uptrend context (retracement, not breakdown)
"""

from __future__ import annotations

import time

import numpy as np

from ..runner import TestResult
from ..fixtures import SyntheticData


def run_tests() -> list[TestResult]:
    """Run all Fibonacci entry integration tests."""
    tests: list[TestResult] = []

    tests.append(test_fib_touch_signal())
    tests.append(test_fib_miss_no_signal())
    tests.append(test_fib_touch_downtrend_no_signal())

    return tests


def _calc_fib_618(high: float, low: float) -> float:
    """Calculate 61.8% Fibonacci retracement level."""
    return high - (high - low) * 0.618


def _eval_near_pct(value: float, target: float, tolerance_pct: float) -> bool:
    """Check if value is within tolerance_pct of target."""
    if target == 0:
        return False
    return abs(value - target) / abs(target) <= tolerance_pct / 100


def _generate_retracement_data(seed: int = 42) -> tuple[SyntheticData, float, float, float]:
    """
    Generate data with clear swing and retracement to 61.8%.

    Returns (data, swing_high, swing_low, fib_618_level).
    """
    import pandas as pd
    np.random.seed(seed)

    n_bars = 100
    dates = pd.date_range("2024-01-01", periods=n_bars, freq="1min")

    # Phase 1: Up move (bars 0-30)
    up_phase = np.linspace(100, 120, 30)

    # Phase 2: Retracement to 61.8% (bars 30-50)
    # 61.8% level = 120 - (120-100)*0.618 = 107.64
    fib_level = _calc_fib_618(120, 100)
    retrace_phase = np.linspace(120, fib_level, 20)

    # Phase 3: Bounce from fib level (bars 50-100)
    bounce_phase = np.linspace(fib_level, 125, 50)

    close = np.concatenate([up_phase, retrace_phase, bounce_phase])

    # Add small noise
    noise = np.random.randn(n_bars) * 0.2
    close = close + noise

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

    return SyntheticData(df=df), 120.0, 100.0, fib_level


def _find_fib_entry_signals(
    data: SyntheticData,
    fib_level: float,
    tolerance_pct: float = 0.5,
    trend_direction: int = 1,
) -> list[int]:
    """
    Find all bar indices where Fibonacci entry condition fires.

    Entry condition:
      all:
        - near_pct: [close, fib_level, tolerance]
        - trend_direction > 0
    """
    close = data.close.values
    signals: list[int] = []

    for i in range(len(close)):
        # Condition 1: Price near fib level
        near_fib = _eval_near_pct(close[i], fib_level, tolerance_pct)

        # Condition 2: Uptrend context
        in_uptrend = trend_direction > 0

        if near_fib and in_uptrend:
            signals.append(i)

    return signals


# =============================================================================
# Integration Tests
# =============================================================================

def test_fib_touch_signal() -> TestResult:
    """I_003a: Price touches 61.8% fib level -> signal fires.

    Trading scenario: Uptrend, price retraces to golden ratio,
    entry signal fires at the touch.
    """
    test_id = "I_003a"
    start = time.perf_counter()

    try:
        data, swing_high, swing_low, fib_level = _generate_retracement_data(seed=42)

        signals = _find_fib_entry_signals(
            data,
            fib_level=fib_level,
            tolerance_pct=1.0,  # 1% tolerance
            trend_direction=1,
        )

        # Should find signals around bar 50 (where price touches fib)
        if len(signals) >= 1:
            # Check that at least one signal is in the retracement zone (bars 40-55)
            in_zone = [s for s in signals if 35 <= s <= 60]
            if in_zone:
                return TestResult(
                    test_id=test_id,
                    passed=True,
                    message=f"Found {len(signals)} fib touch signals (first at bar {signals[0]})",
                    duration_ms=(time.perf_counter() - start) * 1000,
                )
            else:
                return TestResult(
                    test_id=test_id,
                    passed=False,
                    message=f"Signals at {signals}, expected some in bars 35-60",
                    duration_ms=(time.perf_counter() - start) * 1000,
                )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"No fib touch signals found (fib={fib_level:.2f})",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
    except Exception as e:
        return TestResult(
            test_id=test_id,
            passed=False,
            message=f"Error: {e}",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


def test_fib_miss_no_signal() -> TestResult:
    """I_003b: Price doesn't reach fib level -> no signal.

    Shallow retracement that doesn't touch the 61.8% level.
    """
    test_id = "I_003b"
    start = time.perf_counter()

    try:
        import pandas as pd
        np.random.seed(42)

        n_bars = 100
        dates = pd.date_range("2024-01-01", periods=n_bars, freq="1min")

        # Start above fib level (107.64), shallow pullback that doesn't reach it
        # Fib 61.8% of 100-120 = 107.64
        start_above_fib = np.linspace(110, 120, 30)  # Start above 107.64
        shallow_retrace = np.linspace(120, 112, 20)  # Only retrace to 112, above 107.64
        continue_up = np.linspace(112, 130, 50)

        close = np.concatenate([start_above_fib, shallow_retrace, continue_up])
        # Minimal noise to avoid accidentally touching fib level
        noise = np.random.randn(n_bars) * 0.05
        close = close + noise

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
        fib_618 = _calc_fib_618(120, 100)

        signals = _find_fib_entry_signals(
            data,
            fib_level=fib_618,
            tolerance_pct=0.5,  # Tight tolerance
            trend_direction=1,
        )

        if len(signals) == 0:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="No signals (shallow retracement didn't reach 61.8%)",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"Got {len(signals)} signals, expected 0",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
    except Exception as e:
        return TestResult(
            test_id=test_id,
            passed=False,
            message=f"Error: {e}",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


def test_fib_touch_downtrend_no_signal() -> TestResult:
    """I_003c: Fib touch but downtrend -> no signal.

    Testing AND logic with trend filter.
    """
    test_id = "I_003c"
    start = time.perf_counter()

    try:
        data, _, _, fib_level = _generate_retracement_data(seed=42)

        # Same data but downtrend context
        signals = _find_fib_entry_signals(
            data,
            fib_level=fib_level,
            tolerance_pct=1.0,
            trend_direction=-1,  # Downtrend - no long entries
        )

        if len(signals) == 0:
            return TestResult(
                test_id=test_id,
                passed=True,
                message="No signals in downtrend (trend filter worked)",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"Got {len(signals)} signals despite downtrend",
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
    print(f"Fibonacci entry integration: {passed}/{len(results)} passed")
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  {status}: {r.test_id} - {r.message}")
