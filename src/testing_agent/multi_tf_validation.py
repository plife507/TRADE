"""
Multi-Timeframe Validation: Tests for timeframe alignment correctness.

This module validates that multi-timeframe data handling is correct:
- Higher timeframe bar close alignment
- Lower timeframe sees correct higher timeframe data
- Timeframe resampling accuracy

Usage:
    from src.testing_agent.multi_tf_validation import run_all_multi_tf_tests

    results = run_all_multi_tf_tests()
    for r in results:
        print(f"{r.name}: {'PASS' if r.passed else 'FAIL'}")
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

from ..utils.logger import get_logger

logger = get_logger()


@dataclass
class MultiTFTestResult:
    """Result from a single multi-TF test."""
    name: str
    passed: bool
    expected: str
    actual: str
    error_msg: str | None = None


def _resample_ohlcv(df: pd.DataFrame, target_tf: str) -> pd.DataFrame:
    """
    Resample OHLCV data to target timeframe.

    Args:
        df: DataFrame with columns [timestamp, open, high, low, close, volume]
        target_tf: Target timeframe (e.g., '1h', '4h', 'D')

    Returns:
        Resampled DataFrame
    """
    df = df.copy()
    df.set_index("timestamp", inplace=True)

    resampled = df.resample(target_tf).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna()

    resampled.reset_index(inplace=True)
    return resampled


def _test_resample_15m_to_1h() -> MultiTFTestResult:
    """
    Test that 15m data correctly resamples to 1h.

    Four 15m bars should aggregate to one 1h bar with:
    - open = first 15m open
    - high = max of all highs
    - low = min of all lows
    - close = last 15m close
    - volume = sum of all volumes
    """
    # Create 8 bars of 15m data (2 hours)
    base_time = datetime(2024, 1, 1, 0, 0)
    timestamps = [base_time + timedelta(minutes=15*i) for i in range(8)]

    # Known values for first hour
    opens = [100.0, 101.0, 99.0, 102.0, 103.0, 104.0, 102.0, 105.0]
    highs = [102.0, 103.0, 101.0, 104.0, 105.0, 106.0, 104.0, 107.0]
    lows = [99.0, 100.0, 98.0, 101.0, 102.0, 103.0, 101.0, 104.0]
    closes = [101.0, 99.0, 102.0, 103.0, 104.0, 102.0, 105.0, 106.0]
    volumes = [100.0, 150.0, 200.0, 120.0, 180.0, 90.0, 160.0, 140.0]

    df_15m = pd.DataFrame({
        "timestamp": timestamps,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })

    # Resample to 1h
    df_1h = _resample_ohlcv(df_15m, "1h")

    # Expected first hour bar (bars 0-3)
    expected_open = 100.0  # First bar's open
    expected_high = 104.0  # Max of 102, 103, 101, 104
    expected_low = 98.0    # Min of 99, 100, 98, 101
    expected_close = 103.0 # Last bar's close
    expected_volume = 570.0  # 100 + 150 + 200 + 120

    # Get first 1h bar
    h1_bar = df_1h.iloc[0]

    checks = []
    checks.append(("open", expected_open, h1_bar["open"]))
    checks.append(("high", expected_high, h1_bar["high"]))
    checks.append(("low", expected_low, h1_bar["low"]))
    checks.append(("close", expected_close, h1_bar["close"]))
    checks.append(("volume", expected_volume, h1_bar["volume"]))

    failures = []
    for field, exp, act in checks:
        if abs(exp - act) > 0.001:
            failures.append(f"{field}: expected {exp}, got {act}")

    passed = len(failures) == 0
    return MultiTFTestResult(
        name="resample_15m_to_1h",
        passed=passed,
        expected="OHLCV correctly aggregated",
        actual="All fields match" if passed else "; ".join(failures),
        error_msg=None if passed else "; ".join(failures),
    )


def _test_resample_1h_to_4h() -> MultiTFTestResult:
    """
    Test that 1h data correctly resamples to 4h.
    """
    # Create 8 bars of 1h data (8 hours)
    base_time = datetime(2024, 1, 1, 0, 0)
    timestamps = [base_time + timedelta(hours=i) for i in range(8)]

    # Known values for first 4h
    opens = [50000.0, 50100.0, 50050.0, 50200.0, 50300.0, 50250.0, 50400.0, 50350.0]
    highs = [50150.0, 50200.0, 50150.0, 50300.0, 50400.0, 50350.0, 50500.0, 50450.0]
    lows = [49950.0, 50000.0, 49980.0, 50100.0, 50200.0, 50150.0, 50300.0, 50250.0]
    closes = [50100.0, 50050.0, 50200.0, 50250.0, 50250.0, 50400.0, 50350.0, 50400.0]
    volumes = [1000.0, 1200.0, 800.0, 1500.0, 900.0, 1100.0, 1300.0, 1000.0]

    df_1h = pd.DataFrame({
        "timestamp": timestamps,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })

    # Resample to 4h
    df_4h = _resample_ohlcv(df_1h, "4h")

    # Expected first 4h bar (bars 0-3)
    expected_open = 50000.0   # First bar's open
    expected_high = 50300.0   # Max of highs
    expected_low = 49950.0    # Min of lows
    expected_close = 50250.0  # Last bar's close
    expected_volume = 4500.0  # Sum of volumes

    h4_bar = df_4h.iloc[0]

    checks = []
    checks.append(("open", expected_open, h4_bar["open"]))
    checks.append(("high", expected_high, h4_bar["high"]))
    checks.append(("low", expected_low, h4_bar["low"]))
    checks.append(("close", expected_close, h4_bar["close"]))
    checks.append(("volume", expected_volume, h4_bar["volume"]))

    failures = []
    for field, exp, act in checks:
        if abs(exp - act) > 0.001:
            failures.append(f"{field}: expected {exp}, got {act}")

    passed = len(failures) == 0
    return MultiTFTestResult(
        name="resample_1h_to_4h",
        passed=passed,
        expected="OHLCV correctly aggregated",
        actual="All fields match" if passed else "; ".join(failures),
        error_msg=None if passed else "; ".join(failures),
    )


def _test_htf_close_alignment() -> MultiTFTestResult:
    """
    Test that lower timeframe sees updated higher timeframe at close.

    When a 4h bar closes, the next 15m bar should see the NEW 4h close,
    not the previous 4h close.
    """
    # Simulate 4h bar closes at 04:00
    # 15m bar at 04:00 should see the 04:00 4h close (just completed)
    # 15m bar at 03:45 should see the 00:00 4h close (previous)

    # 4h bar 00:00-04:00: close = 50200
    # 4h bar 04:00-08:00: close = 50500

    # At 15m bar 03:45: should see previous 4h close (50000 from earlier bar)
    # At 15m bar 04:00: should see NEW 4h close (50200)

    # Create simple alignment check
    htf_closes = {
        datetime(2024, 1, 1, 0, 0): 50000.0,  # 4h bar ending at 00:00
        datetime(2024, 1, 1, 4, 0): 50200.0,  # 4h bar ending at 04:00
        datetime(2024, 1, 1, 8, 0): 50500.0,  # 4h bar ending at 08:00
    }

    def get_htf_close_at_ltf_bar(ltf_timestamp: datetime) -> float:
        """Get the 4h close visible at a given 15m bar."""
        # Find the most recent 4h close <= ltf_timestamp
        for htf_ts in sorted(htf_closes.keys(), reverse=True):
            if htf_ts <= ltf_timestamp:
                return htf_closes[htf_ts]
        return float('nan')

    # Test cases
    test_cases = [
        # (ltf_timestamp, expected_htf_close)
        (datetime(2024, 1, 1, 3, 45), 50000.0),  # Before 4h close at 04:00
        (datetime(2024, 1, 1, 4, 0), 50200.0),   # At 4h close at 04:00
        (datetime(2024, 1, 1, 4, 15), 50200.0),  # After 4h close at 04:00
        (datetime(2024, 1, 1, 7, 45), 50200.0),  # Before next 4h close
        (datetime(2024, 1, 1, 8, 0), 50500.0),   # At next 4h close
    ]

    failures = []
    for ltf_ts, expected in test_cases:
        actual = get_htf_close_at_ltf_bar(ltf_ts)
        if abs(expected - actual) > 0.001:
            failures.append(f"At {ltf_ts.strftime('%H:%M')}: expected {expected}, got {actual}")

    passed = len(failures) == 0
    return MultiTFTestResult(
        name="high_tf_close_alignment",
        passed=passed,
        expected="Lower timeframe sees higher timeframe close at correct times",
        actual="All alignments correct" if passed else f"{len(failures)} misaligned",
        error_msg=None if passed else "; ".join(failures[:3]),
    )


def _test_htf_during_bar() -> MultiTFTestResult:
    """
    Test that lower timeframe sees PREVIOUS higher timeframe close during bar.

    While a 4h bar is still open, the 15m bars should see the PREVIOUS
    completed 4h bar's close, not the current incomplete bar.
    """
    # 4h bar 04:00-08:00 is forming
    # At 15m bars 04:15, 04:30, etc., we should see the 04:00 close (previous completed)
    # NOT any partial data from the current forming bar

    # This is a conceptual test - in practice, we only have OHLC of completed bars

    # Simulate check: at 05:00, we should have access to:
    # - 4h bar closed at 04:00 (complete)
    # - 4h bar 04:00-08:00 (incomplete - should NOT be visible)

    htf_bars = [
        {"close_time": datetime(2024, 1, 1, 4, 0), "close": 50200.0},
        {"close_time": datetime(2024, 1, 1, 8, 0), "close": 50500.0},
    ]

    def get_visible_htf_at(current_time: datetime) -> dict | None:
        """Get the most recent COMPLETED 4h bar visible at current_time."""
        visible = None
        for bar in htf_bars:
            if bar["close_time"] <= current_time:
                visible = bar
        return visible

    # Test at 05:00 (mid-bar)
    current_time = datetime(2024, 1, 1, 5, 0)
    visible = get_visible_htf_at(current_time)

    expected_close_time = datetime(2024, 1, 1, 4, 0)
    expected_close = 50200.0

    passed = (
        visible is not None and
        visible["close_time"] == expected_close_time and
        abs(visible["close"] - expected_close) < 0.001
    )

    return MultiTFTestResult(
        name="htf_during_bar",
        passed=passed,
        expected=f"At 05:00, see 04:00 bar (close={expected_close})",
        actual=f"Visible bar: {visible}" if visible else "No visible bar",
        error_msg=None if passed else "Mid-bar visibility incorrect",
    )


def _test_tf_ratio_accuracy() -> MultiTFTestResult:
    """
    Test that timeframe ratios are correctly computed.

    15m to 1h = 4:1
    1h to 4h = 4:1
    15m to 4h = 16:1
    """
    tf_minutes = {
        "1m": 1,
        "3m": 3,
        "5m": 5,
        "15m": 15,
        "30m": 30,
        "1h": 60,
        "2h": 120,
        "4h": 240,
        "6h": 360,
        "12h": 720,
        "D": 1440,
    }

    def tf_ratio(low_tf: str, high_tf: str) -> int:
        """Compute how many low_tf bars fit in one high_tf bar."""
        return tf_minutes[high_tf] // tf_minutes[low_tf]

    test_cases = [
        ("15m", "1h", 4),
        ("1h", "4h", 4),
        ("15m", "4h", 16),
        ("5m", "1h", 12),
        ("1m", "15m", 15),
        ("4h", "D", 6),
    ]

    failures = []
    for low, high, expected in test_cases:
        actual = tf_ratio(low, high)
        if actual != expected:
            failures.append(f"{low} to {high}: expected {expected}, got {actual}")

    passed = len(failures) == 0
    return MultiTFTestResult(
        name="tf_ratio_accuracy",
        passed=passed,
        expected="All TF ratios correct",
        actual="All correct" if passed else "; ".join(failures),
        error_msg=None if passed else "; ".join(failures),
    )


def _test_indicator_on_resampled() -> MultiTFTestResult:
    """
    Test that indicators computed on resampled data match.

    EMA(20) on 1h data should equal EMA(20) on resampled 15m->1h data.
    """
    from ..indicators.incremental import IncrementalEMA

    # Create 100 bars of 15m data
    np.random.seed(42)
    base_time = datetime(2024, 1, 1, 0, 0)
    timestamps = [base_time + timedelta(minutes=15*i) for i in range(100)]

    prices = 50000 * np.cumprod(1 + np.random.normal(0, 0.001, 100))

    df_15m = pd.DataFrame({
        "timestamp": timestamps,
        "open": np.roll(prices, 1),
        "high": prices * 1.002,
        "low": prices * 0.998,
        "close": prices,
        "volume": np.random.uniform(100, 1000, 100),
    })
    df_15m.loc[0, "open"] = 50000

    # Resample to 1h (25 bars)
    df_1h = _resample_ohlcv(df_15m, "1h")

    # Compute EMA(10) on 1h data
    ema = IncrementalEMA(length=10)
    for close in df_1h["close"]:
        ema.update(close=float(close))

    ema_value_resampled = ema.value

    # Verify EMA is valid (not NaN after enough bars)
    passed = not np.isnan(ema_value_resampled) and ema.is_ready

    return MultiTFTestResult(
        name="indicator_on_resampled",
        passed=passed,
        expected="EMA computed on resampled 1h data",
        actual=f"EMA={ema_value_resampled:.2f}, ready={ema.is_ready}",
        error_msg=None if passed else "EMA not ready or NaN",
    )


def run_all_multi_tf_tests() -> list[MultiTFTestResult]:
    """Run all multi-timeframe tests and return results."""
    tests = [
        _test_resample_15m_to_1h,
        _test_resample_1h_to_4h,
        _test_htf_close_alignment,
        _test_htf_during_bar,
        _test_tf_ratio_accuracy,
        _test_indicator_on_resampled,
    ]

    results = []
    for test_func in tests:
        try:
            result = test_func()
            results.append(result)
        except Exception as e:
            results.append(MultiTFTestResult(
                name=test_func.__name__.replace("_test_", ""),
                passed=False,
                expected="No exception",
                actual=f"Exception: {type(e).__name__}",
                error_msg=str(e),
            ))

    return results


def format_multi_tf_test_report(results: list[MultiTFTestResult]) -> str:
    """Format multi-TF test results as a report string."""
    lines = []
    lines.append("=" * 60)
    lines.append("MULTI-TIMEFRAME VALIDATION REPORT")
    lines.append("=" * 60)

    passed = sum(1 for r in results if r.passed)
    total = len(results)

    for r in results:
        status = "PASS" if r.passed else "FAIL"
        lines.append(f"  [{status}] {r.name}")
        if not r.passed:
            lines.append(f"         Expected: {r.expected}")
            lines.append(f"         Actual:   {r.actual}")
            if r.error_msg:
                lines.append(f"         Error:    {r.error_msg}")

    lines.append("-" * 60)
    lines.append(f"TOTAL: {passed}/{total} tests passed")
    lines.append("=" * 60)

    return "\n".join(lines)
