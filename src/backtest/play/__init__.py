"""
Play package - Declarative strategy specification with Feature Registry.

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
    TrailingConfig,
    BreakEvenConfig,
)
from .play import (
    SyntheticConfig,
    PositionMode,
    PositionPolicy,
    Play,
    load_play,
    list_plays,
    PLAYS_DIR,
    VALIDATION_PLAYS_DIR,
    STRESS_PLAYS_DIR,
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
    "TrailingConfig",
    "BreakEvenConfig",
    # Play
    "SyntheticConfig",
    "PositionMode",
    "PositionPolicy",
    "Play",
    "load_play",
    "list_plays",
    "PLAYS_DIR",
    "VALIDATION_PLAYS_DIR",
    "STRESS_PLAYS_DIR",
]
