"""
Incremental displacement detector.

Detects strong impulsive candles that signal institutional activity.
A displacement is a candle with a large body relative to ATR and small
wicks relative to body size.

Detection Criteria:
    1. body_atr_ratio = abs(close - open) / ATR >= body_atr_min
    2. wick_ratio = (upper_wick + lower_wick) / body <= wick_ratio_max

Direction:
    - Bullish (1): close > open
    - Bearish (-1): close < open

Per-bar outputs reset each update:
    - is_displacement: True if current bar is a displacement
    - direction: 1 (bullish), -1 (bearish), 0 (none)
    - body_atr_ratio: Body size as ATR multiple
    - wick_ratio: Total wick size as fraction of body

Persistent outputs (carry forward):
    - last_idx: Bar index of most recent displacement
    - last_direction: Direction of most recent displacement
    - version: Monotonic counter, increments on each displacement event

Example Play usage:
    features:
      atr_14:
        indicator: atr
        params: {length: 14}

    structures:
      exec:
        - type: displacement
          key: disp
          params:
            atr_key: atr_14
            body_atr_min: 1.5
            wick_ratio_max: 0.4

    actions:
      entry_long:
        all:
          - ["disp.is_displacement", "==", 1]
          - ["disp.direction", "==", 1]

See: docs/architecture/INCREMENTAL_STATE_ARCHITECTURE.md
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from ..base import BaseIncrementalDetector
from ..registry import register_structure

if TYPE_CHECKING:
    from ..base import BarData


@register_structure("displacement")
class IncrementalDisplacement(BaseIncrementalDetector):
    """
    Displacement detector: strong impulsive candle identification.

    Identifies candles where the body is large relative to ATR and wicks
    are small relative to body. This signals aggressive institutional
    order flow.

    No dependencies on other structure detectors -- only requires an ATR
    indicator value via bar.indicators.

    Outputs:
        - is_displacement: bool (True if current bar is a displacement)
        - direction: int (1=bullish, -1=bearish, 0=none)
        - body_atr_ratio: float (body / ATR)
        - wick_ratio: float ((upper_wick + lower_wick) / body)
        - last_idx: int (bar index of most recent displacement)
        - last_direction: int (direction of most recent displacement)
        - version: int (monotonic counter, increments on displacement event)
    """

    REQUIRED_PARAMS: list[str] = []
    OPTIONAL_PARAMS: dict[str, Any] = {
        "atr_key": "atr",
        "body_atr_min": 1.5,
        "wick_ratio_max": 0.4,
    }
    DEPENDS_ON: list[str] = []

    def __init__(
        self,
        params: dict[str, Any],
        deps: dict[str, BaseIncrementalDetector] | None,
    ) -> None:
        """
        Initialize displacement detector.

        Args:
            params: Parameters dict with optional atr_key, body_atr_min, wick_ratio_max.
            deps: Dependencies dict (unused, displacement has no deps).
        """
        self._atr_key: str = params.get("atr_key", "atr")
        self._body_atr_min: float = float(params.get("body_atr_min", 1.5))
        self._wick_ratio_max: float = float(params.get("wick_ratio_max", 0.4))

        # Per-bar state (reset each update)
        self._is_displacement: bool = False
        self._direction: int = 0
        self._body_atr_ratio: float = float("nan")
        self._wick_ratio: float = float("nan")

        # Persistent state (carry forward)
        self._last_displacement_idx: int = -1
        self._last_displacement_dir: int = 0
        self._version: int = 0

    def update(self, bar_idx: int, bar: "BarData") -> None:
        """
        Process one bar and check for displacement.

        Args:
            bar_idx: Current bar index.
            bar: Bar data including OHLCV and indicators.
        """
        # Reset per-bar flags
        self._is_displacement = False
        self._direction = 0
        self._body_atr_ratio = float("nan")
        self._wick_ratio = float("nan")

        # Get ATR from indicators
        atr_val = bar.indicators.get(self._atr_key)
        if atr_val is None or math.isnan(atr_val):
            return

        atr = float(atr_val)
        if atr <= 0:
            return

        # Compute body and wick sizes
        body = abs(bar.close - bar.open)

        # Guard against zero body (doji)
        if body == 0:
            self._body_atr_ratio = 0.0
            self._wick_ratio = float("inf")
            return

        upper_wick = bar.high - max(bar.open, bar.close)
        lower_wick = min(bar.open, bar.close) - bar.low

        body_atr_ratio = body / atr
        wick_ratio = (upper_wick + lower_wick) / body

        self._body_atr_ratio = body_atr_ratio
        self._wick_ratio = wick_ratio

        # Check displacement criteria
        if body_atr_ratio >= self._body_atr_min and wick_ratio <= self._wick_ratio_max:
            self._is_displacement = True
            self._direction = 1 if bar.close > bar.open else -1
            self._last_displacement_idx = bar_idx
            self._last_displacement_dir = self._direction
            self._version += 1

    def reset(self) -> None:
        """Reset all mutable state to initial values."""
        self._is_displacement = False
        self._direction = 0
        self._body_atr_ratio = float("nan")
        self._wick_ratio = float("nan")
        self._last_displacement_idx = -1
        self._last_displacement_dir = 0
        self._version = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize state for crash recovery."""
        return {
            "is_displacement": self._is_displacement,
            "direction": self._direction,
            "body_atr_ratio": self._body_atr_ratio,
            "wick_ratio": self._wick_ratio,
            "last_displacement_idx": self._last_displacement_idx,
            "last_displacement_dir": self._last_displacement_dir,
            "version": self._version,
        }

    def get_output_keys(self) -> list[str]:
        """
        Return list of output keys.

        Returns:
            List of output key names.
        """
        return [
            "is_displacement",
            "direction",
            "body_atr_ratio",
            "wick_ratio",
            "last_idx",
            "last_direction",
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
        if key == "is_displacement":
            return self._is_displacement
        elif key == "direction":
            return self._direction
        elif key == "body_atr_ratio":
            return self._body_atr_ratio
        elif key == "wick_ratio":
            return self._wick_ratio
        elif key == "last_idx":
            return self._last_displacement_idx
        elif key == "last_direction":
            return self._last_displacement_dir
        elif key == "version":
            return self._version
        else:
            raise KeyError(key)
