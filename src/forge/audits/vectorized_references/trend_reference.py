"""
Vectorized reference implementation for wave-based trend detection.

Takes swing output arrays and replicates IncrementalTrend logic:
- Detect new swings (where idx changes)
- Form waves from alternating swing points
- Classify trend from wave sequence (HH/HL/LH/LL)
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

import numpy as np


@dataclass
class RefWave:
    """A wave for the reference implementation."""

    start_type: str
    start_level: float
    start_idx: int
    end_type: str
    end_level: float
    end_idx: int
    direction: str  # "bullish" or "bearish"
    is_higher_high: bool | None = None
    is_higher_low: bool | None = None
    is_lower_high: bool | None = None
    is_lower_low: bool | None = None


def vectorized_trend(
    swing_outputs: dict[str, np.ndarray],
    wave_history_size: int = 4,
) -> dict[str, np.ndarray]:
    """
    Compute trend classification from swing outputs.

    Args:
        swing_outputs: Dict from vectorized_swing() with high_idx, high_level, etc.
        wave_history_size: Max waves to keep.

    Returns:
        Dict mapping output key -> numpy array.
    """
    high_level_arr = swing_outputs["high_level"]
    high_idx_arr = swing_outputs["high_idx"]
    low_level_arr = swing_outputs["low_level"]
    low_idx_arr = swing_outputs["low_idx"]
    n = len(high_level_arr)

    out_direction = np.zeros(n)
    out_strength = np.zeros(n)
    out_bars_in_trend = np.zeros(n)
    out_wave_count = np.zeros(n)
    out_last_wave_direction = np.full(n, np.nan)  # NaN=none, 1=bullish, -1=bearish
    out_last_hh = np.zeros(n)
    out_last_hl = np.zeros(n)
    out_last_lh = np.zeros(n)
    out_last_ll = np.zeros(n)
    out_version = np.zeros(n)

    # State
    waves: deque[RefWave] = deque(maxlen=wave_history_size)
    prev_high = float("nan")
    prev_low = float("nan")
    last_high_idx = -1
    last_low_idx = -1
    pending_type: str | None = None
    pending_level = float("nan")
    pending_idx = -1

    direction = 0
    strength = 0
    bars_in_trend = 0
    wave_count = 0
    last_wave_dir_val = float("nan")
    last_hh = False
    last_hl = False
    last_lh = False
    last_ll = False
    version = 0

    for bar_idx in range(n):
        hi_idx = int(high_idx_arr[bar_idx])
        lo_idx = int(low_idx_arr[bar_idx])
        hi_level = high_level_arr[bar_idx]
        lo_level = low_level_arr[bar_idx]

        high_changed = hi_idx != last_high_idx and hi_idx >= 0
        low_changed = lo_idx != last_low_idx and lo_idx >= 0

        if not high_changed and not low_changed:
            bars_in_trend += 1
        else:
            # Build events sorted by index
            events = []
            if high_changed:
                events.append(("high", hi_level, hi_idx))
            if low_changed:
                events.append(("low", lo_level, lo_idx))
            events.sort(key=lambda e: e[2])

            for pivot_type, level, idx in events:
                _process_trend_swing(
                    pivot_type, level, idx,
                    waves, prev_high, prev_low,
                    pending_type, pending_level, pending_idx,
                )
                # Inline the state updates that _process_trend_swing would do
                if pending_type is None:
                    pending_type = pivot_type
                    pending_level = level
                    pending_idx = idx
                elif pivot_type == pending_type:
                    if pivot_type == "high" and level >= pending_level:
                        pending_level = level
                        pending_idx = idx
                    elif pivot_type == "low" and level <= pending_level:
                        pending_level = level
                        pending_idx = idx
                else:
                    # Opposite type - complete wave
                    wave_dir = "bullish" if pending_type == "low" else "bearish"
                    wave = RefWave(
                        start_type=pending_type,
                        start_level=pending_level,
                        start_idx=pending_idx,
                        end_type=pivot_type,
                        end_level=level,
                        end_idx=idx,
                        direction=wave_dir,
                    )
                    # Compare END only (use bool() to avoid numpy bool_ which
                    # fails identity checks like `x is True`)
                    if pivot_type == "high" and not math.isnan(prev_high):
                        wave.is_higher_high = bool(level > prev_high)
                        wave.is_lower_high = bool(level < prev_high)
                    if pivot_type == "low" and not math.isnan(prev_low):
                        wave.is_lower_low = bool(level < prev_low)
                        wave.is_higher_low = bool(level > prev_low)

                    waves.append(wave)
                    _update_comparison_outputs_ref(wave)

                    # Update trend outputs from wave
                    last_wave_dir_val = 1.0 if wave.direction == "bullish" else -1.0
                    if wave.end_type == "high":
                        if wave.is_higher_high is not None:
                            last_hh = wave.is_higher_high
                            last_lh = wave.is_lower_high if wave.is_lower_high is not None else not wave.is_higher_high
                    if wave.end_type == "low":
                        if wave.is_lower_low is not None:
                            last_ll = wave.is_lower_low
                            last_hl = wave.is_higher_low if wave.is_higher_low is not None else not wave.is_lower_low

                    # Reclassify trend
                    new_dir, new_strength, new_wave_count = _classify_trend_ref(waves)
                    if new_dir != direction:
                        direction = new_dir
                        bars_in_trend = 0
                        version += 1
                    else:
                        bars_in_trend += 1
                    strength = new_strength
                    wave_count = new_wave_count

                    # Start new pending
                    pending_type = pivot_type
                    pending_level = level
                    pending_idx = idx

            if high_changed:
                prev_high = hi_level
                last_high_idx = hi_idx
            if low_changed:
                prev_low = lo_level
                last_low_idx = lo_idx

        out_direction[bar_idx] = direction
        out_strength[bar_idx] = strength
        out_bars_in_trend[bar_idx] = bars_in_trend
        out_wave_count[bar_idx] = wave_count
        out_last_wave_direction[bar_idx] = last_wave_dir_val
        out_last_hh[bar_idx] = 1.0 if last_hh else 0.0
        out_last_hl[bar_idx] = 1.0 if last_hl else 0.0
        out_last_lh[bar_idx] = 1.0 if last_lh else 0.0
        out_last_ll[bar_idx] = 1.0 if last_ll else 0.0
        out_version[bar_idx] = version

    return {
        "direction": out_direction,
        "strength": out_strength,
        "bars_in_trend": out_bars_in_trend,
        "wave_count": out_wave_count,
        "last_wave_direction": out_last_wave_direction,
        "last_hh": out_last_hh,
        "last_hl": out_last_hl,
        "last_lh": out_last_lh,
        "last_ll": out_last_ll,
        "version": out_version,
    }


def _process_trend_swing(
    pivot_type: str, level: float, idx: int,
    waves: deque, prev_high: float, prev_low: float,
    pending_type: str | None, pending_level: float, pending_idx: int,
) -> None:
    """No-op placeholder - actual logic inlined in main loop for state access."""
    pass


def _update_comparison_outputs_ref(wave: RefWave) -> None:
    """No-op placeholder - comparison updates inlined in main loop."""
    pass


def _classify_trend_ref(waves: deque[RefWave]) -> tuple[int, int, int]:
    """Classify trend from wave history (matches IncrementalTrend._classify_trend)."""
    if len(waves) < 1:
        return (0, 0, 0)

    if len(waves) == 1:
        wave = waves[-1]
        d = 1 if wave.direction == "bullish" else -1
        return (d, 0, 1)

    # Multiple waves - analyze sequence
    return _analyze_wave_sequence_ref(waves)


def _analyze_wave_sequence_ref(waves: deque[RefWave]) -> tuple[int, int, int]:
    """Analyze wave sequence for trend direction and strength."""
    if len(waves) < 2:
        return (0, 0, 0)

    recent = waves[-1]
    prev = waves[-2]

    if recent.direction == "bullish":
        high_wave = recent
        low_wave = prev if prev.direction == "bearish" else None
    else:
        low_wave = recent
        high_wave = prev if prev.direction == "bullish" else None

    has_hh = high_wave is not None and high_wave.is_higher_high is True
    has_lh = high_wave is not None and high_wave.is_lower_high is True
    has_hl = low_wave is not None and low_wave.is_higher_low is True
    has_ll = low_wave is not None and low_wave.is_lower_low is True

    if has_hh and has_hl:
        target_dir = 1
    elif has_lh and has_ll:
        target_dir = -1
    elif has_hh and not has_ll:
        target_dir = 1
    elif has_lh and not has_hl:
        target_dir = -1
    elif has_hl and not has_lh:
        target_dir = 1
    elif has_ll and not has_hh:
        target_dir = -1
    else:
        return (0, 0, 0)

    # Count consecutive wave pairs
    consecutive = 1
    for i in range(len(waves) - 3, -1, -2):
        if i < 0:
            break
        pair_recent = waves[i + 1]
        pair_prev = waves[i]
        pair_dir = _classify_wave_pair_ref(pair_recent, pair_prev)
        if pair_dir == target_dir:
            consecutive += 1
        else:
            break

    if consecutive >= 2:
        s = 2
    elif consecutive == 1:
        s = 1
    else:
        s = 0

    return (target_dir, s, consecutive)


def _classify_wave_pair_ref(recent: RefWave, prev: RefWave) -> int:
    """Classify a pair of waves (matches IncrementalTrend._classify_wave_pair)."""
    if recent.direction == "bullish":
        high_wave, low_wave = recent, prev
    else:
        low_wave, high_wave = recent, prev

    has_hh = high_wave.is_higher_high is True if high_wave else False
    has_lh = high_wave.is_lower_high is True if high_wave else False
    has_hl = low_wave.is_higher_low is True if low_wave else False
    has_ll = low_wave.is_lower_low is True if low_wave else False

    if has_hh and has_hl:
        return 1
    if has_lh and has_ll:
        return -1
    if has_hh and not has_ll:
        return 1
    if has_lh and not has_hl:
        return -1
    if has_hl and not has_lh:
        return 1
    if has_ll and not has_hh:
        return -1
    return 0
