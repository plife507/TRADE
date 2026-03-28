"""
Incremental Fair Value Gap (FVG) detector.

Detects 3-candle imbalance patterns where a strong move creates a gap
between candle 1's range and candle 3's range. Price tends to return
to fill these gaps approximately 70% of the time.

Bullish FVG: candle_3.low > candle_1.high (gap above c1)
Bearish FVG: candle_3.high < candle_1.low (gap below c1)

State Management:
    Active FVGs are tracked in a slot list (newest first).
    Each bar updates mitigation state:
    - Bullish: price dipping into gap fills it
    - Bearish: price rising into gap fills it
    - fill_pct >= 0.5 -> "mitigated"
    - close beyond opposite boundary -> "invalidated"

Output keys:
    new_this_bar: True if a new FVG was detected this bar
    new_direction: Direction of newest FVG (1=bull, -1=bear, 0=none)
    new_upper: Upper boundary of newest FVG (NaN if none)
    new_lower: Lower boundary of newest FVG (NaN if none)
    nearest_bull_upper: Upper boundary of nearest active bullish FVG
    nearest_bull_lower: Lower boundary of nearest active bullish FVG
    nearest_bear_upper: Upper boundary of nearest active bearish FVG
    nearest_bear_lower: Lower boundary of nearest active bearish FVG
    active_bull_count: Number of active bullish FVGs
    active_bear_count: Number of active bearish FVGs
    any_mitigated_this_bar: True if any FVG was mitigated this bar
    version: Monotonic counter, increments on new FVG creation

Example Play usage:
    features:
      atr_14:
        indicator: atr
        params: {length: 14}

    structures:
      exec:
        - type: fair_value_gap
          key: fvg
          params:
            atr_key: atr_14
            min_gap_atr: 0.5
            max_active: 5

    actions:
      entry_long:
        all:
          - ["fvg.new_this_bar", "==", 1]
          - ["fvg.new_direction", "==", 1]
"""

from __future__ import annotations

import math
from collections import deque
from typing import TYPE_CHECKING, Any

from ..base import BaseIncrementalDetector
from ..registry import register_structure

if TYPE_CHECKING:
    from ..base import BarData


