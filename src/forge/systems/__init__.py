"""
Systems Module.

A System is the complete trading configuration combining:
- One or more Plays with weighted blending
- Regime-based weight adjustments
- Runtime configuration (risk, sizing)
- Deployment target (backtest, demo, live)

Systems represent production-ready trading configurations that have been
validated through the Forge workflow.

Hierarchy: Block → Play → System

Usage:
    from src.forge.systems import System, load_system, list_systems

    # Load a system
    system = load_system("btc_trend_v1")

    # Access plays
    for play_ref in system.plays:
        print(f"{play_ref.play_id}: weight={play_ref.base_weight}")
"""

from src.forge.systems.system import (
    System,
    PlayRef,
    RegimeWeight,
    load_system,
    list_systems,
    save_system,
    SystemNotFoundError,
)
from src.forge.systems.normalizer import normalize_system_strict

__all__ = [
    "System",
    "PlayRef",
    "RegimeWeight",
    "load_system",
    "list_systems",
    "save_system",
    "SystemNotFoundError",
    # Normalizer
    "normalize_system_strict",
]
