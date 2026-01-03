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

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

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
from src.backtest.market_structure.zone_interaction import ZoneInteractionComputer


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
    params: dict[str, Any]
    confirmation_mode: str
    confirmation_bars: int
    output_fields: list[str]
    schema_version: str = STRUCTURE_SCHEMA_VERSION
    enum_labels: dict[str, dict[int, str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return asdict(self)

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), separators=(",", ":"), sort_keys=True)


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
    fields: dict[str, np.ndarray] = field(default_factory=dict)

    def get_field(self, field_name: str, bar_idx: int) -> float | None:
        """
        Get zone field value at specific bar index.

        Args:
            field_name: Field name (e.g., "lower", "state", "touched")
            bar_idx: Bar index to retrieve

        Returns:
            float value, or NaN for missing numeric data.
            Returns None only for out-of-bounds access.

        Raises:
            ValueError: If field_name is unknown for this zone

        Note:
            NaN is returned (not None) for missing numeric data to distinguish
            between "no data exists" (out-of-bounds → None) and "data exists but
            value is not available" (e.g., zone not active → NaN for bounds).
        """
        if field_name not in self.fields:
            raise ValueError(
                f"Unknown field '{field_name}' for zone '{self.zone_key}'. "
                f"Valid fields: {list(self.fields.keys())}"
            )
        arr = self.fields[field_name]
        if bar_idx < 0 or bar_idx >= len(arr):
            return None
        val = arr[bar_idx]
        # Return NaN as-is for missing numeric data; convert to Python float/int
        if isinstance(val, (np.floating, float)):
            return float(val)  # Preserves NaN
        return int(val)


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
    fields: dict[str, np.ndarray] = field(default_factory=dict)
    zones: dict[str, ZoneStore] = field(default_factory=dict)

    def get_field(self, field_name: str, bar_idx: int) -> float | None:
        """
        Get field value at specific bar index.

        Args:
            field_name: Public field name (e.g., "swing_high_level")
            bar_idx: Bar index to retrieve

        Returns:
            float value, or NaN for missing numeric data (no valid value at this bar).
            Returns None only for out-of-bounds access.

        Raises:
            ValueError: If field_name is not in allowlist

        Note:
            NaN is returned (not None) for missing numeric data to distinguish
            between "no data exists" (out-of-bounds → None) and "data exists but
            value is not available" (e.g., no pivot confirmed yet → NaN).
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
        # Return NaN as-is for missing numeric data; convert to Python float/int
        if isinstance(val, (np.floating, float)):
            return float(val)  # Preserves NaN
        return int(val)

    def get_zone_field(
        self, zone_key: str, field_name: str, bar_idx: int
    ) -> float | None:
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

    def get_zone_fields(self, zone_key: str) -> list[str]:
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

    def validate_stage2_constraints(self, specs: list[StructureSpec]) -> None:
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
        specs: list[StructureSpec]
    ) -> list[StructureSpec]:
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
        internal_outputs: dict[str, np.ndarray],
        structure_type: StructureType,
    ) -> dict[str, np.ndarray]:
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

    def _compute_atr_if_needed(
        self,
        ohlcv: dict[str, np.ndarray],
        zone_specs: list["ZoneSpec"],
    ) -> np.ndarray | None:
        """
        Compute ATR on-demand if any zone uses atr_mult width model.

        Args:
            ohlcv: Dict with 'high', 'low', 'close' arrays
            zone_specs: List of ZoneSpec to check

        Returns:
            ATR array if needed, None otherwise
        """
        # Check if any zone needs ATR
        atr_zones = [z for z in zone_specs if z.width_model == "atr_mult"]
        if not atr_zones:
            return None

        # Get atr_len from first zone (all atr_mult zones should use same length)
        # If different zones need different ATR lengths, they should be computed separately
        atr_len = atr_zones[0].width_params.get("atr_len", 14)

        # Import pandas-ta for ATR computation
        try:
            import pandas_ta as ta
            import pandas as pd
        except ImportError:
            raise ImportError(
                "Zone width_model='atr_mult' requires pandas-ta. "
                "Install with: pip install pandas-ta"
            )

        # Compute ATR using pandas-ta
        high = pd.Series(ohlcv["high"])
        low = pd.Series(ohlcv["low"])
        close = pd.Series(ohlcv["close"])

        atr_series = ta.atr(high, low, close, length=atr_len)
        return atr_series.to_numpy()

    def _build_zones(
        self,
        store: StructureStore,
        swing_outputs: dict[str, np.ndarray],
        ohlcv: dict[str, np.ndarray],
        zone_specs: list["ZoneSpec"],
    ) -> None:
        """
        Build zone outputs and attach to structure store.

        Stage 5: Zones are children of SWING blocks only.
        Stage 6: Computes interaction metrics (touched, inside, time_in_zone).

        ORDERING INVARIANT (locked):
        1. ZoneDetector.build_batch() → state computed (NONE → ACTIVE → BROKEN)
        2. ZoneInteractionComputer.build_batch() → metrics with state-based overrides
        3. zone_outputs.update() → merged into single dict

        This ordering ensures:
        - State is fully resolved before interaction computation
        - BROKEN bar override zeroes all metrics on same bar
        - Deterministic: same inputs → identical arrays

        Args:
            store: Parent StructureStore to attach zones to
            swing_outputs: Internal swing detector outputs
            ohlcv: Dict with 'high', 'low', 'close' arrays for interaction computation
            zone_specs: List of ZoneSpec from parent structure block
        """
        from src.backtest.market_structure.detectors import ZoneDetector

        zone_detector = ZoneDetector()
        interaction_computer = ZoneInteractionComputer()

        # Compute ATR on-demand if any zone uses atr_mult
        atr = self._compute_atr_if_needed(ohlcv, zone_specs)

        for zone_spec in zone_specs:
            # Compute zone arrays (lower, upper, state, recency, parent_anchor_id, instance_id)
            zone_outputs = zone_detector.build_batch(
                swing_outputs=swing_outputs,
                close_prices=ohlcv["close"],
                zone_spec=zone_spec,
                atr=atr,
            )

            # Stage 6: Compute interaction metrics
            interaction_outputs = interaction_computer.build_batch(
                zone_outputs=zone_outputs,
                bar_high=ohlcv["high"],
                bar_low=ohlcv["low"],
                bar_close=ohlcv["close"],
            )

            # Merge interaction outputs into zone_outputs
            zone_outputs.update(interaction_outputs)

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
        ohlcv: dict[str, np.ndarray],
        specs: list[StructureSpec],
    ) -> dict[str, StructureStore]:
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
        stores: dict[str, StructureStore] = {}

        # Track swing outputs for TREND dependency
        swing_outputs_cache: dict[str, dict[str, np.ndarray]] = {}

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
                if not swing_outputs_cache:
                    raise Stage2ValidationError(
                        f"TREND block '{spec.key}' requires SWING outputs, "
                        f"but no SWING blocks were processed."
                    )

                # P1-12 fix: Use explicit depends_on_swing if specified
                if spec.depends_on_swing:
                    # Find the specified SWING block by key
                    swing_key = spec.depends_on_swing
                    matching_block_ids = [
                        block_id for block_id, _ in swing_outputs_cache.items()
                        if any(s.key == swing_key and s.block_id == block_id for s in specs if s.type == StructureType.SWING)
                    ]
                    if not matching_block_ids:
                        available_swings = [s.key for s in specs if s.type == StructureType.SWING]
                        raise Stage2ValidationError(
                            f"TREND block '{spec.key}' depends on SWING block '{swing_key}', "
                            f"but no SWING block with that key was found. "
                            f"Available SWING blocks: {available_swings}"
                        )
                    swing_outputs = swing_outputs_cache[matching_block_ids[0]]
                else:
                    # Fallback: use first SWING block (backward compatible, with warning behavior)
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
            # Stage 6: Zone interaction uses exec-bar OHLC
            if spec.type == StructureType.SWING and spec.zones:
                self._build_zones(
                    store=store,
                    swing_outputs=internal_outputs,
                    ohlcv=ohlcv,
                    zone_specs=spec.zones,
                )

            stores[spec.block_id] = store

        return stores

    def build_key_map(self, stores: dict[str, StructureStore]) -> dict[str, str]:
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
        specs: list[StructureSpec],
        stores: dict[str, StructureStore],
    ) -> list[StructureManifestEntry]:
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
    ) -> dict[str, dict[int, str]]:
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
        manifest: list[StructureManifestEntry],
        path: str | Path,
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


def validate_stage2_exec_only(specs: list[StructureSpec]) -> None:
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
