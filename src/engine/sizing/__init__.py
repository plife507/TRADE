"""
Unified position sizing module for TRADE engines.

This module provides a single source of truth for position sizing logic
used by PlayEngine in all modes (backtest, demo, live).

Components:
    - SizingModel: Core sizing calculations
    - SizingResult: Result dataclass with size and metadata
    - SizingConfig: Configuration for sizing behavior

Usage:
    from src.engine.sizing import SizingModel, SizingConfig, SizingResult

    config = SizingConfig(
        initial_equity=10000.0,
        risk_per_trade_pct=1.0,
        max_leverage=10.0,
        sizing_model="percent_equity",
    )
    model = SizingModel(config)
    result = model.size_order(equity=10000.0, entry_price=50000.0, stop_loss=49000.0)
"""

from .model import SizingModel, SizingResult, SizingConfig

__all__ = [
    "SizingModel",
    "SizingResult",
    "SizingConfig",
]
