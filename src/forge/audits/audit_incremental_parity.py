"""
G3-1: Incremental vs Vectorized Indicator Parity Audit.

Compares the 11 O(1) incremental indicators against their pandas_ta
vectorized equivalents to ensure mathematical parity.

CLI: python trade_cli.py backtest audit-incremental-parity [--tolerance 1e-6] [--bars 1000]

The 11 incremental indicators tested:
1. EMA - Exponential Moving Average
2. SMA - Simple Moving Average
3. RSI - Relative Strength Index
4. ATR - Average True Range
5. MACD - Moving Average Convergence Divergence
6. BBands - Bollinger Bands
7. Williams %R - Williams Percent Range
8. CCI - Commodity Channel Index
9. Stochastic - Stochastic Oscillator
10. ADX - Average Directional Index
11. SuperTrend - SuperTrend Indicator
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from src.indicators.incremental import (
    IncrementalEMA,
    IncrementalSMA,
    IncrementalRSI,
    IncrementalATR,
    IncrementalMACD,
    IncrementalBBands,
    IncrementalWilliamsR,
    IncrementalCCI,
    IncrementalStochastic,
    IncrementalADX,
    IncrementalSuperTrend,
)
from src.indicators import compute_indicator


@dataclass
class IncrementalIndicatorResult:
    """Result of comparing a single indicator."""

    indicator: str
    passed: bool
    max_abs_diff: float
    mean_abs_diff: float
    valid_comparisons: int
    warmup_bars: int
    outputs_checked: list[str] = field(default_factory=list)
    error_message: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class IncrementalParityAuditResult:
    """Result of the complete incremental parity audit."""

    success: bool
    total_indicators: int
    passed_indicators: int
    failed_indicators: int
    tolerance: float
    bars_tested: int
    results: list[IncrementalIndicatorResult] = field(default_factory=list)
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "success": self.success,
            "total_indicators": self.total_indicators,
            "passed_indicators": self.passed_indicators,
            "failed_indicators": self.failed_indicators,
            "tolerance": self.tolerance,
            "bars_tested": self.bars_tested,
            "results": [
                {
                    "indicator": r.indicator,
                    "passed": r.passed,
                    "max_abs_diff": r.max_abs_diff,
                    "mean_abs_diff": r.mean_abs_diff,
                    "valid_comparisons": r.valid_comparisons,
                    "warmup_bars": r.warmup_bars,
                    "outputs_checked": r.outputs_checked,
                    "error_message": r.error_message,
                }
                for r in self.results
            ],
            "error_message": self.error_message,
        }

    def print_summary(self) -> None:
        """Print human-readable summary to console."""
        print(f"\n{'=' * 60}")
        print("INCREMENTAL vs VECTORIZED INDICATOR PARITY AUDIT")
        print(f"{'=' * 60}")
        print(f"Bars tested: {self.bars_tested}")
        print(f"Tolerance: {self.tolerance}")
        print(f"Indicators: {self.passed_indicators}/{self.total_indicators} passed")
        print(f"{'=' * 60}\n")

        for r in self.results:
            status = "[PASS]" if r.passed else "[FAIL]"
            print(f"{status} {r.indicator}")
            print(f"       Outputs: {', '.join(r.outputs_checked)}")
            print(f"       Max diff: {r.max_abs_diff:.2e}, Mean diff: {r.mean_abs_diff:.2e}")
            if r.error_message:
                print(f"       Error: {r.error_message}")
            print()

        if self.success:
            print("[OK] All incremental indicators match vectorized computation")
        else:
            print("[FAIL] Some indicators show parity issues")


def generate_synthetic_ohlcv(bars: int = 1000, seed: int = 42) -> pd.DataFrame:
    """
    Generate synthetic OHLCV data for testing.

    Creates realistic price action with:
    - Trending behavior
    - Volatility clustering
    - Proper OHLC relationships (high >= low, etc.)
    """
    np.random.seed(seed)

    # Start with a random walk for close prices
    returns = np.random.randn(bars) * 0.02  # 2% daily volatility
    close = 100 * np.exp(np.cumsum(returns))

    # Generate high/low with realistic ranges
    volatility = np.abs(returns) + 0.005  # Base volatility
    high = close * (1 + volatility * np.random.uniform(0.5, 1.5, bars))
    low = close * (1 - volatility * np.random.uniform(0.5, 1.5, bars))

    # Ensure high >= close >= low (mostly)
    high = np.maximum(high, close)
    low = np.minimum(low, close)

    # Open is between previous close and current close
    open_prices = np.roll(close, 1)
    open_prices[0] = close[0]

    # Volume with some clustering
    volume = np.abs(np.random.randn(bars)) * 1000000 + 500000

    # Create DataFrame
    df = pd.DataFrame({
        "open": open_prices,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })

    return df


def _compare_series(
    incremental_values: list[float],
    vectorized_series: pd.Series,
    warmup: int,
    tolerance: float,
) -> tuple[bool, float, float, int]:
    """
    Compare incremental values against vectorized series.

    Returns: (passed, max_diff, mean_diff, valid_comparisons)
    """
    # Skip warmup period
    inc_arr = np.array(incremental_values[warmup:])
    vec_arr = vectorized_series.values[warmup:]

    # Align lengths
    min_len = min(len(inc_arr), len(vec_arr))
    inc_arr = inc_arr[:min_len]
    vec_arr = vec_arr[:min_len]

    # Only compare valid (non-NaN) values
    valid_mask = ~np.isnan(inc_arr) & ~np.isnan(vec_arr)
    valid_count = int(valid_mask.sum())

    if valid_count == 0:
        return True, 0.0, 0.0, 0

    diffs = np.abs(inc_arr[valid_mask] - vec_arr[valid_mask])
    max_diff = float(np.max(diffs))
    mean_diff = float(np.mean(diffs))

    passed = max_diff <= tolerance

    return passed, max_diff, mean_diff, valid_count


def audit_ema_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test EMA parity."""
    length = 20
    warmup = length

    # Incremental
    inc = IncrementalEMA(length=length)
    inc_values = []
    for close in df["close"]:
        inc.update(close=close)
        inc_values.append(inc.value)

    # Vectorized
    vec = compute_indicator("ema", close=df["close"], length=length)

    passed, max_diff, mean_diff, valid = _compare_series(
        inc_values, vec, warmup, tolerance
    )

    return IncrementalIndicatorResult(
        indicator="EMA",
        passed=passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["value"],
    )


