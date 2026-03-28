"""
Incremental breaker block detector.

A breaker block forms when an Order Block is invalidated during a
Change of Character (CHoCH) event. The invalidated OB "flips polarity":
a failed bullish OB becomes a bearish breaker block (resistance zone),
and a failed bearish OB becomes a bullish breaker block (support zone).

Detection Logic:
    1. On each bar, check if both conditions are met:
       a) OB dependency reports an invalidation (any_invalidated_this_bar)
       b) Market structure dependency reports a CHoCH (choch_this_bar)
    2. If both fire, create a breaker block from the invalidated OB's zone
       with flipped direction (bullish OB → bearish breaker, vice versa)

Mitigation Logic:
    Bullish breaker (from invalidated bearish OB): zone acts as support
        - Touched when bar.low <= breaker.upper
        - Invalidated when bar.close < breaker.lower
    Bearish breaker (from invalidated bullish OB): zone acts as resistance
        - Touched when bar.high >= breaker.lower
        - Invalidated when bar.close > breaker.upper

Output keys:
    new_this_bar: True if a new breaker block was detected this bar
    new_direction: Direction of newest breaker (1=bullish support, -1=bearish resistance)
    new_upper: Upper boundary of newest breaker (NaN if none)
    new_lower: Lower boundary of newest breaker (NaN if none)
    nearest_bull_upper: Upper of nearest active bullish breaker
    nearest_bull_lower: Lower of nearest active bullish breaker
    nearest_bear_upper: Upper of nearest active bearish breaker
    nearest_bear_lower: Lower of nearest active bearish breaker
    active_bull_count: Number of active bullish breakers
    active_bear_count: Number of active bearish breakers
    any_mitigated_this_bar: True if any breaker was touched this bar
    version: Monotonic counter, increments on new breaker creation

Example Play usage:
    structures:
      exec:
        - type: swing
          key: swing
          params: {left: 5, right: 5}
        - type: order_block
          key: ob
          uses: swing
          params: {atr_key: atr_14}
        - type: market_structure
          key: ms
          uses: swing
        - type: breaker_block
          key: brk
          uses: ob
          params:
            ms_key: ms

    actions:
      entry_long:
        all:
          - ["brk.new_this_bar", "==", 1]
          - ["brk.new_direction", "==", 1]

See: docs/MARKET_STRUCTURE_FEATURES.md
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from ..base import BaseIncrementalDetector
from ..registry import register_structure

if TYPE_CHECKING:
    from ..base import BarData


@register_structure("breaker_block")
class IncrementalBreakerBlock(BaseIncrementalDetector):
    """
    Breaker block detector — failed OBs that flip polarity on CHoCH.

    Depends on order_block for invalidation events and market_structure
    for CHoCH events. The market_structure dependency is passed via the
    ms_key parameter (key name in the structure config), resolved at
    runtime through OPTIONAL_DEPS.

    Parameters:
        max_active: Maximum tracked active breaker slots (default: 5)
    """

    REQUIRED_PARAMS: list[str] = []
    OPTIONAL_PARAMS: dict[str, Any] = {
        "max_active": 5,
    }
    DEPENDS_ON: list[str] = ["order_block"]
    OPTIONAL_DEPS: list[str] = ["market_structure"]

    @classmethod
    def _validate_params(
        cls, struct_type: str, key: str, params: dict[str, Any]
    ) -> None:
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
        deps: dict[str, BaseIncrementalDetector],
    ) -> None:
        self._ob = deps["order_block"]
        self._ms: BaseIncrementalDetector | None = deps.get("market_structure")
        self._max_active: int = int(params.get("max_active", 5))

        # Active breaker slots: list of dicts, newest first
        self._breakers: list[dict[str, Any]] = []

        # Per-bar flags
        self._new_this_bar: bool = False
        self._new_direction: int = 0
        self._new_upper: float = float("nan")
        self._new_lower: float = float("nan")
        self._any_mitigated_this_bar: bool = False

        # Nearest accessors
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
        Process one bar and update breaker block state.

        1. Reset per-bar flags
        2. Check for concurrent OB invalidation + CHoCH
        3. If both: create breaker from invalidated OB with flipped direction
        4. Update mitigation/invalidation on existing breakers
        5. Prune beyond max_active
        6. Recompute nearest and aggregates
        """
        # 1. Reset per-bar flags
        self._new_this_bar = False
        self._new_direction = 0
        self._new_upper = float("nan")
        self._new_lower = float("nan")
        self._any_mitigated_this_bar = False

        # 2. Check for concurrent OB invalidation + CHoCH
        ob_invalidated = bool(self._ob.get_value("any_invalidated_this_bar"))
        choch_fired = self._ms is not None and bool(self._ms.get_value("choch_this_bar"))

        if ob_invalidated and choch_fired:
            inv_dir = int(self._ob.get_value("last_invalidated_direction"))
            inv_upper = self._ob.get_value("last_invalidated_upper")
            inv_lower = self._ob.get_value("last_invalidated_lower")

            if inv_dir != 0 and not (isinstance(inv_upper, float) and math.isnan(inv_upper)):
                # Flip polarity: bullish OB (1) → bearish breaker (-1), and vice versa
                breaker_dir = -inv_dir
                self._create_breaker(breaker_dir, float(inv_upper), float(inv_lower), bar_idx)

        # 3. Update mitigation/invalidation on existing breakers
        self._update_mitigation(bar_idx, bar)

        # 4. Prune beyond max_active
        if len(self._breakers) > self._max_active:
            self._breakers = self._breakers[: self._max_active]

        # 5. Recompute nearest and aggregates
        self._recompute_aggregates(bar)

    def _create_breaker(
        self, direction: int, upper: float, lower: float, anchor_idx: int
    ) -> None:
        """Create a new breaker block slot."""
        if upper <= lower:
            return

        brk: dict[str, Any] = {
            "direction": direction,
            "upper": upper,
            "lower": lower,
            "anchor_idx": anchor_idx,
            "state": "active",
            "touch_count": 0,
        }
        self._breakers.insert(0, brk)

        self._new_this_bar = True
        self._new_direction = direction
        self._new_upper = upper
        self._new_lower = lower
        self._version += 1

    def _update_mitigation(self, bar_idx: int, bar: "BarData") -> None:
        """Update mitigation/invalidation for all active breakers."""
        for brk in self._breakers:
            if brk["state"] != "active":
                continue

            # Skip on creation bar
            if brk["anchor_idx"] == bar_idx:
                continue

            upper = brk["upper"]
            lower = brk["lower"]

            if brk["direction"] == 1:
                # Bullish breaker (support): invalidation takes priority
                if bar.close < lower:
                    brk["state"] = "invalidated"
                elif bar.low <= upper:
                    brk["touch_count"] += 1
                    brk["state"] = "mitigated"
                    self._any_mitigated_this_bar = True
            else:
                # Bearish breaker (resistance): invalidation takes priority
                if bar.close > upper:
                    brk["state"] = "invalidated"
                elif bar.high >= lower:
                    brk["touch_count"] += 1
                    brk["state"] = "mitigated"
                    self._any_mitigated_this_bar = True

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

        for brk in self._breakers:
            if brk["state"] != "active":
                continue

            mid = (brk["upper"] + brk["lower"]) / 2.0
            dist = abs(price - mid)

            if brk["direction"] == 1:
                self._active_bull_count += 1
                if dist < nearest_bull_dist:
                    nearest_bull_dist = dist
                    self._nearest_bull_upper = brk["upper"]
                    self._nearest_bull_lower = brk["lower"]
            else:
                self._active_bear_count += 1
                if dist < nearest_bear_dist:
                    nearest_bear_dist = dist
                    self._nearest_bear_upper = brk["upper"]
                    self._nearest_bear_lower = brk["lower"]

    def reset(self) -> None:
        """Reset all mutable state."""
        self._breakers.clear()
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
            "breakers": [dict(b) for b in self._breakers],
            "version": self._version,
        }

    def get_output_keys(self) -> list[str]:
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

    def get_value(self, key: str) -> float | int | bool:
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
        return (
            f"IncrementalBreakerBlock("
            f"max_active={self._max_active}, "
            f"breakers={len(self._breakers)})"
        )
