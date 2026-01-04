"""
System Dataclass and Loader.

A System is the top-level trading configuration that combines:
- One or more Playbooks with allocation weights
- Risk profile configuration
- Target deployment mode

Architecture Principle: Pure Data
- System is an immutable dataclass
- load_system is a pure function (id -> System)
- No side effects, no state
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# Default systems directory
DEFAULT_SYSTEMS_DIR = Path("configs/systems")


class SystemNotFoundError(Exception):
    """Raised when a system cannot be found."""

    def __init__(self, system_id: str, searched_paths: list[Path] | None = None):
        self.system_id = system_id
        self.searched_paths = searched_paths or []
        paths_str = ", ".join(str(p) for p in self.searched_paths)
        super().__init__(f"System '{system_id}' not found. Searched: {paths_str}")


@dataclass(frozen=True)
class PlaybookRef:
    """
    A reference to a Playbook within a System.

    Attributes:
        playbook_id: The ID of the Playbook (without .yml extension)
        weight: Allocation weight (0.0-1.0)
        enabled: Whether this playbook is active (default True)
    """

    playbook_id: str
    weight: float = 1.0
    enabled: bool = True

    def __post_init__(self):
        """Validate the reference."""
        if not self.playbook_id:
            raise ValueError("PlaybookRef: playbook_id is required")
        if not (0.0 <= self.weight <= 1.0):
            raise ValueError(f"PlaybookRef: weight must be 0.0-1.0, got {self.weight}")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        d: dict[str, Any] = {"playbook_id": self.playbook_id}
        if self.weight != 1.0:
            d["weight"] = self.weight
        if not self.enabled:
            d["enabled"] = self.enabled
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PlaybookRef:
        """Create PlaybookRef from dictionary."""
        return cls(
            playbook_id=d["playbook_id"],
            weight=d.get("weight", 1.0),
            enabled=d.get("enabled", True),
        )


@dataclass(frozen=True)
class System:
    """
    Complete trading system configuration.

    A System represents a production-ready trading configuration that has
    been validated through the Forge workflow. It combines one or more
    Playbooks with risk and deployment configuration.

    Attributes:
        id: Unique identifier (e.g., "btc_trend_v1")
        version: Semantic version string
        name: Human-readable name
        description: Optional description
        playbooks: Tuple of PlaybookRef objects
        risk_profile: Risk configuration dict
        mode: Target mode ("backtest", "demo", "live")
        tags: Tags for categorization

    Example YAML:
        id: btc_trend_v1
        version: "1.0.0"
        name: "BTC Trend System v1"
        description: "Production trend following system for BTCUSDT"
        mode: backtest
        playbooks:
          - playbook_id: trend_following
            weight: 0.8
          - playbook_id: mean_reversion
            weight: 0.2
            enabled: false
        risk_profile:
          initial_capital: 10000
          max_drawdown_pct: 20.0
          risk_per_trade_pct: 1.0
        tags:
          - production
          - btc
    """

    # Identity
    id: str
    version: str
    name: str | None = None
    description: str | None = None

    # Playbooks in this system
    playbooks: tuple[PlaybookRef, ...] = field(default_factory=tuple)

    # Risk profile (flexible dict for now, can be typed later)
    risk_profile: dict[str, Any] = field(default_factory=dict)

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
        if not self.playbooks:
            errors.append("at least one playbook is required")
        if self.mode not in self._VALID_MODES:
            errors.append(f"mode must be one of {self._VALID_MODES}, got '{self.mode}'")

        # Check for duplicate playbook_ids
        playbook_ids = [r.playbook_id for r in self.playbooks]
        if len(playbook_ids) != len(set(playbook_ids)):
            errors.append("duplicate playbook_id entries found")

        return errors

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        d = {
            "id": self.id,
            "version": self.version,
            "mode": self.mode,
            "playbooks": [r.to_dict() for r in self.playbooks],
        }
        if self.name:
            d["name"] = self.name
        if self.description:
            d["description"] = self.description
        if self.risk_profile:
            d["risk_profile"] = self.risk_profile
        if self.tags:
            d["tags"] = list(self.tags)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> System:
        """Create System from dictionary."""
        playbooks_data = d.get("playbooks", [])
        playbooks = tuple(PlaybookRef.from_dict(r) for r in playbooks_data)

        return cls(
            id=d["id"],
            version=d["version"],
            name=d.get("name"),
            description=d.get("description"),
            playbooks=playbooks,
            risk_profile=d.get("risk_profile", {}),
            mode=d.get("mode", "backtest"),
            tags=tuple(d.get("tags", [])),
        )

    def get_playbook_ids(self) -> list[str]:
        """Get list of all playbook IDs in this system."""
        return [r.playbook_id for r in self.playbooks]

    def get_enabled_playbooks(self) -> list[PlaybookRef]:
        """Get list of enabled playbook refs."""
        return [r for r in self.playbooks if r.enabled]

    def get_total_weight(self) -> float:
        """Get sum of weights for enabled playbooks."""
        return sum(r.weight for r in self.playbooks if r.enabled)


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

    # Try to find the system file
    yaml_path = systems_dir / f"{system_id}.yml"

    if not yaml_path.exists():
        raise SystemNotFoundError(system_id, [yaml_path])

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
