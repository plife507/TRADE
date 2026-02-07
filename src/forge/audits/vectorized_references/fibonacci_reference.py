"""
Vectorized reference implementation for Fibonacci retracement/extension.

Takes swing output arrays and replicates IncrementalFibonacci logic:
- Track swing changes (high_idx/low_idx or pair_version)
- Recompute levels when anchors change
- Forward-fill outputs

Supports three anchoring modes:
- Unpaired (use_paired_anchor=False): uses high_idx/low_idx
- Paired (use_paired_anchor=True): uses pair_version/pair_high_level/pair_low_level
- Trend-wave (use_trend_anchor=True): uses trend direction + paired swing levels
"""

from __future__ import annotations

import math

import numpy as np


def vectorized_fibonacci(
    swing_outputs: dict[str, np.ndarray],
    levels: list[float],
    mode: str = "retracement",
    use_paired_anchor: bool = True,
    use_trend_anchor: bool = False,
    trend_outputs: dict[str, np.ndarray] | None = None,
) -> dict[str, np.ndarray]:
    """
    Compute Fibonacci levels from swing outputs.

    Args:
        swing_outputs: Dict from vectorized_swing().
        levels: List of Fibonacci ratios (e.g., [0.382, 0.5, 0.618]).
        mode: "retracement", "extension", "extension_up", or "extension_down".
        use_paired_anchor: If True, use pair_* outputs for anchoring.
        use_trend_anchor: If True, use trend direction for anchoring.
        trend_outputs: Dict from vectorized_trend() (required if use_trend_anchor).

    Returns:
        Dict mapping output key -> numpy array.
    """
    n = len(swing_outputs["high_level"])

    # Build output key names matching IncrementalFibonacci._format_level_key
    level_keys = [f"level_{lvl:g}" for lvl in levels]

    # Initialize all outputs
    outputs: dict[str, np.ndarray] = {}
    for key in level_keys:
        outputs[key] = np.full(n, np.nan)
    outputs["anchor_high"] = np.full(n, np.nan)
    outputs["anchor_low"] = np.full(n, np.nan)
    outputs["range"] = np.full(n, np.nan)
    outputs["anchor_direction"] = np.full(n, np.nan)  # Encode: NaN=empty
    outputs["anchor_hash"] = np.full(n, np.nan)  # Skip in comparison
    outputs["anchor_trend_direction"] = np.zeros(n)  # 0 = not trend mode

    if use_trend_anchor:
        return _vectorized_fibonacci_trend(
            swing_outputs, trend_outputs, levels, level_keys, mode, n, outputs,
        )

    # State tracking
    if use_paired_anchor:
        pair_version_arr = swing_outputs["pair_version"]
        pair_high_arr = swing_outputs["pair_high_level"]
        pair_low_arr = swing_outputs["pair_low_level"]
        pair_dir_arr = swing_outputs["pair_direction"]
        last_pair_version = -1
    else:
        high_idx_arr = swing_outputs["high_idx"]
        low_idx_arr = swing_outputs["low_idx"]
        high_level_arr = swing_outputs["high_level"]
        low_level_arr = swing_outputs["low_level"]
        last_high_idx = -1
        last_low_idx = -1

    # Forward-filled current values
    cur_values: dict[str, float] = {}
    for key in level_keys:
        cur_values[key] = float("nan")
    cur_values["anchor_high"] = float("nan")
    cur_values["anchor_low"] = float("nan")
    cur_values["range"] = float("nan")
    cur_anchor_dir = float("nan")
    cur_trend_dir = 0.0

    for i in range(n):
        changed = False

        if use_paired_anchor:
            pv = int(pair_version_arr[i])
            if pv != last_pair_version and pv > 0:
                high = pair_high_arr[i]
                low = pair_low_arr[i]
                direction_val = pair_dir_arr[i]
                last_pair_version = pv
                changed = True
        else:
            hi = int(high_idx_arr[i])
            lo = int(low_idx_arr[i])
            if (hi != last_high_idx or lo != last_low_idx) and hi >= 0 and lo >= 0:
                high = high_level_arr[i]
                low = low_level_arr[i]
                direction_val = float("nan")
                last_high_idx = hi
                last_low_idx = lo
                changed = True

        if changed and not (math.isnan(high) or math.isnan(low)):
            range_val = high - low
            cur_values["anchor_high"] = high
            cur_values["anchor_low"] = low
            cur_values["range"] = range_val

            if use_paired_anchor:
                cur_anchor_dir = direction_val
                # Determine direction string equivalent
                if direction_val == 1.0:
                    direction = "bullish"
                elif direction_val == -1.0:
                    direction = "bearish"
                else:
                    direction = ""
            else:
                direction = ""

            for lvl, key in zip(levels, level_keys):
                if mode == "retracement":
                    cur_values[key] = high - (range_val * lvl)
                elif mode == "extension":
                    if direction == "bullish":
                        cur_values[key] = high + (range_val * lvl)
                    elif direction == "bearish":
                        cur_values[key] = low - (range_val * lvl)
                    else:
                        cur_values[key] = float("nan")
                elif mode == "extension_up":
                    cur_values[key] = high + (range_val * lvl)
                elif mode == "extension_down":
                    cur_values[key] = low - (range_val * lvl)

        # Write forward-filled values
        for key in level_keys:
            outputs[key][i] = cur_values[key]
        outputs["anchor_high"][i] = cur_values["anchor_high"]
        outputs["anchor_low"][i] = cur_values["anchor_low"]
        outputs["range"][i] = cur_values["range"]
        outputs["anchor_direction"][i] = cur_anchor_dir
        outputs["anchor_trend_direction"][i] = cur_trend_dir

    return outputs


