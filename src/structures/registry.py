"""
Structure registry for incremental detectors.

Provides:
- STRUCTURE_REGISTRY: Global registry of detector classes by name
- register_structure: Decorator to register detector classes
- get_structure_info: Get metadata about a registered structure
- list_structure_types: List all registered structure type names

The registry enables dynamic discovery and validation of structure types.
Detectors are registered at import time via the @register_structure decorator.

Example:
    @register_structure("my_detector")
    class MyDetector(BaseIncrementalDetector):
        REQUIRED_PARAMS = ["period"]
        OPTIONAL_PARAMS = {"threshold": 0.5}
        DEPENDS_ON = []
        ...

    # Later:
    info = get_structure_info("my_detector")
    # Returns: {
    #     "required_params": ["period"],
    #     "optional_params": {"threshold": 0.5},
    #     "depends_on": [],
    #     "output_keys": ["value"]  # if detector instance available
    # }

See: docs/architecture/INCREMENTAL_STATE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from .types import FeatureOutputType

if TYPE_CHECKING:
    from .base import BaseIncrementalDetector

# Global registry: maps structure type name to detector class
STRUCTURE_REGISTRY: dict[str, type["BaseIncrementalDetector"]] = {}


# =============================================================================
# Structure Output Types
# =============================================================================
# Maps each structure type to its output field types for compile-time validation.
# Used by DSL to validate operator compatibility at Play load time:
# - eq operator only allowed on discrete types (INT, BOOL, ENUM)
# - near_abs/near_pct only allowed on numeric types (FLOAT, INT)

STRUCTURE_OUTPUT_TYPES: dict[str, dict[str, FeatureOutputType]] = {
    "swing": {
        # Individual pivot outputs (update independently)
        "high_level": FeatureOutputType.FLOAT,    # Price level of swing high
        "high_idx": FeatureOutputType.INT,        # Bar index of swing high
        "low_level": FeatureOutputType.FLOAT,     # Price level of swing low
        "low_idx": FeatureOutputType.INT,         # Bar index of swing low
        "version": FeatureOutputType.INT,         # Monotonic counter, increments on confirmed pivot
        "last_confirmed_pivot_idx": FeatureOutputType.INT,   # Bar index of last confirmed pivot
        "last_confirmed_pivot_type": FeatureOutputType.ENUM, # "high" or "low"
        # Gate 0: Significance outputs (require atr_key param)
        "high_significance": FeatureOutputType.FLOAT,  # ATR multiple of move from previous high
        "low_significance": FeatureOutputType.FLOAT,   # ATR multiple of move from previous low
        "high_is_major": FeatureOutputType.BOOL,       # True if high_significance >= major_threshold
        "low_is_major": FeatureOutputType.BOOL,        # True if low_significance >= major_threshold
        # Gate 2: Alternation tracking outputs (reset each bar)
        "high_accepted": FeatureOutputType.BOOL,       # True if high was accepted this bar
        "low_accepted": FeatureOutputType.BOOL,        # True if low was accepted this bar
        "high_replaced_pending": FeatureOutputType.BOOL,  # True if high replaced a pending high
        "low_replaced_pending": FeatureOutputType.BOOL,   # True if low replaced a pending low
        # Paired pivot outputs (update only when pair completes)
        "pair_high_level": FeatureOutputType.FLOAT,  # High of the current paired swing
        "pair_high_idx": FeatureOutputType.INT,      # Bar index of paired high
        "pair_low_level": FeatureOutputType.FLOAT,   # Low of the current paired swing
        "pair_low_idx": FeatureOutputType.INT,       # Bar index of paired low
        "pair_direction": FeatureOutputType.ENUM,    # "bullish" or "bearish"
        "pair_version": FeatureOutputType.INT,       # Increments on complete pair
        "pair_anchor_hash": FeatureOutputType.ENUM,  # Unique hash for this anchor pair
    },
    "trend": {
        "direction": FeatureOutputType.INT,           # 1 (up), -1 (down), 0 (flat)
        "strength": FeatureOutputType.INT,            # 0 (weak), 1 (normal), 2 (strong)
        "bars_in_trend": FeatureOutputType.INT,       # Bars since trend started
        "wave_count": FeatureOutputType.INT,          # Consecutive waves in same direction
        "last_wave_direction": FeatureOutputType.ENUM,  # "bullish", "bearish", "none"
        "last_hh": FeatureOutputType.BOOL,            # Was last high a higher high?
        "last_hl": FeatureOutputType.BOOL,            # Was last low a higher low?
        "last_lh": FeatureOutputType.BOOL,            # Was last high a lower high?
        "last_ll": FeatureOutputType.BOOL,            # Was last low a lower low?
        "version": FeatureOutputType.INT,             # Monotonic counter, increments on direction change
    },
    "zone": {
        "state": FeatureOutputType.ENUM,          # "active", "broken", "none"
        "upper": FeatureOutputType.FLOAT,         # Upper boundary of zone
        "lower": FeatureOutputType.FLOAT,         # Lower boundary of zone
        "anchor_idx": FeatureOutputType.INT,      # Bar index where zone was formed
        "version": FeatureOutputType.INT,         # Monotonic counter, increments on state change
    },
    "fibonacci": {
        # Dynamic level fields: level_<ratio> (prefix matched in get_structure_output_type)
        # Retracement levels (between high and low)
        "level_0.236": FeatureOutputType.FLOAT,
        "level_0.382": FeatureOutputType.FLOAT,
        "level_0.5": FeatureOutputType.FLOAT,
        "level_0.618": FeatureOutputType.FLOAT,
        "level_0.786": FeatureOutputType.FLOAT,
        # Extension levels (above high or below low)
        "level_1.0": FeatureOutputType.FLOAT,
        "level_1.272": FeatureOutputType.FLOAT,
        "level_1.618": FeatureOutputType.FLOAT,
        "level_2.0": FeatureOutputType.FLOAT,
        "level_2.618": FeatureOutputType.FLOAT,
        "level_0.272": FeatureOutputType.FLOAT,  # For extension_down
        # Anchor outputs (always available)
        "anchor_high": FeatureOutputType.FLOAT,  # Swing high (0% reference)
        "anchor_low": FeatureOutputType.FLOAT,   # Swing low (100% reference)
        "range": FeatureOutputType.FLOAT,        # high - low
    },
    "rolling_window": {
        "value": FeatureOutputType.FLOAT,         # Rolling min/max value
    },
    "derived_zone": {
        # Slot fields (zone{N}_*) - dynamic based on max_active param
        # Use prefix matching in get_structure_output_type()
        "zone0_lower": FeatureOutputType.FLOAT,
        "zone0_upper": FeatureOutputType.FLOAT,
        "zone0_state": FeatureOutputType.ENUM,
        "zone0_anchor_idx": FeatureOutputType.INT,
        "zone0_age_bars": FeatureOutputType.INT,
        "zone0_touched_this_bar": FeatureOutputType.BOOL,
        "zone0_touch_count": FeatureOutputType.INT,
        "zone0_last_touch_age": FeatureOutputType.INT,
        "zone0_inside": FeatureOutputType.BOOL,
        "zone0_instance_id": FeatureOutputType.INT,
        # Aggregate fields
        "active_count": FeatureOutputType.INT,
        "any_active": FeatureOutputType.BOOL,
        "any_touched": FeatureOutputType.BOOL,
        "any_inside": FeatureOutputType.BOOL,
        "first_active_lower": FeatureOutputType.FLOAT,
        "first_active_upper": FeatureOutputType.FLOAT,
        "first_active_idx": FeatureOutputType.INT,
        "newest_active_idx": FeatureOutputType.INT,
        "source_version": FeatureOutputType.INT,
    },
    "market_structure": {
        "bias": FeatureOutputType.INT,               # 1 (bullish), -1 (bearish), 0 (ranging)
        "bos_this_bar": FeatureOutputType.BOOL,      # True if BOS occurred this bar
        "choch_this_bar": FeatureOutputType.BOOL,    # True if CHoCH occurred this bar
        "bos_direction": FeatureOutputType.ENUM,     # "bullish", "bearish", "none"
        "choch_direction": FeatureOutputType.ENUM,   # "bullish", "bearish", "none"
        "last_bos_idx": FeatureOutputType.INT,       # Bar index of last BOS
        "last_bos_level": FeatureOutputType.FLOAT,   # Price level of last BOS
        "last_choch_idx": FeatureOutputType.INT,     # Bar index of last CHoCH
        "last_choch_level": FeatureOutputType.FLOAT, # Price level of last CHoCH
        "break_level_high": FeatureOutputType.FLOAT, # Level to watch for bullish break
        "break_level_low": FeatureOutputType.FLOAT,  # Level to watch for bearish break
        "version": FeatureOutputType.INT,            # Monotonic counter, increments on structure event
    },
}


# =============================================================================
# Structure Warmup Formulas
# =============================================================================
# Maps each structure type to its warmup calculation function.
# Used by execution_validation to compute warmup requirements at load time.
#
# Each formula receives:
#   - params: dict of structure params from Play
#   - swing_params: dict with 'left' and 'right' from source swing (for dependents)
#
# Returns: int (warmup bars needed)

# G6.6.7: Use Callable from typing, not lowercase callable
STRUCTURE_WARMUP_FORMULAS: dict[str, Callable] = {
    # SWING: needs left + right bars for pivot confirmation
    "swing": lambda params, swing_params: params.get("left", 5) + params.get("right", 5),

    # TREND: needs multiple swings to form trend pattern
    # Conservative heuristic: (left + right) * 5
    "trend": lambda params, swing_params: (swing_params["left"] + swing_params["right"]) * 5,

    # DERIVED_ZONE: source swing warmup + 1 bar for regen trigger
    "derived_zone": lambda params, swing_params: swing_params["left"] + swing_params["right"] + 1,

    # FIBONACCI: same as source swing warmup
    "fibonacci": lambda params, swing_params: swing_params["left"] + swing_params["right"],

    # ZONE: same as source swing warmup
    "zone": lambda params, swing_params: swing_params["left"] + swing_params["right"],

    # ROLLING_WINDOW: needs its size parameter
    "rolling_window": lambda params, swing_params: params.get("size", 20),

    # MARKET_STRUCTURE: needs multiple swings for structure detection
    # Conservative heuristic: (left + right) * 3
    "market_structure": lambda params, swing_params: (swing_params["left"] + swing_params["right"]) * 3,
}


def get_structure_warmup(structure_type: str, params: dict, swing_params: dict | None = None) -> int:
    """
    Get warmup bars needed for a structure type.

    Args:
        structure_type: Structure type name (e.g., "swing", "trend")
        params: Structure params from Play
        swing_params: Dict with 'left' and 'right' from source swing (for dependents)

    Returns:
        Warmup bars needed

    Raises:
        KeyError: If structure type has no warmup formula
    """
    if structure_type not in STRUCTURE_WARMUP_FORMULAS:
        raise KeyError(
            f"No warmup formula for structure type '{structure_type}'. "
            f"Available: {list(STRUCTURE_WARMUP_FORMULAS.keys())}"
        )

    # Default swing params for independent structures
    if swing_params is None:
        swing_params = {"left": 5, "right": 5}

    return STRUCTURE_WARMUP_FORMULAS[structure_type](params, swing_params)


def register_structure(name: str):
    """
    Decorator to register a structure detector class.

    Validates that the class has required class attributes before
    registration. Raises TypeError if validation fails.

    Args:
        name: The structure type name (e.g., "swing", "trend", "zone").

    Returns:
        Decorator function.

    Raises:
        TypeError: If class doesn't inherit from BaseIncrementalDetector.
        TypeError: If class is missing required class attributes.
        ValueError: If name is already registered.

    Example:
        @register_structure("swing")
        class SwingDetector(BaseIncrementalDetector):
            REQUIRED_PARAMS = ["left", "right"]
            OPTIONAL_PARAMS = {}
            DEPENDS_ON = []
            ...
    """

    def decorator(cls: type["BaseIncrementalDetector"]) -> type["BaseIncrementalDetector"]:
        # Import here to avoid circular import
        from .base import BaseIncrementalDetector

        # Validate inheritance
        if not issubclass(cls, BaseIncrementalDetector):
            raise TypeError(
                f"Cannot register '{name}': class '{cls.__name__}' must inherit from BaseIncrementalDetector\n"
                f"\n"
                f"Fix:\n"
                f"  from src.structures.base import BaseIncrementalDetector\n"
                f"\n"
                f"  @register_structure('{name}')\n"
                f"  class {cls.__name__}(BaseIncrementalDetector):\n"
                f"      ..."
            )

        # Validate required class attributes exist
        required_attrs = ["REQUIRED_PARAMS", "OPTIONAL_PARAMS", "DEPENDS_ON"]
        missing_attrs = []
        for attr in required_attrs:
            if not hasattr(cls, attr):
                missing_attrs.append(attr)

        if missing_attrs:
            attr_lines = "\n".join(
                f"    {attr} = []  # or {{}}" for attr in missing_attrs
            )
            raise TypeError(
                f"Cannot register '{name}': class '{cls.__name__}' missing class attributes: {missing_attrs}\n"
                f"\n"
                f"Fix: Add to class definition:\n"
                f"{attr_lines}"
            )

        # Validate types of class attributes
        if not isinstance(cls.REQUIRED_PARAMS, list):
            raise TypeError(
                f"Cannot register '{name}': REQUIRED_PARAMS must be a list, got {type(cls.REQUIRED_PARAMS).__name__}\n"
                f"\n"
                f"Fix: REQUIRED_PARAMS = ['param1', 'param2']"
            )

        if not isinstance(cls.OPTIONAL_PARAMS, dict):
            raise TypeError(
                f"Cannot register '{name}': OPTIONAL_PARAMS must be a dict, got {type(cls.OPTIONAL_PARAMS).__name__}\n"
                f"\n"
                f"Fix: OPTIONAL_PARAMS = {{'param': default_value}}"
            )

        if not isinstance(cls.DEPENDS_ON, list):
            raise TypeError(
                f"Cannot register '{name}': DEPENDS_ON must be a list, got {type(cls.DEPENDS_ON).__name__}\n"
                f"\n"
                f"Fix: DEPENDS_ON = ['swing', 'other_dep']"
            )

        # Check for duplicate registration
        if name in STRUCTURE_REGISTRY:
            existing_cls = STRUCTURE_REGISTRY[name]
            raise ValueError(
                f"Cannot register '{name}': already registered to '{existing_cls.__name__}'\n"
                f"\n"
                f"Fix: Use a different name or unregister the existing class first."
            )

        # Register the class
        STRUCTURE_REGISTRY[name] = cls

        return cls

    return decorator


def get_structure_info(name: str) -> dict[str, Any]:
    """
    Get metadata about a registered structure type.

    Returns information about required/optional params, dependencies,
    and output keys (if determinable without instantiation).

    Args:
        name: The structure type name.

    Returns:
        Dict with keys:
            - required_params: list[str]
            - optional_params: dict[str, Any]
            - depends_on: list[str]
            - class_name: str
            - docstring: str | None

    Raises:
        KeyError: If name is not registered, with available types listed.

    Example:
        >>> info = get_structure_info("swing")
        >>> info["required_params"]
        ["left", "right"]
    """
    if name not in STRUCTURE_REGISTRY:
        available = list(STRUCTURE_REGISTRY.keys())
        available_str = ", ".join(available) if available else "(none registered)"
        raise KeyError(
            f"Structure type '{name}' not registered\n"
            f"\n"
            f"Available types: {available_str}\n"
            f"\n"
            f"Fix: Use one of the available types, or register a new detector with:\n"
            f"  @register_structure('{name}')\n"
            f"  class MyDetector(BaseIncrementalDetector):\n"
            f"      ..."
        )

    cls = STRUCTURE_REGISTRY[name]

    return {
        "required_params": list(cls.REQUIRED_PARAMS),
        "optional_params": dict(cls.OPTIONAL_PARAMS),
        "depends_on": list(cls.DEPENDS_ON),
        "class_name": cls.__name__,
        "docstring": cls.__doc__,
    }


def list_structure_types() -> list[str]:
    """
    List all registered structure type names.

    Returns:
        Sorted list of registered structure type names.

    Example:
        >>> list_structure_types()
        ["fibonacci", "rolling_window", "swing", "trend", "zone"]
    """
    return sorted(STRUCTURE_REGISTRY.keys())


def unregister_structure(name: str) -> bool:
    """
    Remove a structure type from the registry.

    Primarily useful for testing to clean up after test registrations.

    Args:
        name: The structure type name to unregister.

    Returns:
        True if the structure was removed, False if it wasn't registered.
    """
    if name in STRUCTURE_REGISTRY:
        del STRUCTURE_REGISTRY[name]
        return True
    return False


def get_structure_output_type(
    structure_type: str, field: str
) -> FeatureOutputType:
    """
    Get the output type for a structure field.

    Used by DSL to validate operator compatibility at Play load time:
    - eq operator only allowed on discrete types (INT, BOOL, ENUM)
    - near_abs/near_pct only allowed on numeric types (FLOAT, INT)

    Args:
        structure_type: Structure type name (e.g., "swing", "trend", "zone")
        field: Output field name (e.g., "high_level", "direction", "state")

    Returns:
        FeatureOutputType for the field

    Raises:
        ValueError: If structure type not found or field not found
    """
    if structure_type not in STRUCTURE_OUTPUT_TYPES:
        available = list(STRUCTURE_OUTPUT_TYPES.keys())
        raise ValueError(
            f"No output types defined for structure: '{structure_type}'. "
            f"Available: {available}"
        )

    type_map = STRUCTURE_OUTPUT_TYPES[structure_type]

    # Direct lookup first
    if field in type_map:
        return type_map[field]

    # Handle dynamic fibonacci level fields (e.g., level_0.618 -> FLOAT)
    if structure_type == "fibonacci" and field.startswith("level_"):
        return FeatureOutputType.FLOAT

    # Handle dynamic derived_zone slot fields (e.g., zone1_lower)
    # All zone slots share the same field types as zone0_*
    if structure_type == "derived_zone" and field.startswith("zone"):
        try:
            underscore_idx = field.index("_")
            slot_field = field[underscore_idx + 1:]
            canonical_key = f"zone0_{slot_field}"
            if canonical_key in type_map:
                return type_map[canonical_key]
        except (ValueError, KeyError):
            pass

    raise ValueError(
        f"Unknown field '{field}' for structure '{structure_type}'. "
        f"Available fields: {list(type_map.keys())}"
    )
