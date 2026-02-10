"""
Vectorized reference implementation for derived zone detector.

Replicates IncrementalDerivedZone logic:
- Zones created from swing levels at fibonacci-like ratios
- K slots pattern (most recent first)
- Track active/broken state, touch counts, closest zone aggregates
- Version-triggered regeneration
"""

import hashlib
import struct
from typing import Any

import numpy as np


def vectorized_derived_zone(
    ohlcv: dict[str, np.ndarray],
    swing_outputs: dict[str, np.ndarray],
    levels: list[float],
    max_active: int,
    mode: str = "retracement",
    width_pct: float = 0.002,
    use_paired_source: bool = True,
    break_tolerance_pct: float = 0.001,
) -> dict[str, np.ndarray]:
    """
    Compute derived zones from swing outputs.

    Args:
        ohlcv: Dict with open, high, low, close, volume arrays.
        swing_outputs: Dict from vectorized_swing().
        levels: List of ratios for zone placement.
        max_active: Maximum number of active zones.
        mode: "retracement" or "extension".
        width_pct: Zone width as percentage of level price.
        use_paired_source: If True, trigger on pair_version changes.
        break_tolerance_pct: Tolerance for zone break detection.

    Returns:
        Dict mapping output key -> numpy array (slot + aggregate fields).
    """
    close_arr = ohlcv["close"]
    n = len(close_arr)

    version_key = "pair_version" if use_paired_source else "version"
    version_arr = swing_outputs[version_key]

    if use_paired_source:
        hi_level_arr = swing_outputs["pair_high_level"]
        lo_level_arr = swing_outputs["pair_low_level"]
        hi_idx_arr = swing_outputs["pair_high_idx"]
        lo_idx_arr = swing_outputs["pair_low_idx"]
    else:
        hi_level_arr = swing_outputs["high_level"]
        lo_level_arr = swing_outputs["low_level"]
        hi_idx_arr = swing_outputs["high_idx"]
        lo_idx_arr = swing_outputs["low_idx"]

    # Slot fields
    SLOT_FIELDS = [
        "lower", "upper", "state", "anchor_idx", "age_bars",
        "touched_this_bar", "touch_count", "last_touch_age",
        "inside", "instance_id"
    ]

    # Init output arrays
    outputs: dict[str, np.ndarray] = {}
    for slot in range(max_active):
        for field in SLOT_FIELDS:
            key = f"zone{slot}_{field}"
            if field in ("lower", "upper"):
                outputs[key] = np.full(n, np.nan)
            elif field == "state":
                outputs[key] = np.zeros(n)  # 0=none
            elif field in ("anchor_idx", "last_touch_age"):
                outputs[key] = np.full(n, -1.0)
            elif field == "age_bars":
                outputs[key] = np.full(n, -1.0)
            elif field in ("touched_this_bar", "inside"):
                outputs[key] = np.zeros(n)
            elif field == "touch_count":
                outputs[key] = np.zeros(n)
            elif field == "instance_id":
                outputs[key] = np.zeros(n)

    outputs["active_count"] = np.zeros(n)
    outputs["any_active"] = np.zeros(n)
    outputs["any_touched"] = np.zeros(n)
    outputs["any_inside"] = np.zeros(n)
    outputs["first_active_lower"] = np.full(n, np.nan)
    outputs["first_active_upper"] = np.full(n, np.nan)
    outputs["first_active_idx"] = np.full(n, -1.0)
    outputs["newest_active_idx"] = np.full(n, -1.0)
    outputs["source_version"] = np.zeros(n)

    # Internal zone storage
    zones: list[dict[str, Any]] = []
    source_version = 0

    for bar_idx in range(n):
        cur_version = int(version_arr[bar_idx])

        # REGEN PATH: source version changed
        if cur_version != source_version:
            high_level = hi_level_arr[bar_idx]
            low_level = lo_level_arr[bar_idx]
            high_idx = int(hi_idx_arr[bar_idx])
            low_idx = int(lo_idx_arr[bar_idx])

            if not (np.isnan(high_level) or np.isnan(low_level)) and high_idx >= 0 and low_idx >= 0:
                range_val = high_level - low_level
                if range_val > 0:
                    for level in levels:
                        if mode == "retracement":
                            center = high_level - (range_val * level)
                        else:
                            center = high_level + (range_val * level)

                        width = center * width_pct
                        lower = center - width / 2
                        upper = center + width / 2

                        # Compute hash matching IncrementalDerivedZone._compute_zone_hash
                        instance_id = _compute_zone_hash(
                            source_version, high_idx, low_idx, level, mode
                        )

                        new_zone = {
                            "lower": lower,
                            "upper": upper,
                            "state": 1,  # active
                            "anchor_idx": bar_idx,
                            "age_bars": 0,
                            "touched_this_bar": False,
                            "touch_count": 0,
                            "last_touch_bar": -1,
                            "inside": False,
                            "instance_id": instance_id,
                        }
                        zones.insert(0, new_zone)

                    # Enforce max_active
                    while len(zones) > max_active:
                        zones.pop()

            source_version = cur_version

        # INTERACTION PATH: check touches, breaks, age updates
        price = close_arr[bar_idx]

        any_touched_flag = False
        any_inside_flag = False

        for zone in zones:
            # Reset event flag each bar
            zone["touched_this_bar"] = False

            if zone["state"] != 1:  # not active
                zone["age_bars"] = bar_idx - zone["anchor_idx"]
                zone["inside"] = False
                continue

            # Update age
            zone["age_bars"] = bar_idx - zone["anchor_idx"]

            lower = zone["lower"]
            upper = zone["upper"]

            # Check inside
            currently_inside = lower <= price <= upper

            if currently_inside:
                zone["touched_this_bar"] = True
                zone["touch_count"] += 1
                zone["last_touch_bar"] = bar_idx
                any_touched_flag = True
                any_inside_flag = True

            zone["inside"] = currently_inside

            # Check break: price beyond boundary with tolerance
            break_tol = 1.0 - break_tolerance_pct
            break_tol_upper = 1.0 + break_tolerance_pct
            if price < lower * break_tol:
                zone["state"] = 2  # broken
            elif price > upper * break_tol_upper:
                zone["state"] = 2  # broken

        # Compute aggregates
        # NOTE: first_active_* returns the FIRST active zone (lowest slot
        # index), not the closest by distance. Both incremental and vectorized
        # implementations match this behavior.
        active_count = 0
        first_active_idx = -1
        first_active_lower = float("nan")
        first_active_upper = float("nan")
        newest_active_idx = -1

        for slot_idx, zone in enumerate(zones):
            if zone["state"] == 1:
                active_count += 1
                if first_active_idx == -1:
                    first_active_idx = slot_idx
                    first_active_lower = zone["lower"]
                    first_active_upper = zone["upper"]
                if newest_active_idx == -1:
                    newest_active_idx = slot_idx

        # Write slot outputs
        for slot in range(max_active):
            if slot < len(zones):
                z = zones[slot]
                outputs[f"zone{slot}_lower"][bar_idx] = z["lower"]
                outputs[f"zone{slot}_upper"][bar_idx] = z["upper"]
                outputs[f"zone{slot}_state"][bar_idx] = z["state"]
                outputs[f"zone{slot}_anchor_idx"][bar_idx] = z["anchor_idx"]
                outputs[f"zone{slot}_age_bars"][bar_idx] = z["age_bars"]
                outputs[f"zone{slot}_touched_this_bar"][bar_idx] = 1.0 if z["touched_this_bar"] else 0.0
                outputs[f"zone{slot}_touch_count"][bar_idx] = z["touch_count"]
                ltb = z["last_touch_bar"]
                outputs[f"zone{slot}_last_touch_age"][bar_idx] = (bar_idx - ltb) if ltb >= 0 else -1
                outputs[f"zone{slot}_inside"][bar_idx] = 1.0 if z["inside"] else 0.0
                outputs[f"zone{slot}_instance_id"][bar_idx] = z["instance_id"]

        outputs["active_count"][bar_idx] = active_count
        outputs["any_active"][bar_idx] = 1.0 if active_count > 0 else 0.0
        outputs["any_touched"][bar_idx] = 1.0 if any_touched_flag else 0.0
        outputs["any_inside"][bar_idx] = 1.0 if any_inside_flag else 0.0
        outputs["first_active_lower"][bar_idx] = first_active_lower
        outputs["first_active_upper"][bar_idx] = first_active_upper
        outputs["first_active_idx"][bar_idx] = first_active_idx
        outputs["newest_active_idx"][bar_idx] = newest_active_idx
        outputs["source_version"][bar_idx] = source_version

    return outputs


def _compute_zone_hash(
    source_version: int,
    pivot_high_idx: int,
    pivot_low_idx: int,
    level: float,
    mode: str,
) -> int:
    """Compute stable zone hash matching IncrementalDerivedZone._compute_zone_hash."""
    level_scaled = int(round(level * 1_000_000))
    data = (
        f"derived_zone|"
        f"{source_version}|"
        f"{pivot_high_idx}|"
        f"{pivot_low_idx}|"
        f"{level_scaled}|"
        f"{mode}"
    ).encode("utf-8")
    digest = hashlib.blake2b(data, digest_size=4).digest()
    return struct.unpack(">I", digest)[0]