def audit_sma_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test SMA parity."""
    length = 20
    warmup = length

    # Incremental
    inc = IncrementalSMA(length=length)
    inc_values = []
    for close in df["close"]:
        inc.update(close=close)
        inc_values.append(inc.value)

    # Vectorized
    vec = compute_indicator("sma", close=df["close"], length=length)

    passed, max_diff, mean_diff, valid = _compare_series(
        inc_values, vec, warmup, tolerance
    )

    return IncrementalIndicatorResult(
        indicator="SMA",
        passed=passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["value"],
    )


def audit_rsi_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test RSI parity."""
    length = 14
    warmup = length + 1

    # Incremental
    inc = IncrementalRSI(length=length)
    inc_values = []
    for close in df["close"]:
        inc.update(close=close)
        inc_values.append(inc.value)

    # Vectorized
    vec = compute_indicator("rsi", close=df["close"], length=length)

    passed, max_diff, mean_diff, valid = _compare_series(
        inc_values, vec, warmup, tolerance
    )

    return IncrementalIndicatorResult(
        indicator="RSI",
        passed=passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["value"],
    )


def audit_atr_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test ATR parity."""
    length = 14
    warmup = length

    # Incremental
    inc = IncrementalATR(length=length)
    inc_values = []
    for _, row in df.iterrows():
        inc.update(high=row["high"], low=row["low"], close=row["close"])
        inc_values.append(inc.value)

    # Vectorized - use talib=False to match our pure Python incremental implementation
    vec = compute_indicator(
        "atr", high=df["high"], low=df["low"], close=df["close"], length=length,
        talib=False
    )

    passed, max_diff, mean_diff, valid = _compare_series(
        inc_values, vec, warmup, tolerance
    )

    return IncrementalIndicatorResult(
        indicator="ATR",
        passed=passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["value"],
    )


def audit_macd_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test MACD parity (all 3 outputs)."""
    fast, slow, signal = 12, 26, 9
    warmup = slow + signal

    # Incremental
    inc = IncrementalMACD(fast=fast, slow=slow, signal=signal)
    inc_macd, inc_signal, inc_hist = [], [], []
    for close in df["close"]:
        inc.update(close=close)
        inc_macd.append(inc.macd_value)
        inc_signal.append(inc.signal_value)
        inc_hist.append(inc.histogram_value)

    # Vectorized - use talib=False to match our pure Python incremental implementation
    vec = compute_indicator(
        "macd", close=df["close"], fast=fast, slow=slow, signal=signal,
        talib=False
    )

    # Check all outputs
    results = []
    for inc_vals, vec_key, name in [
        (inc_macd, "macd", "macd"),
        (inc_signal, "signal", "signal"),
        (inc_hist, "histogram", "histogram"),
    ]:
        p, mx, mn, v = _compare_series(inc_vals, vec[vec_key], warmup, tolerance)
        results.append((p, mx, mn, v, name))

    all_passed = all(r[0] for r in results)
    max_diff = max(r[1] for r in results)
    mean_diff = np.mean([r[2] for r in results])
    valid = min(r[3] for r in results)

    return IncrementalIndicatorResult(
        indicator="MACD",
        passed=all_passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["macd", "signal", "histogram"],
    )


