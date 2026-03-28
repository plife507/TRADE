"""
Vectorized reference implementation for liquidity zones detection.

Replicates IncrementalLiquidityZones logic in a single-pass loop:
- Tracks swing high/low history from swing detector outputs
- Clusters nearby swings into liquidity zones
- Detects sweeps when price penetrates beyond zone level
- Computes nearest zone accessors per bar

Used by audit_structure_parity.py for parity comparison.
"""

from __future__ import annotations

import math
from collections import deque
from typing import Any

import numpy as np


def vectorized_liquidity_zones(
    ohlcv: dict[str, np.ndarray],
    swing_outputs: dict[str, np.ndarray],
    atr_array: np.ndarray | None = None,
    tolerance_atr: float = 0.3,
    sweep_atr: float = 0.1,
    min_touches: int = 2,
    max_active: int = 5,
    max_swing_history: int = 20,
) -> dict[str, np.ndarray]:
    """
    Compute liquidity zone outputs from OHLCV, swing outputs, and ATR.

    Args:
        ohlcv: Dict with open, high, low, close, volume arrays.
        swing_outputs: Dict with high_idx, high_level, low_idx, low_level arrays.
        atr_array: ATR indicator array (same length as OHLCV). None = no ATR.
        tolerance_atr: Max distance between clustered swings as ATR multiple.
        sweep_atr: Min penetration to count as sweep as ATR multiple.
        min_touches: Min swing touches to form a zone.
        max_active: Max active zones per side.
        max_swing_history: How many swings to track for clustering.

    Returns:
        Dict mapping output key -> numpy array (float64).
    """
    high = ohlcv["high"]
    low = ohlcv["low"]
    close = ohlcv["close"]
    n = len(close)

    # Swing outputs
    swing_high_idx_arr = swing_outputs["high_idx"]
    swing_high_level_arr = swing_outputs["high_level"]
    swing_low_idx_arr = swing_outputs["low_idx"]
    swing_low_level_arr = swing_outputs["low_level"]

    # Output arrays
    out_new_zone_this_bar = np.zeros(n)
    out_sweep_this_bar = np.zeros(n)
    out_sweep_direction = np.zeros(n)
    out_swept_level = np.full(n, np.nan)
    out_nearest_high_level = np.full(n, np.nan)
    out_nearest_low_level = np.full(n, np.nan)
    out_nearest_high_touches = np.zeros(n)
    out_nearest_low_touches = np.zeros(n)
    out_version = np.zeros(n)

    # State
    swing_highs: deque[tuple[int, float]] = deque(maxlen=max_swing_history)
    swing_lows: deque[tuple[int, float]] = deque(maxlen=max_swing_history)
    last_high_idx = -1
    last_low_idx = -1
    zones: list[dict[str, Any]] = []
    version = 0

    for i in range(n):
        # Reset per-bar flags
        new_zone_this_bar = False
        sweep_this_bar = False
        sweep_direction = 0
        swept_level = float("nan")

        # Get ATR
        atr = float("nan")
        if atr_array is not None and i < len(atr_array):
            atr = float(atr_array[i])

        if math.isnan(atr) or atr <= 0:
            # No ATR: recompute nearest only
            _recompute_nearest_vec(
                zones, float(close[i]),
                out_nearest_high_level, out_nearest_low_level,
                out_nearest_high_touches, out_nearest_low_touches, i,
            )
            out_new_zone_this_bar[i] = 0.0
            out_sweep_this_bar[i] = 0.0
            out_sweep_direction[i] = 0.0
            out_swept_level[i] = float("nan")
            out_version[i] = float(version)
            continue

        # Check for new swing pivots
        hi_idx = float(swing_high_idx_arr[i])
        lo_idx = float(swing_low_idx_arr[i])
        hi_level = float(swing_high_level_arr[i])
        lo_level = float(swing_low_level_arr[i])

        if not math.isnan(hi_idx) and int(hi_idx) != last_high_idx and hi_idx >= 0:
            last_high_idx = int(hi_idx)
            if not math.isnan(hi_level):
                swing_highs.append((int(hi_idx), hi_level))
                formed, version = _try_form_zone_vec(
                    "high", swing_highs, atr, tolerance_atr,
                    min_touches, max_active, zones, version,
                )
                if formed:
                    new_zone_this_bar = True

        if not math.isnan(lo_idx) and int(lo_idx) != last_low_idx and lo_idx >= 0:
            last_low_idx = int(lo_idx)
            if not math.isnan(lo_level):
                swing_lows.append((int(lo_idx), lo_level))
                formed, version = _try_form_zone_vec(
                    "low", swing_lows, atr, tolerance_atr,
                    min_touches, max_active, zones, version,
                )
                if formed:
                    new_zone_this_bar = True

        # Check sweeps
        bar_high = float(high[i])
        bar_low = float(low[i])

        for zone in zones:
            if zone["state"] != "active":
                continue

            if zone["side"] == "high" and bar_high > zone["level"] + sweep_atr * atr:
                zone["state"] = "swept"
                zone["sweep_bar_idx"] = i
                sweep_this_bar = True
                sweep_direction = 1
                swept_level = zone["level"]
                version += 1

            elif zone["side"] == "low" and bar_low < zone["level"] - sweep_atr * atr:
                zone["state"] = "swept"
                zone["sweep_bar_idx"] = i
                sweep_this_bar = True
                sweep_direction = -1
                swept_level = zone["level"]
                version += 1

        # Prune swept zones to prevent unbounded growth
        zones = [z for z in zones if z["state"] == "active"]

        # Recompute nearest
        _recompute_nearest_vec(
            zones, float(close[i]),
            out_nearest_high_level, out_nearest_low_level,
            out_nearest_high_touches, out_nearest_low_touches, i,
        )

        # Write outputs
        out_new_zone_this_bar[i] = 1.0 if new_zone_this_bar else 0.0
        out_sweep_this_bar[i] = 1.0 if sweep_this_bar else 0.0
        out_sweep_direction[i] = float(sweep_direction)
        out_swept_level[i] = swept_level
        out_version[i] = float(version)

    return {
        "new_zone_this_bar": out_new_zone_this_bar,
        "sweep_this_bar": out_sweep_this_bar,
        "sweep_direction": out_sweep_direction,
        "swept_level": out_swept_level,
        "nearest_high_level": out_nearest_high_level,
        "nearest_low_level": out_nearest_low_level,
        "nearest_high_touches": out_nearest_high_touches,
        "nearest_low_touches": out_nearest_low_touches,
        "version": out_version,
    }


