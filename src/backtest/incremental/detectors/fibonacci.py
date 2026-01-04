"""
Fibonacci retracement/extension level detector.

Computes Fibonacci levels from swing high/low points provided by
a swing detector dependency. Levels are recalculated only when the
swing points change, ensuring O(1) per-bar updates in most cases.

Usage in Play:
    structures:
      exec:
        - type: swing
          key: swing
          params:
            left: 5
            right: 5

        - type: fibonacci
          key: fib
          depends_on:
            swing: swing
          params:
            levels: [0.236, 0.382, 0.5, 0.618, 0.786]
            mode: retracement  # or extension

Access in rules:
    condition: close < structure.fib.level_0.618

See: docs/architecture/INCREMENTAL_STATE_ARCHITECTURE.md
"""

from __future__ import annotations

import math
from typing import Any

from ..base import BarData, BaseIncrementalDetector
from ..registry import register_structure


@register_structure("fibonacci")
class IncrementalFibonacci(BaseIncrementalDetector):
    """
    Fibonacci retracement/extension levels from swing points.

    Computes standard Fibonacci levels from the most recent swing
    high and swing low detected by a dependent swing detector.
    Levels are only recalculated when swing points change.

    Parameters:
        levels: List of Fibonacci ratios (must be non-empty, all positive).
                Common values: [0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
        mode: "retracement" (default) or "extension"
              - Retracement: Levels between high and low
              - Extension: Levels projected beyond high

    Dependencies:
        swing: A swing detector instance providing high_level, high_idx,
               low_level, and low_idx outputs.

    Outputs:
        Dynamic based on levels parameter.
        For levels=[0.236, 0.382, 0.618], outputs are:
        - level_0.236: Price at 23.6% level
        - level_0.382: Price at 38.2% level
        - level_0.618: Price at 61.8% level

    Retracement Formula (assuming uptrend from low to high):
        level_price = high - (range * ratio)
        where range = high - low

    Extension Formula:
        level_price = high + (range * ratio)

    Performance:
        - update(): O(k) where k = number of levels (only when swings change)
        - get_value(): O(1)

    Example:
        >>> detector = IncrementalFibonacci(
        ...     params={"levels": [0.382, 0.618], "mode": "retracement"},
        ...     deps={"swing": mock_swing}
        ... )
        >>> detector.get_output_keys()
        ['level_0.382', 'level_0.618']
    """

    REQUIRED_PARAMS: list[str] = ["levels"]
    OPTIONAL_PARAMS: dict[str, Any] = {"mode": "retracement"}
    DEPENDS_ON: list[str] = ["swing"]

    @classmethod
    def _validate_params(
        cls, struct_type: str, key: str, params: dict[str, Any]
    ) -> None:
        """
        Validate Fibonacci parameters.

        Raises:
            ValueError: If levels is not a non-empty list of positive numbers.
            ValueError: If mode is not 'retracement' or 'extension'.
        """
        # Validate levels
        levels = params.get("levels")
        if not isinstance(levels, list) or len(levels) == 0:
            raise ValueError(
                f"Structure '{key}': 'levels' must be a non-empty list of numbers\n"
                f"\n"
                f"Fix: levels: [0.236, 0.382, 0.5, 0.618, 0.786]"
            )

        # Validate each level is a positive number
        for i, level in enumerate(levels):
            if not isinstance(level, (int, float)):
                raise ValueError(
                    f"Structure '{key}': 'levels[{i}]' must be a number, got {type(level).__name__}\n"
                    f"\n"
                    f"Fix: levels: [0.236, 0.382, 0.5, 0.618, 0.786]  # All values must be numbers"
                )
            if level <= 0:
                raise ValueError(
                    f"Structure '{key}': 'levels[{i}]' must be positive, got {level}\n"
                    f"\n"
                    f"Fix: levels: [0.236, 0.382, 0.5, 0.618, 0.786]  # All values must be > 0"
                )

        # Validate mode
        mode = params.get("mode", "retracement")
        if mode not in ("retracement", "extension"):
            raise ValueError(
                f"Structure '{key}': 'mode' must be 'retracement' or 'extension', got {mode!r}\n"
                f"\n"
                f"Fix: mode: retracement  # or: mode: extension"
            )

    def __init__(
        self,
        params: dict[str, Any],
        deps: dict[str, BaseIncrementalDetector],
    ) -> None:
        """
        Initialize Fibonacci detector.

        Args:
            params: Dict with levels and optional mode.
            deps: Dict containing 'swing' dependency.
        """
        self.swing = deps["swing"]
        self.levels: list[float] = [float(lvl) for lvl in params["levels"]]
        self.mode: str = params.get("mode", "retracement")

        # Level values storage: keyed by formatted level string
        self._values: dict[str, float] = {}

        # Initialize with NaN values
        for lvl in self.levels:
            key = self._format_level_key(lvl)
            self._values[key] = float("nan")

        # Track last known swing indices to detect changes
        self._last_high_idx: int = -1
        self._last_low_idx: int = -1

    @staticmethod
    def _format_level_key(level: float) -> str:
        """
        Format a level ratio into a consistent output key.

        Removes trailing zeros and keeps reasonable precision.

        Args:
            level: Fibonacci ratio (e.g., 0.618)

        Returns:
            Formatted key (e.g., "level_0.618")
        """
        # Format with enough precision but remove trailing zeros
        formatted = f"{level:g}"
        return f"level_{formatted}"

    def update(self, bar_idx: int, bar: BarData) -> None:
        """
        Process one bar, recalculating levels if swings changed.

        Checks if the swing detector's high_idx or low_idx has changed
        since the last update. If so, recalculates all Fibonacci levels.

        Args:
            bar_idx: Current bar index.
            bar: Bar data (not directly used, but required by interface).
        """
        # Get current swing indices from dependency
        current_high_idx = self.swing.get_value("high_idx")
        current_low_idx = self.swing.get_value("low_idx")

        # Only recalculate if swings have changed
        if (current_high_idx != self._last_high_idx or
                current_low_idx != self._last_low_idx):
            self._recalculate()
            self._last_high_idx = current_high_idx
            self._last_low_idx = current_low_idx

    def _recalculate(self) -> None:
        """
        Recalculate all Fibonacci levels from current swing points.

        Uses high_level and low_level from the swing dependency.
        Calculates either retracement or extension levels based on mode.
        """
        high = self.swing.get_value("high_level")
        low = self.swing.get_value("low_level")

        # Check for valid values (not NaN)
        if math.isnan(high) or math.isnan(low):
            return

        # Calculate range
        range_val = high - low

        # Compute each level
        for lvl in self.levels:
            key = self._format_level_key(lvl)

            if self.mode == "retracement":
                # Retracement: levels between high and low
                # From high, moving toward low
                self._values[key] = high - (range_val * lvl)
            else:
                # Extension: levels projected beyond high
                self._values[key] = high + (range_val * lvl)

    def get_output_keys(self) -> list[str]:
        """
        Return list of output keys.

        Keys are dynamically generated from the levels parameter,
        formatted as 'level_<ratio>' (e.g., 'level_0.618').

        Returns:
            List of level keys in the order they were specified.
        """
        return [self._format_level_key(lvl) for lvl in self.levels]

    def get_value(self, key: str) -> float:
        """
        Get output by key.

        Args:
            key: Level key (e.g., 'level_0.618').

        Returns:
            Current level price, or NaN if not yet calculated.

        Raises:
            KeyError: If key is not a valid level key.
        """
        if key in self._values:
            return self._values[key]
        raise KeyError(key)

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        levels_str = ", ".join(str(lvl) for lvl in self.levels)
        return f"IncrementalFibonacci(levels=[{levels_str}], mode={self.mode!r})"
