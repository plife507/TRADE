"""
Structure Renderer Registry.

Maps structure types to their visualization methods.
Fails loud if an unsupported structure type is encountered.
"""

from typing import Any
from dataclasses import dataclass


class UnsupportedStructureError(Exception):
    """Raised when a structure type has no supported renderer."""

    def __init__(self, structure_type: str, supported: list[str]):
        self.structure_type = structure_type
        self.supported = supported
        super().__init__(
            f"Visualizer does not support structure type '{structure_type}'. "
            f"Supported: {supported}"
        )


@dataclass
class StructureRenderSpec:
    """Specification for how to render a structure."""

    render_method: str  # pivot_markers, fib_levels, zone_boxes, etc.
    display: str  # overlay (structures are always on price chart)


# Structure colors
STRUCTURE_COLORS = {
    "swing_high": "#F44336",  # Red for highs
    "swing_low": "#4CAF50",  # Green for lows
    "fib_level": "#FF9800",  # Orange for fib levels
    "zone_demand": "#4CAF50",  # Green for demand
    "zone_supply": "#F44336",  # Red for supply
    "zone_neutral": "#9E9E9E",  # Grey for neutral
    "trend_up": "#4CAF50",  # Green for uptrend
    "trend_down": "#F44336",  # Red for downtrend
}


class StructureRenderer:
    """
    Registry of supported structure visualization methods.

    Fail-loud: raises UnsupportedStructureError for unknown types.
    """

    SUPPORTED: dict[str, StructureRenderSpec] = {
        # Swing pivots - triangle markers at pivot points
        "swing": StructureRenderSpec("pivot_markers", "overlay"),

        # Fibonacci - horizontal lines with ratio labels
        "fibonacci": StructureRenderSpec("fib_levels", "overlay"),

        # Zones - filled rectangles
        "zone": StructureRenderSpec("zone_boxes", "overlay"),

        # Derived zones - K-slot zones (same as zone rendering)
        "derived_zone": StructureRenderSpec("zone_boxes", "overlay"),

        # Trend - directional arrows or background coloring
        "trend": StructureRenderSpec("trend_arrows", "overlay"),

        # Rolling window - simple line (like indicator)
        "rolling_window": StructureRenderSpec("line", "overlay"),
    }

    @classmethod
    def get_supported_types(cls) -> list[str]:
        """Get list of all supported structure types."""
        return sorted(cls.SUPPORTED.keys())

    @classmethod
    def is_supported(cls, structure_type: str) -> bool:
        """Check if a structure type is supported."""
        return structure_type in cls.SUPPORTED

    @classmethod
    def get_spec(cls, structure_type: str) -> StructureRenderSpec:
        """
        Get render specification for a structure type.

        Raises:
            UnsupportedStructureError: If type not supported
        """
        if structure_type not in cls.SUPPORTED:
            raise UnsupportedStructureError(
                structure_type, cls.get_supported_types()
            )
        return cls.SUPPORTED[structure_type]

    @classmethod
    def format_label(cls, structure_type: str, params: dict, tf: str) -> str:
        """
        Format a human-readable label for the structure.

        Args:
            structure_type: Type like "swing", "fibonacci"
            params: Structure params like {"left": 5, "right": 5}
            tf: Timeframe like "15m", "1h"

        Returns:
            Label like "Swing(5,5) 15m"
        """
        type_title = structure_type.replace("_", " ").title()

        # Structure-specific param formatting
        if structure_type == "swing":
            left = params.get("left", 5)
            right = params.get("right", 5)
            return f"{type_title}({left},{right}) {tf}"

        if structure_type == "fibonacci":
            mode = params.get("mode", "retracement")
            return f"Fib {mode.title()} {tf}"

        if structure_type in ("zone", "derived_zone"):
            zone_type = params.get("zone_type", "")
            return f"{zone_type.title()} Zones {tf}"

        return f"{type_title} {tf}"

    @classmethod
    def render_swing(
        cls,
        key: str,
        pivots: list[dict],
        params: dict,
        tf: str,
    ) -> dict[str, Any]:
        """
        Render swing pivot data.

        Args:
            key: Structure key
            pivots: List of {"time": unix_ts, "type": "high"|"low", "level": float}
            params: Structure params
            tf: Timeframe

        Returns:
            Dict ready for JSON serialization
        """
        return {
            "key": key,
            "type": "swing",
            "render_method": "pivot_markers",
            "params": params,
            "tf": tf,
            "label": cls.format_label("swing", params, tf),
            "pivots": pivots,
            "colors": {
                "high": STRUCTURE_COLORS["swing_high"],
                "low": STRUCTURE_COLORS["swing_low"],
            },
        }

    @classmethod
    def render_fibonacci(
        cls,
        key: str,
        levels: list[dict],
        params: dict,
        tf: str,
    ) -> dict[str, Any]:
        """
        Render fibonacci level data.

        Args:
            key: Structure key
            levels: List of {"ratio": float, "price": float, "start_time": ts, "end_time": ts}
            params: Structure params
            tf: Timeframe

        Returns:
            Dict ready for JSON serialization
        """
        return {
            "key": key,
            "type": "fibonacci",
            "render_method": "fib_levels",
            "params": params,
            "tf": tf,
            "label": cls.format_label("fibonacci", params, tf),
            "levels": levels,
            "color": STRUCTURE_COLORS["fib_level"],
        }

    @classmethod
    def render_zone(
        cls,
        key: str,
        zones: list[dict],
        params: dict,
        tf: str,
        structure_type: str = "zone",
    ) -> dict[str, Any]:
        """
        Render zone box data.

        Args:
            key: Structure key
            zones: List of {"upper": float, "lower": float, "state": str,
                           "start_time": ts, "end_time": ts|None}
            params: Structure params
            tf: Timeframe
            structure_type: "zone" or "derived_zone"

        Returns:
            Dict ready for JSON serialization
        """
        return {
            "key": key,
            "type": structure_type,
            "render_method": "zone_boxes",
            "params": params,
            "tf": tf,
            "label": cls.format_label(structure_type, params, tf),
            "zones": zones,
            "colors": {
                "demand": STRUCTURE_COLORS["zone_demand"],
                "supply": STRUCTURE_COLORS["zone_supply"],
                "neutral": STRUCTURE_COLORS["zone_neutral"],
            },
        }

    @classmethod
    def render_trend(
        cls,
        key: str,
        segments: list[dict],
        params: dict,
        tf: str,
    ) -> dict[str, Any]:
        """
        Render trend direction data.

        Args:
            key: Structure key
            segments: List of {"start_time": ts, "end_time": ts, "direction": "up"|"down"}
            params: Structure params
            tf: Timeframe

        Returns:
            Dict ready for JSON serialization
        """
        return {
            "key": key,
            "type": "trend",
            "render_method": "trend_arrows",
            "params": params,
            "tf": tf,
            "label": cls.format_label("trend", params, tf),
            "segments": segments,
            "colors": {
                "up": STRUCTURE_COLORS["trend_up"],
                "down": STRUCTURE_COLORS["trend_down"],
            },
        }
