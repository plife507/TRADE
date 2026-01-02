"""
Market Structure Specifications.

Dataclasses for structure blocks and zones with spec_id computation.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal
import hashlib
import json

from src.backtest.market_structure.types import StructureType, ZoneType


@dataclass(frozen=True)
class ConfirmationConfig:
    """
    Confirmation semantics for structure detection.

    - bar_count: Pending for N bars, then confirmed if not invalidated
    - price_break: Pending until price breaks past (confirmed) or invalidates (failed)
    - immediate: No confirmation needed
    """

    mode: Literal["bar_count", "price_break", "immediate"]
    bars: int = 0  # Required for bar_count mode

    def __post_init__(self) -> None:
        if self.mode == "bar_count" and self.bars <= 0:
            raise ValueError(
                f"ConfirmationConfig: mode='bar_count' requires bars > 0, got {self.bars}"
            )

    def to_canonical_dict(self) -> Dict[str, Any]:
        """Canonical dict for hashing."""
        return {"mode": self.mode, "bars": self.bars}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for YAML serialization."""
        return {"mode": self.mode, "bars": self.bars}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ConfirmationConfig":
        """Create from dict."""
        return cls(
            mode=d.get("mode", "immediate"),
            bars=d.get("bars", 0),
        )


@dataclass(frozen=True)
class ZoneSpec:
    """
    Zone specification (child of structure block).

    Zones are parent-scoped:
    - Access via: structure.<parent_key>.zones.<zone_key>.*
    - Reset when parent structure advances
    - No standalone zone.* namespace
    """

    key: str  # User-facing name ("demand_1")
    type: ZoneType  # demand, supply
    width_model: Literal["atr_mult", "percent", "fixed"]
    width_params: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.key:
            raise ValueError("ZoneSpec: key is required")
        if self.width_model == "atr_mult":
            if "atr_len" not in self.width_params or "mult" not in self.width_params:
                raise ValueError(
                    "ZoneSpec: width_model='atr_mult' requires atr_len and mult in width_params"
                )
        elif self.width_model == "percent":
            if "pct" not in self.width_params:
                raise ValueError(
                    "ZoneSpec: width_model='percent' requires pct in width_params"
                )
        elif self.width_model == "fixed":
            if "width" not in self.width_params:
                raise ValueError(
                    "ZoneSpec: width_model='fixed' requires width in width_params"
                )

    def to_canonical_dict(self) -> Dict[str, Any]:
        """Canonical dict for hashing."""
        return {
            "key": self.key,
            "type": self.type.value,
            "width_model": self.width_model,
            "width_params": dict(sorted(self.width_params.items())),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for YAML serialization."""
        return {
            "key": self.key,
            "type": self.type.value,
            "width_model": self.width_model,
            "width_params": dict(self.width_params),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ZoneSpec":
        """Create from dict."""
        return cls(
            key=d["key"],
            type=ZoneType(d["type"]),
            width_model=d["width_model"],
            width_params=d.get("width_params", {}),
        )


@dataclass(frozen=True)
class StructureSpec:
    """
    Structure block specification.

    Defines a market structure detector with optional child zones.

    IdeaCard YAML key is 'type', not 'structure_type' (hard-fail on old key).
    """

    key: str  # User-facing name ("ms_5m")
    type: StructureType  # swing, trend
    tf_role: str  # "exec" or "ctx"
    params: Dict[str, Any]  # Explicit, no defaults
    confirmation: ConfirmationConfig
    zones: List[ZoneSpec] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.key:
            raise ValueError("StructureSpec: key is required")
        if self.tf_role not in ("exec", "ctx"):
            raise ValueError(
                f"StructureSpec: tf_role must be 'exec' or 'ctx', got '{self.tf_role}'"
            )

    @property
    def spec_id(self) -> str:
        """
        Structure math identity hash.

        Includes: type, params, confirmation.
        Excludes: zones, key, tf_role.

        Pure structure detection identity. Zones are a derived layer
        with their own identity (zone_spec_id). This allows structure
        engine to stabilize while zones iterate.
        """
        canonical = {
            "type": self.type.value,
            "params": dict(sorted(self.params.items())),
            "confirmation": self.confirmation.to_canonical_dict(),
        }
        json_str = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(json_str.encode()).hexdigest()[:12]

    @property
    def zone_spec_id(self) -> str:
        """
        Zone layer identity hash.

        Includes: zones only.
        Returns empty string if no zones defined.

        Separate from spec_id so zone iteration doesn't invalidate
        structure caches.
        """
        if not self.zones:
            return ""
        canonical = {"zones": [z.to_canonical_dict() for z in self.zones]}
        json_str = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(json_str.encode()).hexdigest()[:12]

    @property
    def block_id(self) -> str:
        """
        Structure placement identity hash.

        Includes: spec_id + key + tf_role.
        Excludes: zones.

        Use for structure storage keys, artifact names, caching.
        """
        canonical = {
            "spec_id": self.spec_id,
            "key": self.key,
            "tf_role": self.tf_role,
        }
        json_str = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(json_str.encode()).hexdigest()[:12]

    @property
    def zone_block_id(self) -> str:
        """
        Full placement identity including zones.

        Includes: block_id + zone_spec_id.
        Returns block_id if no zones defined.

        Use for zone storage keys when zones are active.
        """
        if not self.zones:
            return self.block_id
        canonical = {
            "block_id": self.block_id,
            "zone_spec_id": self.zone_spec_id,
        }
        json_str = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(json_str.encode()).hexdigest()[:12]

    def to_canonical_dict(self) -> Dict[str, Any]:
        """Full canonical dict for debugging/logging."""
        result = {
            "key": self.key,
            "type": self.type.value,
            "tf_role": self.tf_role,
            "params": dict(sorted(self.params.items())),
            "confirmation": self.confirmation.to_canonical_dict(),
            "zones": [z.to_canonical_dict() for z in self.zones],
            "spec_id": self.spec_id,
            "block_id": self.block_id,
        }
        # Include zone IDs only if zones exist
        if self.zones:
            result["zone_spec_id"] = self.zone_spec_id
            result["zone_block_id"] = self.zone_block_id
        return result

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for YAML serialization."""
        result = {
            "key": self.key,
            "type": self.type.value,
            "tf_role": self.tf_role,
            "params": dict(self.params),
            "confirmation": self.confirmation.to_dict(),
        }
        if self.zones:
            result["zones"] = [z.to_dict() for z in self.zones]
        return result

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "StructureSpec":
        """
        Create from dict (YAML parsing).

        Stage 5: Zones are now supported for SWING blocks only.

        Hard-fail on:
        - 'structure_type' key (legacy, use 'type')
        - zones on non-SWING blocks
        """
        # Hard-fail on legacy key
        if "structure_type" in d:
            raise ValueError(
                "IdeaCard uses 'type', not 'structure_type' for market_structure_blocks. "
                "Replace 'structure_type' with 'type' in your YAML."
            )

        # Validate required fields
        if "key" not in d:
            raise ValueError("StructureSpec: 'key' is required")
        if "type" not in d:
            raise ValueError("StructureSpec: 'type' is required")

        # Parse type
        type_str = d["type"]
        try:
            struct_type = StructureType(type_str)
        except ValueError:
            valid_types = [t.value for t in StructureType]
            raise ValueError(
                f"StructureSpec: unknown type '{type_str}'. "
                f"Valid types: {valid_types}"
            )

        # Parse params
        params = d.get("params", {})
        if not isinstance(params, dict):
            raise ValueError(f"StructureSpec: 'params' must be a dict, got {type(params).__name__}")

        # Parse confirmation (default to immediate if not specified)
        conf_dict = d.get("confirmation", {"mode": "immediate", "bars": 0})
        confirmation = ConfirmationConfig.from_dict(conf_dict)

        # Parse tf_role (default to exec)
        tf_role = d.get("tf_role", "exec")

        # Parse zones (Stage 5+, SWING blocks only)
        zones: List[ZoneSpec] = []
        zones_raw = d.get("zones", [])
        if zones_raw:
            # Validate zones are only on SWING blocks
            if struct_type != StructureType.SWING:
                raise ValueError(
                    f"Zones are only supported for SWING structure blocks, "
                    f"not '{struct_type.value}'. "
                    f"Remove 'zones' from block '{d.get('key', '?')}'."
                )
            for zone_dict in zones_raw:
                zones.append(ZoneSpec.from_dict(zone_dict))

            # Stage 5.1: Validate no duplicate zone keys within block
            zone_keys = [z.key for z in zones]
            seen = set()
            duplicates = []
            for zk in zone_keys:
                if zk in seen:
                    duplicates.append(zk)
                seen.add(zk)
            if duplicates:
                raise ValueError(
                    f"Duplicate zone key(s) in structure block '{d.get('key', '?')}': "
                    f"{duplicates}. Zone keys must be unique within a block."
                )

        return cls(
            key=d["key"],
            type=struct_type,
            tf_role=tf_role,
            params=params,
            confirmation=confirmation,
            zones=zones,
        )


def compute_spec_id(
    structure_type: str,
    params: Dict[str, Any],
    confirmation: Dict[str, Any],
) -> str:
    """
    Compute spec_id from raw dict data (for parsing).

    Same algorithm as StructureSpec.spec_id but works with dicts.

    IMPORTANT: spec_id EXCLUDES zones. Zones have separate zone_spec_id.
    This allows structure engine to stabilize while zones iterate.
    """
    canonical = {
        "type": structure_type,
        "params": dict(sorted(params.items())),
        "confirmation": {
            "mode": confirmation.get("mode", "immediate"),
            "bars": confirmation.get("bars", 0),
        },
    }
    json_str = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(json_str.encode()).hexdigest()[:12]


def compute_zone_spec_id(zones: List[Dict[str, Any]]) -> str:
    """
    Compute zone_spec_id from raw dict data (for parsing).

    Same algorithm as StructureSpec.zone_spec_id but works with dicts.
    Returns empty string if no zones.
    """
    if not zones:
        return ""
    canonical = {
        "zones": sorted(
            [
                {
                    "key": z.get("key", ""),
                    "type": z.get("type", ""),
                    "width_model": z.get("width_model", ""),
                    "width_params": dict(sorted(z.get("width_params", {}).items())),
                }
                for z in zones
            ],
            key=lambda x: x["key"],
        ),
    }
    json_str = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(json_str.encode()).hexdigest()[:12]


def compute_block_id(spec_id: str, key: str, tf_role: str) -> str:
    """
    Compute block_id from spec_id + key + tf_role.

    Same algorithm as StructureSpec.block_id but works with primitives.
    """
    canonical = {
        "spec_id": spec_id,
        "key": key,
        "tf_role": tf_role,
    }
    json_str = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(json_str.encode()).hexdigest()[:12]


def compute_zone_block_id(block_id: str, zone_spec_id: str) -> str:
    """
    Compute zone_block_id from block_id + zone_spec_id.

    Same algorithm as StructureSpec.zone_block_id but works with primitives.
    Returns block_id if zone_spec_id is empty.
    """
    if not zone_spec_id:
        return block_id
    canonical = {
        "block_id": block_id,
        "zone_spec_id": zone_spec_id,
    }
    json_str = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(json_str.encode()).hexdigest()[:12]
