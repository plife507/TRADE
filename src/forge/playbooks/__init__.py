"""
Playbooks Module.

A Playbook is a collection of Plays organized for a specific trading objective.

Playbooks define:
- A list of Plays with their roles (primary, filter, etc.)
- Execution priority order
- Optional allocation weights

Example use cases:
- "Trend Following Playbook" with multiple trend-based Plays
- "Mean Reversion Playbook" with oversold/overbought Plays
- "Multi-Asset Playbook" with Plays for different symbols

Usage:
    from src.forge.playbooks import Playbook, load_playbook, list_playbooks

    # Load a playbook
    playbook = load_playbook("trend_following")

    # Access plays
    for entry in playbook.plays:
        print(f"{entry.play_id}: {entry.role}")
"""

from src.forge.playbooks.playbook import (
    Playbook,
    PlaybookEntry,
    load_playbook,
    list_playbooks,
    save_playbook,
    PlaybookNotFoundError,
)

__all__ = [
    "Playbook",
    "PlaybookEntry",
    "load_playbook",
    "list_playbooks",
    "save_playbook",
    "PlaybookNotFoundError",
]
