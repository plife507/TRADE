"""
Block Dataclass and Loader.

Blocks are the smallest reusable units in the trading hierarchy:
    Block (smallest) → Play → System

A Block defines:
- Features (indicators/structures) it requires
- A condition expression (DSL) that defines when the block is active

Blocks are referenced from Play actions using:
    - block: <block_id>

Architecture Principle: Pure Data
- Block is an immutable dataclass
- load_block is a pure function (id -> Block)
- No side effects, no state

Schema (v1.0.0):
    version: "1.0.0"
    id: "rsi_oversold"
    name: "RSI Oversold"
    features:
      - id: rsi
        type: indicator
        indicator_type: rsi
        params: {length: 14}
    condition:
      lhs: {feature_id: rsi}
      op: lt
      rhs: 30

Required fields: id, version, features (≥1), condition
Not allowed: account, risk (inherited from Play)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# Default blocks directory
DEFAULT_BLOCKS_DIR = Path("strategies/blocks")


class BlockNotFoundError(Exception):
    """Raised when a block cannot be found."""

    def __init__(self, block_id: str, searched_paths: list[Path] | None = None):
        self.block_id = block_id
        self.searched_paths = searched_paths or []
        paths_str = ", ".join(str(p) for p in self.searched_paths)
        super().__init__(f"Block '{block_id}' not found. Searched: {paths_str}")


class BlockValidationError(Exception):
    """Raised when block validation fails."""

    def __init__(self, block_id: str, errors: list[str]):
        self.block_id = block_id
        self.errors = errors
        errors_str = "; ".join(errors)
        super().__init__(f"Invalid Block '{block_id}': {errors_str}")


@dataclass(frozen=True)
class Block:
    """
    A reusable atomic condition block (smallest unit in hierarchy).

    Blocks encapsulate common trading patterns and conditions that can be
    composed into Plays. They define what features they need and when
    they are considered "active".

    Hierarchy Position: Block → Play → System

    Attributes:
        id: Unique identifier (e.g., "rsi_oversold", "ema_pullback")
        version: Semantic version string
        name: Human-readable name
        description: Optional description of the block
        features: Tuple of feature dicts (indicators/structures this block needs)
        condition: DSL condition dict that defines when block is active
        tags: Optional categorization tags

    Example YAML (strategies/blocks/rsi_oversold.yml):
        version: "1.0.0"
        id: rsi_oversold
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

    NOT ALLOWED in Block (inherited from Play):
        - account configuration
        - risk configuration
    """

    # Identity (REQUIRED)
    id: str
    version: str

    # Human-readable (optional)
    name: str | None = None
    description: str | None = None

    # Features this block requires (REQUIRED, must have at least one)
    features: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    # Condition for when block is active (REQUIRED, DSL expression)
    condition: dict[str, Any] = field(default_factory=dict)

    # Tags for categorization (optional)
    tags: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self):
        """Validate the block on construction."""
        errors = self.validate()
        if errors:
            raise BlockValidationError(self.id or "<unknown>", errors)

    def validate(self) -> list[str]:
        """
        Validate the block configuration.

        Returns:
            List of error messages (empty if valid).
        """
        errors: list[str] = []

        # Required fields
        if not self.id:
            errors.append("id is required")
        if not self.version:
            errors.append("version is required")
        if not self.features:
            errors.append("features is required (must have at least one)")
        if not self.condition:
            errors.append("condition is required")

        # Validate features have required fields
        for i, feature in enumerate(self.features):
            if "id" not in feature:
                errors.append(f"features[{i}]: missing 'id' field")
            if "type" not in feature:
                errors.append(f"features[{i}]: missing 'type' field")

        return errors

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        d: dict[str, Any] = {
            "version": self.version,
            "id": self.id,
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
    def from_dict(cls, d: dict[str, Any]) -> Block:
        """
        Create Block from dictionary.

        Raises:
            BlockValidationError: If required fields missing or invalid.
        """
        return cls(
            id=d.get("id", ""),
            version=d.get("version", ""),
            name=d.get("name"),
            description=d.get("description"),
            features=tuple(d.get("features", [])),
            condition=d.get("condition", {}),
            tags=tuple(d.get("tags", [])),
        )

    def get_feature_ids(self) -> set[str]:
        """Get set of feature IDs this block requires."""
        return {f["id"] for f in self.features if "id" in f}

    def get_indicator_types(self) -> set[str]:
        """Get set of indicator types this block uses."""
        return {
            f["indicator_type"]
            for f in self.features
            if f.get("type") == "indicator" and "indicator_type" in f
        }


def load_block(
    block_id: str,
    blocks_dir: Path | str | None = None,
) -> Block:
    """
    Load a Block from YAML file.

    Pure function: (block_id, dir) -> Block

    Args:
        block_id: Block identifier (filename without .yml)
        blocks_dir: Directory containing block YAML files

    Returns:
        Block dataclass instance

    Raises:
        BlockNotFoundError: If block file not found
        BlockValidationError: If block YAML is invalid
    """
    if blocks_dir is None:
        blocks_dir = DEFAULT_BLOCKS_DIR
    else:
        blocks_dir = Path(blocks_dir)

    # Try to find the block file
    yaml_path = blocks_dir / f"{block_id}.yml"

    if not yaml_path.exists():
        raise BlockNotFoundError(block_id, [yaml_path])

    # Load and parse YAML
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if data is None:
        raise BlockValidationError(block_id, ["Block file is empty"])

    # Create Block from dict (validates on construction)
    return Block.from_dict(data)


def list_blocks(blocks_dir: Path | str | None = None) -> list[str]:
    """
    List all available block IDs.

    Args:
        blocks_dir: Directory containing block YAML files

    Returns:
        List of block IDs (filenames without .yml extension)
    """
    if blocks_dir is None:
        blocks_dir = DEFAULT_BLOCKS_DIR
    else:
        blocks_dir = Path(blocks_dir)

    if not blocks_dir.exists():
        return []

    return sorted([
        p.stem for p in blocks_dir.glob("*.yml")
        if not p.stem.startswith("_")  # Skip files starting with underscore
    ])


def save_block(
    block: Block,
    blocks_dir: Path | str | None = None,
) -> Path:
    """
    Save a Block to YAML file.

    Args:
        block: Block to save
        blocks_dir: Directory to save to

    Returns:
        Path to saved file
    """
    if blocks_dir is None:
        blocks_dir = DEFAULT_BLOCKS_DIR
    else:
        blocks_dir = Path(blocks_dir)

    blocks_dir.mkdir(parents=True, exist_ok=True)

    yaml_path = blocks_dir / f"{block.id}.yml"

    with open(yaml_path, "w", encoding="utf-8", newline="\n") as f:
        yaml.dump(
            block.to_dict(),
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

    return yaml_path
