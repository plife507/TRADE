"""
Incremental Market Structure detector (BOS/CHoCH).

Gate 5 implementation: ICT-style market structure detection.

Break of Structure (BOS): Continuation signal
- In uptrend: Price breaks above previous swing HIGH -> bullish continuation
- In downtrend: Price breaks below previous swing LOW -> bearish continuation

Change of Character (CHoCH): Reversal signal
- In uptrend: Price breaks below previous swing LOW -> potential bearish reversal
- In downtrend: Price breaks above previous swing HIGH -> potential bullish reversal

Requires a swing detector as a dependency to provide swing high/low levels.

Outputs:
- bias: int (1 = bullish, -1 = bearish, 0 = ranging) - current market structure bias
- bos_this_bar: bool (True if BOS occurred this bar)
- choch_this_bar: bool (True if CHoCH occurred this bar)
- bos_direction: str ("bullish", "bearish", "none") - direction of last BOS
- choch_direction: str ("bullish", "bearish", "none") - direction of last CHoCH
- last_bos_idx: int (bar index of last BOS event)
- last_bos_level: float (price level that was broken for BOS)
- last_choch_idx: int (bar index of last CHoCH event)
- last_choch_level: float (price level that was broken for CHoCH)
- break_level_high: float (current level to watch for bullish break)
- break_level_low: float (current level to watch for bearish break)
- version: int (increments on any structure event)

Example Play usage:
    structures:
      exec:
        - type: swing
          key: pivots
          params:
            left: 5
            right: 5

        - type: market_structure
          key: ms
          uses: pivots

See: docs/architecture/INCREMENTAL_STATE_ARCHITECTURE.md
See: docs/todos/PIVOT_FOUNDATION_GATES.md (Gate 5)
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from ..base import BaseIncrementalDetector
from ..registry import register_structure

if TYPE_CHECKING:
    from ..base import BarData


@register_structure("market_structure")
class IncrementalMarketStructure(BaseIncrementalDetector):
    """
    ICT Market Structure detector: BOS + CHoCH detection.

    Gate 5 Implementation.

    Depends on swing detector for pivot levels. Tracks structure breaks
    in real-time to identify continuation (BOS) and reversal (CHoCH) events.

    The detector maintains a bias (bullish/bearish/ranging) and watches
    for price breaking key swing levels:

    - Bullish bias: Watch for breaks above previous swing high (BOS)
                   or breaks below previous swing low (CHoCH -> flip to bearish)
    - Bearish bias: Watch for breaks below previous swing low (BOS)
                   or breaks above previous swing high (CHoCH -> flip to bullish)

    Events are signaled as booleans that reset each bar, allowing
    conditions to trigger on the exact bar of the break.
    """

    REQUIRED_PARAMS: list[str] = []
    OPTIONAL_PARAMS: dict[str, Any] = {
        "confirmation_close": False,  # Require candle close beyond level (vs wick)
    }
    DEPENDS_ON: list[str] = ["swing"]

    def __init__(self, params: dict[str, Any], deps: dict[str, BaseIncrementalDetector]):
        """
        Initialize the market structure detector.

        Args:
            params: Configuration params.
            deps: Dependencies dict. Must contain "swing" with a swing detector.
        """
        self.swing = deps["swing"]
        self._confirmation_close = params.get("confirmation_close", False)

        # Current market bias (integer to match trend detector convention)
        # 1 = bullish, -1 = bearish, 0 = ranging
        self.bias: int = 0

        # Break tracking - levels to watch
        self._break_level_high: float = float("nan")  # Level to break for bullish BOS (in uptrend) or CHoCH (in downtrend)
        self._break_level_low: float = float("nan")  # Level to break for bearish BOS (in downtrend) or CHoCH (in uptrend)

        # Track swing indices to detect new swings
        self._last_high_idx: int = -1
        self._last_low_idx: int = -1

        # Store previous swing levels for break detection
        self._prev_swing_high: float = float("nan")
        self._prev_swing_low: float = float("nan")
        self._prev_prev_swing_high: float = float("nan")
        self._prev_prev_swing_low: float = float("nan")

        # Track which swing indices we've already broken through
        # This prevents re-triggering BOS when the same level is re-used
        self._broken_high_idx: int = -1
        self._broken_low_idx: int = -1

        # Last BOS event
        self._last_bos_idx: int = -1
        self._last_bos_level: float = float("nan")
        self._bos_direction: str = "none"

        # Last CHoCH event
        self._last_choch_idx: int = -1
        self._last_choch_level: float = float("nan")
        self._choch_direction: str = "none"

        # Event flags (reset each bar)
        self._bos_this_bar: bool = False
        self._choch_this_bar: bool = False

        # Version tracking
        self._version: int = 0

    def update(self, bar_idx: int, bar: "BarData") -> None:
        """
        Process one bar and detect structure breaks.

        Args:
            bar_idx: Current bar index.
            bar: Bar data with OHLCV.
        """
        # Reset event flags each bar
        self._bos_this_bar = False
        self._choch_this_bar = False

        # Get current swing state via get_value() for consistency
        high_idx = self.swing.get_value("high_idx")
        low_idx = self.swing.get_value("low_idx")
        high_level = self.swing.get_value("high_level")
        low_level = self.swing.get_value("low_level")

        # Check for new swing pivots
        high_changed = high_idx != self._last_high_idx and high_idx >= 0
        low_changed = low_idx != self._last_low_idx and low_idx >= 0

        # Update break levels when new swings are detected
        if high_changed:
            self._prev_prev_swing_high = self._prev_swing_high
            self._prev_swing_high = high_level
            self._last_high_idx = high_idx
            self._update_break_levels()

        if low_changed:
            self._prev_prev_swing_low = self._prev_swing_low
            self._prev_swing_low = low_level
            self._last_low_idx = low_idx
            self._update_break_levels()

        # Check for structure breaks
        self._check_breaks(bar_idx, bar)

    def _update_break_levels(self) -> None:
        """Update the break levels based on current swing structure.

        Only updates if the swing is NEWER than the one we already broke.
        This prevents re-triggering BOS on the same level.
        """
        # High to break: only update if this is a new swing we haven't broken
        if not math.isnan(self._prev_swing_high):
            # Only set break level if this swing is newer than the one we broke
            if self._last_high_idx > self._broken_high_idx:
                self._break_level_high = self._prev_swing_high

        # Low to break: only update if this is a new swing we haven't broken
        if not math.isnan(self._prev_swing_low):
            # Only set break level if this swing is newer than the one we broke
            if self._last_low_idx > self._broken_low_idx:
                self._break_level_low = self._prev_swing_low

    def _check_breaks(self, bar_idx: int, bar: "BarData") -> None:
        """
        Check for BOS and CHoCH breaks.

        Args:
            bar_idx: Current bar index.
            bar: Bar data.
        """
        # Get price levels to check
        check_high = bar.close if self._confirmation_close else bar.high
        check_low = bar.close if self._confirmation_close else bar.low

        if self.bias == 1:
            self._check_bullish_bias_breaks(bar_idx, check_high, check_low)
        elif self.bias == -1:
            self._check_bearish_bias_breaks(bar_idx, check_high, check_low)
        else:  # ranging
            self._check_ranging_breaks(bar_idx, check_high, check_low)

    def _check_bullish_bias_breaks(self, bar_idx: int, check_high: float, check_low: float) -> None:
        """
        Check for breaks in bullish bias.

        In bullish bias:
        - Break below swing low = CHoCH (potential reversal to bearish) - checked first, takes priority
        - Break above swing high = BOS (bullish continuation)
        """
        # Check for CHoCH (reversal) - takes priority over BOS
        if not math.isnan(self._break_level_low) and check_low < self._break_level_low:
            self._choch_this_bar = True
            self._last_choch_idx = bar_idx
            self._last_choch_level = self._break_level_low
            self._choch_direction = "bearish"
            self.bias = -1
            self._version += 1
            # Mark this swing as broken and clear break level
            self._broken_low_idx = self._last_low_idx
            self._break_level_low = float("nan")
            return  # CHoCH supersedes BOS on same bar

        # Check for bullish BOS (continuation)
        if not math.isnan(self._break_level_high) and check_high > self._break_level_high:
            self._bos_this_bar = True
            self._last_bos_idx = bar_idx
            self._last_bos_level = self._break_level_high
            self._bos_direction = "bullish"
            self._version += 1
            # Mark this swing as broken to prevent re-triggering
            self._broken_high_idx = self._last_high_idx
            # Clear break level - require NEW swing to form before next BOS
            self._break_level_high = float("nan")

    def _check_bearish_bias_breaks(self, bar_idx: int, check_high: float, check_low: float) -> None:
        """
        Check for breaks in bearish bias.

        In bearish bias:
        - Break above swing high = CHoCH (potential reversal to bullish) - checked first, takes priority
        - Break below swing low = BOS (bearish continuation)
        """
        # Check for CHoCH (reversal) - takes priority over BOS
        if not math.isnan(self._break_level_high) and check_high > self._break_level_high:
            self._choch_this_bar = True
            self._last_choch_idx = bar_idx
            self._last_choch_level = self._break_level_high
            self._choch_direction = "bullish"
            self.bias = 1
            self._version += 1
            # Mark this swing as broken and clear break level
            self._broken_high_idx = self._last_high_idx
            self._break_level_high = float("nan")
            return  # CHoCH supersedes BOS on same bar

        # Check for bearish BOS (continuation)
        if not math.isnan(self._break_level_low) and check_low < self._break_level_low:
            self._bos_this_bar = True
            self._last_bos_idx = bar_idx
            self._last_bos_level = self._break_level_low
            self._bos_direction = "bearish"
            self._version += 1
            # Mark this swing as broken to prevent re-triggering
            self._broken_low_idx = self._last_low_idx
            # Clear break level - require NEW swing to form before next BOS
            self._break_level_low = float("nan")

    def _check_ranging_breaks(self, bar_idx: int, check_high: float, check_low: float) -> None:
        """
        Check for breaks when bias is ranging.

        In ranging:
        - First significant break establishes initial bias
        - Break above swing high = establish bullish bias
        - Break below swing low = establish bearish bias
        """
        # Check for bullish break to establish bias
        if not math.isnan(self._break_level_high) and check_high > self._break_level_high:
            self._bos_this_bar = True  # First break is also a BOS
            self._last_bos_idx = bar_idx
            self._last_bos_level = self._break_level_high
            self._bos_direction = "bullish"
            self.bias = 1
            self._version += 1
            # Mark this swing as broken to prevent re-triggering
            self._broken_high_idx = self._last_high_idx
            # Clear break level - require NEW swing to form before next BOS
            self._break_level_high = float("nan")
            return

        # Check for bearish break to establish bias
        if not math.isnan(self._break_level_low) and check_low < self._break_level_low:
            self._bos_this_bar = True  # First break is also a BOS
            self._last_bos_idx = bar_idx
            self._last_bos_level = self._break_level_low
            self._bos_direction = "bearish"
            self.bias = -1
            self._version += 1
            # Mark this swing as broken to prevent re-triggering
            self._broken_low_idx = self._last_low_idx
            # Clear break level - require NEW swing to form before next BOS
            self._break_level_low = float("nan")

    def get_output_keys(self) -> list[str]:
        """
        List of readable output keys.

        Returns:
            List of output key names.
        """
        return [
            "bias",
            "bos_this_bar",
            "choch_this_bar",
            "bos_direction",
            "choch_direction",
            "last_bos_idx",
            "last_bos_level",
            "last_choch_idx",
            "last_choch_level",
            "break_level_high",
            "break_level_low",
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
        if key == "bias":
            return self.bias
        elif key == "bos_this_bar":
            return self._bos_this_bar
        elif key == "choch_this_bar":
            return self._choch_this_bar
        elif key == "bos_direction":
            return self._bos_direction
        elif key == "choch_direction":
            return self._choch_direction
        elif key == "last_bos_idx":
            return self._last_bos_idx
        elif key == "last_bos_level":
            return self._last_bos_level
        elif key == "last_choch_idx":
            return self._last_choch_idx
        elif key == "last_choch_level":
            return self._last_choch_level
        elif key == "break_level_high":
            return self._break_level_high
        elif key == "break_level_low":
            return self._break_level_low
        elif key == "version":
            return self._version
        else:
            raise KeyError(key)
