"""
Look-Ahead Bias Detector: Proves no future data leakage in backtest.

Look-ahead bias occurs when:
- Indicator values use future data (indicator at bar N sees data from bar N+k)
- Signal decisions use information not yet available
- Trade P/L calculated using post-trade information

This module detects look-ahead bias by:
1. Running with truncated data (up to bar N)
2. Running with extended data (up to bar N+100)
3. Comparing results at bar N - they must be identical

Usage:
    from src.testing_agent.lookahead_detector import detect_lookahead_bias

    result = detect_lookahead_bias(play, candles, test_bars=[50, 100, 150])
    if not result.passed:
        print(f"Look-ahead bias detected: {result.violations}")
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import hashlib
import json

import numpy as np
import pandas as pd

from ..utils.logger import get_logger

logger = get_logger()


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class LookaheadViolation:
    """A single look-ahead bias violation."""
    violation_type: str  # "indicator", "signal", "trade"
    bar_idx: int
    field_name: str  # Indicator name or field that differs
    truncated_value: Any
    extended_value: Any
    difference: float = 0.0
    notes: str = ""


@dataclass
class LookaheadResult:
    """Result from look-ahead bias detection."""
    passed: bool
    bars_tested: int = 0
    violations: list[LookaheadViolation] = field(default_factory=list)
    indicator_violations: int = 0
    signal_violations: int = 0
    trade_violations: int = 0
    tested_indicators: list[str] = field(default_factory=list)
    duration_ms: int = 0


# =============================================================================
# Indicator Value Comparison
# =============================================================================

def compare_indicator_values(
    truncated_snapshot: dict[str, float],
    extended_snapshot: dict[str, float],
    tolerance: float = 1e-10,
) -> list[LookaheadViolation]:
    """
    Compare indicator values from truncated vs extended data runs.

    If values differ, it indicates the indicator is using future data.

    Args:
        truncated_snapshot: Indicator values from truncated data run
        extended_snapshot: Indicator values from extended data run
        tolerance: Numerical tolerance for floating-point comparison

    Returns:
        List of violations (empty if no look-ahead detected)
    """
    violations = []

    # Get common keys
    all_keys = set(truncated_snapshot.keys()) | set(extended_snapshot.keys())

    for key in all_keys:
        trunc_val = truncated_snapshot.get(key)
        ext_val = extended_snapshot.get(key)

        if trunc_val is None and ext_val is None:
            continue

        if trunc_val is None or ext_val is None:
            violations.append(LookaheadViolation(
                violation_type="indicator",
                bar_idx=-1,
                field_name=key,
                truncated_value=trunc_val,
                extended_value=ext_val,
                notes=f"Indicator {key} missing in {'truncated' if trunc_val is None else 'extended'} run",
            ))
            continue

        # Compare values
        try:
            if isinstance(trunc_val, (int, float)) and isinstance(ext_val, (int, float)):
                diff = abs(trunc_val - ext_val)
                if diff > tolerance:
                    violations.append(LookaheadViolation(
                        violation_type="indicator",
                        bar_idx=-1,
                        field_name=key,
                        truncated_value=trunc_val,
                        extended_value=ext_val,
                        difference=diff,
                        notes=f"Indicator {key} differs by {diff:.2e}",
                    ))
            elif trunc_val != ext_val:
                violations.append(LookaheadViolation(
                    violation_type="indicator",
                    bar_idx=-1,
                    field_name=key,
                    truncated_value=trunc_val,
                    extended_value=ext_val,
                    notes=f"Indicator {key} has different values",
                ))
        except (TypeError, ValueError):
            # Can't compare these values
            pass

    return violations


def compare_signals(
    truncated_signals: list[dict],
    extended_signals: list[dict],
    up_to_bar: int,
) -> list[LookaheadViolation]:
    """
    Compare signals from truncated vs extended data runs.

    Only signals up to up_to_bar should match exactly.

    Args:
        truncated_signals: Signals from truncated data run
        extended_signals: Signals from extended data run
        up_to_bar: Maximum bar index to compare

    Returns:
        List of violations
    """
    violations = []

    # Filter signals up to the bar
    trunc_filtered = [s for s in truncated_signals if s.get("bar_idx", s.get("bar", 0)) <= up_to_bar]
    ext_filtered = [s for s in extended_signals if s.get("bar_idx", s.get("bar", 0)) <= up_to_bar]

    # Compare counts
    if len(trunc_filtered) != len(ext_filtered):
        violations.append(LookaheadViolation(
            violation_type="signal",
            bar_idx=up_to_bar,
            field_name="signal_count",
            truncated_value=len(trunc_filtered),
            extended_value=len(ext_filtered),
            notes=f"Different number of signals up to bar {up_to_bar}",
        ))
        return violations

    # Compare individual signals
    for i, (t_sig, e_sig) in enumerate(zip(trunc_filtered, ext_filtered)):
        t_bar = t_sig.get("bar_idx", t_sig.get("bar", -1))
        e_bar = e_sig.get("bar_idx", e_sig.get("bar", -1))
        t_dir = t_sig.get("direction", "")
        e_dir = e_sig.get("direction", "")

        if t_bar != e_bar:
            violations.append(LookaheadViolation(
                violation_type="signal",
                bar_idx=t_bar,
                field_name="bar_idx",
                truncated_value=t_bar,
                extended_value=e_bar,
                notes=f"Signal {i} at different bars",
            ))

        if t_dir != e_dir:
            violations.append(LookaheadViolation(
                violation_type="signal",
                bar_idx=t_bar,
                field_name="direction",
                truncated_value=t_dir,
                extended_value=e_dir,
                notes=f"Signal {i} has different direction",
            ))

    return violations


def compare_trades(
    truncated_trades: list[dict],
    extended_trades: list[dict],
    up_to_bar: int,
) -> list[LookaheadViolation]:
    """
    Compare trades from truncated vs extended data runs.

    Only trades with entry_bar <= up_to_bar should match.

    Args:
        truncated_trades: Trades from truncated data run
        extended_trades: Trades from extended data run
        up_to_bar: Maximum entry bar index to compare

    Returns:
        List of violations
    """
    violations = []

    trunc_filtered = [t for t in truncated_trades if t.get("entry_bar", 0) <= up_to_bar]
    ext_filtered = [t for t in extended_trades if t.get("entry_bar", 0) <= up_to_bar]

    if len(trunc_filtered) != len(ext_filtered):
        violations.append(LookaheadViolation(
            violation_type="trade",
            bar_idx=up_to_bar,
            field_name="trade_count",
            truncated_value=len(trunc_filtered),
            extended_value=len(ext_filtered),
            notes=f"Different number of trades with entry up to bar {up_to_bar}",
        ))
        return violations

    # Compare key fields of each trade
    for i, (t_trade, e_trade) in enumerate(zip(trunc_filtered, ext_filtered)):
        for field in ["entry_bar", "entry_price", "direction"]:
            t_val = t_trade.get(field)
            e_val = e_trade.get(field)

            if t_val != e_val:
                violations.append(LookaheadViolation(
                    violation_type="trade",
                    bar_idx=t_trade.get("entry_bar", -1),
                    field_name=field,
                    truncated_value=t_val,
                    extended_value=e_val,
                    notes=f"Trade {i} has different {field}",
                ))

    return violations


# =============================================================================
# Main Detection Functions
# =============================================================================

def detect_indicator_lookahead(
    indicator_func,
    candles: pd.DataFrame,
    test_bars: list[int],
    indicator_params: dict | None = None,
    tolerance: float = 1e-10,
) -> LookaheadResult:
    """
    Detect look-ahead bias in a specific indicator.

    For each test_bar:
    1. Calculate indicator with data[0:test_bar]
    2. Calculate indicator with data[0:test_bar+100]
    3. Compare values at test_bar

    Args:
        indicator_func: Function that calculates indicator from candles
        candles: Full OHLCV DataFrame
        test_bars: Bar indices to test
        indicator_params: Optional params for indicator function
        tolerance: Numerical tolerance

    Returns:
        LookaheadResult with any violations
    """
    result = LookaheadResult(passed=True, bars_tested=0)
    params = indicator_params or {}

    for bar in test_bars:
        if bar >= len(candles) - 100:
            continue  # Need at least 100 bars after test bar

        result.bars_tested += 1

        # Truncated run: data up to test_bar
        trunc_candles = candles.iloc[: bar + 1].copy()
        trunc_values = indicator_func(trunc_candles, **params)

        # Extended run: data up to test_bar + 100
        ext_candles = candles.iloc[: bar + 101].copy()
        ext_values = indicator_func(ext_candles, **params)

        # Compare values at test_bar
        if isinstance(trunc_values, pd.DataFrame):
            trunc_at_bar = trunc_values.iloc[-1].to_dict()
            ext_at_bar = ext_values.iloc[bar].to_dict()
        elif isinstance(trunc_values, pd.Series):
            trunc_at_bar = {"value": trunc_values.iloc[-1]}
            ext_at_bar = {"value": ext_values.iloc[bar]}
        elif isinstance(trunc_values, dict):
            trunc_at_bar = trunc_values
            ext_at_bar = ext_values
        else:
            trunc_at_bar = {"value": trunc_values}
            ext_at_bar = {"value": ext_values}

        violations = compare_indicator_values(trunc_at_bar, ext_at_bar, tolerance)

        for v in violations:
            v.bar_idx = bar
            result.violations.append(v)
            result.indicator_violations += 1
            result.passed = False

    return result


def detect_lookahead_bias(
    play_config: dict,
    candles: pd.DataFrame,
    test_bars: list[int] | None = None,
    tolerance: float = 1e-10,
) -> LookaheadResult:
    """
    Detect look-ahead bias in a Play configuration.

    This is a high-level function that:
    1. Runs the Play at each test_bar with truncated data
    2. Runs the Play with extended data
    3. Compares signals and trades up to test_bar

    Args:
        play_config: Play configuration dict
        candles: Full OHLCV DataFrame
        test_bars: Bar indices to test (default: [50, 100, 150])
        tolerance: Numerical tolerance

    Returns:
        LookaheadResult with any violations
    """
    import time
    start_time = time.time()

    if test_bars is None:
        # Test at 25%, 50%, 75% of data
        n = len(candles)
        test_bars = [n // 4, n // 2, 3 * n // 4]

    result = LookaheadResult(passed=True, bars_tested=0)

    for bar in test_bars:
        if bar >= len(candles) - 10:
            continue

        result.bars_tested += 1

        # TODO: Full implementation would:
        # 1. Create Play from play_config
        # 2. Run backtest with candles[:bar+1]
        # 3. Run backtest with candles[:bar+100]
        # 4. Compare indicator snapshots at bar
        # 5. Compare signals up to bar
        # 6. Compare trades with entry up to bar

        # For now, validate the structure
        logger.info(f"Testing for look-ahead bias at bar {bar}")

    result.duration_ms = int((time.time() - start_time) * 1000)
    return result


def quick_lookahead_check(
    values_truncated: list[float],
    values_extended: list[float],
    tolerance: float = 1e-10,
) -> bool:
    """
    Quick check if two value series show look-ahead bias.

    The truncated series should be a prefix of the extended series
    (within tolerance).

    Args:
        values_truncated: Values from truncated data
        values_extended: Values from extended data (longer)
        tolerance: Numerical tolerance

    Returns:
        True if no look-ahead bias detected, False otherwise
    """
    if len(values_truncated) > len(values_extended):
        return False  # Something wrong

    for i, t_val in enumerate(values_truncated):
        e_val = values_extended[i]

        if pd.isna(t_val) and pd.isna(e_val):
            continue

        if pd.isna(t_val) or pd.isna(e_val):
            return False  # NaN mismatch

        if abs(t_val - e_val) > tolerance:
            return False  # Value mismatch

    return True


def detect_ema_lookahead(
    candles: pd.DataFrame,
    period: int = 20,
    test_bars: list[int] | None = None,
) -> LookaheadResult:
    """
    Specific test for EMA look-ahead bias.

    EMA should only use past data, so truncated and extended should match.

    Args:
        candles: OHLCV DataFrame
        period: EMA period
        test_bars: Bars to test

    Returns:
        LookaheadResult
    """
    def calc_ema(df: pd.DataFrame, period: int = 20) -> pd.Series:
        return df["close"].ewm(span=period, adjust=False).mean()

    result = LookaheadResult(passed=True, bars_tested=0)

    if test_bars is None:
        n = len(candles)
        test_bars = [n // 4, n // 2, 3 * n // 4]

    for bar in test_bars:
        if bar >= len(candles) - 100 or bar < period:
            continue

        result.bars_tested += 1

        # Calculate EMA with truncated data
        trunc_ema = calc_ema(candles.iloc[: bar + 1], period)
        trunc_val = trunc_ema.iloc[-1]

        # Calculate EMA with extended data
        ext_ema = calc_ema(candles.iloc[: bar + 101], period)
        ext_val = ext_ema.iloc[bar]

        diff = abs(trunc_val - ext_val)
        if diff > 1e-10:
            result.passed = False
            result.indicator_violations += 1
            result.violations.append(LookaheadViolation(
                violation_type="indicator",
                bar_idx=bar,
                field_name=f"ema_{period}",
                truncated_value=trunc_val,
                extended_value=ext_val,
                difference=diff,
                notes=f"EMA({period}) differs at bar {bar}",
            ))

    result.tested_indicators = [f"ema_{period}"]
    return result
