"""
Liquidation model for margin-based position liquidation.

Checks liquidation conditions and handles forced position closure.
"""

from .liquidation_model import LiquidationModel, LiquidationModelConfig

__all__ = [
    "LiquidationModel",
    "LiquidationModelConfig",
]

