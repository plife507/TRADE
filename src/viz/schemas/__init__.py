"""
Artifact Schema Definitions.

Single source of truth for backtest artifact formats.
Both the backtest exporter and visualizer import from here.
"""

from .artifact_schema import (
    TRADES_SCHEMA,
    EQUITY_SCHEMA,
    RESULT_SCHEMA,
    TradeRecord,
    EquityPoint,
)

__all__ = [
    "TRADES_SCHEMA",
    "EQUITY_SCHEMA",
    "RESULT_SCHEMA",
    "TradeRecord",
    "EquityPoint",
]