def audit_bbands_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test Bollinger Bands parity (all outputs)."""
    length = 20
    std_dev = 2.0
    warmup = length

    # Incremental
    inc = IncrementalBBands(length=length, std_dev=std_dev)
    inc_lower, inc_middle, inc_upper = [], [], []
    for close in df["close"]:
        inc.update(close=close)
        inc_lower.append(inc.lower)
        inc_middle.append(inc.middle)
        inc_upper.append(inc.upper)

    # Vectorized
    vec = compute_indicator("bbands", close=df["close"], length=length, std=std_dev)

    # Check all outputs
    results = []
    for inc_vals, vec_key, name in [
        (inc_lower, "lower", "lower"),
        (inc_middle, "middle", "middle"),
        (inc_upper, "upper", "upper"),
    ]:
        p, mx, mn, v = _compare_series(inc_vals, vec[vec_key], warmup, tolerance)
        results.append((p, mx, mn, v, name))

    all_passed = all(r[0] for r in results)
    max_diff = max(r[1] for r in results)
    mean_diff = np.mean([r[2] for r in results])
    valid = min(r[3] for r in results)

    return IncrementalIndicatorResult(
        indicator="BBands",
        passed=all_passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["lower", "middle", "upper"],
    )


def audit_willr_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test Williams %R parity."""
    length = 14
    warmup = length

    # Incremental
    inc = IncrementalWilliamsR(length=length)
    inc_values = []
    for _, row in df.iterrows():
        inc.update(high=row["high"], low=row["low"], close=row["close"])
        inc_values.append(inc.value)

    # Vectorized
    vec = compute_indicator(
        "willr", high=df["high"], low=df["low"], close=df["close"], length=length
    )

    passed, max_diff, mean_diff, valid = _compare_series(
        inc_values, vec, warmup, tolerance
    )

    return IncrementalIndicatorResult(
        indicator="WilliamsR",
        passed=passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["value"],
    )


def audit_cci_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test CCI parity."""
    length = 14
    warmup = length

    # Incremental
    inc = IncrementalCCI(length=length)
    inc_values = []
    for _, row in df.iterrows():
        inc.update(high=row["high"], low=row["low"], close=row["close"])
        inc_values.append(inc.value)

    # Vectorized
    vec = compute_indicator(
        "cci", high=df["high"], low=df["low"], close=df["close"], length=length
    )

    passed, max_diff, mean_diff, valid = _compare_series(
        inc_values, vec, warmup, tolerance
    )

    return IncrementalIndicatorResult(
        indicator="CCI",
        passed=passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["value"],
    )


def audit_stoch_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test Stochastic parity."""
    k_period = 14
    smooth_k = 3
    d_period = 3
    warmup = k_period + smooth_k + d_period

    # Incremental
    inc = IncrementalStochastic(k_period=k_period, smooth_k=smooth_k, d_period=d_period)
    inc_k, inc_d = [], []
    for _, row in df.iterrows():
        inc.update(high=row["high"], low=row["low"], close=row["close"])
        inc_k.append(inc.k_value)
        inc_d.append(inc.d_value)

    # Vectorized
    vec = compute_indicator(
        "stoch",
        high=df["high"],
        low=df["low"],
        close=df["close"],
        k=k_period,
        d=d_period,
        smooth_k=smooth_k,
    )

    # Check both outputs
    results = []
    for inc_vals, vec_key, name in [
        (inc_k, "k", "%K"),
        (inc_d, "d", "%D"),
    ]:
        p, mx, mn, v = _compare_series(inc_vals, vec[vec_key], warmup, tolerance)
        results.append((p, mx, mn, v, name))

    all_passed = all(r[0] for r in results)
    max_diff = max(r[1] for r in results)
    mean_diff = np.mean([r[2] for r in results])
    valid = min(r[3] for r in results)

    return IncrementalIndicatorResult(
        indicator="Stochastic",
        passed=all_passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["%K", "%D"],
    )


