"""
Setups Module.

Reusable market condition blocks that can be composed into Plays.

A Setup defines:
- Features it needs (indicators, structures)
- A condition that must be true for the setup to be active

Setups are the building blocks of Plays - they encapsulate
common patterns like "RSI oversold", "EMA pullback", "support bounce".

Usage:
    from src.forge.setups import Setup, load_setup, list_setups

    # Load a setup
    setup = load_setup("rsi_oversold")

    # Use in Play blocks via setup reference
    # - setup: rsi_oversold
"""

from src.forge.setups.setup import (
    Setup,
    load_setup,
    list_setups,
    save_setup,
    SetupNotFoundError,
)

__all__ = [
    "Setup",
    "load_setup",
    "list_setups",
    "save_setup",
    "SetupNotFoundError",
]
