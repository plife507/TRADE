"""
Vectorized reference implementation for fractal swing detection.

Implements the same algorithm as IncrementalSwing (fractal mode only,
no significance/alternation gates) using simple loops over numpy arrays.
This is ground truth for parity verification - correctness over speed.

Algorithm:
    For each bar i where we have a full window [i-right ... i ... i+left]
    (adjusting: we process at bar i+right the pivot at bar i):
    - At bar_idx = left + right + j (j >= 0), the candidate pivot is at bar j + left
    - Swing high: high[pivot] > all other highs in the window
    - Swing low: low[pivot] < all other lows in the window
    - Confirmation: pivot at bar (bar_idx - right) is confirmed at bar_idx
    - Forward-fill: outputs hold their value until next confirmation
"""

import hashlib
import math

import numpy as np


def vectorized_swing(
    ohlcv: dict[str, np.ndarray],
    left: int,
    right: int,
) -> dict[str, np.ndarray]:
    """
    Compute swing highs/lows with pairing using vectorized loop.

    Matches IncrementalSwing fractal mode with default params:
    - No significance gates (no atr_key)
    - No alternation (strict_alternation=false)
    - No min_atr_move / min_pct_move filtering

    Args:
        ohlcv: Dict with open, high, low, close, volume arrays.
        left: Number of bars to the left of pivot.
        right: Number of bars to the right of pivot.

    Returns:
        Dict mapping output key -> numpy array (one value per bar).
    """
    high = ohlcv["high"]
    low = ohlcv["low"]
    n = len(high)
    window_size = left + right + 1

    # Individual pivot outputs
    out_high_level = np.full(n, np.nan)
    out_high_idx = np.full(n, -1.0)
    out_low_level = np.full(n, np.nan)
    out_low_idx = np.full(n, -1.0)
    out_version = np.zeros(n)
    out_last_confirmed_pivot_idx = np.full(n, -1.0)
    out_last_confirmed_pivot_type = np.full(n, np.nan)  # NaN=none, 1.0=high, 0.0=low

    # Significance outputs (always NaN/False without atr_key)
    out_high_significance = np.full(n, np.nan)
    out_low_significance = np.full(n, np.nan)
    out_high_is_major = np.zeros(n)
    out_low_is_major = np.zeros(n)

    # Alternation outputs (always False without strict_alternation)
    out_high_accepted = np.zeros(n)
    out_low_accepted = np.zeros(n)
    out_high_replaced_pending = np.zeros(n)
    out_low_replaced_pending = np.zeros(n)

    # Paired pivot outputs
    out_pair_high_level = np.full(n, np.nan)
    out_pair_high_idx = np.full(n, -1.0)
    out_pair_low_level = np.full(n, np.nan)
    out_pair_low_idx = np.full(n, -1.0)
    out_pair_direction = np.full(n, np.nan)  # NaN=none, 1.0=bullish, -1.0=bearish
    out_pair_version = np.zeros(n)
    # pair_anchor_hash is a string - we'll store as special array
    out_pair_anchor_hash = np.full(n, np.nan)  # Skip comparison for hashes

    # Running state
    current_high_level = float("nan")
    current_high_idx = -1
    current_low_level = float("nan")
    current_low_idx = -1
    version = 0
    last_confirmed_pivot_idx = -1
    last_confirmed_pivot_type_val = float("nan")

    # Pair state machine
    STATE_AWAITING_FIRST = 0
    STATE_GOT_HIGH = 1
    STATE_GOT_LOW = 2

    pair_state = STATE_AWAITING_FIRST
    pending_type = ""  # "high" or "low"
    pending_level = float("nan")
    pending_idx = -1

    pair_high_level = float("nan")
    pair_high_idx = -1
    pair_low_level = float("nan")
    pair_low_idx = -1
    pair_direction_val = float("nan")
    pair_version = 0

    for bar_idx in range(n):
        # Reset per-bar event flags
        high_accepted = False
        low_accepted = False
        confirmed_high = False
        confirmed_low = False

        # Need at least window_size bars to confirm a pivot
        # The first pivot can be confirmed at bar_idx = window_size - 1
        if bar_idx >= window_size - 1:
            # The pivot being checked is at bar_idx - right
            pivot_bar_idx = bar_idx - right

            # Check swing high: pivot's high must be strictly greater than all others
            pivot_high = high[pivot_bar_idx]
            is_high = True
            for k in range(pivot_bar_idx - left, pivot_bar_idx + right + 1):
                if k != pivot_bar_idx and high[k] >= pivot_high:
                    is_high = False
                    break

            if is_high:
                current_high_level = pivot_high
                current_high_idx = pivot_bar_idx
                version += 1
                last_confirmed_pivot_idx = pivot_bar_idx
                last_confirmed_pivot_type_val = 1.0  # high
                confirmed_high = True
                high_accepted = True

            # Check swing low: pivot's low must be strictly less than all others
            pivot_low = low[pivot_bar_idx]
            is_low = True
            for k in range(pivot_bar_idx - left, pivot_bar_idx + right + 1):
                if k != pivot_bar_idx and low[k] <= pivot_low:
                    is_low = False
                    break

            if is_low:
                current_low_level = pivot_low
                current_low_idx = pivot_bar_idx
                version += 1
                last_confirmed_pivot_idx = pivot_bar_idx
                last_confirmed_pivot_type_val = 0.0  # low
                confirmed_low = True
                low_accepted = True

        # Update pairing state machine
        if confirmed_high or confirmed_low:
            # Handle both confirmed same bar: process high first, then low
            pivots_to_process = []
            if confirmed_high and confirmed_low:
                pivots_to_process.append(("high", current_high_level, current_high_idx))
                pivots_to_process.append(("low", current_low_level, current_low_idx))
            elif confirmed_high:
                pivots_to_process.append(("high", current_high_level, current_high_idx))
            else:
                pivots_to_process.append(("low", current_low_level, current_low_idx))

            for pivot_type, level, idx in pivots_to_process:
                if pair_state == STATE_AWAITING_FIRST:
                    pending_type = pivot_type
                    pending_level = level
                    pending_idx = idx
                    pair_state = STATE_GOT_HIGH if pivot_type == "high" else STATE_GOT_LOW

                elif pair_state == STATE_GOT_HIGH:
                    if pivot_type == "low":
                        # HIGH -> LOW = bearish (HLH)
                        pair_high_level = pending_level
                        pair_high_idx = pending_idx
                        pair_low_level = level
                        pair_low_idx = idx
                        pair_direction_val = -1.0  # bearish
                        pair_version += 1
                        # New low becomes pending
                        pending_type = "low"
                        pending_level = level
                        pending_idx = idx
                        pair_state = STATE_GOT_LOW
                    else:
                        # HIGH -> HIGH: replace pending
                        pending_level = level
                        pending_idx = idx

                elif pair_state == STATE_GOT_LOW:
                    if pivot_type == "high":
                        # LOW -> HIGH = bullish (LHL)
                        pair_high_level = level
                        pair_high_idx = idx
                        pair_low_level = pending_level
                        pair_low_idx = pending_idx
                        pair_direction_val = 1.0  # bullish
                        pair_version += 1
                        # New high becomes pending
                        pending_type = "high"
                        pending_level = level
                        pending_idx = idx
                        pair_state = STATE_GOT_HIGH
                    else:
                        # LOW -> LOW: replace pending
                        pending_level = level
                        pending_idx = idx

        # Write forward-filled outputs for this bar
        out_high_level[bar_idx] = current_high_level
        out_high_idx[bar_idx] = current_high_idx
        out_low_level[bar_idx] = current_low_level
        out_low_idx[bar_idx] = current_low_idx
        out_version[bar_idx] = version
        out_last_confirmed_pivot_idx[bar_idx] = last_confirmed_pivot_idx
        out_last_confirmed_pivot_type[bar_idx] = last_confirmed_pivot_type_val

        # Significance: always NaN/0 in default mode (no atr_key)
        out_high_significance[bar_idx] = np.nan
        out_low_significance[bar_idx] = np.nan
        out_high_is_major[bar_idx] = 0
        out_low_is_major[bar_idx] = 0

        # Alternation: reset each bar (no strict_alternation)
        out_high_accepted[bar_idx] = 1.0 if high_accepted else 0.0
        out_low_accepted[bar_idx] = 1.0 if low_accepted else 0.0
        out_high_replaced_pending[bar_idx] = 0.0
        out_low_replaced_pending[bar_idx] = 0.0

        # Paired outputs (forward-filled)
        out_pair_high_level[bar_idx] = pair_high_level
        out_pair_high_idx[bar_idx] = pair_high_idx
        out_pair_low_level[bar_idx] = pair_low_level
        out_pair_low_idx[bar_idx] = pair_low_idx
        out_pair_direction[bar_idx] = pair_direction_val
        out_pair_version[bar_idx] = pair_version

    return {
        "high_level": out_high_level,
        "high_idx": out_high_idx,
        "low_level": out_low_level,
        "low_idx": out_low_idx,
        "version": out_version,
        "last_confirmed_pivot_idx": out_last_confirmed_pivot_idx,
        "last_confirmed_pivot_type": out_last_confirmed_pivot_type,
        "high_significance": out_high_significance,
        "low_significance": out_low_significance,
        "high_is_major": out_high_is_major,
        "low_is_major": out_low_is_major,
        "high_accepted": out_high_accepted,
        "low_accepted": out_low_accepted,
        "high_replaced_pending": out_high_replaced_pending,
        "low_replaced_pending": out_low_replaced_pending,
        "pair_high_level": out_pair_high_level,
        "pair_high_idx": out_pair_high_idx,
        "pair_low_level": out_pair_low_level,
        "pair_low_idx": out_pair_low_idx,
        "pair_direction": out_pair_direction,
        "pair_version": out_pair_version,
        "pair_anchor_hash": out_pair_anchor_hash,  # Skip in comparison
    }
