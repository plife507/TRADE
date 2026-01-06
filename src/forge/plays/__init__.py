"""
Plays - Complete strategy configurations.

Hierarchy: Block → Play (here) → System

A Play defines a complete trading strategy with:
- Features (indicators)
- Actions (entry/exit rules using DSL)
- Risk parameters (stop loss, take profit, sizing)
- Optional account configuration
"""

from .normalizer import normalize_play_strict

__all__ = [
    "normalize_play_strict",
]
