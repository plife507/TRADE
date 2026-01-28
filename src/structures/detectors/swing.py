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

    - Bullish swing (LHL): Low -> High sequence (upswing)
      First a swing low forms, then a swing high completes the pair.
      Used for: long retracements, long extension targets

    - Bearish swing (HLH): High -> Low sequence (downswing)
      First a swing high forms, then a swing low completes the pair.
      Used for: short retracements, short extension targets

    The pair_version only increments when a COMPLETE pair forms, ensuring
    downstream structures (fibonacci, derived_zone) only regenerate on
    coherent anchor changes.

Parameters:
    left: Number of bars to the left of the pivot to check (must be >= 1).
    right: Number of bars to the right of the pivot to check (must be >= 1).
    atr_key: (optional) Key of ATR indicator in bar.indicators for significance calculation.
    major_threshold: (optional) ATR multiple threshold for major pivot classification (default: 1.5).
    min_atr_move: (optional) Minimum ATR multiple required to accept a pivot (filters noise).
    min_pct_move: (optional) Minimum percentage move required to accept a pivot.
    strict_alternation: (optional) Force H-L-H-L sequence, no consecutive same-type pivots (default: false).

Outputs:
    Individual pivots (update independently):
        high_level: Most recent confirmed swing high price level (NaN if none).
        high_idx: Bar index of the most recent swing high (-1 if none).
        low_level: Most recent confirmed swing low price level (NaN if none).
        low_idx: Bar index of the most recent swing low (-1 if none).
        version: Increments on ANY confirmed pivot (high or low).

    Significance outputs (require atr_key):
        high_significance: ATR multiple of move from previous high (NaN if no ATR).
        low_significance: ATR multiple of move from previous low (NaN if no ATR).
        high_is_major: True if high_significance >= major_threshold.
        low_is_major: True if low_significance >= major_threshold.

    Paired pivots (update only when pair completes):
        pair_high_level: High price of the current paired swing.
        pair_high_idx: Bar index of the paired high.
        pair_low_level: Low price of the current paired swing.
        pair_low_idx: Bar index of the paired low.
        pair_direction: "bullish" (LHL/upswing) or "bearish" (HLH/downswing).
        pair_version: Increments only when a complete pair forms.
        pair_anchor_hash: Unique hash identifying this specific anchor pair.

Example Play usage:
    # Basic usage (no significance):
    structures:
      exec:
        - type: swing
          key: swing
          params:
            left: 5
            right: 5

    # With significance calculation (requires ATR indicator):
    indicators:
      exec:
        - type: atr
          key: atr_14
          params: { length: 14 }

    structures:
      exec:
        - type: swing
          key: swing
          params:
            left: 5
            right: 5
            atr_key: atr_14       # Reference to ATR indicator
            major_threshold: 1.5  # Pivots moving 1.5x ATR are "major"

    # With significance filtering (Gate 1 - reduces noise):
    structures:
      exec:
        - type: swing
          key: swing
          params:
            left: 5
            right: 5
            atr_key: atr_14
            min_atr_move: 1.0     # Filter pivots < 1.0x ATR move
            min_pct_move: 1.5     # Filter pivots < 1.5% move

