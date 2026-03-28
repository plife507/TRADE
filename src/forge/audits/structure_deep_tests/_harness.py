"""
Test harness for deep structure detector verification.

Provides:
- TestCase / TestResult / TestReport dataclasses
- load_sol_1h() — SOLUSDT 1h data from DuckDB, sliced by regime
- compute_atr_array() — ATR calculation for bar sequences
- make_bar() — Quick BarData construction
- assert_close() / assert_eq() — Assertion helpers with messages
- run_test_module() — Execute a list of test functions, collect results
"""

from __future__ import annotations

import math
import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
import pandas as pd

from src.structures.base import BarData

# ---------------------------------------------------------------------------
# Regime definitions — SOLUSDT 1h date ranges
# Data available: 2025-04-02 to 2026-02-21
# Original TODO regimes adjusted to fit available data window
# ---------------------------------------------------------------------------

REGIMES: dict[str, tuple[str, str]] = {
    # Clean rally — strong uptrend, clear swings
    "BULL": ("2025-07-14", "2025-07-27"),
    # Strong sell-off (adjusted: original Feb 24-Mar 2 had no data)
    "BEAR": ("2025-11-10", "2025-11-23"),
    # Tight range, low net movement
    "CONSOLIDATION": ("2025-09-15", "2025-09-21"),
    # Whipsaw, high range vs low net (adjusted: original Jan 27-Feb 2 had no data)
    "CHOPPY": ("2025-12-01", "2025-12-14"),
    # Trend reversal
    "BULL_BEAR": ("2025-09-08", "2025-10-12"),
    # V-reversal
    "BEAR_BULL": ("2025-04-02", "2025-04-20"),
}


# ---------------------------------------------------------------------------
# Test dataclasses
# ---------------------------------------------------------------------------


@dataclass
class TestResult:
    """Result of a single test case."""

    test_id: str
    category: str  # MATH, ALGORITHM, EDGE, PARITY, REAL
    description: str
    passed: bool
    message: str = ""
    duration_ms: float = 0.0


@dataclass
class TestReport:
    """Aggregated report for one detector module."""

    detector_name: str
    results: list[TestResult] = field(default_factory=list)
    total_duration_ms: float = 0.0

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    @property
    def total(self) -> int:
        return len(self.results)

    def summary_line(self) -> str:
        status = "PASS" if self.failed == 0 else "FAIL"
        return (
            f"[{status}] {self.detector_name}: "
            f"{self.passed}/{self.total} passed "
            f"({self.total_duration_ms:.0f}ms)"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "detector": self.detector_name,
            "passed": self.passed,
            "failed": self.failed,
            "total": self.total,
            "duration_ms": round(self.total_duration_ms, 1),
            "results": [
                {
                    "test_id": r.test_id,
                    "category": r.category,
                    "passed": r.passed,
                    "message": r.message,
                    "duration_ms": round(r.duration_ms, 1),
                }
                for r in self.results
            ],
        }


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

_sol_1h_cache: pd.DataFrame | None = None


def load_sol_1h(regime: str | None = None) -> pd.DataFrame:
    """
    Load SOLUSDT 1h candles from DuckDB, optionally filtered by regime.

    Returns DataFrame with columns: timestamp, open, high, low, close, volume.
    Index is reset (0-based integer).

    Args:
        regime: One of REGIMES keys, or None for full dataset.

    Returns:
        DataFrame with OHLCV data.
    """
    global _sol_1h_cache

    if _sol_1h_cache is None:
        from src.data.historical_data_store import get_ohlcv

        _sol_1h_cache = get_ohlcv("SOLUSDT", "1h", period="12M")

    df = _sol_1h_cache.copy()

    if regime is not None:
        if regime not in REGIMES:
            raise ValueError(f"Unknown regime {regime!r}. Valid: {sorted(REGIMES)}")
        start_str, end_str = REGIMES[regime]
        start = pd.Timestamp(start_str)
        end = pd.Timestamp(end_str + " 23:59:59")
        mask = (df["timestamp"] >= start) & (df["timestamp"] <= end)
        df = pd.DataFrame(df.loc[mask]).reset_index(drop=True)

        if len(df) == 0:
            raise RuntimeError(
                f"No SOLUSDT 1h data for regime {regime} "
                f"({start_str} to {end_str}). Check DuckDB."
            )

    return df


