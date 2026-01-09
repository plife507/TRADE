"""
Play package - Declarative strategy specification with Feature Registry.

Re-exports all Play-related classes and functions for backward compatibility.

Usage:
    from src.backtest.play import Play, load_play, AccountConfig
"""

from .config_models import (
    ExitMode,
    FeeModel,
    AccountConfig,
)
from .risk_model import (
    StopLossType,
    TakeProfitType,
    SizingModel,
    StopLossRule,
    TakeProfitRule,
    SizingRule,
    RiskModel,
)
from .play import (
    PositionMode,
    PositionPolicy,
    Play,
    load_play,
    list_plays,
    PLAYS_DIR,
)

__all__ = [
    # Config models
    "ExitMode",
    "FeeModel",
    "AccountConfig",
    # Risk model
    "StopLossType",
    "TakeProfitType",
    "SizingModel",
    "StopLossRule",
    "TakeProfitRule",
    "SizingRule",
    "RiskModel",
    # Play
    "PositionMode",
    "PositionPolicy",
    "Play",
    "load_play",
    "list_plays",
    "PLAYS_DIR",
]
