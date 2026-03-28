"""
Vectorized reference implementation for Fair Value Gap detection.

Replicates IncrementalFVG logic in a single-pass loop:
- 3-candle gap detection (bullish: c3_low > c1_high, bearish: c3_high < c1_low)
- Slot-based tracking with mitigation and invalidation
- ATR filtering, nearest accessors, aggregate counts
- Produces identical outputs to the incremental detector

Used by audit_structure_parity.py for parity comparison.
"""

from __future__ import annotations

import math

import numpy as np


def vectorized_fair_value_gap(
    ohlcv: dict[str, np.ndarray],
    atr_array: np.ndarray | None = None,
    min_gap_atr: float = 0.0,
    max_active: int = 5,
) -> dict[str, np.ndarray]:
    """
    Compute FVG outputs from OHLCV data.

    Args:
        ohlcv: Dict with open, high, low, close, volume arrays.
        atr_array: ATR indicator array (same length as OHLCV). None = no ATR filter.
        min_gap_atr: Minimum gap size as ATR multiple (0 = no filter).
        max_active: Maximum tracked active FVG slots.

    Returns:
        Dict mapping output key -> numpy array (float64).
    """
    high = ohlcv["high"]
    low = ohlcv["low"]
    close = ohlcv["close"]
    n = len(close)

    # Output arrays
    out_new_this_bar = np.zeros(n)
    out_new_direction = np.zeros(n)
    out_new_upper = np.full(n, np.nan)
    out_new_lower = np.full(n, np.nan)
    out_nearest_bull_upper = np.full(n, np.nan)
    out_nearest_bull_lower = np.full(n, np.nan)
    out_nearest_bear_upper = np.full(n, np.nan)
    out_nearest_bear_lower = np.full(n, np.nan)
    out_active_bull_count = np.zeros(n)
    out_active_bear_count = np.zeros(n)
    out_any_mitigated_this_bar = np.zeros(n)
    out_nearest_bull_fill_pct = np.full(n, np.nan)
    out_nearest_bear_fill_pct = np.full(n, np.nan)
    out_version = np.zeros(n)

    # State: list of FVG dicts (newest first)
    fvgs: list[dict] = []
    version = 0

    # Candle buffer: (high, low) for last 3 bars
    buf_high: list[float] = []
    buf_low: list[float] = []

    for i in range(n):
        # Reset per-bar flags
        new_this_bar = False
        new_direction = 0
        new_upper = float("nan")
        new_lower = float("nan")
        any_mitigated = False

        # Push current bar to buffer
        buf_high.append(float(high[i]))
        buf_low.append(float(low[i]))
        if len(buf_high) > 3:
            buf_high.pop(0)
            buf_low.pop(0)

        # Check for new FVG if we have 3 candles
        if len(buf_high) >= 3:
            c1_high = buf_high[-3]
            c1_low = buf_low[-3]
            c3_high = buf_high[-1]
            c3_low = buf_low[-1]

            # Get ATR for filtering
            atr_val = float("nan")
            if min_gap_atr > 0 and atr_array is not None and i < len(atr_array):
                atr_val = float(atr_array[i])

            # Bullish FVG: c3_low > c1_high
            if c3_low > c1_high:
                gap_size = c3_low - c1_high
                if _passes_atr_filter(gap_size, atr_val, min_gap_atr):
                    fvg = {
                        "direction": 1,
                        "upper": c3_low,
                        "lower": c1_high,
                        "anchor_idx": i,
                        "state": "active",
                        "fill_pct": 0.0,
                    }
                    fvgs.insert(0, fvg)
                    new_this_bar = True
                    new_direction = 1
                    new_upper = c3_low
                    new_lower = c1_high
                    version += 1

            # Bearish FVG: c3_high < c1_low
            elif c3_high < c1_low:
                gap_size = c1_low - c3_high
                if _passes_atr_filter(gap_size, atr_val, min_gap_atr):
                    fvg = {
                        "direction": -1,
                        "upper": c1_low,
                        "lower": c3_high,
                        "anchor_idx": i,
                        "state": "active",
                        "fill_pct": 0.0,
                    }
                    fvgs.insert(0, fvg)
                    new_this_bar = True
                    new_direction = -1
                    new_upper = c1_low
                    new_lower = c3_high
                    version += 1

        # Update mitigation for all active FVGs
        bar_high = float(high[i])
        bar_low = float(low[i])
        bar_close = float(close[i])

        for fvg in fvgs:
            if fvg["state"] != "active":
                continue

            upper = fvg["upper"]
            lower = fvg["lower"]
            gap_range = upper - lower
            if gap_range <= 0:
                continue

            if fvg["direction"] == 1:
                # Bullish: price dips into gap from above
                if bar_low <= upper:
                    fill = (upper - bar_low) / gap_range
                    fill = min(fill, 1.0)
                    fvg["fill_pct"] = max(fvg["fill_pct"], fill)
                    if fvg["fill_pct"] >= 0.5:
                        fvg["state"] = "mitigated"
                        any_mitigated = True
                if bar_close < lower:
                    fvg["state"] = "invalidated"
            else:
                # Bearish: price rises into gap from below
                if bar_high >= lower:
                    fill = (bar_high - lower) / gap_range
                    fill = min(fill, 1.0)
                    fvg["fill_pct"] = max(fvg["fill_pct"], fill)
                    if fvg["fill_pct"] >= 0.5:
                        fvg["state"] = "mitigated"
                        any_mitigated = True
                if bar_close > upper:
                    fvg["state"] = "invalidated"

        # Prune beyond max_active
        if len(fvgs) > max_active:
            fvgs = fvgs[:max_active]

        # Recompute aggregates
        active_bull_count = 0
        active_bear_count = 0
        nearest_bull_upper = float("nan")
        nearest_bull_lower = float("nan")
        nearest_bear_upper = float("nan")
        nearest_bear_lower = float("nan")
        nearest_bull_dist = float("inf")
        nearest_bear_dist = float("inf")
        nearest_bull_fill_pct = float("nan")
        nearest_bear_fill_pct = float("nan")

        for fvg in fvgs:
            if fvg["state"] != "active":
                continue
            mid = (fvg["upper"] + fvg["lower"]) / 2.0
            dist = abs(bar_close - mid)

            if fvg["direction"] == 1:
                active_bull_count += 1
                if dist < nearest_bull_dist:
                    nearest_bull_dist = dist
                    nearest_bull_upper = fvg["upper"]
                    nearest_bull_lower = fvg["lower"]
                    nearest_bull_fill_pct = fvg["fill_pct"]
            else:
                active_bear_count += 1
                if dist < nearest_bear_dist:
                    nearest_bear_dist = dist
                    nearest_bear_upper = fvg["upper"]
                    nearest_bear_lower = fvg["lower"]
                    nearest_bear_fill_pct = fvg["fill_pct"]

        # Write outputs
        out_new_this_bar[i] = 1.0 if new_this_bar else 0.0
        out_new_direction[i] = float(new_direction)
        out_new_upper[i] = new_upper
        out_new_lower[i] = new_lower
        out_nearest_bull_upper[i] = nearest_bull_upper
        out_nearest_bull_lower[i] = nearest_bull_lower
        out_nearest_bear_upper[i] = nearest_bear_upper
        out_nearest_bear_lower[i] = nearest_bear_lower
        out_active_bull_count[i] = float(active_bull_count)
        out_active_bear_count[i] = float(active_bear_count)
        out_any_mitigated_this_bar[i] = 1.0 if any_mitigated else 0.0
        out_nearest_bull_fill_pct[i] = nearest_bull_fill_pct
        out_nearest_bear_fill_pct[i] = nearest_bear_fill_pct
        out_version[i] = float(version)

    return {
        "new_this_bar": out_new_this_bar,
        "new_direction": out_new_direction,
        "new_upper": out_new_upper,
        "new_lower": out_new_lower,
        "nearest_bull_upper": out_nearest_bull_upper,
        "nearest_bull_lower": out_nearest_bull_lower,
        "nearest_bear_upper": out_nearest_bear_upper,
        "nearest_bear_lower": out_nearest_bear_lower,
        "active_bull_count": out_active_bull_count,
        "active_bear_count": out_active_bear_count,
        "any_mitigated_this_bar": out_any_mitigated_this_bar,
        "nearest_bull_fill_pct": out_nearest_bull_fill_pct,
        "nearest_bear_fill_pct": out_nearest_bear_fill_pct,
        "version": out_version,
    }


def _passes_atr_filter(gap_size: float, atr_val: float, min_gap_atr: float) -> bool:
    """Check if gap passes the ATR minimum filter."""
    if min_gap_atr <= 0:
        return True
    if math.isnan(atr_val) or atr_val <= 0:
        return False
    return gap_size >= min_gap_atr * atr_val
