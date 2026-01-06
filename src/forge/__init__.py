"""
The Forge - Development and validation environment for Plays.

This module provides the development workflow for trading strategies:
- Play validation and normalization
- Batch validation across multiple configurations
- Audit tools for parity and correctness verification
- Play generation from templates
- Block management (smallest reusable units)
- System management (deployment configurations)

Trading Hierarchy (smallest → largest):
    Block → Play → System

The Forge is the entry point for all strategy development work.
"""

from src.forge.blocks import (
    Block,
    load_block,
    list_blocks,
    save_block,
    BlockNotFoundError,
    BlockValidationError,
    normalize_block_strict,
    NormalizationResult,
    NormalizationError,
)

from src.forge.plays import normalize_play_strict

from src.forge.setups import (
    Setup,
    load_setup,
    list_setups,
    save_setup,
    SetupNotFoundError,
)

from src.forge.systems import (
    System,
    PlayRef,
    RegimeWeight,
    load_system,
    list_systems,
    save_system,
    SystemNotFoundError,
    normalize_system_strict,
)

__all__ = [
    # Blocks (smallest unit in hierarchy)
    "Block",
    "load_block",
    "list_blocks",
    "save_block",
    "BlockNotFoundError",
    "BlockValidationError",
    "normalize_block_strict",
    "NormalizationResult",
    "NormalizationError",
    # Plays (complete strategies)
    "normalize_play_strict",
    # Setups (deprecated - use Block instead)
    "Setup",
    "load_setup",
    "list_setups",
    "save_setup",
    "SetupNotFoundError",
    # Systems (multiple plays with regime conditions)
    "System",
    "PlayRef",
    "RegimeWeight",
    "load_system",
    "list_systems",
    "save_system",
    "SystemNotFoundError",
    "normalize_system_strict",
]
