"""
System Dataclass and Loader.

A System is the top-level trading configuration that combines:
- One or more Plays with allocation weights
- Regime-based weight adjustments
- Risk profile configuration
- Target deployment mode

Architecture Principle: Pure Data
- System is an immutable dataclass
- load_system is a pure function (id -> System)
- No side effects, no state

Hierarchy: Block → Play → System
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# Default systems directory
DEFAULT_SYSTEMS_DIR = Path("strategies/systems")


class SystemNotFoundError(Exception):
    """Raised when a system cannot be found."""

    def __init__(self, system_id: str, searched_paths: list[Path] | None = None):
        self.system_id = system_id
        self.searched_paths = searched_paths or []
        paths_str = ", ".join(str(p) for p in self.searched_paths)
        super().__init__(f"System '{system_id}' not found. Searched: {paths_str}")


@dataclass(frozen=True)
class RegimeWeight:
    """
    Regime-based weight adjustment.

    When the condition is true, the base_weight is multiplied by the multiplier.

    Attributes:
        condition: DSL condition that triggers this adjustment
        multiplier: Multiplier to apply when condition is true (e.g., 1.5 = boost 50%)
    """

    condition: dict[str, Any]
    multiplier: float = 1.0

    def __post_init__(self):
        """Validate the regime weight."""
        if self.multiplier <= 0:
            raise ValueError(f"RegimeWeight: multiplier must be positive, got {self.multiplier}")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "condition": self.condition,
            "multiplier": self.multiplier,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RegimeWeight:
        """Create RegimeWeight from dictionary."""
        return cls(
            condition=d["condition"],
            multiplier=d.get("multiplier", 1.0),
        )


@dataclass(frozen=True)
class PlayRef:
    """
    A reference to a Play within a System.

    Supports weighted blending with regime-based adjustments:
    - base_weight: Always applied allocation (0.0-1.0)
    - regime_weight: Optional adjustment when condition is true

    Attributes:
        play_id: The ID of the Play (without .yml extension)
        base_weight: Base allocation weight (0.0-1.0)
        enabled: Whether this play is active (default True)
        regime_weight: Optional regime-based weight adjustment
    """

    play_id: str
    base_weight: float = 1.0
    enabled: bool = True
    regime_weight: RegimeWeight | None = None

    def __post_init__(self):
        """Validate the reference."""
        if not self.play_id:
            raise ValueError("PlayRef: play_id is required")
        if not (0.0 <= self.base_weight <= 1.0):
            raise ValueError(f"PlayRef: base_weight must be 0.0-1.0, got {self.base_weight}")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        d: dict[str, Any] = {"play_id": self.play_id}
        if self.base_weight != 1.0:
            d["base_weight"] = self.base_weight
        if not self.enabled:
            d["enabled"] = self.enabled
        if self.regime_weight is not None:
            d["regime_weight"] = self.regime_weight.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PlayRef:
        """Create PlayRef from dictionary."""
        regime_weight = None
        if "regime_weight" in d:
            regime_weight = RegimeWeight.from_dict(d["regime_weight"])

        return cls(
            play_id=d["play_id"],
            base_weight=d.get("base_weight", d.get("weight", 1.0)),  # Accept both for migration
            enabled=d.get("enabled", True),
            regime_weight=regime_weight,
        )


@dataclass(frozen=True)
class System:
    """
    Complete trading system configuration.

    A System represents a production-ready trading configuration that has
    been validated through the Forge workflow. It combines one or more
    Plays with risk and deployment configuration.

    Supports weighted blending:
    - Multiple plays can be active simultaneously
    - Each play has base_weight (always applied)
    - Optional regime_weight.multiplier adjusts weight when condition is true
    - Final weights are normalized to sum ≤ 1.0

    Attributes:
        id: Unique identifier (e.g., "btc_trend_v1")
        version: Semantic version string
        name: Human-readable name
        description: Optional description
        plays: Tuple of PlayRef objects
        risk_profile: Risk configuration dict
        regime_features: Features for regime detection (optional)
        mode: Target mode ("backtest", "demo", "live")
        tags: Tags for categorization

    Example YAML:
        id: btc_trend_v1
        version: "1.0.0"
        name: "BTC Trend System v1"
        mode: backtest
        plays:
          - play_id: ema_trend_v1
            base_weight: 0.6
            regime_weight:
              condition:
                all:
                  - ["atr_14", ">", 100]
              multiplier: 1.5
          - play_id: mean_reversion_v1
            base_weight: 0.4
        regime_features:
          atr_14:
            indicator: atr
            params: { length: 14 }
        risk_profile:
          initial_capital_usdt: 10000
          max_drawdown_pct: 20.0
        tags:
          - production
          - btc
    """

    # Identity
    id: str
    version: str
    name: str | None = None
    description: str | None = None

    # Plays in this system (replaces playbooks)
    plays: tuple[PlayRef, ...] = field(default_factory=tuple)

    # Risk profile (flexible dict for now, can be typed later)
    risk_profile: dict[str, Any] = field(default_factory=dict)

    # Features for regime detection (optional)
    regime_features: dict[str, Any] = field(default_factory=dict)

    # Target mode: backtest, demo, live
    mode: str = "backtest"

    # Tags for categorization
    tags: tuple[str, ...] = field(default_factory=tuple)

    # Valid modes
    _VALID_MODES = ("backtest", "demo", "live")

    def __post_init__(self):
        """Validate the system."""
        errors = self.validate()
        if errors:
            raise ValueError(f"Invalid System '{self.id}': {'; '.join(errors)}")

    def validate(self) -> list[str]:
        """Validate the system configuration."""
        errors = []

        if not self.id:
            errors.append("id is required")
        if not self.version:
            errors.append("version is required")
        if not self.plays:
            errors.append("at least one play is required")
        if self.mode not in self._VALID_MODES:
            errors.append(f"mode must be one of {self._VALID_MODES}, got '{self.mode}'")

        # Check for duplicate play_ids
        play_ids = [r.play_id for r in self.plays]
        if len(play_ids) != len(set(play_ids)):
            errors.append("duplicate play_id entries found")

        return errors

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        d = {
            "id": self.id,
            "version": self.version,
            "mode": self.mode,
            "plays": [r.to_dict() for r in self.plays],
        }
        if self.name:
            d["name"] = self.name
        if self.description:
            d["description"] = self.description
        if self.risk_profile:
            d["risk_profile"] = self.risk_profile
        if self.regime_features:
            d["regime_features"] = self.regime_features
        if self.tags:
            d["tags"] = list(self.tags)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> System:
        """Create System from dictionary."""
        # Support both 'plays' (new) and 'playbooks' (legacy migration)
        plays_data = d.get("plays", d.get("playbooks", []))
        plays = tuple(PlayRef.from_dict(r) for r in plays_data)

        return cls(
            id=d["id"],
            version=d["version"],
            name=d.get("name"),
            description=d.get("description"),
            plays=plays,
            risk_profile=d.get("risk_profile", {}),
            regime_features=d.get("regime_features", {}),
            mode=d.get("mode", "backtest"),
            tags=tuple(d.get("tags", [])),
        )

    def get_play_ids(self) -> list[str]:
        """Get list of all play IDs in this system."""
        return [r.play_id for r in self.plays]

    def get_enabled_plays(self) -> list[PlayRef]:
        """Get list of enabled play refs."""
        return [r for r in self.plays if r.enabled]

    def get_total_base_weight(self) -> float:
        """Get sum of base weights for enabled plays."""
        return sum(r.base_weight for r in self.plays if r.enabled)


def load_system(
    system_id: str,
    systems_dir: Path | str | None = None,
) -> System:
    """
    Load a System from YAML file.

    Pure function: (system_id, dir) -> System

    Args:
        system_id: System identifier (filename without .yml)
        systems_dir: Directory containing system YAML files

    Returns:
        System dataclass instance

    Raises:
        SystemNotFoundError: If system file not found
        ValueError: If system YAML is invalid
    """
    if systems_dir is None:
        systems_dir = DEFAULT_SYSTEMS_DIR
    else:
        systems_dir = Path(systems_dir)

    # Search in main dir and _validation subdirectory
    search_paths = [
        systems_dir / f"{system_id}.yml",
        systems_dir / "_validation" / f"{system_id}.yml",
    ]

    yaml_path = None
    for path in search_paths:
        if path.exists():
            yaml_path = path
            break

    if yaml_path is None:
        raise SystemNotFoundError(system_id, search_paths)

    # Load and parse YAML
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if data is None:
        raise ValueError(f"System file is empty: {yaml_path}")

    # Create System from dict
    return System.from_dict(data)


def list_systems(systems_dir: Path | str | None = None) -> list[str]:
    """
    List all available system IDs.

    Args:
        systems_dir: Directory containing system YAML files

    Returns:
        List of system IDs (filenames without .yml extension)
    """
    if systems_dir is None:
        systems_dir = DEFAULT_SYSTEMS_DIR
    else:
        systems_dir = Path(systems_dir)

    if not systems_dir.exists():
        return []

    return sorted([
        p.stem for p in systems_dir.glob("*.yml")
        if not p.stem.startswith("_")  # Skip files starting with underscore
    ])


def save_system(
    system: System,
    systems_dir: Path | str | None = None,
) -> Path:
    """
    Save a System to YAML file.

    Args:
        system: System to save
        systems_dir: Directory to save to

    Returns:
        Path to saved file
    """
    if systems_dir is None:
        systems_dir = DEFAULT_SYSTEMS_DIR
    else:
        systems_dir = Path(systems_dir)

    systems_dir.mkdir(parents=True, exist_ok=True)

    yaml_path = systems_dir / f"{system.id}.yml"

    with open(yaml_path, "w", encoding="utf-8", newline="\n") as f:
        yaml.dump(
            system.to_dict(),
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

    return yaml_path
