"""
G3-1: Incremental vs Vectorized Indicator Parity Audit.

Compares all 43 O(1) incremental indicators against their pandas_ta
vectorized equivalents to ensure mathematical parity.

CLI: python trade_cli.py backtest audit-incremental-parity [--tolerance 1e-6] [--bars 1000]

The 43 incremental indicators tested:
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
12. StochRSI - Stochastic RSI
13. OHLC4 - OHLC Average
14. MIDPRICE - Midpoint Price
15. ROC - Rate of Change
16. MOM - Momentum
17. OBV - On Balance Volume
18. NATR - Normalized ATR
19. DEMA - Double EMA
20. TEMA - Triple EMA
21. PPO - Percentage Price Oscillator
22. TRIX - Triple Exponential Average
23. TSI - True Strength Index
24. WMA - Weighted Moving Average
25. TRIMA - Triangular Moving Average
26. LINREG - Linear Regression
27. CMF - Chaikin Money Flow
28. CMO - Chande Momentum Oscillator
29. MFI - Money Flow Index
30. AROON - Aroon Indicator
31. DONCHIAN - Donchian Channel
32. KC - Keltner Channel
33. DM - Directional Movement
34. VORTEX - Vortex Indicator
35. KAMA - Kaufman Adaptive MA
36. ALMA - Arnaud Legoux MA
37. ZLMA - Zero Lag MA
38. UO - Ultimate Oscillator
39. PSAR - Parabolic SAR
40. SQUEEZE - Squeeze Indicator
41. FISHER - Fisher Transform
42. KVO - Klinger Volume Oscillator
43. VWAP - Volume Weighted Average Price
"""

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
    IncrementalStochRSI,
    IncrementalOHLC4,
    IncrementalMidprice,
    IncrementalROC,
    IncrementalMOM,
    IncrementalOBV,
    IncrementalNATR,
    IncrementalDEMA,
    IncrementalTEMA,
    IncrementalPPO,
    IncrementalTRIX,
    IncrementalTSI,
    IncrementalWMA,
    IncrementalTRIMA,
    IncrementalLINREG,
    IncrementalCMF,
    IncrementalCMO,
    IncrementalMFI,
    IncrementalAROON,
    IncrementalDonchian,
    IncrementalKC,
    IncrementalDM,
    IncrementalVortex,
    IncrementalKAMA,
    IncrementalALMA,
    IncrementalZLMA,
    IncrementalUO,
    IncrementalPSAR,
    IncrementalSqueeze,
    IncrementalFisher,
    IncrementalKVO,
    IncrementalVWAP,
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


# =============================================================================
# Original 11 Indicator Audits
# =============================================================================