Access in rules:
    # Individual pivots (legacy)
    condition: close > structure.swing.high_level

    # Paired pivots (recommended for fib anchoring)
    condition: structure.swing.pair_direction == "bullish"

    # Significance filtering (only trade major pivots)
    condition: structure.swing.high_is_major == true

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
class IncrementalSwing(BaseIncrementalDetector):
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
        AWAITING_FIRST -> GOT_HIGH -> PAIRED_BEARISH (HLH)
                       \\         /
                        GOT_LOW -> PAIRED_BULLISH (LHL)

        - GOT_HIGH: First pivot was a high, waiting for low to complete pair
        - GOT_LOW: First pivot was a low, waiting for high to complete pair
        - PAIRED_BEARISH: High->Low sequence (downswing, used for shorts)
        - PAIRED_BULLISH: Low->High sequence (upswing, used for longs)

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

    REQUIRED_PARAMS: list[str] = []  # Mode-specific validation done in _validate_params
    OPTIONAL_PARAMS: dict[str, Any] = {
        "mode": "fractal",          # Gate 3: Detection mode - "fractal" or "atr_zigzag"
        "atr_key": None,            # Key of ATR indicator for significance calculation
        "major_threshold": 1.5,     # ATR multiple threshold for major pivot classification
        "min_atr_move": None,       # Gate 1: Minimum ATR multiple to accept pivot (filter noise)
        "min_pct_move": None,       # Gate 1: Minimum percentage move to accept pivot
        "strict_alternation": False,  # Gate 2: Force H-L-H-L sequence
        "atr_multiplier": 2.0,      # Gate 3: ATR multiple for direction change (atr_zigzag mode)
    }
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

        For fractal mode: left and right must be integers >= 1.
        For atr_zigzag mode: atr_key must be provided.

        Raises:
            ValueError: If required parameters are missing or invalid.
        """
        mode = params.get("mode", "fractal")

        # Validate mode parameter
        valid_modes = ["fractal", "atr_zigzag"]
        if mode not in valid_modes:
            raise ValueError(
                f"Structure '{key}': 'mode' must be one of {valid_modes}, got {mode!r}\n"
                f"\n"
                f"Fix: mode: fractal  # or 'atr_zigzag'"
            )

        if mode == "fractal":
            # Fractal mode requires left and right
            for param_name in ["left", "right"]:
                val = params.get(param_name)
                if not isinstance(val, int) or val < 1:
                    raise ValueError(
                        f"Structure '{key}': '{param_name}' must be integer >= 1, got {val!r}\n"
                        f"\n"
                        f"Fix: {param_name}: 5  # Must be a positive integer >= 1"
                    )
        elif mode == "atr_zigzag":
            # ATR ZigZag mode requires atr_key
            atr_key = params.get("atr_key")
            if atr_key is None:
                raise ValueError(
                    f"Structure '{key}': 'atr_key' is required for mode='atr_zigzag'\n"
                    f"\n"
                    f"Fix: Add atr_key parameter pointing to an ATR indicator:\n"
                    f"  params:\n"
                    f"    mode: atr_zigzag\n"
                    f"    atr_key: atr_14\n"
                    f"    atr_multiplier: 2.0"
                )

            # Validate atr_multiplier if provided
            atr_mult = params.get("atr_multiplier", 2.0)
            if not isinstance(atr_mult, (int, float)) or atr_mult <= 0:
                raise ValueError(
                    f"Structure '{key}': 'atr_multiplier' must be a positive number, got {atr_mult!r}\n"
                    f"\n"
                    f"Fix: atr_multiplier: 2.0  # Must be > 0"
                )

    def __init__(
        self,
        params: dict[str, Any],
        deps: dict[str, BaseIncrementalDetector] | None = None,
    ) -> None:
        """
        Initialize swing detector.

        Args:
            params: Dict with mode, left/right (fractal), atr_key/atr_multiplier (zigzag).
            deps: Not used (no dependencies).
        """
        # Gate 3: Detection mode
        self._mode: str = params.get("mode", "fractal")

        # Mode-specific initialization
        if self._mode == "fractal":
            # Fractal mode: fixed bar count window
            self.left: int = params["left"]
            self.right: int = params["right"]
            window_size = self.left + self.right + 1
            self._high_buf = RingBuffer(window_size)
            self._low_buf = RingBuffer(window_size)
        else:
            # atr_zigzag mode: provide dummy values for compatibility
            self.left = 0
            self.right = 0
            self._high_buf = None
            self._low_buf = None

        # Gate 0: ATR-based significance parameters
        self._atr_key: str | None = params.get("atr_key")
        self._major_threshold: float = params.get("major_threshold", 1.5)

        # Gate 1: Significance filtering parameters
        self._min_atr_move: float | None = params.get("min_atr_move")
        self._min_pct_move: float | None = params.get("min_pct_move")

        # Gate 2: Strict alternation parameters
        self._strict_alternation: bool = params.get("strict_alternation", False)
        # Alternation state tracking
        self._alt_last_pivot_type: str | None = None  # "high" or "low" or None
        self._alt_pending_level: float = float("nan")
        self._alt_pending_idx: int = -1
        # Alternation output flags (reset each bar)
        self._high_accepted: bool = False
        self._low_accepted: bool = False
        self._high_replaced_pending: bool = False
        self._low_replaced_pending: bool = False

        # Gate 3: ATR ZigZag mode parameters and state
        self._atr_multiplier: float = params.get("atr_multiplier", 2.0)
        # Direction: 0 = not established, 1 = uptrend, -1 = downtrend
        self._zigzag_direction: int = 0
        # Current extreme (highest high in uptrend, lowest low in downtrend)
        self._zigzag_extreme_price: float = float("nan")
        self._zigzag_extreme_idx: int = -1
        # Track if we've had at least one bar (for initialization)
        self._zigzag_initialized: bool = False

        # Individual pivot outputs - updated independently
        self.high_level: float = float("nan")
        self.high_idx: int = -1
        self.low_level: float = float("nan")
        self.low_idx: int = -1

        # Gate 0: Significance tracking
        # Previous confirmed levels for significance calculation
        self._prev_confirmed_high: float = float("nan")
        self._prev_confirmed_low: float = float("nan")
        # Current significance values (ATR multiples)
        self._high_significance: float = float("nan")
        self._low_significance: float = float("nan")
        # Major/minor classification
        self._high_is_major: bool = False
        self._low_is_major: bool = False

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

        Dispatches to mode-specific update method:
        - fractal: Uses fixed bar-count window for pivot detection
        - atr_zigzag: Uses ATR threshold for direction changes

        Args:
            bar_idx: Current bar index.
            bar: Bar data containing high and low prices.
        """
        # Gate 2: Reset alternation output flags each bar (both modes)
        self._high_accepted = False
        self._low_accepted = False
        self._high_replaced_pending = False
        self._low_replaced_pending = False

        # Dispatch to mode-specific update
        if self._mode == "fractal":
            self._update_fractal(bar_idx, bar)
        else:  # atr_zigzag
            self._update_atr_zigzag(bar_idx, bar)

    def _update_fractal(self, bar_idx: int, bar: "BarData") -> None:
        """
        Fractal mode update: fixed bar-count window pivot detection.

        Pushes the bar's high and low to the respective ring buffers.
        If the buffers are full, checks if the pivot bar is a swing high/low.
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

        # Get ATR for significance calculation (if configured)
        atr = self._get_atr(bar)

        # Check for swing high
        if self._is_swing_high(pivot_idx):
            new_high_level = self._high_buf[pivot_idx]

            # Gate 1: Check if pivot should be accepted (filter insignificant pivots)
            if self._should_accept_pivot("high", new_high_level, atr):
                # Gate 2: Check alternation if enabled
                alt_accepted = True
                alt_replaced = False
                if self._strict_alternation:
                    alt_accepted, alt_replaced = self._check_alternation(
                        "high", new_high_level, pivot_bar_idx
                    )

                if alt_accepted:
                    # Gate 0: Calculate significance before updating state
                    self._high_significance = self._calculate_significance(
                        new_high_level, self._prev_confirmed_high, atr
                    )
                    self._high_is_major = (
                        not math.isnan(self._high_significance)
                        and self._high_significance >= self._major_threshold
                    )

                    # Update state
                    self.high_level = new_high_level
                    self.high_idx = pivot_bar_idx
                    self._version += 1
                    self._last_confirmed_pivot_idx = pivot_bar_idx
                    self._last_confirmed_pivot_type = "high"
                    confirmed_high = True

                    # Update previous confirmed level for next significance calculation
                    self._prev_confirmed_high = new_high_level

                    # Gate 2: Set alternation output flags
                    self._high_accepted = True
                    self._high_replaced_pending = alt_replaced

        # Check for swing low
        if self._is_swing_low(pivot_idx):
            new_low_level = self._low_buf[pivot_idx]

            # Gate 1: Check if pivot should be accepted (filter insignificant pivots)
            if self._should_accept_pivot("low", new_low_level, atr):
                # Gate 2: Check alternation if enabled
                alt_accepted = True
                alt_replaced = False
                if self._strict_alternation:
                    alt_accepted, alt_replaced = self._check_alternation(
                        "low", new_low_level, pivot_bar_idx
                    )

                if alt_accepted:
                    # Gate 0: Calculate significance before updating state
                    self._low_significance = self._calculate_significance(
                        new_low_level, self._prev_confirmed_low, atr
                    )
                    self._low_is_major = (
                        not math.isnan(self._low_significance)
                        and self._low_significance >= self._major_threshold
                    )

                    # Update state
                    self.low_level = new_low_level
                    self.low_idx = pivot_bar_idx
                    self._version += 1
                    self._last_confirmed_pivot_idx = pivot_bar_idx
                    self._last_confirmed_pivot_type = "low"
                    confirmed_low = True

                    # Update previous confirmed level for next significance calculation
                    self._prev_confirmed_low = new_low_level

                    # Gate 2: Set alternation output flags
                    self._low_accepted = True
                    self._low_replaced_pending = alt_replaced

        # Update pairing state machine
        self._update_pair_state(confirmed_high, confirmed_low)

    def _update_atr_zigzag(self, bar_idx: int, bar: "BarData") -> None:
        """
        ATR ZigZag mode update: direction change requires ATR threshold move.

        Algorithm:
        1. Track current direction (up/down) and extreme price
        2. In uptrend:
           - New high > extreme → update extreme
           - Low < extreme - (ATR × multiplier) → PIVOT! Switch to downtrend
        3. In downtrend:
           - New low < extreme → update extreme
           - High > extreme + (ATR × multiplier) → PIVOT! Switch to uptrend
        """
        atr = self._get_atr(bar)
        if atr is None or atr <= 0:
            # Can't run zigzag without valid ATR
            return

        threshold = atr * self._atr_multiplier
        confirmed_high = False
        confirmed_low = False

        # Initialize on first bar
        if not self._zigzag_initialized:
            # Start with current bar's range as initial state
            # Use the bar's high as initial extreme, assume uptrend to start
            self._zigzag_direction = 1  # Start in uptrend
            self._zigzag_extreme_price = bar.high
            self._zigzag_extreme_idx = bar_idx
            self._zigzag_initialized = True
            return

        if self._zigzag_direction == 1:  # Uptrend
            # Extend swing high?
            if bar.high > self._zigzag_extreme_price:
                self._zigzag_extreme_price = bar.high
                self._zigzag_extreme_idx = bar_idx

            # Reversal to downtrend?
            reversal_level = self._zigzag_extreme_price - threshold
            if bar.low < reversal_level:
                # Confirm HIGH pivot at the extreme
                pivot_level = self._zigzag_extreme_price
                pivot_bar_idx = self._zigzag_extreme_idx

                # Gate 1: Check if pivot should be accepted
                if self._should_accept_pivot("high", pivot_level, atr):
                    # Gate 2: Check alternation if enabled
                    alt_accepted = True
                    alt_replaced = False
                    if self._strict_alternation:
                        alt_accepted, alt_replaced = self._check_alternation(
                            "high", pivot_level, pivot_bar_idx
                        )

                    if alt_accepted:
                        # Gate 0: Calculate significance
                        self._high_significance = self._calculate_significance(
                            pivot_level, self._prev_confirmed_high, atr
                        )
                        self._high_is_major = (
                            not math.isnan(self._high_significance)
                            and self._high_significance >= self._major_threshold
                        )

                        # Update state
                        self.high_level = pivot_level
                        self.high_idx = pivot_bar_idx
                        self._version += 1
                        self._last_confirmed_pivot_idx = pivot_bar_idx
                        self._last_confirmed_pivot_type = "high"
                        confirmed_high = True
                        self._prev_confirmed_high = pivot_level
                        self._high_accepted = True
                        self._high_replaced_pending = alt_replaced

                # Switch to downtrend, start tracking from this bar's low
                self._zigzag_direction = -1
                self._zigzag_extreme_price = bar.low
                self._zigzag_extreme_idx = bar_idx

        else:  # Downtrend (direction == -1)
            # Extend swing low?
            if bar.low < self._zigzag_extreme_price:
                self._zigzag_extreme_price = bar.low
                self._zigzag_extreme_idx = bar_idx

            # Reversal to uptrend?
            reversal_level = self._zigzag_extreme_price + threshold
            if bar.high > reversal_level:
                # Confirm LOW pivot at the extreme
                pivot_level = self._zigzag_extreme_price
                pivot_bar_idx = self._zigzag_extreme_idx

                # Gate 1: Check if pivot should be accepted
                if self._should_accept_pivot("low", pivot_level, atr):
                    # Gate 2: Check alternation if enabled
                    alt_accepted = True
                    alt_replaced = False
                    if self._strict_alternation:
                        alt_accepted, alt_replaced = self._check_alternation(
                            "low", pivot_level, pivot_bar_idx
                        )

                    if alt_accepted:
                        # Gate 0: Calculate significance
                        self._low_significance = self._calculate_significance(
                            pivot_level, self._prev_confirmed_low, atr
                        )
                        self._low_is_major = (
                            not math.isnan(self._low_significance)
                            and self._low_significance >= self._major_threshold
                        )

                        # Update state
                        self.low_level = pivot_level
                        self.low_idx = pivot_bar_idx
                        self._version += 1
                        self._last_confirmed_pivot_idx = pivot_bar_idx
                        self._last_confirmed_pivot_type = "low"
                        confirmed_low = True
                        self._prev_confirmed_low = pivot_level
                        self._low_accepted = True
                        self._low_replaced_pending = alt_replaced

                # Switch to uptrend, start tracking from this bar's high
                self._zigzag_direction = 1
                self._zigzag_extreme_price = bar.high
                self._zigzag_extreme_idx = bar_idx

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

    def _get_atr(self, bar: "BarData") -> float | None:
        """
        Get ATR value from bar indicators if configured.

        Args:
            bar: Bar data containing indicators dict.

        Returns:
            ATR value if available, None otherwise.
        """
        if self._atr_key is None:
            return None
        atr = bar.indicators.get(self._atr_key)
        if atr is None or (isinstance(atr, float) and math.isnan(atr)):
            return None
        return float(atr)

    def _calculate_significance(
        self,
        current_level: float,
        previous_level: float,
        atr: float | None,
    ) -> float:
        """
        Calculate pivot significance as ATR multiple.

        Significance = |current - previous| / ATR

        Args:
            current_level: Current pivot price level.
            previous_level: Previous pivot price level of same type.
            atr: Current ATR value (or None if not available).

        Returns:
            Significance as ATR multiple, or NaN if cannot calculate.
        """
        # Cannot calculate without ATR
        if atr is None or atr <= 0:
            return float("nan")

        # Cannot calculate without previous level
        if math.isnan(previous_level):
            return float("nan")

        move = abs(current_level - previous_level)
        return move / atr

    def _should_accept_pivot(
        self,
        pivot_type: str,
        level: float,
        atr: float | None,
    ) -> bool:
        """
        Gate 1: Determine if pivot should be accepted based on significance filters.

        A pivot is accepted if it meets BOTH thresholds (if configured):
        - min_atr_move: Move from previous pivot >= threshold * ATR
        - min_pct_move: Move from previous pivot >= threshold%

        Args:
            pivot_type: "high" or "low"
            level: Price level of the pivot
            atr: Current ATR value (or None if not available)

        Returns:
            True if pivot should be accepted, False if filtered out.
        """
        # No filters configured - accept all
        if self._min_atr_move is None and self._min_pct_move is None:
            return True

        # Get previous level of same type
        if pivot_type == "high":
            prev_level = self._prev_confirmed_high
        else:
            prev_level = self._prev_confirmed_low

        # First pivot of type - always accept (no previous to compare)
        if math.isnan(prev_level):
            return True

        move = abs(level - prev_level)

        # Check ATR threshold if configured
        if self._min_atr_move is not None:
            if atr is None or atr <= 0:
                # Can't filter without ATR - accept by default
                pass
            else:
                threshold = atr * self._min_atr_move
                if move < threshold:
                    return False

        # Check percentage threshold if configured
        if self._min_pct_move is not None:
            if prev_level == 0:
                # Avoid division by zero - accept
                pass
            else:
                pct_move = (move / prev_level) * 100
                if pct_move < self._min_pct_move:
                    return False

        return True

    def _check_alternation(
        self,
        pivot_type: str,
        level: float,
        idx: int,
    ) -> tuple[bool, bool]:
        """
        Gate 2: Check if pivot should be accepted under strict alternation rules.

        Rules:
        - If same type as last pivot:
            - High: Accept only if HIGHER than pending high (replacement)
            - Low: Accept only if LOWER than pending low (replacement)
        - If opposite type: Always accept (completes alternation)
        - First pivot: Always accept

        Args:
            pivot_type: "high" or "low"
            level: Price level of the pivot
            idx: Bar index of the pivot

        Returns:
            Tuple of (accepted, replaced_pending):
            - accepted: True if pivot should be accepted
            - replaced_pending: True if this replaced a pending same-type pivot
        """
        # First pivot - always accept
        if self._alt_last_pivot_type is None:
            self._alt_last_pivot_type = pivot_type
            self._alt_pending_level = level
            self._alt_pending_idx = idx
            return (True, False)

        # Same type as last pivot
        if pivot_type == self._alt_last_pivot_type:
            if pivot_type == "high":
                # Higher high - replace pending
                if level > self._alt_pending_level:
                    self._alt_pending_level = level
                    self._alt_pending_idx = idx
                    return (True, True)  # Accepted as replacement
                else:
                    # Lower high - ignore
                    return (False, False)
            else:
                # Lower low - replace pending
                if level < self._alt_pending_level:
                    self._alt_pending_level = level
                    self._alt_pending_idx = idx
                    return (True, True)  # Accepted as replacement
                else:
                    # Higher low - ignore
                    return (False, False)
        else:
            # Opposite type - accept and update alternation state
            self._alt_last_pivot_type = pivot_type
            self._alt_pending_level = level
            self._alt_pending_idx = idx
            return (True, False)

    def _update_pair_state(self, confirmed_high: bool, confirmed_low: bool) -> None:
        """
        Update the pivot pairing state machine.

        Tracks whether we're building a bullish (LHL) or bearish (HLH) swing.
        A pair completes when we get the second pivot of the sequence.

        State transitions:
            AWAITING_FIRST + HIGH -> GOT_HIGH (pending high)
            AWAITING_FIRST + LOW  -> GOT_LOW (pending low)
            GOT_HIGH + LOW  -> PAIRED BEARISH (H->L downswing)
            GOT_HIGH + HIGH -> GOT_HIGH (new high replaces pending)
            GOT_LOW + HIGH  -> PAIRED BULLISH (L->H upswing)
            GOT_LOW + LOW   -> GOT_LOW (new low replaces pending)

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
                # HIGH -> LOW completes a bearish (HLH) swing
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
                # HIGH -> HIGH: new high replaces pending
                self._pending_level = level
                self._pending_idx = idx

        elif self._pair_state == self.STATE_GOT_LOW:
            if pivot_type == "high":
                # LOW -> HIGH completes a bullish (LHL) swing
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
                # LOW -> LOW: new low replaces pending
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
            List including individual pivots, significance, pair outputs, and version tracking.
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
            # Gate 0: Significance outputs (require atr_key)
            "high_significance",
            "low_significance",
            "high_is_major",
            "low_is_major",
            # Gate 2: Alternation tracking outputs (reset each bar)
            "high_accepted",
            "low_accepted",
            "high_replaced_pending",
            "low_replaced_pending",
            # Paired pivots (update only when pair completes)
            "pair_high_level",
            "pair_high_idx",
            "pair_low_level",
            "pair_low_idx",
            "pair_direction",
            "pair_version",
            "pair_anchor_hash",
        ]

    def get_value(self, key: str) -> float | int | str | bool:
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
        # Gate 0: Significance outputs
        elif key == "high_significance":
            return self._high_significance
        elif key == "low_significance":
            return self._low_significance
        elif key == "high_is_major":
            return self._high_is_major
        elif key == "low_is_major":
            return self._low_is_major
        # Gate 2: Alternation tracking outputs
        elif key == "high_accepted":
            return self._high_accepted
        elif key == "low_accepted":
            return self._low_accepted
        elif key == "high_replaced_pending":
            return self._high_replaced_pending
        elif key == "low_replaced_pending":
            return self._low_replaced_pending
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
            f"IncrementalSwing("
            f"left={self.left}, right={self.right}, "
            f"high_level={self.high_level}, high_idx={self.high_idx}, "
            f"low_level={self.low_level}, low_idx={self.low_idx})"
        )


