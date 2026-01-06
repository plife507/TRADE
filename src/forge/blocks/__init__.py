"""
Blocks - Smallest reusable units in the trading hierarchy.

Hierarchy: Block (smallest) → Play → System

A Block defines:
- Features (indicators/structures) it requires
- A condition expression (DSL) that defines when active

Blocks are referenced from Play actions using:
    block: <block_id>
"""

from .block import (
    Block,
    BlockNotFoundError,
    BlockValidationError,
    load_block,
    list_blocks,
    save_block,
    DEFAULT_BLOCKS_DIR,
)

from .normalizer import (
    normalize_block_strict,
    NormalizationResult,
    NormalizationError,
)

__all__ = [
    # Block dataclass
    "Block",
    "BlockNotFoundError",
    "BlockValidationError",
    "load_block",
    "list_blocks",
    "save_block",
    "DEFAULT_BLOCKS_DIR",
    # Normalizer
    "normalize_block_strict",
    "NormalizationResult",
    "NormalizationError",
]
