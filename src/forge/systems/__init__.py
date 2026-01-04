"""
Systems Module.

A System is the complete trading configuration combining:
- One or more Playbooks
- Runtime configuration (risk, sizing)
- Deployment target (backtest, demo, live)

Systems represent production-ready trading configurations that have been
validated through the Forge workflow.

Usage:
    from src.forge.systems import System, load_system, list_systems

    # Load a system
    system = load_system("btc_trend_v1")

    # Access playbooks
    for playbook_ref in system.playbooks:
        print(f"{playbook_ref.playbook_id}: weight={playbook_ref.weight}")
"""

from src.forge.systems.system import (
    System,
    PlaybookRef,
    load_system,
    list_systems,
    save_system,
    SystemNotFoundError,
)

__all__ = [
    "System",
    "PlaybookRef",
    "load_system",
    "list_systems",
    "save_system",
    "SystemNotFoundError",
]
