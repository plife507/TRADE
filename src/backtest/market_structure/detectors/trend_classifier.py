"""
Trend Classifier.

Classifies market trend based on swing high/low patterns.

Classification Logic:
- UP: Higher Highs (HH) + Higher Lows (HL) - structural uptrend
- DOWN: Lower Lows (LL) + Lower Highs (LH) - structural downtrend
- UNKNOWN: Mixed pattern or insufficient data

Requirements:
- Needs 2 confirmed swing highs + 2 confirmed swing lows to classify
- Classification updates on each new swing confirmation
- Forward-fills the last known trend state

Output Arrays (per-bar, forward-filled):
- trend_state: 0=UNKNOWN, 1=UP, 2=DOWN (TrendState enum)
- recency: Bars since last trend state change (-1 if never classified)
- parent_version: Version counter (increments on each trend state change)
"""

import numpy as np
from typing import Any

from src.backtest.market_structure.registry import BaseDetector
from src.backtest.market_structure.types import TREND_INTERNAL_OUTPUTS, TrendState


class TrendClassifier(BaseDetector):
    """
    Trend classifier based on swing high/low patterns.

    Requires swing outputs as input. Classifies trend as:
    - UP: Last 2 swing highs ascending AND last 2 swing lows ascending (structural uptrend)
    - DOWN: Last 2 swing highs descending AND last 2 swing lows descending (structural downtrend)
    - UNKNOWN: Mixed pattern or insufficient history

    The classifier needs at least 2 confirmed highs and 2 confirmed lows
    before making a trend classification.
    """

    @property
    def output_keys(self) -> tuple[str, ...]:
        """Output key suffixes for trend classifier (internal names)."""
        return TREND_INTERNAL_OUTPUTS

    def build_batch(
        self,
        swing_outputs: dict[str, np.ndarray],
        params: dict[str, Any],
    ) -> dict[str, np.ndarray]:
        """
        Classify trend based on swing high/low patterns.

        Args:
            swing_outputs: Dict with swing detector outputs
                - high_level, high_idx, low_level, low_idx, state
            params: Dict with optional parameters (none required for trend)

        Returns:
            Dict mapping output keys to numpy arrays.
        """
        high_level = swing_outputs["high_level"]
        high_idx = swing_outputs["high_idx"]
        low_level = swing_outputs["low_level"]
        low_idx = swing_outputs["low_idx"]
        swing_state = swing_outputs["state"]

        n = len(high_level)

        # Initialize outputs
        trend_state = np.zeros(n, dtype=np.int8)
        recency = np.full(n, -1, dtype=np.int16)
        parent_version = np.zeros(n, dtype=np.int32)

        # Track confirmed swings for pattern detection
        # We store last 2 of each type (prev and curr)
        high_history = []  # List of (level, idx) tuples
        low_history = []  # List of (level, idx) tuples

        current_trend = TrendState.UNKNOWN
        last_trend_change_bar = -1
        current_version = 0

        for j in range(n):
            # Check for new swing confirmations (state > 0)
            if swing_state[j] > 0:
                # Check if we have new high (state 1 or 3)
                new_high = swing_state[j] in (1, 3)
                # Check if we have new low (state 2 or 3)
                new_low = swing_state[j] in (2, 3)

                # Record new swings
                if new_high:
                    curr_high_level = high_level[j]
                    curr_high_idx = high_idx[j]
                    # Only add if it's a new pivot (different idx from last)
                    if len(high_history) == 0 or high_history[-1][1] != curr_high_idx:
                        high_history.append((curr_high_level, curr_high_idx))
                        # Keep only last 2
                        if len(high_history) > 2:
                            high_history.pop(0)

                if new_low:
                    curr_low_level = low_level[j]
                    curr_low_idx = low_idx[j]
                    # Only add if it's a new pivot (different idx from last)
                    if len(low_history) == 0 or low_history[-1][1] != curr_low_idx:
                        low_history.append((curr_low_level, curr_low_idx))
                        # Keep only last 2
                        if len(low_history) > 2:
                            low_history.pop(0)

                # Classify when we have at least 2 of each
                if len(high_history) >= 2 and len(low_history) >= 2:
                    prev_high_level, _ = high_history[-2]
                    curr_high_level, _ = high_history[-1]
                    prev_low_level, _ = low_history[-2]
                    curr_low_level, _ = low_history[-1]

                    # Determine HH/LH and HL/LL
                    is_higher_high = curr_high_level > prev_high_level
                    is_lower_high = curr_high_level < prev_high_level
                    is_higher_low = curr_low_level > prev_low_level
                    is_lower_low = curr_low_level < prev_low_level

                    # UP: HH + HL (structural uptrend)
                    # DOWN: LH + LL (structural downtrend)
                    if is_higher_high and is_higher_low:
                        new_trend = TrendState.UP
                    elif is_lower_high and is_lower_low:
                        new_trend = TrendState.DOWN
                    else:
                        # Mixed pattern (HH+LL, LH+HL, or equal)
                        new_trend = TrendState.UNKNOWN

                    if new_trend != current_trend:
                        current_trend = new_trend
                        last_trend_change_bar = j
                        current_version += 1

            # Forward-fill trend state
            trend_state[j] = current_trend.value

            # Forward-fill parent_version
            parent_version[j] = current_version

            # Compute recency
            if last_trend_change_bar >= 0:
                recency[j] = j - last_trend_change_bar
            # else: stays -1 (sentinel)

        return {
            "trend_state": trend_state,
            "recency": recency,
            "parent_version": parent_version,
        }


def classify_single_swing_update(
    prev_high: float,
    curr_high: float,
    prev_low: float,
    curr_low: float,
) -> int:
    """
    Pure function to classify trend from two consecutive swing pairs.

    Returns TrendState value (0=UNKNOWN, 1=UP, 2=DOWN).

    Args:
        prev_high: Previous swing high level
        curr_high: Current swing high level
        prev_low: Previous swing low level
        curr_low: Current swing low level

    Returns:
        TrendState enum value
    """
    if np.isnan(prev_high) or np.isnan(curr_high):
        return TrendState.UNKNOWN.value
    if np.isnan(prev_low) or np.isnan(curr_low):
        return TrendState.UNKNOWN.value

    is_higher_high = curr_high > prev_high
    is_lower_high = curr_high < prev_high
    is_higher_low = curr_low > prev_low
    is_lower_low = curr_low < prev_low

    if is_higher_high and is_higher_low:
        return TrendState.UP.value
    elif is_lower_high and is_lower_low:
        return TrendState.DOWN.value
    else:
        return TrendState.UNKNOWN.value