def _vectorized_fibonacci_trend(
    swing_outputs: dict[str, np.ndarray],
    trend_outputs: dict[str, np.ndarray] | None,
    levels: list[float],
    level_keys: list[str],
    mode: str,
    n: int,
    outputs: dict[str, np.ndarray],
) -> dict[str, np.ndarray]:
    """
    Trend-wave anchored fibonacci computation.

    Recalculates when trend version or pair version changes.
    Skips recalculation when direction == 0 (ranging).
    """
    if trend_outputs is None:
        return outputs

    trend_direction_arr = trend_outputs["direction"]
    trend_version_arr = trend_outputs["version"]
    pair_version_arr = swing_outputs["pair_version"]
    pair_high_arr = swing_outputs["pair_high_level"]
    pair_low_arr = swing_outputs["pair_low_level"]

    last_trend_version = -1
    last_pair_version = -1

    # Forward-filled current values
    cur_values: dict[str, float] = {}
    for key in level_keys:
        cur_values[key] = float("nan")
    cur_values["anchor_high"] = float("nan")
    cur_values["anchor_low"] = float("nan")
    cur_values["range"] = float("nan")
    cur_anchor_dir = float("nan")
    cur_trend_dir = 0.0

    for i in range(n):
        tv = int(trend_version_arr[i])
        pv = int(pair_version_arr[i])

        if tv != last_trend_version or pv != last_pair_version:
            direction = int(trend_direction_arr[i])

            if direction != 0:
                high = pair_high_arr[i]
                low = pair_low_arr[i]

                if not (math.isnan(high) or math.isnan(low)):
                    range_val = high - low
                    cur_values["anchor_high"] = high
                    cur_values["anchor_low"] = low
                    cur_values["range"] = range_val
                    cur_trend_dir = float(direction)
                    cur_anchor_dir = 1.0 if direction == 1 else -1.0

                    dir_str = "bullish" if direction == 1 else "bearish"
                    for lvl, key in zip(levels, level_keys):
                        if mode == "retracement":
                            cur_values[key] = high - (range_val * lvl)
                        elif mode == "extension":
                            if dir_str == "bullish":
                                cur_values[key] = high + (range_val * lvl)
                            else:
                                cur_values[key] = low - (range_val * lvl)
                        elif mode == "extension_up":
                            cur_values[key] = high + (range_val * lvl)
                        elif mode == "extension_down":
                            cur_values[key] = low - (range_val * lvl)

            last_trend_version = tv
            last_pair_version = pv

        # Write forward-filled values
        for key in level_keys:
            outputs[key][i] = cur_values[key]
        outputs["anchor_high"][i] = cur_values["anchor_high"]
        outputs["anchor_low"][i] = cur_values["anchor_low"]
        outputs["range"][i] = cur_values["range"]
        outputs["anchor_direction"][i] = cur_anchor_dir
        outputs["anchor_trend_direction"][i] = cur_trend_dir

    return outputs
