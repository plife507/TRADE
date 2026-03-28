"""
Incremental premium/discount zone detector.

Divides the current swing pair range into premium (upper 50%) and discount
(lower 50%) zones, with equilibrium at the midpoint. This is a core ICT
concept: institutions buy at discount and sell at premium.

Computation:
    Given swing pair (pair_high_level, pair_low_level) from the swing dependency:
    - equilibrium = (high + low) / 2
    - premium_level = low + 0.75 * (high - low)  (75th percentile)
    - discount_level = low + 0.25 * (high - low)  (25th percentile)
    - zone classification based on close position relative to these levels
    - depth_pct = (close - low) / (high - low), clamped to [0, 1]

Zone classification:
    - "premium": close >= premium_level (upper 25%)
    - "discount": close <= discount_level (lower 25%)
    - "equilibrium": between discount and premium (middle 50%)
    - "none": swing pair not yet formed (NaN levels)

Output keys:
    equilibrium: Midpoint of swing pair range (NaN if no pair)
    premium_level: 75th percentile of range (NaN if no pair)
    discount_level: 25th percentile of range (NaN if no pair)
    zone: Current zone classification ("premium", "discount", "equilibrium", "none")
    depth_pct: Position within range, 0.0 (at low) to 1.0 (at high) (NaN if no pair)
    version: Monotonic counter, increments on zone change

Example Play usage:
    structures:
      exec:
        - type: swing
          key: swing
          params: {left: 5, right: 5}
        - type: trend
          key: trend
          uses: swing
        - type: premium_discount
          key: pd
          uses: swing

    actions:
      entry_long:
        all:
          - ["pd.zone", "==", "discount"]
          - ["trend.direction", "==", 1]

See: docs/MARKET_STRUCTURE_FEATURES.md
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from ..base import BaseIncrementalDetector
from ..registry import register_structure

if TYPE_CHECKING:
    from ..base import BarData


@register_structure("premium_discount")
class IncrementalPremiumDiscount(BaseIncrementalDetector):
    """
    Premium/discount zone detector.

    Reads swing pair high/low from the swing dependency and classifies
    the current price position within the range. Zero parameters beyond
    the swing dependency.

    Parameters:
        (none — all computation derives from the swing pair)
    """

    REQUIRED_PARAMS: list[str] = []
    OPTIONAL_PARAMS: dict[str, Any] = {}
    DEPENDS_ON: list[str] = ["swing"]

    def __init__(
        self,
        params: dict[str, Any],
        deps: dict[str, BaseIncrementalDetector],
    ) -> None:
        self._swing = deps["swing"]

        # Computed levels (updated each bar)
        self._equilibrium: float = float("nan")
        self._premium_level: float = float("nan")
        self._discount_level: float = float("nan")
        self._zone: str = "none"
        self._depth_pct: float = float("nan")

        # Track previous zone for version bumps
        self._prev_zone: str = "none"
        self._version: int = 0

    def update(self, bar_idx: int, bar: "BarData") -> None:
        """
        Compute premium/discount levels from current swing pair.

        Args:
            bar_idx: Current bar index.
            bar: Bar data (only close price used).
        """
        pair_high = self._swing.get_value("pair_high_level")
        pair_low = self._swing.get_value("pair_low_level")

        # Check if swing pair is valid
        if (
            isinstance(pair_high, float) and math.isnan(pair_high)
            or isinstance(pair_low, float) and math.isnan(pair_low)
        ):
            self._equilibrium = float("nan")
            self._premium_level = float("nan")
            self._discount_level = float("nan")
            self._depth_pct = float("nan")
            new_zone = "none"
        else:
            high = float(pair_high)
            low = float(pair_low)
            span = high - low

            if span <= 0:
                # Degenerate pair (high == low)
                self._equilibrium = high
                self._premium_level = high
                self._discount_level = low
                self._depth_pct = 0.5
                new_zone = "equilibrium"
            else:
                self._equilibrium = low + 0.5 * span
                self._premium_level = low + 0.75 * span
                self._discount_level = low + 0.25 * span

                # Classify zone
                close = bar.close
                if close >= self._premium_level:
                    new_zone = "premium"
                elif close <= self._discount_level:
                    new_zone = "discount"
                else:
                    new_zone = "equilibrium"

                # Depth: 0.0 at low, 1.0 at high, clamped
                raw_depth = (close - low) / span
                self._depth_pct = max(0.0, min(1.0, raw_depth))

        # Version bump on zone change
        if new_zone != self._prev_zone:
            self._version += 1
            self._prev_zone = new_zone
        self._zone = new_zone

    def reset(self) -> None:
        """Reset all mutable state."""
        self._equilibrium = float("nan")
        self._premium_level = float("nan")
        self._discount_level = float("nan")
        self._zone = "none"
        self._depth_pct = float("nan")
        self._prev_zone = "none"
        self._version = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize state for crash recovery."""
        return {
            "equilibrium": self._equilibrium,
            "premium_level": self._premium_level,
            "discount_level": self._discount_level,
            "zone": self._zone,
            "depth_pct": self._depth_pct,
            "prev_zone": self._prev_zone,
            "version": self._version,
        }

    def get_output_keys(self) -> list[str]:
        return [
            "equilibrium",
            "premium_level",
            "discount_level",
            "zone",
            "depth_pct",
            "version",
        ]

    def get_value(self, key: str) -> float | int | str:
        if key == "equilibrium":
            return self._equilibrium
        elif key == "premium_level":
            return self._premium_level
        elif key == "discount_level":
            return self._discount_level
        elif key == "zone":
            return self._zone
        elif key == "depth_pct":
            return self._depth_pct
        elif key == "version":
            return self._version
        else:
            raise KeyError(key)

    def __repr__(self) -> str:
        return f"IncrementalPremiumDiscount(zone={self._zone!r}, depth={self._depth_pct:.2f})"
