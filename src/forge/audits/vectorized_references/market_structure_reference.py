"""
Vectorized reference implementation for ICT Market Structure (BOS/CHoCH).

Takes swing output arrays + OHLCV and replicates IncrementalMarketStructure logic:
- Track bias (bullish/bearish/ranging)
- BOS: continuation break
- CHoCH: reversal break
- Event flags reset each bar
"""

from __future__ import annotations

import math

import numpy as np


def vectorized_market_structure(
    ohlcv: dict[str, np.ndarray],
    swing_outputs: dict[str, np.ndarray],
    confirmation_close: bool = False,
) -> dict[str, np.ndarray]:
    """
    Compute market structure (BOS/CHoCH) from swing outputs.

    Args:
        ohlcv: Dict with open, high, low, close, volume arrays.
        swing_outputs: Dict from vectorized_swing().
        confirmation_close: If True, use close for break detection; else use high/low.

    Returns:
        Dict mapping output key -> numpy array.
    """
    high = ohlcv["high"]
    low = ohlcv["low"]
    close = ohlcv["close"]
    n = len(close)

    swing_high_idx_arr = swing_outputs["high_idx"]
    swing_high_level_arr = swing_outputs["high_level"]
    swing_low_idx_arr = swing_outputs["low_idx"]
    swing_low_level_arr = swing_outputs["low_level"]

    out_bias = np.zeros(n)
    out_bos_this_bar = np.zeros(n)
    out_choch_this_bar = np.zeros(n)
    out_bos_direction = np.full(n, np.nan)  # NaN=none, 1=bullish, -1=bearish
    out_choch_direction = np.full(n, np.nan)
    out_last_bos_idx = np.full(n, -1.0)
    out_last_bos_level = np.full(n, np.nan)
    out_last_choch_idx = np.full(n, -1.0)
    out_last_choch_level = np.full(n, np.nan)
    out_break_level_high = np.full(n, np.nan)
    out_break_level_low = np.full(n, np.nan)
    out_version = np.zeros(n)

    # State
    bias = 0
    last_high_idx = -1
    last_low_idx = -1
    prev_swing_high = float("nan")
    prev_swing_low = float("nan")
    break_level_high = float("nan")
    break_level_low = float("nan")
    broken_high_idx = -1
    broken_low_idx = -1
    last_bos_idx = -1
    last_bos_level = float("nan")
    bos_direction_val = float("nan")
    last_choch_idx = -1
    last_choch_level = float("nan")
    choch_direction_val = float("nan")
    version = 0

    for i in range(n):
        # Reset event flags each bar
        bos_this_bar = False
        choch_this_bar = False

        hi_idx = int(swing_high_idx_arr[i])
        lo_idx = int(swing_low_idx_arr[i])
        hi_level = swing_high_level_arr[i]
        lo_level = swing_low_level_arr[i]

        high_changed = hi_idx != last_high_idx and hi_idx >= 0
        low_changed = lo_idx != last_low_idx and lo_idx >= 0

        if high_changed:
            prev_swing_high = hi_level
            last_high_idx = hi_idx
            # Update break level if newer than broken swing
            if not math.isnan(prev_swing_high) and last_high_idx > broken_high_idx:
                break_level_high = prev_swing_high

        if low_changed:
            prev_swing_low = lo_level
            last_low_idx = lo_idx
            if not math.isnan(prev_swing_low) and last_low_idx > broken_low_idx:
                break_level_low = prev_swing_low

        # Check for breaks
        check_high = close[i] if confirmation_close else high[i]
        check_low = close[i] if confirmation_close else low[i]

        if bias == 1:  # Bullish
            # BOS: break above swing high (continuation)
            if not math.isnan(break_level_high) and check_high > break_level_high:
                bos_this_bar = True
                last_bos_idx = i
                last_bos_level = break_level_high
                bos_direction_val = 1.0
                version += 1
                broken_high_idx = last_high_idx
                break_level_high = float("nan")

            # CHoCH: break below swing low (reversal)
            if not math.isnan(break_level_low) and check_low < break_level_low:
                choch_this_bar = True
                last_choch_idx = i
                last_choch_level = break_level_low
                choch_direction_val = -1.0
                bias = -1
                version += 1

        elif bias == -1:  # Bearish
            # BOS: break below swing low (continuation)
            if not math.isnan(break_level_low) and check_low < break_level_low:
                bos_this_bar = True
                last_bos_idx = i
                last_bos_level = break_level_low
                bos_direction_val = -1.0
                version += 1
                broken_low_idx = last_low_idx
                break_level_low = float("nan")

            # CHoCH: break above swing high (reversal)
            if not math.isnan(break_level_high) and check_high > break_level_high:
                choch_this_bar = True
                last_choch_idx = i
                last_choch_level = break_level_high
                choch_direction_val = 1.0
                bias = 1
                version += 1

        else:  # Ranging
            if not math.isnan(break_level_high) and check_high > break_level_high:
                bos_this_bar = True
                last_bos_idx = i
                last_bos_level = break_level_high
                bos_direction_val = 1.0
                bias = 1
                version += 1
                broken_high_idx = last_high_idx
                break_level_high = float("nan")
            elif not math.isnan(break_level_low) and check_low < break_level_low:
                bos_this_bar = True
                last_bos_idx = i
                last_bos_level = break_level_low
                bos_direction_val = -1.0
                bias = -1
                version += 1
                broken_low_idx = last_low_idx
                break_level_low = float("nan")

        out_bias[i] = bias
        out_bos_this_bar[i] = 1.0 if bos_this_bar else 0.0
        out_choch_this_bar[i] = 1.0 if choch_this_bar else 0.0
        out_bos_direction[i] = bos_direction_val
        out_choch_direction[i] = choch_direction_val
        out_last_bos_idx[i] = last_bos_idx
        out_last_bos_level[i] = last_bos_level
        out_last_choch_idx[i] = last_choch_idx
        out_last_choch_level[i] = last_choch_level
        out_break_level_high[i] = break_level_high
        out_break_level_low[i] = break_level_low
        out_version[i] = version

    return {
        "bias": out_bias,
        "bos_this_bar": out_bos_this_bar,
        "choch_this_bar": out_choch_this_bar,
        "bos_direction": out_bos_direction,
        "choch_direction": out_choch_direction,
        "last_bos_idx": out_last_bos_idx,
        "last_bos_level": out_last_bos_level,
        "last_choch_idx": out_last_choch_idx,
        "last_choch_level": out_last_choch_level,
        "break_level_high": out_break_level_high,
        "break_level_low": out_break_level_low,
        "version": out_version,
    }