def _try_form_zone_vec(
    side: str,
    swings: deque[tuple[int, float]],
    atr: float,
    tolerance_atr: float,
    min_touches: int,
    max_active: int,
    zones: list[dict[str, Any]],
    version: int,
) -> tuple[bool, int]:
    """Try to form a zone from clustered swings. Returns (formed, new_version)."""
    if len(swings) < min_touches:
        return False, version

    tolerance = tolerance_atr * atr
    _newest_idx, newest_price = swings[-1]
    cluster_prices = [newest_price]
    for _idx, price in list(swings)[:-1]:
        if abs(price - newest_price) <= tolerance:
            cluster_prices.append(price)

    if len(cluster_prices) >= min_touches:
        avg_level = sum(cluster_prices) / len(cluster_prices)
        # Check for existing zone near this level
        existing = None
        for z in zones:
            if z["side"] == side and z["state"] == "active":
                if abs(z["level"] - avg_level) <= tolerance:
                    existing = z
                    break

        if existing is not None:
            existing["touches"] = len(cluster_prices)
            existing["level"] = avg_level
            return False, version  # Updated but not new
        else:
            zone: dict[str, Any] = {
                "side": side,
                "level": avg_level,
                "touches": len(cluster_prices),
                "state": "active",
                "sweep_bar_idx": -1,
            }
            zones.append(zone)
            version += 1

            # Enforce max_active per side
            active_count = sum(
                1 for z in zones
                if z["side"] == side and z["state"] == "active"
            )
            while active_count > max_active:
                for j, z in enumerate(zones):
                    if z["side"] == side and z["state"] == "active":
                        zones.pop(j)
                        active_count -= 1
                        break

            return True, version

    return False, version


def _recompute_nearest_vec(
    zones: list[dict[str, Any]],
    close: float,
    out_high_level: np.ndarray,
    out_low_level: np.ndarray,
    out_high_touches: np.ndarray,
    out_low_touches: np.ndarray,
    idx: int,
) -> None:
    """Recompute nearest zone levels and write to output arrays."""
    nearest_high_dist = float("inf")
    nearest_low_dist = float("inf")
    nh_level = float("nan")
    nl_level = float("nan")
    nh_touches = 0
    nl_touches = 0

    for zone in zones:
        if zone["state"] != "active":
            continue
        dist = abs(zone["level"] - close)
        if zone["side"] == "high" and dist < nearest_high_dist:
            nearest_high_dist = dist
            nh_level = zone["level"]
            nh_touches = zone["touches"]
        elif zone["side"] == "low" and dist < nearest_low_dist:
            nearest_low_dist = dist
            nl_level = zone["level"]
            nl_touches = zone["touches"]

    out_high_level[idx] = nh_level
    out_low_level[idx] = nl_level
    out_high_touches[idx] = float(nh_touches)
    out_low_touches[idx] = float(nl_touches)
