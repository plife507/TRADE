"""
Vectorized reference implementation for demand/supply zone detection.

Takes swing output arrays + OHLCV and replicates IncrementalZone logic:
- Create zone from swing pivot when swing changes
- Track state: none -> active -> broken
- Zone breaks when close crosses boundary
"""

import numpy as np


def vectorized_zone(
    ohlcv: dict[str, np.ndarray],
    swing_outputs: dict[str, np.ndarray],
    zone_type: str,
    width_atr: float,
    atr_values: np.ndarray | None = None,
) -> dict[str, np.ndarray]:
    """
    Compute zone state from swing outputs.

    Args:
        ohlcv: Dict with open, high, low, close, volume arrays.
        swing_outputs: Dict from vectorized_swing().
        zone_type: "demand" or "supply".
        width_atr: ATR multiplier for zone width.
        atr_values: ATR indicator array (same length as OHLCV). If None, width=0.

    Returns:
        Dict mapping output key -> numpy array.
    """
    close = ohlcv["close"]
    n = len(close)

    if zone_type == "demand":
        swing_level_arr = swing_outputs["low_level"]
        swing_idx_arr = swing_outputs["low_idx"]
    else:
        swing_level_arr = swing_outputs["high_level"]
        swing_idx_arr = swing_outputs["high_idx"]

    # Output arrays - use object arrays for state strings
    out_state = np.full(n, np.nan)  # 0=none, 1=active, 2=broken
    out_upper = np.full(n, np.nan)
    out_lower = np.full(n, np.nan)
    out_anchor_idx = np.full(n, -1.0)
    out_version = np.zeros(n)

    state = 0  # 0=none, 1=active, 2=broken
    upper = float("nan")
    lower = float("nan")
    anchor_idx = -1
    last_swing_idx = -1
    version = 0

    for i in range(n):
        swing_idx = int(swing_idx_arr[i])
        swing_level = swing_level_arr[i]

        # Check for new swing
        if swing_idx != last_swing_idx and swing_idx >= 0:
            atr = np.nan
            if atr_values is not None and i < len(atr_values):
                val = atr_values[i]
                if not np.isnan(val):
                    atr = val

            # Skip zone creation when ATR is NaN (matches incremental detector)
            if np.isnan(atr):
                last_swing_idx = swing_idx
            else:
                width = atr * width_atr

                if zone_type == "demand":
                    lower = swing_level - width
                    upper = swing_level
                else:
                    lower = swing_level
                    upper = swing_level + width

                state = 1  # active
                anchor_idx = swing_idx
                last_swing_idx = swing_idx
                version += 1

        # Check for break
        if state == 1:
            if zone_type == "demand" and close[i] < lower:
                state = 2  # broken
                version += 1
            elif zone_type == "supply" and close[i] > upper:
                state = 2  # broken
                version += 1

        out_state[i] = state
        out_upper[i] = upper
        out_lower[i] = lower
        out_anchor_idx[i] = anchor_idx
        out_version[i] = version

    return {
        "state": out_state,
        "upper": out_upper,
        "lower": out_lower,
        "anchor_idx": out_anchor_idx,
        "version": out_version,
    }
