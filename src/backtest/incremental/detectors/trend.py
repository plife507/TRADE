"""
Incremental trend detector.

Classifies trend based on swing sequence:
- Higher highs + higher lows = uptrend (direction = 1)
- Lower highs + lower lows = downtrend (direction = -1)
- Mixed = ranging (direction = 0)

Requires a swing detector as a dependency to provide swing high/low levels.

Outputs:
- direction: int (1 = uptrend, -1 = downtrend, 0 = ranging)
- strength: float (0.0, can be enhanced later with additional metrics)
- bars_in_trend: int (increments each bar, resets on direction change)

Example Play usage:
    structures:
      exec:
        - type: swing
          key: swing
          params:
            left: 5
            right: 5

        - type: trend
          key: trend
          depends_on:
            swing: swing

See: docs/architecture/INCREMENTAL_STATE_ARCHITECTURE.md
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from ..base import BaseIncrementalDetector
from ..registry import register_structure

if TYPE_CHECKING:
    from ..base import BarData


@register_structure("trend")
class IncrementalTrendDetector(BaseIncrementalDetector):
    """
    Trend classification from swing sequence.

    Analyzes the sequence of swing highs and lows to determine trend direction:
    - Uptrend (1): Higher highs AND higher lows
    - Downtrend (-1): Lower highs AND lower lows
    - Ranging (0): Mixed conditions or insufficient data

    The detector tracks the previous swing levels and compares them to the
    current levels when a new swing is detected. The bars_in_trend counter
    resets whenever the direction changes.

    Attributes:
        direction: Current trend direction (1, -1, or 0).
        strength: Trend strength metric (0.0 for now, can be enhanced).
        bars_in_trend: Number of bars since the trend direction changed.
    """

    REQUIRED_PARAMS: list[str] = []
    OPTIONAL_PARAMS: dict[str, Any] = {}
    DEPENDS_ON: list[str] = ["swing"]

    def __init__(self, params: dict[str, Any], deps: dict[str, BaseIncrementalDetector]):
        """
        Initialize the trend detector.

        Args:
            params: Configuration params (none required for trend).
            deps: Dependencies dict. Must contain "swing" with a swing detector.
        """
        self.swing = deps["swing"]

        # Track previous swing levels for comparison
        self._prev_high: float = float("nan")
        self._prev_low: float = float("nan")

        # Track last seen swing indices to detect new swings
        self._last_high_idx: int = -1
        self._last_low_idx: int = -1

        # Track last HH/HL comparison results for direction classification
        # None = not yet determined, True = higher, False = lower
        self._last_hh: bool | None = None
        self._last_hl: bool | None = None

        # Output values
        self.direction: int = 0  # 0 = ranging, 1 = uptrend, -1 = downtrend
        self.strength: float = 0.0  # Placeholder for future enhancement
        self.bars_in_trend: int = 0

        # Version tracking: increments when direction changes
        # Used by derived structures to detect trend changes
        self._version: int = 0

    def update(self, bar_idx: int, bar: "BarData") -> None:
        """
        Process one bar and update trend classification.

        Called on every TF bar close. Checks if swing detector has detected
        new swing highs or lows, and if so, updates the trend classification.

        Args:
            bar_idx: Current bar index.
            bar: Bar data (not directly used; trend is derived from swings).
        """
        # Get current swing indices from the swing detector
        high_idx = self.swing.high_idx
        low_idx = self.swing.low_idx

        # Check if any swing has changed
        high_changed = high_idx != self._last_high_idx and high_idx >= 0
        low_changed = low_idx != self._last_low_idx and low_idx >= 0

        # If no swing changes, just increment bars_in_trend
        if not high_changed and not low_changed:
            self.bars_in_trend += 1
            return

        # Determine higher high (HH) and higher low (HL)
        current_high = self.swing.high_level
        current_low = self.swing.low_level

        # Update HH/HL tracking when swings change
        if high_changed and not math.isnan(self._prev_high) and not math.isnan(current_high):
            self._last_hh = current_high > self._prev_high

        if low_changed and not math.isnan(self._prev_low) and not math.isnan(current_low):
            self._last_hl = current_low > self._prev_low

        # Determine new direction based on most recent HH/HL pattern
        new_dir = self._classify_direction(self._last_hh, self._last_hl)

        # If direction changed, reset bars_in_trend and bump version
        if new_dir != self.direction:
            self.direction = new_dir
            self.bars_in_trend = 0
            self._version += 1
        else:
            self.bars_in_trend += 1

        # Update previous levels for next comparison
        if high_changed:
            self._prev_high = current_high
            self._last_high_idx = high_idx

        if low_changed:
            self._prev_low = current_low
            self._last_low_idx = low_idx

    def _classify_direction(self, hh: bool | None, hl: bool | None) -> int:
        """
        Classify trend direction based on higher high and higher low signals.

        Args:
            hh: True if higher high, False if lower high, None if no change.
            hl: True if higher low, False if lower low, None if no change.

        Returns:
            1 for uptrend, -1 for downtrend, 0 for ranging.
        """
        # Clear uptrend: both higher high and higher low
        if hh is True and hl is True:
            return 1

        # Clear downtrend: both lower high and lower low
        if hh is False and hl is False:
            return -1

        # Mixed or insufficient data: ranging
        return 0

    def get_output_keys(self) -> list[str]:
        """
        List of readable output keys.

        Returns:
            ["direction", "strength", "bars_in_trend"]
        """
        return ["direction", "strength", "bars_in_trend", "version"]

    def get_value(self, key: str) -> int | float:
        """
        Get output by key. O(1).

        Args:
            key: One of "direction", "strength", or "bars_in_trend".

        Returns:
            The output value.

        Raises:
            KeyError: If key is not valid.
        """
        if key == "direction":
            return self.direction
        elif key == "strength":
            return self.strength
        elif key == "bars_in_trend":
            return self.bars_in_trend
        elif key == "version":
            return self._version
        else:
            raise KeyError(key)
