"""
StructureBuilder - Orchestrator for market structure computation.

Responsibilities:
- Validate StructureSpec blocks for Stage 2 constraints
- Resolve dependency order (SWING before TREND)
- Compute batch outputs using registered detectors
- Map internal detector outputs to public field names
- Store results into FeedStore.structures[block_id]
- Emit manifest for auditing/debugging

Stage 2 Constraints:
- tf_role must be "exec" only (ctx support in Stage 3+)
- Required params must exist per structure type
"""

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np

from src.backtest.market_structure.spec import StructureSpec, ZoneSpec
from src.backtest.market_structure.types import (
    StructureType,
    TrendState,
    ZoneState,
    STRUCTURE_OUTPUT_MAPPINGS,
    STRUCTURE_REQUIRED_PARAMS,
    STRUCTURE_SCHEMA_VERSION,
)
from src.backtest.market_structure.registry import (
    get_detector,
    validate_structure_params,
    STRUCTURE_REGISTRY,
)


class Stage2ValidationError(ValueError):
    """Raised when Stage 2 constraints are violated."""
    pass


@dataclass
class StructureManifestEntry:
    """
    Manifest entry for a single structure block.

    Used for auditing/debugging to track what was computed.
    Serializable to JSONL for artifact storage.

    Stage 3.2: Includes schema_version and enum_labels for contract tracking.
    """
    block_key: str
    block_id: str
    spec_id: str
    type: str  # "swing" or "trend"
    tf_role: str
    params: Dict[str, Any]
    confirmation_mode: str
    confirmation_bars: int
    output_fields: List[str]
    schema_version: str = STRUCTURE_SCHEMA_VERSION
    enum_labels: Dict[str, Dict[int, str]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return asdict(self)

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), separators=(",", ":"))


@dataclass
class ZoneStore:
    """
    Storage container for a single zone's outputs.

    Contains:
    - zone_key: User-facing zone name (e.g., "demand_1")
    - zone_type: DEMAND or SUPPLY
    - fields: Dict mapping field names to numpy arrays
    """
    zone_key: str
    zone_type: str
    fields: Dict[str, np.ndarray] = field(default_factory=dict)

    def get_field(self, field_name: str, bar_idx: int) -> Optional[float]:
        """Get zone field value at specific bar index."""
        if field_name not in self.fields:
            raise ValueError(
                f"Unknown field '{field_name}' for zone '{self.zone_key}'. "
                f"Valid fields: {list(self.fields.keys())}"
            )
        arr = self.fields[field_name]
        if bar_idx < 0 or bar_idx >= len(arr):
            return None
        val = arr[bar_idx]
        if np.isnan(val) if isinstance(val, float) else False:
            return None
        return float(val) if isinstance(val, (np.floating, float)) else int(val)


@dataclass
class StructureStore:
    """
    Storage container for a single structure block's outputs.

    Contains:
    - block_id: Unique identifier for caching/artifacts
    - block_key: User-facing name (e.g., "ms_5m")
    - structure_type: SWING or TREND
    - fields: Dict mapping public field names to numpy arrays
    - zones: Dict mapping zone_key to ZoneStore (Stage 5+)
    """
    block_id: str
    block_key: str
    structure_type: StructureType
    fields: Dict[str, np.ndarray] = field(default_factory=dict)
    zones: Dict[str, ZoneStore] = field(default_factory=dict)

    def get_field(self, field_name: str, bar_idx: int) -> Optional[float]:
        """
        Get field value at specific bar index.

        Args:
            field_name: Public field name (e.g., "swing_high_level")
            bar_idx: Bar index to retrieve

        Returns:
            Field value or None if not available

        Raises:
            ValueError: If field_name is not in allowlist
        """
        if field_name not in self.fields:
            raise ValueError(
                f"Unknown field '{field_name}' for structure type '{self.structure_type.value}'. "
                f"Valid fields: {list(self.fields.keys())}"
            )
        arr = self.fields[field_name]
        if bar_idx < 0 or bar_idx >= len(arr):
            return None
        val = arr[bar_idx]
        if np.isnan(val) if isinstance(val, float) else False:
            return None
        return float(val) if isinstance(val, (np.floating, float)) else int(val)

    def get_zone_field(
        self, zone_key: str, field_name: str, bar_idx: int
    ) -> Optional[float]:
        """
        Get zone field value at specific bar index.

        Args:
            zone_key: Zone key (e.g., "demand_1")
            field_name: Field name (e.g., "lower", "state")
            bar_idx: Bar index to retrieve

        Returns:
            Field value or None if not available

        Raises:
            ValueError: If zone_key or field_name is unknown
        """
        if zone_key not in self.zones:
            raise ValueError(
                f"Unknown zone '{zone_key}' for structure block '{self.block_key}'. "
                f"Available zones: {list(self.zones.keys())}"
            )
        return self.zones[zone_key].get_field(field_name, bar_idx)

    def has_zone(self, zone_key: str) -> bool:
        """Check if zone exists."""
        return zone_key in self.zones

    def get_zone_fields(self, zone_key: str) -> List[str]:
        """Get available fields for a zone."""
        if zone_key not in self.zones:
            return []
        return list(self.zones[zone_key].fields.keys())


