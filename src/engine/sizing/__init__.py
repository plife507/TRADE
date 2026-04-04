"""
Unified position sizing module for TRADE engines.

This module provides a single source of truth for position sizing logic
used by PlayEngine in all modes (backtest, live, shadow).

Components:
    - SizingModel: Core sizing calculations
    - SizingResult: Result dataclass with size and metadata
    - SizingConfig: Configuration for sizing behavior

Usage:
    All config flows from Play YAML via PlayEngine — no hardcoded values.
    See src/engine/play_engine.py:232 for the production wiring.
"""

from .model import SizingModel, SizingResult, SizingConfig

__all__ = [
    "SizingModel",
    "SizingResult",
    "SizingConfig",
]