def df_to_ohlcv_dict(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """Convert DataFrame to dict of numpy arrays (for vectorized refs)."""
    return {
        "open": df["open"].values.astype(float),
        "high": df["high"].values.astype(float),
        "low": df["low"].values.astype(float),
        "close": df["close"].values.astype(float),
        "volume": df["volume"].values.astype(float),
    }


# ---------------------------------------------------------------------------
# ATR computation
# ---------------------------------------------------------------------------


def compute_atr_array(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    period: int = 14,
) -> np.ndarray:
    """
    Compute ATR array using Wilder's smoothing (RMA).

    Args:
        highs: High prices array.
        lows: Low prices array.
        closes: Close prices array.
        period: ATR period (default 14).

    Returns:
        Array of ATR values (NaN for first period-1 bars).
    """
    n = len(highs)
    tr = np.empty(n)
    atr = np.full(n, np.nan)

    # True Range
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )

    # Wilder's smoothing (RMA)
    if n >= period:
        atr[period - 1] = np.mean(tr[:period])
        alpha = 1.0 / period
        for i in range(period, n):
            atr[i] = atr[i - 1] * (1 - alpha) + tr[i] * alpha

    return atr


# ---------------------------------------------------------------------------
# Bar construction helpers
# ---------------------------------------------------------------------------


def make_bar(
    idx: int,
    open: float,
    high: float,
    low: float,
    close: float,
    volume: float = 1000.0,
    indicators: dict[str, float] | None = None,
) -> BarData:
    """
    Create a BarData instance for testing.

    Args:
        idx: Bar index.
        open/high/low/close: OHLC prices.
        volume: Volume (default 1000).
        indicators: Optional indicator values dict.

    Returns:
        BarData instance.
    """
    return BarData(
        idx=idx,
        open=open,
        high=high,
        low=low,
        close=close,
        volume=volume,
        indicators=indicators or {},
    )


def make_bars_from_df(
    df: pd.DataFrame,
    atr_array: np.ndarray | None = None,
    atr_key: str = "atr_14",
) -> list[BarData]:
    """
    Convert DataFrame rows to list of BarData.

    Args:
        df: DataFrame with open, high, low, close, volume columns.
        atr_array: Optional ATR values to include as indicator.
        atr_key: Indicator key name for ATR.

    Returns:
        List of BarData instances.
    """
    bars: list[BarData] = []
    for i in range(len(df)):
        indicators: dict[str, float] = {}
        if atr_array is not None and not math.isnan(atr_array[i]):
            indicators[atr_key] = float(atr_array[i])
        bars.append(
            BarData(
                idx=i,
                open=float(df["open"].iloc[i]),
                high=float(df["high"].iloc[i]),
                low=float(df["low"].iloc[i]),
                close=float(df["close"].iloc[i]),
                volume=float(df["volume"].iloc[i]),
                indicators=indicators,
            )
        )
    return bars


# ---------------------------------------------------------------------------
# Swing helper for dependent detectors
# ---------------------------------------------------------------------------


def make_swing_fed(
    bars: list[BarData],
    left: int = 5,
    right: int = 5,
) -> "IncrementalSwing":
    """
    Create a swing detector and feed all bars through it.

    Useful for Phase 2+ detectors that depend on swing.

    Returns:
        Fully-fed IncrementalSwing instance.
    """
    from src.structures.detectors.swing import IncrementalSwing

    sw = IncrementalSwing({"left": left, "right": right, "mode": "fractal"}, deps=None)
    for bar in bars:
        sw.update(bar.idx, bar)
    return sw


# Type alias for lazy import
IncrementalSwing = Any  # Avoids circular import at module level


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------


class TestFailure(Exception):
    """Raised by assertion helpers to signal test failure."""

    pass


