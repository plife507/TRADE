"""
Backtest engine re-exports.

This module re-exports factory functions for backward compatibility.
The actual implementation is in engine_factory.py.

USAGE (Play-native factory):
    from src.backtest import load_play, create_engine_from_play, run_engine_with_play

    play = load_play("my_strategy")
    engine = create_engine_from_play(play, window_start, window_end)
    result = run_engine_with_play(engine, play)

NOTE: BacktestEngine class was deleted per "ALL FORWARD, NO LEGACY" principle.
Use create_engine_from_play() which returns a unified PlayEngine.
"""

# Re-export factory functions for backward compatibility
from .engine_factory import (
    run_backtest,
    create_engine_from_play,
    run_engine_with_play,
)

__all__ = [
    "run_backtest",
    "create_engine_from_play",
    "run_engine_with_play",
]