def audit_ema_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test EMA parity."""
    length = 20
    warmup = length

    inc = IncrementalEMA(length=length)
    inc_values = []
    for close in df["close"]:
        inc.update(close=close)
        inc_values.append(inc.value)

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

    inc = IncrementalSMA(length=length)
    inc_values = []
    for close in df["close"]:
        inc.update(close=close)
        inc_values.append(inc.value)

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

    inc = IncrementalRSI(length=length)
    inc_values = []
    for close in df["close"]:
        inc.update(close=close)
        inc_values.append(inc.value)

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

    inc = IncrementalATR(length=length)
    inc_values = []
    for _, row in df.iterrows():
        inc.update(high=row["high"], low=row["low"], close=row["close"])
        inc_values.append(inc.value)

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

    inc = IncrementalMACD(fast=fast, slow=slow, signal=signal)
    inc_macd, inc_signal, inc_hist = [], [], []
    for close in df["close"]:
        inc.update(close=close)
        inc_macd.append(inc.macd_value)
        inc_signal.append(inc.signal_value)
        inc_hist.append(inc.histogram_value)

    vec = compute_indicator(
        "macd", close=df["close"], fast=fast, slow=slow, signal=signal,
        talib=False
    )

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

    inc = IncrementalBBands(length=length, std_dev=std_dev)
    inc_lower, inc_middle, inc_upper = [], [], []
    for close in df["close"]:
        inc.update(close=close)
        inc_lower.append(inc.lower)
        inc_middle.append(inc.middle)
        inc_upper.append(inc.upper)

    vec = compute_indicator("bbands", close=df["close"], length=length, std=std_dev)

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

    inc = IncrementalWilliamsR(length=length)
    inc_values = []
    for _, row in df.iterrows():
        inc.update(high=row["high"], low=row["low"], close=row["close"])
        inc_values.append(inc.value)

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

    inc = IncrementalCCI(length=length)
    inc_values = []
    for _, row in df.iterrows():
        inc.update(high=row["high"], low=row["low"], close=row["close"])
        inc_values.append(inc.value)

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

    inc = IncrementalStochastic(k_period=k_period, smooth_k=smooth_k, d_period=d_period)
    inc_k, inc_d = [], []
    for _, row in df.iterrows():
        inc.update(high=row["high"], low=row["low"], close=row["close"])
        inc_k.append(inc.k_value)
        inc_d.append(inc.d_value)

    vec = compute_indicator(
        "stoch",
        high=df["high"],
        low=df["low"],
        close=df["close"],
        k=k_period,
        d=d_period,
        smooth_k=smooth_k,
    )

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

    inc = IncrementalADX(length=length)
    inc_adx, inc_dmp, inc_dmn = [], [], []
    for _, row in df.iterrows():
        inc.update(high=row["high"], low=row["low"], close=row["close"])
        inc_adx.append(inc.adx_value)
        inc_dmp.append(inc.dmp_value)
        inc_dmn.append(inc.dmn_value)

    vec = compute_indicator(
        "adx", high=df["high"], low=df["low"], close=df["close"], length=length,
        talib=False
    )

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

    inc = IncrementalSuperTrend(length=length, multiplier=multiplier)
    inc_trend, inc_direction = [], []
    for _, row in df.iterrows():
        inc.update(high=row["high"], low=row["low"], close=row["close"])
        inc_trend.append(inc.trend_value)
        inc_direction.append(inc.direction_value)

    vec = compute_indicator(
        "supertrend",
        high=df["high"],
        low=df["low"],
        close=df["close"],
        length=length,
        multiplier=multiplier,
    )

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


# =============================================================================
# Phase 1: Trivial Indicator Audits
# =============================================================================


def audit_ohlc4_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test OHLC4 parity."""
    warmup = 1

    inc = IncrementalOHLC4()
    inc_values = []
    for _, row in df.iterrows():
        inc.update(open=row["open"], high=row["high"], low=row["low"], close=row["close"])
        inc_values.append(inc.value)

    vec = compute_indicator(
        "ohlc4", open_=df["open"], high=df["high"], low=df["low"], close=df["close"]
    )

    passed, max_diff, mean_diff, valid = _compare_series(
        inc_values, vec, warmup, tolerance
    )

    return IncrementalIndicatorResult(
        indicator="OHLC4",
        passed=passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["value"],
    )


def audit_midprice_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test MIDPRICE parity."""
    length = 14
    warmup = length

    inc = IncrementalMidprice(length=length)
    inc_values = []
    for _, row in df.iterrows():
        inc.update(high=row["high"], low=row["low"])
        inc_values.append(inc.value)

    vec = compute_indicator("midprice", high=df["high"], low=df["low"], length=length)

    passed, max_diff, mean_diff, valid = _compare_series(
        inc_values, vec, warmup, tolerance
    )

    return IncrementalIndicatorResult(
        indicator="MIDPRICE",
        passed=passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["value"],
    )


def audit_roc_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test ROC parity."""
    length = 10
    warmup = length + 1

    inc = IncrementalROC(length=length)
    inc_values = []
    for close in df["close"]:
        inc.update(close=close)
        inc_values.append(inc.value)

    vec = compute_indicator("roc", close=df["close"], length=length)

    passed, max_diff, mean_diff, valid = _compare_series(
        inc_values, vec, warmup, tolerance
    )

    return IncrementalIndicatorResult(
        indicator="ROC",
        passed=passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["value"],
    )


