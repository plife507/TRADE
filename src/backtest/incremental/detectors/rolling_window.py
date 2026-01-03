"""
Rolling window min/max detector using MonotonicDeque.

Provides O(1) amortized rolling window minimum or maximum over
a configurable number of bars for any OHLCV field.

Usage in IdeaCard:
    structures:
      exec:
        - type: rolling_window
          key: low_20
          params:
            size: 20
            field: low
            mode: min

Access in rules:
    condition: close < structure.low_20.value

See: docs/architecture/INCREMENTAL_STATE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import Any

from ..base import BarData, BaseIncrementalDetector
from ..primitives import MonotonicDeque
from ..registry import register_structure

# Valid fields that can be tracked
VALID_FIELDS = frozenset({"open", "high", "low", "close", "volume"})

# Valid modes
VALID_MODES = frozenset({"min", "max"})


@register_structure("rolling_window")
class IncrementalRollingWindow(BaseIncrementalDetector):
    """
    Rolling min/max over N bars using MonotonicDeque.

    Maintains O(1) amortized sliding window min or max over a
    configurable OHLCV field. Uses MonotonicDeque internally for
    efficient incremental updates.

    Parameters:
        size: Window size in bars (must be integer >= 1).
        field: Bar field to track - "open", "high", "low", "close", or "volume".
        mode: "min" for minimum tracking, "max" for maximum tracking.

    Outputs:
        value: Current min/max value within the window.

    Example:
        # Track 20-bar low (for support detection)
        params = {"size": 20, "field": "low", "mode": "min"}

        # Track 10-bar high (for resistance detection)
        params = {"size": 10, "field": "high", "mode": "max"}

        # Track 50-bar volume max (for volume spike detection)
        params = {"size": 50, "field": "volume", "mode": "max"}

    Performance:
        - update(): O(1) amortized
        - get_value("value"): O(1)
    """

    REQUIRED_PARAMS: list[str] = ["size", "field", "mode"]
    OPTIONAL_PARAMS: dict[str, Any] = {}
    DEPENDS_ON: list[str] = []

    @classmethod
    def _validate_params(
        cls, struct_type: str, key: str, params: dict[str, Any]
    ) -> None:
        """
        Validate rolling window parameters.

        Raises:
            ValueError: If size is not an integer >= 1.
            ValueError: If field is not one of open/high/low/close/volume.
            ValueError: If mode is not min or max.
        """
        # Validate size
        size = params.get("size")
        if not isinstance(size, int) or size < 1:
            raise ValueError(
                f"Structure '{key}': 'size' must be integer >= 1, got {size!r}\n"
                f"\n"
                f"Fix: size: 20  # Must be a positive integer"
            )

        # Validate field
        field = params.get("field")
        if field not in VALID_FIELDS:
            valid_list = ", ".join(sorted(VALID_FIELDS))
            raise ValueError(
                f"Structure '{key}': 'field' must be one of {valid_list}, got {field!r}\n"
                f"\n"
                f"Fix: field: low  # For 20-bar low tracking"
            )

        # Validate mode
        mode = params.get("mode")
        if mode not in VALID_MODES:
            raise ValueError(
                f"Structure '{key}': 'mode' must be 'min' or 'max', got {mode!r}\n"
                f"\n"
                f"Fix: mode: min  # For minimum tracking"
            )

    def __init__(
        self,
        params: dict[str, Any],
        deps: dict[str, BaseIncrementalDetector] | None = None,
    ) -> None:
        """
        Initialize rolling window detector.

        Args:
            params: Dict with size, field, and mode.
            deps: Not used (no dependencies).
        """
        self.size: int = params["size"]
        self.field: str = params["field"]
        self.mode: str = params["mode"]

        # Internal monotonic deque for O(1) min/max
        self._deque = MonotonicDeque(self.size, self.mode)  # type: ignore[arg-type]

    def update(self, bar_idx: int, bar: BarData) -> None:
        """
        Process one bar, updating the rolling window.

        Extracts the configured field from the bar and pushes
        it to the monotonic deque.

        Args:
            bar_idx: Current bar index.
            bar: Bar data containing OHLCV values.
        """
        # Extract the field value from the bar
        value = getattr(bar, self.field)
        self._deque.push(bar_idx, value)

    def get_output_keys(self) -> list[str]:
        """
        Return list of output keys.

        Returns:
            ["value"] - the current min/max.
        """
        return ["value"]

    def get_value(self, key: str) -> float | None:
        """
        Get output by key.

        Args:
            key: Must be "value".

        Returns:
            Current min/max value, or None if window is empty.

        Raises:
            KeyError: If key is not "value".
        """
        if key == "value":
            return self._deque.get()
        raise KeyError(key)

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        return (
            f"IncrementalRollingWindow("
            f"size={self.size}, field={self.field!r}, mode={self.mode!r})"
        )
