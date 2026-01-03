"""
Market Structure Type Definitions.

Enums for structure and zone types with per-type output schemas.

NAMING CONVENTION:
- Internal outputs: Used by detectors (e.g., "high_level", "recency")
- Public outputs: Exposed via snapshot.get() (e.g., "swing_high_level", "swing_recency_bars")
- Builder maps internal → public

SCHEMA VERSION:
- STRUCTURE_SCHEMA_VERSION tracks the public contract version.
- Once a public field exists, it cannot be renamed or removed (additive-only).
- Increment PATCH for documentation changes, MINOR for new fields, MAJOR for breaking changes.
"""

from enum import Enum


# =============================================================================
# SCHEMA VERSION (Stage 3.2+)
# =============================================================================

# Structure schema version: tracks public field contract
# Format: MAJOR.MINOR.PATCH (semver)
# - MAJOR: Breaking changes (never in practice - additive-only policy)
# - MINOR: New fields added
# - PATCH: Documentation or internal changes
STRUCTURE_SCHEMA_VERSION = "1.2.0"  # 1.2.0: Added zone interaction fields (Stage 6)


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


# =============================================================================
# INTERNAL OUTPUT SCHEMAS (detector outputs)
# =============================================================================

# Note: Default float64 for price levels/bounds to avoid boundary edge bugs.
# Optimize to float32 only if profiling shows memory pressure.

SWING_INTERNAL_OUTPUTS: tuple[str, ...] = (
    "high_level",  # float64: Price level of swing high
    "high_idx",    # int32: Bar index of swing high
    "low_level",   # float64: Price level of swing low
    "low_idx",     # int32: Bar index of swing low
    "state",       # int8: Confirmation state (internal use)
    "recency",     # int16: Bars since last update
)

TREND_INTERNAL_OUTPUTS: tuple[str, ...] = (
    "trend_state",     # int8: 0=unknown, 1=UP, 2=DOWN (TrendState enum)
    "recency",         # int16: Bars since state change
    "parent_version",  # int32: Version counter (increments on change)
)


# =============================================================================
# PUBLIC OUTPUT SCHEMAS (exposed via snapshot.get())
# =============================================================================

SWING_PUBLIC_OUTPUTS: tuple[str, ...] = (
    "swing_high_level",    # float64: Price level of swing high
    "swing_high_idx",      # int32: Bar index of swing high
    "swing_low_level",     # float64: Price level of swing low
    "swing_low_idx",       # int32: Bar index of swing low
    "swing_recency_bars",  # int16: Bars since last update
)

TREND_PUBLIC_OUTPUTS: tuple[str, ...] = (
    "trend_state",     # int8: 0=unknown, 1=UP, 2=DOWN (TrendState enum)
    "parent_version",  # int32: Version counter
)


# =============================================================================
# INTERNAL → PUBLIC MAPPING
# =============================================================================

SWING_OUTPUT_MAPPING: dict[str, str] = {
    # internal_key: public_key
    "high_level": "swing_high_level",
    "high_idx": "swing_high_idx",
    "low_level": "swing_low_level",
    "low_idx": "swing_low_idx",
    "recency": "swing_recency_bars",
    # "state" is internal-only (not exposed publicly)
}

TREND_OUTPUT_MAPPING: dict[str, str] = {
    # internal_key: public_key (same names for TREND)
    "trend_state": "trend_state",
    "parent_version": "parent_version",
    # "recency" is internal-only for TREND
}


# =============================================================================
# STRUCTURE OUTPUT SCHEMAS (used by registry)
# =============================================================================

# Output schemas by structure type (public names for validation)
STRUCTURE_OUTPUT_SCHEMAS: dict[StructureType, tuple[str, ...]] = {
    StructureType.SWING: SWING_PUBLIC_OUTPUTS,
    StructureType.TREND: TREND_PUBLIC_OUTPUTS,
}

# Internal output schemas (used by detectors)
STRUCTURE_INTERNAL_SCHEMAS: dict[StructureType, tuple[str, ...]] = {
    StructureType.SWING: SWING_INTERNAL_OUTPUTS,
    StructureType.TREND: TREND_INTERNAL_OUTPUTS,
}

# Mapping from internal to public names
STRUCTURE_OUTPUT_MAPPINGS: dict[StructureType, dict[str, str]] = {
    StructureType.SWING: SWING_OUTPUT_MAPPING,
    StructureType.TREND: TREND_OUTPUT_MAPPING,
}

# Required params by structure type
STRUCTURE_REQUIRED_PARAMS: dict[StructureType, list[str]] = {
    StructureType.SWING: ["left", "right"],
    StructureType.TREND: [],  # Trend derives from swings, no params
}


# =============================================================================
# ZONE OUTPUT SCHEMAS (Stage 5.1+)
# =============================================================================

ZONE_OUTPUTS: tuple[str, ...] = (
    "lower",            # float64: Lower bound
    "upper",            # float64: Upper bound
    "state",            # int8: 0=none, 1=active, 2=broken
    "recency",          # int16: Bars since zone established
    "parent_anchor_id", # int32: Links to parent swing index
    "instance_id",      # int64: Deterministic hash(zone_key, zone_spec_id, parent_anchor_id)
    # Stage 6: Zone interaction fields
    "touched",          # uint8: 1 if bar range intersects zone (bar_low <= upper AND bar_high >= lower)
    "inside",           # uint8: 1 if close within zone bounds (close >= lower AND close <= upper)
    "time_in_zone",     # int32: Consecutive bars where state==ACTIVE AND inside==1 AND same instance
)