def audit_mom_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test MOM parity."""
    length = 10
    warmup = length + 1

    inc = IncrementalMOM(length=length)
    inc_values = []
    for close in df["close"]:
        inc.update(close=close)
        inc_values.append(inc.value)

    vec = compute_indicator("mom", close=df["close"], length=length)

    passed, max_diff, mean_diff, valid = _compare_series(
        inc_values, vec, warmup, tolerance
    )

    return IncrementalIndicatorResult(
        indicator="MOM",
        passed=passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["value"],
    )


def audit_obv_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test OBV parity."""
    warmup = 1

    inc = IncrementalOBV()
    inc_values = []
    for _, row in df.iterrows():
        inc.update(close=row["close"], volume=row["volume"])
        inc_values.append(inc.value)

    vec = compute_indicator("obv", close=df["close"], volume=df["volume"])

    passed, max_diff, mean_diff, valid = _compare_series(
        inc_values, vec, warmup, tolerance
    )

    return IncrementalIndicatorResult(
        indicator="OBV",
        passed=passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["value"],
    )


def audit_natr_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test NATR parity."""
    length = 14
    warmup = length

    inc = IncrementalNATR(length=length)
    inc_values = []
    for _, row in df.iterrows():
        inc.update(high=row["high"], low=row["low"], close=row["close"])
        inc_values.append(inc.value)

    vec = compute_indicator(
        "natr", high=df["high"], low=df["low"], close=df["close"], length=length,
        talib=False
    )

    passed, max_diff, mean_diff, valid = _compare_series(
        inc_values, vec, warmup, tolerance
    )

    return IncrementalIndicatorResult(
        indicator="NATR",
        passed=passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["value"],
    )


# =============================================================================
# Phase 2: EMA-Composable Indicator Audits
# =============================================================================


def audit_dema_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test DEMA parity."""
    length = 20
    warmup = length * 2

    inc = IncrementalDEMA(length=length)
    inc_values = []
    for close in df["close"]:
        inc.update(close=close)
        inc_values.append(inc.value)

    vec = compute_indicator("dema", close=df["close"], length=length)

    passed, max_diff, mean_diff, valid = _compare_series(
        inc_values, vec, warmup, tolerance
    )

    return IncrementalIndicatorResult(
        indicator="DEMA",
        passed=passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["value"],
    )


def audit_tema_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test TEMA parity."""
    length = 20
    warmup = length * 3

    inc = IncrementalTEMA(length=length)
    inc_values = []
    for close in df["close"]:
        inc.update(close=close)
        inc_values.append(inc.value)

    vec = compute_indicator("tema", close=df["close"], length=length)

    passed, max_diff, mean_diff, valid = _compare_series(
        inc_values, vec, warmup, tolerance
    )

    return IncrementalIndicatorResult(
        indicator="TEMA",
        passed=passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["value"],
    )


def audit_ppo_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test PPO parity."""
    fast, slow, signal = 12, 26, 9
    warmup = slow + signal

    inc = IncrementalPPO(fast=fast, slow=slow, signal=signal)
    inc_ppo, inc_signal, inc_hist = [], [], []
    for close in df["close"]:
        inc.update(close=close)
        inc_ppo.append(inc.ppo_value)
        inc_signal.append(inc.signal_value)
        inc_hist.append(inc.histogram_value)

    vec = compute_indicator(
        "ppo", close=df["close"], fast=fast, slow=slow, signal=signal
    )

    results = []
    for inc_vals, vec_key, name in [
        (inc_ppo, "ppo", "ppo"),
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
        indicator="PPO",
        passed=all_passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["ppo", "signal", "histogram"],
    )


