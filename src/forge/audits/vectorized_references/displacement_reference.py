"""
Vectorized reference implementation for displacement detection.

Simple loop-based reference that computes the same logic as
IncrementalDisplacement for parity auditing.
"""

import numpy as np


def vectorized_displacement(
    ohlcv: dict[str, np.ndarray],
    atr_array: np.ndarray,
    body_atr_min: float = 1.5,
    wick_ratio_max: float = 0.4,
) -> dict[str, np.ndarray]:
    """
    Compute displacement detection from OHLCV and ATR arrays.

    Args:
        ohlcv: Dict with open, high, low, close, volume arrays.
        atr_array: ATR indicator array (same length as OHLCV).
        body_atr_min: Minimum body/ATR ratio for displacement.
        wick_ratio_max: Maximum wick/body ratio for displacement.

    Returns:
        Dict mapping output key -> numpy array.
    """
    open_arr = ohlcv["open"]
    high = ohlcv["high"]
    low = ohlcv["low"]
    close = ohlcv["close"]
    n = len(close)

    # Output arrays
    out_is_displacement = np.zeros(n)
    out_direction = np.zeros(n)
    out_body_atr_ratio = np.full(n, np.nan)
    out_wick_ratio = np.full(n, np.nan)
    out_last_idx = np.full(n, -1.0)
    out_last_direction = np.zeros(n)
    out_version = np.zeros(n)

    # Persistent state
    last_displacement_idx = -1
    last_displacement_dir = 0
    version = 0

    for i in range(n):
        # Per-bar reset
        is_disp = False
        direction = 0
        body_atr_ratio = np.nan
        wick_ratio = np.nan

        # Get ATR
        atr = atr_array[i] if i < len(atr_array) else np.nan
        if np.isnan(atr) or atr <= 0:
            out_is_displacement[i] = 0.0
            out_direction[i] = 0
            out_body_atr_ratio[i] = np.nan
            out_wick_ratio[i] = np.nan
            out_last_idx[i] = float(last_displacement_idx)
            out_last_direction[i] = float(last_displacement_dir)
            out_version[i] = float(version)
            continue

        # Compute body and wicks
        body = abs(close[i] - open_arr[i])

        if body == 0:
            body_atr_ratio = 0.0
            wick_ratio = float("inf")
        else:
            upper_wick = high[i] - max(open_arr[i], close[i])
            lower_wick = min(open_arr[i], close[i]) - low[i]
            body_atr_ratio = body / atr
            wick_ratio = (upper_wick + lower_wick) / body

            # Check displacement criteria
            if body_atr_ratio >= body_atr_min and wick_ratio <= wick_ratio_max:
                is_disp = True
                direction = 1 if close[i] > open_arr[i] else -1
                last_displacement_idx = i
                last_displacement_dir = direction
                version += 1

        out_is_displacement[i] = 1.0 if is_disp else 0.0
        out_direction[i] = float(direction)
        out_body_atr_ratio[i] = body_atr_ratio
        out_wick_ratio[i] = wick_ratio
        out_last_idx[i] = float(last_displacement_idx)
        out_last_direction[i] = float(last_displacement_dir)
        out_version[i] = float(version)

    return {
        "is_displacement": out_is_displacement,
        "direction": out_direction,
        "body_atr_ratio": out_body_atr_ratio,
        "wick_ratio": out_wick_ratio,
        "last_idx": out_last_idx,
        "last_direction": out_last_direction,
        "version": out_version,
    }