class StructureBuilder:
    """
    Orchestrator for market structure computation.

    Usage:
        builder = StructureBuilder()
        stores = builder.build(ohlcv, specs)
        # stores: Dict[block_id, StructureStore]
    """

    def __init__(self, stage: int = 2):
        """
        Initialize builder with stage constraints.

        Args:
            stage: Current implementation stage (default 2)
        """
        self._stage = stage

    def validate_stage2_constraints(self, specs: List[StructureSpec]) -> None:
        """
        Validate that all specs meet Stage 2 requirements.

        Stage 2 constraints:
        - tf_role must be "exec" only
        - Required params must exist

        Raises:
            Stage2ValidationError: If any constraint is violated
        """
        for spec in specs:
            # Enforce exec-only for Stage 2
            if self._stage == 2 and spec.tf_role != "exec":
                raise Stage2ValidationError(
                    f"Stage 2 requires tf_role='exec' only. "
                    f"Block '{spec.key}' has tf_role='{spec.tf_role}'. "
                    f"Context TF support is available in Stage 3+."
                )

            # Validate required params
            validate_structure_params(spec.type, spec.params)

    def _resolve_dependency_order(
        self,
        specs: List[StructureSpec]
    ) -> List[StructureSpec]:
        """
        Sort specs by dependency order.

        SWING must come before TREND.

        Args:
            specs: List of StructureSpec blocks

        Returns:
            Sorted list with dependencies first
        """
        # Group by type
        swing_specs = [s for s in specs if s.type == StructureType.SWING]
        trend_specs = [s for s in specs if s.type == StructureType.TREND]

        # SWING first, then TREND
        return swing_specs + trend_specs

    def _map_to_public_schema(
        self,
        internal_outputs: Dict[str, np.ndarray],
        structure_type: StructureType,
    ) -> Dict[str, np.ndarray]:
        """
        Map internal detector outputs to public field names.

        Args:
            internal_outputs: Dict from detector.build_batch()
            structure_type: SWING or TREND

        Returns:
            Dict with public field names as keys
        """
        mapping = STRUCTURE_OUTPUT_MAPPINGS.get(structure_type, {})
        public_outputs = {}

        for internal_key, public_key in mapping.items():
            if internal_key in internal_outputs:
                public_outputs[public_key] = internal_outputs[internal_key]

        return public_outputs

    def _build_zones(
        self,
        store: StructureStore,
        swing_outputs: Dict[str, np.ndarray],
        close_prices: np.ndarray,
        zone_specs: List["ZoneSpec"],
    ) -> None:
        """
        Build zone outputs and attach to structure store.

        Stage 5: Zones are children of SWING blocks only.

        Args:
            store: Parent StructureStore to attach zones to
            swing_outputs: Internal swing detector outputs
            close_prices: Close prices for zone break detection
            zone_specs: List of ZoneSpec from parent structure block
        """
        from src.backtest.market_structure.detectors import ZoneDetector

        zone_detector = ZoneDetector()

        for zone_spec in zone_specs:
            # Compute zone arrays
            zone_outputs = zone_detector.build_batch(
                swing_outputs=swing_outputs,
                close_prices=close_prices,
                zone_spec=zone_spec,
                atr=None,  # TODO: Pass ATR if width_model='atr_mult'
            )

            # Create zone store
            zone_store = ZoneStore(
                zone_key=zone_spec.key,
                zone_type=zone_spec.type.value,
                fields=zone_outputs,
            )

            # Attach to parent structure store
            store.zones[zone_spec.key] = zone_store

    def build(
        self,
        ohlcv: Dict[str, np.ndarray],
        specs: List[StructureSpec],
    ) -> Dict[str, StructureStore]:
        """
        Build structure outputs for all specs.

        Args:
            ohlcv: Dict with 'open', 'high', 'low', 'close', 'volume' arrays
            specs: List of StructureSpec blocks to compute

        Returns:
            Dict mapping block_id to StructureStore

        Raises:
            Stage2ValidationError: If Stage 2 constraints violated
        """
        # Validate Stage 2 constraints
        self.validate_stage2_constraints(specs)

        # Sort by dependency order
        ordered_specs = self._resolve_dependency_order(specs)

        # Store results
        stores: Dict[str, StructureStore] = {}

        # Track swing outputs for TREND dependency
        swing_outputs_cache: Dict[str, Dict[str, np.ndarray]] = {}

        for spec in ordered_specs:
            detector = get_detector(spec.type)

            if spec.type == StructureType.SWING:
                # SWING uses OHLCV directly
                internal_outputs = detector.build_batch(ohlcv, spec.params)
                # Cache for TREND
                swing_outputs_cache[spec.block_id] = internal_outputs

            elif spec.type == StructureType.TREND:
                # TREND derives from SWING
                # Find the swing block this TREND depends on
                # For Stage 2, we assume one SWING block exists
                if not swing_outputs_cache:
                    raise Stage2ValidationError(
                        f"TREND block '{spec.key}' requires SWING outputs, "
                        f"but no SWING blocks were processed."
                    )
                # Use the first (and typically only) swing outputs
                swing_outputs = list(swing_outputs_cache.values())[0]
                internal_outputs = detector.build_batch(swing_outputs, spec.params)
            else:
                raise ValueError(f"Unknown structure type: {spec.type}")

            # Map to public schema
            public_outputs = self._map_to_public_schema(internal_outputs, spec.type)

            # Create store
            store = StructureStore(
                block_id=spec.block_id,
                block_key=spec.key,
                structure_type=spec.type,
                fields=public_outputs,
            )

            # Stage 5: Compute zones if defined (SWING only)
            if spec.type == StructureType.SWING and spec.zones:
                self._build_zones(
                    store=store,
                    swing_outputs=internal_outputs,
                    close_prices=ohlcv["close"],
                    zone_specs=spec.zones,
                )

            stores[spec.block_id] = store

        return stores

    def build_key_map(self, stores: Dict[str, StructureStore]) -> Dict[str, str]:
        """
        Build block_key → block_id mapping for runtime resolution.

        Args:
            stores: Dict from build()

        Returns:
            Dict mapping block_key to block_id
        """
        return {store.block_key: block_id for block_id, store in stores.items()}

    def build_manifest(
        self,
        specs: List[StructureSpec],
        stores: Dict[str, StructureStore],
    ) -> List[StructureManifestEntry]:
        """
        Build manifest entries for all structure blocks.

        Call after build() to generate audit/debug manifest.
        Stage 3.2: Includes schema_version and enum_labels for contract tracking.

        Args:
            specs: Original StructureSpec list passed to build()
            stores: Dict returned by build()

        Returns:
            List of StructureManifestEntry for each block
        """
        manifest = []
        for spec in specs:
            store = stores.get(spec.block_id)
            if store is None:
                continue

            # Build enum labels for this structure type
            enum_labels = self._get_enum_labels_for_type(spec.type)

            entry = StructureManifestEntry(
                block_key=spec.key,
                block_id=spec.block_id,
                spec_id=spec.spec_id,
                type=spec.type.value,
                tf_role=spec.tf_role,
                params=dict(spec.params),
                confirmation_mode=spec.confirmation.mode,
                confirmation_bars=spec.confirmation.bars,
                output_fields=sorted(store.fields.keys()),
                schema_version=STRUCTURE_SCHEMA_VERSION,
                enum_labels=enum_labels,
            )
            manifest.append(entry)

        return manifest

    def _get_enum_labels_for_type(
        self,
        structure_type: StructureType,
    ) -> Dict[str, Dict[int, str]]:
        """
        Get enum label maps for a structure type.

        Returns dict mapping enum_name -> {int_value: label}.
        Used for contract tracking in manifests.
        """
        if structure_type == StructureType.TREND:
            return {
                "TrendState": {e.value: e.name for e in TrendState},
            }
        # SWING doesn't expose enum fields in public schema
        # ZoneState is for Stage 5+
        return {}

    def write_manifest(
        self,
        manifest: List[StructureManifestEntry],
        path: Union[str, Path],
    ) -> None:
        """
        Write manifest to JSONL file.

        Args:
            manifest: List from build_manifest()
            path: Output file path (typically .jsonl)
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w") as f:
            for entry in manifest:
                f.write(entry.to_json() + "\n")


def validate_stage2_exec_only(specs: List[StructureSpec]) -> None:
    """
    Standalone validator for Stage 2 exec-only constraint.

    Raises:
        Stage2ValidationError: If any spec has tf_role != "exec"
    """
    for spec in specs:
        if spec.tf_role != "exec":
            raise Stage2ValidationError(
                f"Stage 2 requires tf_role='exec' only. "
                f"Block '{spec.key}' has tf_role='{spec.tf_role}'."
            )
