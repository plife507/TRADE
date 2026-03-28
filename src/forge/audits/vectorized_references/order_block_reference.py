"""
Vectorized reference implementation for Order Block detection.

Replicates IncrementalOrderBlock logic in a single-pass loop:
- Inline displacement detection (ATR body/wick ratio)
- Backward search for opposing candle in candle history
- Slot-based tracking with mitigation and invalidation
- Nearest accessors, aggregate counts
- Produces identical outputs to the incremental detector

Used by audit_structure_parity.py for parity comparison.
"""

from __future__ import annotations

import math
from collections import deque

import numpy as np


def vectorized_order_block(
    ohlcv: dict[str, np.ndarray],
    swing_outputs: dict[str, np.ndarray],
    atr_array: np.ndarray | None = None,
    use_body: bool = True,
    body_atr_min: float = 1.5,
    wick_ratio_max: float = 0.4,
    max_active: int = 5,
    lookback: int = 3,
) -> dict[str, np.ndarray]:
    """
    Compute Order Block outputs from OHLCV data.

    This reference implementation uses inline displacement detection
    (same as incremental when no displacement dep is provided).

    Args:
        ohlcv: Dict with open, high, low, close, volume arrays.
        swing_outputs: Dict of swing detector output arrays (not used in detection
            logic directly, but included for API parity with incremental which
            depends on swing).
        atr_array: ATR indicator array (same length as OHLCV). None = skip detection.
        use_body: If True, OB zone = candle body; False = full range.
        body_atr_min: Minimum body/ATR ratio for displacement detection.
        wick_ratio_max: Maximum wick/body ratio for displacement detection.
        max_active: Maximum tracked active OB slots.
        lookback: How many candles back to search for opposing candle.

    Returns:
        Dict mapping output key -> numpy array (float64).
    """
    open_arr = ohlcv["open"]
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
    out_version = np.zeros(n)

    # State
    obs: list[dict] = []
    version = 0

    # Candle history buffer: (idx, open, high, low, close)
    candle_history: deque[tuple[int, float, float, float, float]] = deque(
        maxlen=lookback + 2
    )

    for i in range(n):
        # Reset per-bar flags
        new_this_bar = False
        new_direction = 0
        new_upper = float("nan")
        new_lower = float("nan")
        any_mitigated = False

        bar_open = float(open_arr[i])
        bar_high = float(high[i])
        bar_low = float(low[i])
        bar_close = float(close[i])

        # Check displacement (inline ATR-based)
        is_disp = False
        disp_dir = 0

        if atr_array is not None and i < len(atr_array):
            atr_val = float(atr_array[i])
            if not math.isnan(atr_val) and atr_val > 0:
                body = abs(bar_close - bar_open)
                if body > 0:
                    upper_wick = bar_high - max(bar_open, bar_close)
                    lower_wick = min(bar_open, bar_close) - bar_low
                    body_atr_ratio = body / atr_val
                    wick_ratio = (upper_wick + lower_wick) / body

                    if body_atr_ratio >= body_atr_min and wick_ratio <= wick_ratio_max:
                        is_disp = True
                        disp_dir = 1 if bar_close > bar_open else -1

        # If displacement, search backward for opposing candle
        if is_disp and disp_dir != 0 and len(candle_history) > 0:
            for j in range(len(candle_history) - 1, -1, -1):
                c_idx, c_open, c_high, c_low, c_close = candle_history[j]

                if disp_dir == 1 and c_close < c_open:
                    # Found bearish candle before bullish displacement
                    if use_body:
                        ob_lower = min(c_open, c_close)
                        ob_upper = max(c_open, c_close)
                    else:
                        ob_lower = c_low
                        ob_upper = c_high

                    if ob_upper > ob_lower:
                        ob = {
                            "direction": 1,
                            "upper": ob_upper,
                            "lower": ob_lower,
                            "anchor_idx": i,
                            "state": "active",
                            "touch_count": 0,
                        }
                        obs.insert(0, ob)
                        new_this_bar = True
                        new_direction = 1
                        new_upper = ob_upper
                        new_lower = ob_lower
                        version += 1
                    break

                elif disp_dir == -1 and c_close > c_open:
                    # Found bullish candle before bearish displacement
                    if use_body:
                        ob_lower = min(c_open, c_close)
                        ob_upper = max(c_open, c_close)
                    else:
                        ob_lower = c_low
                        ob_upper = c_high

                    if ob_upper > ob_lower:
                        ob = {
                            "direction": -1,
                            "upper": ob_upper,
                            "lower": ob_lower,
                            "anchor_idx": i,
                            "state": "active",
                            "touch_count": 0,
                        }
                        obs.insert(0, ob)
                        new_this_bar = True
                        new_direction = -1
                        new_upper = ob_upper
                        new_lower = ob_lower
                        version += 1
                    break

        # Push current candle to history AFTER search
        candle_history.append((i, bar_open, bar_high, bar_low, bar_close))

        # Update mitigation/invalidation for all active OBs
        # Skip mitigation on creation bar -- OBs only mitigated on return
        for ob in obs:
            if ob["state"] != "active":
                continue

            if ob["anchor_idx"] == i:
                continue

            ob_upper = ob["upper"]
            ob_lower = ob["lower"]

            if ob["direction"] == 1:
                # Bullish OB: invalidation takes priority
                if bar_close < ob_lower:
                    ob["state"] = "invalidated"
                elif bar_low <= ob_upper:
                    ob["touch_count"] += 1
                    ob["state"] = "mitigated"
                    any_mitigated = True
            else:
                # Bearish OB: invalidation takes priority
                if bar_close > ob_upper:
                    ob["state"] = "invalidated"
                elif bar_high >= ob_lower:
                    ob["touch_count"] += 1
                    ob["state"] = "mitigated"
                    any_mitigated = True

        # Prune beyond max_active
        if len(obs) > max_active:
            obs = obs[:max_active]

        # Recompute aggregates
        active_bull_count = 0
        active_bear_count = 0
        nearest_bull_upper = float("nan")
        nearest_bull_lower = float("nan")
        nearest_bear_upper = float("nan")
        nearest_bear_lower = float("nan")
        nearest_bull_dist = float("inf")
        nearest_bear_dist = float("inf")

        for ob in obs:
            if ob["state"] != "active":
                continue
            mid = (ob["upper"] + ob["lower"]) / 2.0
            dist = abs(bar_close - mid)

            if ob["direction"] == 1:
                active_bull_count += 1
                if dist < nearest_bull_dist:
                    nearest_bull_dist = dist
                    nearest_bull_upper = ob["upper"]
                    nearest_bull_lower = ob["lower"]
            else:
                active_bear_count += 1
                if dist < nearest_bear_dist:
                    nearest_bear_dist = dist
                    nearest_bear_upper = ob["upper"]
                    nearest_bear_lower = ob["lower"]

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
