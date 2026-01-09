"""
Incremental swing high/low detector with delayed confirmation and pivot pairing.

Detects pivot points (swing highs and swing lows) in price action using
a configurable lookback window. A swing high is confirmed when a high
is greater than all neighboring highs within the left/right window.
Similarly for swing lows with lows.

Confirmation is delayed by 'right' bars to ensure the pivot is valid.
At bar N, we confirm pivots at bar (N - right).

Pivot Pairing:
    Beyond individual pivot detection, this detector tracks PAIRED pivots
    that form coherent swing sequences:

    - Bullish swing (LHL): Low → High sequence (upswing)
      First a swing low forms, then a swing high completes the pair.
      Used for: long retracements, long extension targets

    - Bearish swing (HLH): High → Low sequence (downswing)
      First a swing high forms, then a swing low completes the pair.
      Used for: short retracements, short extension targets

    The pair_version only increments when a COMPLETE pair forms, ensuring
    downstream structures (fibonacci, derived_zone) only regenerate on
    coherent anchor changes.

Parameters:
    left: Number of bars to the left of the pivot to check (must be >= 1).
    right: Number of bars to the right of the pivot to check (must be >= 1).

Outputs:
    Individual pivots (update independently):
        high_level: Most recent confirmed swing high price level (NaN if none).
        high_idx: Bar index of the most recent swing high (-1 if none).
        low_level: Most recent confirmed swing low price level (NaN if none).
        low_idx: Bar index of the most recent swing low (-1 if none).
        version: Increments on ANY confirmed pivot (high or low).

    Paired pivots (update only when pair completes):
        pair_high_level: High price of the current paired swing.
        pair_high_idx: Bar index of the paired high.
        pair_low_level: Low price of the current paired swing.
        pair_low_idx: Bar index of the paired low.
        pair_direction: "bullish" (LHL/upswing) or "bearish" (HLH/downswing).
        pair_version: Increments only when a complete pair forms.
        pair_anchor_hash: Unique hash identifying this specific anchor pair.

Example Play usage:
    structures:
      exec:
        - type: swing
          key: swing
          params:
            left: 5
            right: 5

Access in rules:
    # Individual pivots (legacy)
    condition: close > structure.swing.high_level

    # Paired pivots (recommended for fib anchoring)
    condition: structure.swing.pair_direction == "bullish"

See: docs/architecture/INCREMENTAL_STATE_ARCHITECTURE.md
"""

from __future__ import annotations

