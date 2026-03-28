"""
Incremental Order Block (OB) detector.

Detects the last opposing candle before a displacement move. In a bullish
scenario: the last bearish candle before a strong bullish displacement.
When price returns to this zone, institutions defend it.

Detection Logic:
    1. Identify displacement candle (via displacement dep or inline ATR check)
    2. Search backward in candle history for the last opposing candle
    3. Create OB zone from the opposing candle's body (or full range)

Mitigation Logic:
    Bullish OB (direction=1): zone below current price
        - Touched when bar.low <= ob.upper
        - Mitigated when touched (touch_count >= 1)
        - Invalidated when bar.close < ob.lower
    Bearish OB (direction=-1): zone above current price
        - Touched when bar.high >= ob.lower
        - Mitigated when touched (touch_count >= 1)
        - Invalidated when bar.close > ob.upper

Output keys:
    new_this_bar: True if a new OB was detected this bar
    new_direction: Direction of newest OB (1=bull, -1=bear, 0=none)
    new_upper: Upper boundary of newest OB (NaN if none)
    new_lower: Lower boundary of newest OB (NaN if none)
    nearest_bull_upper: Upper of nearest active bullish OB
    nearest_bull_lower: Lower of nearest active bullish OB
    nearest_bear_upper: Upper of nearest active bearish OB
    nearest_bear_lower: Lower of nearest active bearish OB
    active_bull_count: Number of active bullish OBs
    active_bear_count: Number of active bearish OBs
    any_mitigated_this_bar: True if any OB was mitigated this bar
    version: Monotonic counter, increments on new OB creation

Example Play usage:
    features:
      atr_14:
        indicator: atr
        params: {length: 14}

    structures:
      exec:
        - type: swing
          key: swing
          params: {left: 5, right: 5}
        - type: order_block
          key: ob
          uses: swing
          params:
            atr_key: atr_14
            use_body: true
            body_atr_min: 1.5
            max_active: 5
            lookback: 3

    actions:
      entry_long:
        all:
          - ["ob.new_this_bar", "==", 1]
          - ["ob.new_direction", "==", 1]

See: docs/MARKET_STRUCTURE_FEATURES.md
"""

from __future__ import annotations

import math
from collections import deque
from typing import TYPE_CHECKING, Any

from ..base import BaseIncrementalDetector
from ..registry import register_structure

if TYPE_CHECKING:
    from ..base import BarData


