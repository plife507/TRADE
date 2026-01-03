"""
Swing Detector.

Classic left/right pivot detection for swing highs and lows.

Confirmation Logic:
- A potential pivot at bar i is detected when it's STRICTLY the highest/lowest
  within the window [i-left, i+right].
- Any equality in the window invalidates the pivot (strict inequality only).
- Confirmation happens at bar i+right (looking back, we can now confirm
  that bar i was indeed a pivot).
- Sentinel values before any confirmed swing: level=NaN, idx=-1.

Tie-Breaking Rule (LOCKED):
- Equal highs/lows produce NO pivot.
- A pivot requires strict inequality: pivot_high > all other highs in window.

Output Arrays (per-bar, forward-filled):
- high_level: Price level of last confirmed swing high (NaN if none)
- high_idx: Bar index of last confirmed swing high (-1 if none)
- low_level: Price level of last confirmed swing low (NaN if none)
- low_idx: Bar index of last confirmed swing low (-1 if none)
- state: Confirmation state (0=none, 1=new_high, 2=new_low, 3=both)
- recency: Bars since last update (-1 if never updated)
"""

import numpy as np
from typing import Any

from src.backtest.market_structure.registry import BaseDetector
from src.backtest.market_structure.types import SWING_INTERNAL_OUTPUTS


class SwingState:
    """Swing detection state values."""

    NONE = 0
    NEW_HIGH = 1
    NEW_LOW = 2
    BOTH = 3  # Both high and low confirmed on same bar (rare)


class SwingDetector(BaseDetector):
    """
    Classic left/right pivot swing detector.

    Detects swing highs/lows using a symmetric window approach:
    - A swing high is a bar whose high is STRICTLY > all highs in [i-left, i+right]
    - A swing low is a bar whose low is STRICTLY < all lows in [i-left, i+right]

    Any equality invalidates the pivot (strict inequality only).
    Confirmation happens at bar i+right, looking back to confirm the pivot.
    """

    @property
    def output_keys(self) -> tuple[str, ...]:
        """Output key suffixes for swing detector (internal names)."""
        return SWING_INTERNAL_OUTPUTS

    def build_batch(
        self,
        ohlcv: dict[str, Any],
        params: dict[str, Any],
    ) -> dict[str, np.ndarray]:
        """
        Compute swing highs/lows for entire dataset.

        Args:
            ohlcv: Dict with 'high' and 'low' numpy arrays
            params: Dict with 'left' and 'right' lookback periods

        Returns:
            Dict mapping output keys to numpy arrays.
        """
        high = ohlcv["high"]
        low = ohlcv["low"]
        n = len(high)

        left = params["left"]
        right = params["right"]

        # Initialize output arrays with sentinel values
        high_level = np.full(n, np.nan, dtype=np.float64)
        high_idx = np.full(n, -1, dtype=np.int32)
        low_level = np.full(n, np.nan, dtype=np.float64)
        low_idx = np.full(n, -1, dtype=np.int32)
        state = np.zeros(n, dtype=np.int8)
        recency = np.full(n, -1, dtype=np.int16)

        # Track last confirmed values for forward-fill
        last_high_level = np.nan
        last_high_idx = -1
        last_low_level = np.nan
        last_low_idx = -1
        last_update_bar = -1

        # Confirmation window: we can confirm a pivot at bar i
        # when we're at bar i+right (we need right bars after to confirm)
        # So at current bar j, we check if bar (j - right) is a pivot

        for j in range(n):
            # Check if we can confirm a pivot at bar (j - right)
            pivot_bar = j - right

            # Need enough history: pivot_bar >= left to have full left window
            if pivot_bar >= left:
                # Define the window for pivot confirmation
                window_start = pivot_bar - left
                window_end = pivot_bar + right  # == j

                # Check for swing high at pivot_bar (STRICT inequality)
                pivot_high = high[pivot_bar]
                is_swing_high = True
                for k in range(window_start, window_end + 1):
                    if k != pivot_bar:
                        # Any value >= pivot_high invalidates (strict inequality)
                        if high[k] >= pivot_high:
                            is_swing_high = False
                            break

                # Check for swing low at pivot_bar (STRICT inequality)
                pivot_low = low[pivot_bar]
                is_swing_low = True
                for k in range(window_start, window_end + 1):
                    if k != pivot_bar:
                        # Any value <= pivot_low invalidates (strict inequality)
                        if low[k] <= pivot_low:
                            is_swing_low = False
                            break

                # Update state based on confirmations
                bar_state = SwingState.NONE
                if is_swing_high:
                    last_high_level = pivot_high
                    last_high_idx = pivot_bar
                    last_update_bar = j
                    bar_state = SwingState.NEW_HIGH

                if is_swing_low:
                    last_low_level = pivot_low
                    last_low_idx = pivot_bar
                    last_update_bar = j
                    if bar_state == SwingState.NEW_HIGH:
                        bar_state = SwingState.BOTH
                    else:
                        bar_state = SwingState.NEW_LOW

                state[j] = bar_state

            # Forward-fill the last confirmed values
            high_level[j] = last_high_level
            high_idx[j] = last_high_idx
            low_level[j] = last_low_level
            low_idx[j] = last_low_idx

            # Compute recency (bars since last update)
            if last_update_bar >= 0:
                recency[j] = j - last_update_bar
            # else: stays -1 (sentinel)

        return {
            "high_level": high_level,
            "high_idx": high_idx,
            "low_level": low_level,
            "low_idx": low_idx,
            "state": state,
            "recency": recency,
        }


def detect_swing_pivots(
    high: np.ndarray,
    low: np.ndarray,
    left: int,
    right: int,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Pure function to detect pivot points (no forward-fill).

    Uses STRICT inequality: equal values invalidate pivots.

    Returns boolean arrays indicating which bars are pivots.
    Useful for testing and visualization.

    Args:
        high: High prices array
        low: Low prices array
        left: Left lookback period
        right: Right lookback period

    Returns:
        (is_swing_high, is_swing_low) boolean arrays
    """
    n = len(high)
    is_swing_high = np.zeros(n, dtype=bool)
    is_swing_low = np.zeros(n, dtype=bool)

    for i in range(left, n - right):
        window_start = i - left
        window_end = i + right

        # Check swing high (STRICT: pivot must be > all others)
        pivot_high = high[i]
        is_high = True
        for k in range(window_start, window_end + 1):
            if k != i and high[k] >= pivot_high:
                is_high = False
                break
        is_swing_high[i] = is_high

        # Check swing low (STRICT: pivot must be < all others)
        pivot_low = low[i]
        is_low = True
        for k in range(window_start, window_end + 1):
            if k != i and low[k] <= pivot_low:
                is_low = False
                break
        is_swing_low[i] = is_low

    return is_swing_high, is_swing_low
