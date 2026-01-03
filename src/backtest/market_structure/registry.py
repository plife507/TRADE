"""
Structure Registry.

Single source of truth for structure types, their output schemas,
and required parameters.

Registry is contract:
- Fixed output schemas per type
- Drift triggers hard-stop
- Unknown types rejected
"""

from typing import Any, TYPE_CHECKING
from abc import ABC, abstractmethod

from src.backtest.market_structure.types import (
    StructureType,
    STRUCTURE_OUTPUT_SCHEMAS,
    STRUCTURE_REQUIRED_PARAMS,
)

if TYPE_CHECKING:
    from src.backtest.market_structure.detectors import SwingDetector, TrendClassifier


class BaseDetector(ABC):
    """
    Abstract base class for structure detectors.

    All detectors implement build_batch() for vectorized computation.
    Stage 8 adds update_on_close() for incremental streaming.
    """

    @abstractmethod
    def build_batch(
        self,
        ohlcv: dict[str, Any],  # np.ndarray values
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Compute structure features for entire dataset.

        Returns dict mapping output keys to numpy arrays.
        """
        ...

    @property
    @abstractmethod
    def output_keys(self) -> tuple[str, ...]:
        """Output key suffixes for this detector."""
        ...


# Registry entry structure
class RegistryEntry:
    """Single registry entry for a structure type."""

    def __init__(
        self,
        detector_class: type[BaseDetector] | None,
        outputs: tuple[str, ...],
        required_params: list[str],
        depends_on: list[StructureType],
    ):
        self.detector_class = detector_class  # None until implemented
        self.outputs = outputs
        self.required_params = required_params
        self.depends_on = depends_on  # Dependency ordering for builder


# Main registry - single source of truth
# Detector classes are registered lazily to avoid circular imports
STRUCTURE_REGISTRY: dict[StructureType, RegistryEntry] = {
    StructureType.SWING: RegistryEntry(
        detector_class=None,  # Populated by register_detectors()
        outputs=STRUCTURE_OUTPUT_SCHEMAS[StructureType.SWING],
        required_params=STRUCTURE_REQUIRED_PARAMS[StructureType.SWING],
        depends_on=[],  # No dependencies
    ),
    StructureType.TREND: RegistryEntry(
        detector_class=None,  # Populated by register_detectors()
        outputs=STRUCTURE_OUTPUT_SCHEMAS[StructureType.TREND],
        required_params=STRUCTURE_REQUIRED_PARAMS[StructureType.TREND],
        depends_on=[StructureType.SWING],  # Derives from swing outputs
    ),
}

_detectors_registered = False


def register_detectors() -> None:
    """
    Register detector classes into the registry.

    Called lazily to avoid circular imports.
    Safe to call multiple times (idempotent).
    """
    global _detectors_registered
    if _detectors_registered:
        return

    from src.backtest.market_structure.detectors import SwingDetector, TrendClassifier

    STRUCTURE_REGISTRY[StructureType.SWING].detector_class = SwingDetector
    STRUCTURE_REGISTRY[StructureType.TREND].detector_class = TrendClassifier
    _detectors_registered = True


def get_detector(structure_type: StructureType) -> BaseDetector:
    """
    Get detector instance for structure type.

    Lazily registers detectors on first call.
    Raises ValueError for unknown types or missing implementations.
    """
    register_detectors()

    entry = STRUCTURE_REGISTRY.get(structure_type)
    if entry is None:
        raise ValueError(f"UNKNOWN_STRUCTURE_TYPE: '{structure_type}'")
    if entry.detector_class is None:
        raise ValueError(
            f"DETECTOR_NOT_IMPLEMENTED: '{structure_type.value}' detector not registered"
        )
    return entry.detector_class()


def validate_structure_type(type_str: str) -> StructureType:
    """
    Validate structure type string.

    Raises ValueError for unknown types.
    """
    try:
        return StructureType(type_str)
    except ValueError:
        valid = [t.value for t in StructureType]
        raise ValueError(
            f"UNKNOWN_STRUCTURE_TYPE: '{type_str}'. Valid types: {valid}"
        )


def validate_structure_params(
    structure_type: StructureType,
    params: dict[str, Any],
) -> None:
    """
    Validate required params for structure type.

    Raises ValueError for missing required params.
    """
    entry = STRUCTURE_REGISTRY.get(structure_type)
    if entry is None:
        raise ValueError(f"UNKNOWN_STRUCTURE_TYPE: '{structure_type}'")

    missing = [p for p in entry.required_params if p not in params]
    if missing:
        raise ValueError(
            f"MISSING_REQUIRED_PARAM: Structure type '{structure_type.value}' "
            f"requires params {entry.required_params}, missing: {missing}"
        )


def get_structure_outputs(structure_type: StructureType) -> tuple[str, ...]:
    """
    Get output keys for structure type.

    Used for schema validation.
    """
    entry = STRUCTURE_REGISTRY.get(structure_type)
    if entry is None:
        raise ValueError(f"UNKNOWN_STRUCTURE_TYPE: '{structure_type}'")
    return entry.outputs


def validate_deprecated_keys(config: dict[str, Any], context: str = "") -> None:
    """
    Hard-fail on deprecated keys.

    Forward-only: No legacy support.
    """
    deprecated = {
        "price_inputs": "'price_inputs' removed. MARK is implicit.",
        "price_sources": "'price_sources' removed. MARK is implicit.",
        "price_refs": "'price_refs' removed. MARK is implicit.",
        "zone_blocks": "'zone_blocks' removed. Define zones inside structure blocks.",
    }

    for key, message in deprecated.items():
        if key in config:
            ctx = f" (in {context})" if context else ""
            raise ValueError(f"DEPRECATED_KEY{ctx}: {message}")


def validate_structure_block_keys(block: dict[str, Any], context: str = "") -> None:
    """
    Hard-fail on deprecated block-level keys.

    Forward-only: Use 'type' not 'structure_type'.
    """
    if "structure_type" in block:
        ctx = f" (in {context})" if context else ""
        raise ValueError(
            f"DEPRECATED_KEY{ctx}: Use 'type' not 'structure_type'."
        )