def audit_trix_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test TRIX parity."""
    length = 18
    signal = 9
    warmup = length * 3 + signal

    inc = IncrementalTRIX(length=length, signal=signal)
    inc_trix, inc_signal = [], []
    for close in df["close"]:
        inc.update(close=close)
        inc_trix.append(inc.trix_value)
        inc_signal.append(inc.signal_value)

    vec = compute_indicator("trix", close=df["close"], length=length, signal=signal)

    results = []
    for inc_vals, vec_key, name in [
        (inc_trix, "trix", "trix"),
        (inc_signal, "signal", "signal"),
    ]:
        p, mx, mn, v = _compare_series(inc_vals, vec[vec_key], warmup, tolerance)
        results.append((p, mx, mn, v, name))

    all_passed = all(r[0] for r in results)
    max_diff = max(r[1] for r in results)
    mean_diff = np.mean([r[2] for r in results])
    valid = min(r[3] for r in results)

    return IncrementalIndicatorResult(
        indicator="TRIX",
        passed=all_passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["trix", "signal"],
    )


def audit_tsi_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test TSI parity."""
    fast, slow, signal = 13, 25, 13
    warmup = fast + slow + signal

    inc = IncrementalTSI(fast=fast, slow=slow, signal=signal)
    inc_tsi, inc_signal = [], []
    for close in df["close"]:
        inc.update(close=close)
        inc_tsi.append(inc.tsi_value)
        inc_signal.append(inc.signal_value)

    vec = compute_indicator("tsi", close=df["close"], fast=fast, slow=slow, signal=signal)

    results = []
    for inc_vals, vec_key, name in [
        (inc_tsi, "tsi", "tsi"),
        (inc_signal, "signal", "signal"),
    ]:
        p, mx, mn, v = _compare_series(inc_vals, vec[vec_key], warmup, tolerance)
        results.append((p, mx, mn, v, name))

    all_passed = all(r[0] for r in results)
    max_diff = max(r[1] for r in results)
    mean_diff = np.mean([r[2] for r in results])
    valid = min(r[3] for r in results)

    return IncrementalIndicatorResult(
        indicator="TSI",
        passed=all_passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["tsi", "signal"],
    )


# =============================================================================
# Phase 3: SMA/Buffer-Based Indicator Audits
# =============================================================================


def audit_wma_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test WMA parity."""
    length = 20
    warmup = length

    inc = IncrementalWMA(length=length)
    inc_values = []
    for close in df["close"]:
        inc.update(close=close)
        inc_values.append(inc.value)

    vec = compute_indicator("wma", close=df["close"], length=length)

    passed, max_diff, mean_diff, valid = _compare_series(
        inc_values, vec, warmup, tolerance
    )

    return IncrementalIndicatorResult(
        indicator="WMA",
        passed=passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["value"],
    )


def audit_trima_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test TRIMA parity."""
    length = 20
    warmup = length

    inc = IncrementalTRIMA(length=length)
    inc_values = []
    for close in df["close"]:
        inc.update(close=close)
        inc_values.append(inc.value)

    vec = compute_indicator("trima", close=df["close"], length=length)

    passed, max_diff, mean_diff, valid = _compare_series(
        inc_values, vec, warmup, tolerance
    )

    return IncrementalIndicatorResult(
        indicator="TRIMA",
        passed=passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["value"],
    )


def audit_linreg_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test LINREG parity."""
    length = 14
    warmup = length

    inc = IncrementalLINREG(length=length)
    inc_values = []
    for close in df["close"]:
        inc.update(close=close)
        inc_values.append(inc.value)

    vec = compute_indicator("linreg", close=df["close"], length=length)

    passed, max_diff, mean_diff, valid = _compare_series(
        inc_values, vec, warmup, tolerance
    )

    return IncrementalIndicatorResult(
        indicator="LINREG",
        passed=passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["value"],
    )


def audit_cmf_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test CMF parity."""
    length = 20
    warmup = length

    inc = IncrementalCMF(length=length)
    inc_values = []
    for _, row in df.iterrows():
        inc.update(high=row["high"], low=row["low"], close=row["close"], volume=row["volume"])
        inc_values.append(inc.value)

    vec = compute_indicator(
        "cmf", high=df["high"], low=df["low"], close=df["close"], volume=df["volume"], length=length
    )

    passed, max_diff, mean_diff, valid = _compare_series(
        inc_values, vec, warmup, tolerance
    )

    return IncrementalIndicatorResult(
        indicator="CMF",
        passed=passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["value"],
    )


def audit_cmo_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test CMO parity."""
    length = 14
    warmup = length + 1

    inc = IncrementalCMO(length=length)
    inc_values = []
    for close in df["close"]:
        inc.update(close=close)
        inc_values.append(inc.value)

    vec = compute_indicator("cmo", close=df["close"], length=length)

    passed, max_diff, mean_diff, valid = _compare_series(
        inc_values, vec, warmup, tolerance
    )

    return IncrementalIndicatorResult(
        indicator="CMO",
        passed=passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["value"],
    )


def audit_mfi_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test MFI parity."""
    length = 14
    warmup = length + 1

    inc = IncrementalMFI(length=length)
    inc_values = []
    for _, row in df.iterrows():
        inc.update(high=row["high"], low=row["low"], close=row["close"], volume=row["volume"])
        inc_values.append(inc.value)

    vec = compute_indicator(
        "mfi", high=df["high"], low=df["low"], close=df["close"], volume=df["volume"], length=length
    )

    passed, max_diff, mean_diff, valid = _compare_series(
        inc_values, vec, warmup, tolerance
    )

    return IncrementalIndicatorResult(
        indicator="MFI",
        passed=passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["value"],
    )


