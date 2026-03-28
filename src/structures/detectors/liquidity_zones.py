"""
Incremental liquidity zones detector.

Detects clusters of swing highs or swing lows at similar price levels,
forming liquidity pools where stop-loss orders accumulate. When price
sweeps through a zone, it triggers stops and provides fills. A sweep
followed by reversal is a high-probability trade setup.

Zone Formation:
    When multiple swing highs (or lows) cluster within tolerance_atr * ATR
    of each other, a liquidity zone forms at the average of the cluster.
    Requires min_touches swings to form.

Sweep Detection:
    An active zone is swept when price penetrates beyond the zone level
    by at least sweep_atr * ATR:
    - High zone swept: bar.high > level + sweep_atr * ATR (bearish signal)
    - Low zone swept: bar.low < level - sweep_atr * ATR (bullish signal)

Output keys:
    new_zone_this_bar: True if a new zone was created this bar
    sweep_this_bar: True if a zone was swept this bar
    sweep_direction: 1 (swept highs, bearish), -1 (swept lows, bullish), 0 (none)
    swept_level: Price level of the swept zone (NaN if none)
    nearest_high_level: Level of nearest active high zone (NaN if none)
    nearest_low_level: Level of nearest active low zone (NaN if none)
    nearest_high_touches: Touch count of nearest active high zone (0 if none)
    nearest_low_touches: Touch count of nearest active low zone (0 if none)
    version: Monotonic counter, increments on new zone or sweep

Example Play usage:
    features:
      atr_14:
        indicator: atr
        params: {length: 14}

    structures:
      exec:
        - type: swing
          key: pivots
          params:
            left: 3
            right: 3
        - type: liquidity_zones
          key: liq
          uses: pivots
          params:
            atr_key: atr_14
            tolerance_atr: 0.3
            sweep_atr: 0.1
            min_touches: 2
            max_active: 5

    actions:
      entry_long:
        all:
          - ["liq.sweep_this_bar", "==", 1]
          - ["liq.sweep_direction", "==", -1]

See: docs/architecture/INCREMENTAL_STATE_ARCHITECTURE.md
"""

from __future__ import annotations

import math
from collections import deque
from typing import TYPE_CHECKING, Any

from ..base import BaseIncrementalDetector
from ..registry import register_structure

if TYPE_CHECKING:
    from ..base import BarData


