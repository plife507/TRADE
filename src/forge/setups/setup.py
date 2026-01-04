"""
Setup Dataclass and Loader.

Setups are reusable market condition blocks that define:
- Features (indicators/structures) they require
- A condition expression that defines when the setup is active

Setups can be referenced from Play blocks using:
    - setup: <setup_id>

Architecture Principle: Pure Data
- Setup is an immutable dataclass
- load_setup is a pure function (id -> Setup)
- No side effects, no state
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# Default setups directory
DEFAULT_SETUPS_DIR = Path("configs/setups")


class SetupNotFoundError(Exception):
    """Raised when a setup cannot be found."""

    def __init__(self, setup_id: str, searched_paths: list[Path] | None = None):
        self.setup_id = setup_id
        self.searched_paths = searched_paths or []
        paths_str = ", ".join(str(p) for p in self.searched_paths)
        super().__init__(f"Setup '{setup_id}' not found. Searched: {paths_str}")


@dataclass(frozen=True)
class Setup:
    """
    A reusable market condition block.

    Setups encapsulate common trading patterns and conditions that can be
    composed into Plays. They define what features they need and when
    they are considered "active".

    Attributes:
        id: Unique identifier (e.g., "rsi_oversold", "ema_pullback")
        version: Semantic version string
        name: Human-readable name
        description: Optional description of the setup
        features: Tuple of feature dicts (indicators/structures this setup needs)
        condition: DSL condition dict that defines when setup is active

    Example YAML:
        id: rsi_oversold
        version: "1.0.0"
        name: "RSI Oversold"
        description: "RSI below 30 threshold"
        features:
          - id: rsi
            type: indicator
            indicator_type: rsi
            params: {length: 14}
        condition:
          lhs: {feature_id: rsi}
          op: lt
          rhs: 30
    """

    # Identity
    id: str
    version: str
    name: str | None = None
    description: str | None = None

    # Features this setup requires
    features: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    # Condition for when setup is active (DSL expression)
    condition: dict[str, Any] = field(default_factory=dict)

    # Tags for categorization
    tags: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self):
        """Validate the setup."""
        errors = self.validate()
        if errors:
            raise ValueError(f"Invalid Setup '{self.id}': {'; '.join(errors)}")

    def validate(self) -> list[str]:
        """Validate the setup configuration."""
        errors = []

        if not self.id:
            errors.append("id is required")
        if not self.version:
            errors.append("version is required")
        if not self.condition:
            errors.append("condition is required")

        return errors

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        d = {
            "id": self.id,
            "version": self.version,
            "features": list(self.features),
            "condition": self.condition,
        }
        if self.name:
            d["name"] = self.name
        if self.description:
            d["description"] = self.description
        if self.tags:
            d["tags"] = list(self.tags)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Setup:
        """Create Setup from dictionary."""
        return cls(
            id=d["id"],
            version=d["version"],
            name=d.get("name"),
            description=d.get("description"),
            features=tuple(d.get("features", [])),
            condition=d.get("condition", {}),
            tags=tuple(d.get("tags", [])),
        )

    def get_feature_ids(self) -> set[str]:
        """Get set of feature IDs this setup requires."""
        return {f["id"] for f in self.features if "id" in f}


def load_setup(
    setup_id: str,
    setups_dir: Path | str | None = None,
) -> Setup:
    """
    Load a Setup from YAML file.

    Pure function: (setup_id, dir) -> Setup

    Args:
        setup_id: Setup identifier (filename without .yml)
        setups_dir: Directory containing setup YAML files

    Returns:
        Setup dataclass instance

    Raises:
        SetupNotFoundError: If setup file not found
        ValueError: If setup YAML is invalid
    """
    if setups_dir is None:
        setups_dir = DEFAULT_SETUPS_DIR
    else:
        setups_dir = Path(setups_dir)

    # Try to find the setup file
    yaml_path = setups_dir / f"{setup_id}.yml"

    if not yaml_path.exists():
        raise SetupNotFoundError(setup_id, [yaml_path])

    # Load and parse YAML
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if data is None:
        raise ValueError(f"Setup file is empty: {yaml_path}")

    # Create Setup from dict
    return Setup.from_dict(data)


def list_setups(setups_dir: Path | str | None = None) -> list[str]:
    """
    List all available setup IDs.

    Args:
        setups_dir: Directory containing setup YAML files

    Returns:
        List of setup IDs (filenames without .yml extension)
    """
    if setups_dir is None:
        setups_dir = DEFAULT_SETUPS_DIR
    else:
        setups_dir = Path(setups_dir)

    if not setups_dir.exists():
        return []

    return sorted([
        p.stem for p in setups_dir.glob("*.yml")
        if not p.stem.startswith("_")  # Skip files starting with underscore
    ])


def save_setup(
    setup: Setup,
    setups_dir: Path | str | None = None,
) -> Path:
    """
    Save a Setup to YAML file.

    Args:
        setup: Setup to save
        setups_dir: Directory to save to

    Returns:
        Path to saved file
    """
    if setups_dir is None:
        setups_dir = DEFAULT_SETUPS_DIR
    else:
        setups_dir = Path(setups_dir)

    setups_dir.mkdir(parents=True, exist_ok=True)

    yaml_path = setups_dir / f"{setup.id}.yml"

    with open(yaml_path, "w", encoding="utf-8", newline="\n") as f:
        yaml.dump(
            setup.to_dict(),
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

    return yaml_path