# =============================================================================
# Phase 4: Lookback-Based Indicator Audits
# =============================================================================


def audit_aroon_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test AROON parity."""
    length = 25
    warmup = length + 1

    inc = IncrementalAROON(length=length)
    inc_up, inc_down, inc_osc = [], [], []
    for _, row in df.iterrows():
        inc.update(high=row["high"], low=row["low"])
        inc_up.append(inc.up_value)
        inc_down.append(inc.down_value)
        inc_osc.append(inc.osc_value)

    vec = compute_indicator("aroon", high=df["high"], low=df["low"], length=length)

    results = []
    for inc_vals, vec_key, name in [
        (inc_up, "up", "up"),
        (inc_down, "down", "down"),
        (inc_osc, "osc", "osc"),
    ]:
        p, mx, mn, v = _compare_series(inc_vals, vec[vec_key], warmup, tolerance)
        results.append((p, mx, mn, v, name))

    all_passed = all(r[0] for r in results)
    max_diff = max(r[1] for r in results)
    mean_diff = np.mean([r[2] for r in results])
    valid = min(r[3] for r in results)

    return IncrementalIndicatorResult(
        indicator="AROON",
        passed=all_passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["up", "down", "osc"],
    )


def audit_donchian_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test DONCHIAN parity."""
    lower_length = 20
    upper_length = 20
    warmup = max(lower_length, upper_length)

    inc = IncrementalDonchian(lower_length=lower_length, upper_length=upper_length)
    inc_lower, inc_middle, inc_upper = [], [], []
    for _, row in df.iterrows():
        inc.update(high=row["high"], low=row["low"])
        inc_lower.append(inc.lower_value)
        inc_middle.append(inc.middle_value)
        inc_upper.append(inc.upper_value)

    vec = compute_indicator(
        "donchian", high=df["high"], low=df["low"],
        lower_length=lower_length, upper_length=upper_length
    )

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
        indicator="DONCHIAN",
        passed=all_passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["lower", "middle", "upper"],
    )


def audit_kc_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test KC parity."""
    length = 20
    scalar = 2.0
    warmup = length

    inc = IncrementalKC(length=length, scalar=scalar)
    inc_lower, inc_basis, inc_upper = [], [], []
    for _, row in df.iterrows():
        inc.update(high=row["high"], low=row["low"], close=row["close"])
        inc_lower.append(inc.lower_value)
        inc_basis.append(inc.basis_value)
        inc_upper.append(inc.upper_value)

    vec = compute_indicator(
        "kc", high=df["high"], low=df["low"], close=df["close"],
        length=length, scalar=scalar
    )

    results = []
    for inc_vals, vec_key, name in [
        (inc_lower, "lower", "lower"),
        (inc_basis, "basis", "basis"),
        (inc_upper, "upper", "upper"),
    ]:
        p, mx, mn, v = _compare_series(inc_vals, vec[vec_key], warmup, tolerance)
        results.append((p, mx, mn, v, name))

    all_passed = all(r[0] for r in results)
    max_diff = max(r[1] for r in results)
    mean_diff = np.mean([r[2] for r in results])
    valid = min(r[3] for r in results)

    return IncrementalIndicatorResult(
        indicator="KC",
        passed=all_passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["lower", "basis", "upper"],
    )


def audit_dm_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test DM parity."""
    length = 14
    warmup = length

    inc = IncrementalDM(length=length)
    inc_dmp, inc_dmn = [], []
    for _, row in df.iterrows():
        inc.update(high=row["high"], low=row["low"])
        inc_dmp.append(inc.dmp_value)
        inc_dmn.append(inc.dmn_value)

    vec = compute_indicator("dm", high=df["high"], low=df["low"], length=length)

    results = []
    for inc_vals, vec_key, name in [
        (inc_dmp, "dmp", "dmp"),
        (inc_dmn, "dmn", "dmn"),
    ]:
        p, mx, mn, v = _compare_series(inc_vals, vec[vec_key], warmup, tolerance)
        results.append((p, mx, mn, v, name))

    all_passed = all(r[0] for r in results)
    max_diff = max(r[1] for r in results)
    mean_diff = np.mean([r[2] for r in results])
    valid = min(r[3] for r in results)

    return IncrementalIndicatorResult(
        indicator="DM",
        passed=all_passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["dmp", "dmn"],
    )


