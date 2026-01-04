"""
Incremental zone detector for demand/supply zones.

Detects and tracks demand (support) and supply (resistance) zones
based on swing pivot levels. Zones are calculated using ATR-based
width from the swing detector dependency.

State Machine:
    NONE -> ACTIVE: New swing pivot detected
    ACTIVE -> BROKEN: Price closes beyond zone boundary

Zone Calculation:
    Demand zone (from swing low):
        - lower = swing_low - (atr * width_atr)
        - upper = swing_low
    Supply zone (from swing high):
        - lower = swing_high
        - upper = swing_high + (atr * width_atr)

Zone Breaks:
    - Demand: close < lower (price closes below zone)
    - Supply: close > upper (price closes above zone)

See: docs/architecture/INCREMENTAL_STATE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from ..base import BaseIncrementalDetector
from ..registry import register_structure

if TYPE_CHECKING:
    from ..base import BarData


@register_structure("zone")
class IncrementalZoneDetector(BaseIncrementalDetector):
    """
    Demand/supply zone detector with state machine.

    Receives swing detector as dependency to create zones from pivot points.
    Zone width is calculated using ATR from bar.indicators.

    State values:
        - "none": No zone active (initial state)
        - "active": Zone is active and being tracked
        - "broken": Zone has been broken by price

    Outputs:
        - state: Current zone state ("none", "active", "broken")
        - upper: Upper boundary of the zone
        - lower: Lower boundary of the zone
        - anchor_idx: Bar index where the zone was anchored (swing pivot bar)

    Example Play configuration:
        structures:
          exec:
            - type: swing
              key: swing
              params:
                left: 5
                right: 5
            - type: zone
              key: demand_zone
              depends_on:
                swing: swing
              params:
                zone_type: demand
                width_atr: 1.5

    Attributes:
        swing: The swing detector dependency.
        zone_type: "demand" or "supply".
        width_atr: ATR multiplier for zone width.
        state: Current zone state.
        upper: Upper boundary of current zone.
        lower: Lower boundary of current zone.
        anchor_idx: Bar index where zone was created.
    """

    REQUIRED_PARAMS: list[str] = ["zone_type", "width_atr"]
    OPTIONAL_PARAMS: dict[str, Any] = {}
    DEPENDS_ON: list[str] = ["swing"]

    @classmethod
    def _validate_params(
        cls, struct_type: str, key: str, params: dict[str, Any]
    ) -> None:
        """
        Validate zone-specific parameters.

        Args:
            struct_type: The structure type name.
            key: The unique key for this structure instance.
            params: Parameter dict to validate.

        Raises:
            ValueError: If zone_type is not "demand" or "supply".
            ValueError: If width_atr is not a positive number.
        """
        zone_type = params.get("zone_type")
        if zone_type not in ("demand", "supply"):
            raise ValueError(
                f"Structure '{key}' (type: {struct_type}): 'zone_type' must be 'demand' or 'supply', got {zone_type!r}\n"
                f"\n"
                f"Fix in Play:\n"
                f"  - type: {struct_type}\n"
                f"    key: {key}\n"
                f"    params:\n"
                f"      zone_type: demand  # or 'supply'\n"
                f"      width_atr: 1.5\n"
                f"\n"
                f"Hint:\n"
                f"  - 'demand': Zone from swing low (support area)\n"
                f"  - 'supply': Zone from swing high (resistance area)"
            )

        width_atr = params.get("width_atr")
        if not isinstance(width_atr, (int, float)) or width_atr <= 0:
            raise ValueError(
                f"Structure '{key}' (type: {struct_type}): 'width_atr' must be a positive number, got {width_atr!r}\n"
                f"\n"
                f"Fix in Play:\n"
                f"  - type: {struct_type}\n"
                f"    key: {key}\n"
                f"    params:\n"
                f"      zone_type: {zone_type or 'demand'}\n"
                f"      width_atr: 1.5  # Must be > 0\n"
                f"\n"
                f"Hint:\n"
                f"  - Common values: 0.5 (tight), 1.0 (normal), 2.0 (wide)\n"
                f"  - This multiplies the ATR to determine zone width"
            )

    def __init__(
        self,
        params: dict[str, Any],
        deps: dict[str, BaseIncrementalDetector],
    ) -> None:
        """
        Initialize zone detector.

        Args:
            params: Parameters dict with zone_type and width_atr.
            deps: Dependencies dict with swing detector.
        """
        self.swing = deps["swing"]
        self.zone_type: str = params["zone_type"]
        self.width_atr: float = float(params["width_atr"])

        # State machine
        self.state: str = "none"
        self.upper: float = np.nan
        self.lower: float = np.nan
        self.anchor_idx: int = -1

        # Track last swing index to detect new swings
        self._last_swing_idx: int = -1

        # Version tracking: increments on state changes (new zone or broken)
        # Used by derived structures to detect zone state changes
        self._version: int = 0

    def update(self, bar_idx: int, bar: "BarData") -> None:
        """
        Process one bar and update zone state.

        State transitions:
        1. If new swing detected -> create new zone (NONE/ACTIVE -> ACTIVE)
        2. If zone ACTIVE and price breaks boundary -> BROKEN

        Args:
            bar_idx: Current bar index.
            bar: Bar data including OHLCV and indicators.
        """
        # Get current swing level and index based on zone type
        if self.zone_type == "demand":
            swing_level = self.swing.get_value("low_level")
            swing_idx = self.swing.get_value("low_idx")
        else:  # supply
            swing_level = self.swing.get_value("high_level")
            swing_idx = self.swing.get_value("high_idx")

        # Check for new swing (zone creation)
        if swing_idx != self._last_swing_idx and swing_idx >= 0:
            # Get ATR from indicators (default to 0 if not available)
            atr = bar.indicators.get("atr", np.nan)
            width = atr * self.width_atr if not np.isnan(atr) else 0.0

            # Calculate zone boundaries
            if self.zone_type == "demand":
                # Demand zone: extends below the swing low
                self.lower = swing_level - width
                self.upper = swing_level
            else:  # supply
                # Supply zone: extends above the swing high
                self.lower = swing_level
                self.upper = swing_level + width

            self.state = "active"
            self.anchor_idx = int(swing_idx)
            self._last_swing_idx = int(swing_idx)
            self._version += 1

        # Check for zone break (only when active)
        if self.state == "active":
            if self.zone_type == "demand" and bar.close < self.lower:
                # Demand zone broken: price closed below lower boundary
                self.state = "broken"
                self._version += 1
            elif self.zone_type == "supply" and bar.close > self.upper:
                # Supply zone broken: price closed above upper boundary
                self.state = "broken"
                self._version += 1

    def get_output_keys(self) -> list[str]:
        """
        Return list of output keys.

        Returns:
            List of output key names.
        """
        return ["state", "upper", "lower", "anchor_idx", "version"]

    def get_value(self, key: str) -> float | int | str:
        """
        Get output value by key.

        Args:
            key: Output key name.

        Returns:
            The output value.

        Raises:
            KeyError: If key is not valid.
        """
        if key == "state":
            return self.state
        elif key == "upper":
            return self.upper
        elif key == "lower":
            return self.lower
        elif key == "anchor_idx":
            return self.anchor_idx
        elif key == "version":
            return self._version
        else:
            raise KeyError(key)
