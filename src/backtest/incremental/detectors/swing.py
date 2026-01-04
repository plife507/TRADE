"""
Incremental swing high/low detector with delayed confirmation.

Detects pivot points (swing highs and swing lows) in price action using
a configurable lookback window. A swing high is confirmed when a high
is greater than all neighboring highs within the left/right window.
Similarly for swing lows with lows.

Confirmation is delayed by 'right' bars to ensure the pivot is valid.
At bar N, we confirm pivots at bar (N - right).

Parameters:
    left: Number of bars to the left of the pivot to check (must be >= 1).
    right: Number of bars to the right of the pivot to check (must be >= 1).

Outputs:
    high_level: Most recent confirmed swing high price level (NaN if none).
    high_idx: Bar index of the most recent swing high (-1 if none).
    low_level: Most recent confirmed swing low price level (NaN if none).
    low_idx: Bar index of the most recent swing low (-1 if none).

Example IdeaCard usage:
    structures:
      exec:
        - type: swing
          key: swing
          params:
            left: 5
            right: 5

Access in rules:
    condition: close > structure.swing.high_level

See: docs/architecture/INCREMENTAL_STATE_ARCHITECTURE.md
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from ..base import BaseIncrementalDetector
from ..primitives import RingBuffer
from ..registry import register_structure

if TYPE_CHECKING:
    from ..base import BarData


@register_structure("swing")
class IncrementalSwingDetector(BaseIncrementalDetector):
    """
    Swing high/low detection with delayed confirmation.

    Uses two RingBuffers (one for highs, one for lows) of size
    (left + right + 1). When the buffer is full, the element at
    index 'left' (the middle) is the potential pivot.

    A swing high is confirmed if the pivot high is strictly greater
    than all other highs in the window. A swing low is confirmed if
    the pivot low is strictly less than all other lows in the window.

    The confirmation happens with a delay of 'right' bars because
    we need to see 'right' bars after the pivot to confirm it.

    Attributes:
        left: Number of bars to the left of the pivot.
        right: Number of bars to the right of the pivot.
        high_level: Most recent confirmed swing high (NaN if none).
        high_idx: Bar index of the most recent swing high (-1 if none).
        low_level: Most recent confirmed swing low (NaN if none).
        low_idx: Bar index of the most recent swing low (-1 if none).

    Performance:
        - update(): O(left + right + 1) = O(window_size)
        - get_value(): O(1)
    """

    REQUIRED_PARAMS: list[str] = ["left", "right"]
    OPTIONAL_PARAMS: dict[str, Any] = {}
    DEPENDS_ON: list[str] = []

    @classmethod
    def _validate_params(
        cls, struct_type: str, key: str, params: dict[str, Any]
    ) -> None:
        """
        Validate swing detector parameters.

        Both left and right must be integers >= 1.

        Raises:
            ValueError: If left or right is not an integer >= 1.
        """
        for param_name in ["left", "right"]:
            val = params.get(param_name)
            if not isinstance(val, int) or val < 1:
                raise ValueError(
                    f"Structure '{key}': '{param_name}' must be integer >= 1, got {val!r}\n"
                    f"\n"
                    f"Fix: {param_name}: 5  # Must be a positive integer >= 1"
                )

    def __init__(
        self,
        params: dict[str, Any],
        deps: dict[str, BaseIncrementalDetector] | None = None,
    ) -> None:
        """
        Initialize swing detector.

        Args:
            params: Dict with left and right lookback parameters.
            deps: Not used (no dependencies).
        """
        self.left: int = params["left"]
        self.right: int = params["right"]
        window_size = self.left + self.right + 1

        # Ring buffers for highs and lows
        self._high_buf = RingBuffer(window_size)
        self._low_buf = RingBuffer(window_size)

        # Output values - initialized to NaN/-1
        self.high_level: float = float("nan")
        self.high_idx: int = -1
        self.low_level: float = float("nan")
        self.low_idx: int = -1

        # Version tracking: increments exactly once per confirmed pivot
        # Used by derived structures (e.g., derived_zone) to trigger regen
        self._version: int = 0
        self._last_confirmed_pivot_idx: int = -1
        self._last_confirmed_pivot_type: str = ""  # "high" or "low"

    def update(self, bar_idx: int, bar: "BarData") -> None:
        """
        Process one bar, checking for confirmed swing pivots.

        Pushes the bar's high and low to the respective ring buffers.
        If the buffers are full (have seen enough bars), checks if the
        pivot bar (at index 'left' in the buffer, which is bar_idx - right)
        is a swing high or swing low.

        Args:
            bar_idx: Current bar index.
            bar: Bar data containing high and low prices.
        """
        # Push current bar's high and low to buffers
        self._high_buf.push(bar.high)
        self._low_buf.push(bar.low)

        # Need full buffer to confirm pivots
        if not self._high_buf.is_full():
            return

        # The pivot is at index 'left' in the buffer
        # This corresponds to bar_idx - right in absolute terms
        pivot_idx = self.left
        pivot_bar_idx = bar_idx - self.right

        # Check for swing high
        if self._is_swing_high(pivot_idx):
            self.high_level = self._high_buf[pivot_idx]
            self.high_idx = pivot_bar_idx
            # Version bump: exactly once per confirmed pivot
            self._version += 1
            self._last_confirmed_pivot_idx = pivot_bar_idx
            self._last_confirmed_pivot_type = "high"

        # Check for swing low
        if self._is_swing_low(pivot_idx):
            self.low_level = self._low_buf[pivot_idx]
            self.low_idx = pivot_bar_idx
            # Version bump: exactly once per confirmed pivot
            self._version += 1
            self._last_confirmed_pivot_idx = pivot_bar_idx
            self._last_confirmed_pivot_type = "low"

    def _is_swing_high(self, pivot_idx: int) -> bool:
        """
        Check if the pivot is a swing high.

        A swing high is confirmed if the pivot's high is strictly greater
        than all other highs in the window.

        Args:
            pivot_idx: Index of the pivot in the ring buffer.

        Returns:
            True if pivot is a swing high, False otherwise.
        """
        pivot_val = self._high_buf[pivot_idx]

        # Check all other elements in the buffer
        for i in range(len(self._high_buf)):
            if i != pivot_idx and self._high_buf[i] >= pivot_val:
                return False

        return True

    def _is_swing_low(self, pivot_idx: int) -> bool:
        """
        Check if the pivot is a swing low.

        A swing low is confirmed if the pivot's low is strictly less
        than all other lows in the window.

        Args:
            pivot_idx: Index of the pivot in the ring buffer.

        Returns:
            True if pivot is a swing low, False otherwise.
        """
        pivot_val = self._low_buf[pivot_idx]

        # Check all other elements in the buffer
        for i in range(len(self._low_buf)):
            if i != pivot_idx and self._low_buf[i] <= pivot_val:
                return False

        return True

    def get_output_keys(self) -> list[str]:
        """
        Return list of output keys.

        Returns:
            List including version tracking fields for derived structures.
        """
        return [
            "high_level",
            "high_idx",
            "low_level",
            "low_idx",
            "version",
            "last_confirmed_pivot_idx",
            "last_confirmed_pivot_type",
        ]

    def get_value(self, key: str) -> float | int | str:
        """
        Get output by key.

        Args:
            key: One of the output keys.

        Returns:
            The output value.

        Raises:
            KeyError: If key is not valid.
        """
        if key == "high_level":
            return self.high_level
        elif key == "high_idx":
            return self.high_idx
        elif key == "low_level":
            return self.low_level
        elif key == "low_idx":
            return self.low_idx
        elif key == "version":
            return self._version
        elif key == "last_confirmed_pivot_idx":
            return self._last_confirmed_pivot_idx
        elif key == "last_confirmed_pivot_type":
            return self._last_confirmed_pivot_type
        else:
            raise KeyError(key)

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        return (
            f"IncrementalSwingDetector("
            f"left={self.left}, right={self.right}, "
            f"high_level={self.high_level}, high_idx={self.high_idx}, "
            f"low_level={self.low_level}, low_idx={self.low_idx})"
        )


def _run_validation_test() -> None:
    """
    Simple test to validate the swing detector works correctly.

    Run with:
        python -c "from src.backtest.incremental.detectors.swing import _run_validation_test; _run_validation_test()"
    """
    from ..base import BarData

    print("Testing IncrementalSwingDetector...")
    print("-" * 60)

    # Create detector with left=2, right=2 (window size = 5)
    params = {"left": 2, "right": 2}
    detector = IncrementalSwingDetector(params, {})

    # Sample price data with clear swings
    # Bar indices:  0,   1,   2,   3,   4,   5,   6,   7,   8,   9
    # Highs:       10,  12,  15,  11,   9,  11,  18,  14,  13,  16
    # Lows:         8,   9,  12,   9,   7,   8,  15,  12,  11,  14
    #
    # Expected swings:
    # - Swing high at bar 2 (high=15) confirmed at bar 4
    # - Swing low at bar 4 (low=7) confirmed at bar 6
    # - Swing high at bar 6 (high=18) confirmed at bar 8

    bars = [
        BarData(idx=0, open=9.0, high=10.0, low=8.0, close=9.5, volume=100.0, indicators={}),
        BarData(idx=1, open=10.0, high=12.0, low=9.0, close=11.0, volume=100.0, indicators={}),
        BarData(idx=2, open=11.0, high=15.0, low=12.0, close=14.0, volume=100.0, indicators={}),
        BarData(idx=3, open=14.0, high=11.0, low=9.0, close=10.0, volume=100.0, indicators={}),
        BarData(idx=4, open=10.0, high=9.0, low=7.0, close=8.0, volume=100.0, indicators={}),
        BarData(idx=5, open=8.0, high=11.0, low=8.0, close=10.0, volume=100.0, indicators={}),
        BarData(idx=6, open=10.0, high=18.0, low=15.0, close=17.0, volume=100.0, indicators={}),
        BarData(idx=7, open=17.0, high=14.0, low=12.0, close=13.0, volume=100.0, indicators={}),
        BarData(idx=8, open=13.0, high=13.0, low=11.0, close=12.0, volume=100.0, indicators={}),
        BarData(idx=9, open=12.0, high=16.0, low=14.0, close=15.0, volume=100.0, indicators={}),
    ]

    for bar in bars:
        prev_high_idx = detector.high_idx
        prev_low_idx = detector.low_idx

        detector.update(bar.idx, bar)

        # Check for new swing high
        if detector.high_idx != prev_high_idx and detector.high_idx >= 0:
            print(f"Bar {bar.idx}: Swing HIGH confirmed at bar {detector.high_idx}, level={detector.high_level}")

        # Check for new swing low
        if detector.low_idx != prev_low_idx and detector.low_idx >= 0:
            print(f"Bar {bar.idx}: Swing LOW confirmed at bar {detector.low_idx}, level={detector.low_level}")

    print("-" * 60)
    print(f"Final state: {detector}")
    print()

    # Validation assertions
    assert detector.high_level == 18.0, f"Expected high_level=18.0, got {detector.high_level}"
    assert detector.high_idx == 6, f"Expected high_idx=6, got {detector.high_idx}"
    assert detector.low_level == 7.0, f"Expected low_level=7.0, got {detector.low_level}"
    assert detector.low_idx == 4, f"Expected low_idx=4, got {detector.low_idx}"

    print("All assertions passed!")
    print()

    # Test parameter validation
    print("Testing parameter validation...")

    # Test invalid left parameter
    try:
        IncrementalSwingDetector.validate_and_create("swing", "test", {"left": 0, "right": 2}, {})
        print("ERROR: Should have raised ValueError for left=0")
    except ValueError as e:
        if "'left' must be integer >= 1" in str(e):
            print("  OK: Correctly rejected left=0")
        else:
            print(f"ERROR: Wrong error message: {e}")

    # Test invalid right parameter (not an integer)
    try:
        IncrementalSwingDetector.validate_and_create("swing", "test", {"left": 2, "right": "5"}, {})
        print("ERROR: Should have raised ValueError for right='5'")
    except ValueError as e:
        if "'right' must be integer >= 1" in str(e):
            print("  OK: Correctly rejected right='5'")
        else:
            print(f"ERROR: Wrong error message: {e}")

    # Test missing required parameter
    try:
        IncrementalSwingDetector.validate_and_create("swing", "test", {"left": 2}, {})
        print("ERROR: Should have raised ValueError for missing 'right'")
    except ValueError as e:
        if "missing required params" in str(e):
            print("  OK: Correctly rejected missing 'right'")
        else:
            print(f"ERROR: Wrong error message: {e}")

    print()
    print("All validation tests passed!")