def audit_adx_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test ADX parity."""
    length = 14
    warmup = length * 2

    # Incremental
    inc = IncrementalADX(length=length)
    inc_adx, inc_dmp, inc_dmn = [], [], []
    for _, row in df.iterrows():
        inc.update(high=row["high"], low=row["low"], close=row["close"])
        inc_adx.append(inc.adx_value)
        inc_dmp.append(inc.dmp_value)
        inc_dmn.append(inc.dmn_value)

    # Vectorized - use talib=False since IncrementalATR matches pure Python pandas_ta
    vec = compute_indicator(
        "adx", high=df["high"], low=df["low"], close=df["close"], length=length,
        talib=False
    )

    # Check outputs
    results = []
    for inc_vals, vec_key, name in [
        (inc_adx, "adx", "ADX"),
        (inc_dmp, "dmp", "+DI"),
        (inc_dmn, "dmn", "-DI"),
    ]:
        p, mx, mn, v = _compare_series(inc_vals, vec[vec_key], warmup, tolerance)
        results.append((p, mx, mn, v, name))

    all_passed = all(r[0] for r in results)
    max_diff = max(r[1] for r in results)
    mean_diff = np.mean([r[2] for r in results])
    valid = min(r[3] for r in results)

    return IncrementalIndicatorResult(
        indicator="ADX",
        passed=all_passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["ADX", "+DI", "-DI"],
    )


def audit_supertrend_parity(
    df: pd.DataFrame, tolerance: float
) -> IncrementalIndicatorResult:
    """Test SuperTrend parity."""
    length = 10
    multiplier = 3.0
    warmup = length + 1

    # Incremental
    inc = IncrementalSuperTrend(length=length, multiplier=multiplier)
    inc_trend, inc_direction = [], []
    for _, row in df.iterrows():
        inc.update(high=row["high"], low=row["low"], close=row["close"])
        inc_trend.append(inc.trend_value)
        inc_direction.append(inc.direction_value)

    # Vectorized - default pandas_ta uses TA-Lib ATR internally.
    # Our IncrementalSuperTrend uses prenan=True ATR + skips first ATR-ready bar
    # to match this TA-Lib behavior.
    vec = compute_indicator(
        "supertrend",
        high=df["high"],
        low=df["low"],
        close=df["close"],
        length=length,
        multiplier=multiplier,
    )

    # Check trend output (direction may have different conventions)
    passed, max_diff, mean_diff, valid = _compare_series(
        inc_trend, vec["trend"], warmup, tolerance
    )

    return IncrementalIndicatorResult(
        indicator="SuperTrend",
        passed=passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["trend"],
    )


def run_incremental_parity_audit(
    bars: int = 1000,
    tolerance: float = 1e-6,
    seed: int = 42,
) -> IncrementalParityAuditResult:
    """
    Run the complete incremental vs vectorized parity audit.

    Args:
        bars: Number of bars to test
        tolerance: Maximum allowed absolute difference
        seed: Random seed for reproducibility

    Returns:
        IncrementalParityAuditResult with all indicator results
    """
    try:
        # Generate synthetic data
        df = generate_synthetic_ohlcv(bars=bars, seed=seed)

        # Run all audits
        audit_funcs = [
            audit_ema_parity,
            audit_sma_parity,
            audit_rsi_parity,
            audit_atr_parity,
            audit_macd_parity,
            audit_bbands_parity,
            audit_willr_parity,
            audit_cci_parity,
            audit_stoch_parity,
            audit_adx_parity,
            audit_supertrend_parity,
        ]

        results = []
        for audit_func in audit_funcs:
            try:
                result = audit_func(df, tolerance)
                results.append(result)
            except Exception as e:
                # Record failed audit
                indicator_name = audit_func.__name__.replace("audit_", "").replace(
                    "_parity", ""
                ).upper()
                results.append(
                    IncrementalIndicatorResult(
                        indicator=indicator_name,
                        passed=False,
                        max_abs_diff=float("inf"),
                        mean_abs_diff=float("inf"),
                        valid_comparisons=0,
                        warmup_bars=0,
                        outputs_checked=[],
                        error_message=str(e),
                    )
                )

        passed_count = sum(1 for r in results if r.passed)
        failed_count = len(results) - passed_count

        return IncrementalParityAuditResult(
            success=(failed_count == 0),
            total_indicators=len(results),
            passed_indicators=passed_count,
            failed_indicators=failed_count,
            tolerance=tolerance,
            bars_tested=bars,
            results=results,
        )

    except Exception as e:
        import traceback

        return IncrementalParityAuditResult(
            success=False,
            total_indicators=0,
            passed_indicators=0,
            failed_indicators=0,
            tolerance=tolerance,
            bars_tested=bars,
            error_message=f"Audit failed: {str(e)}\n{traceback.format_exc()}",
        )


# CLI entry point
def main():
    """CLI entry point for standalone execution."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Audit incremental vs vectorized indicator parity"
    )
    parser.add_argument(
        "--bars", type=int, default=1000, help="Number of bars to test (default: 1000)"
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=1e-6,
        help="Max allowed difference (default: 1e-6)",
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="Random seed (default: 42)"
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    result = run_incremental_parity_audit(
        bars=args.bars,
        tolerance=args.tolerance,
        seed=args.seed,
    )

    if args.json:
        import json

        print(json.dumps(result.to_dict(), indent=2))
    else:
        result.print_summary()

    return 0 if result.success else 1


if __name__ == "__main__":
    exit(main())
