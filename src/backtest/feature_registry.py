"""
Feature Registry: Unified registry for all features (indicators + structures).

This module provides a single source of truth for all features declared in an Play.
Features can be indicators or structures, each on a specific timeframe.

Key Concepts:
- Feature: A single indicator or structure with unique ID, on a specific TF
- FeatureRegistry: Central registry holding all features for an Play
- Features are referenced by ID in blocks (not by role like exec/high_tf/med_tf)

Design Goals:
1. Unified access: Indicators and structures share the same TF flexibility
2. No fixed TF roles: Arbitrary TFs instead of exec/med_tf/high_tf slots
3. ID-based references: Block conditions reference features by unique ID
4. O(1) lookups: Fast access by ID or by TF

Example Play:
    execution_tf: "15m"
    features:
      - id: "ema_fast"
        tf: "15m"
        type: indicator
        indicator_type: ema
        params: { length: 9 }

      - id: "swing_1h"
        tf: "1h"
        type: structure
        structure_type: swing
        params: { left: 5, right: 5 }

    blocks:
      - id: entry
        cases:
          - when:
              lhs: { feature_id: "ema_fast" }
              op: gt
              rhs: { feature_id: "ema_slow" }
            emit:
              - action: entry_long
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TYPE_CHECKING

from .rules.types import FeatureOutputType

if TYPE_CHECKING:
    from collections.abc import Iterator
    from .indicator_registry import IndicatorRegistry


class FeatureType(Enum):
    """Type of feature: indicator or structure."""
    INDICATOR = "indicator"
    STRUCTURE = "structure"


class InputSource(Enum):
    """Input source for indicators."""
    CLOSE = "close"
    OPEN = "open"
    HIGH = "high"
    LOW = "low"
    VOLUME = "volume"
    HL2 = "hl2"
    HLC3 = "hlc3"
    OHLC4 = "ohlc4"


@dataclass(frozen=True)
class Feature:
    """
    A single feature declaration with unique ID.

    Features can be indicators or structures, each on a specific TF.
    The ID is used to reference the feature in conditions.

    Attributes:
        id: Unique identifier (user-assigned, required)
        tf: Timeframe string (e.g., "15m", "1h", "4h")
        type: INDICATOR or STRUCTURE

        # For indicators
        indicator_type: Indicator type name (e.g., "ema", "rsi")
        params: Indicator parameters
        input_source: Price input (close, high, low, etc.)
        output_keys: Populated by registry for multi-output indicators

        # For structures
        structure_type: Structure type name (e.g., "swing", "trend")
        uses: Structure dependencies as list of feature keys
    """
    id: str
    tf: str
    type: FeatureType

    # Indicator fields
    indicator_type: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    input_source: InputSource = InputSource.CLOSE
    output_keys: tuple[str, ...] = field(default_factory=tuple)

    # Structure fields
    structure_type: str | None = None
    uses: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """Validate feature configuration."""
        if not self.id:
            raise ValueError("Feature id is required")
        if not self.tf:
            raise ValueError(f"Feature '{self.id}': tf is required")

        if self.type == FeatureType.INDICATOR:
            if not self.indicator_type:
                raise ValueError(
                    f"Feature '{self.id}': indicator_type is required for type=indicator"
                )
        elif self.type == FeatureType.STRUCTURE:
            if not self.structure_type:
                raise ValueError(
                    f"Feature '{self.id}': structure_type is required for type=structure"
                )

    @property
    def is_indicator(self) -> bool:
        """Check if this is an indicator feature."""
        return self.type == FeatureType.INDICATOR

    @property
    def is_structure(self) -> bool:
        """Check if this is a structure feature."""
        return self.type == FeatureType.STRUCTURE

    @property
    def primary_key(self) -> str:
        """Get the primary output key for this feature."""
        if self.is_indicator:
            # For multi-output indicators, first output_key is primary
            # For single-output, id is the key
            return self.output_keys[0] if self.output_keys else self.id
        else:
            # For structures, id is the key
            return self.id

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        result: dict[str, Any] = {
            "id": self.id,
            "tf": self.tf,
            "type": self.type.value,
        }

        if self.is_indicator:
            result["indicator_type"] = self.indicator_type
            if self.params:
                result["params"] = dict(self.params)
            if self.input_source != InputSource.CLOSE:
                result["input_source"] = self.input_source.value
        else:
            result["structure_type"] = self.structure_type
            if self.uses:
                result["uses"] = list(self.uses)
            if self.params:
                result["params"] = dict(self.params)

        return result

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Feature":
        """Create Feature from dict."""
        feature_type = FeatureType(d["type"])

        # Parse input_source
        input_source_str = d.get("input_source", "close")
        try:
            input_source = InputSource(input_source_str)
        except ValueError:
            input_source = InputSource.CLOSE

        # Parse uses field (can be string or list)
        uses_raw = d.get("uses", [])
        if isinstance(uses_raw, str):
            uses = (uses_raw,)
        else:
            uses = tuple(uses_raw)

        return cls(
            id=d["id"],
            tf=d["tf"],
            type=feature_type,
            indicator_type=d.get("indicator_type"),
            params=dict(d.get("params", {})),
            input_source=input_source,
            output_keys=tuple(d.get("output_keys", [])),
            structure_type=d.get("structure_type"),
            uses=uses,
        )


class FeatureRegistry:
    """
    Central registry of all features for an Play.

    Provides:
    - O(1) lookup by feature ID
    - TF-grouped access for engine setup
    - Validation against INDICATOR_REGISTRY and STRUCTURE_REGISTRY
    - Warmup computation per TF

    Example:
        registry = FeatureRegistry(execution_tf="15m")
        registry.add(Feature(id="ema_fast", tf="15m", type=FeatureType.INDICATOR, ...))
        registry.add(Feature(id="swing_1h", tf="1h", type=FeatureType.STRUCTURE, ...))

        # Access
        f = registry.get("ema_fast")
        tfs = registry.get_all_tfs()  # {"15m", "1h"}
        warmup = registry.get_warmup_for_tf("15m")
    """

    def __init__(self, execution_tf: str):
        """
        Initialize feature registry.

        Args:
            execution_tf: The execution timeframe (bar stepping granularity).
        """
        self._execution_tf = execution_tf
        self._features: dict[str, Feature] = {}
        self._by_tf: dict[str, list[Feature]] = {}
        self._warmup_cache: dict[str, int] = {}

    @property
    def execution_tf(self) -> str:
        """Get execution timeframe."""
        return self._execution_tf

    def add(self, feature: Feature) -> None:
        """
        Add a feature to the registry.

        Args:
            feature: Feature to add.

        Raises:
            ValueError: If feature ID already exists.
        """
        if feature.id in self._features:
            raise ValueError(
                f"Duplicate feature ID: '{feature.id}'. "
                f"Feature IDs must be unique within an Play."
            )

        self._features[feature.id] = feature

        # Index by TF
        if feature.tf not in self._by_tf:
            self._by_tf[feature.tf] = []
        self._by_tf[feature.tf].append(feature)

        # Invalidate warmup cache
        self._warmup_cache.clear()

    def get(self, feature_id: str) -> Feature:
        """
        Get feature by ID.

        Args:
            feature_id: Feature ID to look up.

        Returns:
            The Feature instance.

        Raises:
            KeyError: If feature ID not found.
        """
        if feature_id not in self._features:
            available = sorted(self._features.keys())
            raise KeyError(
                f"Unknown feature ID: '{feature_id}'. "
                f"Available features: {available}"
            )
        return self._features[feature_id]

    def get_or_none(self, feature_id: str) -> Feature | None:
        """Get feature by ID, returning None if not found."""
        return self._features.get(feature_id)

    def has(self, feature_id: str) -> bool:
        """Check if feature ID exists."""
        return feature_id in self._features

    def get_for_tf(self, tf: str) -> list[Feature]:
        """
        Get all features for a timeframe.

        Args:
            tf: Timeframe string.

        Returns:
            List of features (may be empty).
        """
        return self._by_tf.get(tf, [])

    def get_all_tfs(self) -> set[str]:
        """Get all unique timeframes."""
        return set(self._by_tf.keys())

    def get_indicators(self) -> list[Feature]:
        """Get all indicator features."""
        return [f for f in self._features.values() if f.is_indicator]

    def get_structures(self) -> list[Feature]:
        """Get all structure features."""
        return [f for f in self._features.values() if f.is_structure]

    def get_indicators_for_tf(self, tf: str) -> list[Feature]:
        """Get indicator features for a specific TF."""
        return [f for f in self.get_for_tf(tf) if f.is_indicator]

    def get_structures_for_tf(self, tf: str) -> list[Feature]:
        """Get structure features for a specific TF."""
        return [f for f in self.get_for_tf(tf) if f.is_structure]

    def all_features(self) -> list[Feature]:
        """Get all features as a list."""
        return list(self._features.values())

    def __len__(self) -> int:
        """Get number of features."""
        return len(self._features)

    def __iter__(self) -> "Iterator[Feature]":
        """Iterate over features."""
        # G6.6.2: Fix type hint FeatureConfig -> Feature
        return iter(self._features.values())

    def validate(self) -> list[str]:
        """
        Validate all features against registries.

        Returns:
            List of error messages (empty if valid).
        """
        from .indicator_registry import get_registry as get_indicator_registry
        from src.structures import STRUCTURE_REGISTRY

        errors: list[str] = []
        indicator_registry = get_indicator_registry()

        for feature in self._features.values():
            if feature.is_indicator:
                # Validate indicator type
                if not indicator_registry.is_supported(feature.indicator_type):
                    available = indicator_registry.list_indicators()
                    errors.append(
                        f"Feature '{feature.id}': unknown indicator_type '{feature.indicator_type}'. "
                        f"Available: {available}"
                    )
                else:
                    # Validate params
                    try:
                        indicator_registry.validate_params(
                            feature.indicator_type, feature.params
                        )
                    except ValueError as e:
                        errors.append(f"Feature '{feature.id}': {e}")

            elif feature.is_structure:
                # Validate structure type
                if feature.structure_type not in STRUCTURE_REGISTRY:
                    available = sorted(STRUCTURE_REGISTRY.keys())
                    errors.append(
                        f"Feature '{feature.id}': unknown structure_type '{feature.structure_type}'. "
                        f"Available: {available}"
                    )

                # Validate uses references
                for dep_key in feature.uses:
                    if dep_key not in self._features:
                        errors.append(
                            f"Feature '{feature.id}': uses '{dep_key}' which does not exist"
                        )
                    else:
                        # Check dependency is a structure
                        dep_feature = self._features[dep_key]
                        if not dep_feature.is_structure:
                            errors.append(
                                f"Feature '{feature.id}': uses '{dep_key}' which is not a structure"
                            )
                        else:
                            # Check dependency type is valid for this structure
                            if feature.structure_type in STRUCTURE_REGISTRY:
                                detector_cls = STRUCTURE_REGISTRY[feature.structure_type]
                                allowed_types = set(detector_cls.DEPENDS_ON) | set(
                                    getattr(detector_cls, "OPTIONAL_DEPS", [])
                                )
                                # "source" is an alias for "swing" in derived_zone
                                dep_type = dep_feature.structure_type
                                # Map swing->source for derived_zone compatibility
                                valid = dep_type in allowed_types or (
                                    "source" in allowed_types and dep_type == "swing"
                                )
                                if allowed_types and not valid:
                                    errors.append(
                                        f"Feature '{feature.id}': uses '{dep_key}' (type: {dep_type}) "
                                        f"but accepts: {sorted(allowed_types)}"
                                    )

        return errors

    def get_output_type(
        self, feature_id: str, field: str = "value"
    ) -> FeatureOutputType:
        """
        Get the output type for a feature field.

        Used by DSL to validate operator compatibility at Play load time:
        - eq operator only allowed on discrete types (INT, BOOL, ENUM)
        - near_abs/near_pct only allowed on numeric types (FLOAT, INT)

        Args:
            feature_id: Feature ID to look up.
            field: Output field name.
                   For single-output indicators, use "value".
                   For multi-output indicators, use the suffix (e.g., "macd", "signal").
                   For structures, use the output field (e.g., "high_level", "direction").

        Returns:
            FeatureOutputType for the field.

        Raises:
            KeyError: If feature ID not found.
            ValueError: If field not found for the feature type.

        Examples:
            >>> registry.get_output_type("ema_fast")           # Single-output indicator
            FeatureOutputType.FLOAT
            >>> registry.get_output_type("macd_1h", "signal")  # Multi-output indicator
            FeatureOutputType.FLOAT
            >>> registry.get_output_type("trend_4h", "direction")  # Structure
            FeatureOutputType.INT
        """
        feature = self.get(feature_id)  # Raises KeyError if not found

        if feature.is_indicator:
            from .indicator_registry import get_indicator_output_type
            return get_indicator_output_type(feature.indicator_type, field)

        elif feature.is_structure:
            from src.structures import get_structure_output_type
            return get_structure_output_type(feature.structure_type, field)

        else:
            raise ValueError(f"Unknown feature type for '{feature_id}'")

    def get_warmup_for_tf(self, tf: str) -> int:
        """
        Get required warmup bars for a timeframe.

        Computes the maximum warmup across all features on this TF.

        Args:
            tf: Timeframe string.

        Returns:
            Warmup bars required.
        """
        if tf in self._warmup_cache:
            return self._warmup_cache[tf]

        from .indicator_registry import get_registry as get_indicator_registry
        from src.structures import get_structure_info

        indicator_registry = get_indicator_registry()
        max_warmup = 0

        for feature in self.get_for_tf(tf):
            if feature.is_indicator:
                try:
                    warmup = indicator_registry.get_warmup_bars(
                        feature.indicator_type, feature.params
                    )
                    max_warmup = max(max_warmup, warmup)
                except (KeyError, ValueError) as e:
                    # BUG-003 fix: Specific exceptions for indicator lookup
                    # Use default warmup for unknown or misconfigured indicators
                    import logging
                    logging.getLogger(__name__).debug(
                        f"Warmup lookup failed for {feature.indicator_type}: {e}, using default"
                    )
                    max_warmup = max(max_warmup, 50)

            elif feature.is_structure:
                try:
                    info = get_structure_info(feature.structure_type)
                    # Structure warmup from params (e.g., swing: left + right + 1)
                    left = feature.params.get("left", 5)
                    right = feature.params.get("right", 5)
                    # Multiply by 5 for structure stability
                    struct_warmup = (left + right + 1) * 5
                    max_warmup = max(max_warmup, struct_warmup)
                except (KeyError, ValueError) as e:
                    # BUG-003 fix: Specific exceptions for structure lookup
                    import logging
                    logging.getLogger(__name__).debug(
                        f"Structure info lookup failed for {feature.structure_type}: {e}, using default"
                    )
                    max_warmup = max(max_warmup, 50)

        self._warmup_cache[tf] = max_warmup
        return max_warmup

    def get_max_warmup(self) -> int:
        """Get maximum warmup across all TFs."""
        return max(
            (self.get_warmup_for_tf(tf) for tf in self.get_all_tfs()),
            default=0
        )

    def expand_indicator_outputs(self) -> None:
        """
        Populate output_keys for multi-output indicators.

        Must be called after all features are added.
        Mutates features in place (creates new frozen instances).
        """
        from .indicator_registry import get_registry as get_indicator_registry

        indicator_registry = get_indicator_registry()
        updated: dict[str, Feature] = {}

        for feature_id, feature in self._features.items():
            if feature.is_indicator:
                try:
                    output_keys = indicator_registry.get_expanded_keys(
                        feature.indicator_type, feature.id
                    )
                    # Create new frozen instance with output_keys
                    updated[feature_id] = Feature(
                        id=feature.id,
                        tf=feature.tf,
                        type=feature.type,
                        indicator_type=feature.indicator_type,
                        params=feature.params,
                        input_source=feature.input_source,
                        output_keys=tuple(output_keys),
                        structure_type=feature.structure_type,
                        uses=feature.uses,
                    )
                except (KeyError, ValueError, AttributeError) as e:
                    # BUG-003 fix: Specific exceptions for indicator expansion
                    # Keep original if expansion fails (indicator may not have multi-output)
                    import logging
                    logging.getLogger(__name__).debug(
                        f"Output key expansion failed for {feature.indicator_type}: {e}"
                    )
                    updated[feature_id] = feature
            else:
                updated[feature_id] = feature

        self._features = updated
        # Rebuild by_tf index
        self._by_tf.clear()
        for feature in self._features.values():
            if feature.tf not in self._by_tf:
                self._by_tf[feature.tf] = []
            self._by_tf[feature.tf].append(feature)

    def to_dict(self) -> dict[str, Any]:
        """Convert registry to dict for serialization."""
        return {
            "execution_tf": self._execution_tf,
            "features": [f.to_dict() for f in self._features.values()],
        }

    @classmethod
    def from_features(
        cls,
        execution_tf: str,
        features: list[Feature],
    ) -> "FeatureRegistry":
        """
        Create registry from feature list.

        Args:
            execution_tf: Execution timeframe.
            features: List of Feature instances.

        Returns:
            Populated FeatureRegistry.
        """
        registry = cls(execution_tf=execution_tf)
        for feature in features:
            registry.add(feature)
        return registry

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"FeatureRegistry("
            f"execution_tf={self._execution_tf!r}, "
            f"features={len(self._features)}, "
            f"tfs={sorted(self._by_tf.keys())})"
        )
