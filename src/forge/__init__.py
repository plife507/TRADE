"""
The Forge - Development and validation environment for Plays.

This module provides the development workflow for trading strategies:
- Play validation and normalization
- Batch validation across multiple configurations
- Audit tools for parity and correctness verification
- Play generation from templates
- Setup management (reusable market conditions)
- Playbook management (collections of Plays)

The Forge is the entry point for all strategy development work.
"""

from src.forge.setups import (
    Setup,
    load_setup,
    list_setups,
    SetupNotFoundError,
)

__all__ = [
    # Setups (W4-P1)
    "Setup",
    "load_setup",
    "list_setups",
    "SetupNotFoundError",
]
