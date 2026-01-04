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
    save_setup,
    SetupNotFoundError,
)

from src.forge.playbooks import (
    Playbook,
    PlaybookEntry,
    load_playbook,
    list_playbooks,
    save_playbook,
    PlaybookNotFoundError,
)

from src.forge.systems import (
    System,
    PlaybookRef,
    load_system,
    list_systems,
    save_system,
    SystemNotFoundError,
)

__all__ = [
    # Setups (W4-P1/P2)
    "Setup",
    "load_setup",
    "list_setups",
    "save_setup",
    "SetupNotFoundError",
    # Playbooks (W4-P3)
    "Playbook",
    "PlaybookEntry",
    "load_playbook",
    "list_playbooks",
    "save_playbook",
    "PlaybookNotFoundError",
    # Systems (W4-P4)
    "System",
    "PlaybookRef",
    "load_system",
    "list_systems",
    "save_system",
    "SystemNotFoundError",
]