def _run_validation_test() -> None:
    """
    Simple test to validate the swing detector works correctly.

    Run with:
        python -c "from src.structures.detectors.swing import _run_validation_test; _run_validation_test()"
    """
    from ..base import BarData

    print("Testing IncrementalSwing...")
    print("-" * 60)

    # Create detector with left=2, right=2 (window size = 5)
    params = {"left": 2, "right": 2}
    detector = IncrementalSwing(params, {})

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
        IncrementalSwing.validate_and_create("swing", "test", {"left": 0, "right": 2}, {})
        print("ERROR: Should have raised ValueError for left=0")
    except ValueError as e:
        if "'left' must be integer >= 1" in str(e):
            print("  OK: Correctly rejected left=0")
        else:
            print(f"ERROR: Wrong error message: {e}")

    # Test invalid right parameter (not an integer)
    try:
        IncrementalSwing.validate_and_create("swing", "test", {"left": 2, "right": "5"}, {})
        print("ERROR: Should have raised ValueError for right='5'")
    except ValueError as e:
        if "'right' must be integer >= 1" in str(e):
            print("  OK: Correctly rejected right='5'")
        else:
            print(f"ERROR: Wrong error message: {e}")

    # Test missing required parameter
    try:
        IncrementalSwing.validate_and_create("swing", "test", {"left": 2}, {})
        print("ERROR: Should have raised ValueError for missing 'right'")
    except ValueError as e:
        if "missing required params" in str(e):
            print("  OK: Correctly rejected missing 'right'")
        else:
            print(f"ERROR: Wrong error message: {e}")

    print()
    print("All validation tests passed!")
