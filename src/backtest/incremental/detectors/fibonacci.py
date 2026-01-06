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

        # Retracement levels (entry zones between high and low)
        - type: fibonacci
          key: fib_retracement
          depends_on:
            swing: swing
          params:
            levels: [0.382, 0.5, 0.618]
            mode: retracement

        # Extension levels above high (long targets)
        - type: fibonacci
          key: fib_targets_up
          depends_on:
            swing: swing
          params:
            levels: [1.272, 1.618, 2.0, 2.618]
            mode: extension_up

        # Extension levels below low (short targets)
        - type: fibonacci
          key: fib_targets_down
          depends_on:
            swing: swing
          params:
            levels: [0.272, 0.618]
            mode: extension_down

Modes:
    retracement: level = high - (ratio × range)  → between high and low
    extension_up: level = high + (ratio × range) → above swing high
    extension_down: level = low - (ratio × range) → below swing low

Access in rules:
    condition: close < structure.fib_retracement.level_0.618
    condition: close > structure.fib_targets_up.level_1.618

Anchor Outputs (always available):
    anchor_high: The swing high price (0% reference)
    anchor_low: The swing low price (100% reference)
    range: The price range (high - low)

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
        levels: List of Fibonacci ratios (must be non-empty, positive numbers).
                Retracement: [0.236, 0.382, 0.5, 0.618, 0.786]
                Extension up: [1.272, 1.618, 2.0, 2.618]
                Extension down: [0.272, 0.618] (projected below low)
        mode: Calculation mode:
              - "retracement" (default): Levels between high and low
              - "extension_up" or "extension": Levels above swing high
              - "extension_down": Levels below swing low

    Dependencies:
        swing: A swing detector instance providing high_level, high_idx,
               low_level, and low_idx outputs.

    Outputs:
        Dynamic level outputs based on levels parameter:
        - level_<ratio>: Price at that Fibonacci level

        Fixed anchor outputs (always available):
        - anchor_high: The swing high price (0% reference point)
        - anchor_low: The swing low price (100% reference point)
        - range: The price range (high - low)

    Formulas:
        retracement:    level = high - (ratio × range)
        extension_up:   level = high + (ratio × range)
        extension_down: level = low - (ratio × range)

    Trading Application:
        - Retracement levels (38.2%, 50%, 61.8%): Entry zones in pullbacks
        - Extension up (127.2%, 161.8%): Long profit targets
        - Extension down (27.2%, 61.8%): Short profit targets

    Performance:
        - update(): O(k) where k = number of levels (only when swings change)
        - get_value(): O(1)

    Example:
        >>> detector = IncrementalFibonacci(
        ...     params={"levels": [0.382, 0.618], "mode": "retracement"},
        ...     deps={"swing": mock_swing}
        ... )
        >>> detector.get_output_keys()
        ['level_0.382', 'level_0.618', 'anchor_high', 'anchor_low', 'range']
    """

    REQUIRED_PARAMS: list[str] = ["levels"]
    OPTIONAL_PARAMS: dict[str, Any] = {"mode": "retracement"}
    DEPENDS_ON: list[str] = ["swing"]

    # Valid modes for Fibonacci calculation
    VALID_MODES = ("retracement", "extension", "extension_up", "extension_down")

    @classmethod
    def _validate_params(
        cls, struct_type: str, key: str, params: dict[str, Any]
    ) -> None:
        """
        Validate Fibonacci parameters.

        Raises:
            ValueError: If levels is not a non-empty list of positive numbers.
            ValueError: If mode is not a valid Fibonacci mode.
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
        if mode not in cls.VALID_MODES:
            raise ValueError(
                f"Structure '{key}': 'mode' must be one of {cls.VALID_MODES}, got {mode!r}\n"
                f"\n"
                f"Fix:\n"
                f"  mode: retracement     # levels between high and low\n"
                f"  mode: extension_up    # levels above swing high (long targets)\n"
                f"  mode: extension_down  # levels below swing low (short targets)"
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

        # Normalize 'extension' to 'extension_up' for backward compatibility
        if self.mode == "extension":
            self.mode = "extension_up"

        # Level values storage: keyed by formatted level string
        self._values: dict[str, float] = {}

        # Initialize level outputs with NaN values
        for lvl in self.levels:
            key = self._format_level_key(lvl)
            self._values[key] = float("nan")

        # Initialize anchor outputs (always available)
        self._values["anchor_high"] = float("nan")
        self._values["anchor_low"] = float("nan")
        self._values["range"] = float("nan")

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
        Calculates levels based on mode:
        - retracement: levels between high and low
        - extension_up: levels above swing high
        - extension_down: levels below swing low
        """
        high = self.swing.get_value("high_level")
        low = self.swing.get_value("low_level")

        # Check for valid values (not NaN)
        if math.isnan(high) or math.isnan(low):
            return

        # Calculate range and update anchor outputs
        range_val = high - low
        self._values["anchor_high"] = high
        self._values["anchor_low"] = low
        self._values["range"] = range_val

        # Compute each level based on mode
        for lvl in self.levels:
            key = self._format_level_key(lvl)

            if self.mode == "retracement":
                # Retracement: levels between high and low
                # Formula: high - (ratio × range)
                # At 0%: high, at 100%: low
                self._values[key] = high - (range_val * lvl)

            elif self.mode == "extension_up":
                # Extension up: levels projected above swing high
                # Formula: high + (ratio × range)
                # Used for long profit targets (127.2%, 161.8%, etc.)
                self._values[key] = high + (range_val * lvl)

            elif self.mode == "extension_down":
                # Extension down: levels projected below swing low
                # Formula: low - (ratio × range)
                # Used for short profit targets (27.2%, 61.8%, etc.)
                self._values[key] = low - (range_val * lvl)

    def get_output_keys(self) -> list[str]:
        """
        Return list of output keys.

        Keys include:
        - Dynamic level keys from the levels parameter (e.g., 'level_0.618')
        - Fixed anchor keys: 'anchor_high', 'anchor_low', 'range'

        Returns:
            List of all output keys.
        """
        level_keys = [self._format_level_key(lvl) for lvl in self.levels]
        anchor_keys = ["anchor_high", "anchor_low", "range"]
        return level_keys + anchor_keys

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