@register_structure("order_block")
class IncrementalOrderBlock(BaseIncrementalDetector):
    """
    Order Block detector with slot-based tracking.

    Identifies the last opposing candle before a displacement move and
    tracks the resulting zone for mitigation and invalidation.

    Depends on swing detector (DEPENDS_ON). Optionally uses a displacement
    detector (OPTIONAL_DEPS) for displacement identification; falls back
    to inline ATR-based detection when no displacement dep is provided.

    Parameters:
        atr_key: Indicator key for ATR values (default: "atr")
        use_body: If True, OB zone = candle body; False = full range (default: True)
        require_displacement: Must follow a displacement candle (default: True)
        body_atr_min: Displacement threshold if no dep (default: 1.5)
        wick_ratio_max: Displacement wick filter if no dep (default: 0.4)
        max_active: Maximum tracked active OB slots (default: 5)
        lookback: How many candles back to search for opposing candle (default: 3)

    OB Slot Fields:
        direction: 1 (bullish) or -1 (bearish)
        upper: Upper boundary of the OB zone
        lower: Lower boundary of the OB zone
        anchor_idx: Bar index where OB was detected
        state: "active", "mitigated", or "invalidated"
        touch_count: Number of times price touched the zone
    """

    REQUIRED_PARAMS: list[str] = []
    OPTIONAL_PARAMS: dict[str, Any] = {
        "atr_key": "atr",
        "use_body": True,
        "require_displacement": True,
        "body_atr_min": 1.5,
        "wick_ratio_max": 0.4,
        "max_active": 5,
        "lookback": 3,
    }
    DEPENDS_ON: list[str] = ["swing"]
    OPTIONAL_DEPS: list[str] = ["displacement"]

    @classmethod
    def _validate_params(
        cls, struct_type: str, key: str, params: dict[str, Any]
    ) -> None:
        """Validate order block parameters."""
        max_active = params.get("max_active", 5)
        if not isinstance(max_active, int) or max_active < 1:
            raise ValueError(
                f"Structure '{key}' (type: {struct_type}): 'max_active' must be integer >= 1, got {max_active!r}\n"
                "\n"
                "Fix: max_active: 5"
            )

        lookback = params.get("lookback", 3)
        if not isinstance(lookback, int) or lookback < 1:
            raise ValueError(
                f"Structure '{key}' (type: {struct_type}): 'lookback' must be integer >= 1, got {lookback!r}\n"
                "\n"
                "Fix: lookback: 3"
            )

        body_atr_min = params.get("body_atr_min", 1.5)
        if not isinstance(body_atr_min, (int, float)) or body_atr_min <= 0:
            raise ValueError(
                f"Structure '{key}' (type: {struct_type}): 'body_atr_min' must be positive, got {body_atr_min!r}\n"
                "\n"
                "Fix: body_atr_min: 1.5"
            )

        wick_ratio_max = params.get("wick_ratio_max", 0.4)
        if not isinstance(wick_ratio_max, (int, float)) or wick_ratio_max < 0:
            raise ValueError(
                f"Structure '{key}' (type: {struct_type}): 'wick_ratio_max' must be >= 0, got {wick_ratio_max!r}\n"
                "\n"
                "Fix: wick_ratio_max: 0.4"
            )

    def __init__(
        self,
        params: dict[str, Any],
        deps: dict[str, BaseIncrementalDetector],
    ) -> None:
        """
        Initialize order block detector.

        Args:
            params: Parameters dict.
            deps: Dependencies dict with 'swing' and optionally 'displacement'.
        """
        self._swing = deps["swing"]
        self._displacement_dep: BaseIncrementalDetector | None = deps.get("displacement")

        self._atr_key: str = params.get("atr_key", "atr")
        self._use_body: bool = params.get("use_body", True)
        self._require_displacement: bool = params.get("require_displacement", True)
        self._body_atr_min: float = float(params.get("body_atr_min", 1.5))
        self._wick_ratio_max: float = float(params.get("wick_ratio_max", 0.4))
        self._max_active: int = int(params.get("max_active", 5))
        self._lookback: int = int(params.get("lookback", 3))

        # Candle history buffer: (idx, open, high, low, close)
        self._candle_history: deque[tuple[int, float, float, float, float]] = deque(
            maxlen=self._lookback + 2
        )

        # Active OB slots: list of dicts, newest first
        self._obs: list[dict[str, Any]] = []

        # Per-bar flags (reset each update)
        self._new_this_bar: bool = False
        self._new_direction: int = 0
        self._new_upper: float = float("nan")
        self._new_lower: float = float("nan")
        self._any_mitigated_this_bar: bool = False
        self._any_invalidated_this_bar: bool = False
        self._last_invalidated_direction: int = 0
        self._last_invalidated_upper: float = float("nan")
        self._last_invalidated_lower: float = float("nan")

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
        Process one bar and update OB state.

        Steps:
        1. Reset per-bar flags
        2. Check if current bar is a displacement
        3. If displacement: search backward for opposing candle, create OB
        4. Push current candle to history
        5. Update mitigation/invalidation for all active OBs
        6. Prune beyond max_active
        7. Recompute nearest and aggregates

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
        self._any_invalidated_this_bar = False
        self._last_invalidated_direction = 0
        self._last_invalidated_upper = float("nan")
        self._last_invalidated_lower = float("nan")

        # Step 2: Check for displacement
        is_disp, disp_dir = self._check_displacement(bar)

        # Step 3: If displacement detected, search backward for opposing candle
        if is_disp and disp_dir != 0 and len(self._candle_history) > 0:
            self._search_and_create_ob(bar_idx, disp_dir)

        # Step 4: Push current candle to history AFTER OB search
        self._candle_history.append(
            (bar_idx, bar.open, bar.high, bar.low, bar.close)
        )

        # Step 5: Update mitigation/invalidation for all active OBs
        self._update_mitigation(bar_idx, bar)

        # Step 6: Prune beyond max_active
        self._prune_obs()

        # Step 7: Recompute nearest and aggregates
        self._recompute_aggregates(bar)

    def _check_displacement(self, bar: "BarData") -> tuple[bool, int]:
        """
        Check if the current bar is a displacement candle.

        Uses displacement dependency if available, otherwise computes inline
        using ATR-based body/wick ratio checks.

        Args:
            bar: Current bar data.

        Returns:
            Tuple of (is_displacement, direction). Direction is 1 (bull), -1 (bear), 0 (none).
        """
        # Try displacement dependency first
        if self._displacement_dep is not None:
            is_disp = self._displacement_dep.get_value("is_displacement")
            direction = self._displacement_dep.get_value("direction")
            return (bool(is_disp), int(direction))

        # Inline displacement detection
        atr_val = bar.indicators.get(self._atr_key)
        if atr_val is None or math.isnan(atr_val):
            return (False, 0)

        atr = float(atr_val)
        if atr <= 0:
            return (False, 0)

        body = abs(bar.close - bar.open)
        if body == 0:
            return (False, 0)

        upper_wick = bar.high - max(bar.open, bar.close)
        lower_wick = min(bar.open, bar.close) - bar.low

        body_atr_ratio = body / atr
        wick_ratio = (upper_wick + lower_wick) / body

        if body_atr_ratio >= self._body_atr_min and wick_ratio <= self._wick_ratio_max:
            direction = 1 if bar.close > bar.open else -1
            return (True, direction)

        return (False, 0)

    def _search_and_create_ob(self, bar_idx: int, disp_dir: int) -> None:
        """
        Search backward in candle history for the last opposing candle.

        For bullish displacement (disp_dir=1): look for last bearish candle (close < open).
        For bearish displacement (disp_dir=-1): look for last bullish candle (close > open).

        Args:
            bar_idx: Current bar index.
            disp_dir: Displacement direction (1 or -1).
        """
        # Search backward through candle history (most recent first)
        for i in range(len(self._candle_history) - 1, -1, -1):
            c_idx, c_open, c_high, c_low, c_close = self._candle_history[i]

            # Check if this candle is opposing
            if disp_dir == 1 and c_close < c_open:
                # Found bearish candle before bullish displacement
                self._create_ob(
                    direction=1,
                    candle_open=c_open,
                    candle_high=c_high,
                    candle_low=c_low,
                    candle_close=c_close,
                    anchor_idx=bar_idx,
                )
                return
            elif disp_dir == -1 and c_close > c_open:
                # Found bullish candle before bearish displacement
                self._create_ob(
                    direction=-1,
                    candle_open=c_open,
                    candle_high=c_high,
                    candle_low=c_low,
                    candle_close=c_close,
                    anchor_idx=bar_idx,
                )
                return

    def _create_ob(
        self,
        direction: int,
        candle_open: float,
        candle_high: float,
        candle_low: float,
        candle_close: float,
        anchor_idx: int,
    ) -> None:
        """Create a new OB slot and prepend to list."""
        if self._use_body:
            # Zone = candle body range
            lower = min(candle_open, candle_close)
            upper = max(candle_open, candle_close)
        else:
            # Zone = full candle range
            lower = candle_low
            upper = candle_high

        # Guard: zero-width zone (doji)
        if upper <= lower:
            return

        ob: dict[str, Any] = {
            "direction": direction,
            "upper": upper,
            "lower": lower,
            "anchor_idx": anchor_idx,
            "state": "active",
            "touch_count": 0,
        }
        # Prepend (newest first)
        self._obs.insert(0, ob)

        # Set per-bar flags
        self._new_this_bar = True
        self._new_direction = direction
        self._new_upper = upper
        self._new_lower = lower

        # Increment version
        self._version += 1

    def _update_mitigation(self, bar_idx: int, bar: "BarData") -> None:
        """Update mitigation/invalidation state for all active OBs.

        Skips mitigation on the creation bar -- OBs should only be mitigated
        when price RETURNS to the zone on a later bar.

        Args:
            bar_idx: Current bar index.
            bar: Bar data including OHLCV.
        """
        for ob in self._obs:
            if ob["state"] != "active":
                continue

            # Skip mitigation check on creation bar
            if ob["anchor_idx"] == bar_idx:
                continue

            upper = ob["upper"]
            lower = ob["lower"]

            if ob["direction"] == 1:
                # Bullish OB: invalidation takes priority
                if bar.close < lower:
                    ob["state"] = "invalidated"
                    self._any_invalidated_this_bar = True
                    self._last_invalidated_direction = ob["direction"]
                    self._last_invalidated_upper = upper
                    self._last_invalidated_lower = lower
                elif bar.low <= upper:
                    ob["touch_count"] += 1
                    ob["state"] = "mitigated"
                    self._any_mitigated_this_bar = True
            else:
                # Bearish OB: invalidation takes priority
                if bar.close > upper:
                    ob["state"] = "invalidated"
                    self._any_invalidated_this_bar = True
                    self._last_invalidated_direction = ob["direction"]
                    self._last_invalidated_upper = upper
                    self._last_invalidated_lower = lower
                elif bar.high >= lower:
                    ob["touch_count"] += 1
                    ob["state"] = "mitigated"
                    self._any_mitigated_this_bar = True

    def _prune_obs(self) -> None:
        """Remove OBs beyond max_active total."""
        if len(self._obs) > self._max_active:
            self._obs = self._obs[: self._max_active]

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

        for ob in self._obs:
            if ob["state"] != "active":
                continue

            mid = (ob["upper"] + ob["lower"]) / 2.0
            dist = abs(price - mid)

            if ob["direction"] == 1:
                self._active_bull_count += 1
                if dist < nearest_bull_dist:
                    nearest_bull_dist = dist
                    self._nearest_bull_upper = ob["upper"]
                    self._nearest_bull_lower = ob["lower"]
            else:
                self._active_bear_count += 1
                if dist < nearest_bear_dist:
                    nearest_bear_dist = dist
                    self._nearest_bear_upper = ob["upper"]
                    self._nearest_bear_lower = ob["lower"]

    def reset(self) -> None:
        """Reset all mutable state to initial values."""
        self._candle_history.clear()
        self._obs.clear()
        self._new_this_bar = False
        self._new_direction = 0
        self._new_upper = float("nan")
        self._new_lower = float("nan")
        self._any_mitigated_this_bar = False
        self._any_invalidated_this_bar = False
        self._last_invalidated_direction = 0
        self._last_invalidated_upper = float("nan")
        self._last_invalidated_lower = float("nan")
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
            "candle_history": list(self._candle_history),
            "obs": [dict(ob) for ob in self._obs],
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
            "any_invalidated_this_bar",
            "last_invalidated_direction",
            "last_invalidated_upper",
            "last_invalidated_lower",
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
        elif key == "any_invalidated_this_bar":
            return self._any_invalidated_this_bar
        elif key == "last_invalidated_direction":
            return self._last_invalidated_direction
        elif key == "last_invalidated_upper":
            return self._last_invalidated_upper
        elif key == "last_invalidated_lower":
            return self._last_invalidated_lower
        elif key == "version":
            return self._version
        else:
            raise KeyError(key)

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        return (
            f"IncrementalOrderBlock("
            f"atr_key={self._atr_key!r}, "
            f"use_body={self._use_body}, "
            f"max_active={self._max_active}, "
            f"obs={len(self._obs)})"
        )