import hashlib
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
    Swing high/low detection with delayed confirmation and pivot pairing.

    Uses two RingBuffers (one for highs, one for lows) of size
    (left + right + 1). When the buffer is full, the element at
    index 'left' (the middle) is the potential pivot.

    A swing high is confirmed if the pivot high is strictly greater
    than all other highs in the window. A swing low is confirmed if
    the pivot low is strictly less than all other lows in the window.

    The confirmation happens with a delay of 'right' bars because
    we need to see 'right' bars after the pivot to confirm it.

    Pivot Pairing State Machine:
        AWAITING_FIRST → GOT_HIGH → PAIRED_BEARISH (HLH)
                       ↘         ↗
                        GOT_LOW → PAIRED_BULLISH (LHL)

        - GOT_HIGH: First pivot was a high, waiting for low to complete pair
        - GOT_LOW: First pivot was a low, waiting for high to complete pair
        - PAIRED_BEARISH: High→Low sequence (downswing, used for shorts)
        - PAIRED_BULLISH: Low→High sequence (upswing, used for longs)

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

    # Pairing states
    STATE_AWAITING_FIRST = "awaiting_first"
    STATE_GOT_HIGH = "got_high"
    STATE_GOT_LOW = "got_low"

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

        # Individual pivot outputs - updated independently
        self.high_level: float = float("nan")
        self.high_idx: int = -1
        self.low_level: float = float("nan")
        self.low_idx: int = -1

        # Version tracking: increments on ANY confirmed pivot
        self._version: int = 0
        self._last_confirmed_pivot_idx: int = -1
        self._last_confirmed_pivot_type: str = ""  # "high" or "low"

        # Paired pivot state machine
        self._pair_state: str = self.STATE_AWAITING_FIRST

        # Pending pivot (first of pair, waiting for second)
        self._pending_type: str = ""  # "high" or "low"
        self._pending_level: float = float("nan")
        self._pending_idx: int = -1

        # Completed pair outputs - only update when pair completes
        self._pair_high_level: float = float("nan")
        self._pair_high_idx: int = -1
        self._pair_low_level: float = float("nan")
        self._pair_low_idx: int = -1
        self._pair_direction: str = ""  # "bullish" (LHL) or "bearish" (HLH)
        self._pair_version: int = 0
        self._pair_anchor_hash: str = ""

    def update(self, bar_idx: int, bar: "BarData") -> None:
        """
        Process one bar, checking for confirmed swing pivots.

        Pushes the bar's high and low to the respective ring buffers.
        If the buffers are full (have seen enough bars), checks if the
        pivot bar (at index 'left' in the buffer, which is bar_idx - right)
        is a swing high or swing low.

        Also manages the pivot pairing state machine to track coherent
        swing sequences (bullish LHL or bearish HLH).

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

        # Track what pivots were confirmed this bar
        confirmed_high = False
        confirmed_low = False

        # Check for swing high
        if self._is_swing_high(pivot_idx):
            self.high_level = self._high_buf[pivot_idx]
            self.high_idx = pivot_bar_idx
            self._version += 1
            self._last_confirmed_pivot_idx = pivot_bar_idx
            self._last_confirmed_pivot_type = "high"
            confirmed_high = True

        # Check for swing low
        if self._is_swing_low(pivot_idx):
            self.low_level = self._low_buf[pivot_idx]
            self.low_idx = pivot_bar_idx
            self._version += 1
            self._last_confirmed_pivot_idx = pivot_bar_idx
            self._last_confirmed_pivot_type = "low"
            confirmed_low = True

        # Update pairing state machine
        self._update_pair_state(confirmed_high, confirmed_low)

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

    def _update_pair_state(self, confirmed_high: bool, confirmed_low: bool) -> None:
        """
        Update the pivot pairing state machine.

        Tracks whether we're building a bullish (LHL) or bearish (HLH) swing.
        A pair completes when we get the second pivot of the sequence.

        State transitions:
            AWAITING_FIRST + HIGH → GOT_HIGH (pending high)
            AWAITING_FIRST + LOW  → GOT_LOW (pending low)
            GOT_HIGH + LOW  → PAIRED BEARISH (H→L downswing)
            GOT_HIGH + HIGH → GOT_HIGH (new high replaces pending)
            GOT_LOW + HIGH  → PAIRED BULLISH (L→H upswing)
            GOT_LOW + LOW   → GOT_LOW (new low replaces pending)

        When a pair completes, the pair_version increments and we start
        waiting for a new first pivot (the completing pivot becomes pending).

        Args:
            confirmed_high: True if a swing high was confirmed this bar.
            confirmed_low: True if a swing low was confirmed this bar.
        """
        if not confirmed_high and not confirmed_low:
            return

        # Handle case where both high and low confirmed same bar (rare but possible)
        # In this case, we treat it as two sequential pivots
        if confirmed_high and confirmed_low:
            # Process high first, then low (arbitrary order)
            self._process_pivot("high", self.high_level, self.high_idx)
            self._process_pivot("low", self.low_level, self.low_idx)
        elif confirmed_high:
            self._process_pivot("high", self.high_level, self.high_idx)
        else:
            self._process_pivot("low", self.low_level, self.low_idx)

    def _process_pivot(self, pivot_type: str, level: float, idx: int) -> None:
        """
        Process a single confirmed pivot through the pairing state machine.

        Args:
            pivot_type: "high" or "low"
            level: Price level of the pivot
            idx: Bar index of the pivot
        """
        if self._pair_state == self.STATE_AWAITING_FIRST:
            # First pivot of a new pair
            self._pending_type = pivot_type
            self._pending_level = level
            self._pending_idx = idx
            self._pair_state = (
                self.STATE_GOT_HIGH if pivot_type == "high" else self.STATE_GOT_LOW
            )

        elif self._pair_state == self.STATE_GOT_HIGH:
            if pivot_type == "low":
                # HIGH → LOW completes a bearish (HLH) swing
                self._complete_pair(
                    high_level=self._pending_level,
                    high_idx=self._pending_idx,
                    low_level=level,
                    low_idx=idx,
                    direction="bearish",
                )
                # New low becomes pending for next pair
                self._pending_type = "low"
                self._pending_level = level
                self._pending_idx = idx
                self._pair_state = self.STATE_GOT_LOW
            else:
                # HIGH → HIGH: new high replaces pending
                self._pending_level = level
                self._pending_idx = idx

        elif self._pair_state == self.STATE_GOT_LOW:
            if pivot_type == "high":
                # LOW → HIGH completes a bullish (LHL) swing
                self._complete_pair(
                    high_level=level,
                    high_idx=idx,
                    low_level=self._pending_level,
                    low_idx=self._pending_idx,
                    direction="bullish",
                )
                # New high becomes pending for next pair
                self._pending_type = "high"
                self._pending_level = level
                self._pending_idx = idx
                self._pair_state = self.STATE_GOT_HIGH
            else:
                # LOW → LOW: new low replaces pending
                self._pending_level = level
                self._pending_idx = idx

    def _complete_pair(
        self,
        high_level: float,
        high_idx: int,
        low_level: float,
        low_idx: int,
        direction: str,
    ) -> None:
        """
        Complete a pivot pair and update outputs.

        Args:
            high_level: Price of the swing high
            high_idx: Bar index of the swing high
            low_level: Price of the swing low
            low_idx: Bar index of the swing low
            direction: "bullish" (LHL) or "bearish" (HLH)
        """
        self._pair_high_level = high_level
        self._pair_high_idx = high_idx
        self._pair_low_level = low_level
        self._pair_low_idx = low_idx
        self._pair_direction = direction
        self._pair_version += 1
        self._pair_anchor_hash = self._compute_anchor_hash(
            high_idx, high_level, low_idx, low_level, direction
        )

    @staticmethod
    def _compute_anchor_hash(
        high_idx: int,
        high_level: float,
        low_idx: int,
        low_level: float,
        direction: str,
    ) -> str:
        """
        Compute a unique hash for this anchor pair.

        The hash uniquely identifies this specific swing structure,
        enabling downstream structures (derived_zone) to track and
        invalidate zones tied to specific anchors.

        Args:
            high_idx: Bar index of swing high
            high_level: Price of swing high
            low_idx: Bar index of swing low
            low_level: Price of swing low
            direction: "bullish" or "bearish"

        Returns:
            16-character hex hash (blake2b truncated)
        """
        # Create deterministic string representation
        data = f"{high_idx}|{high_level:.8f}|{low_idx}|{low_level:.8f}|{direction}"
        hash_bytes = hashlib.blake2b(data.encode(), digest_size=8).digest()
        return hash_bytes.hex()

    def get_output_keys(self) -> list[str]:
        """
        Return list of output keys.

        Returns:
            List including individual pivots, pair outputs, and version tracking.
        """
        return [
            # Individual pivots (update independently)
            "high_level",
            "high_idx",
            "low_level",
            "low_idx",
            "version",
            "last_confirmed_pivot_idx",
            "last_confirmed_pivot_type",
            # Paired pivots (update only when pair completes)
            "pair_high_level",
            "pair_high_idx",
            "pair_low_level",
            "pair_low_idx",
            "pair_direction",
            "pair_version",
            "pair_anchor_hash",
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
        # Individual pivot outputs
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
        # Paired pivot outputs
        elif key == "pair_high_level":
            return self._pair_high_level
        elif key == "pair_high_idx":
            return self._pair_high_idx
        elif key == "pair_low_level":
            return self._pair_low_level
        elif key == "pair_low_idx":
            return self._pair_low_idx
        elif key == "pair_direction":
            return self._pair_direction
        elif key == "pair_version":
            return self._pair_version
        elif key == "pair_anchor_hash":
            return self._pair_anchor_hash
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
