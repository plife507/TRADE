"""
Incremental trend detector with wave-based tracking.

Gate 4 implementation: Fixes state memory issue by tracking complete swing waves
instead of individual HH/HL comparisons.

Classifies trend based on wave sequence:
- Higher highs + higher lows = uptrend (direction = 1)
- Lower highs + lower lows = downtrend (direction = -1)
- Mixed = ranging (direction = 0)

Wave-based tracking provides:
- Proper recovery detection (LL then HH, HH, HH correctly identifies trend change)
- Strength classification (0=weak, 1=normal, 2=strong)
- Complete wave history for analysis

Requires a swing detector as a dependency to provide swing high/low levels.

Outputs:
- direction: int (1 = uptrend, -1 = downtrend, 0 = ranging)
- strength: int (0 = weak/ranging, 1 = normal, 2 = strong)
- bars_in_trend: int (increments each bar, resets on direction change)
- wave_count: int (consecutive waves in same direction)
- last_wave_direction: str ("bullish", "bearish", or "none")
- last_hh: bool (was last high a higher high?)
- last_hl: bool (was last low a higher low?)
- last_lh: bool (was last high a lower high?)
- last_ll: bool (was last low a lower low?)
- version: int (increments on direction change)

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
See: docs/todos/PIVOT_FOUNDATION_GATES.md (Gate 4)
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..base import BaseIncrementalDetector
from ..registry import register_structure

if TYPE_CHECKING:
    from ..base import BarData


@dataclass
class Wave:
    """
    A complete swing wave (L→H or H→L).

    Tracks the transition from one swing point to another and
    stores comparison results against the previous wave.
    """

    # Wave endpoints
    start_type: str  # "high" or "low"
    start_level: float
    start_idx: int
    end_type: str  # "high" or "low"
    end_level: float
    end_idx: int

    # Wave direction
    direction: str  # "bullish" (L→H) or "bearish" (H→L)

    # Comparison to previous same-type level
    # For bullish wave (L→H): end is high, compare to prev high
    # For bearish wave (H→L): end is low, compare to prev low
    is_higher_high: bool | None = None  # True if end > prev high
    is_higher_low: bool | None = None  # True if start > prev low
    is_lower_high: bool | None = None  # True if end < prev high
    is_lower_low: bool | None = None  # True if start < prev low


@register_structure("trend")
class IncrementalTrendDetector(BaseIncrementalDetector):
    """
    Trend classification from swing wave sequence.

    Gate 4 Implementation: Wave-based tracking.

    Instead of tracking individual HH/HL comparisons (which lose state),
    this implementation tracks complete waves and their structural relationships.

    A wave is formed when we get a H-L or L-H swing pair. We track the last
    4 waves and classify trend based on the wave sequence:

    - Strong uptrend (direction=1, strength=2):
        2+ consecutive waves with HH+HL
    - Normal uptrend (direction=1, strength=1):
        Most recent wave has HH+HL
    - Strong downtrend (direction=-1, strength=2):
        2+ consecutive waves with LH+LL
    - Normal downtrend (direction=-1, strength=1):
        Most recent wave has LH+LL
    - Ranging (direction=0, strength=0):
        Mixed conditions or insufficient data

    This fixes the state memory issue where recovery patterns were incorrectly
    classified (e.g., LL followed by HH, HH, HH should show trend recovery).
    """

    REQUIRED_PARAMS: list[str] = []
    OPTIONAL_PARAMS: dict[str, Any] = {
        "wave_history_size": 4,  # Number of waves to track
    }
    DEPENDS_ON: list[str] = ["swing"]

    def __init__(self, params: dict[str, Any], deps: dict[str, BaseIncrementalDetector]):
        """
        Initialize the wave-based trend detector.

        Args:
            params: Configuration params.
            deps: Dependencies dict. Must contain "swing" with a swing detector.
        """
        self.swing = deps["swing"]
        self._wave_history_size = params.get("wave_history_size", 4)

        # Wave tracking
        self._waves: deque[Wave] = deque(maxlen=self._wave_history_size)

        # Track previous swing levels for comparison
        self._prev_high: float = float("nan")
        self._prev_low: float = float("nan")

        # Track last seen swing indices to detect new swings
        self._last_high_idx: int = -1
        self._last_low_idx: int = -1

        # Pending wave endpoint (waiting for opposite swing to complete wave)
        self._pending_type: str | None = None  # "high" or "low"
        self._pending_level: float = float("nan")
        self._pending_idx: int = -1

        # Output values
        self.direction: int = 0  # 0 = ranging, 1 = uptrend, -1 = downtrend
        self.strength: int = 0  # 0 = weak, 1 = normal, 2 = strong
        self.bars_in_trend: int = 0
        self.wave_count: int = 0  # Consecutive waves in same direction
        self.last_wave_direction: str = "none"  # "bullish", "bearish", "none"

        # Individual comparison outputs (from last wave)
        self.last_hh: bool = False  # Was last high a higher high?
        self.last_hl: bool = False  # Was last low a higher low?
        self.last_lh: bool = False  # Was last high a lower high?
        self.last_ll: bool = False  # Was last low a lower low?

        # Version tracking: increments when direction changes
        self._version: int = 0

    def update(self, bar_idx: int, bar: "BarData") -> None:
        """
        Process one bar and update trend classification.

        Called on every TF bar close. Checks if swing detector has detected
        new swing highs or lows, and if so, updates the wave tracking and
        trend classification.

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

        # Get current swing levels
        current_high = self.swing.high_level
        current_low = self.swing.low_level

        # Process swing changes to form waves
        # We need to handle both highs and lows, potentially in order
        events = []
        if high_changed:
            events.append(("high", current_high, high_idx))
        if low_changed:
            events.append(("low", current_low, low_idx))

        # Sort by index to process in chronological order
        events.sort(key=lambda e: e[2])

        for pivot_type, level, idx in events:
            self._process_swing(pivot_type, level, idx)

        # Update previous levels for next comparison
        if high_changed:
            self._prev_high = current_high
            self._last_high_idx = high_idx

        if low_changed:
            self._prev_low = current_low
            self._last_low_idx = low_idx

    def _process_swing(self, pivot_type: str, level: float, idx: int) -> None:
        """
        Process a new swing point and potentially complete a wave.

        Args:
            pivot_type: "high" or "low"
            level: Swing level price
            idx: Bar index of swing
        """
        if self._pending_type is None:
            # First swing - just store as pending
            self._pending_type = pivot_type
            self._pending_level = level
            self._pending_idx = idx
            return

        if pivot_type == self._pending_type:
            # Same type as pending - this can happen with strict_alternation=false
            # Update pending if this extends it
            if pivot_type == "high" and level >= self._pending_level:
                self._pending_level = level
                self._pending_idx = idx
            elif pivot_type == "low" and level <= self._pending_level:
                self._pending_level = level
                self._pending_idx = idx
            return

        # Opposite type - complete the wave
        wave = self._create_wave(
            start_type=self._pending_type,
            start_level=self._pending_level,
            start_idx=self._pending_idx,
            end_type=pivot_type,
            end_level=level,
            end_idx=idx,
        )

        self._waves.append(wave)
        self._update_comparison_outputs(wave)

        # Start new pending
        self._pending_type = pivot_type
        self._pending_level = level
        self._pending_idx = idx

        # Reclassify trend
        self._classify_trend()

    def _create_wave(
        self,
        start_type: str,
        start_level: float,
        start_idx: int,
        end_type: str,
        end_level: float,
        end_idx: int,
    ) -> Wave:
        """
        Create a wave with comparison values calculated.

        Args:
            start_type: "high" or "low"
            start_level: Start price level
            start_idx: Start bar index
            end_type: "high" or "low"
            end_level: End price level
            end_idx: End bar index

        Returns:
            Completed Wave object with comparison flags set.
        """
        # Determine wave direction
        if start_type == "low" and end_type == "high":
            direction = "bullish"
        else:
            direction = "bearish"

        wave = Wave(
            start_type=start_type,
            start_level=start_level,
            start_idx=start_idx,
            end_type=end_type,
            end_level=end_level,
            end_idx=end_idx,
            direction=direction,
        )

        # Calculate comparisons against previous levels
        if end_type == "high" and not math.isnan(self._prev_high):
            wave.is_higher_high = end_level > self._prev_high
            wave.is_lower_high = end_level < self._prev_high

        if end_type == "low" and not math.isnan(self._prev_low):
            wave.is_lower_low = end_level < self._prev_low
            wave.is_higher_low = end_level > self._prev_low

        # Also check start of wave for full picture
        if start_type == "high" and not math.isnan(self._prev_high):
            wave.is_higher_high = start_level > self._prev_high
            wave.is_lower_high = start_level < self._prev_high

        if start_type == "low" and not math.isnan(self._prev_low):
            wave.is_lower_low = start_level < self._prev_low
            wave.is_higher_low = start_level > self._prev_low

        return wave

    def _update_comparison_outputs(self, wave: Wave) -> None:
        """
        Update the individual comparison output flags from a wave.

        Args:
            wave: The most recent completed wave.
        """
        self.last_wave_direction = wave.direction

        # Update comparison flags based on wave endpoint
        if wave.end_type == "high":
            if wave.is_higher_high is not None:
                self.last_hh = wave.is_higher_high
                self.last_lh = wave.is_lower_high if wave.is_lower_high is not None else not wave.is_higher_high

        if wave.end_type == "low":
            if wave.is_lower_low is not None:
                self.last_ll = wave.is_lower_low
                self.last_hl = wave.is_higher_low if wave.is_higher_low is not None else not wave.is_lower_low

        # Also update from wave start
        if wave.start_type == "high":
            if wave.is_higher_high is not None:
                self.last_hh = wave.is_higher_high
                self.last_lh = wave.is_lower_high if wave.is_lower_high is not None else not wave.is_higher_high

        if wave.start_type == "low":
            if wave.is_lower_low is not None:
                self.last_ll = wave.is_lower_low
                self.last_hl = wave.is_higher_low if wave.is_higher_low is not None else not wave.is_lower_low

    def _classify_trend(self) -> None:
        """
        Classify trend direction and strength from wave history.

        Uses the wave sequence to determine:
        - direction: 1 (up), -1 (down), 0 (ranging)
        - strength: 0 (weak), 1 (normal), 2 (strong)
        """
        if len(self._waves) < 1:
            new_dir = 0
            new_strength = 0
            new_wave_count = 0
        elif len(self._waves) == 1:
            # Single wave - direction from wave type, weak strength
            wave = self._waves[-1]
            if wave.direction == "bullish":
                new_dir = 1
            else:
                new_dir = -1
            new_strength = 0
            new_wave_count = 1
        else:
            # Multiple waves - analyze sequence
            new_dir, new_strength, new_wave_count = self._analyze_wave_sequence()

        # If direction changed, reset bars_in_trend and bump version
        if new_dir != self.direction:
            self.direction = new_dir
            self.bars_in_trend = 0
            self._version += 1
        else:
            self.bars_in_trend += 1

        self.strength = new_strength
        self.wave_count = new_wave_count

    def _analyze_wave_sequence(self) -> tuple[int, int, int]:
        """
        Analyze wave sequence for trend direction and strength.

        Returns:
            Tuple of (direction, strength, wave_count).
        """
        # Start from most recent and work back
        recent = self._waves[-1]

        # Check most recent wave for HH+HL or LH+LL pattern
        recent_bullish = self._is_bullish_wave(recent)
        recent_bearish = self._is_bearish_wave(recent)

        if not recent_bullish and not recent_bearish:
            # Mixed signals in most recent wave - ranging
            return (0, 0, 0)

        # Count consecutive waves in same direction
        consecutive = 1
        target_dir = 1 if recent_bullish else -1

        for i in range(len(self._waves) - 2, -1, -1):
            wave = self._waves[i]
            if target_dir == 1 and self._is_bullish_wave(wave):
                consecutive += 1
            elif target_dir == -1 and self._is_bearish_wave(wave):
                consecutive += 1
            else:
                break

        # Determine strength
        if consecutive >= 2:
            strength = 2  # Strong
        elif consecutive == 1:
            strength = 1  # Normal
        else:
            strength = 0  # Weak

        return (target_dir, strength, consecutive)

    def _is_bullish_wave(self, wave: Wave) -> bool:
        """
        Check if a wave represents bullish structure (HH + HL).

        For a bullish classification, we need both:
        - The high endpoint is a higher high (or wave contains HH)
        - The low endpoint is a higher low (or wave contains HL)

        Args:
            wave: Wave to analyze.

        Returns:
            True if wave shows bullish structure.
        """
        # Check for HH (higher high)
        has_hh = wave.is_higher_high is True

        # Check for HL (higher low)
        has_hl = wave.is_higher_low is True

        # Both conditions must be met, or at least one with neutral other
        if has_hh and has_hl:
            return True
        if has_hh and wave.is_higher_low is None:
            return True
        if has_hl and wave.is_higher_high is None:
            return True

        return False

    def _is_bearish_wave(self, wave: Wave) -> bool:
        """
        Check if a wave represents bearish structure (LH + LL).

        For a bearish classification, we need both:
        - The high endpoint is a lower high (or wave contains LH)
        - The low endpoint is a lower low (or wave contains LL)

        Args:
            wave: Wave to analyze.

        Returns:
            True if wave shows bearish structure.
        """
        # Check for LH (lower high)
        has_lh = wave.is_lower_high is True

        # Check for LL (lower low)
        has_ll = wave.is_lower_low is True

        # Both conditions must be met, or at least one with neutral other
        if has_lh and has_ll:
            return True
        if has_lh and wave.is_lower_low is None:
            return True
        if has_ll and wave.is_lower_high is None:
            return True

        return False

    def get_output_keys(self) -> list[str]:
        """
        List of readable output keys.

        Returns:
            List of output key names.
        """
        return [
            "direction",
            "strength",
            "bars_in_trend",
            "wave_count",
            "last_wave_direction",
            "last_hh",
            "last_hl",
            "last_lh",
            "last_ll",
            "version",
        ]

    def get_value(self, key: str) -> int | float | str | bool:
        """
        Get output by key. O(1).

        Args:
            key: Output key name.

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
        elif key == "wave_count":
            return self.wave_count
        elif key == "last_wave_direction":
            return self.last_wave_direction
        elif key == "last_hh":
            return self.last_hh
        elif key == "last_hl":
            return self.last_hl
        elif key == "last_lh":
            return self.last_lh
        elif key == "last_ll":
            return self.last_ll
        elif key == "version":
            return self._version
        else:
            raise KeyError(key)
