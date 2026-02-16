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
    ValidationConfig,
    PositionMode,
    PositionPolicy,
    Play,
    PlayInfo,
    load_play,
    list_plays,
    list_play_dirs,
    peek_play_yaml,
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
    "TrailingConfig",
    "BreakEvenConfig",
    # Play
    "ValidationConfig",
    "PositionMode",
    "PositionPolicy",
    "Play",
    "PlayInfo",
    "load_play",
    "list_plays",
    "list_play_dirs",
    "peek_play_yaml",
    "PLAYS_DIR",
]
