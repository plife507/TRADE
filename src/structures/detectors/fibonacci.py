"""
Fibonacci retracement/extension level detector.

Computes Fibonacci levels from swing high/low points provided by
a swing detector dependency. Levels are recalculated only when the
swing points change, ensuring O(1) per-bar updates in most cases.

Anchoring Modes:

    Paired Anchoring (Default):
        Anchors to COMPLETE swing pairs (L->H for bullish, H->L for bearish).
        The high and low come from the same swing sequence, ensuring no
        inversions. Set `use_paired_anchor: false` for legacy unpaired mode.

    Trend-Wave Anchoring:
        Uses a trend detector dependency to determine anchor meaning.
        In uptrend: anchors to the latest paired swing high/low (HH/HL).
        In downtrend: anchors to the latest paired swing high/low (LH/LL).
        When ranging (direction=0), keeps last known anchors frozen.
        Set `use_trend_anchor: true` + add trend to `uses:`.

    Raw Unpaired (Legacy):
        Uses the latest independent high_level/low_level from the swing
        detector, which may come from different swing sequences. Can produce
        inverted anchors (high < low). Set `use_paired_anchor: false`.

Level Calculation (Unified Formula):
    All levels use: level = high - (ratio x range)

    This single formula covers ALL scenarios:
    - ratio = 0.0    -> level = high (0% reference)
    - ratio = 0.382  -> 38.2% retracement (between high and low)
    - ratio = 1.0    -> level = low (100% reference)
    - ratio = 1.272  -> 127.2% extension BELOW low (short targets)
    - ratio = -0.272 -> -27.2% extension ABOVE high (long targets)

    The ratio determines where the level falls:
    - ratio < 0:   ABOVE the swing high (long targets/negative extension)
    - 0 <= ratio <= 1: BETWEEN high and low (retracement/entry zones)
    - ratio > 1:   BELOW the swing low (short targets/positive extension)

Modes:
    retracement: Standard formula. Use ratios 0-1 for pullback zones.
    extension:   Auto-direction based on pair_direction (paired mode only):
                 - Bullish pair -> targets ABOVE high (negates ratios)
                 - Bearish pair -> targets BELOW low (adds 1 to ratios)
    extension_up:   (legacy) Forces targets above high
    extension_down: (legacy) Forces targets below low

Usage in Play:
    structures:
      exec:
        - type: swing
          key: pivots
          params: { left: 5, right: 5 }

        # Entry zones (retracement) - paired anchor is default
        - type: fibonacci
          key: fib_entry
          uses: pivots
          params:
            levels: [0.382, 0.5, 0.618]
            mode: retracement

        # Profit targets (auto-direction based on swing)
        - type: fibonacci
          key: fib_targets
          uses: pivots
          params:
            levels: [0.272, 0.618, 1.0]  # Will become 1.272, 1.618, 2.0 for bearish
            mode: extension              # or -0.272, -0.618, -1.0 for bullish

        # Trend-wave anchoring (ICT/SMC style)
        - type: trend
          key: trend
          uses: pivots
        - type: fibonacci
          key: fib_trend
          uses: [pivots, trend]
          params:
            levels: [0.618, 0.705, 0.786]
            mode: retracement
            use_trend_anchor: true

Access in rules:
    condition: close < structure.fib_entry.level_0.618
    condition: close > structure.fib_targets.level_0.272
    condition: structure.fib_entry.anchor_direction == "bullish"
    condition: structure.fib_trend.anchor_trend_direction == 1

Anchor Outputs (always available):
    anchor_high: The swing high price (0% reference)
    anchor_low: The swing low price (100% reference)
    range: The price range (high - low)
    anchor_direction: "bullish", "bearish", or "" (paired/trend mode)
    anchor_hash: Unique hash identifying the anchor pair (paired mode only)
    anchor_trend_direction: Trend direction at anchor time (0 if not trend mode)

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
        levels: List of Fibonacci ratios (must be non-empty, numbers).
                Retracement: [0.236, 0.382, 0.5, 0.618, 0.786]
                Extension up: [1.272, 1.618, 2.0, 2.618]
                Extension down: [0.272, 0.618] (projected below low)
        mode: Calculation mode:
              - "retracement" (default): Levels between high and low
              - "extension_up" or "extension": Levels above swing high
              - "extension_down": Levels below swing low
        use_paired_anchor: Anchor to COMPLETE swing pairs (L->H for bullish,
                          H->L for bearish). Default: true (recommended).
                          Set false for legacy unpaired mode.
        use_trend_anchor: Anchor based on trend direction from a trend
                         dependency. Requires `uses: [swing_key, trend_key]`.
                         Mutually exclusive with use_paired_anchor.
                         Default: false.

    Dependencies:
        swing: A swing detector providing high_level, high_idx,
               low_level, low_idx, and pair_* outputs.
        trend: (optional) A trend detector providing direction and version.
               Required when use_trend_anchor=true.

    Outputs:
        Dynamic level outputs based on levels parameter:
        - level_<ratio>: Price at that Fibonacci level

        Fixed anchor outputs (always available):
        - anchor_high: The swing high price (0% reference point)
        - anchor_low: The swing low price (100% reference point)
        - range: The price range (high - low)
        - anchor_direction: "bullish", "bearish", or "" (empty if unpaired mode)
        - anchor_hash: Unique hash of anchor pair (empty if unpaired mode)
        - anchor_trend_direction: Trend direction at anchor (0 if not trend mode)

    Formulas:
        retracement:    level = high - (ratio x range)
        extension_up:   level = high + (ratio x range)
        extension_down: level = low - (ratio x range)

    Performance:
        - update(): O(k) where k = number of levels (only when swings change)
        - get_value(): O(1)

    Example:
        >>> detector = IncrementalFibonacci(
        ...     params={"levels": [0.382, 0.618], "mode": "retracement"},
        ...     deps={"swing": mock_swing}
        ... )
        >>> detector.get_output_keys()
        ['level_0.382', 'level_0.618', 'anchor_high', 'anchor_low', 'range', ...]
    """

    REQUIRED_PARAMS: list[str] = ["levels"]
    OPTIONAL_PARAMS: dict[str, Any] = {
        "mode": "retracement",
        "use_paired_anchor": True,
        "use_trend_anchor": False,
    }
    DEPENDS_ON: list[str] = ["swing"]
    OPTIONAL_DEPS: list[str] = ["trend"]

    # Valid modes for Fibonacci calculation
    # - retracement: level = high - (ratio x range) - works with any ratio
    # - extension: auto-direction based on pair_direction (requires use_paired_anchor)
    # - extension_up: (legacy) level = high + (ratio x range)
    # - extension_down: (legacy) level = low - (ratio x range)
    VALID_MODES = ("retracement", "extension", "extension_up", "extension_down")

    @classmethod
    def _validate_params(
        cls, struct_type: str, key: str, params: dict[str, Any]
    ) -> None:
        """
        Validate Fibonacci parameters.

        Raises:
            ValueError: If levels is not a non-empty list of numbers.
            ValueError: If mode is not a valid Fibonacci mode.
            ValueError: If mode=extension without use_paired_anchor=true.
        """
        # Validate levels
        levels = params.get("levels")
        if not isinstance(levels, list) or len(levels) == 0:
            raise ValueError(
                f"Structure '{key}': 'levels' must be a non-empty list of numbers\n"
                f"\n"
                f"Fix: levels: [0.236, 0.382, 0.5, 0.618, 0.786]"
            )

        # Validate each level is a number (can be negative for extension above high)
        for i, level in enumerate(levels):
            if not isinstance(level, (int, float)):
                raise ValueError(
                    f"Structure '{key}': 'levels[{i}]' must be a number, got {type(level).__name__}\n"
                    f"\n"
                    f"Fix: levels: [0.382, 0.5, 0.618]  # All values must be numbers\n"
                    f"     Negative levels project ABOVE high: [-0.272, -0.618]\n"
                    f"     Levels > 1 project BELOW low: [1.272, 1.618]"
                )

        # Validate mode
        mode = params.get("mode", "retracement")
        if mode not in cls.VALID_MODES:
            raise ValueError(
                f"Structure '{key}': 'mode' must be one of {cls.VALID_MODES}, got {mode!r}\n"
                f"\n"
                f"Fix:\n"
                f"  mode: retracement   # Unified formula: level = high - (ratio x range)\n"
                f"  mode: extension     # Auto-direction based on pair (requires use_paired_anchor)\n"
                f"  mode: extension_up  # (legacy) level = high + (ratio x range)\n"
                f"  mode: extension_down  # (legacy) level = low - (ratio x range)"
            )

        # Validate extension mode requires paired anchor
        use_paired = params.get("use_paired_anchor", True)
        use_trend = params.get("use_trend_anchor", False)

        if mode == "extension" and not use_paired and not use_trend:
            raise ValueError(
                f"Structure '{key}': mode='extension' requires use_paired_anchor=true\n"
                f"\n"
                f"The 'extension' mode auto-determines direction based on the swing pair.\n"
                f"For bullish pairs (L->H): targets project ABOVE high\n"
                f"For bearish pairs (H->L): targets project BELOW low\n"
                f"\n"
                f"Fix: Add use_paired_anchor: true\n"
                f"  params:\n"
                f"    levels: [0.272, 0.618, 1.0]\n"
                f"    mode: extension\n"
                f"    use_paired_anchor: true\n"
                f"\n"
                f"Or use explicit modes:\n"
                f"  mode: extension_up    # Always above high\n"
                f"  mode: extension_down  # Always below low"
            )

        # Validate mutual exclusivity of trend and paired anchor
        if use_trend and use_paired:
            raise ValueError(
                f"Structure '{key}': use_trend_anchor and use_paired_anchor "
                f"are mutually exclusive\n"
                f"\n"
                f"use_trend_anchor implies paired anchoring internally.\n"
                f"Fix: Set use_paired_anchor: false when using "
                f"use_trend_anchor: true"
            )

    def __init__(
        self,
        params: dict[str, Any],
        deps: dict[str, BaseIncrementalDetector],
    ) -> None:
        """
        Initialize Fibonacci detector.

        Args:
            params: Dict with levels, optional mode, use_paired_anchor, use_trend_anchor.
            deps: Dict containing 'swing' dependency and optionally 'trend'.
        """
        self.swing = deps["swing"]
        self.levels: list[float] = [float(lvl) for lvl in params["levels"]]
        self.mode: str = params.get("mode", "retracement")
        self.use_trend_anchor: bool = params.get("use_trend_anchor", False)
        self.use_paired_anchor: bool = params.get("use_paired_anchor", True)

        if self.use_trend_anchor and self.use_paired_anchor:
            raise ValueError(
                "use_trend_anchor and use_paired_anchor are mutually exclusive. "
                "use_trend_anchor implies paired anchoring internally."
            )

        # Trend anchor setup
        if self.use_trend_anchor:
            if "trend" not in deps:
                raise ValueError(
                    "use_trend_anchor=true requires a trend dependency.\n"
                    "Fix: uses: [<swing_key>, <trend_key>]"
                )
            self.trend = deps["trend"]
            self._last_trend_version: int = -1
            self._last_trend_pair_version: int = -1
        else:
            self.trend = None

        # Note: 'extension' mode is NOT normalized - it uses direction-aware logic
        # in _compute_levels() that determines bullish (above high) vs bearish
        # (below low) based on pair_direction from the swing detector.

        # Level values storage: keyed by formatted level string
        self._values: dict[str, float | str | int] = {}

        # Initialize level outputs with NaN values
        for lvl in self.levels:
            key = self._format_level_key(lvl)
            self._values[key] = float("nan")

        # Initialize anchor outputs (always available)
        self._values["anchor_high"] = float("nan")
        self._values["anchor_low"] = float("nan")
        self._values["range"] = float("nan")
        self._values["anchor_direction"] = ""  # "bullish", "bearish", or ""
        self._values["anchor_hash"] = ""       # Hash from swing pair
        self._values["anchor_trend_direction"] = 0  # Trend direction at anchor

        # Track last known swing state to detect changes
        # For unpaired mode: track individual pivot indices
        self._last_high_idx: int = -1
        self._last_low_idx: int = -1
        # For paired mode: track pair_version
        self._last_pair_version: int = -1

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

        In trend mode: Checks if trend version or pair_version changed.
        In paired mode: Checks if pair_version has changed.
        In unpaired mode: Checks if high_idx or low_idx has changed.

        Args:
            bar_idx: Current bar index.
            bar: Bar data (not directly used, but required by interface).
        """
        if self.use_trend_anchor:
            # Trend-wave mode: recalculate when trend or pair changes
            assert self.trend is not None
            current_trend_version = int(self.trend.get_value("version"))
            current_pair_version = int(self.swing.get_value("pair_version"))
            if (current_trend_version != self._last_trend_version or
                    current_pair_version != self._last_trend_pair_version):
                self._recalculate_trend_anchored()
                self._last_trend_version = current_trend_version
                self._last_trend_pair_version = current_pair_version
        elif self.use_paired_anchor:
            # Paired mode: only recalculate when a complete pair forms
            current_pair_version = int(self.swing.get_value("pair_version"))
            if current_pair_version != self._last_pair_version:
                self._recalculate_paired()
                self._last_pair_version = current_pair_version
        else:
            # Unpaired mode: recalculate when any pivot changes
            current_high_idx = int(self.swing.get_value("high_idx"))
            current_low_idx = int(self.swing.get_value("low_idx"))

            if (current_high_idx != self._last_high_idx or
                    current_low_idx != self._last_low_idx):
                self._recalculate()
                self._last_high_idx = current_high_idx
                self._last_low_idx = current_low_idx

    def _recalculate(self) -> None:
        """
        Recalculate all Fibonacci levels from current swing points (unpaired mode).

        Uses high_level and low_level from the swing dependency.
        These may come from different swing sequences.
        Calculates levels based on mode:
        - retracement: levels between high and low
        - extension_up: levels above swing high
        - extension_down: levels below swing low
        """
        high = float(self.swing.get_value("high_level"))
        low = float(self.swing.get_value("low_level"))

        # Check for valid values (not NaN)
        if math.isnan(high) or math.isnan(low):
            return

        # Calculate range and update anchor outputs
        range_val = high - low
        self._values["anchor_high"] = high
        self._values["anchor_low"] = low
        self._values["range"] = range_val
        # Unpaired mode: no direction or hash
        self._values["anchor_direction"] = ""
        self._values["anchor_hash"] = ""

        # Compute each level based on mode
        self._compute_levels(high, low, range_val)

    def _recalculate_paired(self) -> None:
        """
        Recalculate all Fibonacci levels from paired swing anchors.

        Uses pair_high_level and pair_low_level from the swing dependency.
        These are guaranteed to come from the same swing sequence.
        """
        high = float(self.swing.get_value("pair_high_level"))
        low = float(self.swing.get_value("pair_low_level"))
        direction = str(self.swing.get_value("pair_direction"))
        anchor_hash = str(self.swing.get_value("pair_anchor_hash"))

        # Check for valid values (not NaN)
        if math.isnan(high) or math.isnan(low):
            return

        # Calculate range and update anchor outputs
        range_val = high - low
        self._values["anchor_high"] = high
        self._values["anchor_low"] = low
        self._values["range"] = range_val
        self._values["anchor_direction"] = direction
        self._values["anchor_hash"] = anchor_hash

        # Compute each level based on mode (pass direction for extension mode)
        self._compute_levels(high, low, range_val, direction)

    def _recalculate_trend_anchored(self) -> None:
        """
        Recalculate Fibonacci levels using trend-wave anchoring.

        Uses the trend detector's direction to contextualize the paired swing
        anchors. When direction=0 (ranging), keeps the last known anchors
        frozen to avoid flickering.
        """
        assert self.trend is not None
        direction = int(self.trend.get_value("direction"))
        if direction == 0:
            return  # Ranging — keep last known anchors

        high = float(self.swing.get_value("pair_high_level"))
        low = float(self.swing.get_value("pair_low_level"))

        if math.isnan(high) or math.isnan(low):
            return

        range_val = high - low
        self._values["anchor_high"] = high
        self._values["anchor_low"] = low
        self._values["range"] = range_val
        self._values["anchor_trend_direction"] = direction
        self._values["anchor_direction"] = "bullish" if direction == 1 else "bearish"
        self._values["anchor_hash"] = ""

        self._compute_levels(high, low, range_val,
                             "bullish" if direction == 1 else "bearish")

    def _compute_levels(
        self, high: float, low: float, range_val: float, direction: str = ""
    ) -> None:
        """
        Compute Fibonacci levels from anchor points.

        Unified formula: level = high - (ratio x range)
        - ratio < 0:     level > high (above high, long targets)
        - 0 <= ratio <= 1: low <= level <= high (retracement)
        - ratio > 1:     level < low (below low, short targets)

        Args:
            high: Swing high price
            low: Swing low price
            range_val: Price range (high - low)
            direction: "bullish" or "bearish" (for extension mode)
        """
        for lvl in self.levels:
            key = self._format_level_key(lvl)

            if self.mode == "retracement":
                # Unified formula: works with any ratio
                # ratio < 0: above high, ratio 0-1: between, ratio > 1: below low
                self._values[key] = high - (range_val * lvl)

            elif self.mode == "extension":
                # Auto-direction based on pair_direction
                # Bullish pair (L->H): targets ABOVE high -> negate the ratio
                # Bearish pair (H->L): targets BELOW low -> add 1 to ratio
                if direction == "bullish":
                    # Long targets: above high
                    # Input ratio 0.272 -> actual -0.272 -> high + 0.272 x range
                    self._values[key] = high + (range_val * lvl)
                elif direction == "bearish":
                    # Short targets: below low
                    # Input ratio 0.272 -> actual 1.272 -> low - 0.272 x range
                    self._values[key] = low - (range_val * lvl)
                else:
                    # No direction available (shouldn't happen with validation)
                    self._values[key] = float("nan")

            elif self.mode == "extension_up":
                # Legacy: levels projected above swing high
                # Formula: high + (ratio x range)
                self._values[key] = high + (range_val * lvl)

            elif self.mode == "extension_down":
                # Legacy: levels projected below swing low
                # Formula: low - (ratio x range)
                self._values[key] = low - (range_val * lvl)

    def reset(self) -> None:
        """Reset all mutable state to initial values."""
        for lvl in self.levels:
            key = self._format_level_key(lvl)
            self._values[key] = float("nan")
        self._values["anchor_high"] = float("nan")
        self._values["anchor_low"] = float("nan")
        self._values["range"] = float("nan")
        self._values["anchor_direction"] = ""
        self._values["anchor_hash"] = ""
        self._values["anchor_trend_direction"] = 0
        self._last_high_idx = -1
        self._last_low_idx = -1
        self._last_pair_version = -1
        if self.use_trend_anchor:
            self._last_trend_version = -1
            self._last_trend_pair_version = -1

    def to_dict(self) -> dict[str, Any]:
        """Serialize state for crash recovery."""
        state: dict[str, Any] = {
            "values": dict(self._values),
            "last_high_idx": self._last_high_idx,
            "last_low_idx": self._last_low_idx,
            "last_pair_version": self._last_pair_version,
        }
        if self.use_trend_anchor:
            state["last_trend_version"] = self._last_trend_version
            state["last_trend_pair_version"] = self._last_trend_pair_version
        return state

    def get_output_keys(self) -> list[str]:
        """
        Return list of output keys.

        Keys include:
        - Dynamic level keys from the levels parameter (e.g., 'level_0.618')
        - Fixed anchor keys: 'anchor_high', 'anchor_low', 'range',
                            'anchor_direction', 'anchor_hash'

        Returns:
            List of all output keys.
        """
        level_keys = [self._format_level_key(lvl) for lvl in self.levels]
        anchor_keys = [
            "anchor_high", "anchor_low", "range",
            "anchor_direction", "anchor_hash", "anchor_trend_direction",
        ]
        return level_keys + anchor_keys

    def get_value(self, key: str) -> float | str | int:
        """
        Get output by key.

        Args:
            key: Level key (e.g., 'level_0.618') or anchor key.

        Returns:
            Current level price (float), direction (str), hash (str),
            or trend direction (int).
            Returns NaN for numeric keys if not yet calculated.
            Returns "" for string keys if not yet available.

        Raises:
            KeyError: If key is not a valid output key.
        """
        if key in self._values:
            return self._values[key]
        raise KeyError(key)

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        levels_str = ", ".join(str(lvl) for lvl in self.levels)
        return f"IncrementalFibonacci(levels=[{levels_str}], mode={self.mode!r})"