def assert_close(
    actual: float,
    expected: float,
    tol: float = 1e-6,
    msg: str = "",
) -> None:
    """Assert two floats are close within tolerance."""
    if math.isnan(expected) and math.isnan(actual):
        return  # Both NaN is a match
    if math.isnan(expected) or math.isnan(actual):
        raise TestFailure(
            f"NaN mismatch: actual={actual}, expected={expected}"
            + (f" — {msg}" if msg else "")
        )
    if abs(actual - expected) > tol:
        raise TestFailure(
            f"Value mismatch: actual={actual}, expected={expected}, "
            f"diff={abs(actual - expected):.8f}, tol={tol}"
            + (f" — {msg}" if msg else "")
        )


def assert_eq(actual: Any, expected: Any, msg: str = "") -> None:
    """Assert exact equality."""
    if actual != expected:
        raise TestFailure(
            f"Expected {expected!r}, got {actual!r}"
            + (f" — {msg}" if msg else "")
        )


def assert_true(condition: bool, msg: str = "") -> None:
    """Assert condition is True."""
    if not condition:
        raise TestFailure(f"Condition is False" + (f" — {msg}" if msg else ""))


def assert_gt(actual: float, threshold: float, msg: str = "") -> None:
    """Assert actual > threshold."""
    if not actual > threshold:
        raise TestFailure(
            f"Expected {actual} > {threshold}"
            + (f" — {msg}" if msg else "")
        )


def assert_lt(actual: float, threshold: float, msg: str = "") -> None:
    """Assert actual < threshold."""
    if not actual < threshold:
        raise TestFailure(
            f"Expected {actual} < {threshold}"
            + (f" — {msg}" if msg else "")
        )


def assert_nan(actual: float, msg: str = "") -> None:
    """Assert value is NaN."""
    if not math.isnan(actual):
        raise TestFailure(
            f"Expected NaN, got {actual}" + (f" — {msg}" if msg else "")
        )


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

# Type alias for test functions
TestFunc = Callable[[], None]


@dataclass
class TestCase:
    """A single named test case."""

    test_id: str
    category: str  # MATH, ALGORITHM, EDGE, PARITY, REAL
    description: str
    func: TestFunc


def run_test_module(
    detector_name: str,
    tests: list[TestCase],
    verbose: bool = False,
) -> TestReport:
    """
    Execute a list of test cases and collect results.

    Args:
        detector_name: Name of the detector being tested.
        tests: List of TestCase instances.
        verbose: If True, print each test result.

    Returns:
        TestReport with all results.
    """
    report = TestReport(detector_name=detector_name)
    t0 = time.perf_counter()

    for tc in tests:
        t_start = time.perf_counter()
        try:
            tc.func()
            duration = (time.perf_counter() - t_start) * 1000
            result = TestResult(
                test_id=tc.test_id,
                category=tc.category,
                description=tc.description,
                passed=True,
                message="OK",
                duration_ms=duration,
            )
        except TestFailure as e:
            duration = (time.perf_counter() - t_start) * 1000
            result = TestResult(
                test_id=tc.test_id,
                category=tc.category,
                description=tc.description,
                passed=False,
                message=str(e),
                duration_ms=duration,
            )
        except Exception as e:
            duration = (time.perf_counter() - t_start) * 1000
            tb = traceback.format_exc()
            result = TestResult(
                test_id=tc.test_id,
                category=tc.category,
                description=tc.description,
                passed=False,
                message=f"EXCEPTION: {e}\n{tb}",
                duration_ms=duration,
            )

        report.results.append(result)

        if verbose:
            icon = "PASS" if result.passed else "FAIL"
            print(
                f"  [{icon}] {tc.test_id} {tc.category}: "
                f"{tc.description} ({result.duration_ms:.0f}ms)"
            )
            if not result.passed:
                # Indent failure message
                for line in result.message.split("\n")[:5]:
                    print(f"         {line}")

    report.total_duration_ms = (time.perf_counter() - t0) * 1000
    return report


def run_module_cli(detector_name: str, tests: list[TestCase]) -> None:
    """
    Run tests and print report. Exit with code 1 if any failures.

    Usage in each test module:
        if __name__ == "__main__":
            run_module_cli("rolling_window", get_tests())
    """
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    report = run_test_module(detector_name, tests, verbose=verbose)

    print(report.summary_line())
    if report.failed > 0:
        print(f"\nFailed tests:")
        for r in report.results:
            if not r.passed:
                print(f"  {r.test_id}: {r.message[:200]}")
        sys.exit(1)