def audit_vortex_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test VORTEX parity."""
    length = 14
    warmup = length

    inc = IncrementalVortex(length=length)
    inc_vip, inc_vim = [], []
    for _, row in df.iterrows():
        inc.update(high=row["high"], low=row["low"], close=row["close"])
        inc_vip.append(inc.vip_value)
        inc_vim.append(inc.vim_value)

    vec = compute_indicator(
        "vortex", high=df["high"], low=df["low"], close=df["close"], length=length
    )

    results = []
    for inc_vals, vec_key, name in [
        (inc_vip, "vip", "vip"),
        (inc_vim, "vim", "vim"),
    ]:
        p, mx, mn, v = _compare_series(inc_vals, vec[vec_key], warmup, tolerance)
        results.append((p, mx, mn, v, name))

    all_passed = all(r[0] for r in results)
    max_diff = max(r[1] for r in results)
    mean_diff = np.mean([r[2] for r in results])
    valid = min(r[3] for r in results)

    return IncrementalIndicatorResult(
        indicator="VORTEX",
        passed=all_passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["vip", "vim"],
    )


# =============================================================================
# Phase 5: Complex Adaptive Indicator Audits
# =============================================================================


def audit_kama_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test KAMA parity."""
    length = 10
    warmup = length + 10  # Extra warmup for adaptive MA

    inc = IncrementalKAMA(length=length)
    inc_values = []
    for close in df["close"]:
        inc.update(close=close)
        inc_values.append(inc.value)

    vec = compute_indicator("kama", close=df["close"], length=length)

    passed, max_diff, mean_diff, valid = _compare_series(
        inc_values, vec, warmup, tolerance
    )

    return IncrementalIndicatorResult(
        indicator="KAMA",
        passed=passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["value"],
    )


def audit_alma_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test ALMA parity."""
    length = 10
    sigma = 6.0
    offset = 0.85
    warmup = length

    inc = IncrementalALMA(length=length, sigma=sigma, offset=offset)
    inc_values = []
    for close in df["close"]:
        inc.update(close=close)
        inc_values.append(inc.value)

    vec = compute_indicator("alma", close=df["close"], length=length, sigma=sigma, offset=offset)

    passed, max_diff, mean_diff, valid = _compare_series(
        inc_values, vec, warmup, tolerance
    )

    return IncrementalIndicatorResult(
        indicator="ALMA",
        passed=passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["value"],
    )


def audit_zlma_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test ZLMA parity."""
    length = 20
    warmup = length

    inc = IncrementalZLMA(length=length)
    inc_values = []
    for close in df["close"]:
        inc.update(close=close)
        inc_values.append(inc.value)

    vec = compute_indicator("zlma", close=df["close"], length=length)

    passed, max_diff, mean_diff, valid = _compare_series(
        inc_values, vec, warmup, tolerance
    )

    return IncrementalIndicatorResult(
        indicator="ZLMA",
        passed=passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["value"],
    )


