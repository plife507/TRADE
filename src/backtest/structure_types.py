"""
Shared structure type definitions.

This module is the CANONICAL location for structure-related enums.
Both market_structure/ (batch) and incremental/ (O(1)) should import from here.

Note: market_structure/types.py re-exports these for backward compatibility.
"""

from enum import Enum


class StructureType(str, Enum):
    """
    Supported market structure types.

    Each type has a specific output schema defined in STRUCTURE_REGISTRY.
    """

    SWING = "swing"  # Swing high/low detection
    TREND = "trend"  # HH/HL vs LL/LH classification


class ZoneType(str, Enum):
    """
    Supported zone types.

    Zones are children of structure blocks.
    """

    DEMAND = "demand"  # Demand zone (below swing low)
    SUPPLY = "supply"  # Supply zone (above swing high)


class ZoneState(int, Enum):
    """Zone state values."""

    NONE = 0
    ACTIVE = 1
    BROKEN = 2


class TrendState(int, Enum):
    """Trend classification values for market structure.

    Note: UP/DOWN refer to structural trend (HH/HL vs LL/LH).
    BULL/BEAR are reserved for future sentiment/regime layer.
    """

    UNKNOWN = 0  # No clear trend established
    UP = 1       # HH + HL pattern (structural uptrend)
    DOWN = 2     # LL + LH pattern (structural downtrend)