@register_structure("liquidity_zones")
class IncrementalLiquidityZones(BaseIncrementalDetector):
    """
    Liquidity zone detector with sweep tracking.

    Depends on swing detector for pivot levels. Clusters nearby swing
    highs/lows into zones and detects when price sweeps through them.

    Parameters:
        atr_key: Indicator key for ATR values (default: "atr")
        tolerance_atr: Max distance between clustered swings as ATR multiple (default: 0.3)
        sweep_atr: Min penetration to count as sweep as ATR multiple (default: 0.1)
        min_touches: Min swing touches to form a zone (default: 2)
        max_active: Max active zones per side (default: 5)
        max_swing_history: How many swings to track for clustering (default: 20)
    """

    REQUIRED_PARAMS: list[str] = []
    OPTIONAL_PARAMS: dict[str, Any] = {
        "atr_key": "atr",
        "tolerance_atr": 0.3,
        "sweep_atr": 0.1,
        "min_touches": 2,
        "max_active": 5,
        "max_swing_history": 20,
    }
    DEPENDS_ON: list[str] = ["swing"]

    @classmethod
    def _validate_params(
        cls, struct_type: str, key: str, params: dict[str, Any]
    ) -> None:
        """Validate liquidity zones parameters."""
        tolerance_atr = params.get("tolerance_atr", 0.3)
        if not isinstance(tolerance_atr, (int, float)) or tolerance_atr < 0:
            raise ValueError(
                f"Structure '{key}' (type: {struct_type}): 'tolerance_atr' must be >= 0, got {tolerance_atr!r}\n"
                "\n"
                "Fix: tolerance_atr: 0.3"
            )

        sweep_atr = params.get("sweep_atr", 0.1)
        if not isinstance(sweep_atr, (int, float)) or sweep_atr < 0:
            raise ValueError(
                f"Structure '{key}' (type: {struct_type}): 'sweep_atr' must be >= 0, got {sweep_atr!r}\n"
                "\n"
                "Fix: sweep_atr: 0.1"
            )

        min_touches = params.get("min_touches", 2)
        if not isinstance(min_touches, int) or min_touches < 1:
            raise ValueError(
                f"Structure '{key}' (type: {struct_type}): 'min_touches' must be integer >= 1, got {min_touches!r}\n"
                "\n"
                "Fix: min_touches: 2"
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
        deps: dict[str, BaseIncrementalDetector],
    ) -> None:
        """
        Initialize liquidity zones detector.

        Args:
            params: Parameters dict.
            deps: Dependencies dict with swing detector.
        """
        self.swing = deps["swing"]
        self._atr_key: str = params.get("atr_key", "atr")
        self._tolerance_atr: float = float(params.get("tolerance_atr", 0.3))
        self._sweep_atr: float = float(params.get("sweep_atr", 0.1))
        self._min_touches: int = int(params.get("min_touches", 2))
        self._max_active: int = int(params.get("max_active", 5))
        self._max_swing_history: int = int(params.get("max_swing_history", 20))

        # Swing history: (bar_idx, price) tuples
        self._swing_highs: deque[tuple[int, float]] = deque(maxlen=self._max_swing_history)
        self._swing_lows: deque[tuple[int, float]] = deque(maxlen=self._max_swing_history)

        # Track last swing indices to detect new pivots
        self._last_high_idx: int = -1
        self._last_low_idx: int = -1

        # Active zones: list of dicts
        # Each: {"side": "high"|"low", "level": float, "touches": int,
        #        "state": "active"|"swept", "sweep_bar_idx": int}
        self._zones: list[dict[str, Any]] = []

        # Per-bar flags (reset each bar)
        self._new_zone_this_bar: bool = False
        self._sweep_this_bar: bool = False
        self._sweep_direction: int = 0  # 1=swept highs (bearish), -1=swept lows (bullish)
        self._swept_level: float = float("nan")

        # Nearest zone accessors
        self._nearest_high_level: float = float("nan")
        self._nearest_low_level: float = float("nan")
        self._nearest_high_touches: int = 0
        self._nearest_low_touches: int = 0

        # Version tracking
        self._version: int = 0

    def update(self, bar_idx: int, bar: "BarData") -> None:
        """
        Process one bar and update liquidity zone state.

        1. Reset per-bar flags
        2. Get ATR from indicators
        3. Check for new swing pivots and try to form zones
        4. Check for sweeps on active zones
        5. Recompute nearest zones

        Args:
            bar_idx: Current bar index.
            bar: Bar data including OHLCV and indicators.
        """
        # 1. Reset per-bar flags
        self._new_zone_this_bar = False
        self._sweep_this_bar = False
        self._sweep_direction = 0
        self._swept_level = float("nan")

        # 2. Get ATR
        atr = bar.indicators.get(self._atr_key, float("nan"))
        if isinstance(atr, float) and math.isnan(atr):
            # Without ATR, we cannot form zones or detect sweeps.
            # Still update nearest accessors from existing zones.
            self._recompute_nearest(bar.close)
            return
        if atr <= 0:
            self._recompute_nearest(bar.close)
            return

        # 3. Check for new swing pivots
        high_idx = self.swing.get_value("high_idx")
        low_idx = self.swing.get_value("low_idx")
        high_level = self.swing.get_value("high_level")
        low_level = self.swing.get_value("low_level")

        if high_idx != self._last_high_idx and high_idx >= 0:  # type: ignore[operator]
            self._last_high_idx = int(high_idx)
            if not (isinstance(high_level, float) and math.isnan(high_level)):
                self._swing_highs.append((int(high_idx), float(high_level)))
                self._try_form_zone("high", float(atr))

        if low_idx != self._last_low_idx and low_idx >= 0:  # type: ignore[operator]
            self._last_low_idx = int(low_idx)
            if not (isinstance(low_level, float) and math.isnan(low_level)):
                self._swing_lows.append((int(low_idx), float(low_level)))
                self._try_form_zone("low", float(atr))

        # 4. Check sweeps on active zones
        for zone in self._zones:
            if zone["state"] != "active":
                continue

            if zone["side"] == "high" and bar.high > zone["level"] + self._sweep_atr * atr:
                # High zone swept: bearish signal
                zone["state"] = "swept"
                zone["sweep_bar_idx"] = bar_idx
                self._sweep_this_bar = True
                self._sweep_direction = 1
                self._swept_level = zone["level"]
                self._version += 1

            elif zone["side"] == "low" and bar.low < zone["level"] - self._sweep_atr * atr:
                # Low zone swept: bullish signal
                zone["state"] = "swept"
                zone["sweep_bar_idx"] = bar_idx
                self._sweep_this_bar = True
                self._sweep_direction = -1
                self._swept_level = zone["level"]
                self._version += 1

        # 5. Prune swept zones to prevent unbounded growth
        self._zones = [z for z in self._zones if z["state"] == "active"]

        # 6. Recompute nearest zones
        self._recompute_nearest(bar.close)

    def _try_form_zone(self, side: str, atr: float) -> None:
        """
        Try to form a new zone from clustered swings.

        Checks if the newest swing clusters with enough existing swings
        (within tolerance_atr * ATR) to meet min_touches threshold.

        Args:
            side: "high" or "low"
            atr: Current ATR value (already validated > 0)
        """
        swings = self._swing_highs if side == "high" else self._swing_lows
        if len(swings) < self._min_touches:
            return

        tolerance = self._tolerance_atr * atr

        # Check the newest swing against all others for clustering
        _newest_idx, newest_price = swings[-1]
        cluster_prices = [newest_price]
        for _idx, price in list(swings)[:-1]:
            if abs(price - newest_price) <= tolerance:
                cluster_prices.append(price)

        if len(cluster_prices) >= self._min_touches:
            avg_level = sum(cluster_prices) / len(cluster_prices)
            # Check if zone already exists at this level (within tolerance)
            existing = self._find_zone_near(side, avg_level, tolerance)
            if existing is not None:
                existing["touches"] = len(cluster_prices)
                existing["level"] = avg_level
            else:
                self._create_zone(side, avg_level, len(cluster_prices))

    def _find_zone_near(
        self, side: str, level: float, tolerance: float
    ) -> dict[str, Any] | None:
        """
        Find an existing active zone near the given level.

        Args:
            side: "high" or "low"
            level: Price level to check
            tolerance: Maximum distance to match

        Returns:
            Zone dict if found, None otherwise.
        """
        for zone in self._zones:
            if zone["side"] == side and zone["state"] == "active":
                if abs(zone["level"] - level) <= tolerance:
                    return zone
        return None

    def _create_zone(self, side: str, level: float, touches: int) -> None:
        """
        Create a new active zone.

        Enforces max_active per side by removing oldest zones.

        Args:
            side: "high" or "low"
            level: Average price level of the cluster
            touches: Number of swing touches forming this zone
        """
        zone: dict[str, Any] = {
            "side": side,
            "level": level,
            "touches": touches,
            "state": "active",
            "sweep_bar_idx": -1,
        }
        self._zones.append(zone)
        self._new_zone_this_bar = True
        self._version += 1

        # Enforce max_active per side
        active_count = sum(
            1 for z in self._zones
            if z["side"] == side and z["state"] == "active"
        )
        while active_count > self._max_active:
            # Remove oldest active zone of this side
            for i, z in enumerate(self._zones):
                if z["side"] == side and z["state"] == "active":
                    self._zones.pop(i)
                    active_count -= 1
                    break

    def _recompute_nearest(self, close: float) -> None:
        """
        Recompute nearest zone levels relative to current close.

        Args:
            close: Current bar close price.
        """
        nearest_high_dist = float("inf")
        nearest_low_dist = float("inf")
        self._nearest_high_level = float("nan")
        self._nearest_low_level = float("nan")
        self._nearest_high_touches = 0
        self._nearest_low_touches = 0

        for zone in self._zones:
            if zone["state"] != "active":
                continue
            dist = abs(zone["level"] - close)
            if zone["side"] == "high" and dist < nearest_high_dist:
                nearest_high_dist = dist
                self._nearest_high_level = zone["level"]
                self._nearest_high_touches = zone["touches"]
            elif zone["side"] == "low" and dist < nearest_low_dist:
                nearest_low_dist = dist
                self._nearest_low_level = zone["level"]
                self._nearest_low_touches = zone["touches"]

    def reset(self) -> None:
        """Reset all mutable state to initial values."""
        self._swing_highs.clear()
        self._swing_lows.clear()
        self._last_high_idx = -1
        self._last_low_idx = -1
        self._zones.clear()
        self._new_zone_this_bar = False
        self._sweep_this_bar = False
        self._sweep_direction = 0
        self._swept_level = float("nan")
        self._nearest_high_level = float("nan")
        self._nearest_low_level = float("nan")
        self._nearest_high_touches = 0
        self._nearest_low_touches = 0
        self._version = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize state for crash recovery."""
        return {
            "swing_highs": list(self._swing_highs),
            "swing_lows": list(self._swing_lows),
            "last_high_idx": self._last_high_idx,
            "last_low_idx": self._last_low_idx,
            "zones": [dict(z) for z in self._zones],
            "new_zone_this_bar": self._new_zone_this_bar,
            "sweep_this_bar": self._sweep_this_bar,
            "sweep_direction": self._sweep_direction,
            "swept_level": self._swept_level,
            "nearest_high_level": self._nearest_high_level,
            "nearest_low_level": self._nearest_low_level,
            "nearest_high_touches": self._nearest_high_touches,
            "nearest_low_touches": self._nearest_low_touches,
            "version": self._version,
        }

    def get_output_keys(self) -> list[str]:
        """
        Return list of output keys.

        Returns:
            List of output key names.
        """
        return [
            "new_zone_this_bar",
            "sweep_this_bar",
            "sweep_direction",
            "swept_level",
            "nearest_high_level",
            "nearest_low_level",
            "nearest_high_touches",
            "nearest_low_touches",
            "version",
        ]

    def get_value(self, key: str) -> float | int | bool:
        """
        Get output value by key.

        Args:
            key: Output key name.

        Returns:
            The output value.

        Raises:
            KeyError: If key is not valid.
        """
        if key == "new_zone_this_bar":
            return self._new_zone_this_bar
        elif key == "sweep_this_bar":
            return self._sweep_this_bar
        elif key == "sweep_direction":
            return self._sweep_direction
        elif key == "swept_level":
            return self._swept_level
        elif key == "nearest_high_level":
            return self._nearest_high_level
        elif key == "nearest_low_level":
            return self._nearest_low_level
        elif key == "nearest_high_touches":
            return self._nearest_high_touches
        elif key == "nearest_low_touches":
            return self._nearest_low_touches
        elif key == "version":
            return self._version
        else:
            raise KeyError(key)