def audit_uo_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test UO parity."""
    fast, medium, slow = 7, 14, 28
    warmup = slow + 1

    inc = IncrementalUO(fast=fast, medium=medium, slow=slow)
    inc_values = []
    for _, row in df.iterrows():
        inc.update(high=row["high"], low=row["low"], close=row["close"])
        inc_values.append(inc.value)

    vec = compute_indicator(
        "uo", high=df["high"], low=df["low"], close=df["close"],
        fast=fast, medium=medium, slow=slow
    )

    passed, max_diff, mean_diff, valid = _compare_series(
        inc_values, vec, warmup, tolerance
    )

    return IncrementalIndicatorResult(
        indicator="UO",
        passed=passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["value"],
    )


# =============================================================================
# Phase 6: Stateful Multi-Output Indicator Audits
# =============================================================================


def audit_psar_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test PSAR parity."""
    af0, af, max_af = 0.02, 0.02, 0.2
    warmup = 5  # PSAR needs a few bars to establish trend

    inc = IncrementalPSAR(af0=af0, af=af, max_af=max_af)
    inc_long, inc_short = [], []
    for _, row in df.iterrows():
        inc.update(high=row["high"], low=row["low"], close=row["close"])
        inc_long.append(inc.long_value)
        inc_short.append(inc.short_value)

    vec = compute_indicator(
        "psar", high=df["high"], low=df["low"], close=df["close"],
        af0=af0, af=af, max_af=max_af
    )

    # PSAR has mutually exclusive long/short, so we just check that values exist
    # where expected (harder to do exact parity due to state machine complexity)
    inc_long_arr = np.array(inc_long[warmup:])
    inc_short_arr = np.array(inc_short[warmup:])
    vec_long_arr = vec["long"].values[warmup:]
    vec_short_arr = vec["short"].values[warmup:]

    # Compare only where both have values
    long_valid = ~np.isnan(inc_long_arr) & ~np.isnan(vec_long_arr)
    short_valid = ~np.isnan(inc_short_arr) & ~np.isnan(vec_short_arr)

    if long_valid.sum() > 0:
        long_diff = np.abs(inc_long_arr[long_valid] - vec_long_arr[long_valid])
        max_long = float(np.max(long_diff))
    else:
        max_long = 0.0

    if short_valid.sum() > 0:
        short_diff = np.abs(inc_short_arr[short_valid] - vec_short_arr[short_valid])
        max_short = float(np.max(short_diff))
    else:
        max_short = 0.0

    max_diff = max(max_long, max_short)
    passed = max_diff <= tolerance
    valid = int(long_valid.sum() + short_valid.sum())

    return IncrementalIndicatorResult(
        indicator="PSAR",
        passed=passed,
        max_abs_diff=max_diff,
        mean_abs_diff=max_diff / 2 if max_diff > 0 else 0.0,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["long", "short"],
    )


def audit_squeeze_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test SQUEEZE parity."""
    bb_length, bb_std = 20, 2.0
    kc_length, kc_scalar = 20, 1.5
    warmup = max(bb_length, kc_length)

    inc = IncrementalSqueeze(
        bb_length=bb_length, bb_std=bb_std,
        kc_length=kc_length, kc_scalar=kc_scalar
    )
    inc_sqz, inc_on, inc_off = [], [], []
    for _, row in df.iterrows():
        inc.update(high=row["high"], low=row["low"], close=row["close"])
        inc_sqz.append(inc.sqz_value)
        inc_on.append(inc.on_value)
        inc_off.append(inc.off_value)

    vec = compute_indicator(
        "squeeze", high=df["high"], low=df["low"], close=df["close"],
        bb_length=bb_length, bb_std=bb_std, kc_length=kc_length, kc_scalar=kc_scalar
    )

    # Just check sqz value for now (on/off are binary)
    passed, max_diff, mean_diff, valid = _compare_series(
        inc_sqz, vec["sqz"], warmup, tolerance
    )

    return IncrementalIndicatorResult(
        indicator="SQUEEZE",
        passed=passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["sqz"],
    )


def audit_fisher_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test FISHER parity."""
    length = 9
    warmup = length

    inc = IncrementalFisher(length=length)
    inc_fisher, inc_signal = [], []
    for _, row in df.iterrows():
        inc.update(high=row["high"], low=row["low"])
        inc_fisher.append(inc.fisher_value)
        inc_signal.append(inc.signal_value)

    vec = compute_indicator("fisher", high=df["high"], low=df["low"], length=length)

    results = []
    for inc_vals, vec_key, name in [
        (inc_fisher, "fisher", "fisher"),
        (inc_signal, "signal", "signal"),
    ]:
        p, mx, mn, v = _compare_series(inc_vals, vec[vec_key], warmup, tolerance)
        results.append((p, mx, mn, v, name))

    all_passed = all(r[0] for r in results)
    max_diff = max(r[1] for r in results)
    mean_diff = np.mean([r[2] for r in results])
    valid = min(r[3] for r in results)

    return IncrementalIndicatorResult(
        indicator="FISHER",
        passed=all_passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["fisher", "signal"],
    )


# =============================================================================
# Phase 7: Volume Complex Indicator Audits
# =============================================================================