@register_structure("fair_value_gap")
class IncrementalFVG(BaseIncrementalDetector):
    """
    Fair Value Gap detector with slot-based tracking.

    Detects 3-candle imbalance patterns and tracks their mitigation.
    No dependencies on other structure detectors -- operates directly
    on OHLCV data with optional ATR filtering.

    Parameters:
        atr_key: Indicator key for ATR values (default: "atr")
        min_gap_atr: Minimum gap size as ATR multiple; 0 = no filter (default: 0.0)
        max_active: Maximum tracked active FVG slots (default: 5)

    FVG Slot Fields:
        direction: 1 (bullish) or -1 (bearish)
        upper: Upper boundary of the gap
        lower: Lower boundary of the gap
        anchor_idx: Bar index where FVG was detected
        state: "active", "mitigated", or "invalidated"
        fill_pct: How much of the gap has been filled (0.0 to 1.0)

    Mitigation Logic:
        Bullish FVG: price dips into gap from above
            - fill_pct = (upper - bar.low) / (upper - lower)
            - mitigated when fill_pct >= 0.5
            - invalidated when bar.close < lower
        Bearish FVG: price rises into gap from below
            - fill_pct = (bar.high - lower) / (upper - lower)
            - mitigated when fill_pct >= 0.5
            - invalidated when bar.close > upper
    """

    REQUIRED_PARAMS: list[str] = []
    OPTIONAL_PARAMS: dict[str, Any] = {
        "atr_key": "atr",
        "min_gap_atr": 0.0,
        "max_active": 5,
    }
    DEPENDS_ON: list[str] = []

    @classmethod
    def _validate_params(
        cls, struct_type: str, key: str, params: dict[str, Any]
    ) -> None:
        """Validate FVG-specific parameters."""
        min_gap_atr = params.get("min_gap_atr", 0.0)
        if not isinstance(min_gap_atr, (int, float)) or min_gap_atr < 0:
            raise ValueError(
                f"Structure '{key}' (type: {struct_type}): 'min_gap_atr' must be >= 0, got {min_gap_atr!r}\n"
                "\n"
                "Fix in Play:\n"
                f"  - type: {struct_type}\n"
                f"    key: {key}\n"
                "    params:\n"
                "      min_gap_atr: 0.5  # Must be >= 0\n"
                "\n"
                "Hint:\n"
                "  - 0.0: No ATR filter (all gaps detected)\n"
                "  - 0.5: Only gaps >= 0.5 ATR width\n"
                "  - 1.0: Only significant gaps >= 1 ATR"
            )

        max_active = params.get("max_active", 5)
        if not isinstance(max_active, int) or max_active < 1:
            raise ValueError(
                f"Structure '{key}' (type: {struct_type}): 'max_active' must be integer >= 1, got {max_active!r}\n"
                "\n"
                "Fix: max_active: 5"
            )

    def __init__(
        self,
        params: dict[str, Any],
        deps: dict[str, BaseIncrementalDetector] | None,
    ) -> None:
        """
        Initialize FVG detector.

        Args:
            params: Parameters dict with optional atr_key, min_gap_atr, max_active.
            deps: Dependencies dict (unused -- FVG has no deps).
        """
        self.atr_key: str = params.get("atr_key", "atr")
        self.min_gap_atr: float = float(params.get("min_gap_atr", 0.0))
        self.max_active: int = int(params.get("max_active", 5))

        # Candle buffer: stores (high, low) for last 3 bars
        self._candle_buf: deque[tuple[float, float]] = deque(maxlen=3)

        # Active FVG slots: list of dicts, newest first
        self._fvgs: list[dict[str, Any]] = []

        # Per-bar flags (reset each update)
        self._new_this_bar: bool = False
        self._new_direction: int = 0
        self._new_upper: float = float("nan")
        self._new_lower: float = float("nan")
        self._any_mitigated_this_bar: bool = False

        # Nearest accessors (recomputed each bar)
        self._nearest_bull_upper: float = float("nan")
        self._nearest_bull_lower: float = float("nan")
        self._nearest_bear_upper: float = float("nan")
        self._nearest_bear_lower: float = float("nan")

        # Aggregates
        self._active_bull_count: int = 0
        self._active_bear_count: int = 0

        # Version counter
        self._version: int = 0

    def update(self, bar_idx: int, bar: "BarData") -> None:
        """
        Process one bar and update FVG state.

        Steps:
        1. Reset per-bar flags
        2. Push current bar to candle buffer
        3. Check for new FVG (3-candle pattern)
        4. Update mitigation state for all active FVGs
        5. Prune beyond max_active
        6. Recompute nearest and aggregates

        Args:
            bar_idx: Current bar index.
            bar: Bar data including OHLCV and indicators.
        """
        # Step 1: Reset per-bar flags
        self._new_this_bar = False
        self._new_direction = 0
        self._new_upper = float("nan")
        self._new_lower = float("nan")
        self._any_mitigated_this_bar = False

        # Step 2: Push current bar to candle buffer
        self._candle_buf.append((bar.high, bar.low))

        # Step 3: Check for new FVG if we have 3 candles
        if len(self._candle_buf) >= 3:
            c1_high, c1_low = self._candle_buf[-3]
            c3_high, c3_low = self._candle_buf[-1]

            # Get ATR for filtering
            atr_val = float("nan")
            if self.min_gap_atr > 0:
                atr_val = bar.indicators.get(self.atr_key, float("nan"))

            # Check bullish FVG: c3_low > c1_high (gap above c1)
            if c3_low > c1_high:
                gap_size = c3_low - c1_high
                if self._passes_atr_filter(gap_size, atr_val):
                    self._create_fvg(
                        direction=1,
                        upper=c3_low,
                        lower=c1_high,
                        anchor_idx=bar_idx,
                    )

            # Check bearish FVG: c3_high < c1_low (gap below c1)
            elif c3_high < c1_low:
                gap_size = c1_low - c3_high
                if self._passes_atr_filter(gap_size, atr_val):
                    self._create_fvg(
                        direction=-1,
                        upper=c1_low,
                        lower=c3_high,
                        anchor_idx=bar_idx,
                    )

        # Step 4: Update mitigation state for all active FVGs
        self._update_mitigation(bar)

        # Step 5: Prune inactive FVGs beyond max_active total
        self._prune_fvgs()

        # Step 6: Recompute nearest and aggregates
        self._recompute_aggregates(bar)

    def _passes_atr_filter(self, gap_size: float, atr_val: float) -> bool:
        """Check if gap passes the ATR minimum filter."""
        if self.min_gap_atr <= 0:
            return True
        if math.isnan(atr_val) or atr_val <= 0:
            return False
        return gap_size >= self.min_gap_atr * atr_val

    def _create_fvg(
        self, direction: int, upper: float, lower: float, anchor_idx: int
    ) -> None:
        """Create a new FVG slot and prepend to list."""
        fvg: dict[str, Any] = {
            "direction": direction,
            "upper": upper,
            "lower": lower,
            "anchor_idx": anchor_idx,
            "state": "active",
            "fill_pct": 0.0,
        }
        # Prepend (newest first)
        self._fvgs.insert(0, fvg)

        # Set per-bar flags
        self._new_this_bar = True
        self._new_direction = direction
        self._new_upper = upper
        self._new_lower = lower

        # Increment version
        self._version += 1

    def _update_mitigation(self, bar: "BarData") -> None:
        """Update mitigation state for all active FVGs."""
        for fvg in self._fvgs:
            if fvg["state"] != "active":
                continue

            upper = fvg["upper"]
            lower = fvg["lower"]
            gap_range = upper - lower

            if gap_range <= 0:
                continue

            if fvg["direction"] == 1:
                # Bullish FVG: price dips into gap from above
                if bar.low <= upper:
                    fill = (upper - bar.low) / gap_range
                    fill = min(fill, 1.0)
                    fvg["fill_pct"] = max(fvg["fill_pct"], fill)

                    if fvg["fill_pct"] >= 0.5:
                        fvg["state"] = "mitigated"
                        self._any_mitigated_this_bar = True

                if bar.close < lower:
                    fvg["state"] = "invalidated"

            else:
                # Bearish FVG: price rises into gap from below
                if bar.high >= lower:
                    fill = (bar.high - lower) / gap_range
                    fill = min(fill, 1.0)
                    fvg["fill_pct"] = max(fvg["fill_pct"], fill)

                    if fvg["fill_pct"] >= 0.5:
                        fvg["state"] = "mitigated"
                        self._any_mitigated_this_bar = True

                if bar.close > upper:
                    fvg["state"] = "invalidated"

    def _prune_fvgs(self) -> None:
        """Remove invalidated/mitigated FVGs beyond max_active total."""
        # Keep all active first, then keep mitigated/invalidated up to limit
        if len(self._fvgs) > self.max_active:
            # Keep newest max_active entries; drop from the end (oldest)
            self._fvgs = self._fvgs[: self.max_active]

    def _recompute_aggregates(self, bar: "BarData") -> None:
        """Recompute nearest bull/bear and aggregate counts."""
        self._active_bull_count = 0
        self._active_bear_count = 0
        self._nearest_bull_upper = float("nan")
        self._nearest_bull_lower = float("nan")
        self._nearest_bear_upper = float("nan")
        self._nearest_bear_lower = float("nan")

        nearest_bull_dist = float("inf")
        nearest_bear_dist = float("inf")
        price = bar.close

        for fvg in self._fvgs:
            if fvg["state"] != "active":
                continue

            if fvg["direction"] == 1:
                self._active_bull_count += 1
                # Distance from price to gap midpoint
                mid = (fvg["upper"] + fvg["lower"]) / 2.0
                dist = abs(price - mid)
                if dist < nearest_bull_dist:
                    nearest_bull_dist = dist
                    self._nearest_bull_upper = fvg["upper"]
                    self._nearest_bull_lower = fvg["lower"]
            else:
                self._active_bear_count += 1
                mid = (fvg["upper"] + fvg["lower"]) / 2.0
                dist = abs(price - mid)
                if dist < nearest_bear_dist:
                    nearest_bear_dist = dist
                    self._nearest_bear_upper = fvg["upper"]
                    self._nearest_bear_lower = fvg["lower"]

    def reset(self) -> None:
        """Reset all mutable state to initial values."""
        self._candle_buf.clear()
        self._fvgs.clear()
        self._new_this_bar = False
        self._new_direction = 0
        self._new_upper = float("nan")
        self._new_lower = float("nan")
        self._any_mitigated_this_bar = False
        self._nearest_bull_upper = float("nan")
        self._nearest_bull_lower = float("nan")
        self._nearest_bear_upper = float("nan")
        self._nearest_bear_lower = float("nan")
        self._active_bull_count = 0
        self._active_bear_count = 0
        self._version = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize state for crash recovery."""
        return {
            "candle_buf": list(self._candle_buf),
            "fvgs": [dict(f) for f in self._fvgs],
            "version": self._version,
        }

    def get_output_keys(self) -> list[str]:
        """Return list of output keys."""
        return [
            "new_this_bar",
            "new_direction",
            "new_upper",
            "new_lower",
            "nearest_bull_upper",
            "nearest_bull_lower",
            "nearest_bear_upper",
            "nearest_bear_lower",
            "active_bull_count",
            "active_bear_count",
            "any_mitigated_this_bar",
            "version",
        ]

    def get_value(self, key: str) -> float | int | str | bool:
        """
        Get output value by key.

        Args:
            key: Output key name.

        Returns:
            The output value.

        Raises:
            KeyError: If key is not valid.
        """
        if key == "new_this_bar":
            return self._new_this_bar
        elif key == "new_direction":
            return self._new_direction
        elif key == "new_upper":
            return self._new_upper
        elif key == "new_lower":
            return self._new_lower
        elif key == "nearest_bull_upper":
            return self._nearest_bull_upper
        elif key == "nearest_bull_lower":
            return self._nearest_bull_lower
        elif key == "nearest_bear_upper":
            return self._nearest_bear_upper
        elif key == "nearest_bear_lower":
            return self._nearest_bear_lower
        elif key == "active_bull_count":
            return self._active_bull_count
        elif key == "active_bear_count":
            return self._active_bear_count
        elif key == "any_mitigated_this_bar":
            return self._any_mitigated_this_bar
        elif key == "version":
            return self._version
        else:
            raise KeyError(key)

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        return (
            f"IncrementalFVG("
            f"atr_key={self.atr_key!r}, "
            f"min_gap_atr={self.min_gap_atr}, "
            f"max_active={self.max_active}, "
            f"fvgs={len(self._fvgs)})"
        )
