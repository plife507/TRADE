"""
Vectorized reference implementation for breaker block detection.

Replicates IncrementalBreakerBlock logic in a single-pass loop:
- Checks for concurrent OB invalidation + CHoCH events
- Creates breaker blocks with flipped polarity
- Tracks mitigation/invalidation with nearest accessors

Used by audit_structure_parity.py for parity comparison.
"""

from __future__ import annotations

import math

import numpy as np


def vectorized_breaker_block(
    ohlcv: dict[str, np.ndarray],
    ob_outputs: dict[str, np.ndarray],
    ms_outputs: dict[str, np.ndarray],
    max_active: int = 5,
) -> dict[str, np.ndarray]:
    """
    Compute breaker block outputs from OHLCV, OB outputs, and MS outputs.

    Args:
        ohlcv: Dict with open, high, low, close, volume arrays.
        ob_outputs: Dict of order_block detector output arrays. Must include
            any_invalidated_this_bar, last_invalidated_direction/upper/lower.
        ms_outputs: Dict of market_structure detector output arrays. Must include
            choch_this_bar.
        max_active: Maximum tracked active breaker slots.

    Returns:
        Dict mapping output key -> numpy array (float64).
    """
    close = ohlcv["close"]
    high = ohlcv["high"]
    low = ohlcv["low"]
    n = len(close)

    ob_invalidated_arr = ob_outputs["any_invalidated_this_bar"]
    ob_inv_dir_arr = ob_outputs["last_invalidated_direction"]
    ob_inv_upper_arr = ob_outputs["last_invalidated_upper"]
    ob_inv_lower_arr = ob_outputs["last_invalidated_lower"]
    ms_choch_arr = ms_outputs["choch_this_bar"]

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
    out_version = np.zeros(n)

    # State
    breakers: list[dict] = []
    version = 0

    for i in range(n):
        # Reset per-bar flags
        new_this_bar = False
        new_direction = 0
        new_upper = float("nan")
        new_lower = float("nan")
        any_mitigated = False

        bar_high = float(high[i])
        bar_low = float(low[i])
        bar_close = float(close[i])

        # Check for concurrent OB invalidation + CHoCH
        ob_inv = float(ob_invalidated_arr[i])
        choch = float(ms_choch_arr[i])

        if ob_inv >= 1.0 and choch >= 1.0:
            inv_dir = int(float(ob_inv_dir_arr[i]))
            inv_upper = float(ob_inv_upper_arr[i])
            inv_lower = float(ob_inv_lower_arr[i])

            if inv_dir != 0 and not math.isnan(inv_upper) and inv_upper > inv_lower:
                # Flip polarity
                breaker_dir = -inv_dir
                brk = {
                    "direction": breaker_dir,
                    "upper": inv_upper,
                    "lower": inv_lower,
                    "anchor_idx": i,
                    "state": "active",
                    "touch_count": 0,
                }
                breakers.insert(0, brk)
                new_this_bar = True
                new_direction = breaker_dir
                new_upper = inv_upper
                new_lower = inv_lower
                version += 1

        # Update mitigation/invalidation
        for brk in breakers:
            if brk["state"] != "active":
                continue
            if brk["anchor_idx"] == i:
                continue

            b_upper = brk["upper"]
            b_lower = brk["lower"]

            if brk["direction"] == 1:
                # Bullish breaker (support): invalidation takes priority
                if bar_close < b_lower:
                    brk["state"] = "invalidated"
                elif bar_low <= b_upper:
                    brk["touch_count"] += 1
                    brk["state"] = "mitigated"
                    any_mitigated = True
            else:
                # Bearish breaker (resistance): invalidation takes priority
                if bar_close > b_upper:
                    brk["state"] = "invalidated"
                elif bar_high >= b_lower:
                    brk["touch_count"] += 1
                    brk["state"] = "mitigated"
                    any_mitigated = True

        # Prune beyond max_active
        if len(breakers) > max_active:
            breakers = breakers[:max_active]

        # Recompute aggregates
        active_bull_count = 0
        active_bear_count = 0
        nearest_bull_upper = float("nan")
        nearest_bull_lower = float("nan")
        nearest_bear_upper = float("nan")
        nearest_bear_lower = float("nan")
        nearest_bull_dist = float("inf")
        nearest_bear_dist = float("inf")

        for brk in breakers:
            if brk["state"] != "active":
                continue
            mid = (brk["upper"] + brk["lower"]) / 2.0
            dist = abs(bar_close - mid)

            if brk["direction"] == 1:
                active_bull_count += 1
                if dist < nearest_bull_dist:
                    nearest_bull_dist = dist
                    nearest_bull_upper = brk["upper"]
                    nearest_bull_lower = brk["lower"]
            else:
                active_bear_count += 1
                if dist < nearest_bear_dist:
                    nearest_bear_dist = dist
                    nearest_bear_upper = brk["upper"]
                    nearest_bear_lower = brk["lower"]

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
        "version": out_version,
    }