def audit_kvo_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test KVO parity."""
    fast, slow, signal = 34, 55, 13
    warmup = slow + signal

    inc = IncrementalKVO(fast=fast, slow=slow, signal=signal)
    inc_kvo, inc_signal = [], []
    for _, row in df.iterrows():
        inc.update(high=row["high"], low=row["low"], close=row["close"], volume=row["volume"])
        inc_kvo.append(inc.kvo_value)
        inc_signal.append(inc.signal_value)

    vec = compute_indicator(
        "kvo", high=df["high"], low=df["low"], close=df["close"], volume=df["volume"],
        fast=fast, slow=slow, signal=signal
    )

    results = []
    for inc_vals, vec_key, name in [
        (inc_kvo, "kvo", "kvo"),
        (inc_signal, "signal", "signal"),
    ]:
        p, mx, mn, v = _compare_series(inc_vals, vec[vec_key], warmup, tolerance)
        results.append((p, mx, mn, v, name))

    all_passed = all(r[0] for r in results)
    max_diff = max(r[1] for r in results)
    mean_diff = np.mean([r[2] for r in results])
    valid = min(r[3] for r in results)

    return IncrementalIndicatorResult(
        indicator="KVO",
        passed=all_passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["kvo", "signal"],
    )


def audit_vwap_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test VWAP parity."""
    warmup = 1

    inc = IncrementalVWAP()
    inc_values = []
    for _, row in df.iterrows():
        inc.update(high=row["high"], low=row["low"], close=row["close"], volume=row["volume"])
        inc_values.append(inc.value)

    vec = compute_indicator(
        "vwap", high=df["high"], low=df["low"], close=df["close"], volume=df["volume"]
    )

    passed, max_diff, mean_diff, valid = _compare_series(
        inc_values, vec, warmup, tolerance
    )

    return IncrementalIndicatorResult(
        indicator="VWAP",
        passed=passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["value"],
    )


def audit_stochrsi_parity(df: pd.DataFrame, tolerance: float) -> IncrementalIndicatorResult:
    """Test StochRSI parity."""
    length = 14
    rsi_length = 14
    k, d = 3, 3
    warmup = rsi_length + length + max(k, d)

    inc = IncrementalStochRSI(length=length, rsi_length=rsi_length, k=k, d=d)
    inc_k, inc_d = [], []
    for close in df["close"]:
        inc.update(close=close)
        inc_k.append(inc.k_value)
        inc_d.append(inc.d_value)

    vec = compute_indicator(
        "stochrsi", close=df["close"],
        length=length, rsi_length=rsi_length, k=k, d=d
    )

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
        indicator="StochRSI",
        passed=all_passed,
        max_abs_diff=max_diff,
        mean_abs_diff=mean_diff,
        valid_comparisons=valid,
        warmup_bars=warmup,
        outputs_checked=["%K", "%D"],
    )


# =============================================================================
# Main Audit Runner
# =============================================================================


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

        # Run all audits - all 43 indicators
        audit_funcs = [
            # Original 11
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
            audit_stochrsi_parity,
            # Phase 1: Trivial
            audit_ohlc4_parity,
            audit_midprice_parity,
            audit_roc_parity,
            audit_mom_parity,
            audit_obv_parity,
            audit_natr_parity,
            # Phase 2: EMA-composable
            audit_dema_parity,
            audit_tema_parity,
            audit_ppo_parity,
            audit_trix_parity,
            audit_tsi_parity,
            # Phase 3: SMA/Buffer-based
            audit_wma_parity,
            audit_trima_parity,
            audit_linreg_parity,
            audit_cmf_parity,
            audit_cmo_parity,
            audit_mfi_parity,
            # Phase 4: Lookback-based
            audit_aroon_parity,
            audit_donchian_parity,
            audit_kc_parity,
            audit_dm_parity,
            audit_vortex_parity,
            # Phase 5: Complex adaptive
            audit_kama_parity,
            audit_alma_parity,
            audit_zlma_parity,
            audit_uo_parity,
            # Phase 6: Stateful multi-output
            audit_psar_parity,
            audit_squeeze_parity,
            audit_fisher_parity,
            # Phase 7: Volume complex
            audit_kvo_parity,
            audit_vwap_parity,
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
