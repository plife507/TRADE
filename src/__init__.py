"""
TRADE - Bybit Trading Bot

A production-ready, modular trading bot for Bybit Unified Trading Account (UTA).
Provides complete Bybit API integration, all order types, position management,
risk controls, and diagnostic tools.
"""

__version__ = "1.0.0"
__author__ = "TRADE"

from .config import get_config, TradingMode
from .core import (
    ExchangeManager,
    RiskManager,
    panic_close_all,
)
from .data import get_market_data, get_historical_store

__all__ = [
    "__version__",
    "get_config",
    "TradingMode",
    "ExchangeManager",
    "RiskManager",
    "panic_close_all",
    "get_market_data",
    "get_historical_store",
]
