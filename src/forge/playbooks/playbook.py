"""
Playbook Dataclass and Loader.

A Playbook is a collection of Plays organized for a specific trading objective.

Architecture Principle: Pure Data
- Playbook is an immutable dataclass
- load_playbook is a pure function (id -> Playbook)
- No side effects, no state
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# Default playbooks directory
DEFAULT_PLAYBOOKS_DIR = Path("configs/playbooks")


class PlaybookNotFoundError(Exception):
    """Raised when a playbook cannot be found."""

    def __init__(self, playbook_id: str, searched_paths: list[Path] | None = None):
        self.playbook_id = playbook_id
        self.searched_paths = searched_paths or []
        paths_str = ", ".join(str(p) for p in self.searched_paths)
        super().__init__(f"Playbook '{playbook_id}' not found. Searched: {paths_str}")


@dataclass(frozen=True)
class PlaybookEntry:
    """
    A single entry in a Playbook.

    Attributes:
        play_id: The ID of the Play (without .yml extension)
        role: The role of this Play in the playbook (e.g., "primary", "filter")
        weight: Optional allocation weight (0.0-1.0)
        enabled: Whether this entry is active (default True)
    """

    play_id: str
    role: str = "primary"
    weight: float | None = None
    enabled: bool = True

    def __post_init__(self):
        """Validate the entry."""
        if not self.play_id:
            raise ValueError("PlaybookEntry: play_id is required")
        if self.weight is not None and not (0.0 <= self.weight <= 1.0):
            raise ValueError(f"PlaybookEntry: weight must be 0.0-1.0, got {self.weight}")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        d: dict[str, Any] = {"play_id": self.play_id}
        if self.role != "primary":
            d["role"] = self.role
        if self.weight is not None:
            d["weight"] = self.weight
        if not self.enabled:
            d["enabled"] = self.enabled
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PlaybookEntry:
        """Create PlaybookEntry from dictionary."""
        return cls(
            play_id=d["play_id"],
            role=d.get("role", "primary"),
            weight=d.get("weight"),
            enabled=d.get("enabled", True),
        )


@dataclass(frozen=True)
class Playbook:
    """
    A collection of Plays organized for a specific trading objective.

    Attributes:
        id: Unique identifier (e.g., "trend_following", "mean_reversion")
        version: Semantic version string
        name: Human-readable name
        description: Optional description of the playbook
        plays: Tuple of PlaybookEntry objects
        tags: Tags for categorization

    Example YAML:
        id: trend_following
        version: "1.0.0"
        name: "Trend Following Playbook"
        description: "Collection of trend-based strategies"
        plays:
          - play_id: ema_crossover_1h
            role: primary
          - play_id: adx_filter_4h
            role: filter
        tags:
          - trend
          - momentum
    """

    # Identity
    id: str
    version: str
    name: str | None = None
    description: str | None = None

    # Plays in this playbook
    plays: tuple[PlaybookEntry, ...] = field(default_factory=tuple)

    # Tags for categorization
    tags: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self):
        """Validate the playbook."""
        errors = self.validate()
        if errors:
            raise ValueError(f"Invalid Playbook '{self.id}': {'; '.join(errors)}")

    def validate(self) -> list[str]:
        """Validate the playbook configuration."""
        errors = []

        if not self.id:
            errors.append("id is required")
        if not self.version:
            errors.append("version is required")
        if not self.plays:
            errors.append("at least one play is required")

        # Check for duplicate play_ids
        play_ids = [e.play_id for e in self.plays]
        if len(play_ids) != len(set(play_ids)):
            errors.append("duplicate play_id entries found")

        return errors

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        d = {
            "id": self.id,
            "version": self.version,
            "plays": [e.to_dict() for e in self.plays],
        }
        if self.name:
            d["name"] = self.name
        if self.description:
            d["description"] = self.description
        if self.tags:
            d["tags"] = list(self.tags)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Playbook:
        """Create Playbook from dictionary."""
        plays_data = d.get("plays", [])
        plays = tuple(PlaybookEntry.from_dict(e) for e in plays_data)

        return cls(
            id=d["id"],
            version=d["version"],
            name=d.get("name"),
            description=d.get("description"),
            plays=plays,
            tags=tuple(d.get("tags", [])),
        )

    def get_play_ids(self) -> list[str]:
        """Get list of all play IDs in this playbook."""
        return [e.play_id for e in self.plays]

    def get_enabled_plays(self) -> list[PlaybookEntry]:
        """Get list of enabled plays."""
        return [e for e in self.plays if e.enabled]

    def get_plays_by_role(self, role: str) -> list[PlaybookEntry]:
        """Get plays with a specific role."""
        return [e for e in self.plays if e.role == role and e.enabled]


def load_playbook(
    playbook_id: str,
    playbooks_dir: Path | str | None = None,
) -> Playbook:
    """
    Load a Playbook from YAML file.

    Pure function: (playbook_id, dir) -> Playbook

    Args:
        playbook_id: Playbook identifier (filename without .yml)
        playbooks_dir: Directory containing playbook YAML files

    Returns:
        Playbook dataclass instance

    Raises:
        PlaybookNotFoundError: If playbook file not found
        ValueError: If playbook YAML is invalid
    """
    if playbooks_dir is None:
        playbooks_dir = DEFAULT_PLAYBOOKS_DIR
    else:
        playbooks_dir = Path(playbooks_dir)

    # Try to find the playbook file
    yaml_path = playbooks_dir / f"{playbook_id}.yml"

    if not yaml_path.exists():
        raise PlaybookNotFoundError(playbook_id, [yaml_path])

    # Load and parse YAML
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if data is None:
        raise ValueError(f"Playbook file is empty: {yaml_path}")

    # Create Playbook from dict
    return Playbook.from_dict(data)


def list_playbooks(playbooks_dir: Path | str | None = None) -> list[str]:
    """
    List all available playbook IDs.

    Args:
        playbooks_dir: Directory containing playbook YAML files

    Returns:
        List of playbook IDs (filenames without .yml extension)
    """
    if playbooks_dir is None:
        playbooks_dir = DEFAULT_PLAYBOOKS_DIR
    else:
        playbooks_dir = Path(playbooks_dir)

    if not playbooks_dir.exists():
        return []

    return sorted([
        p.stem for p in playbooks_dir.glob("*.yml")
        if not p.stem.startswith("_")  # Skip files starting with underscore
    ])


def save_playbook(
    playbook: Playbook,
    playbooks_dir: Path | str | None = None,
) -> Path:
    """
    Save a Playbook to YAML file.

    Args:
        playbook: Playbook to save
        playbooks_dir: Directory to save to

    Returns:
        Path to saved file
    """
    if playbooks_dir is None:
        playbooks_dir = DEFAULT_PLAYBOOKS_DIR
    else:
        playbooks_dir = Path(playbooks_dir)

    playbooks_dir.mkdir(parents=True, exist_ok=True)

    yaml_path = playbooks_dir / f"{playbook.id}.yml"

    with open(yaml_path, "w", encoding="utf-8", newline="\n") as f:
        yaml.dump(
            playbook.to_dict(),
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

    return yaml_path
