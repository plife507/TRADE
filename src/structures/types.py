"""
Shared structure type definitions.

This module is the CANONICAL location for structure-related enums.
Both market_structure/ (batch) and incremental/ (O(1)) should import from here.

Note: market_structure/types.py re-exports these for backward compatibility.
"""

from enum import Enum, IntEnum, auto


class FeatureOutputType(IntEnum):
    """
    Compile-time output type declarations for feature fields.

    Used to validate operator compatibility at Play load time:
    - FLOAT: Numeric, but eq requires near_abs/near_pct (no exact equality)
    - INT: Discrete integer, eq/in allowed
    - BOOL: Boolean, eq allowed
    - ENUM: String enum token (e.g., "UP", "DOWN"), eq/in allowed

    Examples:
        - rsi.value → FLOAT
        - trend.direction → INT (1, -1, 0)
        - zone.state → ENUM ("active", "broken", "none")
        - swing.high_idx → INT
    """

    FLOAT = auto()   # Numeric float (use near_* for equality)
    INT = auto()     # Discrete integer (eq/in allowed)
    BOOL = auto()    # Boolean (eq allowed)
    ENUM = auto()    # String enum token (eq/in allowed)

    def is_numeric(self) -> bool:
        """Check if type supports numeric operators (gt, lt, between, near_*)."""
        return self in (FeatureOutputType.FLOAT, FeatureOutputType.INT)

    def is_discrete(self) -> bool:
        """Check if type supports discrete operators (eq, in)."""
        return self in (FeatureOutputType.INT, FeatureOutputType.BOOL, FeatureOutputType.ENUM)

    def allows_eq(self) -> bool:
        """Check if type allows exact equality (eq operator)."""
        # FLOAT disallowed - must use near_abs or near_pct
        return self.is_discrete()

    def allows_near(self) -> bool:
        """Check if type allows near_* operators (near_abs, near_pct)."""
        return self.is_numeric()


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
